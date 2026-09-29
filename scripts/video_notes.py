#!/usr/bin/env python3
"""Deterministic storage, evidence checks and scoped cleanup for video notes.
The host assistant supplies semantic summaries; this CLI never pretends to be an LLM.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import tempfile
import shutil
import html_reader

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "video-transcript-summary/v2"
LEGACY_SCHEMA = "video-transcript-summary/v1"
MEDIA_EXT = {".mp4", ".mp3", ".wav", ".m4a", ".aac", ".webm", ".mkv", ".mov", ".flv", ".ogg", ".opus", ".m4s", ".ts", ".part", ".ytdl"}
TIME = r"\d{1,3}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?"
HEADER = re.compile(rf"^(?:(?P<speaker>.+?)\s+)?[\[【]?(?P<time>{TIME})[\]】]?\s*$")
CUE = re.compile(rf"^\s*({TIME})\s*-->\s*({TIME})")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def put(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing a symlink destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n" if not isinstance(value, str) else value
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scoped(root, path):
    root = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.absolute()
    if not candidate.is_relative_to(root) or candidate == root:
        raise ValueError("Path leaves task directory")
    for part in (candidate, *candidate.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Refusing symlink path")
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("Resolved path leaves task directory")
    return candidate


def state(job):
    job = Path(job).absolute()
    if job.is_symlink():
        raise ValueError("Task root must not be a symlink")
    data = load(job / "task.json")
    if data.get("schema") not in {SCHEMA, LEGACY_SCHEMA} or data.get("job_root") != str(job.resolve()):
        raise ValueError("Not an owned task directory")
    return job, data


def source_value(text):
    urls = list(dict.fromkeys(re.findall(r"https?://[^\s<>\"“”]+", text)))
    if len(urls) != 1:
        raise ValueError("Provide exactly one HTTP(S) video URL per task")
    value = urls[0].rstrip("。，；！）】)")
    from urllib.parse import urlparse
    parsed = urlparse(value)
    if parsed.username or parsed.password or not parsed.hostname or any(c in value for c in "\r\n\x00"):
        raise ValueError("Invalid public video URL")
    import ipaddress
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Only public video URLs are accepted")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Private network URLs are not accepted")
    # Only a platform URL is handed to the existing video extractor, never shell code.
    return value


def new_job(output_root, name, source):
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "-", name).strip(". ")[:90] or "视频笔记"
    for i in range(1, 10000):
        job = root / (safe if i == 1 else f"{safe}-{i}")
        try:
            job.mkdir(mode=0o700)
            break
        except FileExistsError:
            continue
    else:
        raise ValueError("Too many tasks with same title")
    (job / ".work/media").mkdir(parents=True)
    (job / ".work/notes").mkdir()
    data = {"schema": SCHEMA, "job_root": str(job), "title": name, "source_url": source,
            "status": "created", "cloud_media": "not_uploaded", "local_cleanup": "pending"}
    put(job / "task.json", data)
    return job, data


def backend_path(value=None):
    candidates = [Path(value)] if value else [ROOT.parent.parent / ".skills/doubao-video-extract"]
    for candidate in candidates:
        script = candidate / "scripts/minutes/social_video_to_minutes.py"
        if script.is_file():
            return candidate.resolve(), script.resolve()
    raise ValueError("Video extractor unavailable; pass --backend-root with the installed skill directory")


def runtime_env():
    env = os.environ.copy()
    lib = ROOT / ".runtime/pythonlibs"
    if lib.is_dir():
        env["PYTHONPATH"] = str(lib) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def fetch(source, output_root, name, backend_root=None):
    source = source_value(source)
    backend, script = backend_path(backend_root)
    job, data = new_job(output_root, name, source)
    data["status"] = "transcribing"
    data["cloud_media"] = "may_be_retained_by_cloud_service"
    put(job / "task.json", data)
    print(json.dumps({"job": str(job), "status": "transcribing"}, ensure_ascii=False), flush=True)
    # The upstream helper executes lark-cli from its own skill root. Use its
    # documented /tmp output area for TEXT only, then archive under this job.
    # Do not move or copy user-owned files, and never put media in this staging area.
    with tempfile.TemporaryDirectory(prefix="video-notes-text-", dir="/tmp") as staging:
        notes_stage = Path(staging).resolve() / "notes"
        argv = [sys.executable, str(script), source, "--run-lark", "--json",
                "--output-dir", str(job / ".work/media"), "--audio-output-dir", str(job / ".work/media"),
                "--notes-output-dir", str(notes_stage)]
        with (job / ".work/backend-result.json").open("x", encoding="utf-8") as out, (job / ".work/backend-stderr.log").open("x", encoding="utf-8") as err:
            completed = subprocess.run(argv, cwd=backend, env=runtime_env(), stdout=out, stderr=err, check=False)
        if notes_stage.exists():
            for path in notes_stage.rglob("*"):
                checked = scoped(notes_stage, path)
                if checked.is_file():
                    dest = scoped(job, Path(".work/notes") / checked.relative_to(notes_stage))
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(checked, dest)
    try:
        result = load(job / ".work/backend-result.json")
    except (ValueError, OSError):
        data["status"] = "blocked"
        put(job / "task.json", data)
        raise ValueError(f"Backend did not return JSON; inspect {job / '.work/backend-result.json'}")
    if completed.returncode or not result.get("success"):
        data.update(status="blocked", error=result.get("error", "Backend failed"))
        put(job / "task.json", data)
        raise ValueError(f"Extraction blocked: {data['error']}; job={job}")
    for key in ("video_path", "media_path"):
        if result.get(key):
            try:
                scoped(job / ".work/media", result[key])
            except ValueError:
                data.update(status="blocked", error="Backend used an out-of-scope media directory; do not delete it automatically")
                put(job / "task.json", data)
                raise ValueError(data["error"])
    lark = result.get("lark_result", {})
    data["minute_url"] = lark.get("minute_url")
    data["wait_estimate"] = lark.get("wait_estimate")
    data["metadata"] = result.get("metadata", {})
    data["platform"] = result.get("platform")
    data["status"] = "awaiting_transcript" if lark.get("ready_state") != "ready" else "transcript_available"
    put(job / "task.json", data)
    if lark.get("ready_state") == "ready" and lark.get("transcript_file"):
        returned = Path(lark["transcript_file"])
        relative = returned.relative_to(notes_stage)
        transcript = scoped(job / ".work/notes", relative)
        return ingest(job, transcript, "cloud_asr")
    return {"job": str(job), "status": data["status"], "message": "Resume existing minute; do not upload again. Full transcript required before finalize."}


def recover(job):
    job, data = state(job)
    if data["status"] in {"needs_summary", "ready", "complete"}:
        return {"job": str(job), "status": data["status"], "message": "No upload or recovery needed"}
    backend = load(job / ".work/backend-result.json")
    token = backend.get("lark_result", {}).get("minute_token")
    if not token:
        match = re.search(r"minute-tokens.*?, .*?([a-z0-9]{20,})", backend.get("error", ""))
        token = match.group(1) if match else None
    if not token or not re.fullmatch(r"[a-z0-9]+", token):
        raise ValueError("No existing cloud task identifier found; do not guess or reupload")
    proc = subprocess.run(["lark-cli", "vc", "+notes", "--minute-tokens", token,
                           "--output-dir", "./.work/notes", "--format", "json"],
                          cwd=job, text=True, capture_output=True, check=False)
    put(job / ".work/recovered-notes.json", proc.stdout)
    put(job / ".work/recovered-stderr.log", proc.stderr)
    if proc.returncode:
        raise ValueError("Cloud transcript retrieval failed; inspect recovered-notes.json")
    result = json.loads(proc.stdout)
    notes = result.get("data", {}).get("notes", [])
    matched = [n for n in notes if n.get("minute_token") == token]
    if not result.get("ok") or len(matched) != 1:
        raise ValueError("No unique cloud transcription result")
    note = matched[0]
    if note.get("error"):
        data.update(status="awaiting_transcript", error=note["error"])
        put(job / "task.json", data)
        raise ValueError(f"Cloud transcript not ready: {note['error']}")
    path = note.get("artifacts", {}).get("transcript_file")
    if not path:
        raise ValueError("Cloud result has no transcript; no summary generated")
    data.update(status="transcript_available", cloud_media="may_be_retained_by_cloud_service")
    data.pop("error", None)
    put(job / "task.json", data)
    return ingest(job, scoped(job, path), "cloud_asr")


def timestamp(value):
    parts = value.replace(",", ".").split(":")
    nums = [float(p) for p in parts]
    if not all(math.isfinite(p) and p >= 0 for p in nums) or nums[-1] >= 60 or (len(nums) == 3 and nums[-2] >= 60):
        raise ValueError("Invalid timestamp")
    return round(nums[-1] + nums[-2] * 60 + (nums[0] * 3600 if len(nums) == 3 else 0), 3)


def clock(seconds):
    if seconds is None:
        return "时间未知"
    millis = round(seconds * 1000)
    hours, rem = divmod(millis, 3600000)
    minutes, rem = divmod(rem, 60000)
    sec, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{sec:02}" + (f".{ms:03}" if ms else "")


def parse_transcript(text):
    if not text.strip():
        raise ValueError("Empty transcript")
    segments, lines = [], []
    start, speaker = None, None

    def finish():
        nonlocal lines
        content = "\n".join(lines).strip()
        if content:
            segments.append({"id": f"S{len(segments)+1:04}", "start_seconds": start, "speaker": speaker, "text": content})
        lines = []

    raw = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    for i, line in enumerate(raw):
        cue = CUE.match(line)
        header = HEADER.match(line.strip())
        if line.strip().isdigit() and i + 1 < len(raw) and CUE.match(raw[i+1]):
            continue
        if line.strip() == "WEBVTT":
            continue
        if cue or header:
            finish()
            start = timestamp(cue.group(1) if cue else header.group("time"))
            speaker = None if cue else header.group("speaker")
        elif not line.strip() and start is None:
            finish()
        else:
            lines.append(line)
    finish()
    if not segments:
        raise ValueError("Transcript contains no text")
    # Never invent timestamps or silently reorder content.
    times = [s["start_seconds"] for s in segments if s["start_seconds"] is not None]
    if times != sorted(times):
        raise ValueError("Non-monotonic timestamps; inspect original transcript")
    return segments


def chunk_segments(segments, limit=12000):
    chunks, current, size = [], [], 0
    for segment in segments:
        content = segment["text"]
        pieces = [content[i:i+limit] for i in range(0, len(content), limit)]
        for index, piece in enumerate(pieces):
            item = dict(segment, text=piece, part=index+1, parts=len(pieces))
            if current and size + len(piece) > limit:
                chunks.append(current)
                current, size = [], 0
            current.append(item)
            size += len(piece)
    if current:
        chunks.append(current)
    return chunks


def md(value):
    return html.escape(str(value), quote=False).replace("[", "\\[").replace("]", "\\]")


def ingest(job, transcript, method="cloud_asr"):
    job, data = state(job)
    if data["status"] in {"ready", "complete"}:
        raise ValueError("Completed task is immutable; create a new task for a revision")
    source = Path(transcript).resolve()
    text = source.read_text(encoding="utf-8-sig")
    segments = parse_transcript(text)
    if (job / "transcript.txt").exists():
        if (job / "transcript.txt").read_text(encoding="utf-8") != text:
            raise ValueError("Transcript differs from existing archive; create a new task")
    put(job / "transcript.txt", text)
    put(job / "transcript.json", {"source_url": data["source_url"], "method": method, "segments": segments})
    document = [f"# {md(data['title'])}｜文字稿", "", f"来源：{data['source_url']}", "",
                f"文字来源：{'云端 ASR 自动转写' if method == 'cloud_asr' else '用户提供的文字/字幕文件'}。不是人工核对稿；专名、数字和否定词可能有识别错误。", "",
                "仅保留来源实际返回的时间戳；时间未知处不推测。", ""]
    for s in segments:
        document.extend([f"## {s['id']} · {clock(s['start_seconds'])}", "", md(s["text"]), ""])
    put(job / "文字稿.md", "\n".join(document))
    chunks = chunk_segments(segments)
    paths = []
    for i, values in enumerate(chunks, 1):
        path = job / f".work/chunks/{i:03}.json"
        put(path, {"chunk_index": i, "chunk_count": len(chunks), "segments": values})
        paths.append(str(path.relative_to(job)))
    data.update(status="needs_summary", transcript_method=method, segment_count=len(segments),
                character_count=len(text), chunks=paths, transcript_sha256=digest(job / "transcript.txt"))
    put(job / "task.json", data)
    return {"job": str(job), "status": "needs_summary", "segments": len(segments), "chunks": paths}


def validate_summary(summary, segments):
    by_id = {s["id"]: s for s in segments}
    if set(summary.get("covered_segment_ids", [])) != set(by_id):
        raise ValueError("covered_segment_ids must cover the complete transcript, no missing or invented IDs")
    overview = summary.get("overview")
    if not isinstance(overview, str) or not overview.strip():
        raise ValueError("Missing overview")
    for key in ("takeaways", "chapters", "evidence", "caveats"):
        if not isinstance(summary.get(key), list) or not summary[key]:
            raise ValueError(f"Missing {key}")
    for key in ("takeaways", "chapters", "evidence", "actions"):
        for item in summary.get(key, []):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
                raise ValueError(f"Invalid {key} item")
            refs = item.get("refs", [])
            if not refs:
                raise ValueError(f"Each {key} item needs transcript evidence")
            for ref in refs:
                segment = by_id.get(ref.get("id"))
                quote = ref.get("quote")
                if not segment or not isinstance(quote, str) or not quote.strip() or quote not in segment["text"]:
                    raise ValueError(f"Invalid evidence reference in {key}: {ref.get('id')}")
    if not all(isinstance(x, str) and x.strip() for x in summary["caveats"]):
        raise ValueError("Invalid caveats")
    return by_id


def render_summary(data, summary, by_id):
    result = [f"# {md(data['title'])}｜结构化总结", "", f"视频来源：{data['source_url']}", "",
              "> 以下是视频内容与观点的整理，未作外部事实核验。引文来自自动转写，须结合原视频核对。", "",
              "## 一句话概括", "", md(summary["overview"]), ""]
    for field, title in (("takeaways", "核心结论"), ("chapters", "分段要点"), ("evidence", "关键论据与数据"), ("actions", "视频明确提出的建议")):
        result.extend([f"## {title}", ""])
        values = summary.get(field, [])
        if not values:
            result.extend(["视频未明确提出可执行建议。", ""])
        for i, item in enumerate(values, 1):
            result.extend([f"### {i}. {md(item.get('title', '要点'))}", "", md(item["text"]), ""])
            for ref in item["refs"]:
                seg = by_id[ref["id"]]
                result.extend([f"> 原稿 {ref['id']} · {clock(seg['start_seconds'])}：{md(ref['quote'])}", ""])
    result.extend(["## 不确定性与核验提醒", ""])
    result.extend(f"- {md(item)}" for item in summary["caveats"])
    result.extend(["", "## 媒体与隐私说明", "", "本工具只清理本任务在本机生成的临时音视频，不处理用户已有文件。云端转写服务可能保留音频及妙记；本地清理不等于云端删除。清理的实际状态以 task.json 为准。", ""])
    return "\n".join(result)


def verify(job):
    job, data = state(job)
    if data["status"] not in {"ready", "complete"}:
        raise ValueError("Task is not ready for delivery or cleanup")
    required = {"文字稿.md", "总结.md", "transcript.txt", "transcript.json", "summary.json"}
    if data["schema"] == SCHEMA:
        required.add(html_reader.FILENAME)
    if set(data.get("artifacts", {})) != required:
        raise ValueError("Artifact manifest is incomplete or contains unexpected files")
    for name, expected in data["artifacts"].items():
        path = scoped(job, name)
        if not path.is_file() or not path.stat().st_size or digest(path) != expected:
            raise ValueError(f"Artifact missing or altered: {name}")
    segments = load(job / "transcript.json")["segments"]
    validate_summary(load(job / "summary.json"), segments)
    if parse_transcript((job / "transcript.txt").read_text(encoding="utf-8")) != segments:
        raise ValueError("Normalized transcript differs from original")
    return {"passed": True, "artifacts": list(data["artifacts"]), "segments": len(segments)}


def finalize(job, summary_file):
    job, data = state(job)
    if data["status"] != "needs_summary":
        raise ValueError("Task is not awaiting summary")
    if digest(job / "transcript.txt") != data["transcript_sha256"]:
        raise ValueError("Original transcript changed")
    segments = load(job / "transcript.json")["segments"]
    summary = load(summary_file)
    by_id = validate_summary(summary, segments)
    put(job / "summary.json", summary)
    put(job / "总结.md", render_summary(data, summary, by_id))
    page = html_reader.render(data, summary, segments, (job / "transcript.txt").read_text(encoding="utf-8"))
    put(job / html_reader.FILENAME, page)
    names = ["文字稿.md", "总结.md", "transcript.txt", "transcript.json", "summary.json", html_reader.FILENAME]
    data.update(schema=SCHEMA, status="ready", html_renderer=html_reader.VERSION,
                artifacts={name: digest(job / name) for name in names})
    put(job / "task.json", data)
    return verify(job)


def render_html(job):
    """Add/update the reader without touching source transcript or repeating ASR."""
    verify(job)
    job, data = state(job)
    destination = scoped(job, html_reader.FILENAME)
    if destination.exists() and html_reader.FILENAME not in data.get("artifacts", {}):
        raise ValueError("Existing HTML is not owned by this task; refusing to overwrite")
    if destination.exists():
        backup_root = scoped(job, "_backup")
        backup_root.mkdir(exist_ok=True)
        for number in range(1, 10000):
            backup = scoped(job, backup_root / f"视频笔记-v{number}.html")
            if not backup.exists():
                shutil.copy2(destination, backup)
                break
        else:
            raise ValueError("Too many HTML backup revisions")
    segments = load(job / "transcript.json")["segments"]
    summary = load(job / "summary.json")
    raw = (job / "transcript.txt").read_text(encoding="utf-8")
    put(destination, html_reader.render(data, summary, segments, raw))
    data["schema"] = SCHEMA
    data["html_renderer"] = html_reader.VERSION
    data["artifacts"][html_reader.FILENAME] = digest(destination)
    put(job / "task.json", data)
    return verify(job)


def cleanup(job, apply=False):
    verified = verify(job)
    job, data = state(job)
    if html_reader.FILENAME not in data.get("artifacts", {}):
        raise ValueError("HTML is required before cleanup; run render-html for this legacy task")
    media = scoped(job, ".work/media")
    files = []
    if media.exists():
        for path in media.rglob("*"):
            scoped(job, path)
            if path.is_file():
                if path.suffix.lower() not in MEDIA_EXT:
                    raise ValueError(f"Unexpected file in media directory; not deleted: {path.name}")
                files.append(path)
    plan = [str(p.relative_to(job)) for p in files]
    if apply:
        for path in files:
            scoped(job, path).unlink()
        remaining = [p for p in media.rglob("*") if p.is_file()] if media.exists() else []
        if remaining:
            raise ValueError("Media cleanup incomplete")
        previous = data.get("deleted_media", [])
        data.update(status="complete", local_cleanup="complete", deleted_media=list(dict.fromkeys(previous + plan)))
        put(job / "task.json", data)
        verify(job)
    return {"passed": verified["passed"], "applied": apply, "media_files": plan,
            "cloud_media": data["cloud_media"], "job": str(job)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("fetch", "init"):
        p = sub.add_parser(command)
        p.add_argument("--source-file", required=True, help="UTF-8 file containing one video URL/share text")
        p.add_argument("--output-root", required=True)
        p.add_argument("--name", required=True)
        if command == "fetch":
            p.add_argument("--backend-root")
    p = sub.add_parser("ingest")
    p.add_argument("--job", required=True)
    p.add_argument("--transcript", required=True)
    p.add_argument("--method", choices=["cloud_asr", "provided_transcript"], default="cloud_asr")
    p = sub.add_parser("finalize")
    p.add_argument("--job", required=True)
    p.add_argument("--summary", required=True)
    for command in ("verify", "cleanup", "recover", "render-html"):
        p = sub.add_parser(command)
        p.add_argument("--job", required=True)
        if command == "cleanup":
            p.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.command in {"fetch", "init"}:
            source = Path(args.source_file).read_text(encoding="utf-8-sig")
            if args.command == "fetch":
                result = fetch(source, args.output_root, args.name, args.backend_root)
            else:
                job, data = new_job(args.output_root, args.name, source_value(source))
                result = {"job": str(job), "status": data["status"]}
        elif args.command == "ingest":
            result = ingest(args.job, args.transcript, args.method)
        elif args.command == "finalize":
            result = finalize(args.job, args.summary)
        elif args.command == "verify":
            result = verify(args.job)
        elif args.command == "recover":
            result = recover(args.job)
        elif args.command == "render-html":
            result = render_html(args.job)
        else:
            result = cleanup(args.job, args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

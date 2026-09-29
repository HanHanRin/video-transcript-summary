#!/usr/bin/env python3
"""Offline regression tests. No network calls, uploads, or user media access."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("video_notes", Path(__file__).with_name("video_notes.py"))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

TEXT = "讲解者 00:00:01\n视频介绍相机定位。\n\n讲解者 00:00:08\n高端机型也有不同用途。\n"


class VideoNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="video-notes-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def prepared(self):
        job, _ = v.new_job(self.root, "测试笔记", "https://www.bilibili.com/video/BVtest/")
        original = self.root / "original.txt"
        original.write_text(TEXT, encoding="utf-8")
        v.ingest(job, original)
        segments = v.load(job / "transcript.json")["segments"]
        entry = {"title": "定位", "text": "视频介绍不同相机的定位。", "refs": [{"id": "S0001", "quote": "视频介绍相机定位。"}]}
        summary = {"overview": "视频讨论相机定位。", "takeaways": [entry], "chapters": [entry], "evidence": [entry], "actions": [], "caveats": ["自动转写尚未回听核实。"], "covered_segment_ids": [s["id"] for s in segments]}
        draft = job / ".work/summary-draft.json"
        v.put(draft, summary)
        return job, summary, draft, segments

    def test_share_preserves_query(self):
        url = "https://www.bilibili.com/video/BVtest/?p=2&x=value"
        self.assertEqual(v.source_value("标题 " + url), url)

    def test_multiple_urls_rejected(self):
        with self.assertRaises(ValueError):
            v.source_value("https://a.test/ https://b.test/")

    def test_parse_lark(self):
        s = v.parse_transcript(TEXT)
        self.assertEqual(len(s), 2)
        self.assertEqual(s[1]["start_seconds"], 8)

    def test_srt(self):
        s = v.parse_transcript("1\n00:00:01,200 --> 00:00:03,000\n你好\n\n2\n00:00:04,000 --> 00:00:06,000\n世界")
        self.assertEqual([x["text"] for x in s], ["你好", "世界"])
        self.assertEqual(s[0]["start_seconds"], 1.2)

    def test_vtt(self):
        s = v.parse_transcript("WEBVTT\n\n00:01.000 --> 00:02.000\n你好")
        self.assertEqual(s[0]["text"], "你好")

    def test_plain_text_preserved(self):
        s = v.parse_transcript("开场介绍\n\n正文段落")
        self.assertEqual(len(s), 2)
        self.assertTrue(all(x["start_seconds"] is None for x in s))

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            v.parse_transcript(" \n")

    def test_invalid_time_rejected(self):
        with self.assertRaises(ValueError):
            v.timestamp("00:68:11")

    def test_unordered_times_rejected(self):
        with self.assertRaises(ValueError):
            v.parse_transcript("甲 00:00:08\n先\n甲 00:00:01\n后")

    def test_chunks_preserve_every_character(self):
        segments = v.parse_transcript("甲 00:00:01\n" + "测试"*19000)
        chunks = v.chunk_segments(segments)
        self.assertEqual("".join(x["text"] for c in chunks for x in c), segments[0]["text"])
        self.assertTrue(all(sum(len(x["text"]) for x in c) <= 12000 for c in chunks))

    def test_no_overwrite(self):
        a, _ = v.new_job(self.root, "同名", "https://a.test/")
        b, _ = v.new_job(self.root, "同名", "https://a.test/")
        self.assertNotEqual(a, b)

    def test_fake_quote_rejected(self):
        job, summary, draft, segments = self.prepared()
        summary["takeaways"][0]["refs"][0]["quote"] = "不存在的引文"
        with self.assertRaises(ValueError):
            v.validate_summary(summary, segments)

    def test_incomplete_coverage_rejected(self):
        job, summary, draft, segments = self.prepared()
        summary["covered_segment_ids"] = ["S0001"]
        with self.assertRaises(ValueError):
            v.validate_summary(summary, segments)

    def test_cleanup_requires_summary(self):
        job, _, _, _ = self.prepared()
        with self.assertRaises(ValueError):
            v.cleanup(job, True)

    def test_complete_and_idempotent_cleanup(self):
        job, _, draft, _ = self.prepared()
        media = job / ".work/media/test.mp3"
        media.write_bytes(b"test media")
        user_media = self.root / "user.mp4"
        user_media.write_bytes(b"user media")
        self.assertTrue(v.finalize(job, draft)["passed"])
        self.assertFalse(v.cleanup(job)["applied"])
        self.assertTrue(media.exists())
        v.cleanup(job, True)
        self.assertFalse(media.exists())
        self.assertTrue(user_media.exists())
        self.assertEqual(v.cleanup(job, True)["media_files"], [])
        self.assertTrue(v.verify(job)["passed"])

    def test_tamper_blocks_cleanup(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        (job / "总结.md").write_text("tampered", encoding="utf-8")
        with self.assertRaises(ValueError):
            v.cleanup(job, True)

    def test_symlink_blocks_cleanup(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        original = self.root / "outside.mp3"
        original.write_bytes(b"keep")
        (job / ".work/media/link.mp3").symlink_to(original)
        with self.assertRaises(ValueError):
            v.cleanup(job, True)
        self.assertTrue(original.exists())

    def test_foreign_file_blocks_cleanup(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        (job / ".work/media/keep.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            v.cleanup(job, True)

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            v.scoped(self.root, "../outside.mp3")

    def test_private_url_rejected(self):
        for url in ("http://localhost/video.mp4", "http://127.0.0.1/video.mp4", "http://192.168.1.2/a.mp4"):
            with self.assertRaises(ValueError):
                v.source_value(url)

    def test_manifest_missing_entry_blocks_cleanup(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        manifest = v.load(job / "task.json")
        manifest["artifacts"].pop("文字稿.md")
        v.put(job / "task.json", manifest)
        with self.assertRaises(ValueError):
            v.cleanup(job, True)

    def test_fetch_text_staging_contract(self):
        from unittest.mock import patch
        backend = self.root / "backend"
        (backend / "scripts/minutes").mkdir(parents=True)
        (backend / "scripts/minutes/social_video_to_minutes.py").write_text("", encoding="utf-8")
        def fake_run(argv, **kwargs):
            stage = Path(argv[argv.index("--notes-output-dir") + 1])
            media = Path(argv[argv.index("--output-dir") + 1])
            (stage / "result").mkdir(parents=True)
            (stage / "result/transcript.txt").write_text(TEXT, encoding="utf-8")
            (media / "clip.mp4").write_bytes(b"media")
            (media / "clip.mp3").write_bytes(b"audio")
            import json
            json.dump({"success": True, "video_path": str(media/"clip.mp4"), "media_path": str(media/"clip.mp3"), "lark_result": {"ready_state": "ready", "transcript_file": str(stage/"result/transcript.txt")}}, kwargs["stdout"])
            return type("Completed", (), {"returncode": 0})()
        with patch.object(v.subprocess, "run", side_effect=fake_run):
            result = v.fetch("https://www.bilibili.com/video/BVtest/", self.root, "mock integration", backend)
        job = Path(result["job"])
        self.assertEqual(result["status"], "needs_summary")
        self.assertEqual((job/"transcript.txt").read_text(encoding="utf-8"), TEXT)
        self.assertTrue((job/".work/media/clip.mp3").exists())

    def test_html_generated_by_finalize(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        manifest = v.load(job / "task.json")
        self.assertEqual(manifest["schema"], v.SCHEMA)
        self.assertIn(v.html_reader.FILENAME, manifest["artifacts"])
        self.assertTrue((job / v.html_reader.FILENAME).is_file())

    def test_missing_html_blocks_cleanup(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        (job / v.html_reader.FILENAME).unlink()
        with self.assertRaises(ValueError):
            v.cleanup(job, True)

    def test_tampered_html_blocks_cleanup(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        (job / v.html_reader.FILENAME).write_text("changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            v.cleanup(job, True)

    def test_legacy_upgrade_preserves_text_and_state(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        v.cleanup(job, True)
        manifest = v.load(job / "task.json")
        manifest["schema"] = v.LEGACY_SCHEMA
        manifest["artifacts"].pop(v.html_reader.FILENAME)
        (job / v.html_reader.FILENAME).unlink()
        v.put(job / "task.json", manifest)
        before = {name: v.digest(job / name) for name in manifest["artifacts"]}
        with self.assertRaises(ValueError):
            v.cleanup(job, True)
        self.assertTrue(v.render_html(job)["passed"])
        after = v.load(job / "task.json")
        self.assertEqual(after["status"], "complete")
        self.assertTrue(all(v.digest(job / name) == sha for name, sha in before.items()))

    def test_html_revision_keeps_backup(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        previous = (job / v.html_reader.FILENAME).read_bytes()
        v.render_html(job)
        self.assertEqual((job / "_backup/视频笔记-v1.html").read_bytes(), previous)

    def test_legacy_foreign_html_not_overwritten(self):
        job, _, draft, _ = self.prepared()
        v.finalize(job, draft)
        data = v.load(job / "task.json")
        data["schema"] = v.LEGACY_SCHEMA
        data["artifacts"].pop(v.html_reader.FILENAME)
        v.put(job / "task.json", data)
        (job / v.html_reader.FILENAME).write_text("user file", encoding="utf-8")
        with self.assertRaises(ValueError):
            v.render_html(job)

    def test_html_escapes_untrusted_content(self):
        job, summary, draft, segments = self.prepared()
        data = v.load(job / "task.json")
        data["title"] = '<script>alert("x")</script>'
        summary["overview"] = '<img src=x onerror="alert(1)">'
        result = v.html_reader.render(data, summary, segments, TEXT)
        self.assertNotIn('<img src=x', result)
        self.assertNotIn('<script>alert', result)
        self.assertIn('&lt;script&gt;', result)

    def test_html_rejects_unsafe_source_url(self):
        for value in ('javascript:alert(1)', 'data:text/html,bad', 'file:///etc/passwd'):
            with self.assertRaises(ValueError):
                v.html_reader.public_url(value)

    def test_bilibili_time_link_preserves_part(self):
        from urllib.parse import urlsplit, parse_qs
        target = v.html_reader.video_link('https://www.bilibili.com/video/BVtest/?p=2&share_source=copy&t=2', 74.5)
        query = parse_qs(urlsplit(target).query)
        self.assertEqual(query['p'], ['2'])
        self.assertEqual(query['t'], ['74'])
        self.assertEqual(query['share_source'], ['copy'])

    def test_no_fake_duration(self):
        self.assertIsNone(v.html_reader.duration_from_text(TEXT, {}))
        self.assertEqual(v.html_reader.duration_from_text('2026|14min 20s\n', {}), '14:20')

    def test_raw_transcript_is_exact(self):
        job, _, _, _ = self.prepared()
        self.assertEqual((job / "transcript.txt").read_text(encoding="utf-8"), TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Offline, deterministic HTML reader for validated video notes (stdlib only)."""
from __future__ import annotations

import html
import math
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

VERSION = "2.0"
FILENAME = "视频笔记.html"


def esc(value):
    return html.escape(str(value), quote=True)


def public_url(value):
    value = str(value).strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("HTML source link must be an HTTP(S) URL without credentials")
    if any(ord(c) < 32 for c in value):
        raise ValueError("Invalid control character in source URL")
    return value


def time_label(value):
    if value is None:
        return "无时间戳"
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Invalid segment time")
    seconds = int(value)
    hour, rem = divmod(seconds, 3600)
    minute, sec = divmod(rem, 60)
    return f"{hour:02}:{minute:02}:{sec:02}" if hour else f"{minute:02}:{sec:02}"


def video_link(source, start):
    parsed = urlsplit(source)
    host = (parsed.hostname or "").lower()
    if start is not None and (host == "bilibili.com" or host.endswith(".bilibili.com")):
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "t"]
        query.append(("t", str(int(start))))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    return source


def duration_from_text(text, metadata):
    # Explicit duration only; never confuse the last segment start with duration.
    value = metadata.get("duration") if isinstance(metadata, dict) else None
    if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
        return time_label(value)
    match = re.search(r"\|\s*(?:(\d+)h\s*)?(?:(\d+)min\s*)?(\d+)s\s*$", text.splitlines()[0] if text else "")
    if match:
        hours, minutes, seconds = (int(x or 0) for x in match.groups())
        return time_label(hours * 3600 + minutes * 60 + seconds)
    return None


CSS = r"""
:root{--ink:#192c37;--muted:#526874;--accent:#007c78;--wash:#e6f4f1;--paper:#fff;--canvas:#f1f5f7;--line:#d5e0e4;--note:#f6efe0;--note-ink:#695221;--radius:12px}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}body{margin:0;background:var(--canvas);color:var(--ink);font:16px/1.8 "PingFang SC","Microsoft YaHei",system-ui,sans-serif}a{color:var(--accent);text-underline-offset:4px}button,input{font:inherit}a,button,summary{touch-action:manipulation}a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:4px}button{cursor:pointer}button:disabled{cursor:default}.topbar{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid var(--line)}.top-inner{max-width:1260px;margin:auto;display:flex;justify-content:space-between;gap:16px;align-items:center;padding:12px 28px}.brand{display:flex;align-items:center;gap:10px;font-weight:650;text-decoration:none;color:var(--ink)}.brand svg{width:28px;height:28px}.actions{display:flex;align-items:center;gap:14px}.actions a,.actions button{font-size:14px;min-height:44px;display:inline-flex;align-items:center;justify-content:center}.print{background:var(--wash);border:0;border-radius:8px;padding:7px 16px;color:var(--accent)}.layout{max-width:1260px;margin:auto;padding:38px 28px 64px;display:grid;grid-template-columns:190px minmax(0,1fr);gap:40px}.sidebar{align-self:start;position:sticky;top:98px}.sidebar p{font-size:13px;color:var(--muted);margin:0 0 12px}.sidebar nav{display:grid;gap:5px}.sidebar nav a{padding:9px 12px;min-height:44px;color:var(--muted);text-decoration:none;border-radius:8px;border-left:3px solid transparent}.sidebar nav a:hover,.sidebar nav a[aria-current=true]{background:var(--wash);color:var(--accent);border-left-color:var(--accent)}.sidebar .scope{font-size:12px;line-height:1.7;margin-top:25px;color:var(--muted)}main{min-width:0}.masthead{padding:0 0 32px;border-bottom:2px solid var(--ink)}.source-label{display:flex;flex-wrap:wrap;align-items:center;gap:9px;color:var(--muted);font-size:13px}.chip{border:1px solid var(--line);border-radius:5px;padding:1px 8px;background:var(--paper)}h1{font-size:clamp(29px,3.6vw,48px);line-height:1.3;letter-spacing:-.035em;max-width:850px;margin:19px 0 20px;font-weight:720;overflow-wrap:anywhere}.lede{font-size:19px;line-height:1.85;max-width:820px;margin:0}.meta{display:flex;flex-wrap:wrap;gap:8px 25px;margin-top:22px;font-size:13px;color:var(--muted)}.meta strong{color:var(--ink);font-size:16px;margin-right:4px;font-variant-numeric:tabular-nums}.disclaimer{margin:18px 0 0;font-size:13px;color:var(--muted)}section{margin-top:38px;scroll-margin-top:90px}.section-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:20px}h2{font-size:24px;line-height:1.4;letter-spacing:-.025em;margin:0}h3{font-size:18px;line-height:1.6;margin:0 0 10px}p{margin:0 0 12px;overflow-wrap:anywhere}.section-head span,.subtle{font-size:13px;color:var(--muted)}.takeaways{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 26px}.takeaway{padding:16px 0 18px;border-bottom:1px solid var(--line)}.takeaway h3{color:var(--accent)}.takeaway p{font-size:15px}.refs{border-top:1px dashed var(--line);padding-top:8px;margin-top:12px;font-size:13px;color:var(--muted)}.refs summary{cursor:pointer;min-height:40px;display:list-item;padding:7px 0;color:var(--accent)}.refs blockquote{margin:8px 0;padding:8px 12px;background:var(--canvas);border-radius:6px;font-size:14px;line-height:1.75}.refs blockquote a{display:inline-block;margin-top:5px;font-size:12px}.roadmap{border:1px solid var(--line);background:var(--paper);border-radius:var(--radius);padding:20px 24px;margin-bottom:24px}.roadmap h3{font-size:15px;margin-bottom:14px}.stops{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px 18px}.stop{position:relative;border-top:2px solid var(--accent);padding:9px 0 2px;text-decoration:none;font-size:13px;line-height:1.6;color:var(--ink)}.stop:before{content:"";position:absolute;top:-5px;left:0;width:8px;height:8px;background:var(--accent);border-radius:50%}.stop time{display:block;color:var(--accent);font-weight:600;font-variant-numeric:tabular-nums;font-size:13px;margin-bottom:3px}.timeline{list-style:none;margin:0;padding:0}.timeline li{display:grid;grid-template-columns:62px 22px minmax(0,1fr);column-gap:12px}.timeline .time{padding-top:16px;font-size:13px;color:var(--accent);font-weight:600;font-variant-numeric:tabular-nums;text-align:right}.rail{position:relative;display:grid;justify-items:center}.rail:before{content:"";position:absolute;top:0;bottom:0;width:2px;background:var(--line)}.rail:after{content:"";width:10px;height:10px;background:var(--accent);border:2px solid var(--canvas);border-radius:50%;margin-top:24px;z-index:1}.timeline li:first-child .rail:before{top:26px}.timeline li:last-child .rail:before{bottom:auto;height:26px}.chapter{min-width:0;padding:13px 0 28px}.chapter h3{font-size:18px}.chapter .context{font-size:12px;color:var(--muted);margin-bottom:7px}.chapter p{font-size:15px}.chapter .refs{margin-top:10px}.proof-list{display:grid;gap:18px}.proof{padding:22px 24px;background:var(--paper);border:1px solid var(--line);border-radius:var(--radius)}.proof p{font-size:15px}.caution{background:var(--note);padding:24px;border-radius:var(--radius);color:var(--note-ink)}.caution h2{color:var(--ink);margin-bottom:16px}.caution ul{padding-left:20px;margin:0;display:grid;gap:11px;font-size:14px}.action-list{padding:0;list-style:none;display:grid;gap:18px}.action-list li{padding-bottom:20px;border-bottom:1px solid var(--line)}.action-list p{font-size:15px}.reader{background:var(--paper);border:1px solid var(--line);border-radius:var(--radius);padding:22px 24px}.reader>summary{font-weight:650;font-size:18px;cursor:pointer;min-height:44px}.reader-help{font-size:13px;color:var(--muted);margin:12px 0 18px}.tools{display:flex;align-items:center;gap:12px;margin:14px 0;flex-wrap:wrap}.tools input{width:min(100%,420px);min-height:44px;border:1px solid var(--line);border-radius:8px;padding:9px 12px;background:var(--canvas);color:var(--ink)}.tools button{padding:8px 12px;min-height:44px;border:1px solid var(--line);border-radius:8px;background:white;color:var(--ink)}.tools output{font-size:13px;color:var(--muted)}.transcript-segment{border-top:1px solid var(--line);padding:20px 0;scroll-margin-top:90px}.transcript-segment:target{background:var(--wash);outline:10px solid var(--wash)}.transcript-segment h3{font-size:13px;color:var(--muted);font-weight:500}.transcript-segment p{font-size:15px;white-space:pre-line;line-height:1.95}.transcript-segment a{display:inline-flex;min-height:35px;align-items:center;font-size:13px}.footer{border-top:1px solid var(--line);padding-top:20px;margin-top:30px;font-size:13px;color:var(--muted)}.footer p{margin:7px 0}.source-url{word-break:break-all}.hidden,[hidden]{display:none!important}.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}mark{background:var(--wash);color:var(--ink)}
@media(max-width:1050px){.layout{grid-template-columns:155px minmax(0,1fr);gap:28px}.stops{grid-template-columns:repeat(2,minmax(0,1fr))}.sidebar nav a{padding-left:7px;font-size:14px}}
@media(max-width:760px){.layout{display:block;padding:25px 20px 44px}.sidebar{position:static;margin-bottom:25px}.sidebar>p,.sidebar .scope{display:none}.sidebar nav{display:flex;flex-wrap:wrap;gap:5px 6px}.sidebar nav a{font-size:13px;padding:7px 10px;min-height:38px;border-left:0;background:white}.top-inner{padding:8px 20px}.actions{gap:10px}.top-inner .brand{font-size:14px}.actions a,.actions button{font-size:12px}.print{padding:6px 9px}.takeaways{grid-template-columns:minmax(0,1fr)}h1{font-size:32px}.lede{font-size:17px}.masthead{padding-bottom:23px}.meta{gap:6px 18px}.section-head{align-items:flex-start;flex-direction:column;gap:6px}h2{font-size:23px}.timeline li{grid-template-columns:47px 16px minmax(0,1fr);gap:8px}.timeline .time{font-size:12px}.chapter h3{font-size:17px}.chapter p{font-size:15px}.roadmap{padding:20px 18px}.proof,.caution,.reader{padding:20px 18px}.section-head span{font-size:12px}.refs summary{font-size:13px}section{margin-top:30px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
details:not([open])>:not(summary){display:none!important}.transcript-segment>a{display:flex;width:100%;min-height:44px}.refs summary{min-height:44px}.brand{min-height:44px}
@media(max-width:760px){.sidebar nav a{min-height:44px;font-size:14px}.source-label,.meta,.disclaimer,.section-head span,.subtle,.timeline .time,.chapter .context,.refs,.refs summary,.refs blockquote a,.reader-help,.tools output,.transcript-segment h3,.transcript-segment a,.footer,.stop,.stop time{font-size:14px}.actions a,.actions button{font-size:14px}.top-inner{gap:10px}.actions{gap:8px}.brand{gap:6px}}
@media print{body{background:white;font-size:11pt}.topbar,.sidebar,.tools{display:none!important}.layout{display:block;max-width:none;padding:0}section{break-inside:auto}.proof,.takeaway,.chapter{break-inside:avoid}.refs{display:block}.refs summary{display:none}.reader{border:0;padding:0}.footer{break-inside:avoid}a{color:inherit;text-decoration:none}h1{font-size:28pt}.caution{background:#f6f6f6}.roadmap{break-inside:avoid}}
"""

JS = r"""
(function(){
  'use strict';
  try {
    var root=document.getElementById('notes-app');
    if(!root)return;
    var printButton=document.getElementById('print-page');
    if(printButton){printButton.hidden=false;printButton.addEventListener('click',function(){window.print();});}
    var reader=document.getElementById('reader');
    var query=document.getElementById('transcript-search');
    var output=document.getElementById('search-result');
    var rows=Array.from(root.querySelectorAll('.transcript-segment'));
    var searchTools=document.getElementById('search-tools');
    if(searchTools)searchTools.hidden=false;
    function filter(){
      if(!query||!output)return;
      var word=query.value.trim().toLocaleLowerCase();
      var visible=0;
      rows.forEach(function(row){var keep=!word||row.textContent.toLocaleLowerCase().includes(word);row.hidden=!keep;if(keep)visible++;});
      output.textContent=word?'匹配 '+visible+' / '+rows.length+' 段':'共 '+rows.length+' 段';
    }
    if(query)query.addEventListener('input',filter);
    var clear=document.getElementById('clear-search');
    if(clear)clear.addEventListener('click',function(){if(query){query.value='';filter();query.focus();}});
    function reveal(id){
      var target=document.getElementById(id);
      if(!target||!target.classList.contains('transcript-segment'))return;
      if(reader)reader.open=true;
      if(query){query.value='';filter();}
      target.hidden=false;
      window.requestAnimationFrame(function(){target.scrollIntoView({block:'start'});target.focus({preventScroll:true});});
    }
    root.querySelectorAll('a[data-segment]').forEach(function(link){
      link.addEventListener('click',function(){reveal(link.getAttribute('data-segment'));});
    });
    window.addEventListener('hashchange',function(){reveal(window.location.hash.slice(1));});
    reveal(window.location.hash.slice(1));filter();
    var opened=[],filtered=[];
    window.addEventListener('beforeprint',function(){opened=[];filtered=[];root.querySelectorAll('details').forEach(function(d){if(!d.open){opened.push(d);d.open=true;}});rows.forEach(function(r){if(r.hidden){filtered.push(r);r.hidden=false;}});});
    window.addEventListener('afterprint',function(){opened.forEach(function(d){d.open=false;});filtered.forEach(function(r){r.hidden=true;});});
    if('IntersectionObserver' in window){
      var links=Array.from(root.querySelectorAll('.sidebar nav a'));
      var observer=new IntersectionObserver(function(entries){entries.forEach(function(e){if(e.isIntersecting){links.forEach(function(a){a.setAttribute('aria-current',a.hash==='#'+e.target.id?'true':'false');});}});},{rootMargin:'-15% 0px -65% 0px'});
      root.querySelectorAll('main>section').forEach(function(s){observer.observe(s);});
    }
  } catch(e) { var msg=document.getElementById('page-message');if(msg){msg.textContent='增强交互暂不可用，正文和原稿仍可阅读。';msg.hidden=false;} }
})();
"""


def render(data, summary, segments, raw_text):
    source = public_url(data["source_url"])
    by_id = {s["id"]: s for s in segments}
    anchors = {s["id"]: f"segment-{i:04d}" for i, s in enumerate(segments, 1)}
    titles = {"takeaways": "核心结论", "chapters": "章节时间轴", "evidence": "论据与数据", "actions": "作者建议", "caveats": "核验提醒", "transcript": "完整文字稿"}
    host = (urlsplit(source).hostname or "").lower()
    platform = "Bilibili" if host == "b23.tv" or host == "bilibili.com" or host.endswith(".bilibili.com") else host
    mode = "云端 ASR 转写" if data.get("transcript_method") == "cloud_asr" else "用户提供文字稿"
    duration = duration_from_text(raw_text, data.get("metadata", {}))

    def refs(item):
        blocks = []
        for ref in item.get("refs", []):
            segment = by_id[ref["id"]]
            anchor = anchors[ref["id"]]
            blocks.append(f'<blockquote>{esc(ref["quote"])}<br><a href="#{anchor}" data-segment="{anchor}">查看原稿 {esc(ref["id"])} · {time_label(segment["start_seconds"])}</a></blockquote>')
        return '<details class="refs"><summary>展开原文依据</summary>' + ''.join(blocks) + '</details>'

    def item_markup(item, kind):
        return f'<article class="{kind}"><h3>{esc(item.get("title", "要点"))}</h3><p>{esc(item["text"])}</p>{refs(item)}</article>'

    def chapter_time(item):
        values = [by_id[r["id"]]["start_seconds"] for r in item["refs"] if by_id[r["id"]]["start_seconds"] is not None]
        return min(values) if values else None

    # Heading text is displayed intact below. Remove redundant timestamp only on
    # the compact navigation, never interpret an unverified title as a timestamp.
    def short_title(item):
        return item.get("title", "章节").split("｜", 1)[-1]

    takeaways = ''.join(item_markup(item, 'takeaway') for item in summary["takeaways"])
    stop_markup, chapter_markup = [], []
    for i, item in enumerate(summary["chapters"], 1):
        when = time_label(chapter_time(item))
        stop_markup.append(f'<a class="stop" href="#chapter-{i}"><time>{when}</time>{esc(short_title(item))}</a>')
        chapter_markup.append(f'<li id="chapter-{i}"><div class="time">{when}</div><div class="rail" aria-hidden="true"></div><article class="chapter"><div class="context">第 {i} 节 · 时间为引用段落起点</div><h3>{esc(item.get("title", "章节"))}</h3><p>{esc(item["text"])}</p>{refs(item)}</article></li>')
    evidence = ''.join(item_markup(item, 'proof') for item in summary["evidence"])
    actions = ''.join(f'<li>{item_markup(item, "advice")}</li>' for item in summary.get("actions", []))
    if not actions:
        actions = '<li><p>视频没有明确提出可执行建议；不额外补造作者观点。</p></li>'
    caveats = ''.join(f'<li>{esc(value)}</li>' for value in summary["caveats"])
    transcript = []
    for s in segments:
        anchor = anchors[s["id"]]
        time = time_label(s["start_seconds"])
        speaker = s.get("speaker") or "未标注说话人"
        link = '' if s["start_seconds"] is None else f'<a href="{esc(video_link(source, s["start_seconds"]))}" target="_blank" rel="noopener noreferrer">在来源视频中查看这一段</a>'
        transcript.append(f'<article class="transcript-segment" id="{anchor}" tabindex="-1"><h3>{esc(s["id"])} / {time} / {esc(speaker)}</h3><p>{esc(s["text"])}</p>{link}</article>')
    nav = ''.join(f'<a href="#{key}">{value}</a>' for key, value in titles.items())
    duration_meta = f'<span><strong>{duration}</strong>原稿标记时长</span>' if duration else ''
    title = esc(data["title"])
    favicon = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23007c78'/%3E%3Cpath d='M18 18h28v5H18zm0 12h20v5H18zm0 12h28v5H18z' fill='white'/%3E%3C/svg%3E"
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="generator" content="video-transcript-summary HTML {VERSION}">
<title>{title}｜视频笔记</title><link rel="icon" href="{favicon}">
<style>{CSS}</style></head>
<body><div id="notes-app">
<header class="topbar"><div class="top-inner"><a class="brand" href="#overview"><svg viewBox="0 0 28 28" fill="none" aria-hidden="true"><rect x="2" y="2" width="24" height="24" rx="6" stroke="currentColor" stroke-width="1.5"/><path d="M8 9h12M8 14h8M8 19h12" stroke="currentColor" stroke-width="1.5"/></svg>视频笔记</a><div class="actions"><a href="{esc(source)}" target="_blank" rel="noopener noreferrer">打开原视频</a><button id="print-page" class="print" type="button" hidden>打印 / 存 PDF</button></div></div></header>
<div class="layout"><aside class="sidebar"><p>阅读导航</p><nav aria-label="笔记目录">{nav}</nav><div class="scope">先看结论，再沿章节阅读。<br>每条观点都保留原文依据。<br>展开引用，可定位完整文字稿。</div></aside>
<main>
<header id="overview" class="masthead"><div class="source-label"><span class="chip">{esc(platform)}</span><span>{mode}</span><span class="chip">离线阅读版</span></div><h1>{title}</h1><p class="lede">{esc(summary["overview"])}</p><div class="meta">{duration_meta}<span><strong>{len(summary["chapters"])}</strong>主题章节</span><span><strong>{len(summary["takeaways"])}</strong>核心结论</span><span><strong>{len(segments)}</strong>原稿段落</span></div><p class="disclaimer">内容整理自视频，未作外部事实核验。自动转写中的型号、数字和术语请结合原视频复核。</p></header>
<p id="page-message" class="subtle" hidden></p>
<section id="takeaways"><div class="section-head"><h2>核心结论</h2><span>先理解主张，再查看原文</span></div><div class="takeaways">{takeaways}</div></section>
<section id="chapters"><div class="section-head"><h2>沿着视频读下去</h2><span>时间标记来自原稿，不推算章节时长</span></div><div class="roadmap"><h3>章节路线 · 按视频顺序</h3><div class="stops">{''.join(stop_markup)}</div></div><ol class="timeline">{''.join(chapter_markup)}</ol></section>
<section id="evidence"><div class="section-head"><h2>论据与数据</h2><span>口述数据 ≠ 已核实事实</span></div><div class="proof-list">{evidence}</div></section>
<section id="actions"><div class="section-head"><h2>作者明确提出的建议</h2><span>仅复述视频，不追加个性化建议</span></div><ul class="action-list">{actions}</ul></section>
<section id="caveats" class="caution"><h2>这些地方，需要多核对一步</h2><ul>{caveats}</ul></section>
<section id="transcript"><details id="reader" class="reader"><summary>完整文字稿与原文回查</summary><p class="reader-help">原稿按原顺序保留，包括无时间戳的附带信息。搜索在本机完成，不会发送到服务器。</p><div id="search-tools" class="tools" hidden><label class="visually-hidden" for="transcript-search">搜索文字稿</label><input id="transcript-search" type="search" placeholder="搜索型号、概念或一句话" autocomplete="off"><button id="clear-search" type="button">清空</button><output id="search-result" aria-live="polite"></output></div><noscript><p class="reader-help">JavaScript 未启用，可展开阅读原稿并使用浏览器查找。</p></noscript>{''.join(transcript)}</details></section>
<footer class="footer"><p><strong>来源与隐私</strong></p><p class="source-url"><a href="{esc(source)}" target="_blank" rel="noopener noreferrer">{esc(source)}</a></p><p>这是本次总结的静态阅读快照，已内嵌全部正文，不依赖旁边的文件。页面不上传、追踪或自动加载音视频。</p><p>转换流程仅在文稿与网页保存校验后清理本任务本地临时媒体；云端转写服务可能保留音频及妙记，本地清理不等于云端删除。</p></footer>
</main></div></div><script>{JS}</script></body></html>'''

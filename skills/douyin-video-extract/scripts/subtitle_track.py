#!/usr/bin/env python3
"""
文案提取 · 第 1 层：官方字幕轨（subtitle_infos）

抖音作品详情里，创作者上了字幕的视频会带 subtitle_infos，
里面是 VTT/SRT 文件地址。这一层最准、最快，优先用。

用法:
  # 从详情 JSON 自动找字幕轨（推荐，先把 dy_fetch.js 的输出存下来）
  python subtitle_track.py --from-detail detail.json [-o out.txt] [--timestamps]

  # 直接给字幕地址
  python subtitle_track.py --url "https://..." [--format vtt] [-o out.txt]

注意:
  - is_subtitled=0 或没有 subtitle_infos，说明创作者没上字幕轨 —— 这不是失败，
    转第 2 层 ASR 或第 3 层画面 OCR。
  - 本脚本**不做长度截断**。字幕轨有多长就输出多长。
"""

import argparse
import json
import re
import sys
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def pick_subtitle_infos(detail: dict) -> list:
    """从详情 JSON 里取字幕轨，两个可能的位置都查"""
    infos = detail.get("subtitle_infos") or []
    if not infos:
        infos = ((detail.get("video") or {}).get("subtitle") or {}).get("subtitleInfos") or []
    out = []
    for s in infos:
        url = s.get("Url") or s.get("url") or ""
        if not url:
            continue
        out.append(
            {
                "url": url,
                "lang": s.get("LanguageCodeName") or s.get("languageCodeName") or "",
                "format": (s.get("Format") or s.get("format") or "vtt").lower(),
            }
        )
    return out


def pick_best(infos: list) -> dict:
    """优先中文字幕，其次第一个"""
    for s in infos:
        lang = s["lang"].lower()
        if "zh" in lang or "cn" in lang or "chinese" in lang:
            return s
    return infos[0]


TS_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{3})"
)


def _sec(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_subtitle(content: str) -> list:
    """解析 VTT/SRT → [(start_sec, end_sec, text)]，按时间顺序"""
    cues = []
    cur_ts = None
    buf = []

    def flush():
        nonlocal cur_ts, buf
        text = " ".join(x for x in buf if x).strip()
        if text and cur_ts:
            cues.append((cur_ts[0], cur_ts[1], text))
        cur_ts, buf = None, []

    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        m = TS_RE.search(line)
        if m:
            flush()
            cur_ts = (_sec(*m.groups()[:4]), _sec(*m.groups()[4:]))
            continue
        if re.fullmatch(r"\d+", line):  # SRT 序号
            continue
        # 去掉 <c>/<v> 之类的样式标签
        clean = re.sub(r"<[^>]+>", "", line).strip()
        # 纯样式残留行（无中文无字母数字）丢掉
        if clean and not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", clean):
            continue
        if clean:
            buf.append(clean)

    flush()
    return cues


def dedupe(cues: list) -> list:
    """抖音字幕轨常有滚动重复（一句分多行重复出现），去掉连续重复的文本"""
    out = []
    for start, end, text in cues:
        if out and out[-1][2] == text:
            out[-1] = (out[-1][0], end, text)
            continue
        out.append((start, end, text))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-detail", help="dy_fetch.js --save-json 存下来的详情 JSON")
    ap.add_argument("--url", help="直接指定字幕文件地址")
    ap.add_argument("--format", default="", help="vtt / srt")
    ap.add_argument("--timestamps", action="store_true", help="输出带时间戳（默认只输出纯文本）")
    ap.add_argument("-o", "--out", help="输出文件，缺省打到 stdout")
    args = ap.parse_args()

    if args.from_detail:
        with open(args.from_detail, encoding="utf-8") as f:
            detail = json.load(f)
        if "aweme_detail" in detail:
            detail = detail["aweme_detail"]
        infos = pick_subtitle_infos(detail)
        if not infos:
            print(
                "NO_SUBTITLE_TRACK: 这个作品没有官方字幕轨"
                "（is_subtitled=%s）。改用 ASR 或画面 OCR。"
                % detail.get("is_subtitled"),
                file=sys.stderr,
            )
            return 2
        target = pick_best(infos)
    elif args.url:
        target = {"url": args.url, "lang": "", "format": args.format or "vtt"}
    else:
        ap.error("需要 --from-detail 或 --url")

    req = urllib.request.Request(target["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read().decode("utf-8", "replace")

    cues = dedupe(parse_subtitle(content))
    if not cues:
        print("字幕文件解析后为空", file=sys.stderr)
        return 3

    if args.timestamps:
        lines = ["%.2f-%.2fs  %s" % (s, e, t) for s, e, t in cues]
    else:
        lines = [t for _, _, t in cues]

    text = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("已写入 %s（%d 段 / %d 字）" % (args.out, len(cues), len(text.replace("\n", ""))), file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

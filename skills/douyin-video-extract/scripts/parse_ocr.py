#!/usr/bin/env python3
"""
OCR 结果解析 —— 把 subtitle_ocr 的 ocr.json 变成可直接用的时间轴

用法:
  # ① 先看 y 分布，确认字幕带 / 标题带在哪（每次新视频都建议先跑一次）
  python parse_ocr.py ocr.json --bands

  # ② 底部字幕时间轴
  python parse_ocr.py ocr.json --subtitles

  # ③ 中部「强调卡 / 金句卡」区间（常是全片记忆锚点，只看字幕带会漏掉）
  python parse_ocr.py ocr.json --cards

  # ④ 都要（默认）
  python parse_ocr.py ocr.json -o timeline.txt

坐标约定: Vision 原点在【左下】，y 越大越靠上。
默认分带: 字幕带 y < 0.45 ｜ 强调卡带 0.38 <= y <= 0.72
可用 --sub-band / --card-band 覆盖。

为什么要分带: 强调卡出现时底部字幕是【空的】，只抓 y<0.45 会完全漏掉它。
"""

import argparse
import difflib
import json
import re
import sys
from collections import Counter

# 只保留中英文数字与常用标点，去掉 OCR 常带出来的噪点字符
KEEP = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9%＋+./、，：:!？?！]")
DIGITS = re.compile(r"\d+")


def clean(s: str) -> str:
    return KEEP.sub("", s.strip()).strip()


# 数字串超过这个长度就不当"换了一条字幕"的依据 —— 日期 / ID / 手机号这类
# 长串数字，OCR 本身就会一帧一个读法（实测 2026030920260315 有 9 种读法），
# 拿它分句只会把同一条字幕撕成好几条。
LONG_NUM = 6


def digit_conflict(a: str, b: str) -> bool:
    """两条文本能否判定为【不同的字幕】（而不是同一句的两个 OCR 版本）。

    只在一种形态上判定：**句式完全一样、只有数字不同**。
    例：`播放量低于500` → `播放量低于3000`

    这两条字符相似度高达 0.82，超过合并阈值 0.6，会被当成"同一句话的两个 OCR
    版本"合并掉 —— 但它们其实是两条不同字幕，而 500 / 3000 正是唯一的区别。
    （实测：2fps 抽帧时整段开头被并成了一条，把 500 / 3000 的对比讲丢了。）

    不判定的情况，交回普通相似度：
      · 有一方没数字
      · 数字一样（千分位 `3,000` / `3000` 已被 clean 归一）
      · 句式本身不同 —— 那是 OCR 把汉字读成了近形字（正/罡、赞/潜），
        这种情况【应该】合并，再靠 better() 挑更完整的版本
      · 长数字串 —— 日期 / ID 的 OCR 读法本就不稳定，拿它分句会把
        同一条字幕撕成 7～9 条（实测过，可读性反而变差）
    """
    da, db = DIGITS.findall(a), DIGITS.findall(b)
    if not da or not db:
        return False
    if da == db:
        return False
    if DIGITS.sub("#", a) != DIGITS.sub("#", b):
        return False  # 句式不同 → 属于 OCR 残读，不拆
    if any(len(d) > LONG_NUM for d in set(da) | set(db)):
        return False  # 长数字串（日期/ID）读法不稳定，不拆
    return True


def similar(a: str, b: str) -> float:
    """两条同位置文本的相似度。OCR 对同一句常给出长短不一的多个版本，
    需要靠相似度而不是全等来判断'还是同一句'。"""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if digit_conflict(a, b):
        return 0.0  # 数字对不上 → 是两条不同字幕，绝不能合并
    return difflib.SequenceMatcher(None, a, b).ratio()


def better(a: str, b: str) -> str:
    """同一句的两个 OCR 版本里挑更可信的：字更全的那个（残读总是更短）。
    实测 '当你主动告诉A' / '当你主动告诉AI' → 后者对；
        '已经常非常值钱了' / '已经非常非常值钱了' → 后者对。"""
    return a if len(a) >= len(b) else b


def load(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    frames = []
    for item in data:
        if item.get("error"):
            continue
        m = re.search(r"(\d+)", item.get("file", ""))
        if not m:
            continue
        frames.append((int(m.group(1)), item.get("lines", [])))
    frames.sort(key=lambda x: x[0])
    return frames


def frame_time(idx: int, fps: float) -> float:
    """f_001.jpg 是第 1 帧 → t=0"""
    return (idx - 1) / fps


def show_bands(frames):
    print("=== y 分布（每 0.05 一档，n 越大说明该带是稳定元素）===", file=sys.stderr)
    hist = Counter()
    for _, lines in frames:
        for ln in lines:
            hist[round(ln["y"] / 0.05) * 0.05] += 1
    total = len(frames) or 1
    for y in sorted(hist, reverse=True):
        bar = "#" * max(1, int(hist[y] / total * 40))
        print(f"  y={y:.2f}  n={hist[y]:5d}  {bar}", file=sys.stderr)
    print(
        "\n提示：n 接近总帧数的档位 = 常年不动的固定元素（顶部标题/台标）；"
        "\nn 中等且成片的 = 滚动字幕带。",
        file=sys.stderr,
    )


def group_lines(band):
    """把同一横排上的多个文本框合成一行。

    不同 OCR 引擎切框粒度不同：RapidOCR 常把一句话切成几段
    （'已经非常' + '非常值钱了'、'我要' + '住酒店'），
    直接拼会变成 '已经非常/非常值钱了'。这里按垂直重叠把它们并回一行，
    同一行内【直接连接不加分隔符】，不同行之间才用 ' / '。
    """
    band = sorted(band, key=lambda l: -(l["y"] + l.get("h", 0)))
    lines = []
    for ln in band:
        top = ln["y"] + ln.get("h", 0)
        bot = ln["y"]
        placed = False
        for L in lines:
            ov = min(top, L["top"]) - max(bot, L["bot"])
            if ov > 0.5 * min(ln.get("h", 0) or 1e-6, (L["top"] - L["bot"]) or 1e-6):
                L["items"].append(ln)
                L["top"] = max(L["top"], top)
                L["bot"] = min(L["bot"], bot)
                placed = True
                break
        if not placed:
            lines.append({"top": top, "bot": bot, "items": [ln]})
    out = []
    for L in lines:
        items = sorted(L["items"], key=lambda l: l["x"])
        out.append("".join(clean(l["text"]) for l in items))
    return [t for t in out if t]


def extract(frames, fps, lo, hi, min_len=2, sim=0.6, max_gap=1.2):
    """抽某一 y 带内的文本，收成 [(start, end, text)]。

    两条规则：
      1. 相邻两次出现只要【时间间隔 <= max_gap】且【文本相似度 >= sim】，就认为是同一条，
         合并并把文本换成更完整的那个版本（OCR 对同一句会给出长短不一的多个残读）。
      2. end 取【最后一次真正读到该文本的时间】，不用空帧去无限延长 ——
         否则强调卡结束后会被一路拉到片尾（实测踩过这个坑）。

    ⚠️ 数字比对要用 run 的【锚点文本】（本段第一条），不能用演化后的当前文本：
       `播放量低于500` → `播放量低于500 / 正常吗` → `播放量低于3,000`
       当前文本已经长成带"正常吗"的句式，再跟 `播放量低于3,000` 比句式就对不上了，
       于是 500 和 3000 会被并成一条（实测 2fps 时就是这个现象）。
       锚点始终保持 `播放量低于#` 的句式，才能真正拦住这次误合并。
    """
    runs = []
    for idx, lines in frames:
        t = frame_time(idx, fps)
        band = [ln for ln in lines if lo <= ln["y"] <= hi]
        txt = " / ".join(group_lines(band)).strip()
        if len(txt) < min_len:
            continue  # 空帧：不延长，只跳过

        if runs:
            r = runs[-1]
            same_sentence = similar(r["text"], txt) >= sim
            # 换了数字 → 是另一条字幕，不许并（锚点比，见上面注释）
            numeric_break = digit_conflict(r["anchor"], txt)
            if (t - r["last"]) <= max_gap and same_sentence and not numeric_break:
                r["last"] = t
                r["text"] = better(r["text"], txt)
                continue

        runs.append({"start": t, "last": t, "text": txt, "anchor": txt})

    return [(r["start"], r["last"], r["text"]) for r in runs]


def cluster_cards(cards, gap=2.5):
    """强调卡是静态的，会被 OCR 读成几十个相似变体 —— 按时间聚类成区间，
    区间内取【出现次数最多】的读法作为该条的代表。

    gap 默认 2.5s：一张卡从第一行到最后一行逐步显现，中间可能有 1~2 秒的
    "只有半行" 状态，gap 太小会把同一张卡切成好几段（实测 1.2s 就会切碎）。"""
    groups = []
    for s, e, txt in cards:
        if groups and s - groups[-1]["end"] <= gap:
            groups[-1]["end"] = max(groups[-1]["end"], e)
            groups[-1]["votes"][txt] += 1
        else:
            groups.append({"start": s, "end": e, "votes": Counter({txt: 1})})
    for g in groups:
        # 取票数最高的；票数相同时取更完整的
        g["text"] = max(g["votes"].items(), key=lambda kv: (kv[1], len(kv[0])))[0]
        g["variants"] = len(g["votes"])
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ocr_json")
    ap.add_argument("--fps", type=float, default=4.0, help="抽帧帧率（默认 4）")
    ap.add_argument("--bands", action="store_true", help="只打印 y 分布，帮助确认分带")
    ap.add_argument("--subtitles", action="store_true", help="只出底部字幕时间轴")
    ap.add_argument("--cards", action="store_true", help="只出中部强调卡区间")
    ap.add_argument("--sub-band", default="0,0.45", help="字幕带 y 区间，如 0,0.45")
    ap.add_argument("--card-band", default="0.38,0.72", help="强调卡带 y 区间")
    ap.add_argument("--timestamps", action="store_true", help="字幕带时间戳输出")
    ap.add_argument("--plain", action="store_true", help="字幕只输出纯文本（无时间戳，便于直接读）")
    ap.add_argument("-o", "--out", help="输出文件，缺省打到 stdout")
    args = ap.parse_args()

    frames = load(args.ocr_json)
    if not frames:
        print("没解析出任何帧，检查 ocr.json 格式", file=sys.stderr)
        return 1

    if args.bands:
        show_bands(frames)
        return 0

    lo, hi = (float(x) for x in args.sub_band.split(","))
    clo, chi = (float(x) for x in args.card_band.split(","))

    want_sub = args.subtitles or not args.cards
    want_card = args.cards or not args.subtitles

    lines_out = []

    if want_sub:
        subs = extract(frames, args.fps, lo, hi)
        lines_out.append("=== 底部字幕时间轴（y %.2f–%.2f，共 %d 条）===" % (lo, hi, len(subs)))
        for s, e, txt in subs:
            if args.plain:
                lines_out.append(txt)
            else:
                lines_out.append(f"{s:7.2f}-{e:7.2f}s  {txt}")
        lines_out.append("")

    if want_card:
        cards = extract(frames, args.fps, clo, chi, min_len=3, sim=0.5)
        groups = cluster_cards(cards)
        lines_out.append("=== 中部强调卡 / 金句卡（y %.2f–%.2f，共 %d 处）===" % (clo, chi, len(groups)))
        if not groups:
            lines_out.append("（无：这条视频没有大字强调卡，纯字幕带）")
        for g in groups:
            lines_out.append(
                f"{g['start']:7.2f}-{g['end']:7.2f}s  {g['text']}"
                f"   [OCR 有 {g['variants']} 种变体，务必 Read 关键帧确认]"
            )

    text = "\n".join(lines_out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"已写入 {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

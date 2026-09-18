#!/usr/bin/env python3
"""
视频抽帧 / 场景检测 —— 跨平台版本（替代散落在文档里的 ffmpeg shell 命令）

用法:
  python extract_frames.py video.mp4 --info                     # 看时长 / 分辨率 / 有无音轨
  python extract_frames.py video.mp4 --fps 4 -o frames/          # 按 4fps 抽帧
  python extract_frames.py video.mp4 --fps auto -o frames/       # 按「总帧数 <= 800」自动定帧率
  python extract_frames.py video.mp4 --scenes                    # 剪辑点检测（画面突变时间点）

为什么要有这个脚本:
  文档里原来直接写 `$FF ... | grep -o 'pts_time:...' | sed ...` —— 那是 bash 语法，
  Windows 的 cmd / PowerShell 跑不了。统一收进 Python，两端同一条命令。

抽帧率怎么定（--fps auto）:
  实测 OCR 约 0.18s/帧（Vision）/ 0.30s/帧（RapidOCR），
  以「总帧数 <= 800」为预算（约 2.5~4 分钟），即 fps = 800 / 时长，
  再夹到 [2, 6] 之间：短于 2 分钟取 6，长于 6 分钟取 2，中间线性。
"""

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import env  # noqa: E402

MAX_FRAMES = 800


# ───────────────────────── 基础 ─────────────────────────

def probe(ffmpeg: str, video: str) -> dict:
    """ffmpeg -i 的流信息写在 stderr 里"""
    p = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", video],
        capture_output=True, text=True, errors="replace", timeout=120,
    )
    info = p.stderr or ""
    out = {"raw": info, "has_video": False, "has_audio": False, "duration": None,
           "width": None, "height": None}
    out["has_video"] = bool(re.search(r"Stream #\d+:\d+.*?: Video:", info))
    out["has_audio"] = bool(re.search(r"Stream #\d+:\d+.*?: Audio:", info))
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", info)
    if m:
        out["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", info)
    if m:
        out["width"], out["height"] = int(m.group(1)), int(m.group(2))
    return out


def auto_fps(duration: float) -> float:
    """按「总帧数 <= MAX_FRAMES」定帧率，并对齐到 0.5 的整数倍。
    对齐是为了时间轴好算 —— 5.00407 这种数字换算出来没法看。"""
    if not duration or duration <= 0:
        return 4.0
    v = max(2.0, min(6.0, MAX_FRAMES / duration))
    return round(v * 2) / 2


# ───────────────────────── 抽帧 ─────────────────────────

def extract(ffmpeg: str, video: str, outdir: str, fps: float, quality: int = 2) -> int:
    os.makedirs(outdir, exist_ok=True)
    pattern = os.path.join(outdir, "f_%03d.jpg")
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", video,
        # 原分辨率抽帧：花字缩小后 OCR 错字率明显上升，不要加 scale
        "-vf", f"fps={fps}", "-q:v", str(quality), "-y", pattern,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=3600)
    if p.returncode != 0:
        env.die("抽帧失败", [(p.stderr or "")[:500]])
    return len([f for f in os.listdir(outdir) if f.startswith("f_") and f.endswith(".jpg")])


# ───────────────────────── 场景检测 ─────────────────────────

def scenes(ffmpeg: str, video: str, threshold: float = 0.3) -> list:
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", video,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=3600)
    # showinfo 把 pts_time 打在 stderr
    stamps = re.findall(r"pts_time:([0-9.]+)", (p.stderr or "") + (p.stdout or ""))
    return [float(s) for s in stamps]


# ───────────────────────── main ─────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--fps", default=None,
                    help="抽帧率，或 'auto'（按总帧数 <= 800 自动定）")
    ap.add_argument("-o", "--outdir", default="frames", help="抽帧输出目录")
    ap.add_argument("--quality", type=int, default=2, help="JPEG 质量 2~31，越小越好")
    ap.add_argument("--scenes", action="store_true", help="只做剪辑点检测")
    ap.add_argument("--threshold", type=float, default=0.3, help="场景突变阈值，默认 0.3")
    ap.add_argument("--info", action="store_true", help="只打印视频信息")
    ap.add_argument("--json", action="store_true", help="信息以 JSON 输出（便于脚本消费）")
    args = ap.parse_args()

    if not os.path.isfile(args.video):
        env.die(f"找不到视频文件: {args.video}")

    ffmpeg = env.find_ffmpeg()
    meta = probe(ffmpeg, args.video)

    if args.info or args.json:
        if args.json:
            print(json.dumps({k: v for k, v in meta.items() if k != "raw"},
                             ensure_ascii=False, indent=2))
        else:
            dur = meta["duration"]
            print(f"  文件      : {os.path.basename(args.video)}")
            print(f"  大小      : {os.path.getsize(args.video)/1024/1024:.1f} MB")
            print(f"  时长      : {dur:.2f} s" if dur else "  时长      : 未知")
            print(f"  分辨率    : {meta['width']}x{meta['height']}")
            print(f"  视频轨    : {'有' if meta['has_video'] else '无'}")
            print(f"  音频轨    : {'有' if meta['has_audio'] else '无'}"
                  + ("" if meta["has_audio"] else "   ← 缺音轨，ASR 跑不了，需换档重下"))
            if dur:
                f = auto_fps(dur)
                print(f"  建议抽帧率: {f:g} fps（总帧数约 {int(dur*f)}）")
        if not args.fps and not args.scenes:
            return 0

    if args.scenes:
        pts = scenes(ffmpeg, args.video, args.threshold)
        if not pts:
            print("（无剪辑点 —— 这条视频是【一镜到底】）")
        else:
            print(f"检测到 {len(pts)} 个剪辑点（阈值 {args.threshold}）：")
            for t in pts:
                print(f"  {t:7.2f}s")
            gaps = [round(pts[i+1]-pts[i], 2) for i in range(len(pts)-1)]
            if gaps:
                print(f"\n镜头间隔: 最短 {min(gaps)}s / 最长 {max(gaps)}s / "
                      f"平均 {sum(gaps)/len(gaps):.2f}s")
        return 0

    # 抽帧
    if args.fps == "auto":
        fps = auto_fps(meta["duration"] or 0)
    else:
        try:
            fps = float(args.fps)
        except (TypeError, ValueError):
            env.die(f"--fps 只能是数字或 'auto'，收到: {args.fps}")
            return 1

    n = extract(ffmpeg, args.video, args.outdir, fps, args.quality)
    print(f"已抽 {n} 帧 → {args.outdir}/  （{fps:g} fps）")
    print(f"时间轴换算: t = (序号 - 1) / {fps:g}")
    if n > MAX_FRAMES * 1.3:
        print(f"⚠️ 帧数偏多（{n}），OCR 会慢。下次可降 --fps。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

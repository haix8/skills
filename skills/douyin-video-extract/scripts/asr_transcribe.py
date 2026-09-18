#!/usr/bin/env python3
"""
文案提取 · 第 2 层：口播 ASR（faster-whisper）

适用：视频只有配音、既没有官方字幕轨、画面也没有花字的场景。
比第 3 层（画面 OCR）慢，但能拿到 OCR 拿不到的口播内容。

用法:
  python asr_transcribe.py video.mp4 [-o out.txt] [--model base] [--timestamps]

依赖:
  pip install faster-whisper          # 装在隔离 venv 里
  一个带完整解码器的 ffmpeg            # Playwright 自带那份不行（没有 h264/aac）

首次运行会下载模型（tiny≈75MB / base≈145MB）。国内网络慢的话设：
  export HF_ENDPOINT=https://hf-mirror.com
"""

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import env  # noqa: E402 — 跨平台解析 ffmpeg，不硬编码本机路径


def find_ffmpeg(explicit: str = "") -> str:
    """显式指定 > 环境变量 FFMPEG > imageio-ffmpeg 自带 > PATH"""
    if explicit and os.path.isfile(explicit):
        return explicit
    prev = os.environ.get("FFMPEG")
    if explicit:
        os.environ["FFMPEG"] = explicit
    try:
        return env.find_ffmpeg()
    finally:
        if explicit:
            if prev is None:
                os.environ.pop("FFMPEG", None)
            else:
                os.environ["FFMPEG"] = prev


def probe_audio(ffmpeg: str, video: str):
    """返回 (has_audio, has_video)。ffmpeg -i 的流信息在 stderr 里。"""
    p = subprocess.run([ffmpeg, "-hide_banner", "-i", video], capture_output=True, text=True, timeout=60)
    info = p.stderr or ""
    has_audio = bool([l for l in info.splitlines() if "Stream #" in l and "Audio:" in l])
    has_video = bool([l for l in info.splitlines() if "Stream #" in l and "Video:" in l])
    return has_audio, has_video, info


def extract_audio(ffmpeg: str, video: str, out_wav: str) -> bool:
    """抽成 16k 单声道 wav —— whisper 的输入规格"""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", video,
           "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-y", out_wav]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        print("ffmpeg 抽音频失败: " + (p.stderr or "")[:300], file=sys.stderr)
        return False
    return os.path.exists(out_wav) and os.path.getsize(out_wav) > 2000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-o", "--out")
    ap.add_argument("--model", default="base", help="tiny / base / small / medium")
    ap.add_argument("--timestamps", action="store_true")
    ap.add_argument("--ffmpeg", default="")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        print("找不到文件: " + args.video, file=sys.stderr)
        return 1

    ffmpeg = find_ffmpeg(args.ffmpeg)
    has_audio, has_video, _ = probe_audio(ffmpeg, args.video)
    if not has_audio:
        print(
            "NO_AUDIO_TRACK: 这个文件没有音频轨。\n"
            "抖音常见的音视频分轨问题 —— 用 dy_fetch.js 换个 --gear 档位重新下载。",
            file=sys.stderr,
        )
        return 2
    if not has_video:
        print("注意：这个文件没有视频轨，只有音频。", file=sys.stderr)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper 未安装，请运行:\n  pip install faster-whisper", file=sys.stderr)
        return 3

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "audio.wav")
        print("抽取音频 ...", file=sys.stderr)
        if not extract_audio(ffmpeg, args.video, wav):
            return 4

        print("加载模型 %s（首次会下载）..." % args.model, file=sys.stderr)
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        segments, info = model.transcribe(wav, language="zh", beam_size=5, vad_filter=True)
        print("识别中 ... 检测语言=%s(%.2f)" % (info.language, info.language_probability), file=sys.stderr)

        lines = []
        plain = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            plain.append(text)
            lines.append("%.2f-%.2fs  %s" % (seg.start, seg.end, text))

    text = "\n".join(lines if args.timestamps else plain)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("已写入 %s（%d 段 / %d 字）" % (args.out, len(plain), len("".join(plain))), file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

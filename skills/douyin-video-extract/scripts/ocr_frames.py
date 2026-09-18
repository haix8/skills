#!/usr/bin/env python3
"""
抽帧 OCR —— 跨平台版本（替代只支持 macOS 的 subtitle_ocr.swift）

用法:
  python ocr_frames.py frames/*.jpg -o ocr.json
  python ocr_frames.py frames/*.jpg --engine rapidocr -o ocr.json
  python ocr_frames.py frames/*.jpg --engine vision               # 仅 macOS
  python ocr_frames.py frames/*.jpg --min-conf 0.5 -o ocr.json

引擎选择（--engine auto，默认）:
  macOS 且 swiftc 可用  →  Vision（编译好的一次即可）
  其他情况              →  RapidOCR（pip 装，Windows / Linux / macOS 都能跑）

  ⚠️ 实测对比：RapidOCR 在这类「描边花字 + 竖排大字」上【比 macOS Vision 更准】，
     会把 Vision 读错/读串行的内容读对（如 '原包开始收费以后' → '豆包开始收费以后'）。
     所以非 macOS 用户不是"降级"，反而是拿到更好的结果。

输出格式（与旧版 subtitle_ocr.swift 完全一致，parse_ocr.py 无需改动）：
  [{ "file": "f_001.jpg",
     "lines": [ {"text": "...", "conf": 0.9, "x": .., "y": .., "h": ..} ] }]
  x / y / h 均为【归一化】坐标，原点在【左下】—— y 越大越靠上。
  （RapidOCR 原生是左上原点的像素坐标，本脚本统一换算成上面的约定。）

依赖:
  pip install rapidocr-onnxruntime      # 跨平台，自带中文模型
  pip install pillow                    # 读图像尺寸
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import env  # noqa: E402


# ─────────────────────── 引擎：macOS Vision ───────────────────────

VISION_BIN_NAME = "subtitle_ocr"


def vision_available() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, env.exe(VISION_BIN_NAME))


def ensure_vision_built() -> str:
    """确保 Vision 产物存在；没有就【自动编译一次】。
    编译产物是平台专属二进制，不会随技能分发，所以换机器后第一次会现编。"""
    if not env.IS_MACOS:
        env.die(
            f"Vision 引擎只有 macOS 有，当前是 {env.os_name()}。",
            [
                "用跨平台引擎（推荐，实测对描边花字更准）：",
                f"    {sys.executable} -m pip install rapidocr-onnxruntime",
                "    python ocr_frames.py '...' --engine rapidocr",
            ],
        )

    binp = vision_available()
    if os.path.isfile(binp):
        return binp

    src = os.path.join(os.path.dirname(binp), "subtitle_ocr.swift")
    swiftc = shutil.which("swiftc")
    if not swiftc:
        env.die(
            "macOS 上没找到 swiftc（需要 Xcode Command Line Tools）。",
            [
                "装它：  xcode-select --install",
                "或者改用跨平台引擎（推荐，实测更准）：",
                f"    {sys.executable} -m pip install rapidocr-onnxruntime",
                "    python ocr_frames.py '...' --engine rapidocr",
            ],
        )
    print("# 首次使用 Vision，正在编译（只需一次）...", file=sys.stderr)
    p = subprocess.run(
        [swiftc, "-O", "-framework", "Vision", "-framework", "AppKit", src, "-o", binp],
        capture_output=True, text=True, errors="replace", timeout=600,
    )
    if p.returncode != 0 or not os.path.isfile(binp):
        env.die("Vision 编译失败", [(p.stderr or "")[:400],
                                    "也可以改用：--engine rapidocr"])
    return binp


def run_vision(files):
    """调用 swift 产物，它的输出格式就是目标格式"""
    binp = ensure_vision_built()
    out = subprocess.run([binp, *files], capture_output=True)
    if out.returncode != 0:
        env.die("Vision OCR 执行失败: " + (out.stderr or b"").decode("utf-8", "replace")[:300])
    return json.loads(out.stdout.decode("utf-8", "replace"))


# ─────────────────────── 引擎：RapidOCR ───────────────────────

def run_rapidocr(files, min_conf=0.0, quiet=True):
    if quiet:
        os.environ.setdefault("OMP_NUM_THREADS", "4")
        import logging
        logging.getLogger().setLevel(logging.ERROR)

    env.require(
        "rapidocr_onnxruntime",
        "rapidocr-onnxruntime",
        "跨平台画面花字 OCR（Windows / Linux / macOS 通吃）",
    )
    from rapidocr_onnxruntime import RapidOCR  # type: ignore

    try:
        from PIL import Image  # type: ignore
    except ImportError:
        env.die("缺少 pillow", [f"装它：{sys.executable} -m pip install pillow"])

    engine = RapidOCR()
    results = []
    t0 = time.time()

    for i, path in enumerate(files, 1):
        try:
            with Image.open(path) as im:
                W, H = im.size
        except Exception as e:
            results.append({"file": os.path.basename(path), "error": f"load_failed: {e}"})
            continue

        try:
            res, _elapse = engine(path)
        except Exception as e:
            results.append({"file": os.path.basename(path), "error": f"ocr_failed: {e}"})
            continue

        lines = []
        for item in res or []:
            box, text, conf = item[0], item[1], item[2]
            try:
                c = float(conf)
            except (TypeError, ValueError):
                c = 0.0
            if c < min_conf:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            # 关键：用【真实图像尺寸】换算，绝不硬编码 1080/1920
            # RapidOCR 是左上原点像素坐标 → 转成左下原点归一化
            lines.append({
                "text": text,
                "conf": round(c, 2),
                "x": round(min(xs) / W, 3),
                "y": round(1 - max(ys) / H, 3),     # 取框的下边缘，对应 Vision 的 origin.y
                "h": round((max(ys) - min(ys)) / H, 3),
            })

        if not quiet and i % 25 == 0:
            print(f"  ... {i}/{len(files)} 帧  ({time.time()-t0:.0f}s)", file=sys.stderr)

        results.append({"file": os.path.basename(path), "lines": lines})

    return results


# ─────────────────────── main ───────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="图片路径（支持 glob）")
    ap.add_argument("--engine", default="auto", choices=["auto", "vision", "rapidocr"])
    ap.add_argument("--min-conf", type=float, default=0.0, help="丢弃置信度低于该值的结果")
    ap.add_argument("--quiet", action="store_true", default=True)
    ap.add_argument("-o", "--out", help="输出 JSON 文件，缺省打到 stdout")
    args = ap.parse_args()

    # 展开 glob（Windows 的 cmd 不做 glob 展开，必须自己在脚本里做）
    files = []
    for p in args.images:
        hit = glob.glob(p)
        files.extend(hit if hit else [p])
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        env.die("没有找到任何图片文件", ["检查路径，或确认抽帧那一步是否成功"])

    engine = args.engine
    if engine == "auto":
        engine, _ = env.pick_ocr_engine()
        if engine is None:
            env.die(
                "没有可用的 OCR 引擎。",
                [
                    "装跨平台的那个（推荐，Windows/Linux/macOS 都能用）:",
                    f"    {sys.executable} -m pip install rapidocr-onnxruntime",
                    "",
                    "macOS 也可以用系统 Vision：装 Xcode Command Line Tools 后",
                    f"    xcode-select --install",
                ],
            )

    print(f"# OCR 引擎: {engine} ｜ 帧数: {len(files)}", file=sys.stderr)
    t0 = time.time()

    if engine == "vision":
        results = run_vision(files)
    else:
        results = run_rapidocr(files, min_conf=args.min_conf)

    payload = json.dumps(results, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        n_lines = sum(len(r.get("lines", [])) for r in results)
        print(
            f"# 已写入 {args.out}（{len(results)} 帧 / {n_lines} 行，"
            f"耗时 {time.time()-t0:.0f}s）",
            file=sys.stderr,
        )
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

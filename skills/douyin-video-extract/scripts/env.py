#!/usr/bin/env python3
"""
跨平台环境解析 —— 本技能所有脚本共用。

═══════════════════════════════════════════════════════════════
铁律：任何脚本里都【不要】硬编码 /Users/... 或 C:\\... 这类绝对路径。
      这个技能是要分享给别人的，对方的机器可能是 Windows / Linux。
      一切都改成运行时解析。
═══════════════════════════════════════════════════════════════

解析顺序（find_ffmpeg）：
    环境变量 FFMPEG  >  当前解释器的 imageio-ffmpeg  >  其他解释器的 imageio-ffmpeg
                     >  PATH 里的 ffmpeg

    （最后两条的区别很重要：imageio-ffmpeg 装在了别的 venv 里、当前解释器
      import 不到时，仍然能把那个 ffmpeg 二进制找出来用。）

OCR 引擎（见 ocr_frames.py）：
    macOS  >  系统 Vision（快，且对描边花字更准）
    其他平台 >  RapidOCR（pip 装，纯跨平台，不需要任何系统组件）

自检：
    python env.py --check       # 解释器依赖矩阵 + ffmpeg/OCR 探测 + 缺什么、怎么装
    python env.py --which       # 只打印"该用哪个解释器"（给 shell 用）
    python env.py --ffmpeg      # 只打印 ffmpeg 路径

⚠️ 依赖必须装在【一个】解释器里，然后所有脚本都用它跑。
   库（rapidocr / faster-whisper）装在别的环境里，当前解释器 import 不到就是没有。
   最省事的做法：先按 --check 的推荐值定下 PY，后面一律用 $PY。
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys


# ─────────────────────────── 平台判断 ───────────────────────────

def os_name() -> str:
    """返回 'macos' / 'windows' / 'linux'"""
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


IS_WINDOWS = os_name() == "windows"
IS_MACOS = os_name() == "macos"


def exe(name: str) -> str:
    """Windows 上补 .exe 后缀"""
    if IS_WINDOWS and not name.lower().endswith(".exe"):
        return name + ".exe"
    return name


# ─────────────────────────── ffmpeg ───────────────────────────

_FFMPEG_CACHE: str | None = None


def _env_key(p: str) -> tuple:
    """判断两个解释器路径是不是【同一个环境】。

    规则：
      - 同一目录下的 python / python3 → 同一个环境（去重掉）
      - venv 的 bin/python 和基础解释器 → 不同环境（venv 的符号链接 realpath
        会指向基础解释器，但那不代表是同一个环境：sys.prefix 不同、
        site-packages 不同）。所以 key 里带上「路径所在的目录」。
    """
    ap = os.path.abspath(p)
    return (os.path.dirname(ap), os.path.realpath(ap))


def _python_candidates() -> list:
    """可能装着 imageio-ffmpeg 的解释器候选（按优先级）。

    为什么要跨解释器找：ffmpeg 是个【外部二进制】，任何一个装过
    imageio-ffmpeg 的 python 都能告诉我们它在哪，找到的路径对所有调用者都有效。
    （对比：rapidocr / faster-whisper 这类【库】必须当前解释器自己能 import，
      跨解释器找到也没用 —— 所以 have_module() 刻意不做这种探测。）
    """
    home = os.path.expanduser("~")
    here = os.path.dirname(os.path.abspath(__file__))
    venv_py = (os.path.join("Scripts", "python.exe") if IS_WINDOWS
               else os.path.join("bin", "python"))

    cands = [
        # 技能自带 / 旁边的 venv（用户按提示自建时最常见的位置）
        os.path.join(here, "..", ".venv", venv_py),
        os.path.join(here, ".venv", venv_py),
        # WorkBuddy 托管环境
        os.path.join(home, ".workbuddy", "binaries", "python", "envs", "default", venv_py),
        # PATH 上的解释器（Windows 上 py 是 launcher）
        shutil.which("py") if IS_WINDOWS else shutil.which("python3"),
        shutil.which("python"),
        None if IS_WINDOWS else "/usr/bin/python3",
    ]

    seen, uniq = set(), []
    for p in cands:
        if not p or not os.path.isfile(p):
            continue
        key = _env_key(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def _imageio_ffmpeg_via(py: str) -> str | None:
    """问某个解释器 imageio-ffmpeg 的 ffmpeg 在哪；问不到返回 None。"""
    try:
        r = subprocess.run(
            [py, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    lines = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
    p = lines[-1] if lines else ""
    return p if p and os.path.isfile(p) else None


def find_ffmpeg(refresh: bool = False) -> str:
    """找到可用的 ffmpeg。

    注意：Playwright 自己那份 `ffmpeg-mac` / `ffmpeg-win64` 是
    `--disable-everything` 编出来的，【没有 h264/aac 解码器】，不能用来抽帧。
    所以这里优先 imageio-ffmpeg 自带的那份（各平台都带完整解码器）。
    """
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE and not refresh and os.path.isfile(_FFMPEG_CACHE):
        return _FFMPEG_CACHE

    # 1) 显式指定
    cand = os.environ.get("FFMPEG", "").strip()
    if cand and os.path.isfile(cand):
        _FFMPEG_CACHE = cand
        return cand

    # 2) imageio-ffmpeg 自带（跨平台，推荐）
    #    2a) 先看当前解释器（最快，纯内存）
    try:
        import imageio_ffmpeg  # type: ignore
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            _FFMPEG_CACHE = p
            return p
    except Exception:
        pass
    #    2b) 当前解释器没有 → 逐个问其他解释器
    #        （常见情形：用户把 imageio-ffmpeg 装进了别的 venv）
    for py in _python_candidates():
        p = _imageio_ffmpeg_via(py)
        if p:
            _FFMPEG_CACHE = p
            return p

    # 3) PATH
    p = shutil.which(exe("ffmpeg"))
    if p:
        _FFMPEG_CACHE = p
        return p

    die(
        "找不到可用的 ffmpeg。",
        [
            "推荐（跨平台，一条命令搞定）：",
            f"    {sys.executable} -m pip install imageio-ffmpeg",
            "",
            "或者自己装一个系统级 ffmpeg 并确保在 PATH 里：",
            "    macOS   : brew install ffmpeg",
            "    Windows : winget install Gyan.FFmpeg   （或 scoop install ffmpeg）",
            "    Linux   : sudo apt install ffmpeg",
            "",
            "装好后也可以用环境变量直接指定：",
            "    macOS/Linux : export FFMPEG=/path/to/ffmpeg",
            "    Windows     : set FFMPEG=C:\\path\\to\\ffmpeg.exe",
        ],
    )


# ─────────────────────────── python / 依赖 ───────────────────────────

# 依赖清单：(import 名, pip 名, 用途, 是否必需)
DEPS = [
    ("imageio_ffmpeg", "imageio-ffmpeg", "抽帧 / 探测（同时提供 ffmpeg 二进制）", True),
    ("PIL", "pillow", "OCR 读图尺寸", True),
    ("numpy", "numpy", "RapidOCR 依赖", False),
    ("rapidocr_onnxruntime", "rapidocr-onnxruntime", "非 macOS 平台 OCR（macOS 用 Vision 可省）", False),
    ("faster_whisper", "faster-whisper", "口播 ASR（可选，只在没人声字幕时才要）", False),
]

# 矩阵里显示的短名字（避免被截断成 faste / rapid 这种没法读的）
SHORT = {
    "imageio_ffmpeg": "ffmpeg",
    "PIL": "pillow",
    "numpy": "numpy",
    "rapidocr_onnxruntime": "ocr",
    "faster_whisper": "asr",
}


def have_module(name: str) -> bool:
    """当前解释器能不能 import 这个模块。

    ⚠️ 只查当前解释器 —— 这是故意的。库必须由【正在跑脚本的那个解释器】
       自己能 import 才算数；别的解释器有并不代表能用（会变成假阳性）。
       跨解释器探测只对 ffmpeg 这种外部二进制成立，见 find_ffmpeg()。
    """
    try:
        __import__(name)
        return True
    except Exception:
        return False


def probe_interpreter(py: str) -> dict:
    """问某个解释器它装了清单里的哪些依赖。返回 {import名: bool}。"""
    code = (
        "import importlib,json,sys\n"
        "r={}\n"
        "for m in sys.argv[1:]:\n"
        "    try:\n"
        "        importlib.import_module(m); r[m]=True\n"
        "    except Exception:\n"
        "        r[m]=False\n"
        "print(json.dumps(r))\n"
    )
    try:
        r = subprocess.run(
            [py, "-c", code, *[m for m, _, _, _ in DEPS]],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0:
            import json as _json
            data = _json.loads((r.stdout or "").strip().splitlines()[-1])
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def recommend_python() -> str:
    """挑一个"最该拿来跑本技能脚本"的解释器。

    当前解释器满足必需依赖就用它；否则在候选里挑满足得最全的那个。
    优先返回带 venv 的路径（而不是 PATH 上的裸 python），因为裸 python 常常
    是系统自带、装不进去东西的那个。
    """
    cands = [sys.executable] + _python_candidates()
    scored = []
    for py in cands:
        if not os.path.isfile(py):
            continue
        got = probe_interpreter(py)
        if not got:
            continue
        req_ok = all(got.get(m) for m, _, _, req in DEPS if req)
        score = (req_ok, sum(1 for v in got.values() if v))
        scored.append((score, 0 if ".venv" in py or "envs" in py else 1, py, got))
    if not scored:
        return sys.executable
    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    return scored[0][2]


def python_hint() -> str:
    return (
        "  macOS/Linux : python3 -m venv .venv && source .venv/bin/activate\n"
        "  Windows     : py -m venv .venv && .venv\\Scripts\\activate"
    )


def die(msg: str, hints=None):
    print(f"\n[环境检查失败] {msg}\n", file=sys.stderr)
    for h in hints or []:
        print("  " + h, file=sys.stderr)
    print("", file=sys.stderr)
    sys.exit(1)


def require(module: str, pip_name: str, why: str):
    """确认【当前解释器】能 import 某模块，否则给出可操作的报错。"""
    if have_module(module):
        return
    if IS_WINDOWS:
        rerun = [
            '     $PY = python env.py --which',
            '     & $PY scripts/xxx.py ...            # PowerShell',
        ]
    else:
        rerun = [
            '     PY=$(python3 env.py --which)',
            '     "$PY" scripts/xxx.py ...',
        ]
    die(
        f"缺少依赖 {pip_name}（用途：{why}）",
        [
            "① 就装在当前解释器（最直接）：",
            f"     {sys.executable} -m pip install {pip_name}",
            "",
            "② 如果你确信已经装过了 —— 那就是【装到了别的解释器】：",
            "   库必须由正在跑脚本的那个解释器 import 得到，装在别的环境里等于没有。",
            "   先查该用哪个 python：",
            "     python env.py --check          # 找依赖矩阵里全是 ✓ 的那一行",
            "   然后用它重跑：",
            *rerun,
        ],
    )


# ─────────────────────────── 自检 ───────────────────────────

def _dep_matrix() -> list:
    """对候选解释器逐个探测依赖，返回 [(py, got), ...]（推荐的在最前）。"""
    cands = [sys.executable] + _python_candidates()
    seen, rows = set(), []
    for py in cands:
        if not os.path.isfile(py):
            continue
        key = _env_key(py)
        if key in seen:
            continue
        seen.add(key)
        got = probe_interpreter(py)
        if got:
            rows.append((py, got))
    rec = recommend_python()
    rows.sort(key=lambda r: (r[0] != rec, -sum(1 for v in r[1].values() if v)))
    return rows


def check(verbose: bool = True) -> dict:
    info = {"os": os_name(), "python": sys.version.split()[0]}
    print("═" * 68)
    print(f"  平台      : {os_name()}  ({platform.platform()})")
    print(f"  Python    : {sys.version.split()[0]}  ({sys.executable})")
    print("═" * 68)

    # ffmpeg
    try:
        ff = find_ffmpeg()
        info["ffmpeg"] = ff
        out = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=30)
        ver = (out.stdout or out.stderr or "").splitlines()[0][:70]
        print(f"  ✓ ffmpeg  : {ff}")
        print(f"              {ver}")
        # 关键解码器
        dec = subprocess.run([ff, "-hide_banner", "-decoders"], capture_output=True, text=True, timeout=30)
        for codec in ("h264", "aac"):
            ok = codec in (dec.stdout or "")
            print(f"              {'✓' if ok else '✗'} 解码器 {codec}")
            if not ok:
                print("                ⚠️ 缺这个解码器 → 抽帧会失败。换 imageio-ffmpeg 那份。")
    except SystemExit:
        info["ffmpeg"] = None

    # OCR 引擎
    engine, detail = pick_ocr_engine(probe=True)
    info["ocr_engine"] = engine
    print(f"  {'✓' if engine else '✗'} OCR     : {engine or '无可用引擎'}")
    print(f"              {detail}")
    if not engine:
        print("              装一个即可（跨平台）：")
        print(f"                {sys.executable} -m pip install rapidocr-onnxruntime")

    # ── 解释器依赖矩阵（跑脚本该用哪个 python）──
    print()
    print("─" * 68)
    print("  解释器依赖矩阵 —— ⚠️ 所有脚本必须用【同一个】解释器跑")
    print("  （库不像 ffmpeg，装在别的环境里当前解释器 import 不到就是没有）")
    print("─" * 68)

    rows = _dep_matrix()
    if not rows:
        print("  （没探测到任何解释器，用当前这个）")
        rec = sys.executable
    else:
        rec = rows[0][0]
        head = "  " + "解释器".ljust(50)
        for m, _, _, _ in DEPS:
            head += " " + SHORT.get(m, m[:6]).rjust(7)
        print(head)
        for py, got in rows:
            show = py
            home = os.path.expanduser("~")
            if show.startswith(home):
                show = "~" + show[len(home):]
            if len(show) > 48:
                show = "…" + show[-47:]
            line = "  " + (("→ " if py == rec else "  ") + show).ljust(50)
            for m, _, _, _ in DEPS:
                line += " " + ("  ✓".rjust(7) if got.get(m) else "  ·".rjust(7))
            print(line)

        missing = [n for m, n, _, req in DEPS if req and not rows[0][1].get(m)]
        print()
        if missing:
            pip_names = " ".join(n for m, n, _, req in DEPS if req and not rows[0][1].get(m))
            quoted = f'"{rec}"' if " " in rec else rec
            print(f"  ✗ 推荐解释器仍缺必需依赖：{', '.join(missing)}")
            print(f"    装它：{quoted} -m pip install {pip_names}")
        else:
            print("  ✓ 推荐解释器依赖齐全。")

    info["recommend_python"] = rec
    print()
    print(f"  👉 后续所有命令都用它：")
    print(f"       PY={rec}" if " " not in rec else f'       PY="{rec}"')
    print(f"       之后一律  $PY scripts/xxx.py ...")
    print("═" * 68)
    return info


def pick_ocr_engine(probe: bool = False):
    """选 OCR 引擎。返回 (引擎名 or None, 说明文本)

    macOS 有系统 Vision（快、对描边花字更准），编译一次即可；
    其他平台没有 Vision，用 RapidOCR。
    但【不能假设 macOS 一定有 swiftc】，所以两个都查，按可用性降级。
    """
    cwd = os.path.dirname(os.path.abspath(__file__))

    if IS_MACOS:
        swift_src = os.path.join(cwd, "subtitle_ocr.swift")
        swift_bin = os.path.join(cwd, exe("subtitle_ocr"))
        swiftc = shutil.which("swiftc")
        if os.path.isfile(swift_bin):
            return "vision", f"macOS Vision（已编译：{swift_bin}）"
        if swiftc and os.path.isfile(swift_src):
            return "vision", "macOS Vision（首次需编译：swiftc 可用）"
        # macOS 但没装 Xcode CLT → 降级
        if have_module("rapidocr_onnxruntime"):
            return "rapidocr", "macOS 上没找到 swiftc（Xcode CLT 未装），降级用 RapidOCR"

    if have_module("rapidocr_onnxruntime"):
        return "rapidocr", "RapidOCR（跨平台）"

    if IS_MACOS:
        return None, "macOS 既没 swiftc 也没 RapidOCR"
    return None, f"{os_name()} 上没有 Vision，需要 RapidOCR"


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--check" in args:
        check()
    elif "--which" in args:
        # 只打印"该用哪个解释器"，方便 shell 直接吃掉：PY=$(python env.py --which)
        print(recommend_python())
    elif "--ffmpeg" in args:
        print(find_ffmpeg())
    else:
        print(__doc__)

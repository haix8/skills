"""声剪 Voice Polish · 口播视频：转写 → 校对稿对齐 → 静音检测剪气口/删废句 → 烧录字幕 → 回转核对。

用法（先 --check 自检；缺依赖会打印安装命令并以退出码 2 中断）:
  1) python3 voice_polish.py 原片.MOV --transcribe-only      # 产出 <name>_raw.txt 供校对
  2) python3 voice_polish.py 原片.MOV --text 校对稿.txt       # 出片 + 回转核对
校对稿规则：保留原话每一个字（含说错重来的句子），只改错字；要删的话用 [[ ]] 括起来。
输出: <name><suffix>.mp4 / .srt / _check.txt；流程见 WORKFLOW.md
本机 ffmpeg 无 libass，字幕用 Pillow 渲染成 PNG 序列后 overlay。
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
# 字幕字体候选：(路径或 glob, ttc 内序号)。--font 或环境变量 VOICE_POLISH_FONT 可覆盖
FONT_CANDIDATES = {
    "darwin": [("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/PingFang.ttc", 11),  # 苹方 SC Semibold
               ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),  # 冬青黑体 W6
               ("/System/Library/Fonts/STHeiti Medium.ttc", 0)],
    "win32": [("C:/Windows/Fonts/msyhbd.ttc", 0),  # 微软雅黑 Bold
              ("C:/Windows/Fonts/msyh.ttc", 0)],
    "linux": [("/usr/share/fonts/**/NotoSansCJK-Bold.ttc", 2),
              ("/usr/share/fonts/**/wqy-microhei.ttc", 0)],
}
FONT = None  # (路径, 序号)，main() 里由 find_font() 填充
PUNCT = "，。！？、；：,.!?;:“”\"'‘’（）()…—《》"
BREAK_PUNCT = "，。！？；,.!?;…"


def find_font(override=None):
    import glob
    import os
    if override or os.environ.get("VOICE_POLISH_FONT"):
        spec = override or os.environ["VOICE_POLISH_FONT"]
        path, _, idx = spec.partition(":") if not re.match(r"^[A-Za-z]:[\\/]", spec) else (spec, "", "")
        return (path, int(idx or 0)) if Path(path).exists() else None
    key = "darwin" if IS_MAC else "win32" if IS_WIN else "linux"
    for pattern, idx in FONT_CANDIDATES[key]:
        hits = sorted(glob.glob(pattern, recursive=True))
        if hits:
            return hits[-1], idx
    return None


def hf_cached(repo):
    from huggingface_hub import constants
    d = Path(constants.HF_HUB_CACHE) / f"models--{repo.replace('/', '--')}" / "snapshots"
    return d.exists() and any(p.is_dir() and any(p.iterdir()) for p in d.iterdir())


def preflight(need_verify, allow_cpu, font_override=None):
    """运行前自检。缺必需依赖 → 打印原因和安装命令后中断（退出码 2）；只影响速度的项给警告。"""
    import os
    import platform
    import shutil
    fails, warns, oks = [], [], []
    mac_arm = IS_MAC and platform.machine() == "arm64"
    pip = "python3 -m pip install" if not IS_WIN else "py -m pip install"

    if sys.version_info < (3, 10):
        fails.append(("Python ≥ 3.10", f"当前 {platform.python_version()}",
                      "brew install python@3.12" if IS_MAC else "winget install Python.Python.3.12"))
    else:
        oks.append(f"Python {platform.python_version()}")

    ff = shutil.which("ffmpeg")
    if not ff or not shutil.which("ffprobe"):
        fails.append(("ffmpeg / ffprobe", "不在 PATH 里",
                      "brew install ffmpeg" if IS_MAC else "winget install Gyan.FFmpeg（装完重开终端）"))
    else:
        ver = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
        m = re.search(r"version (\d+)\.", ver)
        if m and int(m.group(1)) < 7:
            fails.append(("ffmpeg ≥ 7", ver, "升级 ffmpeg（脚本用到 -/filter_complex 读滤镜文件）"))
        else:
            oks.append(ver[:40])
        encs = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        hw = [e for e in ("h264_videotoolbox", "h264_nvenc", "h264_qsv", "h264_amf") if e in encs]
        if IS_MAC and "h264_videotoolbox" not in encs:
            warns.append("ffmpeg 不带 h264_videotoolbox，出片走 CPU（约慢一倍）")
        elif not IS_MAC:
            warns.append(f"非 Mac 平台出片暂走 CPU libx264（检测到硬件编码器：{', '.join(hw) or '无'}，脚本尚未接入）")

    for mod, name, cmd in (("PIL", "Pillow", f"{pip} pillow"),
                           ("faster_whisper", "faster-whisper（静音检测必需）", f"{pip} faster-whisper")):
        try:
            __import__(mod)
            oks.append(name)
        except ImportError:
            fails.append((name, "未安装", cmd))

    gpu = False
    if mac_arm:
        try:
            import mlx.core as mx
            import mlx_whisper  # noqa: F401
            mx.default_device()
            gpu = True
            oks.append("mlx-whisper（Apple GPU）")
        except ImportError as e:
            if "Metal" in str(e):
                why, cmd = "拿不到 GPU（在沙箱 / 远程 / 虚拟机会话里？）", "换到普通终端运行"
            else:
                why, cmd = "未安装", f"{pip} mlx-whisper"
            (warns if allow_cpu else fails).append(
                f"mlx-whisper：{why}，将用 CPU 转写" if allow_cpu else ("mlx-whisper（GPU 转写）", why, cmd))
    else:
        try:
            import ctranslate2
            gpu = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            gpu = False
        if gpu:
            oks.append("faster-whisper（CUDA GPU）")
        elif allow_cpu:
            warns.append("没有可用的 NVIDIA GPU，转写走 CPU（慢 3–4 倍）")
        else:
            fails.append(("CUDA GPU 转写", "未检测到可用的 NVIDIA GPU / CUDA 库",
                          "装 NVIDIA 驱动 + CUDA 12 / cuDNN 9 运行库；或加 --allow-cpu 接受 CPU 转写"))

    models = ["small"] + (["turbo"] if need_verify else [])
    for m in models:
        repo = MLX_MODELS[m] if gpu and mac_arm else FW_MODELS[m]
        if hf_cached(repo):
            oks.append(f"模型 {repo}")
        elif os.environ.get("HF_HUB_OFFLINE") == "1":
            fails.append((f"模型 {repo}", "本地没有，且设置了 HF_HUB_OFFLINE=1",
                          f"去掉 HF_HUB_OFFLINE 让脚本首次运行时下载，或：hf download {repo}"))
        else:
            warns.append(f"模型 {repo} 未下载，首次运行会自动下载（{MODEL_SIZE.get(m, '')}）")

    font = find_font(font_override)
    if font:
        oks.append(f"字体 {Path(font[0]).name}")
    else:
        fails.append(("中文字体", "找不到默认字体", "用 --font 指定一个中文 .ttf/.ttc（如 --font C:/Windows/Fonts/msyhbd.ttc）"))

    print("环境自检：")
    for o in oks:
        print(f"  ✓ {o}")
    for w_ in warns:
        print(f"  ! {w_}")
    for name, why, cmd in fails:
        print(f"  ✗ {name}：{why}\n      → {cmd}")
    if fails:
        print(f"\n缺少 {len(fails)} 项必需依赖，已中断。按上面的提示安装后重试（--check 只做自检）。")
        sys.exit(2)
    return font


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"命令失败: {' '.join(cmd[:6])}...\n{r.stderr[-2000:]}")
    return r.stdout


def probe(path):
    info = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json",
                           "-show_streams", "-show_format", str(path)]))
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if abs(rot) in (90, 270):
        w, h = h, w
    hdr = v.get("color_transfer") in ("arib-std-b67", "smpte2084")
    return w, h, float(num) / float(den), float(info["format"]["duration"]), hdr, rot


MLX_MODELS = {"turbo": "mlx-community/whisper-large-v3-turbo", "small": "mlx-community/whisper-small-mlx"}
FW_MODELS = {"turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "small": "Systran/faster-whisper-small"}
MODEL_SIZE = {"small": "约 0.5GB", "turbo": "约 1.6GB"}
PROMPT = "以下是普通话的口播内容，使用简体中文和标点。"


def transcribe(audio, model_name):
    """优先 mlx-whisper（Apple GPU），不可用时退回 faster-whisper（CPU）。返回 (words, lines, 引擎名)。"""
    try:
        if not IS_MAC:
            raise ImportError("mlx 仅支持 Apple 芯片")
        import mlx_whisper
        r = mlx_whisper.transcribe(str(audio), path_or_hf_repo=MLX_MODELS.get(model_name, model_name),
                                   language="zh", word_timestamps=True, initial_prompt=PROMPT, verbose=None)
        words = [[w["start"], w["end"], w["word"].strip()]
                 for s in r["segments"] for w in s.get("words", []) if w["word"].strip()]
        return words, [s["text"].strip() for s in r["segments"]], "mlx-whisper"
    except Exception as e:
        if IS_MAC:
            print(f"!! mlx-whisper 不可用（{type(e).__name__}），改用 faster-whisper")
    import ctranslate2
    from faster_whisper import WhisperModel
    cuda = ctranslate2.get_cuda_device_count() > 0
    model = WhisperModel(model_name, device="cuda" if cuda else "cpu",
                         compute_type="float16" if cuda else "int8")
    segs, _ = model.transcribe(str(audio), language="zh", word_timestamps=True,
                               vad_filter=False, beam_size=5, initial_prompt=PROMPT)
    words, lines = [], []
    for s in segs:
        lines.append(s.text.strip())
        for w in s.words:
            t = w.word.strip()
            if t:
                words.append([w.start, w.end, t])
    return words, lines, "faster-whisper/" + ("cuda" if cuda else "cpu")


def vad_segments(wav, threshold):
    """Silero VAD（faster-whisper 自带）给出的人声片段，秒。切口以此为准，不用转写时间戳。"""
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    audio = decode_audio(str(wav), 16000)
    segs = get_speech_timestamps(audio, VadOptions(threshold=threshold, min_silence_duration_ms=100,
                                                   speech_pad_ms=0, min_speech_duration_ms=100))
    return [[s["start"] / 16000, s["end"] / 16000] for s in segs]


def word_chars(words):
    """把词拆成逐字 [起, 止, 字]（多字词按字均分时间），去掉标点。"""
    out = []
    for s, e, t in words:
        clean = [c for c in t if c not in PUNCT and not c.isspace()]
        n = max(len(clean), 1)
        for k, c in enumerate(clean):
            out.append([s + (e - s) * k / n, s + (e - s) * (k + 1) / n, c])
    return out


def parse_text(text):
    """解析校对稿 → [字, 是否删除, 后面是否断句]。[[ ]] 内为要删的话，换行和句读标点视为断句。"""
    out, deleted = [], False
    i = 0
    while i < len(text):
        if text.startswith("[[", i):
            deleted, i = True, i + 2
            continue
        if text.startswith("]]", i):
            deleted, i = False, i + 2
            continue
        c = text[i]
        if c in BREAK_PUNCT or c == "\n":
            if out:
                out[-1][2] = True
        elif c not in PUNCT and not c.isspace():
            out.append([c, deleted, False])
        i += 1
    return out


def align(raw, corr):
    """校对稿逐字对齐到转写逐字时间。返回 (带时间的校对字列表, 转写→校对 的替换对)。"""
    a = "".join(c for _, _, c in raw)
    b = "".join(c for c, _, _ in corr)
    timed, pairs = [None] * len(corr), set()
    end_all = raw[-1][1] if raw else 0.0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(j2 - j1):
                timed[j1 + k] = (raw[i1 + k][0], raw[i1 + k][1])
            continue
        if op == "delete":
            continue
        if op == "replace":
            s, e = raw[i1][0], raw[i2 - 1][1]
            pairs.add((a[i1:i2], b[j1:j2]))
        else:  # insert：落在前后两个转写字之间
            s = raw[i1 - 1][1] if i1 > 0 else 0.0
            e = raw[i1][0] if i1 < len(raw) else end_all
            pairs.add(("", b[j1:j2]))
        n = j2 - j1
        for k in range(n):
            timed[j1 + k] = (s + (e - s) * k / n, s + (e - s) * (k + 1) / n)
    chars = [[t[0], t[1], c, dl, br] for t, (c, dl, br) in zip(timed, corr)]
    return chars, pairs


def drop_ranges(chars, speech, dur, snap=0.4):
    """连续的删除字 → 删除区间。边界吸附到附近的停顿里（转写时间戳只用来定位，不用来定边界），
    且吸附后不能越过前后保留字的中点。附近没有停顿时退回转写时间。"""
    runs, cur, prev_mid = [], None, 0.0
    for i, (s, e, _, dl, _) in enumerate(chars):
        if dl:
            if cur is None:
                cur = [s, e, prev_mid, dur]
            cur[1] = e
        else:
            if cur:
                cur[3] = (s + e) / 2
                runs.append(cur)
                cur = None
            prev_mid = (s + e) / 2
    if cur:
        runs.append(cur)
    gaps = [(0.0, speech[0][0])] if speech else []
    gaps += [(speech[i][1], speech[i + 1][0]) for i in range(len(speech) - 1)]
    gaps += [(speech[-1][1], dur)] if speech else []

    def dist(t, g):
        return 0.0 if g[0] <= t <= g[1] else min(abs(t - g[0]), abs(t - g[1]))

    out = []
    for s, e, lo, hi in runs:
        gs = [g for g in gaps if g[1] >= lo and dist(s, g) <= snap]
        ge = [g for g in gaps if g[0] <= hi and dist(e, g) <= snap]
        s2 = min(gs, key=lambda g: dist(s, g))[0] if gs else s
        e2 = min(ge, key=lambda g: dist(e, g))[1] if ge else e
        if e2 > s2:
            out.append([s2, e2])
    return out


def subtract(iv, drops):
    out = []
    for s, e in iv:
        parts = [[s, e]]
        for ds, de in drops:
            nxt = []
            for ps, pe in parts:
                if de <= ps or ds >= pe:
                    nxt.append([ps, pe])
                    continue
                if ds > ps:
                    nxt.append([ps, ds])
                if de < pe:
                    nxt.append([de, pe])
            parts = nxt
        out += [p for p in parts if p[1] - p[0] > 0.02]
    return out


def keep_intervals(speech, drops, gap, pad, dur):
    """人声片段减去删除区间 → 停顿 >gap 处切开 → 两侧留 pad → 再减一次删除区间防止 pad 漏进废句。"""
    iv = []
    for s, e in subtract(speech, drops):
        if iv and s - iv[-1][1] <= gap:
            iv[-1][1] = max(iv[-1][1], e)
        else:
            iv.append([s, e])
    out = []
    for s, e in iv:
        s, e = max(0.0, s - pad), min(dur, e + pad)
        if out and s <= out[-1][1]:
            out[-1][1] = e
        else:
            out.append([s, e])
    return subtract(out, drops)


def remap(t, iv):
    acc = 0.0
    for s, e in iv:
        if t < s:
            return acc
        if t <= e:
            return acc + t - s
        acc += e - s
    return acc


SOFT_AFTER = set("的了呢吧啊是在和就都也去被让把对跟说")


def build_captions(chars, iv, max_chars):
    """chars: [起, 止, 字, 断句]。先按断句/停顿切成短句，超长短句按字数均分并挑软断点，时间映射到剪后时间轴。"""
    sents, cur, prev_end = [], [], None
    for s, e, c, br in chars:
        if cur and prev_end is not None and s - prev_end > 0.3:
            sents.append(cur)
            cur = []
        cur.append((s, e, c))
        if br:
            sents.append(cur)
            cur = []
        prev_end = e
    if cur:
        sents.append(cur)

    caps = []
    for ch in sents:
        n = len(ch)
        lines = -(-n // max_chars) if n > max_chars + 2 else 1
        cuts, start = [], 0
        for li in range(1, lines):
            target = round(n * li / lines)
            best, score = target, -1e9
            for p in range(max(start + 4, target - 3), min(n - 3, target + 4)):
                sc = (ch[p][0] - ch[p - 1][1]) * 10 - abs(p - target) * 0.3
                if ch[p - 1][2] in SOFT_AFTER:
                    sc += 1.5
                if sc > score:
                    best, score = p, sc
            cuts.append(best)
            start = best
        for a, b in zip([0] + cuts, cuts + [n]):
            seg = ch[a:b]
            if seg:
                caps.append([remap(seg[0][0], iv), remap(seg[-1][1], iv), "".join(c for _, _, c in seg)])
    caps = [c for c in caps if c[1] > c[0]]  # 落在被剪区间里的字幕丢弃
    # 相邻字幕首尾衔接，避免闪烁
    for i in range(len(caps) - 1):
        if caps[i + 1][0] - caps[i][1] < 0.5:
            caps[i][1] = caps[i + 1][0]
    return caps


def fmt_srt(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def render_pngs(caps, w, h, total, workdir):
    """生成固定尺寸的透明字幕条 PNG，并写 ffconcat 列表。"""
    vertical = h > w
    size = int(w * (0.068 if vertical else 0.045))
    font = ImageFont.truetype(FONT[0], size, index=FONT[1])
    stroke = max(3, size // 10)
    box_h = int(size * 1.8)
    blank = workdir / "blank.png"
    Image.new("RGBA", (w, box_h), (0, 0, 0, 0)).save(blank)
    lines, t = ["ffconcat version 1.0"], 0.0

    def add(path, d):
        lines.append(f"file '{Path(path).as_posix()}'")
        lines.append(f"duration {max(d, 0.001):.3f}")

    for i, (s, e, text) in enumerate(caps):
        if s > t:
            add(blank, s - t)
        img = Image.new("RGBA", (w, box_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        tw = d.textlength(text, font=font)
        x, y = (w - tw) / 2, (box_h - size) / 2 - size * 0.12
        d.text((x + stroke * 0.6, y + stroke * 0.8), text, font=font,
               fill=(0, 0, 0, 120), stroke_width=stroke, stroke_fill=(0, 0, 0, 120))
        d.text((x, y), text, font=font, fill=(255, 255, 255, 255),
               stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        p = workdir / f"c{i:04d}.png"
        img.save(p)
        add(p, e - s)
        t = e
    if total > t:
        add(blank, total - t)
    lines.append(f"file '{blank.as_posix()}'")
    lst = workdir / "caps.ffconcat"
    lst.write_text("\n".join(lines))
    y_pos = int(h * (0.72 if vertical else 0.82))
    return lst, y_pos


def back_issues(out_wav, expected, corr, src_wav, model, work):
    """用一个模型回转成片，返回与应有文字的差异。该模型在原片上就会犯的错（原片转写 vs 校对稿）不算。"""
    cache = work / f"words_{model}.json"
    if cache.exists():
        src_words = json.loads(cache.read_text())
    else:
        src_words = transcribe(src_wav, model)[0]
        cache.write_text(json.dumps(src_words, ensure_ascii=False))
    _, known = align(word_chars(src_words), corr)
    back = word_chars(transcribe(out_wav, model)[0])
    b = "".join(c for _, _, c in back)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, expected, b, autojunk=False).get_opcodes():
        if op == "equal" or (b[j1:j2], expected[i1:i2]) in known:
            continue
        t = back[min(j1, len(back) - 1)][0] if back else 0.0
        out.append({"op": op, "i1": i1, "i2": i2, "exp": expected[i1:i2], "got": b[j1:j2], "t": t})
    sim = difflib.SequenceMatcher(None, expected, b, autojunk=False).ratio()
    return out, b, sim


def verify(out_mp4, expected, corr, src_wav, work):
    """回转核对：small（贴近原话，能听出重复）和 turbo（准，但会把重复整理掉）各转一遍成片。
    重点 = 两个模型在同一位置都有差异；或 small 听到的多余内容是紧邻上下文的重复（废句残留特征）。其余为低。"""
    wav = work / "out_audio.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(out_mp4), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    small, heard, sim = back_issues(wav, expected, corr, src_wav, "small", work)
    turbo, _, _ = back_issues(wav, expected, corr, src_wav, "turbo", work)

    def near(x, ys):
        return any(y["i1"] - 2 <= x["i2"] and x["i1"] <= y["i2"] + 2 for y in ys)

    def repeat(x):
        extra = x["got"].replace(x["exp"], "", 1) if x["exp"] else x["got"]
        ctx = expected[max(0, x["i1"] - 15):x["i2"] + 15]
        return len(extra) >= 2 and any(extra[k:k + 3] in ctx for k in range(len(extra) - 2)) if len(extra) >= 3 \
            else len(extra) >= 2 and extra in ctx

    issues = []
    for x in small:
        high = near(x, turbo) or (x["op"] in ("insert", "replace") and repeat(x))
        if x["op"] == "insert" and x["i1"] == len(expected):  # 片尾多字多为尾音幻听
            high = False
        kind = {"delete": "缺字", "insert": "多字", "replace": "不一致"}[x["op"]]
        issues.append((x["t"], kind, x["exp"], x["got"], expected[max(0, x["i1"] - 6):x["i1"]],
                       expected[x["i2"]:x["i2"] + 6], not high))
    return issues, sim, "small+turbo", heard


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="原片路径（--check 时可省略）")
    ap.add_argument("--text", help="校对稿：只改错字，要删的话用 [[ ]] 括起来")
    ap.add_argument("--transcribe-only", action="store_true", help="只转写，输出 <name>_raw.txt 供校对后退出")
    ap.add_argument("--model", default="small", help="small（默认，逐字照录、保留重复，废句才能被标出）/ turbo（字更准但会把重复整理掉）")
    ap.add_argument("--gap", type=float, default=0.3, help="人声间停顿超过该秒数就剪掉")
    ap.add_argument("--pad", type=float, default=0.08, help="切口两侧保留秒数")
    ap.add_argument("--vad", type=float, default=0.5, help="静音检测阈值，越高剪得越狠")
    ap.add_argument("--no-verify", action="store_true", help="跳过回转核对")
    ap.add_argument("--check", action="store_true", help="只做环境自检")
    ap.add_argument("--allow-cpu", action="store_true", help="没有 GPU 时允许用 CPU 转写（慢且错字更多），默认中断")
    ap.add_argument("--font", help="字幕字体路径，ttc 可写 路径:序号")
    ap.add_argument("--cpu", action="store_true", help="强制用 CPU 编码")
    ap.add_argument("--suffix", default="_cut", help="输出文件名后缀")
    a = ap.parse_args()

    global FONT
    FONT = preflight(not a.no_verify, a.allow_cpu, a.font)
    if a.check:
        print("自检通过。")
        return
    src = Path(a.input).resolve()
    if not src.exists():
        sys.exit(f"找不到视频文件：{src}")
    out_dir = Path.cwd()
    work = out_dir / f".{src.stem}_work"
    work.mkdir(exist_ok=True)
    timings = {}
    t0 = time.time()

    w, h, fps, dur, hdr, rot = probe(src)
    wav = work / "audio.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    timings["抽音频"] = time.time() - t0

    t1 = time.time()
    cache = work / f"words_{a.model}.json"
    if cache.exists():
        words = json.loads(cache.read_text())
    else:
        words, lines, engine = transcribe(wav, a.model)
        timings["转写引擎"] = engine
        cache.write_text(json.dumps(words, ensure_ascii=False))
        (out_dir / f"{src.stem}_raw.txt").write_text("\n".join(lines) + "\n")
    timings["转写"] = time.time() - t1
    if not words:
        sys.exit("没有识别到语音")
    if a.transcribe_only:
        print(f"转写完成 {time.time() - t0:.1f}s → {out_dir / (src.stem + '_raw.txt')}")
        return

    t2 = time.time()
    raw = word_chars(words)
    if a.text:
        corr = parse_text(Path(a.text).read_text())
        chars, _ = align(raw, corr)
    else:  # 没有校对稿：直接用转写文字，转写标点作为断句
        chars = []
        for s, e, t in words:
            for c in word_chars([[s, e, t]]):
                chars.append([c[0], c[1], c[2], False, False])
            if chars and any(p in BREAK_PUNCT for p in t):
                chars[-1][4] = True
        corr = [[c, False, br] for _, _, c, _, br in chars]
    speech = vad_segments(wav, a.vad)
    drops = drop_ranges(chars, speech, dur)
    iv = keep_intervals(speech, drops, a.gap, a.pad, dur)
    new_dur = sum(e - s for s, e in iv)
    timings["静音检测+对齐"] = time.time() - t2

    t3 = time.time()
    kept = [[s, e, c, br] for s, e, c, dl, br in chars if not dl]
    caps = build_captions(kept, iv, 12 if h > w else 18)
    srt = [f"{i}\n{fmt_srt(s)} --> {fmt_srt(e)}\n{t}\n" for i, (s, e, t) in enumerate(caps, 1)]
    (out_dir / f"{src.stem}{a.suffix}.srt").write_text("\n".join(srt))
    lst, y_pos = render_pngs(caps, w, h, new_dur, work)
    timings["分句+渲染字幕"] = time.time() - t3

    t4 = time.time()
    expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in iv)
    (work / "sel.txt").write_text(expr)
    out = out_dir / f"{src.stem}{a.suffix}.mp4"
    tail = (f"[0:a]aselect='{expr}',asetpts=N/SR/TB[a];"
            f"[1:v]format=rgba,fps={fps:.3f}[c];"
            f"[v][c]overlay=0:{y_pos}:eof_action=pass:format=auto,format=yuv420p[vo]")
    caps_in = ["-f", "concat", "-safe", "0", "-i", str(lst)]
    enc_a = ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]

    # 优先走 VideoToolbox：硬解 + GPU 旋转/调色 + 硬编（M1 Pro 上约快一倍）
    hw_ok = False
    turn = {0: "", -90: "transpose_vt=dir=clock,", 270: "transpose_vt=dir=clock,",
            90: "transpose_vt=dir=cclock,", -270: "transpose_vt=dir=cclock,"}.get(rot)
    if turn is not None and not a.cpu:
        color = ("scale_vt=color_matrix=bt709:color_primaries=bt709:color_transfer=bt709,"
                 "hwdownload,format=p010le,") if hdr else "hwdownload,format=nv12,"
        fc_file = work / "filter_vt.txt"
        fc_file.write_text(f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,{turn}{color}format=yuv420p[v];" + tail)
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-noautorotate",
                            "-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld",
                            "-i", str(src), *caps_in, "-/filter_complex", str(fc_file),
                            "-map", "[vo]", "-map", "[a]", "-c:v", "h264_videotoolbox", "-b:v", "8M", *enc_a],
                           capture_output=True, text=True)
        hw_ok = r.returncode == 0
        if not hw_ok:
            print("!! 硬件路径失败，改用 CPU：", r.stderr.strip().splitlines()[-1:] if r.stderr else "")
    if not hw_ok:
        # HDR(HLG/PQ) 转 SDR：本机 ffmpeg 无 zscale，用 colorspace 做 bt2020→bt709 近似转换
        cs = "colorspace=all=bt709:iall=bt2020:itrc=bt2020-10:format=yuv420p," if hdr else ""
        fc_file = work / "filter.txt"
        fc_file.write_text(f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,{cs}format=yuv420p[v];" + tail)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src), *caps_in,
             "-/filter_complex", str(fc_file), "-map", "[vo]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", *enc_a])
    timings["编码方式"] = "VideoToolbox" if hw_ok else "CPU libx264"
    timings["剪辑+烧字幕+编码"] = time.time() - t4

    report = None
    if not a.no_verify:
        t5 = time.time()
        expected = "".join(c for _, _, c, _ in kept)
        issues, sim, engine, heard = verify(out, expected, corr, wav, work)
        report = out_dir / f"{src.stem}{a.suffix}_check.txt"
        high = [x for x in issues if not x[6]]
        low = [x for x in issues if x[6]]
        lines = [f"回转核对（{engine}）：与应有文字相似度 {sim:.1%}，重点 {len(high)} 处，低 {len(low)} 处"]
        for title, group in (("重点（请听这些位置：可能吞字、废句残留、字幕与原声不符）", high),
                             ("低（多为识别误差，抽空看一眼）", low)):
            lines += ["", title]
            for t, kind, exp, got, before, after, _ in group:
                lines.append(f"  {fmt_srt(t)[:8]}  {kind}  应为「{exp}」 听到「{got}」  …{before}【】{after}…")
        lines += ["", "应有文字：", expected, "", "成片听到：", heard]
        report.write_text("\n".join(lines) + "\n")
        timings["回转核对"] = time.time() - t5
        timings["核对结果"] = f"相似度 {sim:.1%}，重点 {len(high)} 处，低 {len(low)} 处"
    timings["总计"] = time.time() - t0

    print(f"原时长 {dur:.2f}s → 剪后 {new_dur:.2f}s（剪掉 {dur - new_dur:.2f}s，"
          f"{len(iv) - 1} 处切口，删句 {len(drops)} 段，{len(caps)} 条字幕）")
    for k, v in timings.items():
        print(f"{k}: {v:.1f}s" if isinstance(v, float) else f"{k}: {v}")
    print(out)
    if report:
        print(report)


if __name__ == "__main__":
    main()

# 声剪 Voice Polish · 口播视频自动剪辑工作流

> 作为技能使用时，脚本位于技能目录下的 `scripts/voice_polish.py`（Claude Code 个人安装为 `~/.claude/skills/voice-polish/`），执行步骤见技能目录的 `SKILL.md`；下文命令里的 `voice_polish.py` 指这个路径。

输入一条口播原片，输出：剪掉气口、删掉说错重来的句子、烧好字幕的成片 + SRT 字幕 + 核对报告。

实测（IMG_6404.MOV，132 秒，iPhone HLG HDR 竖拍，M1 Pro）：脚本两步合计约 60 秒（不含校对），132 秒 → 90 秒。

## 设计原则

| 要回答的问题 | 由谁回答 | 为什么 |
|---|---|---|
| 哪里是停顿/气口 | 静音检测（Silero VAD） | 停顿是声音事实；转写时间戳是推测的，会把停顿吞进字里 |
| 说了什么 | 转写（small）+ 大模型校对 | small 逐字照录、保留重复，废句才看得见；错字交给校对 |
| 哪些话不要 | 大模型在校对稿里用 `[[ ]]` 标出 | 大模型擅长判断文字，不擅长读秒数 |
| 字和时间怎么对上 | 代码把校对稿逐字对齐到转写 | 确定性操作，不让大模型处理时间 |
| 成片对不对 | 成片用两个模型回转，和应有文字比对 | 不能用生成字幕的同一份文字自证 |

## 流程图

```mermaid
flowchart TD
    A[/原片 xxx.MOV/] --> S1
    S1["① 转写（脚本，约 8 秒）<br/>mlx-whisper small"] --> F1[/xxx_raw.txt/]
    F1 --> S2["② 校对（大模型）<br/>只改错字，废句用 [[ ]] 括起来"]
    S2 --> F2[/xxx_corrected.txt/]
    F2 --> S3
    A --> S3
    subgraph S3["③ 出片 + 核对（脚本，约 50 秒）"]
        direction TB
        S3a[校对稿逐字对齐到转写时间] --> S3b[VAD 人声片段<br/>减去废句 → 停顿 >0.3s 剪掉]
        S3b --> S3c[字幕渲染 + VideoToolbox 出片]
        S3c --> S3d[small + turbo 回转成片<br/>与应有文字比对]
    end
    S3 --> O1[/xxx_final.mp4 + .srt/]
    S3 --> O2[/xxx_final_check.txt/]
    O2 --> Q{人：听"重点"位置}
    Q -- 有问题 --> S2
    Q -- 通过 --> D[交付]
```

## 每一步怎么跑

| 步骤 | 谁来做 | 命令 / 动作 | 输入 | 输出 |
|---|---|---|---|---|
| ⓪ 环境自检 | agent | `python3 voice_polish.py --check`；失败就把 ✗ 项和安装命令转述给用户并**停止**，不收视频 | — | 自检结果（退出码 0 通过 / 2 缺依赖） |
| ① 转写 | 脚本 | `python3 voice_polish.py 原片.MOV --transcribe-only` | 原片 | `xxx_raw.txt` |
| ② 校对 | 大模型 | 按下方规则改写 `xxx_raw.txt` | `xxx_raw.txt` | `xxx_corrected.txt` |
| ③ 出片 + 核对 | 脚本 | `python3 voice_polish.py 原片.MOV --text xxx_corrected.txt --suffix _final` | 原片、校对稿 | `xxx_final.mp4`、`.srt`、`_check.txt` |
| ④ 确认 | 人 | 只听核对报告"重点"列出的位置；有问题改校对稿重跑 ③ | 成片、报告 | — |

③ 复用 ① 的转写缓存；改了校对稿只需重跑 ③（约 50 秒，其中核对约 18–30 秒，可用 `--no-verify` 跳过）。

## 第 ② 步的校对规则（给大模型的提示词要点）

产出一份完整的校对稿 `xxx_corrected.txt`：

1. **保留原话的每一个字**，包括口头禅（呢、然后、已经）和说错重来的句子。不要润色、不要删字、不要调整语序。
2. **只改识别错的字**，例如：捞客→唠嗑、PBA→BBA、去命→祛魅、代骗→带偏、问及/问家→问界、支架→智驾、支换→置换、有越理→有阅历。
3. **要删的话用 `[[ ]]` 括起来**。说错重来的句子只保留最后一遍，前面几遍整体括起来。可以跨行。
4. 标点和换行用于字幕断句，按说话停顿加。
5. 拿不准的字照样写出最可能的版本，另外列给人确认。

示例：
```
然后奔驰开这么多年，我已经对豪车品牌已经祛魅了，
[[不再迷信那些大品牌所谓的那些光环，当然也会被网上，]]
不会迷信那些大品牌的那种光环，[[当然也会被网上那波网红，]]
当然也会被网上那波网红的各种言论去带偏我的节奏，
```

## 核对报告怎么看（xxx_final_check.txt）

- **重点**：两个模型在同一位置都听出差异，或 small 听到了紧邻上下文的重复（废句残留特征）。**只需要听这些位置。**
- **低**：只有一个模型报的差异，多为识别误差，抽空扫一眼。
- 报告末尾附"应有文字"和"成片听到"全文，便于对照。
- 实测：本条素材重点 4 处，均为已知情况（原声"这个台车"、字幕写"这台车"；"问界"两个模型都听不准），无漏剪、无吞字。

## 涉及的文件

### 固定文件

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能入口：agent 的执行步骤和停止条件 |
| `scripts/voice_polish.py` | 主脚本 |
| `references/WORKFLOW.md` | 本文档 |

### 每条视频产生的文件（在运行目录下）

| 文件 | 阶段 | 用途 | 是否保留 |
|---|---|---|---|
| `xxx_raw.txt` | ① | 转写原文，给大模型校对 | 可删 |
| `xxx_corrected.txt` | ② | 校对稿（含 `[[ ]]` 删除标记） | 想重出片就留 |
| `xxx_final.mp4` | ③ | 成片 | **交付物** |
| `xxx_final.srt` | ③ | 字幕 | **交付物** |
| `xxx_final_check.txt` | ③ | 核对报告 | 确认后可删 |
| `.xxx_work/` | ①③ | 中间文件目录 | 交付后可整个删除 |

`.xxx_work/` 内：`audio.wav`（原片音频）、`out_audio.wav`（成片音频）、`words_small.json` / `words_turbo.json`（原片转写缓存，turbo 只用于核对）、`c0000.png…` / `blank.png` / `caps.ffconcat`（字幕图片和时间表）、`sel.txt`、`filter_vt.txt` / `filter.txt`（ffmpeg 滤镜脚本）。

## 依赖与跨平台对照

> 标记：✅ 本机（M1 Pro / macOS）实测　⚠️ 按资料编写，**未在该平台实测**　🚧 脚本尚未接入

### 依赖总表

| 作用 | macOS（Apple 芯片） | Windows | 必需？ |
|---|---|---|---|
| 运行脚本 | Python ≥ 3.10 ✅ | Python ≥ 3.10 ⚠️ | 必需 |
| 抽音频 / 剪辑 / 编码 | ffmpeg ≥ 7 ✅（本机 9.0.1，Homebrew） | ffmpeg ≥ 7 ⚠️（gyan.dev 或 BtbN 构建） | 必需 |
| 静音检测（VAD） | faster-whisper 自带 Silero VAD ✅ | 同左 ⚠️（跨平台 ONNX，预期一致） | 必需 |
| 字幕渲染 | Pillow ✅ | Pillow ⚠️ | 必需 |
| 转写 / 回转（GPU） | **mlx-whisper**（Apple GPU）✅ | **faster-whisper + CUDA**（NVIDIA 显卡）⚠️ | 默认必需；`--allow-cpu` 可降级 |
| 转写（CPU 降级） | faster-whisper CPU int8 ✅（约 32 秒/132 秒素材） | 同左 ⚠️ | 降级用 |
| 转写模型 small | `mlx-community/whisper-small-mlx`（459MB）✅ | `Systran/faster-whisper-small`（约 0.5GB）⚠️ | 必需 |
| 核对模型 turbo | `mlx-community/whisper-large-v3-turbo`（1.5GB）✅ | `mobiuslabsgmbh/faster-whisper-large-v3-turbo`（约 1.6GB）⚠️ | 核对时必需 |
| 硬件解码 / 旋转 / HDR 转 SDR / 编码 | VideoToolbox（`transpose_vt`、`scale_vt`、`h264_videotoolbox`）✅ | NVENC `h264_nvenc` / Intel `h264_qsv` / AMD `h264_amf` 🚧 目前走 CPU libx264 | 可选（只影响速度） |
| HDR 转 SDR（CPU 路径） | ffmpeg `colorspace` 近似转换 ✅ | 同左 ⚠️；Windows 常见构建带 `zscale`/`libplacebo`，可做更准的色调映射 🚧 | HDR 素材必需 |
| 字幕字体 | 苹方 SC Semibold → 冬青黑体 W6 → 华文黑体，自动查找 ✅ | 微软雅黑 Bold `C:/Windows/Fonts/msyhbd.ttc` ⚠️ | 必需；`--font` 可指定 |

### 安装命令

| 平台 | 命令 |
|---|---|
| macOS ✅ | `brew install ffmpeg`<br>`python3 -m pip install mlx-whisper faster-whisper pillow` |
| Windows ⚠️ | `winget install Gyan.FFmpeg`（装完重开终端）<br>`py -m pip install faster-whisper pillow`<br>GPU：NVIDIA 驱动 + CUDA 12 / cuDNN 9 运行库（faster-whisper 的 CTranslate2 后端要求，具体以其 README 为准） |
| 模型（两平台） | 联网时首次运行自动下载；离线环境先 `hf download <repo>` |

### 本机实际安装位置（macOS）

| 依赖 | 位置 |
|---|---|
| ffmpeg 9.0.1 | `/opt/homebrew/bin/ffmpeg` |
| Python 3.10.17 及以上各包 | pyenv `~/.pyenv/versions/3.10.17` |
| 模型缓存 | `~/.cache/huggingface/hub`（受 `HF_HOME` / `HF_HUB_CACHE` 影响） |
| 苹方字体 | `/System/Library/AssetsV2/com_apple_MobileAsset_Font*/…/PingFang.ttc`（带哈希路径，脚本按通配符查找） |

### Windows 上目前的差距（🚧）

- 出片走 CPU libx264，速度预计约为 Mac 硬件路径的一半（未实测）。接入 NVENC 需要新增一条滤镜链（`-hwaccel cuda` + `h264_nvenc`，HDR 用 `zscale`/`tonemap` 或 `libplacebo`）。
- 已为 Windows 做的兼容：字幕图片清单用正斜杠路径（ffconcat 里反斜杠是转义符）、字体按平台查找、faster-whisper 自动选 CUDA / CPU。以上均未在 Windows 实测。

## 环境自检（两层）

| 层 | 何时 | 做什么 |
|---|---|---|
| **对话层（主）** | 用户启用技能后、发视频前 | agent 先跑 `python3 voice_polish.py --check`；退出码 2 时把 ✗ 项（缺什么、为什么、安装命令）用人话告诉用户，**停止流程**，等用户装好再继续 |
| **脚本层（兜底）** | 每次运行脚本开头 | 同一套检查；缺必需项打印原因 + 命令，退出码 2 中断，防止有人绕过 agent 直接运行 |

自检项：Python 版本、ffmpeg/ffprobe 及版本、Pillow、faster-whisper、GPU 转写可用性（Mac：mlx + Metal；Windows：CUDA 设备）、所需模型是否已缓存（离线时缺模型即失败，联网时提示首次下载）、中文字体；硬件编码器缺失只警告不中断。

已在本机实测的三种情况：正常环境通过；模拟缺 faster-whisper + 离线缺模型 → 列出 3 项并中断；Claude Code 沙箱内拿不到 GPU → 提示"换到普通终端运行"并中断（加 `--allow-cpu` 后改为警告，并正确指出 CPU 核对所需的 turbo 模型未下载）。

## 脚本参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--transcribe-only` | 关 | 只转写，产出 `xxx_raw.txt` |
| `--text` | 无 | 校对稿；不给则直接用转写文字、不删句 |
| `--model` | `small` | 转写模型；`turbo` 字更准但会把重复整理掉，废句标不出来 |
| `--gap` | `0.3` | 人声间停顿超过多少秒就剪 |
| `--pad` | `0.08` | 切口两侧保留秒数，防吞字 |
| `--vad` | `0.5` | 静音检测阈值，越高剪得越狠（0.35 约少剪 10 处） |
| `--no-verify` | 关 | 跳过回转核对（省 18–30 秒） |
| `--check` | 关 | 只做环境自检（agent 第 ⓪ 步调用） |
| `--allow-cpu` | 关 | 没有 GPU 时允许 CPU 转写（慢、错字多），默认中断 |
| `--font` | 自动 | 字幕字体，ttc 可写 `路径:序号`；也可用环境变量 `VOICE_POLISH_FONT` |
| `--suffix` | `_cut` | 输出文件名后缀 |
| `--cpu` | 关 | 强制 CPU 编码 |

## 运行要求

- 必须在**能访问 GPU 的环境**运行（普通终端即可）。Claude Code 沙箱里拿不到 GPU 和硬件编码器，自检会中断；加 `--allow-cpu` 才会降级：转写变 faster-whisper CPU（约 32 秒），出片变 libx264（约 40 秒）。
- 建议设 `HF_HUB_OFFLINE=1`，避免每次联网检查模型。

## 已知限制

- 大模型听不到声音：同音词（如"智驾/支架"）只能靠上下文推断，需要人确认。
- 删句边界：优先吸附到附近 0.4 秒内的停顿；废句和保留句之间没有停顿时，退回转写时间，可能残留或切掉半个字，核对报告会提示。
- 核对报告"低"一档噪音较多（本条 24 处），主要是 small 在剪辑后短上下文里的识别误差。
- 字幕断行没有分词，偶尔会把一个词拆到两行。
- 只验证过 macOS + iPhone 竖拍（旋转 -90°）的 HLG 素材；Windows 全部未实测。

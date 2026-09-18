# 抖音视频拆解 / Douyin Video Teardown

一个 WorkBuddy / Agent Skill：**把一条抖音链接变成「原片 + 带时间戳的逐句文案 + 互动数据 + 形态与结构分析」**。

面向短视频与广告素材的拆解场景 —— 不只是把话扒下来，而是回答「这条片子是怎么组织的、为什么这么剪」。

---

## 它做什么

1. **解析短链**：`v.douyin.com/xxx` → 作品详情（点赞 / 收藏 / 转发 / 评论、型号、发布者、话题、音乐）
2. **下载原片**：取最高码率档，并**校验音轨**（抖音会分轨，个别档位下下来没有声音）
3. **三层提取逐句文案**，然后交叉校验：
   - **L1 官方字幕轨** —— 创作者上传过就是零错字，命中即止
   - **L2 口播 ASR** —— faster-whisper，负责时间轴与画面无花字时的兜底
   - **L3 画面花字 OCR** —— 创作者自己打上去的字，近零错字，且是**金句卡 / 强调卡、字幕配色层级、画面有字但没念出来**的唯一来源
4. **形态检测**：剪辑点数量 + 强调卡区间 → 判定「一镜到底 / 快切带货 / 录屏演示」
5. **出报告**：HTML（含模板）+ Markdown，逐句文案带时间戳与来源层标注

## 安装

作为 WorkBuddy 技能使用：

```bash
git clone https://github.com/<your-name>/douyin-video-extract.git
mkdir -p ~/.workbuddy/skills
cp -r douyin-video-extract ~/.workbuddy/skills/
```

也可以把本仓库链接直接贴进 WorkBuddy 对话框，让它自动安装。

## 环境准备

**先跑自检**，它会打印平台、ffmpeg 是否带 h264/aac 解码器、OCR 引擎、
以及一张**解释器依赖矩阵**，并给出对应平台的安装命令：

```bash
python scripts/env.py --check
```

自检最后会打印一行 `👉 后续所有命令都用它：PY=...`。**后面每一步都用这个解释器。**

> ⚠️ 这是最容易踩的坑：库（rapidocr / pillow / faster-whisper）必须由**正在跑脚本的那个解释器**
> 能 `import` 到。装到别的 venv 里，当前解释器就是看不见，会报「没有可用引擎」——
> 但其实是装错地方了，不是没装。

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
pip install imageio-ffmpeg rapidocr-onnxruntime pillow faster-whisper

# Windows（PowerShell / cmd）
py -m venv .venv
.venv\Scripts\activate
pip install imageio-ffmpeg rapidocr-onnxruntime pillow faster-whisper
```

| 包 | 用途 | 必需性 |
|---|---|---|
| `imageio-ffmpeg` | **各平台自带完整解码器的 ffmpeg** | 必需 |
| `rapidocr-onnxruntime` | 跨平台中文 OCR（Windows / Linux 的唯一选择） | 非 macOS 必需 |
| `pillow` | 读图像尺寸（OCR 坐标归一化用） | 必需 |
| `faster-whisper` | 口播 ASR | 需要转写口播时 |

> **ffmpeg 必须带完整解码器。** Playwright 自带的 `ffmpeg-mac` / `ffmpeg-win64` 是
> `--disable-everything` 编出来的，没有 h264/aac，抽帧会直接报 `Unknown decoder 'h264'`。

Node 侧（给 `dy_fetch.js` 用）：

```bash
npm install playwright-core
npx playwright install chromium
```

脚本会自动按 `CHROME` 环境变量 → playwright 报告路径 → `ms-playwright` 缓存 → 系统 Chrome/Edge
的顺序找 Chromium。**Windows 上系统自带 Edge，通常无需任何操作。**

## 快速开始

```bash
PY=$(python3 scripts/env.py --which)

# 1) 取详情（每次都要存 --save-json，L1 要用原始结构）
node scripts/dy_fetch.js "https://v.douyin.com/xxxxx/" \
  --save-json detail.json --download out.mp4 > summary.json

# 2) 看 summary.json 里的 subtitle_count 决定要不要跑 L1
$PY scripts/subtitle_track.py --from-detail detail.json --timestamps -o l1.txt   # 退出码 2 = 没有字幕轨，正常

# 3) L2 与 L3 并行（互不依赖）
$PY scripts/asr_transcribe.py out.mp4 --model base --timestamps -o l2.txt
$PY scripts/extract_frames.py out.mp4 --fps auto -o frames/
$PY scripts/ocr_frames.py "frames/f_*.jpg" -o ocr.json

# 4) 解析 OCR 结果
$PY scripts/parse_ocr.py ocr.json --bands                             # 先确认分带
$PY scripts/parse_ocr.py ocr.json --subtitles --timestamps -o l3.txt
$PY scripts/parse_ocr.py ocr.json --cards                             # 金句卡 / 强调卡

# 5) 形态检测
$PY scripts/extract_frames.py out.mp4 --scenes
```

最后以 `templates/report_template.html` 为底稿填内容出报告（不要重写 CSS）。

## 目录结构

```
douyin-video-extract/
├── SKILL.md                        # 技能定义与完整工作流
├── scripts/
│   ├── env.py                      # 环境解析与自检（先跑 --check）
│   ├── dy_fetch.js                 # 短链解析 / 详情 / 下载
│   ├── extract_frames.py           # 抽帧 · 剪辑点检测 · 视频信息
│   ├── ocr_frames.py               # 画面花字 OCR（Vision / RapidOCR 自动切换）
│   ├── parse_ocr.py                # OCR 结果 → 时间轴 + 强调卡 + 自动分带
│   ├── asr_transcribe.py           # L2 口播转写
│   ├── subtitle_track.py           # L1 官方字幕轨
│   └── subtitle_ocr.swift          # macOS Vision OCR 源码（缺失时自动编译）
├── references/                     # 按需加载的补充材料
│   ├── ocr-engines.md              # 两套 OCR 引擎的实测准确率对比
│   ├── sampling-budget.md          # 抽帧 fps 预算与三层耗时基准
│   ├── accuracy-evidence.md        # ASR / OCR 误读样本库
│   └── troubleshooting.md          # 故障处置表
└── templates/
    └── report_template.html        # 报告模板（含全套 CSS）
```

## 几个设计取舍

- **不盲目先跑 L1。** 用详情里的 `subtitle_count` 判断即可 —— 抖音口播类创作者极少上传字幕轨，
  先跑 L1 几乎总是白跑一次。
- **L2 便宜 ≠ L2 能顶替 L3。** ASR 快得多（39 秒音频 7 秒 vs OCR 40 秒），但画面花字是
  创作者自己打上去的，近零错字，而且是金句卡、配色层级、画面有字没念出来这三类信息的**唯一来源**。
- **抽帧「≤800 帧」是时间预算，不是准确率需求。** 实测字幕平均 1.5–3 秒才换一条，6fps 下
  绝大多数帧是重复的。降帧率能省 2.6–3.3 倍时间，但会丢掉开场的闪现钩子（实测有片头大字只显示 0.2 秒）。
- **投流素材的自然互动天然低。** 实测一个有 91.5 万粉的账号，其投流素材只有 203 赞 / 0 评论 ——
  所以点赞数不能当内容质量判据，要看互动**比值**（收藏÷点赞、评论÷点赞、转发÷点赞）。

## 已知限制

- **依赖抖音 Web 端接口。** 接口或签名机制一变，取详情 / 下载部分就会失效，需要跟进修复。
- 强依赖本机 ffmpeg 与 OCR / ASR 运行环境，首次安装有一定门槛。
- 抽帧 OCR 对**描边花字与艺术字**仍会整句认错，关键帧需人工用眼看一遍确认。

## ⚠️ 免责声明

本项目**仅供学习研究与自有素材分析使用**。

- 抖音平台上的视频、音频、文案等内容，**版权始终属于原作者与字节跳动**，本项目不主张任何权利。
- 请勿将本项目用于**抓取、下载、传播他人作品**，或任何侵犯他人合法权益的用途。
- 请勿用于**商业用途**。使用者应自行确保其行为符合抖音平台服务条款及所在地法律法规
  （包括但不限于著作权、反不正当竞争、个人信息保护相关法律）。
- 本项目按「原样」提供，不对可用性、准确性或使用后果作任何担保。
  **使用者对自己的一切行为及其后果负全部责任**，作者不承担任何连带责任。
- 若相关权利人认为本项目内容侵犯其权益，请联系我，我会及时删除相关内容。

## License

[MIT](LICENSE)

---
name: douyin-video-extract
description: 拆解抖音视频/广告素材——解析短链接、拉取作品详情与互动数据、下载竖屏原片、三层提取逐句文案（官方字幕轨 / 口播 ASR / 画面花字 OCR）、检测剪辑形态与金句卡，最终产出带时间戳的文案与 HTML + Markdown 拆解报告。当用户发来 v.douyin.com 短链或抖音作品链接并要求「拆解视频」「提取文案」「分析爆款」「扒字幕」时使用。
category: writing
version: 1.0.0
---

# 抖音视频拆解

目标：把一条抖音链接变成「原片 + 带时间戳的逐句文案 + 互动数据 + 形态与结构分析」。

## 文件清单

| 文件 | 作用 |
|---|---|
| `scripts/env.py` | **环境解析与自检**（ffmpeg / OCR / ASR / 解释器依赖矩阵）。第一次用先跑 `--check` |
| `scripts/dy_fetch.js` | 解析短链 → 浏览器内取详情 → 下载原片；运行时自动解析 Chromium |
| `scripts/extract_frames.py` | 抽帧（`--fps auto`）/ 剪辑点检测（`--scenes`）/ 视频信息（`--info`） |
| `scripts/ocr_frames.py` | 画面花字 OCR（自动选 Vision 或 RapidOCR） |
| `scripts/parse_ocr.py` | 解析 OCR 结果 → 字幕时间轴 + 强调卡区间 + 自动分带 |
| `scripts/subtitle_track.py` | L1 官方字幕轨（VTT/SRT）解析，带滚动去重 |
| `scripts/asr_transcribe.py` | L2 口播语音转文字（faster-whisper） |
| `scripts/subtitle_ocr.swift` | macOS Vision OCR 的源码（非必需，缺失时自动编译） |
| `templates/report_template.html` | 报告 HTML 模板（含全套 CSS，直接填内容，不要重写样式） |
| `references/ocr-engines.md` | OCR 引擎选择与 Vision / RapidOCR 实测对比 |
| `references/sampling-budget.md` | 抽帧 fps 预算、三层耗时基准、ASR 模型选型 |
| `references/accuracy-evidence.md` | ASR 与 OCR 的误读样本库（交叉校验时查） |
| `references/troubleshooting.md` | 故障处置表（按现象查） |

---

## Step 0 — 环境准备

### 0.1 先自检

```bash
python scripts/env.py --check
```

它会打印：平台 / Python 版本 / ffmpeg 是否可用（**并检查 h264、aac 解码器**）/
OCR 引擎 / **解释器依赖矩阵**，缺什么就给出**对应平台**的安装命令。

### 0.2 定下「用哪个解释器」

自检最后会打印一行 `👉 后续所有命令都用它：PY=...`。**记住这个路径，后面每一步都用它。**

依据是自检里那张依赖矩阵：**哪一行全是 `✓` 就用哪一行。**
库（rapidocr / pillow / faster-whisper）必须由**正在跑脚本的那个解释器** import 得到 ——
装到别的环境里，当前解释器就是看不见，会报"没有可用引擎"，但其实是装错地方了。

```bash
# macOS / Linux
PY=$(python3 scripts/env.py --which)
"$PY" scripts/ocr_frames.py "frames/f_*.jpg" -o ocr.json

# Windows PowerShell
$PY = python scripts/env.py --which
& $PY scripts/ocr_frames.py "frames/f_*.jpg" -o ocr.json
```

`env.py --which` 只打印该用的解释器路径（方便脚本消费）；`env.py --ffmpeg` 只打印 ffmpeg 路径。

### 0.3 Python 依赖

**装进同一个环境，然后一直用它。**

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
| `imageio-ffmpeg` | **各平台自带完整解码器的 ffmpeg** | 必需（抽帧 / ASR 都要） |
| `rapidocr-onnxruntime` | 跨平台中文 OCR（**Windows / Linux 的唯一选择**） | 非 macOS 必需 |
| `pillow` | 读图像尺寸（OCR 坐标归一化要用） | 必需 |
| `faster-whisper` | 口播 ASR | 只有需要口播转写时才装 |

**⚠️ ffmpeg 必须带完整解码器。** Playwright 自带的 `ffmpeg-mac` / `ffmpeg-win64` 是
`--disable-everything` 编出来的，**没有 h264/aac**，抽帧会直接报
`Unknown decoder 'h264'`。`imageio-ffmpeg` 自带的那份是完整的，跨平台都可用，由 `env.py` 自动解析。

### 0.4 Node 依赖（给 `dy_fetch.js` 用）

```bash
npm install playwright-core
npx playwright install chromium
```

`dy_fetch.js` 会**自动**按以下顺序找 Chromium，一般不用配：

1. 环境变量 `CHROME`
2. playwright 自己报告的路径（**会校验是否真的存在**）
3. 扫 `ms-playwright` 缓存目录，取版本号最大的 `chromium-*`
4. 系统已装的 Chrome / Edge（**Windows 上 Edge 是系统自带的，通常无需任何操作**）

同理，`playwright-core` 也会在 cwd、`NODE_PATH`、全局 npm 目录等处依次查找。

引擎选择与两套引擎的实测准确率差异见 `@references/ocr-engines.md`。

---

## Step 1 — 解析短链接拿 aweme_id

`dy_fetch.js` 内置了短链跳转解析，直接喂链接即可，无需手动 curl。

## Step 2 — 拿详情（关键：必须在浏览器里 fetch）

**直接 curl 详情接口会 403**（`Blocked by ArgusSecurityPlugin Uifid Not Found`）——
接口需要 ttwid / Uifid / `a_bogus` 签名。可行做法：用 Chromium 打开 `https://www.douyin.com/`
让站点自己写好 cookie，再在**页面上下文内**同源 fetch，此时不需要自己算签名。

```bash
node scripts/dy_fetch.js "<aweme_id 或 分享链接>" \
  [--download <out.mp4>] [--gear <档位>] [--save-json <detail.json>] [--verbose]
```

**⚠️ 两个产物形状不一样，不要混用：**

| 产物 | 内容 | 用途 |
|---|---|---|
| **stdout**（打印出来的） | **加工摘要**（字段名友好） | 给人看、给后续步骤判断用 |
| `--save-json` 写出的文件 | **抖音原始 `aweme_detail`**（几百个原始字段：`statistics` / `video.bit_rate` / `video.subtitle.subtitleInfos` …） | **L1 的输入**（`subtitle_track.py --from-detail`），它需要原始的嵌套结构 |

所以不要拿 `jq .subtitle_count detail.json` 去查 `--save-json` 的文件 —— 那个字段只在
stdout 摘要里。两个都要留就重定向一下：

```bash
node scripts/dy_fetch.js <id> --save-json detail.json > summary.json   # 原始 + 摘要各一份
```

stdout 摘要字段：

- `stats`：点赞 / 收藏 / 转发 / 评论
- `ad_aweme_source` / `is_paid_creative` / `has_link_ad`
- `duration_sec` / `resolution` / `publish_time` / `author` / `hashtags` / `music`
- `is_subtitled` / `subtitle_count` / `subtitles[]` ← **Step 4 的决策依据**
- `gears[]`：各档位（gear / 分辨率 / 码率）。默认不带 URL（URL 带签名且很长，会把摘要淹掉）；
  需要直链时加 `--verbose`

**接口**：`/aweme/v1/web/aweme/detail/?aweme_id=<id>&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1`

**每次都要存 `--save-json`** —— Step 4 L1 要用。

## Step 3 — 下载原片

`dy_fetch.js --download` 会用正确 Referer 直下**最高码率档**。
播放地址**必须带 Referer**（`https://www.douyin.com/`），否则 403。

**下载后要校验音轨**：抖音会把音视频**分轨**，个别档位下下来只有视频轨、没有音频。
`dy_fetch.js` 会自动打印 `# tracks: video=true audio=true`；缺音轨时 `--gear` 换档重下。
（没找到 ffmpeg 时会跳过校验并提示，不影响主流程。）

也可以随时单独查视频信息：

```bash
python scripts/extract_frames.py <video.mp4> --info     # 时长/分辨率/有无音轨/建议抽帧率
python scripts/extract_frames.py <video.mp4> --json     # 同上，JSON 输出便于脚本消费
```

## Step 4 — 拿逐句文案

### 4.0 先决策：要跑哪几层

**看 Step 2 输出里的 `subtitle_count` 就够了，不要盲目先跑 L1**：

| `subtitle_count` | 动作 |
|---|---|
| `> 0` | 跑 L1，大概率直接拿到零错字带时间轴的文案 |
| `== 0`（含 `is_subtitled` 为 0 / null） | **跳过 L1**，直接进 L2 + L3 |

实测：抖音**口播类**视频创作者极少上传字幕轨（4 条里 0 条命中 L1）。
先跑 L1 对本技能的主要场景几乎总是白跑一次，用 `subtitle_count` 判断可以省掉这一步。

### 4.1 L1 — 官方字幕轨（有就是最准的）

```bash
python scripts/subtitle_track.py --from-detail detail.json --timestamps -o l1.txt
```

- 有字幕轨 → 拿到**带时间轴、零错字**的逐句文案。
- 没有 → 退出码 2 + `NO_SUBTITLE_TRACK`，**这不是失败**。
- 注意：创作者**上传的字幕轨**和**画面里烧的花字**是两回事 —— 前者有才有，后者只能 OCR。
- 本脚本**不做长度截断**。

### 4.2 L2 + L3 — 主力组合，**并行跑**

没有字幕轨时，**L2 和 L3 一起跑，不要串行**（互不依赖，并行能省一半墙钟时间）。

**先把两件容易被混为一谈的事分清：**

| 问题 | 答案 | 原因 |
|---|---|---|
| 谁**便宜**？ | **L2 ASR** | 39 秒音频只要 7 秒；同一条视频 OCR 要 40 秒 |
| 谁**权威**？ | **L3 OCR** | 画面花字是创作者自己打上去的，近零错字；ASR 实测错 15 处 |

**L2 便宜 ≠ L2 可以顶替 L3。** OCR 不只是"另一份文案"，它同时还是：
中部**金句卡 / 强调卡**的唯一来源、**字幕配色层级**的唯一来源、
**画面里有但口播没念的文字**（卖点、价格、电话、UI）的唯一来源 ——
这些 ASR 一条都拿不到。**可以优化 OCR 的开销，不能把它降级成可选。**

#### L2 — 口播 ASR

```bash
python scripts/asr_transcribe.py <video.mp4> --model <模型> --timestamps -o l2.txt
```

**模型选择**：

| 视频情况 | 模型 | 理由 |
|---|---|---|
| 短视频（< 60s）、画面有花字 | `base` | **L3 会覆盖文本准确性**，ASR 只用来补时间轴和漏句 |
| 长口播（≥ 60s）、画面无花字或花字稀疏 | `small` | 此时 ASR 是主要来源，值得多花时间 |

实测耗时与下载体积见 `@references/sampling-budget.md`。

#### L3 — 抽帧 + 画面花字 OCR

```bash
# ① 抽帧（--fps auto 按「总帧数 <= 800」自动定帧率）
python scripts/extract_frames.py <video.mp4> --fps auto -o frames/

# ② OCR（自动选引擎；也可 --engine vision / --engine rapidocr 指定）
python scripts/ocr_frames.py "frames/f_*.jpg" -o ocr.json
```

**fps 怎么定、为什么不能无脑降、原分辨率抽帧的原因，见 `@references/sampling-budget.md`。**
要点：`--fps auto` = `800 / 时长` 夹到 `[2, 6]`；**短教学 / 口播类保持 6fps**；
若降帧率，必须单独给**开场前 2 秒**补一轮高密度抽帧（闪现钩子只在这个位置集中出现）。

#### 解析 ocr.json（**必用 `parse_ocr.py`，不要每次手写**）

```bash
python scripts/parse_ocr.py ocr.json --bands                          # ① 先看 y 分布
python scripts/parse_ocr.py ocr.json --subtitles --timestamps -o t.txt # ② 字幕时间轴
python scripts/parse_ocr.py ocr.json --cards                          # ③ 强调卡区间
python scripts/parse_ocr.py ocr.json --fps 4 --plain -o sub.txt       # 纯文本（便于直接读）
```

**不同引擎的 fps 要对上**：`--fps` 必须与抽帧时用的帧率一致，否则时间轴全错。

它已经把五件麻烦事做掉了：

1. **自动分带**：顶部固定标题（n ≈ 总帧数）与滚动字幕带（n 中等成片）一眼分开。
2. **同行拼接**：不同引擎切框粒度不同，RapidOCR 常把一句切成两段
   （`已经非常` + `非常值钱了`），脚本按垂直重叠并回一行再连接。
3. **模糊合并**：OCR 对同一句会给出长短不一的多个残读
   （`当你主动告诉A` / `当你主动告诉AI`），按相似度合并并**保留更完整的那个版本**。
4. **数字分句**：只差数字的两句**不会被并成一条**。
   例：`播放量低于500` 和 `播放量低于3000` 必须各自成条 —— 否则 500 / 3000 的对比就丢了。
   汉字近形误读（正/罡、赞/潜）仍照常合并，不受影响。
5. **强调卡聚类**：静态大字卡会被读成几十个变体，按时间聚类、取票数最高的读法，
   并提示「有 N 种变体，务必 Read 关键帧确认」。

默认分带：字幕带 `y < 0.45`，强调卡带 `0.38 ≤ y ≤ 0.72`。不同视频版式不同，
**先跑 `--bands` 确认，再按需用 `--sub-band` / `--card-band` 覆盖**。

### 4.3 L2 × L3 交叉校验（不是二选一，是必须交叉）

- **L1 才是"命中即止"** —— L1 命中就不用跑 L2/L3。
- **L2 和 L3 是同一层的两个信息源，永远都跑，然后交叉**：
  1. **L2 提供时间轴**（ASR 分段天然带时间戳，密度好、切句干净）。
  2. **L3 提供准确用词**（画面花字是创作者自己打上去的，零错字）。
  3. **以 L3 的文本为准，用 L2 补 L3 没 OCR 到的句子**（画面没花字的过渡句只有 ASR 有）。
  4. 报告里注明来源；两层冲突时记录**修正明细**（这条很受用户认可，不要省）。

**反例**：画面**没有**烧花字（纯口播 + 风景 / B-roll）时，L3 会返回噪声或空，
此时 L2 ASR 是唯一来源 —— 不要硬让 OCR 去"纠正" ASR。

常见误读样本（ASR 与 OCR 各一组）见 `@references/accuracy-evidence.md`。

### 4.4 L3 字幕纠错（必要时）

`parse_ocr.py` 的合并逻辑已能处理多数残读，但**描边花字 + 艺术字**仍会整句认错。

**纠错方法：用 `Read` 直接看关键帧**（开场 / 痛点段 / 产品亮相 / CTA 段 / 金句卡各一张）。
**时间轴用 OCR（密），关键字用肉眼（准）。** 具体误读样本与抽帧噪声剔除规则见
`@references/accuracy-evidence.md`。

## Step 5 — 形态检测 + 拆解维度

### 5.0 形态检测（很快，必做）

```bash
python scripts/extract_frames.py <video.mp4> --scenes        # 剪辑点检测
python scripts/parse_ocr.py ocr.json --cards                 # 强调卡检测
```

**为什么重要**：强调卡往往是全片**唯一的视觉变化**和**记忆锚点**，是拆解里最值得写的一段。
只看底部字幕带会**完全漏掉**它（强调卡出现时底部字幕是空的）。

实测的三种形态，报告里要点明属于哪种：

| 形态 | 特征 | 例子 |
|---|---|---|
| 一镜到底 | 零剪辑点，靠内容密度撑时长 | 160s 口播 + 1 处金句卡 |
| 快切带货 | 高频剪辑，2–3 秒一个信息点 | 26s 产品广告 |
| 录屏演示 | 真人 + 屏幕录制画中画，红圈标操作位 | 39s 教学 |

### 5.1 拆解维度（抖音短视频 / 广告素材）

1. **性质**：自然内容还是投流素材（看 `ad_aweme_source`、`link_ad_data`）
   - ⚠️ **投流素材的自然互动天然低，不能当内容质量判据**（实测：91.5 万粉账号的投流素材
     只有 203 赞 / 0 评论）。报告里要明确提醒，并给出该看的指标。
2. **互动结构**：用占比不用绝对值
   - `收藏÷点赞` = 工具 / 采购信号（实测正常值 0.1–0.2，0.95 属极罕见）
   - `评论÷点赞` = 讨论卷入信号
   - `转发÷点赞` = 社交传播信号（实测一条视频号 10.65，典型传播型）
   - **把多条视频的这三个比值做成横向对比表** —— 这是报告里最有信息量的一张表
3. **逐句文案时间轴**：时间 + 文案 + 对应画面，注明来源层
4. **节奏**：时长 ÷ 信息段数 = 平均切换间隔（实测 1.9–2.2 秒/段是常态）
5. **形态**：见 5.0
6. **字幕配色层级**：哪层颜色给了什么词。**核心规律：颜色是稀缺资源，只花在"必须记住的那个词"上**
7. **画面验证**：每个抽象卖点配了什么可验证画面（卷尺、手指、红圈、录屏）
8. **CTA 与人群点名**：含「零 CTA」这种情况 —— 要解释**为什么零 CTA 反而合理**
9. **可复用结构模板**：把时间轴抽象成段落骨架 + 可迁移到其他行业的要点

## Step 6 — 出报告

- **HTML**：直接以 `templates/report_template.html` 为底稿填内容，**不要每次重写 CSS**。
  模板里已含十节骨架与全部样式（浅色主题；深色主题改 `:root` 变量即可）。
- **Markdown**：同一内容出一份 md，供入知识库用（部分知识库连接器不接受 html）。

**文件命名规范**：

```
{平台}拆解_{主题}.md / {平台}拆解报告_{主题}.html
原片：{主题}_原片_{作者}.mp4
关键帧：{主题}_关键帧/
例：抖音拆解_豆包收费与意图经济.md
```

主题取「一句话能说清的那件事」，2–8 字，不要用 aweme_id。

## 批量处理（一次给多条链接）

用户丢来一批链接时，**不要逐条盲拆**。先用 `dy_fetch.js`（不带 `--download`）批量取详情，
按互动数据过滤出值得深拆的，再对入选的跑完整流程。

**入选条件**（阈值可按用户口径调）：

```
通过 = 点赞 >= min_digg  且  (评论 >= min_comment  或  转发 >= min_share)
```

- 点赞是**曝光广度**；评论 / 转发才是**真实参与度**。只有点赞高但零评论零转发的，多半是泛流量。
- **投流素材（`is_paid_creative=true`）单独标记，不要按自然量阈值一票否决** ——
  它们是**花了钱验证过**的素材。
- 过滤结果先列表给用户看（aweme_id / 文案摘要 / 互动数 / 是否投流 / 入选与否），确认后再深拆。

## 报告落地

- 本地：`outputs/` 下出 HTML + MD 两份；异常产物（原片 mp4、关键帧）留在本地 `outputs/` 即可。
- 若要把报告存进知识库（如 ima 连接器），**只存拆解报告本身的 Markdown**：
  - 报告正文里已有原视频链接，就不要再单独存一条 URL 条目；也不要额外上传关键帧总览图之类的辅助图。
  - 判据：**这条东西删掉之后，还要不要再去别处找它？不需要，就不该存。**
  - 连接器**没有删除能力**，加错条目只能让用户手动删 —— 不要"先试着加一条"。
- 知识库入库是**异步的**：刚存完进度可能只有 75%，如实告知用户"稍等片刻"，不要说"解析完成"。
- **mp4 和 html 通常无法通过知识库连接器上传**（preflight 直接拒绝），只能存 md。
- 如确需加"来源链接"，**用 PC 长链别用短链**：

| 链接形式 | 结果 |
|---|---|
| `https://v.douyin.com/xxx/` | ❌ 抓成空条目 |
| `https://www.douyin.com/video/<aweme_id>` | ✅ 正常 |

## 故障处置

按现象查 `@references/troubleshooting.md`。最常踩的三条：

- 脚本说「没有可用引擎 / 缺依赖」→ 库装到了别的解释器，用 `env.py --check` 矩阵里全 `✓` 的那行。
- 详情接口 403 `ArgusSecurityPlugin` → 正常现象，改用浏览器内同源 fetch。
- 字幕时间轴整体偏移 → `parse_ocr.py --fps` 与抽帧帧率不一致。

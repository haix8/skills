---
name: voice-polish
display_name: 声剪
display_name_en: Voice Polish
description: "口播视频自动剪辑：转写 → 大模型校对错字并标出说错重来的句子 → 静音检测剪气口和废句 → 烧录字幕 → 回转核对。当用户发来口播/讲话/vlog 视频，并说「剪气口」「去停顿」「删口误」「删重复句」「加字幕」「把这条口播剪一下」时使用。macOS（Apple 芯片）已实测；Windows 未实测。"
description_zh: 口播视频一键精剪：剪气口、删说错重来的句子、校对并烧录字幕，出片后自动回转核对。
description_en: Polish talking-head videos — cut pauses and breaths, drop flubbed retakes, proofread and burn in subtitles, then verify the cut by re-transcribing it.
category: video
version: 1.0.0
author: 大鱼来客
agent_created: true
tags: [口播, talking-head, 剪辑, video-editing, 气口, 字幕, subtitles, whisper, vad, ffmpeg]
examples_zh:
  - 把桌面上这条口播剪一下，去掉气口和说错的地方，加上字幕
  - 这个视频帮我删掉停顿和重复的句子
examples_en:
  - Cut the pauses and retakes out of this talking-head video and add subtitles
  - Clean up this vlog recording and burn in Chinese captions
---

# 声剪 Voice Polish · 口播视频自动剪辑

脚本：`<技能目录>/scripts/voice_polish.py`。`<技能目录>` 指本 SKILL.md 所在目录（Claude Code 个人安装时为 `~/.claude/skills/voice-polish`），执行前替换成绝对路径。
完整设计、依赖对照、文件说明：`references/WORKFLOW.md`（需要时再读）

## 运行约束（每一步都适用）

- 脚本要用 GPU：在 Claude Code 里调用 Bash 时**必须关闭沙箱**（`dangerouslyDisableSandbox: true`），否则自检会因"拿不到 GPU"中断。第一次调用前用一句话告诉用户：之后每次运行都会弹权限确认。
- 命令前加 `HF_HUB_OFFLINE=1`（模型已缓存时避免联网检查；自检若提示模型缺失，去掉它让脚本下载）。
- 每条视频单独建输出目录，在该目录里运行脚本（脚本把产物写到当前目录）。默认：视频所在目录下的 `<视频名>_polish/`；用户指定了就用用户的。
- 不要改脚本。脚本报错时把原文和你的判断告诉用户。

## 第 0 步：环境自检（收视频之前）

```bash
HF_HUB_OFFLINE=1 python3 "<技能目录>/scripts/voice_polish.py" --check
```

- 退出码 0：继续。
- 退出码 2：**停止流程**。把每个 ✗ 项用一句人话转述（缺什么、为什么、给出的安装命令），等用户装好再重跑自检。不要自己安装，除非用户要求。
- 只有 GPU 那一项失败、用户明确接受"慢且错字更多"时，后续所有命令加 `--allow-cpu`。

## 第 1 步：转写

```bash
cd <输出目录> && HF_HUB_OFFLINE=1 python3 "<技能目录>/scripts/voice_polish.py" <视频路径> --transcribe-only
```

产出 `<name>_raw.txt`（small 模型逐字照录，保留重复和口头禅，错字较多）。读它。

## 第 2 步：校对（你来做）

基于 `<name>_raw.txt` 写 `<name>_corrected.txt`。规则：

1. **保留原话的每一个字**，包括口头禅（呢、然后、已经）和说错重来的句子。不润色、不删字、不调语序。字数和原文差太多会导致对齐出错。
2. **只改识别错的字**。按全文上下文判断同音/近音错字；专有名词（品牌、车型、人名）尤其要查。常见例子：捞客→唠嗑、PBA→BBA、去命→祛魅、代骗→带偏、问家→问界、支架→智驾。
3. **要删的话用 `[[ ]]` 括起来**：说错重来的句子只保留最后一遍，前面几遍整体括起来；可以跨行；括号内同样只改错字不改写。
4. 标点和换行用于字幕断句，按说话停顿加。
5. 拿不准的字照写最可能的版本，记进"存疑清单"（原识别 → 你的改法 → 理由）。

写完**不用停下来等确认**，直接进第 3 步：出片只要几十秒，让用户对着成片一次性确认更省事。

## 第 3 步：出片 + 回转核对

```bash
cd <输出目录> && HF_HUB_OFFLINE=1 python3 "<技能目录>/scripts/voice_polish.py" <视频路径> --text <name>_corrected.txt --suffix _final
```

产出 `<name>_final.mp4`、`<name>_final.srt`、`<name>_final_check.txt`。读核对报告。

## 第 4 步：汇报

按这个顺序告诉用户（结论先行）：

1. 成片路径、时长变化（原 → 剪后）、删了几段废句、总耗时。
2. **需要人听的位置**：核对报告"重点"里的每一条（时间点 + 应为/听到）。对每条给出你的判断：疑似吞字 / 废句残留 / 字幕与原声不符 / 两个模型都听不准的识别误差。"低"一档只报数量，不逐条列。
3. **存疑清单**：第 2 步拿不准的用字。
4. 删掉的废句：逐条列原话。

用户要改：只改 `<name>_corrected.txt`（改字、增删 `[[ ]]`），重跑第 3 步。改完再汇报一次差异。

## 常见情况

| 现象 | 处理 |
|---|---|
| 核对报告"重点"出现"多字"，内容是前后文的重复 | 废句残留：转写漏记了某遍重复，校对稿里没有它。在校对稿对应位置补上那段话并用 `[[ ]]` 括起来，重跑第 3 步 |
| "缺字"且两个模型都报 | 疑似删句切到了保留的字。检查附近 `[[ ]]` 的边界是否多括了字 |
| 成片文件超过 30MB | 发送给手机端会失败，告诉用户只能在本机打开 |
| 没有校对稿也想先看效果 | 去掉 `--text` 直接跑第 3 步：只剪气口、字幕用转写原文、不删句 |

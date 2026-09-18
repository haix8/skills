# OCR 引擎选择与实测对比

## 引擎矩阵

| 平台 | 引擎 | 说明 |
|---|---|---|
| macOS | Vision（优先）+ RapidOCR（兜底） | Vision 需 `xcode-select --install` 拿到 `swiftc` |
| Windows / Linux | **RapidOCR** | pip 装，无需任何系统组件 |

`ocr_frames.py --engine auto` 按上表自动选；也可显式指定 `--engine vision` / `--engine rapidocr`。

## 实测结论：RapidOCR 比 macOS Vision 更准、召回更全

同一条 39 秒教学视频、同一批 234 帧，对底部字幕带逐帧比对：
**完全一致 99 帧 / 有差异 111 帧，差异里绝大多数是 RapidOCR 对。**

| 正确原文 | Vision | RapidOCR |
|---|---|---|
| 都不**正**常 | 都不**罡**常 ✗ | 都不**正**常 ✓ |
| 第一步右上角三**道**杠 | 第一步右上角三**旦**道杠 ✗ / 三**道和** ✗ | 第一步右上角三**道**杠 ✓ |
| 而是一**个**明确的 | 而是一**企**明确的 ✗ | 而是**一个**明确的 ✓ |
| **豆包**开始收费以后 | **原包**开始收费以后 ✗ | **豆包**开始收费以后 ✓ |
| 播放量低于500 / 正常吗（两行） | 只读到「正常吗」（**漏一行**）✗ | 两行都读到 ✓ |

误读集中在**描边花字与近似字形**（正/罡、三/旦、个/企、豆/原）。

**结论：Windows / Linux 用户不是"降级"，反而拿到更准的结果；macOS 上也可显式用
`--engine rapidocr` 换掉 Vision。**

## macOS Vision 需要编译一次

`ocr_frames.py` 会自动编译（约 4 秒），手动编译：

```bash
# 仅 macOS
swiftc -O -framework Vision -framework AppKit scripts/subtitle_ocr.swift -o scripts/subtitle_ocr
```

编译产物是 macOS 专属二进制，删掉无妨，下次运行会自动重建。或者干脆用 RapidOCR。

## 坐标约定

`ocr_frames.py` 统一输出的 `lines[].y` 是**归一化纵坐标，原点在左下**（y 越大越靠上）。
RapidOCR 原生是左上原点像素坐标，脚本内部已换算成同一约定 ——
不同引擎的坐标不可直接混用，一律以 `ocr.json` 里的 `y` 为准。

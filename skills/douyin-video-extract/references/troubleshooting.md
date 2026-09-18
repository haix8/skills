# 故障处置

按「现象」查表。第一条最重要：绝大多数"缺依赖"其实是装到了别的解释器。

| 现象 | 原因 / 处置 |
|---|---|
| `env.py --check` 报缺 ffmpeg | `pip install imageio-ffmpeg`（跨平台，最省事） |
| 明明装了库，脚本却说「没有可用引擎 / 缺依赖」 | **装到了别的解释器**。看 `env.py --check` 的依赖矩阵，改用全 `✓` 那行的 python（`PY=$(python env.py --which)`） |
| 依赖矩阵里推荐的行仍缺必需项 | 按提示装：`"$PY" -m pip install <缺的包>` |
| ffmpeg 报 `Unknown decoder 'h264'` | 用到了 Playwright 自带那份（无完整解码器）；换成 imageio-ffmpeg 的 |
| 抽帧出来的图是黑屏 / 花屏 | 同上：ffmpeg 缺解码器 |
| 详情接口 403 `ArgusSecurityPlugin` | 正常，改用浏览器内同源 fetch |
| 播放地址 403 / 返回错误页 | 少了 `Referer: https://www.douyin.com/` |
| 找不到 playwright-core | `npm install playwright-core`；或运行前设 `NODE_PATH` 指到 node_modules |
| 找不到 Chromium | `npx playwright install chromium`；Windows 上一般用系统自带 Edge 即可 |
| 页面显示「视频数据加载中」/ 空 | 没等够时间，加 `waitForTimeout(6000)` 让 cookie 落盘 |
| m.douyin.com 显示「请尝试在抖音内观看」 | 正常，移动端分享页要求 App；走 PC 站 + 接口路径 |
| `is_subtitled` 为 `null` 或 `0` | 都表示没有字幕轨，走 L2 + L3 |
| L1 退出码 2 `NO_SUBTITLE_TRACK` | 创作者没上字幕轨，正常，不是失败 |
| L2 退出码 2 `NO_AUDIO_TRACK` | 下载的档位是纯视频轨，`--gear` 换档重下 |
| L2 退出码 3 未安装 faster-whisper | `pip install faster-whisper` |
| OCR 报缺引擎（非 macOS） | `pip install rapidocr-onnxruntime` |
| macOS 上 `swiftc` 不可用 | `xcode-select --install`；或直接用 `--engine rapidocr` |
| 字幕时间轴整体偏移 / 错乱 | `parse_ocr.py --fps` 与抽帧帧率不一致，对不上 |
| `parse_ocr.py --cards` 输出乱码变体 | 静态大字卡 OCR 本来就差；按提示 **Read 关键帧**确认 |

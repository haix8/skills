# 附录：在 WSL 中以系统服务方式常驻运行

> **本附录为可选项。** 绝大多数用户直接用 SKILL.md 主流程（Windows / macOS / Linux 本机运行）即可，不需要看这一页。
> 仅当你希望浏览器在 WSL 环境内常驻、随会话自动启动时，才参考本节。

## 适用场景

- 你的工作环境主要在 WSL 内，希望 CDP 服务随 WSL 启动自动就绪
- 需要长时间挂机运行定时采集任务

## 前提条件

- WSL 已启用 systemd（`/etc/wsl.conf` 中含 `[boot]` 段的 `systemd=true`，修改后需 `wsl --shutdown` 重启）
- WSL 内已安装 Chromium 系浏览器（`which google-chrome` 或 `which chromium` 有输出）
- 需要看到浏览器窗口时，还需 WSLg 或 X server；无头模式则不需要

## 服务配置

创建 `~/.config/systemd/user/chrome-cdp.service`：

```ini
[Unit]
Description=Chrome with remote debugging port (CDP)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/google-chrome --remote-debugging-port=9222 --no-first-run --new-window --user-data-dir=%h/.cdp-browser/profile about:blank
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

说明：

- `%h` 是 systemd 的家目录占位符，会自动替换为你的用户目录，**不要手写绝对路径**。
- 浏览器路径以 `which google-chrome` 的实际输出为准，若是 Chromium 则改为对应路径。
- 需要登录态时用持久目录（`%h/.cdp-browser/profile`）；不需要登录态时改为临时目录（如 `/tmp/cdp-browser`，重启即清空）。
- 无头模式：在 `ExecStart` 末尾加 `--headless=new`，并去掉窗口相关参数。

## 常用命令

```bash
# 首次启用
systemctl --user daemon-reload
systemctl --user enable chrome-cdp.service
systemctl --user start chrome-cdp.service

# 日常控制
systemctl --user status chrome-cdp.service
systemctl --user stop chrome-cdp.service
systemctl --user restart chrome-cdp.service

# 验证（应返回含 Browser 与 webSocketDebuggerUrl 的 JSON）
curl -s http://localhost:9222/json/version
```

服务起来后，SKILL.md 中的 Step 3、Step 4 命令**照常使用**，脚本会自动连上这个端口。

## 注意事项

| 事项 | 说明 |
|------|------|
| 重复实例 | 若已有一个使用同一配置目录的浏览器在跑，新进程会把网址丢给已有窗口后立刻退出，服务随即变成 `inactive (dead)`。启动服务前先确认没有同名配置目录的浏览器在运行 |
| 安全结束进程 | 不要用 `pkill -f chrome`，容易误伤。先 `systemctl --user stop chrome-cdp.service`，仍不行再按命令行精确匹配端口后结束 |
| 端口冲突 | 9222 被占用时换端口，服务文件与后续脚本命令要一起改 |
| 代理 | 大多数环境不需要。仅在确认必须经由代理访问时才加 `--proxy-server=<代理地址>`；代理未运行时所有页面会报 `ERR_PROXY_CONNECTION_FAILED`，届时去掉该参数重启服务即可 |
| 资源占用 | 一个空白页的浏览器约占 150~200 MB 内存，属正常 |

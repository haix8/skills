> **内嵌版路径说明**：本文原为独立技能 `browser-automation-cdp` 的操作手册，
> 在本技能中已被内嵌到 **`scripts/browser/`**。
> 因此文中出现的 `<SKILL_DIR>/scripts/xxx.py`（如 `cdp.py`、`start_chrome.py`）
> 一律对应 **`scripts/browser/xxx.py`**，命令参数与用法完全不变。
> 该部分版权归原作者 **W2Q**，**MIT 许可**。

---
name: browser-automation-cdp
description: "浏览器自动化与网页抓取（Browser Automation / Web Scraping）— 用 Chrome DevTools Protocol 驱动本机真实 Chrome 或 Edge 浏览器，完成网页打开、点击、填表、截图、数据采集与定时监控。相比无头爬虫更不容易被识别为机器人，适合需要登录态、存在反爬机制、遇验证码或依赖 JavaScript 动态渲染的页面。当用户需要浏览器自动化、网页自动化、网页抓取、爬虫爬取、数据采集、网页截图、自动填表、表单提交、网页监控、价格监控比价、绕过反爬，或发现直接抓取被拦截时，应使用本技能。"
display_name: "浏览器自动化 · 网页抓取与数据采集"
display_name_en: "Browser Automation · Web Scraping & Data Extraction"
description_zh: "用 Chrome DevTools Protocol 驱动本机真实 Chrome 或 Edge 浏览器，做浏览器自动化与网页数据采集。全程脚本化、零第三方依赖，装好 Python 即可运行。覆盖场景：网页抓取与爬虫（直接抓取被拦、需要先登录、前端动态渲染）、数据采集与网页采集、自动填表与表单提交、自动点击与页面操作、网页截图与整页截图、网页监控与价格监控比价、竞品与商品信息追踪、批量查询与信息核对。相比无头爬虫，真实浏览器带完整指纹，更不容易被识别为机器人，可绕过常见反爬与验证码。能力包括：自动探测或引导安装 Chrome（官方手动下载、自动安装，或用系统自带 Edge 免安装）、以调试模式启动、持久登录态管理、登录过期自动检测与告警、按日期落盘 JSON 与 CSV、环境一键体检。配合定时任务可实现每日自动采集。"
description_en: "Drive your real local Chrome or Edge browser through the CDP for browser automation and web scraping. Fully scripted with zero third-party dependencies, Python alone is enough. Covers web scraping and crawling blocked by anti-bot systems, pages behind a login, and JavaScript-rendered content; data extraction; auto form filling and submission; auto clicking; page and full-page screenshots; web monitoring; price tracking and comparison; competitor monitoring and bulk lookups. Because it drives a real browser with a genuine fingerprint, it is far less likely to be flagged as a bot than a headless scraper, and it gets past most anti-bot walls and captchas. Features: auto-detect or guide Chrome installation; debug-mode launch; persistent login sessions; automatic login-expiry detection and alerts; JSON and CSV output organized by date; one-command environment health check. Pair with scheduled automation for daily collection."
agent_created: true
version: 1.1.1
license: MIT
author: "W2Q"
tags: [browser-automation, web-automation, web-scraping, data-extraction, crawler, crawling, cdp, chrome, chromium, edge, headless-browser, screenshot, form-filling, auto-click, rpa, anti-bot, captcha, login-session, price-monitoring, web-monitoring, price-tracking, javascript-rendering, 浏览器自动化, 网页自动化, 网页抓取, 网页采集, 数据采集, 爬虫, 爬取, 反爬, 验证码, 登录态, 网页截图, 自动填表, 自动点击, 网页监控, 价格监控, 比价, 竞品监控, 无头浏览器, 自动化脚本]
---

# 浏览器自动化 · 网页抓取与数据采集（CDP 真实浏览器）

> **适合场景**：网页抓取 / 爬虫被拦截 · 需要登录才能看到的数据 · 反爬与验证码 · 前端动态渲染页面 · 自动填表与表单提交 · 网页截图 · 网页监控与价格比价 · 批量信息核对

**执行手册**：严格按 Step 0 → Step 6 顺序执行，不跳步、不自由发挥。每步都有精确命令和固定产出。

> **路径约定**：下文 `<SKILL_DIR>` 指本 SKILL.md 所在目录，使用时替换为实际路径。
> **Python 命令**：Windows 一般用 `python`（也可用 `py -3`），macOS/Linux 一般用 `python3`；提示「命令未找到」时换另一个再试。

## 0. 流程概览

| 步骤 | 动作 | 何时需要 | 产出 |
|------|------|---------|------|
| Step 0 | 准备浏览器 | 首次使用，或提示找不到浏览器时 | 浏览器可执行文件路径 |
| Step 1 | 启动调试浏览器 | 每次开始自动化前 | CDP 端口就绪 |
| Step 2 | 环境体检 | 出现异常时；平时可跳过 | 体检报告 |
| Step 3 | 操作浏览器 | 打开/点击/填表/截图 | 页面按预期响应 |
| Step 4 | 采集数据 | 需要把页面内容存下来时 | JSON + CSV |
| Step 5 | 关闭浏览器 | 全部任务完成后 | 浏览器退出 |
| Step 6 | 排障 | 任何一步报错时 | 见负向规则表与故障速查表 |

---

## Step 0：准备浏览器

先探测本机是否已有可用浏览器：

```bash
python <SKILL_DIR>/scripts/setup_chrome.py
```

- 输出 `READY` → 已记录浏览器路径，**直接进入 Step 1**。
- 输出 `NOT_FOUND` → 按下面 A/B/C 任选其一获取浏览器。

| 途径 | 操作 | 说明 |
|------|------|------|
| **A. 手动下载（最稳妥）** | 访问浏览器官方下载页下载安装，装完重新运行上面的探测命令 | 官方渠道，任何系统都适用 |
| **B. 自动安装** | `python <SKILL_DIR>/scripts/setup_chrome.py --install` | 自动调用系统包管理器；失败则下载官方离线安装包。可能需要管理员权限 |
| **C. 用系统自带 Edge（免安装）** | `python <SKILL_DIR>/scripts/setup_chrome.py --use-edge` | Windows 自带 Edge，同为 Chromium 内核，完整支持本技能全部功能 |

> 自动安装脚本只使用浏览器官方分发地址与系统自带包管理器，不涉及任何第三方渠道。
> 若已装浏览器但没被识别到，用 `python <SKILL_DIR>/scripts/setup_chrome.py --path "<可执行文件路径>"` 手动指定。

---

## Step 1：启动调试浏览器

**先决定用哪种配置目录**（--user-data-dir），这决定了登录态是否保留：

| 场景 | 命令 | 登录态 |
|------|------|--------|
| 需要登录的站点、后台看板、反复采集 | `python <SKILL_DIR>/scripts/start_chrome.py` | 保留，下次免登录 |
| 一次性抓取、公开页面 | `python <SKILL_DIR>/scripts/start_chrome.py --temp` | 关闭即清空 |
| 不需要看到窗口 | 上面任一命令加 `--headless` | 同上 |
| 端口 9222 被占用 | 上面任一命令加 `--port 9333`（之后所有命令都要带同样的 `--port`） | 同上 |

输出 `READY` 即就绪；输出 `ALREADY_RUNNING` 说明已在运行，**直接复用，不要重复启动**。

> 本技能使用独立的配置目录，与你日常使用的浏览器完全隔离：不会串用账号，也不会互相干扰。

### 可选：经由 HTTP 代理访问

**大多数用户不需要这一步。** 仅当你确认目标站点必须经由代理才能访问时才配置。

```bash
python <SKILL_DIR>/scripts/start_chrome.py --proxy <代理地址>
```

注意：

- 浏览器不会读取 `http_proxy` 环境变量，必须显式传参才生效。
- **代理服务未运行时，所有页面都会报 `ERR_PROXY_CONNECTION_FAILED`。** 此时去掉 `--proxy` 重启即可恢复。因此不要长期把这个参数固定写死。
- 本机 CDP 连接走本地回环地址，不受代理影响，无需额外配置。
- 代理地址请从你所在网络的既有网络配置或网络管理员处获取。**本技能不提供、也不推荐任何代理服务。请遵守当地法律法规与所在网络的管理规定。**

---

### 受限环境启动（沙箱不可用）

当 `start_chrome.py` 打印 `READY` 但随后 `status` 连不上，且浏览器日志里出现
`sandbox initialization failed: Operation not permitted`、紧跟着
`FATAL: GPU process isn't usable. Goodbye.` 时，说明当前环境不允许 Chrome 启用自身沙箱。

此时**不要用 `start_chrome.py`**，改为手工启动，两个条件缺一不可：

1. 追加 `--no-sandbox --disable-gpu --disable-dev-shm-usage`；
2. 让浏览器进程**常驻后台**运行——用一次性的前台命令启动，命令一返回进程就会被回收。

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 "--remote-allow-origins=*" \
  --user-data-dir="$HOME/.cdp-browser/profile" \
  --no-first-run --no-default-browser-check \
  --no-sandbox --disable-gpu --disable-dev-shm-usage about:blank
```

- Windows 把可执行文件换成 `chrome.exe` / `msedge.exe` 的完整路径。
- `--remote-allow-origins=*` 里的 `*` 在 zsh 下会被当通配符展开，**必须加引号**，否则报 `no matches found`。
- 启动后**必须再跑一次 `cdp.py status` 确认 `CDP_OK`**：脚本自己打印的 `READY` 不可信，它只代表启动瞬间探测到过端口。

其余子命令（`open` / `eval` / `text` / `shot`）用法完全不变。

---

## Step 2：环境体检（出现异常时执行）
```bash
python <SKILL_DIR>/scripts/doctor.py
```

逐项报告浏览器路径、端口、CDP 连通性、登录态目录，并在末尾给出编号的修复建议。**按编号顺序处理，处理完重新体检。**

---

## Step 3：操作浏览器

命令速查表（`<CDP>` = `python <SKILL_DIR>/scripts/cdp.py`）：

| 目的 | 命令 |
|------|------|
| 检查是否就绪 | `<CDP> status` |
| 列出标签页 | `<CDP> tabs` |
| 打开网址 | `<CDP> open "https://example.com"` |
| 取页面标题 | `<CDP> title` |
| 取页面 URL | `<CDP> url` |
| 取页面文本 | `<CDP> text --max 3000` |
| 执行 JS | `<CDP> eval "document.title"` |
| 执行 JS 文件 | `<CDP> eval --file my.js` |
| 点击元素 | `<CDP> click "button.submit"` |
| 填入文本 | `<CDP> type "input[name=q]" "搜索词"` |
| 等待条件成立 | `<CDP> wait "document.querySelector('.done')"` |
| 截图 | `<CDP> shot out.png`（整页加 `--full`） |

**铁律（每次操作必守）：**

1. **`loaded: true` 不代表拿到了目标内容。** 它只表示页面加载完成；导航失败时浏览器会停在错误页，此时输出里 `isErrorPage` 为 `true`。**每次 `open` 后必须用 `text` 或 `title` 确认内容确实是你要的。**
2. **写选择器前必先看真实 DOM。** 绝不凭记忆或文档里的 class 名写选择器：先 `open`，再 `text --max 3000`，看清当前真实结构再动手。
3. **优先用文本和语义匹配，不要依赖 CSS class。** 反爬站点会频繁改名 class 来破坏自动化脚本。
4. **复杂 JS 一律写成文件用 `--file` 传入**，避免命令行转义把引号和中文弄坏。

---

## Step 4：采集数据

适合需要登录、有反爬、或内容由前端动态渲染的页面。

**首次使用需登录站点时（只需做一次）：**

1. `python <SKILL_DIR>/scripts/start_chrome.py`（务必用持久配置）
2. 在弹出的浏览器窗口里手动登录目标站点
3. `python <SKILL_DIR>/scripts/stop_chrome.py` 关闭，再重新启动一次
4. 验证登录态是否仍在：`python <SKILL_DIR>/scripts/cdp.py open "<需登录的网址>"` 后用 `text` 确认看到的是内容页而非登录页
5. 确认成功后，才交给自动化

**正式采集：**

```bash
python <SKILL_DIR>/scripts/scrape.py \
  --url "<目标网址>" \
  --extract "<抽取脚本.js>" \
  --out "<数据输出目录>" \
  --name "<任务名>"
```

抽取脚本照抄 `<SKILL_DIR>/templates/extract.example.js`，**只改文件顶部的 CONFIG 四处**（分隔关键词、目标行正则、回溯行数、噪音词）。

产出结构：

```
<数据输出目录>/<任务名>/<日期>/data-<时间>.json      机读，供下游处理
<数据输出目录>/<任务名>/<日期>/data-<时间>.csv       人读，便于纵向对比
<数据输出目录>/<任务名>/login-expiry.log            登录过期告警
```

退出码含义：`0` 成功；`1` 执行失败；`2` 登录态失效（**本轮不落盘，需人工重新登录一次**）；`3` CDP 不可达。

要点：

- 脚本内置登录态检测：一旦页面跳回登录页，本轮跳过并记录告警，**不会把登录页当成有效数据存下来**。
- 长期定时采集时，会话通常隔一段时间会过期，属正常现象。发现 `login-expiry.log` 有新记录，手动登录一次即可恢复。
- 需要定时执行时，配合本平台的定时任务能力，按上述命令设置即可。

---

## Step 5：关闭浏览器

```bash
python <SKILL_DIR>/scripts/stop_chrome.py
```

如换了端口：加 `--port 9333`。持久配置中的登录态会保留，下次启动无需重新登录。

---

## 6. 负向规则表（禁止做的事）

| 禁止 | 后果 | 正确做法 |
|------|------|---------|
| 凭记忆写 CSS class 选择器 | 反爬站点改名后脚本静默失效 | 先 `text` 看真实 DOM，优先按文本匹配 |
| 看到 `loaded: true` 就认为成功 | 错误页也会返回 true | 检查 `isErrorPage`，并用 `text` 确认内容 |
| 登录态失效时继续硬跑 | 把登录页当数据存下来 | 检测到即跳过并告警，人工登录后再跑 |
| 复杂 JS 用命令行直接传 | 引号与中文被转义破坏 | 写成文件，用 `eval --file` |
| 把 `--proxy` 长期固定写死 | 代理未运行时全部页面打不开 | 仅在确需时临时加，用完去掉 |
| 直接杀所有浏览器进程 | 可能误关用户正在用的浏览器 | 用 `stop_chrome.py`，它只结束带调试端口的进程 |
| 未确认登录态就上定时任务 | 半夜失效无人处理，产出脏数据 | 先手动验证一次再上定时 |

---

## 7. 故障速查表

| 现象 | 原因 | 处理 |
|------|------|------|
| `CDP_UNREACHABLE` | 浏览器未以调试模式启动 | `start_chrome.py` |
| 启动后 CDP 一直不就绪 | 端口被占用，或残留进程占用了同一配置目录 | 换 `--port`；或先 `stop_chrome.py` 再启动 |
| `start_chrome.py` 明明打印 `READY`，紧接着 `status` 却报 `CDP_UNREACHABLE` | 受限 / 容器化环境下的两个叠加原因：①浏览器进程随启动命令一起被回收；②Chrome 自身沙箱初始化失败（`sandbox initialization failed: Operation not permitted`），GPU 进程随即 `FATAL: GPU process isn't usable. Goodbye.` 导致主进程退出 | 见下方「受限环境启动（沙箱不可用）」 |
| 页面报 `ERR_PROXY_CONNECTION_FAILED` | 加了 `--proxy` 但代理服务没运行 | 去掉 `--proxy` 重启 |
| `NOT_FOUND: <选择器>` | 选择器在当前 DOM 上不存在 | `text --max 3000` 核对真实结构 |
| 页面一直是空的 | 内容由前端异步渲染，尚未加载完 | 用 `wait "<条件>"` 等待后再取 |
| 提示登录态失效 | 会话过期 | 按 Step 4 手动登录一次 |
| 抽取结果为空 | 关键词或正则与当前页面不匹配 | 用 `text` 看实际文本，改 CONFIG |
| 提示端口被占用但不是 CDP | 其它程序占用了该端口 | 换一个 `--port` |

---

## 8. 参考资料（按需读取）

| 文件 | 内容 |
|------|------|
| `@references/cdp-authenticated-scraping.md` | **采集方法论**：需登录 / 反爬站点的通用打法，含抽取抗脆弱原则、登录态运维闭环、自写客户端的三个必改 bug |
| `@references/cdp-content-extraction.md` | **抽取片段库**：文档站导航树、搜索结果、表格等常见结构的现成 JS |
| `@references/wsl-appendix.md` | **WSL 附录**：在 WSL 中以系统服务方式常驻运行的可选方案 |

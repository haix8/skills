---
name: douyin-keyword-harvest
display_name: 抖音关键词批量采集
display_name_en: Douyin Keyword Harvest
description: "按关键词批量采集抖音短视频的文案与互动数据（点赞/评论/收藏/分享/发布时间/作者/链接），并按发布时间与互动量筛选排序。用于找投放对标素材、竞品文案参考、短视频选题库搭建。当用户说「找抖音文案」「抖音素材采集」「按关键词找短视频」「短视频对标素材」「抖音爆款文案」时使用。"
description_zh: 按关键词批量采集抖音短视频文案与互动数据，按发布时间与点赞量筛选排序。
description_en: Harvest Douyin short-video captions and engagement metrics by keyword, then filter and rank by recency and likes.
category: writing
version: 1.0.0
author: 大鱼来客
agent_created: true
tags: [douyin, 抖音, short-video, 短视频, 文案, copywriting, content-research, 素材采集, keyword-harvest, engagement-metrics, 投放素材]
---

# 抖音关键词批量采集

按关键词批量采集抖音短视频的**文案 + 互动数据**，按「发布时间 + 点赞量」筛出高互动素材，
用于投放对标、竞品参考、选题库搭建。

## 依赖与前置

1. **浏览器通道已内嵌，开箱即用，不需要额外装任何技能。**
   驱动浏览器所需的脚本全部内嵌在本技能的 `scripts/browser/` 下，
   浏览器的启动、登录态、排障手册见 `@references/browser-automation-cdp.md`。

   ```
   scripts/
   ├── _env.py              前置检查（定位浏览器通道 + 探活）
   ├── collect.js           搜索页卡片解析
   ├── probe_video.js       详情页解析
   ├── harvest.py / rank.py / detail.py
   └── browser/             ← 内嵌的浏览器通道
       ├── cdp.py / start_chrome.py / stop_chrome.py
       ├── setup_chrome.py / doctor.py / scrape.py
       └── refs/
   ```

   - 想改用市场版 `browser-automation-cdp`（比如那份更新更及时），
     加 `--cdp-skill <技能目录>` 指过去即可。
   - 默认查找顺序：**内嵌 `scripts/browser/`** → `~/.workbuddy/skills/browser-automation-cdp/`。
   - 找不到浏览器通道 → 退出码 2；找到了但浏览器没启动 → 退出码 3。两种情况都会打印怎么修。
2. **登录**：抖音网页版搜索必须登录，未登录只会看到扫码弹窗。让用户在浏览器窗口扫码一次即可，
   登录态存在持久配置目录里，之后免登录。
3. **受限环境**：若环境不允许 Chrome 启用自身沙箱，`start_chrome.py` 会打印 `READY` 但进程随即退出
   （日志含 `sandbox initialization failed: Operation not permitted`）。此时按
   `@references/browser-automation-cdp.md` 的「受限环境启动（沙箱不可用）」一节，
   用 `--no-sandbox --disable-gpu` 且**常驻后台**手工启动，并复核 `cdp.py status` 到 `CDP_OK`。
4. 只有 Python 标准库，不需要装任何包。

## 风控（先读这条，比命令本身重要）

抖音搜索会弹人机验证（拖拽图片）。

- **验证码必须由用户在浏览器窗口里手动完成。** 不要尝试绕过、不要写自动拖拽、不要试图点掉它。
- **抓到 0 条 ≈ 已被验证拦截。** 立刻停下来请用户过验证，然后只补跑没抓到的关键词 ——
  `harvest.py` 会复用 `all_items.json`，不会重复劳动。
- 默认节奏已经是压低过的：每轮翻页间隔 4.5~6.5 秒、关键词之间停 9~14 秒、**单次不超过 5 个关键词**。
  想跑得更快只会换来验证码，净亏时间。

## 三步流程

### 第 1 步：批量采集搜索结果卡片

```bash
python scripts/harvest.py --out <输出目录> --keywords "装修避坑,装修后悔,建材避坑"
```

可选参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--rounds` | 6 | 每个关键词向下翻页轮数，约每轮多 10 条 |
| `--port` | 9222 | 浏览器调试端口 |
| `--cdp-skill` | 内嵌副本 | 改用指定的浏览器通道目录（默认用 `scripts/browser/`） |
| `--pause-min/max` | 4.5 / 6.5 | 翻页间隔（秒） |
| `--gap-min/max` | 9 / 14 | 关键词之间停顿（秒） |

产出 `<输出目录>/all_items.json` 与 `all_items.csv`。字段：

| 字段 | 含义 |
|---|---|
| `likes` | 点赞数（`2.6万` 这种原样保留） |
| `date` | **相对**发布时间（`2月前` / `3天前`） |
| `dur` | 视频时长 |
| `author` | 作者（含 `@`） |
| `desc` | 文案正文 + 话题标签 |
| `href` | 视频链接 |
| `kw` | 来自哪个关键词 |
| `coll` | 是否为合集 |

> 搜索页是无限滚动懒加载，`collect.js` 每轮「滚一屏 + 解析当前 DOM」。
> 若某天页面明明有结果却抓到 0 条，多半是卡片行序变了 —— 改 `collect.js` 顶部那三个正则
> （`DUR` 时长 / `LIKE` 点赞 / `DATE` 时间）。

### 第 2 步：按时间和互动量筛选

```bash
python scripts/rank.py --dir <输出目录> --days 92
```

- `--days` 时间范围，默认 92（约 3 个月）。
- 时间是**相对时间换算的估计值**（`月` 按 30 天）。要精确发布时间走第 3 步。
- 产出 `ranked.json`，按点赞降序，并在终端打印榜单。

### 第 3 步：给选定的少量视频补精确数据

```bash
python scripts/detail.py --dir <输出目录> --urls "https://www.douyin.com/video/xxx,https://www.douyin.com/video/yyy"
```

产出 `details.json`：

| 字段 | 含义 |
|---|---|
| `digg` / `comment` / `collect` / `share` | 点赞 / 评论 / 收藏 / 分享 |
| `publish` | **精确发布时间**，形如 `发布时间：2026-06-30 18:07` |
| `user` | 作者 + 粉丝数 + 获赞数 |
| `tags` | 话题标签数组 |
| `info` | 详情页整块文案信息 |

字段取自 `data-e2e` 属性（比 CSS class 稳定）。若某字段取空，先看当前真实节点名：

```bash
python scripts/cdp.py eval "JSON.stringify([...document.querySelectorAll('[data-e2e]')].map(e=>e.getAttribute('data-e2e')))"
```

再改 `detail.py` 里的 `FIELDS` 映射。

## 结果怎么用

- `desc` 本身（文案 + 话题标签）就是一条可对标的**标题文案**。
- 需要**逐字口播稿**得另配 ASR，不在本技能范围；单条视频的深度拆解见 `douyin-video-extract` 技能。
- 判断素材类型：**收藏 > 点赞** → 工具型内容（清单/攻略），适合长效投放；
  **评论或分享占比高** → 情绪型内容，适合跑量拉新。这是分层复用素材的判据。
- 同题材高互动选题做成「第N集」，一个模板可反复用。

## 排障

| 现象 | 原因 | 处置 |
|---|---|---|
| 退出码 2：找不到浏览器通道 `cdp.py` | 技能包解压不完整 | 确认 `scripts/browser/cdp.py` 存在；或 `--cdp-skill <技能目录>` 指向市场版 |
| 退出码 3：调试浏览器不可达 | 浏览器没启动 | 跑 `scripts/browser/start_chrome.py`，再 `cdp.py status` 复核到 `CDP_OK`；受限环境见 `@references/browser-automation-cdp.md` |
| 某个关键词抓到 0 条 | 人机验证拦截 | 请用户过验证，再只补跑该关键词 |
| 全部抓到 0 条，页面空白 | 未登录 | 请用户扫码登录 |
| 抓到条目但字段错乱 | 卡片行序变了 | 改 `collect.js` 的三个正则 |
| 详情页某指标为空 | `data-e2e` 节点改名 | 先列节点名，再改 `detail.py` 的 `FIELDS` |

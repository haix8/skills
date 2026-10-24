---
name: douyin-keyword-harvest
display_name: 抖音关键词批量采集-大鱼
display_name_en: Douyin Keyword Harvest
description: "按关键词批量采集抖音短视频的文案与互动数据（点赞/评论/收藏/分享/发布时间/作者/链接），并按发布时间与互动量筛选排序。用于找投放对标素材、竞品文案参考、短视频选题库搭建。当用户说「找抖音文案」「抖音素材采集」「按关键词找短视频」「短视频对标素材」「抖音爆款文案」时使用。"
description_zh: 按关键词批量采集抖音短视频文案与互动数据，按发布时间与点赞量筛选排序。
description_en: Harvest Douyin short-video captions and engagement metrics by keyword, then filter and rank by recency and likes.
category: writing
version: 1.0.2
author: 大鱼来客
agent_created: true
tags: [douyin, 抖音, short-video, 短视频, 文案, copywriting, content-research, 素材采集, keyword-harvest, engagement-metrics, 投放素材]
examples_zh:
  - 帮我按「装修避坑」采集抖音短视频文案，只要近 3 个月的
  - 找一批高互动的探店短视频文案，用来做投放对标
  - 把「修车被坑」相关的高赞视频抓下来，按点赞排序
examples_en:
  - Harvest Douyin captions for renovation pitfalls from the last 3 months
  - Find high-engagement restaurant review videos to benchmark my ads
  - Pull top-liked Douyin videos about car repair scams
---

# 抖音关键词批量采集

按关键词批量采集抖音短视频的**文案 + 互动数据**，按「发布时间 + 点赞量」筛出高互动素材，
用于投放对标、竞品参考、选题库搭建。

## 依赖与前置

1. **浏览器通道已内嵌，不需要额外安装技能。**
   驱动浏览器的脚本位于本技能的 `scripts/` 下，
   启动、登录态与排障手册见 `@references/browser-automation-cdp.md`。
   脚本可运行不等于浏览器已就绪：开始前需探活，结束后需关闭，
   按下面的「浏览器生命周期」执行。

   ```
   scripts/
   ├── _env.py              前置检查（定位浏览器通道 + 探活）
   ├── harvest.py           第 1 步：批量采集搜索卡片
   ├── rank.py              第 2 步：按时间与互动量筛选
   ├── detail.py            第 3 步：补精确发布时间与互动数据
   ├── collect.js           搜索页卡片解析
   ├── probe_video.js       详情页解析
   ├── cdp.py               浏览器通道：状态 / 打开 / 执行 JS / 截图
   ├── start_chrome.py      浏览器通道：启动调试浏览器
   ├── stop_chrome.py       浏览器通道：关闭调试浏览器
   ├── setup_chrome.py      浏览器通道：探测与安装浏览器
   ├── doctor.py            浏览器通道：环境体检
   ├── scrape.py            浏览器通道：通用抓取
   ├── extract.example.js   抽取脚本示例
   ├── demo.py              无浏览器环境下的流程演示
   └── demo_data.json       演示用内置样本
   ```

   - 改用市场版 `browser-automation-cdp` 时，加 `--cdp-skill <技能目录>` 指过去。
   - 默认查找顺序：**内嵌 `scripts/`** → `~/.workbuddy/skills/browser-automation-cdp/`。
   - 找不到浏览器通道返回退出码 2；找到了但浏览器未启动返回退出码 3。两种情况都会打印处置方法。
2. **登录**：抖音网页版搜索需登录，未登录只显示扫码弹窗。由用户在浏览器窗口扫码一次，
   登录态保存在持久配置目录中，后续无需重复登录。
3. **受限环境**：环境不允许 Chrome 启用自身沙箱时，`start_chrome.py` 会打印 `READY` 但进程随即退出，
   日志含 `sandbox initialization failed: Operation not permitted`。
   处置见「浏览器生命周期」的启动一节。
4. 仅依赖 Python 标准库，无需安装第三方包。

## 环境要求与验证

本技能驱动**本机真实浏览器**，运行前提如下：

| 条件 | 说明 |
|---|---|
| 浏览器 | 已安装 Chrome 或 Edge，用 `python scripts/setup_chrome.py` 探测或安装 |
| 网络 | 可访问 `douyin.com` |
| 登录态 | 抖音网页版搜索需登录，首次使用由用户在浏览器窗口扫码一次 |
| 无沙箱环境 | 需在启动命令追加参数，见「浏览器生命周期」 |

**在没有浏览器的环境中验证产出格式**：用内置样本跑通完整流程，不访问网络。

```bash
python scripts/demo.py --out ./demo-out
python scripts/rank.py --dir ./demo-out --days 92
```

`demo.py` 生成 `all_items.json` / `all_items.csv`（20 条）与 `details.json`（3 条含精确发布时间），
`rank.py` 直接处理该目录并输出榜单。可在无浏览器、未登录的条件下确认三步产出的字段与结构。

**环境自检**：

```bash
python scripts/doctor.py
```

逐项报告浏览器路径、调试端口、CDP 连通性、登录态目录，并给出编号的修复建议。

## 浏览器生命周期

一次任务只启动一次浏览器，全部完成后关闭。中途重启会关闭标签页、丢失页面状态，
并重新触发登录态解密。

### 开始前探活

```bash
python scripts/cdp.py status
```

返回 `CDP_OK` 时直接复用，不重复启动；返回 `CDP_UNREACHABLE` 时才启动。

### 启动

普通环境：

```bash
python scripts/start_chrome.py
```

沙箱不可用时，脚本会打印 `READY` 但进程随即退出，`cdp.py status` 转而报
`CDP_UNREACHABLE`。此时启动命令需追加 `--no-sandbox --disable-gpu --disable-dev-shm-usage`，
并让进程以常驻方式运行。完整命令与说明见
`@references/browser-automation-cdp.md` 的「受限环境启动（沙箱不可用）」一节。

> `start_chrome.py` 输出的 `READY` 仅表示启动瞬间端口可达。
> 启动后必须用 `cdp.py status` 复核到 `CDP_OK`，再进入采集流程。

### 完成后关闭

```bash
python scripts/stop_chrome.py
python scripts/cdp.py status    # 应返回 CDP_UNREACHABLE
```

`stop_chrome.py` 优先通过 CDP 的 `Browser.close` 关闭，失败时按命令行中的
`--remote-debugging-port` 精确匹配进程，不影响日常使用的浏览器。
持久 profile 中的登录态会保留，下次启动无需重新登录。

## 风控

抖音搜索会触发人机验证（拖拽图片）。

- **验证码必须由用户在浏览器窗口手动完成。** 不绕过、不编写自动拖拽、不尝试点击。
- **抓到 0 条通常意味着已被验证拦截。** 停止并请用户完成验证，然后只补跑未采到的关键词 ——
  `harvest.py` 会复用 `all_items.json`，不会重复劳动。
- 默认节奏已为下限：每轮翻页间隔 4.5~6.5 秒、关键词之间停 9~14 秒、单次不超过 5 个关键词。
  提高速度只会增加验证码触发概率。

> **关键词选择**：使用「行业 + 动作/情绪」的组合词。宽泛词会引入大量无关内容，
> 实测「车主日常」「汽车后市场」这类词翻 8 轮可收 40+ 条，其中约一半是提车 vlog、
> 自驾游、影视片段等无关素材，人工筛选成本高于多采几个精准词。
> 优先使用 `修车被坑`、`保养套路`、`修理工的心酸` 这类组合；宽泛词最多保留 1 个用于探边界。

## 三步流程

执行前先确认环境：`python scripts/doctor.py`。若当前环境没有浏览器或未登录抖音，
改用 `python scripts/demo.py --out <目录>` 走通产出格式（见「环境要求与验证」），
实际采集需在装有浏览器并完成登录的本机执行。

三步依次为：采集 → 筛选 → 补精确数据。第 1、3 步依赖浏览器，第 2 步为纯本地计算。

### 第 1 步：批量采集搜索结果卡片

```bash
python scripts/harvest.py --out <输出目录> --keywords "装修避坑,装修后悔,建材避坑"
```

可选参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--rounds` | 6 | 每个关键词向下翻页轮数，约每轮多 10 条 |
| `--port` | 9222 | 浏览器调试端口 |
| `--cdp-skill` | 内嵌副本 | 改用指定的浏览器通道目录（默认用 `scripts/`） |
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
> 页面有结果却抓到 0 条时，通常是卡片行序变化 —— 修改 `collect.js` 顶部三个正则
> （`DUR` 时长 / `LIKE` 点赞 / `DATE` 时间）。

### 第 2 步：按时间和互动量筛选

```bash
python scripts/rank.py --dir <输出目录> --days 92
```

- `--days` 时间范围，默认 92（约 3 个月）。
- 时间是**相对时间换算的估计值**（`月` 按 30 天）。需要精确发布时间时执行第 3 步。
- 产出 `ranked.json`，按点赞降序，并在终端打印榜单。

> **相对时间标签与真实发布时间存在偏差，交付前需复核。**
> 实测搜索页标注「3月前」的视频，详情页精确发布时间距抓取日可达 120 天以上，
> `rank.py --days 92` 会因此保留已超出窗口的条目。
> 交付口径包含「近 N 天 / 近 N 个月」时，对每个入选条目执行第 3 步，
> 用 `details.json` 的 `publish` 做二次卡口。

### 第 3 步：给选定的少量视频补精确数据

```bash
python scripts/detail.py --dir <输出目录> --urls "https://www.douyin.com/video/xxx,https://www.douyin.com/video/yyy"
```

每个链接约 30~45 秒（含随机停顿），20 条约需 10 分钟，建议以后台任务执行。

产出 `details.json`：

| 字段 | 含义 |
|---|---|
| `digg` / `comment` / `collect` / `share` | 点赞 / 评论 / 收藏 / 分享 |
| `publish` | **精确发布时间**，形如 `发布时间：2026-06-30 18:07` |
| `user` | 作者 + 粉丝数 + 获赞数 |
| `tags` | 话题标签数组 |
| `info` | 详情页整块文案信息 |

> **`details.json` 为整文件覆盖写入，不做追加。**
> 分批补数据时，后一次运行会覆盖前一次结果。每批完成后另存副本
> （如 `details_keep1.json`），最后合并判读。

字段取自 `data-e2e` 属性（比 CSS class 稳定）。字段取空时，先查看当前真实节点名：

```bash
python scripts/cdp.py eval "JSON.stringify([...document.querySelectorAll('[data-e2e]')].map(e=>e.getAttribute('data-e2e')))"
```

再修改 `detail.py` 中的 `FIELDS` 映射。

`info` 为整块文本，文案之后会拼接点赞/评论/收藏/分享四个数字与 `举报`、`发布时间：…`。
判读时按 `发布时间` 截断即可取得干净文案。

## 结果怎么用

- `desc` 本身（文案 + 话题标签）就是一条可对标的**标题文案**。
- 需要**逐字口播稿**时另配 ASR，不在本技能范围；单条视频的深度拆解需另行调用视频解析工具。
- 判断素材类型：**收藏 > 点赞** → 工具型内容（清单/攻略），适合长效投放；
  **评论或分享占比高** → 情绪型内容，适合跑量拉新。这是分层复用素材的判据。
- 同题材高互动选题做成「第N集」，一个模板可反复用。

## 排障

| 现象 | 原因 | 处置 |
|---|---|---|
| 退出码 2：找不到浏览器通道 `cdp.py` | 技能包解压不完整 | 确认 `scripts/cdp.py` 存在；或 `--cdp-skill <技能目录>` 指向市场版 |
| 退出码 3：调试浏览器不可达 | 浏览器未启动 | 运行 `scripts/start_chrome.py`，再用 `cdp.py status` 复核到 `CDP_OK`；受限环境见「浏览器生命周期」 |
| 运行环境没有浏览器 | 无法驱动页面 | 用 `python scripts/demo.py --out <目录>` 验证产出格式；实际采集需在装有浏览器的本机执行 |
| `start_chrome.py` 打印 `READY`，随后 `status` 报 `CDP_UNREACHABLE` | 进程随启动命令被回收，或浏览器沙箱初始化失败 | 按「浏览器生命周期」的沙箱不可用流程启动 |
| 任务完成后浏览器仍在运行 | 未执行关闭步骤 | 运行 `scripts/stop_chrome.py`，再复核到 `CDP_UNREACHABLE` |
| 某个关键词抓到 0 条 | 人机验证拦截 | 请用户完成验证，再只补跑该关键词 |
| 全部抓到 0 条，页面空白 | 未登录 | 请用户扫码登录 |
| 抓到条目但字段错乱 | 卡片行序变化 | 修改 `collect.js` 的三个正则 |
| 详情页某指标为空 | `data-e2e` 节点改名 | 先列出节点名，再修改 `detail.py` 的 `FIELDS` |

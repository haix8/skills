# CDP 采集方法论：需登录 / 反爬站点

本文由实战场景提炼而来，去掉特定细节后，归纳出一套适用于**任何需登录态或存在反爬机制的网站**的 CDP 采集打法。

> 命令约定：下文 `<CDP>` 代表 `python <SKILL_DIR>/scripts/cdp.py`，`<SCRAPE>` 代表 `python <SKILL_DIR>/scripts/scrape.py`。

## 一、适用边界

当目标站点满足以下任一条件时，优先用「真实浏览器 + CDP」而非 HTTP 直连抓取：

- 有验证码、JS 挑战、请求签名校验（直连被拦）
- 真实数据只在登录后可见（后台看板、购物车、会员价）
- 页面内容由前端异步渲染，直接抓 HTML 拿不到
- 搜索引擎缓存的结果滞后或不准，必须看实时页面

真实浏览器会渲染真实 JS、通过指纹校验，看到与人类一致的页面，因此能绕过上述大部分障碍。

## 二、核心原则（按复用价值排序）

### 1. 反爬 / 需登录站点 → 用真实浏览器 CDP，别用 HTTP 直连

直连请求会被拦；第三方缓存结果又常滞后。用 CDP 驱动真实浏览器是唯一稳定解。

### 2. 登录态用独立配置目录，并区分持久与临时

| 用途 | 配置目录 | 登录态 |
|------|---------|--------|
| 需登录的任务（看板、购物车、任何靠 cookie 维持的账号） | 持久目录（`start_chrome.py` 默认） | 跨重启保留 |
| 纯公开页 / 一次性抓取 | 临时目录（`start_chrome.py --temp`） | 关闭即清空 |

切换只需改启动参数，无需改动任何脚本。

### 3. 首次手动登录 + 程序化验证（bootstrap 模式）

第一次手动登录目标站，并验证「关掉重开仍在线」后，再交给自动化。自动化运行前，先程序化确认能访问受保护区（目标页返回的是内容而非登录页），失败则不要继续。

`scrape.py` 已内置这一检测，命中登录特征会直接跳过本轮。

### 4. 写选择器前必先 inspect 真实 DOM（头号铁律）

绝不信记忆或文档里的 class。先用 `<CDP> text --max 3000` 看**当前真实结构**，再动手。

这是全篇最高频、最通用的踩坑结论。

### 5. 抽取要「抗脆弱」——按角色 / 属性 / 文本模式匹配，而非脆化的 CSS class

反爬站会**故意频繁改名 CSS class** 来破坏自动化脚本。

稳健写法：抓 `innerText` 逐行解析 → 用业务关键词定位区块 → 用正则定位数值 → 再上下文回溯找关联字段。

**通用建议：能按文本 / 位置 / 语义匹配，就别依赖 class。**

### 6. 会话过期要有「检测 → 跳过 → 告警 → 人工补登」闭环

- **检测**：页面 URL 或文本含登录特征。
- **处理**：本轮跳过记录、写日志、告警，**不要硬跑**。
- **恢复**：人工重登一次，下次自动恢复。

这是所有需登录自动化的通用运维模式（会话通常隔一段时间就会过期）。

### 7. 反爬挑战偶发 → 跳过 + 告警，不要崩

真实浏览器过指纹，已登录页极少触发验证码或滑块；万一触发，定时任务直接跳过本轮并通知，等人工处理。

### 8. 抽取用 `Runtime.evaluate` 直连，比高层 DOM 解析更稳

打开页面用 `open`，**内容抽取用 `eval --file`**，绕过中间层，更可靠。

### 9. 自写 CDP 客户端的三个必改 bug（实现级，可复用）

本技能的 `scripts/cdp.py` 已全部规避，自写时注意：

1. `navigate()` 加载超时必须返回 `False`（**不是** `True`），否则下游静默失败。
2. `send()` 响应循环必须跳过事件消息，否则 CDP 事件会被误当成下一条命令的响应。
3. 建立连接前必须校验 WebSocket URL 格式（含 `ws://` 与目标端口）。

### 10. 结构化落盘（JSON 机读 + CSV 人读 + 按日期归档）

机器用 JSON 便于下游处理，人看 CSV 便于纵向对比，统一存到带日期的目录。

## 三、注意：`loaded: true` 不等于拿到数据

页面加载完成只代表 `readyState` 变成 complete。导航失败时浏览器会停在错误页，此时同样是 complete。

因此每次操作后都要用 `title` 或 `text` 确认内容确实是你要的，`open` 命令输出的 `isErrorPage` 字段就是为此而设。

## 四、示例附录：按文本模式抗脆弱抽取（技术骨架）

> 以下为「按文本模式抗脆弱抽取」的**技术骨架**示例。所有真实商品、价格、店铺名均已替换为通用术语，仅保留匹配逻辑本身。完整可直接用的模板见 `<SKILL_DIR>/templates/extract.example.js`。

### 抽取思路

1. 取 `document.body.innerText`，按行清洗。
2. 用业务关键词定位每行所属区块。
3. 用正则定位目标行（如价格），再向前 / 向后回溯关联字段（标题、规格）。
4. 组装为对象数组返回，落盘为 JSON 与 CSV。

### 骨架：按正则定位 + 上下文回溯

```javascript
(() => {
  const CONFIG = {
    sectionKeywords: ['店铺', '专营', '自营'], // 区块分隔关键词
    valuePattern: /^¥[\d,]+(\.\d+)?$/,          // 目标行正则
    titleLookback: 6,                            // 向上回溯行数
    noiseWords: ['删除', '结算', '全选']          // 噪音行
  };

  const lines = (document.body ? document.body.innerText : '')
    .split('\n').map(l => l.trim()).filter(Boolean);

  const isNoise = (l) => CONFIG.noiseWords.some(w => l.includes(w));
  const isSection = (l) => CONFIG.sectionKeywords.some(k => l.includes(k)) && l.length < 40;

  const results = [];
  let currentSection = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (isSection(line)) { currentSection = line; continue; }
    if (!CONFIG.valuePattern.test(line)) continue;

    let title = '';
    for (let j = i - 1; j >= Math.max(0, i - CONFIG.titleLookback); j--) {
      const c = lines[j];
      if (!c || isNoise(c) || CONFIG.valuePattern.test(c)) continue;
      title = c;
      break;
    }
    results.push({ section: currentSection, title: title, value: line.replace(/[¥,\s]/g, '') });
  }
  return results;
})()
```

> 真实运行前务必先用 `<CDP> text --max 3000` 核对目标页当前文本，再据此调整 CONFIG——这是原则 4 的硬性要求。

## 五、一句话结论

去掉具体平台后，这套打法是一份高质量的「**需登录 / 反爬站点的 CDP 采集方法论**」；落地时拆成「通用原则 + 抽取模板 + 客户端 checklist」三块，具体站点的抽取 JS 仅作示例保留。

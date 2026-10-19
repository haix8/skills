# 常见结构的抽取片段库

按页面结构分类的现成 JavaScript 片段，配合 `python <SKILL_DIR>/scripts/cdp.py eval --file <文件>` 使用。

**使用前必读**：不要直接照抄选择器。先跑 `python <SKILL_DIR>/scripts/cdp.py text --max 3000` 看清当前页面真实结构，再据此调整。反爬站点会频繁改名 class，按文本与语义匹配永远比按 class 稳妥。

---

## 一、文档站侧边栏（Docusaurus 等）

这类文档站把侧边栏渲染为 `<nav>` 内的嵌套 `<li>`。

### 1. 列出全部可见链接（带层级深度）

```javascript
(function() {
  function walk(root, depth) {
    let result = [];
    root.querySelectorAll(':scope > li').forEach(li => {
      let a = li.querySelector(':scope > a, :scope > div > a');
      let href = a ? a.href : '';
      let text = a ? a.textContent.trim().replace(/\s+/g, ' ') : '';
      if (text && href && !href.includes('#')) result.push({ text, href, depth });
      let childUl = li.querySelector(':scope > ul, :scope > div > ul');
      if (childUl) result = result.concat(walk(childUl, depth + 1));
    });
    return result;
  }
  let menu = document.querySelector('.theme-doc-sidebar-menu, .menu__list, nav ul');
  return menu ? walk(menu, 0) : 'no menu';
})()
```

### 2. 构建完整目录树（分类 + 页面）

```javascript
(function() {
  function buildTree(ul) {
    let result = [];
    for (let li of ul.children) {
      let a = li.querySelector(':scope > a, :scope > div > a');
      let text = a ? a.textContent.trim().replace(/\s+/g, ' ') : '';
      if (!text) continue;
      let childUl = li.querySelector(':scope > ul, :scope > div > ul');
      let entry = { text, href: (a && a.href && !a.href.endsWith('#')) ? a.href : '' };
      if (childUl && childUl.children.length > 0) entry.children = buildTree(childUl);
      result.push(entry);
    }
    return result;
  }
  let menu = document.querySelector('.theme-doc-sidebar-menu, .menu__list, nav ul');
  return menu ? buildTree(menu) : 'no sidebar';
})()
```

### 3. 先展开所有折叠的分类

部分站点默认折叠，抽取前需要先展开：

```javascript
(function() {
  document.querySelectorAll(
    '.menu__list-item-collapsible[aria-expanded="false"], ' +
    '.menu__link--sublist[aria-expanded="false"], ' +
    'button[aria-label*="Expand"], button[aria-label*="展开"]'
  ).forEach(el => {
    let btn = el.tagName === 'BUTTON' ? el : el.closest('button');
    if (btn) btn.click();
  });
  document.querySelectorAll('.menu__link--sublist').forEach(link => {
    if (link.parentElement && link.parentElement.getAttribute('aria-expanded') === 'false') link.click();
  });
  return 'expanded';
})()
```

展开后**等 1~2 秒**再抽取。

---

## 二、搜索结果页

### 提取结果标题与链接

```javascript
Array.from(document.querySelectorAll('h3'))
  .slice(0, 10)
  .map((h, i) => `${i + 1}. ${h.textContent} - ${(h.closest('a') || {}).href || 'no link'}`)
  .join('\n')
```

### 完整搜索流程

```bash
# 1. 打开搜索页
python <SKILL_DIR>/scripts/cdp.py open "https://www.example-search.com"

# 2. 填入关键词（用 --file 更稳妥，见下）
python <SKILL_DIR>/scripts/cdp.py type "textarea[name=q], input[name=q]" "搜索词"

# 3. 提交
python <SKILL_DIR>/scripts/cdp.py click "form button[type=submit], input[type=submit]"

# 4. 等结果出现
python <SKILL_DIR>/scripts/cdp.py wait "document.querySelectorAll('h3').length > 0"

# 5. 抽取结果
python <SKILL_DIR>/scripts/cdp.py eval --file extract-results.js
```

> 若表单提交后页面无变化，改用 `eval` 直接提交：`document.querySelector('form').submit()`。

---

## 三、表格与列表

### 通用表格转二维数组

```javascript
(function() {
  const table = document.querySelector('table');
  if (!table) return 'no table';
  return Array.from(table.querySelectorAll('tr')).map(tr =>
    Array.from(tr.querySelectorAll('th, td')).map(td => td.innerText.trim())
  );
})()
```

### 通用列表项提取

```javascript
Array.from(document.querySelectorAll('li')).map(li => li.innerText.trim()).filter(Boolean).slice(0, 50)
```

---

## 四、通用检查片段

### 确认 CDP 连通

```bash
python <SKILL_DIR>/scripts/cdp.py status      # 看浏览器版本与标签页数
python <SKILL_DIR>/scripts/cdp.py tabs        # 看所有标签页的 id / 标题 / URL
```

### 快速判断当前在什么页面

```bash
python <SKILL_DIR>/scripts/cdp.py url
python <SKILL_DIR>/scripts/cdp.py title
python <SKILL_DIR>/scripts/cdp.py text --max 800
```

### 检查页面是否已渲染完成

```bash
python <SKILL_DIR>/scripts/cdp.py wait "document.querySelectorAll('.item').length > 0" --timeout 20
```

---

## 五、常见坑

| 坑 | 说明 |
|----|------|
| 不能用 `await` | `Runtime.evaluate` 里不能用 `await`，改用 `wait` 子命令轮询 |
| 多标签页 | 默认操作第一个标签页；用 `--url-contains` 或 `--target` 指定 |
| JS 返回值必须是可序列化的 | 返回 DOM 节点会得到空对象，要取 `innerText` / `value` 等基本类型 |
| 复杂 JS 别用命令行传 | 引号和中文容易被转义破坏，一律写文件用 `--file` |
| 页面结构会变 | 每次跑之前先用 `text` 核对，别假设结构不变 |

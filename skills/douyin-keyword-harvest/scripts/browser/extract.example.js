/**
 * 抗脆弱抽取模板 —— 复制本文件后，只改顶部 CONFIG 三处即可。
 *
 * 设计原则（为什么不用 CSS class）：
 *   反爬站点会刻意频繁改名 CSS class 来破坏爬虫。按「文本模式 + 位置回溯」匹配，
 *   页面改版后只需改关键词，不用重写选择器，健壮得多。
 *
 * 用法：
 *   1. 复制本文件为 my-extract.js
 *   2. 先用真实页面核对结构（铁律：写选择器前必先看真实 DOM）：
 *        python scripts/cdp.py open "<网址>"
 *        python scripts/cdp.py text --max 3000
 *   3. 按实际文本修改 CONFIG
 *   4. 试跑：python scripts/cdp.py eval --file my-extract.js
 *   5. 正式采集：python scripts/scrape.py --url "<网址>" --extract my-extract.js --out "<数据目录>"
 *
 * 本脚本必须返回一个能被 JSON 解析的值（对象或对象数组）。
 */
(() => {
  // ============ 按目标页面修改这三处 ============
  const CONFIG = {
    // 区块分隔关键词：命中该关键词的行，被视为一个新区块的开始
    sectionKeywords: ['旗舰店', '专营店', '专卖店', '自营'],

    // 目标行正则：命中即认为找到了一条记录的主行（这里以金额为例）
    valuePattern: /^¥[\d,]+(\.\d+)?$/,

    // 主行确定后，向上回溯多少行去找标题（标题通常在价格上方）
    titleLookback: 6,

    // 需要跳过的噪音行（含这些词的行不参与标题匹配）
    noiseWords: ['删除', '移入收藏', '找相似', '结算', '全选', '优惠券', '领券']
  };
  // ============================================

  const raw = document.body ? document.body.innerText : '';
  const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);

  const isNoise = (line) => CONFIG.noiseWords.some(w => line.includes(w));
  const isSection = (line) =>
    CONFIG.sectionKeywords.some(k => line.includes(k)) &&
    line.length < 40 && !line.includes('.') && !line.startsWith('http');

  const results = [];
  let currentSection = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (isSection(line)) {
      currentSection = line.replace(/^[^\w\u4e00-\u9fff]*/, '');
      continue;
    }

    if (!CONFIG.valuePattern.test(line)) continue;

    // 命中主行：向上回溯找标题
    let title = '';
    for (let j = i - 1; j >= Math.max(0, i - CONFIG.titleLookback); j--) {
      const candidate = lines[j];
      if (!candidate || isNoise(candidate) || CONFIG.valuePattern.test(candidate)) continue;
      if (candidate.length < 2) continue;
      title = candidate;
      break;
    }

    results.push({
      section: currentSection,
      title: title,
      value: line.replace(/[¥,\s]/g, ''),
      rawValue: line,
      lineIndex: i
    });
  }

  // 直接 return 数组即可，cdp.py 会把它序列化输出
  return results;
})()

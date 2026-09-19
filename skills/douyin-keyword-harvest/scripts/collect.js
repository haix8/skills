(() => {
  // 向下滚动一屏，并把当前 DOM 里所有搜索结果卡片解析出来。
  // 抖音搜索页是无限滚动 + 懒加载：必须"滚一次 → 读一次"，重复若干轮才能攒够。
  function findScroller() {
    var best = null;
    var all = document.querySelectorAll('div');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      var st = getComputedStyle(el);
      if (/(auto|scroll)/.test(st.overflowY) && el.scrollHeight > el.clientHeight + 200) {
        if (!best || el.scrollHeight > best.scrollHeight) best = el;
      }
    }
    return best;
  }
  var sc = findScroller();
  if (sc) { sc.scrollTop = sc.scrollTop + Math.max(800, Math.round(sc.clientHeight * 0.9)); }
  else { window.scrollBy(0, Math.max(800, Math.round(window.innerHeight * 0.9))); }

  // 卡片内文本按行排列：时长 / 点赞数 / 文案 / @作者 / 发布时间
  // 抖音改版时优先改这三个正则。
  var DUR = /^\d{1,2}:\d{2}(:\d{2})?$/;
  var LIKE = /^[\d.]+(万|亿)?$/;
  var DATE = /^(\d+(分钟|小时|天|周|月|年)前|今天|昨天|前天|刚刚)$/;

  var out = [];
  var seen = {};
  var anchors = document.querySelectorAll('a[href*="/video/"]');
  for (var k = 0; k < anchors.length; k++) {
    var a = anchors[k];
    var href = (a.href || '').split('?')[0];
    if (!href || seen[href]) continue;
    seen[href] = 1;
    var li = a.closest('li') || a.parentElement;
    if (!li) continue;
    var lines = (li.innerText || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    var isCollection = false;
    if (lines[0] === '合集') { isCollection = true; lines = lines.slice(1); }
    if (lines.length < 4) continue;
    if (!DUR.test(lines[0])) continue;
    var idx = 1;
    var likes = '';
    if (LIKE.test(lines[idx])) { likes = lines[idx]; idx++; }
    var date = lines[lines.length - 1];
    var author = lines[lines.length - 2];
    if (!DATE.test(date) || author.indexOf('@') !== 0) continue;
    var desc = lines.slice(idx, lines.length - 2).join(' ');
    out.push({ href: href, dur: lines[0], likes: likes, desc: desc, author: author, date: date, coll: isCollection });
  }
  return JSON.stringify({
    scroller: sc ? { sh: sc.scrollHeight, ch: sc.clientHeight, top: Math.round(sc.scrollTop) } : null,
    winY: Math.round(window.scrollY),
    count: out.length,
    items: out
  });
})()

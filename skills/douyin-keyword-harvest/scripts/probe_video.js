(() => {
  // 在抖音视频详情页（https://www.douyin.com/video/<id>）提取互动数据与发布时间。
  // 抖音用 data-e2e 标记这些节点，比 CSS class 稳定得多。
  var res = { title: document.title, url: location.href, e2e: {}, tags: [] };
  var nodes = document.querySelectorAll('[data-e2e]');
  for (var i = 0; i < nodes.length; i++) {
    var k = nodes[i].getAttribute('data-e2e');
    var t = (nodes[i].innerText || '').trim().replace(/\s+/g, ' ');
    if (t && t.length < 400) {
      if (!res.e2e[k]) res.e2e[k] = [];
      if (res.e2e[k].indexOf(t) === -1) res.e2e[k].push(t);
    }
  }
  var tagEls = document.querySelectorAll('a[href*="/search/"]');
  for (var j = 0; j < tagEls.length; j++) {
    var tt = (tagEls[j].innerText || '').trim();
    if (tt.charAt(0) === '#' && res.tags.indexOf(tt) === -1) res.tags.push(tt);
  }
  return JSON.stringify(res);
})()

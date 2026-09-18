#!/usr/bin/env node
/**
 * 抖音作品详情抓取 + 原片下载
 *
 *   node dy_fetch.js <aweme_id | https://v.douyin.com/xxx/>
 *   node dy_fetch.js <aweme_id> --download /path/out.mp4
 *   node dy_fetch.js <aweme_id> --gear normal_1080_0     # 指定清晰度档位
 *   node dy_fetch.js <aweme_id> --save-json /path/detail.json
 *
 * 原理：详情接口需要 ttwid / Uifid / a_bogus 签名，curl 直连会 403。
 * 先用 Chromium 打开 douyin.com 让站点写好 cookie，再在页面上下文内同源 fetch。
 *
 * 产物里会带上 subtitle_infos（官方字幕轨）和 is_subtitled，
 * 供「文案提取」第一层直接使用，见 SKILL.md Step 4。
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const https = require('https');
const { execFileSync } = require('child_process');

/** 解析 playwright-core —— 依次尝试常见位置，不写死本机路径 */
function loadPlaywright() {
  const names = ['playwright-core', 'playwright'];
  const bases = [null]; // null = 交给 node 自己按 NODE_PATH / node_modules 找

  if (process.env.NODE_PATH) {
    bases.push(...process.env.NODE_PATH.split(path.delimiter).filter(Boolean));
  }
  bases.push(
    path.join(process.cwd(), 'node_modules'),
    // WorkBuddy 各平台的统一托管目录（相对 home，不是某台机器专属路径）
    path.join(os.homedir(), '.workbuddy', 'binaries', 'node', 'workspace', 'node_modules'),
    path.join(os.homedir(), 'AppData/Roaming/npm/node_modules'), // Windows 全局 npm
    '/usr/local/lib/node_modules',
    '/opt/homebrew/lib/node_modules',
  );

  for (const base of bases) {
    for (const name of names) {
      try {
        return base ? require(path.join(base, name)) : require(name);
      } catch { /* 换下一个 */ }
    }
  }
  console.error(
    '\n[错误] 找不到 playwright-core。\n' +
    '  装它（在任意目录执行，或用 npm 全局装）：\n' +
    '    npm install playwright-core\n' +
    '    npx playwright install chromium\n\n' +
    '  如果是装在某个工作目录下，运行本脚本时把 NODE_PATH 指过去：\n' +
    '    macOS/Linux : NODE_PATH=/path/to/node_modules node dy_fetch.js ...\n' +
    '    Windows     : set NODE_PATH=C:\\path\\to\\node_modules && node dy_fetch.js ...\n'
  );
  process.exit(1);
}

const { chromium } = loadPlaywright();

/* ═══════════════════════════════════════════════════════════════
   跨平台解析 Chromium 与 ffmpeg —— 不要硬编码本机绝对路径。
   这个技能要分享给别人，对方的机器可能是 Windows / Linux。
   ═══════════════════════════════════════════════════════════════ */

/** 各平台的 ms-playwright 缓存目录 */
function playwrightCacheDirs() {
  const home = os.homedir();
  if (process.platform === 'darwin') return [path.join(home, 'Library/Caches/ms-playwright')];
  if (process.platform === 'win32') {
    const local = process.env.LOCALAPPDATA || path.join(home, 'AppData', 'Local');
    return [path.join(local, 'ms-playwright')];
  }
  return [path.join(home, '.cache/ms-playwright')];
}

/** chromium-<rev>/ 目录下的可执行文件相对路径（各平台不同） */
function chromiumRelPaths() {
  const rel = [];
  if (process.platform === 'darwin') {
    rel.push('chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing');
    rel.push('chrome-mac/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing');
    rel.push('chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing');
  } else if (process.platform === 'win32') {
    rel.push('chrome-win/chrome.exe');
    rel.push('chrome-win64/chrome.exe');
  } else {
    rel.push('chrome-linux/chrome');
  }
  return rel;
}

/** 系统已装的 Chrome / Edge —— 没装 playwright 浏览器时的兜底（Windows 上 Edge 必有） */
function systemBrowsers() {
  const out = [];
  if (process.platform === 'win32') {
    out.push('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe');
    out.push('C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe');
    out.push('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe');
    out.push('C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe');
  } else if (process.platform === 'darwin') {
    out.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
    out.push('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge');
  } else {
    out.push('/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium');
  }
  return out;
}

function resolveChromium() {
  // 1) 环境变量
  if (process.env.CHROME && fs.existsSync(process.env.CHROME)) return process.env.CHROME;

  // 2) 问 playwright 自己（注意：它可能指向【没装】的版本，必须校验存在）
  try {
    const p = chromium.executablePath();
    if (p && fs.existsSync(p)) return p;
  } catch { /* 忽略 */ }

  // 3) 扫缓存目录，取版本号最大的那个
  for (const dir of playwrightCacheDirs()) {
    if (!fs.existsSync(dir)) continue;
    const revs = fs.readdirSync(dir)
      .filter((n) => /^chromium-\d+$/.test(n))
      .sort((a, b) => parseInt(b.split('-')[1], 10) - parseInt(a.split('-')[1], 10));
    for (const rev of revs) {
      for (const rel of chromiumRelPaths()) {
        const full = path.join(dir, rev, rel);
        if (fs.existsSync(full)) return full;
      }
    }
  }

  // 4) 系统浏览器兜底
  for (const p of systemBrowsers()) {
    if (fs.existsSync(p)) return p;
  }

  console.error(
    '\n[错误] 找不到可用的 Chromium。\n' +
    '  playwright 的浏览器没装，至少要做以下之一：\n' +
    '    1) npx playwright install chromium\n' +
    '    2) 装一个系统 Chrome / Edge（Windows 上 Edge 自带，通常无需操作）\n' +
    '    3) 用环境变量指定：\n' +
    '         macOS/Linux : export CHROME=/path/to/chrome\n' +
    '         Windows     : set CHROME=C:\\path\\to\\chrome.exe\n'
  );
  process.exit(1);
}

function resolveFfmpeg() {
  // 只用它来探测下载到的文件有没有音轨，属于"有更好、没有也能跑"
  if (process.env.FFMPEG && fs.existsSync(process.env.FFMPEG)) return process.env.FFMPEG;

  // 借 python 的 imageio-ffmpeg 拿到跨平台路径。
  // 候选里既有 PATH 上的 python，也有 WorkBuddy 托管 venv（各平台相对 home，非机器专属）。
  const home = os.homedir();
  const pythons = [
    'python3', 'python', 'py',
    path.join(home, '.workbuddy', 'binaries', 'python', 'envs', 'default', 'bin', 'python'),
    path.join(home, '.workbuddy', 'binaries', 'python', 'envs', 'default', 'Scripts', 'python.exe'),
  ];
  for (const py of pythons) {
    try {
      const out = execFileSync(py, ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())'],
        { encoding: 'utf-8', timeout: 20000, stdio: ['ignore', 'pipe', 'ignore'] }).trim();
      if (out && fs.existsSync(out)) return out;
    } catch { /* 换下一个 */ }
  }

  // PATH 里找
  for (const name of ['ffmpeg', 'ffmpeg.exe']) {
    try {
      const out = execFileSync(process.platform === 'win32' ? 'where' : 'which', [name],
        { encoding: 'utf-8', timeout: 10000, stdio: ['ignore', 'pipe', 'ignore'] }).trim().split('\n')[0];
      if (out && fs.existsSync(out)) return out;
    } catch { /* 忽略 */ }
  }
  return null; // 探测跳过，不影响主流程
}

const CHROME = resolveChromium();
const FFMPEG = resolveFfmpeg();

const MODERN_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';
const MOBILE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';

function parseArgv(argv) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const k = argv[i].slice(2);
      const v = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
      flags[k] = v;
    } else positional.push(argv[i]);
  }
  return { positional, flags };
}

function resolveShortLink(link) {
  return new Promise((resolve, reject) => {
    const req = https.get(link, { headers: { 'User-Agent': MOBILE_UA } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return resolve(res.headers.location);
      }
      resolve(link);
    });
    req.on('error', reject);
    req.setTimeout(20000, () => {
      req.destroy();
      reject(new Error('resolve timeout'));
    });
  });
}

function download(url, outPath) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(outPath);
    https
      .get(url, { headers: { 'User-Agent': MODERN_UA, Referer: 'https://www.douyin.com/' } }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          file.close();
          try { fs.unlinkSync(outPath); } catch {}
          return download(res.headers.location, outPath).then(resolve, reject);
        }
        if (res.statusCode !== 200) {
          file.close();
          return reject(new Error('HTTP ' + res.statusCode));
        }
        res.pipe(file);
        file.on('finish', () => file.close(() => resolve(outPath)));
      })
      .on('error', reject);
  });
}

/** 用 ffmpeg 的 stderr 读流信息，校验下载到的文件有没有音频轨 */
function probeStreams(file) {
  if (!FFMPEG) return ''; // 没找到 ffmpeg 就跳过校验，不影响主流程
  try {
    return execFileSync(FFMPEG, ['-hide_banner', '-i', file], { stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  } catch (e) {
    return (e.stderr || Buffer.from('')).toString();
  }
}

(async () => {
  const { positional, flags } = parseArgv(process.argv.slice(2));
  let input = positional[0];
  if (!input) {
    console.error('usage: node dy_fetch.js <aweme_id | 抖音分享链接> [--download out.mp4] [--gear 档位] [--save-json f.json] [--verbose]');
    process.exit(1);
  }

  if (/^https?:/.test(input) && !/\/video\//.test(input)) {
    console.error('# resolving short link ...');
    input = await resolveShortLink(input);
  }
  const m = String(input).match(/(\d{15,25})/);
  if (!m) {
    console.error('无法从输入里解析出 aweme_id:', input);
    process.exit(1);
  }
  const awemeId = m[1];

  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox', '--mute-audio'] });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'zh-CN', userAgent: MODERN_UA });
  const page = await ctx.newPage();
  await page.goto('https://www.douyin.com/', { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
  await page.waitForTimeout(6000);

  const body = await page.evaluate(async (id) => {
    const url =
      '/aweme/v1/web/aweme/detail/?aweme_id=' + id + '&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1';
    const r = await fetch(url, { credentials: 'include' });
    return { status: r.status, text: await r.text() };
  }, awemeId);
  await browser.close();

  if (body.status !== 200) {
    console.error('详情接口返回', body.status, body.text.slice(0, 200));
    process.exit(1);
  }
  let j;
  try {
    j = JSON.parse(body.text);
  } catch {
    console.error('返回不是 JSON:', body.text.slice(0, 300));
    process.exit(1);
  }
  const d = j.aweme_detail;
  if (!d) {
    console.error('无 aweme_detail，可能作品已删除或需要登录');
    process.exit(1);
  }
  if (flags['save-json']) fs.writeFileSync(flags['save-json'], JSON.stringify(d, null, 2));

  // ── 官方字幕轨：两个位置都要看 ──
  let subtitleInfos = d.subtitle_infos || [];
  if (!subtitleInfos.length) {
    subtitleInfos = (d.video && d.video.subtitle && d.video.subtitle.subtitleInfos) || [];
  }
  const subtitles = subtitleInfos.map((s) => ({
    lang: s.LanguageCodeName || s.languageCodeName || '',
    format: s.Format || s.format || 'vtt',
    url: s.Url || s.url || '',
  }));

  // 清晰度档位。默认【不带 URL】—— URL 又长又带签名，会把摘要淹掉；
  // 需要直链时加 --verbose。
  const gears = (d.video.bit_rate || []).map((b) => {
    const g = {
      gear: b.gear_name,
      size: b.play_addr ? b.play_addr.width + 'x' + b.play_addr.height : '',
      kbps: Math.round((b.bit_rate || 0) / 1000),
      fmt: b.format || 'mp4',
    };
    if (flags.verbose) g.url = b.play_addr && b.play_addr.url_list ? b.play_addr.url_list[0] : null;
    return g;
  });

  // 选流：优先高码率；但抖音有「纯视频轨」的流，下载后必须校验音轨
  let chosen = [...gears].sort((a, b) => b.kbps - a.kbps)[0];
  if (flags.gear) chosen = gears.find((g) => g.gear === flags.gear) || chosen;
  const chosenFull = (d.video.bit_rate || []).find((b) => b.gear_name === (chosen && chosen.gear));
  const chosenUrl = chosenFull && chosenFull.play_addr && chosenFull.play_addr.url_list
    ? chosenFull.play_addr.url_list[0]
    : null;

  const summary = {
    aweme_id: awemeId,
    desc: d.desc,
    publish_time: new Date(d.create_time * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
    create_time: d.create_time,
    duration_sec: d.video && d.video.duration ? d.video.duration / 1000 : null,
    resolution: d.video ? d.video.width + 'x' + d.video.height : null,
    author: d.author && {
      nickname: d.author.nickname,
      douyin_id: d.author.unique_id,
      follower: d.author.follower_count,
      total_favorited: d.author.total_favorited,
      verify: d.author.enterprise_verify_reason || d.author.custom_verify || '',
    },
    hashtags: (d.text_extra || []).map((t) => t.hashtag_name).filter(Boolean),
    stats: {
      digg: d.statistics && d.statistics.digg_count,
      collect: d.statistics && d.statistics.collect_count,
      share: d.statistics && d.statistics.share_count,
      comment: d.statistics && d.statistics.comment_count,
    },
    is_paid_creative: d.ad_aweme_source === 1 || !!d.is_ads,
    ad_aweme_source: d.ad_aweme_source,
    has_link_ad: !!d.link_ad_data,
    music: d.music && d.music.title,
    // ↓ 文案提取第一层用。注意 is_subtitled 可能是 0 / 1 / 缺字段，
    //   显式补 null，避免字段整个消失导致误判
    is_subtitled: d.is_subtitled === undefined ? null : d.is_subtitled,
    subtitle_count: subtitles.length,
    subtitles,
    gears,
    chosen_gear: chosen && chosen.gear,
  };
  if (flags.verbose) summary.play_url = chosenUrl;
  console.log(JSON.stringify(summary, null, 2));

  if (flags.download && chosenUrl) {
    console.error('# downloading', chosen.gear, '->', flags.download);
    await download(chosenUrl, flags.download);
    console.error('# saved', (fs.statSync(flags.download).size / 1024 / 1024).toFixed(1), 'MB');

    const info = probeStreams(flags.download);
    if (!info) {
      console.error('# （没找到 ffmpeg，跳过音轨校验。要跑 ASR 的话建议装上 imageio-ffmpeg）');
    } else {
      const hasAudio = /Stream #\d+:\d+.*Audio:/i.test(info);
      const hasVideo = /Stream #\d+:\d+.*Video:/i.test(info);
      console.error('# tracks: video=' + hasVideo + ' audio=' + hasAudio);
      if (!hasAudio) {
        console.error('# ⚠️ 这个流没有音频轨（抖音会把音视频分轨）。要跑 ASR 就换档位重下：' + gears.map((g) => g.gear).join(' / '));
      }
      if (!hasVideo) console.error('# ⚠️ 没有视频轨，换档位重下');
    }
  }
})();

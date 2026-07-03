#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const axios = require('axios');
const FormData = require('form-data');
const MarkdownIt = require('markdown-it');

const skillDir = path.resolve(__dirname, '..');
require('dotenv').config({ path: path.join(skillDir, '.env') });
require('dotenv').config();

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith('--')) continue;
    const key = item.slice(2);
    if (key === 'dry-run' || key === 'no-verify' || key === 'help') {
      args[key] = true;
    } else {
      args[key] = argv[i + 1];
      i += 1;
    }
  }
  return args;
}

function usage() {
  return `Usage:
  node scripts/publish-draft.js \\
    --title "Article title" \\
    --content /absolute/path/article.html \\
    --cover /absolute/path/cover.png \\
    [--author "Author"] [--digest "Digest"] [--format auto|html|markdown] [--dry-run] [--no-verify]
`;
}

function credentialHelp() {
  return [
    'WECHAT_APPID and WECHAT_SECRET are required.',
    '',
    'How to get them:',
    '1. Open https://mp.weixin.qq.com/ and log in to the target official account.',
    '2. Go to 设置与开发 -> 基本配置.',
    '3. Copy 开发者ID(AppID) as WECHAT_APPID.',
    '4. Use 开发者密码(AppSecret) as WECHAT_SECRET. If hidden, reset it after admin verification; the old secret becomes invalid.',
    '',
    `Save them to ${path.join(skillDir, '.env')}:`,
    'WECHAT_APPID=wx...',
    'WECHAT_SECRET=...',
    '',
    `Then run: chmod 600 ${path.join(skillDir, '.env')}`,
    '',
    'Do not commit or print AppSecret in user-facing output.'
  ].join('\n');
}

function requireFile(filePath, label) {
  if (!filePath) throw new Error(`Missing --${label}`);
  const abs = path.resolve(filePath);
  if (!fs.existsSync(abs)) throw new Error(`${label} file not found: ${abs}`);
  if (!fs.statSync(abs).isFile()) throw new Error(`${label} is not a file: ${abs}`);
  return abs;
}

function detectFormat(contentPath, explicitFormat) {
  const format = explicitFormat || 'auto';
  if (!['auto', 'html', 'markdown'].includes(format)) {
    throw new Error(`Unsupported --format: ${format}`);
  }
  if (format !== 'auto') return format;
  const ext = path.extname(contentPath).toLowerCase();
  if (ext === '.html' || ext === '.htm') return 'html';
  if (ext === '.md' || ext === '.markdown') return 'markdown';
  throw new Error('Cannot auto-detect content format. Pass --format html or --format markdown.');
}

function markdownToWechatHtml(markdown) {
  const md = new MarkdownIt({ html: true, linkify: true, typographer: true });

  md.renderer.rules.paragraph_open = () =>
    '<p style="margin: 0 0 16px 0; line-height: 1.8; font-size: 15px; color: #333333; letter-spacing: 0.5px;">';

  md.renderer.rules.heading_open = (tokens, idx) => {
    const tag = tokens[idx].tag;
    const size = tag === 'h1' ? '24px' : tag === 'h2' ? '20px' : '17px';
    return `<${tag} style="font-size: ${size}; font-weight: 700; line-height: 1.5; margin: 24px 0 12px; color: #111111;">`;
  };

  md.renderer.rules.blockquote_open = () =>
    '<blockquote style="margin: 18px 0; padding: 12px 16px; border-left: 4px solid #2F6BFF; background: #F6F8FF; color: #444444;">';

  md.renderer.rules.bullet_list_open = () =>
    '<ul style="margin: 12px 0 18px; padding-left: 22px; line-height: 1.8; font-size: 15px; color: #333333;">';

  md.renderer.rules.ordered_list_open = () =>
    '<ol style="margin: 12px 0 18px; padding-left: 22px; line-height: 1.8; font-size: 15px; color: #333333;">';

  return md.render(markdown);
}

function readContent(contentPath, format) {
  const raw = fs.readFileSync(contentPath, 'utf8');
  if (format === 'html') return raw;
  return markdownToWechatHtml(raw);
}

class WechatDraftClient {
  constructor(appId, appSecret) {
    this.appId = appId;
    this.appSecret = appSecret;
    this.accessToken = null;
  }

  async getAccessToken() {
    if (this.accessToken) return this.accessToken;
    const res = await axios.get('https://api.weixin.qq.com/cgi-bin/token', {
      params: {
        grant_type: 'client_credential',
        appid: this.appId,
        secret: this.appSecret
      }
    });
    if (res.data.errcode) {
      throw new Error(`getAccessToken failed [${res.data.errcode}]: ${res.data.errmsg}`);
    }
    this.accessToken = res.data.access_token;
    return this.accessToken;
  }

  async uploadCover(coverPath) {
    const token = await this.getAccessToken();
    const form = new FormData();
    form.append('media', fs.createReadStream(coverPath));
    const res = await axios.post('https://api.weixin.qq.com/cgi-bin/material/add_material', form, {
      params: { access_token: token, type: 'image' },
      headers: form.getHeaders()
    });
    if (res.data.errcode) {
      throw new Error(`uploadCover failed [${res.data.errcode}]: ${res.data.errmsg}`);
    }
    return res.data.media_id;
  }

  async createDraft(article) {
    const token = await this.getAccessToken();
    const res = await axios.post('https://api.weixin.qq.com/cgi-bin/draft/add',
      { articles: [article] },
      {
        params: { access_token: token },
        headers: { 'Content-Type': 'application/json; charset=UTF-8' }
      }
    );
    if (res.data.errcode && res.data.errcode !== 0) {
      throw new Error(`createDraft failed [${res.data.errcode}]: ${res.data.errmsg}`);
    }
    return res.data.media_id;
  }

  async getDraft(mediaId) {
    const token = await this.getAccessToken();
    const res = await axios.post('https://api.weixin.qq.com/cgi-bin/draft/get',
      { media_id: mediaId },
      {
        params: { access_token: token },
        headers: { 'Content-Type': 'application/json; charset=UTF-8' }
      }
    );
    if (res.data.errcode && res.data.errcode !== 0) {
      throw new Error(`getDraft failed [${res.data.errcode}]: ${res.data.errmsg}`);
    }
    return res.data.news_item && res.data.news_item[0];
  }
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    process.stdout.write(usage());
    return;
  }

  const title = args.title;
  if (!title) throw new Error('Missing --title');
  const contentPath = requireFile(args.content, 'content');
  const coverPath = requireFile(args.cover, 'cover');
  const format = detectFormat(contentPath, args.format);
  const content = readContent(contentPath, format);

  const article = {
    title,
    author: args.author || '',
    digest: args.digest || '',
    content,
    need_open_comment: 0,
    only_fans_can_comment: 0
  };

  if (args['dry-run']) {
    process.stdout.write(JSON.stringify({
      success: true,
      dry_run: true,
      format,
      title,
      author: article.author,
      digest: article.digest,
      content_path: contentPath,
      cover_path: coverPath,
      content_length: content.length
    }, null, 2) + '\n');
    return;
  }

  const appId = process.env.WECHAT_APPID;
  const appSecret = process.env.WECHAT_SECRET;
  if (!appId || !appSecret) {
    throw new Error(credentialHelp());
  }

  const client = new WechatDraftClient(appId, appSecret);
  const thumbMediaId = await client.uploadCover(coverPath);
  article.thumb_media_id = thumbMediaId;

  const draftMediaId = await client.createDraft(article);
  const result = {
    success: true,
    draft_media_id: draftMediaId,
    thumb_media_id: thumbMediaId
  };

  if (!args['no-verify']) {
    const verified = await client.getDraft(draftMediaId);
    result.verified = {
      title: verified && verified.title,
      author: verified && verified.author,
      digest: verified && verified.digest,
      content_length: verified && verified.content ? verified.content.length : 0,
      thumb_media_id: verified && verified.thumb_media_id
    };
  }

  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}

main().catch((error) => {
  process.stderr.write(JSON.stringify({ success: false, error: error.message }, null, 2) + '\n');
  process.exit(1);
});

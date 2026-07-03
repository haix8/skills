---
name: wechat-draft-publisher
description: Upload a finished WeChat official account article to the draft box. Use when the user asks to send, upload, publish, push, or save an already-written article as a WeChat/微信公众号 draft, including Markdown or WeChat-ready HTML plus a cover image. Also use when the user needs guidance obtaining or configuring WeChat AppID/AppSecret for draft upload. This skill does not write articles, generate covers, or design layouts.
---

# WeChat Draft Publisher

Use this skill only for one capability: create a WeChat official account draft from an existing article file and cover image.

## Inputs

Required:

- `--title`: article title
- `--content`: existing article file, Markdown or HTML
- `--cover`: local PNG/JPG cover image

Optional:

- `--author`: author shown in WeChat
- `--digest`: draft summary
- `--format`: `auto`, `html`, or `markdown`; default `auto`
- `--no-verify`: skip `draft/get` verification after creation
- `--dry-run`: validate files and conversion without calling WeChat APIs

## Credentials

The WeChat draft API requires official account credentials:

```bash
WECHAT_APPID=...
WECHAT_SECRET=...
```

Read credentials from the skill-local `.env` first, then environment variables. If credentials are missing, do not attempt upload. Guide the user to get them:

1. Open [WeChat Official Account Platform](https://mp.weixin.qq.com/) and log in as an admin or operator with developer settings permission.
2. Go to `设置与开发` -> `基本配置`.
3. Copy `开发者ID(AppID)` as `WECHAT_APPID`.
4. Use `开发者密码(AppSecret)` as `WECHAT_SECRET`. If it is not visible, use `重置` and complete the admin verification; the old secret becomes invalid after reset.
5. Put the values in `/Users/ld/.codex/skills/wechat-draft-publisher/.env`:

```bash
WECHAT_APPID=wx...
WECHAT_SECRET=...
```

Then run:

```bash
chmod 600 /Users/ld/.codex/skills/wechat-draft-publisher/.env
```

Never place AppSecret in `SKILL.md`, chat output, committed files, or user-facing deliverables. If the user provides credentials in chat, write them only to `.env`, tighten permissions, and avoid echoing the secret back.

## Workflow

1. Confirm the article content already exists. Do not write or rewrite it unless the user separately asks.
2. Prefer HTML input when the article has already been styled for WeChat. Markdown input is converted with simple inline styles.
3. Run `scripts/publish-draft.js`.
4. If credentials are missing, stop and provide the credential retrieval steps above.
5. If the API fails with `invalid ip ... not in whitelist`, tell the user to add the IP returned by WeChat to the official account IP whitelist, then retry.
6. Treat the task as complete only after WeChat returns a draft `media_id` and verification succeeds or the user explicitly accepts skipping verification.

## Command

```bash
node /Users/ld/.codex/skills/wechat-draft-publisher/scripts/publish-draft.js \
  --title "文章标题" \
  --author "作者" \
  --digest "摘要" \
  --content /absolute/path/article.html \
  --cover /absolute/path/cover.png \
  --format html
```

The script prints JSON. On success, record:

- `draft_media_id`
- `thumb_media_id`
- verified `title`, `author`, `digest`, and `content_length`

## Constraints

- Requires an official account that supports the WeChat draft API.
- Requires `WECHAT_APPID` and `WECHAT_SECRET`; these come from `设置与开发` -> `基本配置` in the WeChat official account backend.
- Requires the current machine/network IP to be in the official account IP whitelist.
- Cover image must be a local PNG/JPG accepted by WeChat material upload.
- HTML input must already use WeChat-compatible inline styles; the script does not sanitize complex CSS.
- Body images must already use remote URLs accessible to WeChat. Upload local body images separately before using this skill.

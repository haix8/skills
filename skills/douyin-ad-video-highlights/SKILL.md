---
name: douyin-ad-video-highlights
description: Turn long videos, meeting recordings, course recordings, livestream replays, product demos, or raw oral footage into Douyin/TikTok paid-ad short-video materials and visible CapCut/Jianying draft projects. Use when the user asks for Douyin投流视频, 巨量引擎素材, 短视频广告切片, 口播广告剪辑, 素材A/B版本, 高转化短视频, or 剪映工程 for ad creatives.
---

# Douyin Ad Video Highlights

## Purpose

Create Douyin paid-ad-ready short videos from long source material. Optimize for attention, retention, trust, and conversion instead of meeting completeness or chronological summaries.

The expected deliverable is a working folder containing source material, an ad-focused editing plan, cut clips, variant exports when requested, validation checks, and optionally a CapCut/Jianying draft installed under the local draft root so it appears in the app.

## Core Positioning

Treat every output as an ad creative candidate. Prefer short standalone clips that can sell one idea clearly:

- Problem: a painful user situation, misconception, cost, risk, or desire.
- Promise: a specific result, workflow, comparison, or transformation.
- Proof: visible demo, screenshot, before/after, data, customer case, authority, or operational detail.
- Action: a soft or explicit next step suitable for Douyin paid traffic.

Do not produce a balanced meeting recap unless the user explicitly asks for one.

## Workflow

### 1. Ingest Source

Accept:

- Tencent Meeting, Feishu/Lark meeting, local video, livestream replay, product demo, oral footage, screen recording, or existing CapCut/Jianying draft.
- Transcript, subtitles, script, product notes, landing page copy, customer persona, or campaign objective if available.

Create a working folder before cutting. Use the user-specified folder if given; otherwise create a clear folder under the current workspace or video collection path.

Recommended shape:

```text
<workdir>/
├── source/
├── clips/
├── variants/
├── draft-build/
├── checks/
├── edit-plan.md
├── concat.txt
└── notes.md
```

Record source and campaign context in `notes.md`:

```markdown
# Source

- Link:
- Local file:
- Retrieved at:
- Duration:
- Transcript:
- Product/service:
- Audience:
- Campaign objective:
- Compliance/claims notes:
```

If the source cannot be accessed, do not invent clip choices. State the access blocker and continue only with available local material.

### 2. Create Ad Editing Plan First

Always write `edit-plan.md` before cutting. The plan must include time ranges, ad angle, hook, proof, CTA, and scoring. It should be concrete enough for another editor to execute.

Default output target:

- Aspect ratio: `9:16`
- Canvas: `1080x1920`
- Duration: prefer `15-45s`; allow `6-12s` for hook tests and `45-60s` when proof/demo needs continuity.
- First screen: no neutral title card by default. Start with the strongest hook or a freeze frame carrying an editable hook text layer.

Ad scoring, 10 points:

| Dimension | Points | What qualifies |
|---|---:|---|
| 0-3s hook | 0-2 | Pain, result, contradiction, curiosity, or direct target-user callout |
| Pain/result clarity | 0-2 | Viewer immediately understands the problem or promised outcome |
| Proof/trust | 0-2 | Demo, data, case, concrete process, real UI, customer language, or authority |
| Conversion focus | 0-2 | One offer/benefit/next step is clear without becoming noisy |
| Visual retention | 0-2 | Screen change, face, gesture, subtitle rhythm, before/after, or pattern break |

Keep candidates scoring `7+`. Keep `6` only for A/B learning or a missing campaign angle. Reject low-signal context, long setup, greetings, meeting logistics, and generic claims.

Recommended `edit-plan.md`:

```markdown
# Douyin Ad Editing Plan

## Source

- Recording:
- Local media:
- Duration:
- Transcript/material basis:
- Product/service:
- Audience:
- Campaign objective:

## Creative Strategy

- Primary conversion goal:
- Core pain:
- Main promise:
- Proof assets:
- Compliance constraints:

## Clip Plan

| Clip | Ad Angle | Hook Text | Start | End | Duration | Score | Proof/Payoff | CTA | Output |
|---|---|---|---:|---:|---:|---:|---|---|---|
| 1 | 痛点直击 |  | 00:00:00 | 00:00:00 | 0s | 0/10 |  |  | clips/clip01.mp4 |

## Variant Plan

| Variant | Base Clip | Change | Purpose |
|---|---|---|---|
| A | clip01 | Strong pain hook | Test pain resonance |
| B | clip01 | Result-first hook | Test outcome pull |

## Rejected Candidates

| Candidate | Start | End | Score | Why rejected |
|---|---:|---:|---:|---|

## Packaging Notes

- Canvas:
- Crop/reframe:
- Captions:
- Hook text:
- Highlight words:
- CTA:
- Audio:

## Execution Notes

- ffmpeg command pattern:
- Draft output path:
- Validation checklist:
```

### 3. Cut And Reframe

Use `ffprobe` before cutting:

```bash
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$source"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -of default=nw=1 "$source"
```

Cut planned segments into `clips/`.

Fast approximate cut:

```bash
ffmpeg -y -ss "$start" -to "$end" -i "$source" -c copy "$out"
```

Accurate cut and 9:16 export:

```bash
ffmpeg -y -ss "$start" -to "$end" -i "$source" \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" \
  -c:v libx264 -preset veryfast -crf 18 \
  -c:a aac -b:a 160k \
  "$out"
```

For screen recordings, do not blindly center-crop if it hides the product. Prefer a readable 9:16 layout: main content crop, face/camera crop when useful, enlarged UI region, or top/bottom background fill. Keep the real product/result visible.

After cutting:

- Run `ffprobe` on outputs and compare durations with `edit-plan.md`.
- Save representative frames in `checks/` when crop/readability matters.
- Mark any low-confidence clip or crop decision in the plan.

### 3.1 Tighten Oral Clips

For talking-head, oral sales, course, or livestream footage, do not leave obvious dead air just because it is inside a planned time range.

Default tightening pass:

- Detect silence or low-volume gaps with `ffmpeg` `silencedetect`, then inspect the transcript/audio around the candidate gaps.
- Cut filler pauses, long breath gaps, repeated restarts, and empty thinking time when they do not carry meaning.
- Preserve natural micro-pauses that make the speaker sound human; do not over-compress until speech feels robotic.
- After removing gaps, remap subtitle/caption timings onto the compressed timeline. Do not reuse source timestamps directly after silence removal.
- If audio and subtitles drift after tightening, rebuild the caption timing from the final cut timeline before exporting.

Useful pattern:

```bash
ffmpeg -i "$source" -af silencedetect=noise=-32dB:d=0.22 -f null - 2> checks/silencedetect.log
```

Treat the thresholds as starting points. Adjust for noisy rooms, lav mic volume, and speaker style.

### 4. Package For Douyin Ads

Default packaging:

- Put the strongest hook in the first frame or first 1 second.
- Use large editable hook text, not a neutral project title card.
- Keep subtitles inside Douyin safe zones: avoid the bottom interaction area and the right-side buttons.
- Use short subtitle lines with intentional breaks. Compress filler words; do not transcribe every hesitation.
- For rendered ad captions, remove visible punctuation. Use punctuation from the transcript only as line-break hints.
- If one caption contains two short clauses or sentences, prefer two lines rather than one long line.
- Keep captions synced to the exported audio, especially after any silence/gap removal.
- Highlight keywords only when they help scanning. Avoid turning the whole video into flashing text.
- Prefer one CTA per video. Keep it native and low-friction.

Default text guidance for `1080x1920`:

- Hook text: top or upper-middle, large enough to read on mobile, concise enough to fit.
- Captions: lower-middle, above bottom UI controls.
- Key colors: use strong contrast; avoid relying on a single brand color if it hurts readability.
- For regulated or sensitive claims, keep proof and wording conservative. Do not fabricate numbers, customer results, medical/financial/legal promises, or platform performance claims.

### 5. Generate CapCut/Jianying Draft

When the user asks for a visible editable project, generate a CapCut/Jianying draft and install it under the detected draft root.

Prefer detecting local roots instead of hardcoding another user's path:

```bash
for p in \
  "$HOME/Movies/JianyingPro/User Data/Projects/com.lveditor.draft" \
  "$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft"
do
  if [ -d "$p" ]; then draft_root="$p"; break; fi
done
test -n "$draft_root" || { echo "No CapCut/Jianying draft root found"; exit 1; }
```

Use `<workdir>/draft-build/<project-name>_剪映工程` as staging. After validation, copy the complete folder into `$draft_root`.

Draft requirements:

- Canvas should match the ad output, usually `1080x1920`.
- All video segments should be contiguous unless the user requests gaps.
- Hook text, captions, and CTA should remain editable text layers when possible.
- Use source clips as media assets; do not bake all text into MP4 unless the user only wants rendered exports.
- Copy a cover image to `draft_cover.jpg`.
- Update `draft_info.json`, `draft_meta_info.json`, and root `root_meta_info.json` so the draft appears in the app.
- Back up existing draft JSON and root index before editing.

Root index entry must include a visible draft path, draft JSON path, cover path, name, id, root path, invisible=false, ready=true, microsecond create/modified times, and microsecond duration.

Do not edit a draft while CapCut/Jianying has it open. If the app is running, ask the user to quit it or explain that the draft box may not refresh until restart.

### 6. Optional Variant Production

When the goal is paid traffic, create variants intentionally rather than random duplicates:

- Hook A/B: pain-first vs result-first vs contradiction-first.
- Proof A/B: demo-first vs case-first vs process-first.
- Length A/B: 15s vs 30s vs 45s.
- CTA A/B: consult, trial, comment, private message, coupon, or landing-page action.
- Audience A/B: beginner, expert, business owner, operator, parent, student, etc.

Keep each variant's changed variable clear in `edit-plan.md`. Do not change hook, length, proof, CTA, and caption style all at once unless the user asks for a completely different creative direction.

When revising from user feedback, prefer targeted re-export of the affected clip or variant. Do not rerender every output unless the changed rule applies globally or the user asks for a full refresh.

Common revision cases:

- CTA removal: remove the CTA block entirely, including its background shape, instead of leaving an empty or mismatched bottom panel.
- Caption style change: update the caption renderer and inspect frames where long or two-line captions appear.
- Audio/subtitle mismatch: verify against the final compressed timeline, not the original source timeline.

### 7. Validation

Minimum validation:

- Source duration and clip output durations verified with `ffprobe`.
- First 3 seconds inspected for hook clarity.
- 9:16 crop inspected so faces, UI, subtitles, and proof are readable.
- Subtitle safe-zone and CTA placement checked visually.
- After silence removal or oral tightening, spot-check audio/subtitle sync at the beginning, middle, and end of each affected clip.
- Inspect at least one frame with a two-line caption to confirm punctuation is not visible and text stays inside the caption block.
- Draft JSON validated before opening in CapCut/Jianying.
- Final response distinguishes planned cuts, actual clips, variants, rendered videos, and installed draft path.

Use a stronger validation pass for expensive campaigns: check repeated claims, proof alignment, landing-page consistency, duplicate material fatigue, and platform-sensitive wording.

## Guardrails

- Do not treat meeting structure as the story structure.
- Do not keep setup just because it explains context; rewrite or cut to make the clip standalone.
- Do not invent performance claims, customer outcomes, prices, guarantees, qualifications, or compliance facts.
- Do not hide the product/demo behind oversized captions.
- Do not use a generic 1-second project title card unless the user explicitly wants it; for ads, the opening is part of the hook.
- Do not modify `draft_info.json`, `draft_meta_info.json`, or `root_meta_info.json` without a timestamped backup.
- Prefer the smallest reliable workflow that produces reviewable materials and an editable draft.

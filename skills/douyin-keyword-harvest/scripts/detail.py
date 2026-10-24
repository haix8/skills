#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取指定视频详情页的精确数据（点赞/评论/收藏/分享 + 发布时间 + 作者粉丝数）。

用法：
    python detail.py --dir <采集输出目录> --urls "https://www.douyin.com/video/xxx,https://..."

产出：<输出目录>/details.json

详情页节点（data-e2e）：
    video-player-digg        点赞
    feed-comment-icon        评论
    video-player-collect     收藏
    video-player-share       分享
    detail-video-publish-time 发布时间（精确到分钟）
    user-info                作者 + 粉丝数 + 获赞数
"""
import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

from _env import cdp_cmd, preflight_cdp, resolve_browser_dir

HERE = Path(__file__).resolve().parent
PROBE = HERE / "probe_video.js"

FIELDS = {
    "video-player-digg": "digg",
    "feed-comment-icon": "comment",
    "video-player-collect": "collect",
    "video-player-share": "share",
    "detail-video-publish-time": "publish",
    "user-info": "user",
    "detail-video-info": "info",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--urls", required=True, help="逗号分隔的视频链接")
    ap.add_argument("--cdp-skill", default=None, help="指定浏览器通道目录（默认用内嵌的 scripts）")
    ap.add_argument("--port", default="9222")
    ap.add_argument("--gap-min", type=float, default=12.0)
    ap.add_argument("--gap-max", type=float, default=18.0)
    args = ap.parse_args()

    out_dir = Path(args.dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    browser_dir = resolve_browser_dir(args.cdp_skill)   # 默认用内嵌副本
    cdp = cdp_cmd(browser_dir, args.port)
    preflight_cdp(browser_dir)                          # 浏览器没起就别空跑
    urls = [u.strip() for u in args.urls.split(",") if u.strip()]

    records = []
    for i, url in enumerate(urls):
        if i > 0:
            time.sleep(random.uniform(args.gap_min, args.gap_max))
        subprocess.run(cdp + ["open", url, "--wait", "30"], capture_output=True, text=True, timeout=180)
        time.sleep(random.uniform(7, 10))
        p = subprocess.run(cdp + ["eval", "--file", str(PROBE)], capture_output=True, text=True, timeout=180)
        rec = {"url": url}
        try:
            data = json.loads(p.stdout)
            e2e = data.get("e2e", {})
            for k, name in FIELDS.items():
                vals = e2e.get(k) or [""]
                rec[name] = vals[0][:400]
            rec["tags"] = data.get("tags", [])
        except Exception as e:
            rec["error"] = str(e)
        records.append(rec)
        print("%s -> 赞%s 评%s 藏%s 发布%s" % (
            url.split("/")[-1], rec.get("digg", ""), rec.get("comment", ""),
            rec.get("collect", ""), rec.get("publish", "")))

    (out_dir / "details.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print("已写出：%s" % (out_dir / "details.json"))


if __name__ == "__main__":
    main()

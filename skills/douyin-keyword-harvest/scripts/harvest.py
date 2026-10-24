#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按关键词批量采集抖音搜索结果卡片。

用法：
    python harvest.py --out <输出目录> --keywords "装修避坑,装修后悔,建材避坑"

产出：
    <输出目录>/all_items.json   机读
    <输出目录>/all_items.csv    人读

依赖 browser-automation-cdp 技能（默认 ~/.workbuddy/skills/browser-automation-cdp），
且浏览器已以调试模式常驻启动、抖音已登录。
"""
import argparse
import csv
import json
import random
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from _env import cdp_cmd, preflight_cdp, resolve_browser_dir

HERE = Path(__file__).resolve().parent
COLLECT_JS = HERE / "collect.js"


def cdp_call(cdp, args, timeout=180):
    p = subprocess.run(cdp + args, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--keywords", required=True, help="逗号分隔的关键词列表")
    ap.add_argument("--rounds", type=int, default=6, help="每个关键词向下翻页轮数，默认 6")
    ap.add_argument("--cdp-skill", default=None, help="指定浏览器通道目录（默认用内嵌的 scripts，也可传市场版技能目录）")
    ap.add_argument("--port", default="9222")
    ap.add_argument("--pause-min", type=float, default=4.5, help="翻页间隔下限（秒）")
    ap.add_argument("--pause-max", type=float, default=6.5, help="翻页间隔上限（秒）")
    ap.add_argument("--gap-min", type=float, default=9.0, help="关键词之间停顿下限（秒）")
    ap.add_argument("--gap-max", type=float, default=14.0, help="关键词之间停顿上限（秒）")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    browser_dir = resolve_browser_dir(args.cdp_skill)   # 默认用内嵌副本
    cdp = cdp_cmd(browser_dir, args.port)
    preflight_cdp(browser_dir)                          # 浏览器没起就别空跑
    print("浏览器通道：%s" % browser_dir)
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    # 复用已有结果，避免重复采集
    merged = {}
    existing = out_dir / "all_items.json"
    if existing.exists():
        try:
            for it in json.loads(existing.read_text(encoding="utf-8")):
                merged[it["href"]] = it
        except Exception:
            pass
    print("已有候选：%d" % len(merged))

    for ki, kw in enumerate(keywords):
        if ki > 0:
            time.sleep(random.uniform(args.gap_min, args.gap_max))
        url = "https://www.douyin.com/search/%s?type=video" % urllib.parse.quote(kw)
        rc, out, err = cdp_call(cdp, ["open", url, "--wait", "30"])
        if rc != 0 or '"isErrorPage": true' in out:
            print("[WARN] 打开失败：%s %s" % (kw, out[:160]))
            continue
        time.sleep(random.uniform(7, 10))

        rounds_ok = 0
        for _ in range(args.rounds):
            rc, out, err = cdp_call(cdp, ["eval", "--file", str(COLLECT_JS)])
            if rc == 0:
                try:
                    data = json.loads(out)
                    for it in data.get("items", []):
                        it["kw"] = kw
                        merged[it["href"]] = it
                    if data.get("count", 0) > 0:
                        rounds_ok += 1
                except Exception:
                    pass
            time.sleep(random.uniform(args.pause_min, args.pause_max))

        flag = "" if rounds_ok else "   <<< 抓到 0 条，多半被人机验证拦了，先让用户手动过验证"
        print("[OK] %-12s 有效翻页 %d/%d 轮，累计 %d%s" % (kw, rounds_ok, args.rounds, len(merged), flag))

    items = list(merged.values())
    (out_dir / "all_items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out_dir / "all_items.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["kw", "likes", "date", "dur", "author", "desc", "href"])
        w.writeheader()
        for it in items:
            w.writerow({k: it.get(k, "") for k in w.fieldnames})
    print("总计去重候选：%d -> %s" % (len(items), out_dir))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 all_items.json 按「近 N 天 + 点赞数」筛选排序。

用法：
    python rank.py --dir <采集输出目录> [--days 92] [--top 40]
"""
import argparse
import json
import re
from pathlib import Path


def parse_likes(s):
    """'2.6万' -> 26000；'797' -> 797；'1.2亿' -> 120000000"""
    m = re.match(r"^([\d.]+)(万|亿)?$", (s or "").strip())
    if not m:
        return 0
    v = float(m.group(1))
    return int(v * {"万": 10000, "亿": 100000000}.get(m.group(2), 1))


def parse_age_days(s):
    """'3天前'/'2周前'/'1月前' -> 天数。注意这是区间下限估计，用于卡时间范围足够。"""
    s = (s or "").strip()
    if s in ("刚刚", "今天", "昨天", "前天"):
        return {"刚刚": 0, "今天": 0, "昨天": 1, "前天": 2}[s]
    m = re.match(r"^(\d+)(分钟|小时|天|周|月|年)前$", s)
    if not m:
        return None
    n = int(m.group(1))
    return n * {"分钟": 1 / 1440, "小时": 1 / 24, "天": 1, "周": 7, "月": 30, "年": 365}[m.group(2)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="harvest.py 的输出目录")
    ap.add_argument("--days", type=float, default=92, help="时间范围天数，默认 92（约 3 个月）")
    ap.add_argument("--top", type=int, default=40, help="打印条数")
    args = ap.parse_args()

    d = Path(args.dir)
    items = json.loads((d / "all_items.json").read_text(encoding="utf-8"))
    for it in items:
        it["like_n"] = parse_likes(it.get("likes"))
        it["age_days"] = parse_age_days(it.get("date"))
    recent = [it for it in items if it["age_days"] is not None and it["age_days"] <= args.days]
    recent.sort(key=lambda x: -x["like_n"])
    (d / "ranked.json").write_text(json.dumps(recent, ensure_ascii=False, indent=1), encoding="utf-8")

    print("候选总数 %d ；近 %g 天内 %d" % (len(items), args.days, len(recent)))
    print("-" * 96)
    for i, it in enumerate(recent[: args.top], 1):
        print("%3d|%8s|%7s| %-16s| %s" % (i, it["likes"], it["date"], it["author"][:16], it["desc"][:56]))
    print("-" * 96)
    print("已写出：%s" % (d / "ranked.json"))


if __name__ == "__main__":
    main()

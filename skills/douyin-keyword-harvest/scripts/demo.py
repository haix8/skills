#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""demo.py —— 用内置样本数据演示完整产出格式。

用途：在没有浏览器、未登录抖音、或不便触发人机验证的环境中，
验证本技能的三步流程与产出结构，不会访问网络。

用法：
    python scripts/demo.py --out <输出目录>
    python scripts/rank.py --dir <输出目录> --days 92    # 第 2 步可正常处理演示数据

产出：
    <输出目录>/all_items.json   第 1 步格式（含 20 条样本）
    <输出目录>/all_items.csv    第 1 步 CSV
    <输出目录>/details.json     第 3 步格式（样本中带精确数据的条目）

退出码：0 成功；1 样本文件缺失或损坏。
"""

import argparse
import csv
import json
import sys
from pathlib import Path

SAMPLE = Path(__file__).resolve().parent / "demo_data.json"
FIELDS = ["href", "dur", "likes", "desc", "author", "date", "coll", "kw"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="demo.py", description="用内置样本演示产出格式（不访问网络）")
    parser.add_argument("--out", required=True, help="输出目录")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not SAMPLE.exists():
        print("错误：样本文件缺失：%s" % SAMPLE, file=sys.stderr)
        return 1
    try:
        data = json.loads(SAMPLE.read_text(encoding="utf-8"))
        items = data.get("items") or []
    except (json.JSONDecodeError, OSError) as exc:
        print("错误：样本文件解析失败：%s" % exc, file=sys.stderr)
        return 1

    if not items:
        print("错误：样本为空", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    records = [{k: it.get(k, "") for k in FIELDS} for it in items]
    for r in records:
        r["coll"] = bool(r.get("coll"))

    (out / "all_items.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")

    with open(out / "all_items.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(records)

    details = []
    for it in items:
        d = it.get("detail")
        if not d:
            continue
        details.append({
            "url": it["href"],
            "digg": d.get("digg"),
            "comment": d.get("comment"),
            "collect": d.get("collect"),
            "share": d.get("share"),
            "publish": "发布时间：%s" % d.get("publish", ""),
            "user": d.get("user"),
            "tags": d.get("tags"),
            "info": it.get("desc", ""),
        })
    (out / "details.json").write_text(
        json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")

    print("已写入演示数据（不访问网络）：%s" % out)
    print("  all_items.json / all_items.csv    %d 条" % len(records))
    print("  details.json                      %d 条（含精确发布时间与互动数据）" % len(details))
    print()
    print("下一步可用第 2 步处理该目录：")
    print("  python scripts/rank.py --dir %s --days 92" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

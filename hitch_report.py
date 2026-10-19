#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺风车数据汇总报表
==================
把工作目录下所有 hitchList-*.json / hitch-all.json / hitch-snapshot.json
里的车源合并、按 hitchId 去重，输出可读清单。

用法
----
  python hitch_report.py                # 打印前 30 条
  python hitch_report.py --top 50
  python hitch_report.py --save         # 同时落盘 outputs/顺风车_汇总_*.txt
"""

import argparse
import glob
import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "outputs")


def collect():
    items, seen = [], set()
    pats = ["hitchList-*.json", "hitch-all.json", "hitch-snapshot.json"]
    for pat in pats:
        for f in glob.glob(os.path.join(HERE, pat)):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            lst = []
            if isinstance(d, dict):
                if "items" in d:                       # hitch-all / snapshot
                    lst = d["items"] or []
                else:
                    lst = (d.get("content") or {}).get("hitchList") or []
            for it in lst:
                hid = str(it.get("hitchId"))
                if hid in seen:
                    continue
                seen.add(hid)
                items.append(it)
    return items


def line(it):
    return "%-14s %-6s元  %-6s → %-6s  %s ~ %s  %s天  id=%s" % (
        (it.get("modelName") or "?")[:14], it.get("realTotalPrice", "?"),
        it.get("pickupCityName", "?"), it.get("returnCityName", "?"),
        it.get("beginDate", "?"), it.get("endDate", "?"),
        it.get("limitTenancyDay", "?"), it.get("hitchId", "?"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()

    items = collect()
    if not items:
        print("没找到数据文件")
        return 1

    items.sort(key=lambda x: (str(x.get("beginDate") or ""), x.get("hitchId") or 0))

    head = "神州顺风车车源汇总  %s ｜ 共 %d 条（去重后）" % (
        datetime.now().strftime("%Y-%m-%d %H:%M"), len(items))
    body = "\n".join(line(it) for it in items)

    print(head)
    print("-" * 96)
    print("\n".join(line(it) for it in items[:a.top]))
    if len(items) > a.top:
        print("... 其余 %d 条见落盘文件" % (len(items) - a.top))

    if a.save:
        os.makedirs(OUTDIR, exist_ok=True)
        fn = os.path.join(OUTDIR, "顺风车_汇总_%s.txt" % datetime.now().strftime("%Y%m%d_%H%M"))
        with open(fn, "w", encoding="utf-8") as f:
            f.write(head + "\n" + "=" * 96 + "\n" + body + "\n")
        print("\n-> %s" % fn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

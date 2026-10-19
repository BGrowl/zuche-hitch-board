#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺风车全量快照（慢速 + 断点续传）
=================================
服务端限流约 6~8 请求/10 分钟量级，所以全量不能一把梭。
本脚本每页之间留长间隔，撞限流就长睡重试，进度落盘可续传。

用法
----
  python hitch_snapshot.py                 # 默认 gap=120s，抓完
  python hitch_snapshot.py --gap 90
  python hitch_snapshot.py --pages 3       # 只抓前 3 页
  python hitch_snapshot.py --status        # 看进度
  python hitch_snapshot.py --merge         # 仅把已有进度合并成 hitch-all.json

产物
----
  snapshot-state.json   逐页进度（可续传）
  hitch-all.json        合并后的全量
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hitch_api as H

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "snapshot-state.json")
OUT = os.path.join(HERE, "hitch-all.json")
PS = 200
COOLDOWN = 900          # 撞限流后睡多久再试（要够长，否则等于一直给风控"续杯"）


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    return {"pages": {}, "total": None, "startedAt": None, "updatedAt": None}


def save_state(st):
    st["updatedAt"] = datetime.now().isoformat()
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def detect_ps(st):
    """试出服务端接受的每页上限，尽量少发请求"""
    if st.get("ps"):
        return st["ps"]
    for want in (500, 400, 300, 200):
        while True:
            d = H.hitch_list(1, want, 1)
            if H.is_ratelimited(d):
                log("探测 pageSize=%d 时限流 → 睡 %d 秒" % (want, COOLDOWN))
                time.sleep(COOLDOWN)
                continue
            break
        if not H.ok(d):
            log("探测 pageSize=%d 失败：%s" % (want, d.get("msg")))
            continue
        got = len((d.get("content") or {}).get("hitchList") or [])
        if got > 0:
            log("pageSize 上限 = %d（请求 %d 返回 %d）" % (want, want, got))
            st["ps"] = want
            st["pages"] = {}          # 换了页大小，之前按别的页大小抓的要废弃
            save_state(st)
            return want
    return PS


def merge(st):
    items, seen = [], set()
    for pn in sorted(st["pages"], key=int):
        for it in st["pages"][pn]:
            hid = str(it.get("hitchId"))
            if hid not in seen:
                seen.add(hid)
                items.append(it)
    json.dump({"count": st.get("total"), "items": items,
               "fetchedAt": datetime.now().isoformat()},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=int, default=240, help="页间隔秒数")
    ap.add_argument("--pages", type=int, default=0, help="最多抓几页（0=抓完）")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="丢弃进度重来")
    ap.add_argument("--wait", type=int, default=0, help="先静默等待 N 秒再开始")
    a = ap.parse_args()

    st = {"pages": {}, "total": None, "startedAt": None, "updatedAt": None} if a.fresh else load_state()

    if a.status:
        got = sum(len(v) for v in st["pages"].values())
        print("已抓页数 %d，条数 %d，服务端总数 %s"
              % (len(st["pages"]), got, st.get("total")))
        print("页: %s" % sorted(st["pages"], key=int))
        print("pageSize: %s  开始 %s  更新 %s"
              % (st.get("ps"), st.get("startedAt"), st.get("updatedAt")))
        return 0

    if a.merge:
        items = merge(st)
        print("合并 %d 条 -> %s" % (len(items), OUT))
        return 0

    if a.wait:
        log("静默等待 %d 秒（让限流彻底冷却）…" % a.wait)
        time.sleep(a.wait)

    if st.get("startedAt") is None:
        st["startedAt"] = datetime.now().isoformat()
        log("开始全量快照")

    ps = detect_ps(st)
    log("页大小 %d，页间隔 %d 秒" % (ps, a.gap))

    pn = 1
    while True:
        if a.pages and pn > a.pages:
            break
        while str(pn) in st["pages"]:
            pn += 1

        while True:
            d = H.hitch_list(pn, ps, 1)
            if H.is_ratelimited(d):
                log("第 %d 页限流 → 睡 %d 秒" % (pn, COOLDOWN))
                time.sleep(COOLDOWN)
                continue
            break

        if not H.ok(d):
            log("第 %d 页失败：%s" % (pn, d.get("msg")))
            break

        c = d["content"]
        st["total"] = c.get("count")
        lst = c.get("hitchList") or []
        st["pages"][str(pn)] = lst
        save_state(st)
        log("第 %d 页 %d 条（累计 %d / %s）"
            % (pn, len(lst), sum(len(v) for v in st["pages"].values()), st["total"]))

        if len(lst) < ps:
            break
        pn += 1
        if not (a.pages and pn > a.pages):
            time.sleep(a.gap)

    items = merge(st)
    log("完成：%d 条 -> %s" % (len(items), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())

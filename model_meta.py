#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神州租车 车型元数据抓取（官方分类）
====================================
数据源：POST m.zuche.com/api/gw.do?uri=/action/carrctapi/order/modelInfo/v7
        data = {"modelId": "1395"}          # 免登录

返回的 baseConfigList 里有官方分类字段：
    结构/座位   ->  如 "三厢轿车 5座" / "MPV 7座" / "SUV 5座"
    能源类型    ->  如 "汽油" / "插电混" / "纯电"

本脚本对 hitch-all.json 里出现的所有 modelId 逐个抓取，
产出 model-meta.json：{ modelId: {name, body, seats, energy, disp, raw} }

特点：断点续传（已抓过的跳过）、自动限流退避、可配间隔。

用法
----
  python model_meta.py                 # 抓全部缺的
  python model_meta.py --gap 3         # 请求间隔 3 秒
  python model_meta.py --status        # 看进度
  python model_meta.py --show          # 打印已抓到的分类
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ALL = os.path.join(HERE, "hitch-all.json")
OUT = os.path.join(HERE, "model-meta.json")

sys.path.insert(0, HERE)
import hitch_api as H  # noqa: E402

COOLDOWN = 600          # 撞限流后的冷却秒数


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def load():
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save(d):
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def parse_cfg(cfg_list):
    """从 baseConfigList 提取 结构/座位、能源类型、排量/排挡"""
    body, seats, energy, disp = "", "", "", ""
    for it in (cfg_list or []):
        name = (it.get("name") or "").strip()
        val = (it.get("value") or "").strip()
        if name == "结构/座位":
            # 形如 "三厢轿车 5座" / "MPV 7座" / "SUV 5座"
            parts = val.split()
            if len(parts) >= 2 and parts[-1].endswith("座"):
                body = " ".join(parts[:-1]).strip()
                seats = parts[-1]
            else:
                body = val
        elif name == "能源类型":
            energy = val
        elif name == "排量/排挡":
            disp = val
    return body, seats, energy, disp


def fetch(mid):
    d = H.gw("/action/carrctapi/order/modelInfo/v7", {"modelId": str(mid)})
    if H.is_ratelimited(d):
        return None, "ratelimit"
    if not H.ok(d):
        return None, d.get("msg") or "fail"
    c = d.get("content") or {}
    body, seats, energy, disp = parse_cfg(c.get("baseConfigList"))
    return {
        "name": c.get("modelName") or "",
        "body": body,          # 车身类型：轿车 / SUV / MPV ...
        "seats": seats,        # 5座 / 7座 ...
        "energy": energy,      # 汽油 / 插电混 / 纯电 ...
        "disp": disp,          # 1.5 自动 ...
    }, "ok"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=float, default=4.0, help="请求间隔秒")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args(argv[1:])

    meta = load()

    if a.show:
        for mid, m in sorted(meta.items(), key=lambda kv: kv[1].get("body", "")):
            print("%-6s %-16s %-10s %-5s %-6s %s"
                  % (mid, m.get("name"), m.get("body"), m.get("seats"),
                     m.get("energy"), m.get("disp")))
        return 0

    # 目标 modelId 集合
    allj = json.load(open(ALL, encoding="utf-8"))
    ids, names = set(), {}
    for x in allj["items"]:
        mid = str(x.get("modelId"))
        ids.add(mid)
        names.setdefault(mid, x.get("modelName"))

    todo = [m for m in ids if m not in meta]
    if a.status:
        print("总车型 %d，已抓 %d，待抓 %d" % (len(ids), len(meta), len(todo)))
        print("待抓: %s" % sorted(todo))
        return 0

    log("总车型 %d，已抓 %d，待抓 %d" % (len(ids), len(meta), len(todo)))
    done = 0
    for mid in sorted(todo, key=lambda m: int(m)):
        # 已在上一轮抓到就跳过（防并发/重复）
        if mid in meta:
            continue
        while True:
            data, st = fetch(mid)
            if st == "ratelimit":
                log("限流 → 冷却 %d 秒" % COOLDOWN)
                time.sleep(COOLDOWN)
                continue
            break
        if st == "ok":
            meta[mid] = data
            save(meta)
            done += 1
            log("%-6s %-16s %-10s %-5s %-6s" % (mid, data["name"], data["body"],
                                                data["seats"], data["energy"]))
        else:
            log("%-6s 失败: %s" % (mid, st))
            meta[mid] = {"name": names.get(mid, ""), "body": "", "seats": "",
                         "energy": "", "disp": "", "error": st}
            save(meta)
        time.sleep(a.gap)

    log("完成，本轮新增 %d 个，共 %d 个 -> %s" % (done, len(meta), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

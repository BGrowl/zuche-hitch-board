#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每半小时一轮：抓全量 → 更新快照 / 线上数据 → 产出新增清单
==========================================================
给定时任务调用。一轮的完整动作：

  1. 匿名抓取全量顺风车车源（pageSize=500，页间隔 12s，约 5 个请求）
  2. 与上一轮的 id 集合对比，算出**新增**车源
  3. 更新 hitch-all.json（本地全量快照）
  4. 更新 hitch-site/data.json（在线看板的数据源，含 newIds）
  5. 重新生成本地可浏览的 顺风车车源.html
  6. 有新增时写 outputs/顺风车_新增_*.txt，并把清单打印出来

用法
----
  python refresh.py                 # 跑一轮
  python refresh.py --quiet         # 不打印明细
  python refresh.py --max-price 1   # 只把 ≤1 元的算作"值得推送"
  python refresh.py --city 贵阳,南宁
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hitch_api as H                                            # noqa: E402
from car_class import classify, by_name_index, meta_for          # noqa: E402
from car_rank import score as rank_of                             # noqa: E402

ALL = os.path.join(HERE, "hitch-all.json")
SITE = os.path.join(HERE, "hitch-site")
DATA = os.path.join(SITE, "data.json")
META = os.path.join(HERE, "model-meta.json")
META_SITE = os.path.join(SITE, "model-meta.json")
OUTDIR = os.path.join(HERE, "outputs")


def load_meta():
    """官方车型分类表：modelId -> {name, body(车身类型), seats, energy, disp}"""
    for p in (META, META_SITE):
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                pass
    return {}

PS = 500          # 服务端接受的上限
GAP = 12          # 页间隔秒
MAX_PAGES = 24


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def fetch_all():
    """翻页抓全量。返回 (items, total, error)"""
    items, total = [], None
    for pn in range(1, MAX_PAGES + 1):
        d = H.hitch_list(pn, PS, 1)
        if H.is_ratelimited(d):
            return items, total, "服务端限流：%s" % d.get("msg")
        if not H.ok(d):
            return items, total, "第 %d 页失败：code=%s msg=%s" % (pn, d.get("code"), d.get("msg"))
        c = d.get("content") or {}
        if c.get("count") is not None:
            total = c["count"]
        lst = c.get("hitchList") or []
        if not lst:
            break
        items.extend(lst)
        log("  第 %d 页 %d 条（累计 %d）" % (pn, len(lst), len(items)))
        if len(lst) < PS:
            break
        time.sleep(GAP)
    return items, total, None


def slim(it, meta=None, by_name=None):
    m = meta_for(it.get("modelId"), it.get("modelName"), meta, by_name)
    name = it.get("modelName") or ""
    return {
        "id": str(it.get("hitchId") or ""),
        "model": name,
        "cls": classify(name, m.get("energy"), m.get("body")),  # 新能源/高端车/普通车
        "rank": rank_of(name, m.get("body") or ""),             # 档次分：同类别内越大越靠前
        "body": m.get("body") or "",       # 官方车身类型：轿车 / SUV / MPV ...
        "seats": m.get("seats") or "",     # 5座 / 7座 ...
        "energy": m.get("energy") or "",   # 汽油 / 插电混 / 纯电 ...
        "price": str(it.get("realTotalPrice") if it.get("realTotalPrice") is not None else ""),
        "est": str(it.get("estTotalPrice") if it.get("estTotalPrice") is not None else ""),
        "from": it.get("pickupCityName") or "",
        "to": it.get("returnCityName") or "",
        "bd": it.get("beginDate") or "",
        "ed": it.get("endDate") or "",
        "days": it.get("limitTenancyDay") or "",
    }


def load_prev_ids():
    """上一轮见过的 hitchId 集合：优先 data.json，其次退回 hitch-all.json"""
    if os.path.exists(DATA):
        try:
            j = json.load(open(DATA, encoding="utf-8"))
            ids = {x.get("id") for x in (j.get("items") or []) if x.get("id")}
            if ids:
                return ids
        except Exception:
            pass
    if os.path.exists(ALL):
        try:
            j = json.load(open(ALL, encoding="utf-8"))
            return {str(x.get("hitchId")) for x in (j.get("items") or []) if x.get("hitchId")}
        except Exception:
            pass
    return set()


def fmt(r):
    est = ("  原价¥%s" % r["est"]) if r.get("est") and r["est"] != r.get("price") else ""
    cls = r.get("cls") or ""
    if r.get("body"):
        cls = (cls + "·" + r["body"]) if cls else r["body"]
    cls = ("[%s]" % cls) if cls else ""
    return "%-12s %-10s ¥%-5s%s  %-6s → %-6s  %s~%s  %s天  id=%s" % (
        (r["model"] or "?")[:12], cls, r["price"], est, r["from"], r["to"],
        r["bd"], r["ed"], r["days"], r["id"])


def match(r, cities, max_price):
    if cities and not any(c in (r.get("from") or "") for c in cities):
        return False
    if max_price is not None:
        try:
            if float(r.get("price") or 1e9) > max_price:
                return False
        except ValueError:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--city", default="")
    ap.add_argument("--max-price", type=float, default=None)
    a = ap.parse_args()
    cities = [c.strip() for c in a.city.split(",") if c.strip()] or None

    log("抓取全量车源…")
    items, total, err = fetch_all()
    if err or not items:
        log("本轮抓取失败：%s（保留旧数据不覆盖）" % (err or "空结果"))
        return 1

    meta = load_meta()
    by_name = by_name_index(meta)
    rows = [slim(x, meta, by_name) for x in items]
    unknown = sorted({str(x.get("modelId")) for x in items
                      if x.get("modelId") is not None and str(x.get("modelId")) not in meta})
    if unknown:
        log("⚠️ %d 个车型尚无官方分类（跑 model_meta.py 可补）：%s"
            % (len(unknown), ",".join(unknown[:12])))
    old_ids = load_prev_ids()
    cur_ids = {r["id"] for r in rows if r["id"]}
    first = not old_ids
    new_ids = [] if first else sorted(cur_ids - old_ids, reverse=True)
    gone = len(old_ids - cur_ids) if old_ids else 0

    now_ms = int(time.time() * 1000)

    # 1) 本地全量快照
    json.dump({"count": total, "items": items}, open(ALL, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 2) 在线看板的数据源
    os.makedirs(SITE, exist_ok=True)
    # 官方车型分类表同步到站点目录（服务端 slim 时要用）
    if os.path.exists(META):
        try:
            import shutil
            shutil.copyfile(META, META_SITE)
        except Exception as exc:                                 # noqa: BLE001
            log("model-meta.json 同步失败：%s" % exc)
    payload = {
        "updatedAt": now_ms, "total": total, "count": len(rows),
        "newIds": new_ids, "error": None, "source": "m.zuche.com",
        "items": rows,
    }
    tmp = DATA + ".tmp"
    json.dump(payload, open(tmp, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, DATA)

    # 3) 本地可浏览页
    try:
        from make_html import main as gen_html
        gen_html()
    except Exception as exc:                                     # noqa: BLE001
        log("本地 HTML 生成失败：%s" % exc)

    log("全量 %d 条（服务端总数 %s）｜新增 %d ｜下架 %d"
        % (len(rows), total, len(new_ids), gone))

    if first:
        log("首次建立基线，不报新增")
        return 0
    if not new_ids:
        log("无新增")
        return 0

    new_rows = [r for r in rows if r["id"] in set(new_ids)]
    hits = [r for r in new_rows if match(r, cities, a.max_price)]
    os.makedirs(OUTDIR, exist_ok=True)
    fn = os.path.join(OUTDIR, "顺风车_新增_%s.txt" % datetime.now().strftime("%Y%m%d_%H%M"))
    with open(fn, "w", encoding="utf-8") as f:
        f.write("神州顺风车新增车源  %s\n" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        f.write("服务端总数 %s ｜ 本轮新增 %d 条 ｜ 过滤后 %d 条\n"
                % (total, len(new_rows), len(hits)))
        f.write("=" * 96 + "\n")
        for r in hits:
            f.write(fmt(r) + "\n")

    log("★ 新增 %d 条（过滤后 %d 条）→ %s" % (len(new_rows), len(hits), fn))
    if not a.quiet:
        for r in hits:
            print("    " + fmt(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

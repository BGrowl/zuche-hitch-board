#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性工具：把 data.json 里出现的城市批量地理编码成经纬度，写入 city-geo.json。

用 OpenStreetMap Nominatim 公共接口，遵守其使用政策：每秒最多 1 次请求。
结果永久缓存，之后 geo.py 完全离线计算距离，运行期不再访问网络。

⚠️ 关键点：**不要**用 featureType=city 过滤。
   上海的行政类型是 state（直辖市），加了该过滤会把它排除、转而命中青海一个叫
   「上海」的小地方（实测坐标 97.888,35.9947，完全错）。正确做法是取多条候选，
   按「名称完全匹配 → 行政级别 → importance」排序。

用法：
    python fetch_city_geo.py [--force]
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
OUT = os.path.join(HERE, "city-geo.json")
LOG = os.path.join(HERE, "city-geo-audit.txt")
UA = "zuche-hitch-board/1.0 (personal project; contact via GitHub issues)"
INTERVAL = 1.1                     # 秒，Nominatim 政策要求 <= 1 次/秒
SUFFIX = ("市", "地区", "盟", "自治州", "县", "区", "新区", "林区", "特别行政区")

# 行政级别优先级：数值越大越可信
TYPE_PRI = {"state": 4, "city": 4, "administrative": 3, "county": 2, "town": 1, "village": 0}

# 中国经纬度范围，用于兜底校验
LON_MIN, LON_MAX = 73.0, 136.0
LAT_MIN, LAT_MAX = 17.0, 54.5


def norm(name):
    n = (name or "").strip()
    for s in SUFFIX:
        if len(n) > len(s) + 1 and n.endswith(s):
            return n[: -len(s)]
    return n


def ask(q):
    params = {"q": q, "format": "jsonv2", "limit": 6, "countrycodes": "cn",
              "accept-language": "zh", "addressdetails": 1}
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:                               # noqa: BLE001
        print("   请求失败 %s: %s" % (q, exc))
        return []


def pick(cands, base):
    """在候选里挑名称匹配、行政级别最高的一个。"""
    best, best_key = None, None
    for x in cands or []:
        if norm(x.get("name") or "") != base:
            continue
        try:
            imp = float(x.get("importance") or 0)
        except Exception:                                  # noqa: BLE001
            imp = 0.0
        key = (TYPE_PRI.get(x.get("addresstype") or "", 0), imp)
        if best_key is None or key > best_key:
            best, best_key = x, key
    return best


def geocode(name):
    base = norm(name)
    for q in ("%s, 中国" % base, "%s市, 中国" % base):
        x = pick(ask(q), base)
        if x:
            try:
                lon, lat = float(x["lon"]), float(x["lat"])
            except Exception:                              # noqa: BLE001
                continue
            return [round(lon, 4), round(lat, 4)], (x.get("display_name") or "")[:70]
        time.sleep(INTERVAL)
    return None, ""


def main():
    force = "--force" in sys.argv
    rows = json.load(open(DATA, encoding="utf-8")).get("items") or []
    cities = sorted({c for r in rows for c in (r.get("from"), r.get("to")) if c})
    geo = {}
    if os.path.exists(OUT) and not force:
        geo = json.load(open(OUT, encoding="utf-8"))
    todo = [c for c in cities if c not in geo]
    print("共 %d 个城市，已有 %d，待抓 %d" % (len(cities), len(geo), len(todo)))

    audit, miss = [], []
    for i, c in enumerate(todo, 1):
        pos, disp = geocode(c)
        if pos:
            geo[c] = pos
            audit.append("%-8s %-22s %s" % (c, pos, disp))
        else:
            miss.append(c)
        if i % 20 == 0 or i == len(todo):
            json.dump(geo, open(OUT, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=0, sort_keys=True)
            with open(LOG, "w", encoding="utf-8") as f:
                f.write("\n".join(audit))
            print("  进度 %d/%d，已解析 %d，未解析 %d" % (i, len(todo), len(geo), len(miss)))
        time.sleep(INTERVAL)

    # 校验：范围 + 重复坐标（重复通常意味着匹配错了）
    bad = {k: v for k, v in geo.items()
           if not (LON_MIN <= v[0] <= LON_MAX and LAT_MIN <= v[1] <= LAT_MAX)}
    seen, dup = {}, []
    for k, v in geo.items():
        key = (v[0], v[1])
        if key in seen:
            dup.append((seen[key], k, v))
        else:
            seen[key] = k

    print("\n完成：%d/%d 有坐标" % (len(geo), len(cities)))
    if bad:
        print("坐标越界（需手工修）:", bad)
    if dup:
        print("坐标重复（可疑）:")
        for a, b, v in dup[:15]:
            print("   %s 与 %s 同为 %s" % (a, b, v))
    if miss:
        print("未解析（需手工补）:", "、".join(miss))
    print("明细见", LOG)


if __name__ == "__main__":
    main()

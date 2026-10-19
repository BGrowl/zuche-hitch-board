# -*- coding: utf-8 -*-
"""城市间**驾车里程**：OSRM 路由 + 本地缓存。

与 geo.py 的区别
----------------
geo.py  算的是球面直线距离，零网络、但偏小（跨城约为驾车的 0.7~0.8）。
本模块算的是**真实道路里程**，需要请求路由服务，因此**必须缓存**：

- `route-cache.json` 存 "起点|终点" → 公里数，算过就不会再请求；
- `get()` 只读缓存，**不做网络请求**，供 server.py 在渲染数据时调用；
- `fill_missing()` 负责在后台慢慢补齐缺的对，带限速与熔断。

数据来源：OSRM（OpenStreetMap 路网）。
服务地址：官方 demo 优先，失败自动切 FOSSGIS 实例，两个都是同一份 OSM 数据、结果一致。
"""
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "route-cache.json")
UA = "zuche-hitch-board/1.0 (personal project; contact via GitHub issues)"

HOSTS = (
    "router.project-osrm.org",
    "routing.openstreetmap.de/routed-car",
)
TIMEOUT = 8          # 单次请求超时（秒）——别太长，避免把刷新线程拖死
GAP = 0.8            # 两次请求间隔（秒），对公共实例保持礼貌
BREAK_AFTER = 3      # 连续失败几次就放弃本轮（多半是网络/限流，硬扛没意义）

_CACHE = {}
_last_call = 0.0

try:
    with open(CACHE_FILE, encoding="utf-8") as f:
        _CACHE = json.load(f)
except Exception:                                          # noqa: BLE001
    _CACHE = {}


def key(a, b):
    return "%s|%s" % ((a or "").strip(), (b or "").strip())


def get(a, b):
    """只读缓存：有驾车里程就返回 int km，否则 None。**不联网。**"""
    v = _CACHE.get(key(a, b))
    try:
        return int(v) if v is not None else None
    except Exception:                                      # noqa: BLE001
        return None


def known():
    return len(_CACHE)


def save():
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_CACHE, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, CACHE_FILE)


def _sleep():
    """全局限速。"""
    global _last_call
    dt = time.time() - _last_call
    if dt < GAP:
        time.sleep(GAP - dt)
    _last_call = time.time()


def query(a, b):
    """问一次 OSRM 拿驾车里程（km）。失败返回 None。"""
    try:
        import geo
        pa, pb = geo.coord(a), geo.coord(b)
    except Exception:                                      # noqa: BLE001
        return None
    if not pa or not pb:
        return None
    if pa == pb:
        return 0
    path = "%s/route/v1/driving/%.4f,%.4f;%.4f,%.4f?overview=false&alternatives=false" % (
        "%s", pa[0], pa[1], pb[0], pb[1])
    for host in HOSTS:
        url = "https://" + (path % host)
        _sleep()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("code") == "Ok" and d.get("routes"):
                return int(round(d["routes"][0]["distance"] / 1000.0))
        except Exception:                                  # noqa: BLE001
            continue
    return None


def fill_missing(pairs, limit=0, log=print):
    """补齐缓存里没有的城市对。

    pairs: [(from, to), ...] 任意可迭代
    limit: 本轮最多算多少对（0=不限）；server.py 用它控制每轮耗时
    返回本轮新算出的条数。
    """
    todo = []
    seen = set()
    for a, b in pairs:
        if not a or not b:
            continue
        k = key(a, b)
        if k in _CACHE or k in seen:
            continue
        seen.add(k)
        todo.append((a, b))
    if limit:
        todo = todo[:limit]
    if not todo:
        return 0

    got, fails = 0, 0
    for i, (a, b) in enumerate(todo, 1):
        km = query(a, b)
        if km is None:
            fails += 1
            if fails >= BREAK_AFTER:
                log("  驾车里程：连续 %d 次失败，本轮停止（网络或限流）" % fails)
                break
            continue
        fails = 0
        _CACHE[key(a, b)] = km
        got += 1
        if got % 20 == 0:
            save()
            log("  驾车里程：本轮已补 %d/%d" % (got, len(todo)))
    if got:
        save()
    return got

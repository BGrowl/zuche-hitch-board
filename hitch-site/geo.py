# -*- coding: utf-8 -*-
"""城市间距离：经纬度查表 + 半正矢公式。

数据来自 city-geo.json（由 fetch_city_geo.py 一次性抓取并缓存），
运行期**不访问网络**，纯本地计算，毫秒级。

坐标数据来源：OpenStreetMap 贡献者，遵循 ODbL 许可
（https://www.openstreetmap.org/copyright）。若分发本项目，请保留此署名。

口径说明
--------
算的是两个城市中心点之间的**球面直线距离（大圆距离）**，不是驾车里程。
中国境内跨城驾车里程通常是直线距离的 1.2~1.4 倍。
页面上明确标注「直线」，避免误导。
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GEO_FILE = os.path.join(HERE, "city-geo.json")

# 城市名后缀：查表时逐一剥离，兼容「杭州」「杭州市」两种写法
_SUFFIX = ("市", "地区", "盟", "自治州", "县", "区", "新区", "林区", "特别行政区")

_GEO = {}
try:
    with open(GEO_FILE, encoding="utf-8") as f:
        _GEO = json.load(f)
except Exception:                                          # noqa: BLE001
    _GEO = {}

EARTH_R = 6371.0088          # 地球平均半径（km）


def _candidates(name):
    """由粗到细给出可能的查表键。"""
    n = (name or "").strip()
    if not n:
        return []
    out = [n]
    for s in _SUFFIX:
        if len(n) > len(s) + 1 and n.endswith(s):
            out.append(n[: -len(s)])
    return out


def coord(name):
    """城市名 → (lon, lat)；查不到返回 None。"""
    for k in _candidates(name):
        p = _GEO.get(k)
        if p and len(p) == 2:
            return float(p[0]), float(p[1])
    return None


def haversine(p1, p2):
    """两点球面距离，单位 km。p = (lon, lat)。"""
    lon1, lat1 = map(math.radians, p1)
    lon2, lat2 = map(math.radians, p2)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def distance(city_a, city_b):
    """两城市直线距离（km，整数）；任一城市无坐标时返回 None。"""
    pa, pb = coord(city_a), coord(city_b)
    if not pa or not pb:
        return None
    km = haversine(pa, pb)
    if km < 1:                       # 同城（取还车同地）不显示距离
        return 0
    return int(round(km))


def known():
    """已有坐标的城市数，便于自检。"""
    return len(_GEO)

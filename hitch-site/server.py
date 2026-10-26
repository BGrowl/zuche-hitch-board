#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神州顺风车 · 车源在线看板（服务端）
====================================
一个自包含的单端口 HTTP 服务，发布到公网后手机可直接访问。

设计要点
--------
· 启动时先读同目录的 data.json（随包发布的最新快照）→ 保证一上线就有数据。
· 后台线程每 REFRESH_SEC（默认 600 秒 = 10 分钟）自动抓一轮全量并刷新页面数据。
  → 链接发布一次即可长期使用，不需要反复重新发布。
· **云端推送**：抓到的「新增」里档次为金/银/铜（rank ≥ 70）的车源推到手机。
  **两条腿并行**（见 push.py 的 pushImmediate / push_every_sec）：
    · 即时推送 —— 每轮一出现达标新车就立刻推一条「新增 N 台好车」（= 每 10 分钟一条）；
    · 小时汇总 —— 同一批车攒进 push-state.json 的 pendingIds，满 1 小时再推一条
      「近 1 小时汇总 N 台好车」，一眼看全这一小时。两条腿内容有重叠，是有意设计。
  优先走「**企业微信群机器人**」（**text 纯文本**，一台车一行、全部新增列完、不用点链接；
  用 text 而非 markdown 是因为企业微信「微信插件」不支持 markdown，用 markdown 在个人微信里
  只会显示"暂不支持此消息类型"）。免实名、不限量、不校验 IP 白名单。其次是微信测试号 /
  PushPlus / WxPusher。整个过程跑在云沙箱，**不需要用户电脑开机**（见同目录 push.py）。
· 抓取失败**不清空**旧数据，只在页面顶部提示"数据可能不是最新"（降级安全）。
· 只依赖 Python 标准库，发布沙箱无需安装任何第三方包。

路由
----
  GET /            页面
  GET /data.json   数据（页面每 2 分钟自动拉一次）
  GET /health      运行状态

⚠️ 抓取一律**匿名**（不带 cookie）：实测带登录会话会被服务端按会话限流，
   而不带 cookie 的匿名请求畅通无阻。hitchList 本身免登录。
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "data.json")
PAGE_FILE = os.path.join(HERE, "page.html")
META_FILE = os.path.join(HERE, "model-meta.json")

# 官方车型分类表：modelId -> {name, body(车身类型), seats, energy, disp}
try:
    _META = json.load(open(META_FILE, encoding="utf-8"))
except Exception:
    _META = {}

# 档次评分（越好的车分越高，用于同类别内排序）与 refresh.py 共用同一份 car_rank.py
try:
    from car_rank import score as _rank_of
except Exception:                                            # 兜底：缺文件也不影响服务
    def _rank_of(name, body=""):
        return 0

# 归类规则（新能源 / 高端车 / 普通车）与 refresh.py 共用同一份 car_class.py
try:
    from car_class import classify as _classify, by_name_index as _by_name_index
except Exception:                                            # 兜底：缺文件也不影响服务
    def _classify(name, energy="", body=""):
        e = energy or ""
        if any(k in e for k in ("纯电", "插电混", "插混", "增程")):
            return "新能源"
        n = (name or "").upper().replace(" ", "")
        for b in ("奥迪", "宝马", "奔驰", "沃尔沃", "雷克萨斯", "保时捷", "路虎", "捷豹",
                  "凯迪拉克", "林肯", "英菲尼迪", "讴歌", "玛莎拉蒂", "宾利", "劳斯莱斯",
                  "兰博基尼", "法拉利", "迈凯伦", "阿斯顿马丁", "布加迪", "阿尔法罗密欧",
                  "捷尼赛思", "路特斯", "红旗", "MINI", "特斯拉", "蔚来"):
            if b.upper() in n:
                return "高端车"
        return "普通车"

    def _by_name_index(meta):
        idx = {}
        for v in (meta or {}).values():
            nm = (v or {}).get("name")
            if nm and nm not in idx:
                idx[nm] = v
        return idx

_BYNAME = _by_name_index(_META)

# 取车城市 → 还车城市的直线距离（本地坐标表 + 半正矢，运行期不联网）
try:
    from geo import distance as _distance, coord as _coord
except Exception:                                            # 兜底：缺文件则不出距离
    def _distance(a, b):
        return None

    def _coord(c):
        return None

# 真实**驾车里程**（OSRM 路由 + 本地缓存；只读缓存，不在这里发请求）
try:
    import route_dist as _route
except Exception:                                            # 兜底：缺文件则退化为直线
    _route = None

# 云端推送：未配置凭据时安静跳过，不影响服务
try:
    import push as _push
except Exception:                                            # noqa: BLE001
    _push = None

PORT = int(os.environ.get("PORT") or 8000)
REFRESH_SEC = int(os.environ.get("REFRESH_SEC") or 600)
PAGE_SIZE = 500          # 服务端接受的上限
PAGE_GAP = 12            # 页间隔秒（温和，避免触发风控）
MAX_PAGES = 24
RATELIMIT = "访问频次过高"

GW = "https://m.zuche.com/api/gw.do?uri=/action/carrctapi/order/hitchList/v1"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

_state = {
    "items": [], "total": None, "updatedAt": None,
    "newIds": [], "error": None, "lastTry": None, "runs": 0,
    "pushSent": None, "pushInfo": None, "pushAt": None,
}
_lock = threading.Lock()


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


# --------------------------------------------------------------------------
# 抓取
# --------------------------------------------------------------------------
def fetch_page(pn):
    body = json.dumps({"pageNo": pn, "pageSize": PAGE_SIZE, "cityId": 1},
                      separators=(",", ":"))
    req = urllib.request.Request(
        GW,
        data=urllib.parse.urlencode({"data": body}).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "accept": "application/json, text/plain, */*",
            "referer": "https://m.zuche.com/",
            "user-agent": UA,
            "accept-language": "zh-CN,zh;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_all():
    """翻页抓全量。返回 (items, total)。撞限流/出错直接抛异常。"""
    items, total = [], None
    for pn in range(1, MAX_PAGES + 1):
        d = fetch_page(pn)
        if RATELIMIT in (d.get("msg") or ""):
            raise RuntimeError("服务端限流（%s）" % d.get("msg"))
        c = d.get("content") or {}
        if c.get("count") is not None:
            total = c["count"]
        lst = c.get("hitchList") or []
        if not lst:
            break
        items.extend(lst)
        log("  第 %d 页 %d 条（累计 %d）" % (pn, len(lst), len(items)))
        if len(lst) < PAGE_SIZE:
            break
        time.sleep(PAGE_GAP)
    return items, total


def slim(it):
    """只留页面需要的字段，压缩传输体积"""
    name = it.get("modelName") or ""
    m = _META.get(str(it.get("modelId") or "")) or _BYNAME.get(name) or {}
    return {
        "id": str(it.get("hitchId") or ""),
        "model": name,
        "cls": _classify(name, m.get("energy"), m.get("body")),  # 新能源 / 高端车 / 普通车
        "rank": _rank_of(name, m.get("body") or ""),             # 档次分：同类别内越大越靠前
        "body": m.get("body") or "",       # 官方车身类型：轿车 / SUV / MPV ...
        "seats": m.get("seats") or "",     # 5座 / 7座 ...
        "energy": m.get("energy") or "",   # 汽油 / 插电混 / 纯电 ...
        "price": str(it.get("realTotalPrice") if it.get("realTotalPrice") is not None else ""),
        "est": str(it.get("estTotalPrice") if it.get("estTotalPrice") is not None else ""),
        "from": it.get("pickupCityName") or "",
        "to": it.get("returnCityName") or "",
        "km": _distance(it.get("pickupCityName"), it.get("returnCityName")),  # 直线距离(km)；无坐标则 None
        "drive": (_route.get(it.get("pickupCityName"), it.get("returnCityName"))
                  if _route is not None else None),          # 驾车里程(km)；未算出则 None，前端退回直线
        "bd": it.get("beginDate") or "",
        "ed": it.get("endDate") or "",
        "days": it.get("limitTenancyDay") or "",
    }


def save_data():
    with _lock:
        payload = {
            "updatedAt": _state["updatedAt"],
            "total": _state["total"],
            "count": len(_state["items"]),
            "newIds": _state["newIds"],
            "error": _state["error"],
            "source": "m.zuche.com",
            "items": _state["items"],
        }
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, DATA_FILE)


def load_data():
    if not os.path.exists(DATA_FILE):
        return False
    try:
        j = json.load(open(DATA_FILE, encoding="utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        log("data.json 读取失败：%s" % exc)
        return False
    with _lock:
        _state["items"] = j.get("items") or []
        _state["total"] = j.get("total")
        _state["updatedAt"] = j.get("updatedAt")
        _state["newIds"] = j.get("newIds") or []
    log("载入初始数据 %d 条" % len(_state["items"]))
    return True


def refresh_once():
    with _lock:
        _state["lastTry"] = int(time.time() * 1000)
    try:
        items, total = fetch_all()
    except Exception as exc:                                   # noqa: BLE001
        with _lock:
            _state["error"] = "%s: %s" % (type(exc).__name__, exc)
        log("抓取失败：%s" % _state["error"])
        save_data()
        return
    if not items:
        with _lock:
            _state["error"] = "本轮未取到数据"
        save_data()
        return

    rows = [slim(x) for x in items]
    new_ids = [r["id"] for r in rows if r["id"]]
    with _lock:
        old = {x.get("id") for x in _state["items"]}
        first = not old                                     # 首次抓取不报"全部新增"
        _state["items"] = rows
        _state["total"] = total
        _state["updatedAt"] = int(time.time() * 1000)
        _state["newIds"] = [] if first else sorted(set(new_ids) - old, reverse=True)
        _state["error"] = None
        _state["runs"] += 1
        n_new = len(_state["newIds"])
        fresh = list(_state["newIds"])
    save_data()
    log("刷新完成：%d 条（服务端总数 %s），新增 %d 条" % (len(rows), total, n_new))

    # 云端推送：只把新增里的金/银/铜档次（尊享 / 高级 / 中档）纳入。
    # 两条腿：即时推（本轮有新车就发）+ 小时汇总（攒满 push_every_sec 再发一条）。
    # 整段包在 try 里 —— 推送出任何问题都绝不能影响看板本身。
    #
    # ⚠️ 进程启动后的**首轮只建基线、不推送**：库存量波动大（825~1198），
    #    首轮的 newIds 是"全量 vs 空集合"，推出去就是整库轰炸（2026-10-26 推了 169 台）。
    if _push is not None:
        try:
            if _state["runs"] == 1:                      # 首轮
                n = _push.seed_baseline(rows, log=log)
                sent, info = 0, "首轮建基线：%d 台已标记为已读，本轮不推送" % n
            else:
                sent, info = _push.push_new(rows, fresh, log=log)
            with _lock:
                _state["pushSent"] = sent
                _state["pushInfo"] = info
                if sent:
                    _state["pushAt"] = int(time.time() * 1000)
        except Exception as exc:                             # noqa: BLE001
            log("推送模块异常（已忽略）：%s: %s" % (type(exc).__name__, exc))
            with _lock:
                _state["pushInfo"] = "异常：%s: %s" % (type(exc).__name__, exc)


    # 驾车里程：缓存里没有的城市对，慢慢补齐（每轮最多 25 对，带熔断）。
    # 放在推送之后、整段包 try —— 路由服务挂了也绝不能影响看板与推送。
    if _route is not None:
        try:
            got = _route.fill_missing(
                [(r.get("from"), r.get("to")) for r in rows], limit=25, log=log)
            if got:
                rows = [slim(x) for x in items]           # 带上新算出的 drive 再写一次
                with _lock:
                    _state["items"] = rows
                save_data()
                log("驾车里程：本轮补 %d 条，缓存共 %d 条" % (got, _route.known()))
        except Exception as exc:                             # noqa: BLE001
            log("驾车里程补齐异常（已忽略）：%s: %s" % (type(exc).__name__, exc))


def refresh_loop():
    while True:
        refresh_once()
        time.sleep(REFRESH_SEC)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "HitchBoard/1.0"

    def _send(self, code, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):                                          # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html", "/page.html"):
            try:
                html = open(PAGE_FILE, encoding="utf-8").read()
            except Exception as exc:                           # noqa: BLE001
                self._send(500, "page.html 读取失败：%s" % exc, "text/plain; charset=utf-8")
                return
            self._send(200, html, "text/html; charset=utf-8")
        elif path == "/data.json":
            if os.path.exists(DATA_FILE):
                self._send(200, open(DATA_FILE, "rb").read(),
                           "application/json; charset=utf-8")
            else:
                self._send(200, json.dumps({"items": [], "error": "数据尚未就绪"}),
                           "application/json; charset=utf-8")
        elif path == "/health":
            with _lock:
                st = {
                    "ok": _state["error"] is None,
                    "count": len(_state["items"]),
                    "total": _state["total"],
                    "updatedAt": _state["updatedAt"],
                    "newCount": len(_state["newIds"]),
                    "runs": _state["runs"],
                    "error": _state["error"],
                    "refreshSec": REFRESH_SEC,
                    "push": {
                        "sent": _state["pushSent"],
                        "info": _state["pushInfo"],
                        "at": _state["pushAt"],
                    },
                }
                # 上一轮推送明细：真新增几条 / 各档次分布 / 实际推了哪几台
                if _push is not None:
                    try:
                        st["pushDetail"] = _push.last_summary()
                    except Exception:                        # noqa: BLE001
                        st["pushDetail"] = None
                # 距离覆盖率自检：城市坐标表里没有的城市，那几条会显示不出距离
                # （2026-10-22 踩过：贺州不在坐标表里，推送该条完全没有距离项）
                try:
                    items = _state["items"]
                    st["distance"] = {
                        "covered": sum(1 for r in items if r.get("drive")),
                        "total": len(items),
                        "missingCities": sorted({
                            c for r in items
                            for c in (r.get("from"), r.get("to"))
                            if c and _coord(c) is None}),
                    }
                except Exception:                            # noqa: BLE001
                    st["distance"] = None
            self._send(200, json.dumps(st, ensure_ascii=False, indent=2),
                       "application/json; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    do_HEAD = do_GET

    def log_message(self, fmt, *args):
        pass                                                    # 静默访问日志


def main():
    log("启动车源看板，端口 %s，刷新间隔 %d 分钟" % (PORT, REFRESH_SEC // 60))
    if not load_data():
        log("无本地快照，等待首次抓取…")
    threading.Thread(target=refresh_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

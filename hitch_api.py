#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神州租车「顺风车」客户端（触屏版网关，明文，无需 AES/签名）
==========================================================
网关：POST https://m.zuche.com/api/gw.do?uri=<api>
      body: data=<urlencoded JSON>        ← 明文，加解密在服务端做
      鉴权：cookie（CAR_UID / szzcuser / ENCRYPT_MEMBER_ID ...）

接口
----
  /action/carrctapi/order/hitchList/v1    顺风车列表
      data = {"pageNo":1,"pageSize":20,"cityId":1}      # pageNo+pageSize 必须同时给
      -> {count, hitchList:[{hitchId, modelName, realTotalPrice,
                             pickupCityName, returnCityName, beginDate, endDate,
                             limitTenancyDay, modelId, modelPic}], picUrl}

  /action/carrctapi/order/hitchDetail/v1  顺风车详情
      data = {"hitchId":"9488080"}
      -> {pickupDept, returnDept, estTotalPrice, realTotalPrice, specification, ...}

⚠️ 服务端有 IP 维度限流（"访问频次过高，请稍后再试"，code=6 / BASE001）。
   实测：浏览器和 Python 同时被拦，跟客户端无关；恢复窗口 > 5 分钟。
   → 请求之间务必留间隔，连续失败要长退避，不要短时间重试。

用法
----
  python hitch_api.py list                      # 第 1 页
  python hitch_api.py list 1 20                 # 页码 页大小
  python hitch_api.py all 3                     # 抓前 3 页
  python hitch_api.py detail 9488080
  python hitch_api.py probe                     # 只测连通性
"""

import json
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://m.zuche.com"
GW = BASE + "/api/gw.do?uri="
COOKIE_FILE = os.path.join(HERE, "h5-cookies.json")
COOKIE_TXT = os.path.join(HERE, "h5-cookie-header.txt")

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

RATELIMIT_MSG = "访问频次过高"

# ⚠️ 默认**不带 cookie**！实测：带登录会话的请求会被服务端按会话限流
# （返回 访问频次过高），而不带 cookie 的匿名请求一切正常。
# hitchList 本来免登录，这份 cookie 只会惹麻烦。
# 需要时用环境变量 ZUCHE_USE_COOKIE=1 打开（例如要调需要登录的接口）。
USE_COOKIE = os.environ.get("ZUCHE_USE_COOKIE") == "1"

_session = None


# --------------------------------------------------------------------------
# cookie 装载 / 回写
# --------------------------------------------------------------------------
def _load_cookie_list():
    """返回 [{name,value,domain,path}, ...]，优先 cookie json"""
    if os.path.exists(COOKIE_FILE):
        try:
            jar = json.load(open(COOKIE_FILE, encoding="utf-8"))
            if isinstance(jar, list) and jar:
                return jar
        except Exception:
            pass
    if os.path.exists(COOKIE_TXT):
        out = []
        for part in open(COOKIE_TXT, encoding="utf-8").read().strip().split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                out.append({"name": k, "value": v, "domain": "m.zuche.com", "path": "/"})
        return out
    raise SystemExit("缺少 cookie 文件：%s / %s" % (COOKIE_TXT, COOKIE_FILE))


def get_session() -> requests.Session:
    """单例 Session。默认**匿名**（不带 cookie），因为带登录会话会被会话级限流。
    设 ZUCHE_USE_COOKIE=1 时才灌入 cookie。"""
    global _session
    if _session is not None:
        return _session
    s = requests.Session()
    jar = []
    if USE_COOKIE:
        try:
            jar = _load_cookie_list()
        except SystemExit:
            jar = []
    for c in jar:
        try:
            s.cookies.set(c["name"], c["value"],
                          domain=c.get("domain") or "m.zuche.com",
                          path=c.get("path") or "/")
        except Exception:
            pass
    s.headers.update({
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "accept": "application/json, text/plain, */*",
        "referer": BASE + "/",
        "user-agent": UA,
        "accept-language": "zh-CN,zh;q=0.9",
    })
    _session = s
    return s


def save_session():
    """仅在使用 cookie 模式下，把 Session 里新增的 WAF cookie 回写（**不**覆盖登录文件）"""
    if not USE_COOKIE:
        return
    s = get_session()
    out = []
    for c in s.cookies:
        out.append({
            "name": c.name, "value": c.value,
            "domain": c.domain or "m.zuche.com",
            "path": c.path or "/",
            "expires": c.expires,
        })
    if out:
        json.dump(out, open(os.path.join(HERE, "waf-cookies.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)


def load_cookie_header() -> str:
    """只读：拼一个 cookie header 字符串（用于调试）"""
    return "; ".join("%s=%s" % (c["name"], c["value"])
                     for c in _load_cookie_list())


# --------------------------------------------------------------------------
# 网关调用
# --------------------------------------------------------------------------
def gw(uri: str, data: dict = None, timeout: int = 25) -> dict:
    """调一次网关，返回解析后的 JSON；自动回写 cookie"""
    if not uri.startswith("/"):
        uri = "/" + uri
    s = get_session()
    r = s.post(
        GW + uri,
        data={"data": json.dumps(data or {}, separators=(",", ":"), ensure_ascii=False)},
        timeout=timeout,
    )
    save_session()                      # WAF 的 acw_tc 每次都会刷新，必须存回去
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        return {"code": -1, "status": "NON_JSON", "msg": r.text[:300]}


def ok(resp: dict) -> bool:
    return resp.get("code") == 1 and resp.get("status") == "SUCCESS"


def is_ratelimited(resp: dict) -> bool:
    return RATELIMIT_MSG in (resp.get("msg") or "")


def hitch_list(page_no: int = 1, page_size: int = 20, city_id: int = 1) -> dict:
    return gw("/action/carrctapi/order/hitchList/v1",
              {"pageNo": page_no, "pageSize": page_size, "cityId": city_id})


def hitch_detail(hitch_id) -> dict:
    return gw("/action/carrctapi/order/hitchDetail/v1", {"hitchId": str(hitch_id)})


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _show(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 0
    cmd, rest = argv[1], argv[2:]

    if cmd == "probe":
        d = hitch_list(1, 3)
        print("code=%s status=%s uid=%s" % (d.get("code"), d.get("status"), d.get("uid")))
        c = d.get("content") or {}
        print("count=%s 本页=%d  msg=%s" % (c.get("count"), len(c.get("hitchList") or []),
                                            d.get("msg")))
        return 0 if ok(d) else 1

    if cmd == "list":
        pn = int(rest[0]) if rest else 1
        ps = int(rest[1]) if len(rest) > 1 else 20
        d = hitch_list(pn, ps)
        if not ok(d):
            _show(d)
            return 1
        c = d["content"]
        print("总数 %s  第 %d 页（%d 条）" % (c.get("count"), pn, len(c["hitchList"])))
        for it in c["hitchList"]:
            print("  %-10s %-6s元  %-6s→%-6s  %s~%s  %s天  hitchId=%s" % (
                it.get("modelName"), it.get("realTotalPrice"),
                it.get("pickupCityName"), it.get("returnCityName"),
                it.get("beginDate"), it.get("endDate"),
                it.get("limitTenancyDay"), it.get("hitchId")))
        return 0

    if cmd == "all":
        pages = int(rest[0]) if rest else 1
        ps = int(rest[1]) if len(rest) > 1 else 200
        total, seen = 0, []
        for pn in range(1, pages + 1):
            d = hitch_list(pn, ps)
            if is_ratelimited(d):
                print("第 %d 页撞上限流，停止（已取 %d 条）" % (pn, len(seen)))
                break
            if not ok(d):
                print("第 %d 页失败: %s" % (pn, d.get("msg")))
                break
            lst = d["content"]["hitchList"]
            seen.extend(lst)
            total = d["content"].get("count")
            print("第 %d 页 %d 条" % (pn, len(lst)))
            if len(lst) < ps:
                break
            if pn < pages:
                time.sleep(3)
        out = os.path.join(HERE, "hitch-all.json")
        json.dump({"count": total, "items": seen}, open(out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("共 %d 条 -> %s" % (len(seen), out))
        return 0

    if cmd == "detail":
        _show(hitch_detail(rest[0]))
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

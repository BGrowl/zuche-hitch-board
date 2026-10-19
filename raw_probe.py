#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""raw 调用：打印完整原始响应，观察 uid / 鉴权字段"""
import json, sys
sys.path.insert(0, r"C:/Users/15258/WorkBuddy/2026-09-29-14-35-55/hitch-watch")
import requests
from zuche_api import BASE, build_form, CID

def raw(api, data=None, uid=None, headers=None):
    form = build_form(data, uid)
    h = {"content-type": "application/x-www-form-urlencoded",
         "appletEncrypt": "appletEncrypt"}
    if headers:
        h.update(headers)
    r = requests.post(BASE + api, data=form, headers=h, timeout=20)
    print("### %s  uid=%r" % (api, uid))
    print("HTTP", r.status_code, "len", len(r.content))
    print("headers:", dict(r.headers))
    print("cookies:", r.cookies.get_dict())
    try:
        print(json.dumps(r.json(), ensure_ascii=False)[:1200])
    except Exception:
        print(r.text[:600])
    print()

if __name__ == "__main__":
    # 1. 免登录接口，看完整响应（含 uid?）
    raw("/action/carrctapi/order/hometab/v5")
    # 2. 带一个假 uid 打 hitchList，看报错是否变化
    raw("/action/carrctapi/order/hitchList/v1", {}, uid="1234567890")
    # 3. 不带 uid
    raw("/action/carrctapi/order/hitchList/v1", {})

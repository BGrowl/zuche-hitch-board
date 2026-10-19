#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺风车接口诊断
==============
限流恢复后跑一次，回答三个问题：
  1. 带 cookie 能否正常取数
  2. **不带 cookie 能否取数**（决定要不要长期维护登录态）
  3. pageSize 上限是多少（决定每轮请求数）

用法：python hitch_diag.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hitch_api as H

GAP = 3.0


def brief(tag, d):
    c = d.get("content") or {}
    print("%-22s code=%-3s status=%-12s count=%-6s 本页=%-3d msg=%s" % (
        tag, d.get("code"), d.get("status"), c.get("count"),
        len(c.get("hitchList") or []), d.get("msg")))


def main():
    print("=== 1) 带 cookie ===")
    d = H.hitch_list(1, 5, 1)
    brief("with-cookie", d)
    if H.is_ratelimited(d):
        print("  → 仍在限流，稍后再试")
        return 2

    time.sleep(GAP)

    print("\n=== 2) 不带 cookie ===")
    s = H.get_session()
    saved = list(s.cookies)
    s.cookies.clear()
    try:
        d2 = H.gw("/action/carrctapi/order/hitchList/v1",
                  {"pageNo": 1, "pageSize": 5, "cityId": 1})
        brief("no-cookie", d2)
        if H.ok(d2):
            print("  ✅ **免登录可读** —— 不需要维护登录态！")
        else:
            print("  ❌ 需要登录态（cookie 失效即不可用）")
    finally:
        for c in saved:
            s.cookies.set_cookie(c)

    time.sleep(GAP)

    print("\n=== 3) pageSize 上限 ===")
    for ps in (50, 100):
        d3 = H.hitch_list(1, ps, 1)
        if H.is_ratelimited(d3):
            print("  pageSize=%-4d → 限流" % ps)
            break
        c = d3.get("content") or {}
        print("  pageSize=%-4d → code=%s count=%s 本页=%d"
              % (ps, d3.get("code"), c.get("count"), len(c.get("hitchList") or [])))
        time.sleep(GAP)
    return 0


if __name__ == "__main__":
    sys.exit(main())

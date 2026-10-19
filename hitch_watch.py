#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神州顺风车「车源监控」
=====================
每轮**只发 1 个请求**（第 1 页，pageSize=200），和上次见过的 hitchId 集合对比，报新增。

为什么这么设计
--------------
· 列表**严格按 hitchId 倒序** → 最新车源永远在第 1 页顶部，无需翻页。
· `hitchList` **免登录**（无 cookie 也能读）→ 不需要维护会话，不会过期。
· ⚠️ **千万不要带 cookie**：实测带登录会话会被**会话级限流**（返回"访问频次过高"），
  而不带 cookie 的匿名请求畅通无阻。本脚本依赖 hitch_api 的匿名默认（不带 cookie）。
· `cityId` 参数被服务端忽略 → 城市过滤在**本地**按 `pickupCityName` 做。

用法
----
  python hitch_watch.py run                      # 抓一轮，报新增
  python hitch_watch.py run --city 北京,上海      # 只看这些取车城市
  python hitch_watch.py run --max-price 1        # 只看 ≤1 元
  python hitch_watch.py run --force              # 无视冷却
  python hitch_watch.py loop --interval 1200     # 常驻，20 分钟一轮
  python hitch_watch.py status

产物
----
  hitch-state.json        已知 hitchId + 首见时间 + 冷却状态
  outputs/顺风车_*.txt     有新增时的清单
  hitch-watch.log         运行日志
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import hitch_api as H

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "hitch-state.json")
OUTDIR = os.path.join(HERE, "outputs")
LOGFILE = os.path.join(HERE, "hitch-watch.log")

PS = 200                  # 每轮取最新 200 条
KEEP_DAYS = 14            # 已知集合保留天数
COOLDOWN_BASE = 900       # 限流冷却 15 分钟
COOLDOWN_MAX = 3600
RATE_HITS_RESET = 3600    # 连续成功满 1 小时就重置限流计数


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    return default


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _iso(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def save_state(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def in_cooldown(st):
    t = _iso(st.get("cooldownUntil") or "")
    return t if (t and datetime.now() < t) else None


def bump_cooldown(st):
    n = int(st.get("rateLimitHits") or 0) + 1
    secs = min(COOLDOWN_BASE * (2 ** (n - 1)), COOLDOWN_MAX)
    st["rateLimitHits"] = n
    st["cooldownUntil"] = (datetime.now() + timedelta(seconds=secs)).isoformat()
    save_state(st)
    log("  限流第 %d 次 → 冷却 %d 分钟（至 %s）"
        % (n, secs // 60, st["cooldownUntil"][11:19]))


def fetch_top():
    """取第 1 页最新 200 条。返回 (items, total, blocked)"""
    d = H.hitch_list(1, PS, 1)
    if H.is_ratelimited(d):
        return [], None, True
    if not H.ok(d):
        log("  请求失败：code=%s status=%s msg=%s" % (d.get("code"), d.get("status"), d.get("msg")))
        return [], None, False
    c = d.get("content") or {}
    return c.get("hitchList") or [], c.get("count"), False


def fmt(it):
    return "%-14s %-5s元  原价%-6s  %-6s → %-6s  %s~%s  %s天  id=%s" % (
        (it.get("modelName") or "?")[:14], it.get("realTotalPrice", "?"),
        it.get("estTotalPrice", "-"),
        it.get("pickupCityName", "?"), it.get("returnCityName", "?"),
        it.get("beginDate", "?"), it.get("endDate", "?"),
        it.get("limitTenancyDay", "?"), it.get("hitchId", "?"))


def match(it, cities, max_price):
    if cities:
        p = it.get("pickupCityName") or ""
        if not any(c in p for c in cities):
            return False
    if max_price is not None:
        try:
            if float(it.get("realTotalPrice") or 1e9) > max_price:
                return False
        except ValueError:
            return False
    return True


def run_once(quiet=False, cities=None, max_price=None, force=False):
    now = datetime.now()
    st = load_json(STATE, {"known": {}, "firstRun": None})
    known = st.get("known", {})

    if not force:
        until = in_cooldown(st)
        if until:
            log("处于冷却期，跳过（至 %s）。--force 可强制" % until.strftime("%H:%M:%S"))
            return 0, []

    first_run = st.get("firstRun") is None
    log("抓取最新车源…")
    items, total, blocked = fetch_top()

    if blocked:
        bump_cooldown(st)
        return 0, []

    if items:
        st["rateLimitHits"] = 0
        st.pop("cooldownUntil", None)

    log("  服务端总数 %s，本轮 %d 条" % (total, len(items)))
    if not items:
        st["lastRun"] = now.isoformat()
        save_state(st)
        return 0, []

    new_items = [] if first_run else [it for it in items if str(it.get("hitchId")) not in known]

    for it in items:
        k = str(it.get("hitchId"))
        rec = known.setdefault(k, {"firstSeen": now.isoformat()})
        rec.update({
            "lastSeen": now.isoformat(),
            "modelName": it.get("modelName"),
            "pickupCityName": it.get("pickupCityName"),
            "returnCityName": it.get("returnCityName"),
            "realTotalPrice": it.get("realTotalPrice"),
            "beginDate": it.get("beginDate"),
            "endDate": it.get("endDate"),
        })

    # 清理久未出现的
    cutoff = now - timedelta(days=KEEP_DAYS)
    known = {k: v for k, v in known.items()
             if (_iso(v.get("lastSeen") or v.get("firstSeen") or "") or now) >= cutoff}
    st["known"] = known
    st["firstRun"] = st.get("firstRun") or now.isoformat()
    st["lastRun"] = now.isoformat()
    st["lastTotal"] = total
    save_state(st)

    if first_run:
        log("  首次运行：建立基线 %d 条（不报新增）" % len(known))
        return 0, []

    hits = [it for it in new_items if match(it, cities, max_price)]
    if not new_items:
        log("  无新增")
        return 0, []
    log("  ★ 新增 %d 条（过滤后 %d 条）" % (len(new_items), len(hits)))

    if not hits:
        return 0, []

    os.makedirs(OUTDIR, exist_ok=True)
    fn = os.path.join(OUTDIR, "顺风车_%s.txt" % now.strftime("%Y%m%d_%H%M"))
    with open(fn, "w", encoding="utf-8") as f:
        f.write("神州顺风车新增车源  %s\n" % now.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("服务端总数 %s ｜ 新增 %d 条 ｜ 过滤后 %d 条\n" % (total, len(new_items), len(hits)))
        f.write("=" * 100 + "\n")
        for it in hits:
            f.write(fmt(it) + "\n")
    log("  清单 -> %s" % fn)
    if not quiet:
        for it in hits:
            print("    " + fmt(it))
    return len(hits), hits


def show_status():
    st = load_json(STATE, {})
    print("已知车源   : %d 条（保留 %d 天）" % (len(st.get("known") or {}), KEEP_DAYS))
    print("服务端总数 : %s" % st.get("lastTotal"))
    print("首见基线   : %s" % st.get("firstRun"))
    print("上轮运行   : %s" % st.get("lastRun"))
    print("限流累计   : %s 次" % st.get("rateLimitHits", 0))
    until = _iso(st.get("cooldownUntil") or "")
    if until:
        if datetime.now() < until:
            print("冷却中     : 至 %s（还剩 %d 分钟）"
                  % (until.strftime("%H:%M:%S"),
                     int((until - datetime.now()).total_seconds() // 60) + 1))
        else:
            print("冷却       : 已过期")
    return 0


def main():
    ap = argparse.ArgumentParser(description="神州顺风车车源监控")
    ap.add_argument("cmd", choices=["run", "loop", "status"], nargs="?", default="run")
    ap.add_argument("--city", default="", help="只看这些取车城市，逗号分隔")
    ap.add_argument("--max-price", type=float, default=None)
    ap.add_argument("--interval", type=int, default=1200)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    cities = [c.strip() for c in a.city.split(",") if c.strip()] or None

    if a.cmd == "status":
        return show_status()

    if a.cmd == "loop":
        log("常驻监控，间隔 %d 秒，Ctrl+C 退出" % a.interval)
        while True:
            try:
                run_once(a.quiet, cities, a.max_price, a.force)
            except KeyboardInterrupt:
                break
            except Exception as exc:                      # noqa: BLE001
                log("出错：%s: %s" % (type(exc).__name__, exc))
            time.sleep(a.interval)
    else:
        run_once(a.quiet, cities, a.max_price, a.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

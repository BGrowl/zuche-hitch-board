#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重算车源归类，刷新站点数据 + 本地单页 HTML（不重新抓取）
============================================================
分类规则（`car_class.py`）改变时用它：基于本地已有的 `hitch-all.json`
重算 `cls`（新能源 / 高端车 / 普通车）字段，写回 `hitch-site/data.json`，
并重新生成 `顺风车车源.html`。

- **不发任何网络请求**，秒级完成，不碰接口、不触发风控。
- 保留原有 `updatedAt` / `newIds` / `total`，页面的「NEW」标记不会丢。

用法
----
  python reclass.py
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from refresh import slim, load_meta                            # noqa: E402
from car_class import by_name_index                            # noqa: E402

ALL = os.path.join(HERE, "hitch-all.json")
SITE = os.path.join(HERE, "hitch-site")
DATA = os.path.join(SITE, "data.json")
META = os.path.join(HERE, "model-meta.json")
META_SITE = os.path.join(SITE, "model-meta.json")


def main():
    allj = json.load(open(ALL, encoding="utf-8"))
    items = allj.get("items") or []
    meta = load_meta()
    by_name = by_name_index(meta)
    rows = [slim(x, meta, by_name) for x in items]

    old = {}
    if os.path.exists(DATA):
        try:
            old = json.load(open(DATA, encoding="utf-8"))
        except Exception:
            old = {}

    os.makedirs(SITE, exist_ok=True)
    if os.path.exists(META):
        shutil.copyfile(META, META_SITE)
    # 归类模块同步一份到站点目录（服务端 server.py 会 import 它）
    shutil.copyfile(os.path.join(HERE, "car_class.py"),
                    os.path.join(SITE, "car_class.py"))
    shutil.copyfile(os.path.join(HERE, "car_rank.py"),
                    os.path.join(SITE, "car_rank.py"))

    payload = {
        "updatedAt": old.get("updatedAt"),
        "total": old.get("total") or allj.get("count"),
        "count": len(rows),
        "newIds": old.get("newIds") or [],
        "error": old.get("error"),
        "source": "m.zuche.com",
        "items": rows,
    }
    tmp = DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, DATA)

    # 统计
    cnt = {}
    for r in rows:
        cnt[r["cls"]] = cnt.get(r["cls"], 0) + 1
    print("data.json 已更新：%d 条" % len(rows))
    for k in ("新能源", "高端车", "普通车"):
        print("   %-4s %d 条" % (k, cnt.get(k, 0)))
        if cnt.get(k, 0) == 0:
            print("   ⚠️ 「%s」为空，检查 car_class.py 规则" % k)

    try:
        from make_html import main as gen_html
        gen_html()
    except Exception as exc:                                   # noqa: BLE001
        print("本地 HTML 生成失败：%s" % exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""车源归类：新能源 / 高端车 / 普通车（三类互斥，一车只进一栏）

规则（2026-10-11 与用户确认）
----------------------------
1. **能源优先**：纯电 / 插电混 / 增程式 一律算「新能源」。
   即便是豪华品牌（特斯拉、理想、问界、奥迪E5、沃尔沃XC70…）也归「新能源」，
   这样「新能源」这一栏是完整可用的。
2. 剩下的车按**品牌**识别「高端车」（豪华品牌）。
3. 其余为「普通车」。

注：油电混（HEV，如丰田凯美瑞双擎）不插电、上蓝牌，按国内惯例**不算**新能源，
    因而落到「普通车」。

这套规则被 refresh.py / make_html.py / hitch-site/server.py 共用，
改规则只改本文件（hitch-site/ 下留一份同步副本）。
"""

NEW_ENERGY_KEYS = ("纯电", "插电混", "插混", "增程")

# 只做纯电/插混/增程的品牌：官方档案还没抓到（新车）时的兜底识别
NEV_BRANDS = (
    "特斯拉", "理想", "问界", "蔚来", "小鹏", "零跑", "比亚迪", "腾势", "岚图",
    "智界", "享界", "尊界", "深蓝", "阿维塔", "极氪", "极狐", "智己", "埃安",
    "乐道", "方程豹", "尚界", "仰望", "昊铂", "启源", "星纪元",
)

# 豪华品牌：命中即「高端车」（在能源之后判断，所以特斯拉/蔚来实际会落「新能源」）
LUX_BRANDS = (
    "奥迪", "宝马", "奔驰", "沃尔沃", "雷克萨斯", "保时捷", "路虎", "捷豹",
    "凯迪拉克", "林肯", "英菲尼迪", "讴歌", "玛莎拉蒂", "宾利", "劳斯莱斯",
    "兰博基尼", "法拉利", "迈凯伦", "阿斯顿马丁", "布加迪", "阿尔法罗密欧",
    "捷尼赛思", "路特斯", "红旗", "MINI", "特斯拉", "蔚来",
)

GROUP_NEW = "新能源"
GROUP_LUX = "高端车"
GROUP_NORMAL = "普通车"
GROUPS = (GROUP_NEW, GROUP_LUX, GROUP_NORMAL)


def is_new_energy(energy, name=""):
    e = energy or ""
    if any(k in e for k in NEW_ENERGY_KEYS):
        return True
    # 档案里没能源字段时（新车还没抓到档案），靠品牌名兜底
    if not e:
        n = (name or "").upper().replace(" ", "")
        return any(b.upper() in n for b in NEV_BRANDS)
    return False


def is_luxury(name):
    n = (name or "").upper().replace(" ", "")
    return any(b.upper() in n for b in LUX_BRANDS)


def classify(name, energy, body=""):
    """→ 「新能源」/「高端车」/「普通车」"""
    if is_new_energy(energy, name):
        return GROUP_NEW
    if is_luxury(name):
        return GROUP_LUX
    return GROUP_NORMAL


def by_name_index(meta):
    """{车型名: 档案}，用于 modelId 缺失时按名字兜底"""
    idx = {}
    for v in (meta or {}).values():
        nm = (v or {}).get("name")
        if nm and nm not in idx:
            idx[nm] = v
    return idx


def meta_for(model_id, model_name, meta, by_name=None):
    """优先按 modelId 查官方档案；查不到再按车型名兜底（同一车型可能挂多个 modelId）"""
    m = (meta or {}).get(str(model_id or "")) or {}
    if not m and by_name:
        m = by_name.get(model_name or "") or {}
    return m


if __name__ == "__main__":
    samples = [
        ("特斯拉Model3", "纯电"), ("理想L7", "增程式"), ("奥迪A4L", "汽油"),
        ("沃尔沃S90", "汽油"), ("大众朗逸", "汽油"), ("丰田凯美瑞双擎", "油电混"),
        ("比亚迪秦PLUS", "插电混"), ("奥迪E5Sportback", "纯电"),
    ]
    for n, e in samples:
        print("%-16s %-6s → %s" % (n, e, classify(n, e)))

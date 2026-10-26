#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
车源看板 · 云端推送模块（多通道）
==================================
挂在 server.py 的刷新循环后面：每抓完一轮，挑出**新增**且**档次属于金/银/铜**
（尊享 / 高级 / 中档，即 rank >= 70）的车源，推到微信/手机。

推送节奏（两条腿并行，各自可开关）
----------------------------------
1) **即时推送**（`pushImmediate`，默认 `true`）
   本轮一出现达标新车就**立刻推一条**「顺风车 · 新增 N 台好车」。
   抓取每 REFRESH_SEC（默认 600 秒 = 10 分钟）一轮 ⇒ 即"每 10 分钟一条"，没新车就不发。
2) **小时汇总**（`push_every_sec`，默认 `3600`）
   同一批车同时攒进 `push-state.json` 的 `pendingIds` 缓冲区，
   **满 1 小时再推一条**「顺风车 · 近 1 小时汇总 N 台好车」，一眼看全这一小时。
   `0` = 关闭汇总，只保留即时推送。

两条腿内容**会有重叠**（汇总必然包含即时已推过的车），这是有意设计：
即时条抢先看，汇总条看全貌。缓冲里存**整条车源记录**，中途下架的车照样能汇总进去。

为什么放在云端服务里做
----------------------
WorkBuddy 的定时任务都在本机跑（电脑关机就停），而本服务发布后跑在云沙箱，
每 REFRESH_SEC 秒自己抓一轮 —— 所以「推送」搭在它身上，**不需要用户电脑开机**。

通道一览（push-config.json 里用 channel 选）
--------------------------------------------
1) wecom      —— **企业微信群机器人**（推荐，默认优先）
   免费、不限量、**不需要实名**、**不需要 IP 白名单**。消息直接落在企业微信群里，
   群成员再关注「微信插件」后还能**同步进个人微信**，全程**不用点链接**。
   只需 1 个 webhook 地址：
     https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
   获取：企业微信 → 进目标群（**内部群**）→ 右上角「...」→ **消息推送** → 添加 →
        **自定义消息推送** → 复制 Webhook。全程**不会问你任何"模式"**。
   （v4.1.41 起"群机器人"已改名"消息推送"；若被要求选「普通模式 / API 模式」，
     说明点进了"智能机器人"——那是 AI 对话机器人，**没有 webhook**，退回重来。）
   ⚠️ 正文类型由配置项 `wecomMsgType` 决定，**默认 text**：
     · `text`     ≤ **2048** 字节，**微信插件（个人微信侧）能看到** ✔
     · `markdown` ≤ 4096 字节，颜色更好看，但**微信插件不支持该类型**，会显示
       "暂不支持此消息类型，点击前往企业微信查看"（官方开发者社区明确答复）
     ⇒ 目标是"推到个人微信"就必须用 `text`，代价是失去颜色，改用【尊享】等文字标注。
   机器人消息**每分钟最多 20 条**；单条塞不下会**自动拆成多条连续发**，不截断。

2) wechat_mp  —— 微信公众平台**接口测试号 + 模板消息**
   腾讯官方开发者沙箱号。免费、**不需要实名**、不需要企业资质、**不用装任何 App**，
   且**测试号不校验 IP 白名单**，云沙箱可直接调用。
   ⚠️ 短板：模板消息是**卡片**，正文单个字段过长会被微信截断，只能列前几台 + "另有 N 台"，
      用户还得点进「服务通知」才看得到 —— 不够"直接"。因此默认让位给 wecom。
   需要 4 个值：mpAppId / mpAppSecret / mpTemplateId / mpOpenIds。
   开通：https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login 微信扫码登录 →
   即得 appID 与 appsecret → 扫页面底部二维码关注（"关注者列表"里出现你的 openid）→
   「模板消息接口 → 新增测试模板」填两行 `{{title.DATA}}` `{{content.DATA}}` → 得模板 ID。

3) pushplus  —— https://www.pushplus.plus
   只需一个 token，但平台自 2024-08-01 起**强制实名认证**（身份证+手机号+1 元认证费），
   未实名调用发送接口返回 905。已实名的账号可用。

4) wxpusher  —— https://wxpusher.zjiecode.com
   免费、**不需要实名**，但**微信公众号通道已被微信停掉**，现在必须装它的客户端 App
   才能收消息（"微信 ClawBot"通道也要先在 App 里绑定，且每 24 小时限 10 条）。
   仅在用户愿意装 App 时使用。

channel 取值
------------
  "auto"      （默认）谁配好了用谁：wecom → wechat_mp → pushplus → wxpusher
  "wecom"     只走企业微信群机器人
  "wechat_mp" 只走微信测试号
  "pushplus"  只走 PushPlus
  "wxpusher"  只走 WxPusher

配置（文件优先，其次环境变量）
------------------------------
同目录 push-config.json：
  {
    "enabled": true, "channel": "auto",
    "wecomWebhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
    "mpAppId": "", "mpAppSecret": "", "mpTemplateId": "", "mpOpenIds": [],
    "token": "", "appToken": "", "uids": [],
    "wecomMsgType": "text",
    "min_tier": 3, "max_items": 0
  }
环境变量：WECOM_WEBHOOK / WECOM_MSGTYPE（text|markdown）/ WECHAT_MP_APPID /
         WECHAT_MP_SECRET / WECHAT_MP_TEMPLATE_ID / WECHAT_MP_OPENIDS（逗号分隔）/
         PUSHPLUS_TOKEN / WXPUSHER_APP_TOKEN / WXPUSHER_UIDS

CLI
---
  python push.py --test     发一条测试消息到当前生效通道
  python push.py --dry      只打印将要推送的内容，不真发
  python push.py --new      按当前 data.json 试算「新增里符合条件的有哪些」
  python push.py --probe    逐个通道探活，报告每个通道的真实返回码
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "push-config.json")
STATE_FILE = os.path.join(HERE, "push-state.json")
TOKEN_FILE = os.path.join(HERE, "push-token.json")
DATA_FILE = os.path.join(HERE, "data.json")

API_PUSHPLUS = "https://www.pushplus.plus/send"
API_WXPUSHER = "https://wxpusher.zjiecode.com/api/send/message"
API_WECOM = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
API_MP_TOKEN = "https://api.weixin.qq.com/cgi-bin/stable_token"
API_MP_SEND = "https://api.weixin.qq.com/cgi-bin/message/template/send"

TIER_NAME = {1: "尊享", 2: "高级", 3: "中档", 4: "入门"}
TIER_COLOR = {1: "#d4a017", 2: "#7b8794", 3: "#c08552", 4: "#9aa3ad"}

# 企业微信 markdown 只认这 3 种颜色；顺便把档次映射上去（尊享红、高级绿、中档灰）
TIER_WECOM_COLOR = {1: "warning", 2: "info", 3: "comment", 4: "comment"}

# 只要这几种档次的新车才值得打扰用户（4 = 入门，不推）
DEFAULT_MIN_TIER = 3

# 模板消息单个字段太长会被微信截断，这里主动收口
MP_FIELD_MAX = 220
MP_ITEMS = 6

# 企业微信正文上限（官方文档，单位是**字节**不是字符）
#   text     ≤ 2048 —— **微信插件（个人微信侧）可见**
#   markdown ≤ 4096 —— 颜色好看，但**微信插件不支持**，会显示"暂不支持此消息类型"
WECOM_LIMIT = {"text": 2048, "markdown": 4096}

# 默认走 text：因为最终目的是"推到个人微信"，而微信插件只认 text。
# 只看企业微信客户端、想要颜色的话，把 push-config.json 的 wecomMsgType 改成 "markdown"。
WECOM_MSGTYPE = "text"
WECOM_MAX_BYTES = WECOM_LIMIT[WECOM_MSGTYPE]      # 兼容旧引用

# 单条塞不下时拆成多条连续发（企业微信限速 20 条/分钟，间隔 0.35s 足够安全）
WECOM_PAGE_GAP = 0.35

# 微信 access_token 判定失效的错误码 → 强制刷新后重试一次
TOKEN_ERRCODES = {40001, 40014, 42001, -1}


def tier(rank):
    r = int(rank or 0)
    return 1 if r >= 90 else (2 if r >= 80 else (3 if r >= 70 else 4))


def _as_list(v):
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v or "").split(",") if x.strip()]


def load_config():
    cfg = {
        "enabled": True,
        "channel": "auto",
        "wecomWebhook": "",
        "wecomMsgType": WECOM_MSGTYPE,     # text=微信插件可见（默认）；markdown=仅企业微信、有颜色
        "mpAppId": "", "mpAppSecret": "", "mpTemplateId": "", "mpOpenIds": [],
        "mpUrl": "",
        "token": "",
        "appToken": "", "uids": [],
        "min_tier": DEFAULT_MIN_TIER,
        "cooldown_sec": 0,
        "max_items": 0,          # 0 = 不限，推送里列出全部新增（超长自动拆多条）
        "pushImmediate": True,   # 每轮有达标新车就立刻推一条（"每 10 分钟一条"）
        "push_every_sec": 3600,  # 额外的小时汇总周期：0 = 关闭汇总，只做即时推送
    }
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f) or {})
    except Exception:
        pass

    # 环境变量兜底（云端发布若用环境变量注入凭据）
    env = os.environ.get
    cfg["wecomWebhook"] = cfg.get("wecomWebhook") or env("WECOM_WEBHOOK") or ""
    cfg["wecomMsgType"] = (cfg.get("wecomMsgType") or env("WECOM_MSGTYPE")
                           or WECOM_MSGTYPE).strip().lower()
    cfg["mpAppId"] = cfg.get("mpAppId") or env("WECHAT_MP_APPID") or ""
    cfg["mpAppSecret"] = cfg.get("mpAppSecret") or env("WECHAT_MP_SECRET") or ""
    cfg["mpTemplateId"] = cfg.get("mpTemplateId") or env("WECHAT_MP_TEMPLATE_ID") or ""
    if not cfg.get("mpOpenIds"):
        cfg["mpOpenIds"] = _as_list(env("WECHAT_MP_OPENIDS"))
    cfg["token"] = cfg.get("token") or env("PUSHPLUS_TOKEN") or ""
    cfg["appToken"] = cfg.get("appToken") or env("WXPUSHER_APP_TOKEN") or ""
    if not cfg.get("uids"):
        cfg["uids"] = _as_list(env("WXPUSHER_UIDS"))
    if env("PUSH_EVERY_SEC"):
        try:
            cfg["push_every_sec"] = int(env("PUSH_EVERY_SEC"))
        except Exception:                                    # noqa: BLE001
            pass
    if env("PUSH_IMMEDIATE"):
        cfg["pushImmediate"] = env("PUSH_IMMEDIATE").strip().lower() not in (
            "0", "false", "no", "off", "")

    cfg["mpOpenIds"] = _as_list(cfg.get("mpOpenIds"))
    cfg["uids"] = _as_list(cfg.get("uids"))
    return cfg


def _has_wecom(cfg):
    return bool(str(cfg.get("wecomWebhook") or "").strip())


def _has_mp(cfg):
    return bool(cfg.get("mpAppId") and cfg.get("mpAppSecret")
                and cfg.get("mpTemplateId") and cfg.get("mpOpenIds"))


def _has_wx(cfg):
    return bool(cfg.get("appToken")) and bool(cfg.get("uids"))


def active_channel(cfg):
    """决定这轮用哪条通道。返回通道名或 None。"""
    ch = (cfg.get("channel") or "auto").lower()
    if ch in ("wecom", "qy", "qywx", "work"):
        return "wecom" if _has_wecom(cfg) else None
    if ch in ("wechat_mp", "mp", "wechat", "weixin"):
        return "wechat_mp" if _has_mp(cfg) else None
    if ch == "pushplus":
        return "pushplus" if cfg.get("token") else None
    if ch == "wxpusher":
        return "wxpusher" if _has_wx(cfg) else None
    # auto：企业微信机器人最优（纯文本直接显示、不限量），其次微信测试号/PushPlus/WxPusher
    if _has_wecom(cfg):
        return "wecom"
    if _has_mp(cfg):
        return "wechat_mp"
    if cfg.get("token"):
        return "pushplus"
    if _has_wx(cfg):
        return "wxpusher"
    return None


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            d = json.load(f) or {}
    except Exception:
        d = {}
    d.setdefault("sentIds", [])
    d.setdefault("pendingIds", [])           # 汇总模式下攒着待推的达标新车（整条记录）
    return d


def save_state(st):
    ids = st.get("sentIds") or []
    if len(ids) > 5000:                      # 只留最近 5000 个，防无限增长
        ids = ids[-5000:]
        st["sentIds"] = ids
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, STATE_FILE)


def seed_baseline(rows, log=None):
    """新进程/新沙箱的**首轮**：把当前全量标记为已读，清空待汇总，本轮不推送。

    为什么必须这么做：数据源的库存量波动很大（实测同一接口在 825~1198 之间跳），
    任何"拿发布前的 data.json 当基线"的做法，都会漏掉波动进来的那部分 ——
    它们会在首轮被整批判成"新增"。2026-10-26 就是这样：seed 了 825 台，
    首轮抓到 1198 台，430 个新 id 里 169 台达标，直接被推了出去。

    本质上，新沙箱首轮的 newIds 是"全量 vs 空集合"的对比，没有增量含义，
    推它一定是错的。所以首轮只建基线，从第二轮起才做真正的增量推送。
    """
    st = load_state()
    ids = [r.get("id") for r in rows if r.get("id")]
    st["sentIds"] = list(dict.fromkeys((st.get("sentIds") or []) + sorted(ids)))
    st["pendingIds"] = []                    # 顺手清掉上一版残留的待汇总
    st["seededAt"] = int(time.time() * 1000)
    save_state(st)
    if log:
        log("首轮建基线：%d 台标记为已读（累计 %d），本轮不推送"
            % (len(ids), len(st["sentIds"])))
    return len(ids)


def _post_json(url, obj, timeout=25):
    """POST JSON，返回解析后的 dict。网络/解析异常直接抛。"""
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"content-type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# --------------------------------------------------------------------------
# 通道一：微信公众平台接口测试号 + 模板消息
# --------------------------------------------------------------------------
_token_cache = {"appid": None, "token": None, "expireAt": 0}


def mp_access_token(appid, secret, force=False, timeout=20):
    """取 access_token。返回 (token, info)；失败时 token 为 None。

    微信提供 stable_token 接口（force_refresh=false 时多实例共享同一 token），
    比老的 /cgi-bin/token 更适合云沙箱。内存 + 文件双层缓存，2 小时有效。
    """
    now = time.time()
    if (not force and _token_cache["token"] and _token_cache["appid"] == appid
            and _token_cache["expireAt"] > now + 300):
        return _token_cache["token"], "内存缓存"
    if not force:
        try:
            c = json.load(open(TOKEN_FILE, encoding="utf-8"))
            if (c.get("appid") == appid and c.get("accessToken")
                    and float(c.get("expireAt") or 0) > now + 300):
                _token_cache.update(appid=appid, token=c["accessToken"],
                                    expireAt=float(c["expireAt"]))
                return c["accessToken"], "文件缓存"
        except Exception:
            pass

    try:
        j = _post_json(API_MP_TOKEN, {
            "grant_type": "client_credential",
            "appid": appid,
            "secret": secret,
            "force_refresh": bool(force),
        }, timeout=timeout)
    except Exception as e:                                    # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, e)

    tok = j.get("access_token")
    if tok:
        exp = now + int(j.get("expires_in") or 7200)
        _token_cache.update(appid=appid, token=tok, expireAt=exp)
        try:
            tmp = TOKEN_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"appid": appid, "accessToken": tok, "expireAt": exp}, f)
            os.replace(tmp, TOKEN_FILE)
        except Exception:
            pass
        return tok, "已刷新"
    return None, "微信返回 %s：%s" % (j.get("errcode"), j.get("errmsg"))


def _mp_send_one(token, openid, template_id, title, content, url="", timeout=25):
    obj = {
        "touser": openid,
        "template_id": template_id,
        "data": {
            "title": {"value": title[:MP_FIELD_MAX]},
            "content": {"value": content[:MP_FIELD_MAX]},
        },
    }
    if url:
        obj["url"] = url
    return _post_json(API_MP_SEND + "?access_token=" + token, obj, timeout=timeout)


def wechat_mp_send(cfg, title, content, timeout=25):
    """向 mpOpenIds 逐个发模板消息。返回 (ok, info)。"""
    appid = cfg.get("mpAppId")
    secret = cfg.get("mpAppSecret")
    tid = cfg.get("mpTemplateId")
    oids = cfg.get("mpOpenIds") or []
    url = cfg.get("mpUrl") or ""

    token, info = mp_access_token(appid, secret, timeout=timeout)
    if not token:
        return False, "取 access_token 失败：%s" % info

    ok_cnt, errs = 0, []
    for oid in oids:
        try:
            j = _mp_send_one(token, oid, tid, title, content, url, timeout=timeout)
        except Exception as e:                                # noqa: BLE001
            errs.append("%s: %s" % (type(e).__name__, e))
            continue

        if int(j.get("errcode") or 0) in TOKEN_ERRCODES:
            # token 失效 → 强制刷新后重试一次
            token, info = mp_access_token(appid, secret, force=True, timeout=timeout)
            if not token:
                errs.append("刷新 token 失败：%s" % info)
                continue
            try:
                j = _mp_send_one(token, oid, tid, title, content, url, timeout=timeout)
            except Exception as e:                            # noqa: BLE001
                errs.append("%s: %s" % (type(e).__name__, e))
                continue

        if int(j.get("errcode") or 0) == 0:
            ok_cnt += 1
        else:
            errs.append("errcode %s：%s" % (j.get("errcode"), j.get("errmsg")))

    if ok_cnt and not errs:
        return True, "模板消息已送达 %d 个接收者" % ok_cnt
    if ok_cnt:
        return True, "送达 %d 个，部分失败：%s" % (ok_cnt, "；".join(errs[:2]))
    return False, "全部失败：%s" % ("；".join(errs[:2]) or "无接收者")


# --------------------------------------------------------------------------
# 通道二：PushPlus
# --------------------------------------------------------------------------
def pushplus_send(token, title, content, timeout=25):
    """返回 (ok, info)。任何异常都吞掉并如实回报，绝不假装成功。"""
    try:
        j = _post_json(API_PUSHPLUS, {
            "token": token, "title": title, "content": content, "template": "html",
        }, timeout=timeout)
    except urllib.error.HTTPError as e:
        return False, "HTTP %s：%s" % (e.code, e.read()[:200])
    except Exception as e:                                    # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)

    if str(j.get("code")) == "200":
        return True, "PushPlus 已受理"
    hint = ""
    if str(j.get("code")) == "905":
        hint = ("（PushPlus 要求实名认证：个人中心→个人资料→实名认证，"
                "身份证+手机号，认证费 1 元）")
    return False, "PushPlus 返回 %s：%s%s" % (j.get("code"), j.get("msg"), hint)


# --------------------------------------------------------------------------
# 通道三：WxPusher（需装客户端 App）
# --------------------------------------------------------------------------
def wxpusher_send(app_token, uids, title, content, timeout=25):
    """contentType=2 表示 html（只发 body 内部片段）。返回 (ok, info)。"""
    try:
        j = _post_json(API_WXPUSHER, {
            "appToken": app_token,
            "content": content,
            "summary": title[:100],
            "contentType": 2,
            "uids": list(uids),
        }, timeout=timeout)
    except urllib.error.HTTPError as e:
        return False, "HTTP %s：%s" % (e.code, e.read()[:200])
    except Exception as e:                                    # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)

    if int(j.get("code") or 0) == 1000:
        return True, "WxPusher 已受理"
    return False, "WxPusher 返回 %s：%s" % (j.get("code"), j.get("msg"))


# --------------------------------------------------------------------------
# 通道四：企业微信群机器人（markdown 纯文本，推荐）
# --------------------------------------------------------------------------
def wecom_send(webhook, content, msgtype=WECOM_MSGTYPE, timeout=25):
    """向企业微信群机器人发消息。返回 (ok, info)。

    webhook 形如 https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
    msgtype：`text`（默认，**微信插件也能看到**）或 `markdown`（只有企业微信客户端能看）。
    成功判定看 errcode == 0（HTTP 200 不代表成功）。
    """
    url = str(webhook or "").strip()
    if not url:
        return False, "未配置 wecomWebhook"
    if "key=" not in url:                                    # 容错：只给了 key
        url = API_WECOM + "?key=" + url
    elif url.startswith("http") is False:                    # 容错：给了半截地址
        url = API_WECOM + "?" + url.split("?", 1)[-1]
    mt = str(msgtype or "text").strip().lower()
    if mt not in WECOM_LIMIT:
        mt = "text"
    try:
        j = _post_json(url, {"msgtype": mt, mt: {"content": content}}, timeout=timeout)
    except urllib.error.HTTPError as e:
        return False, "HTTP %s：%s" % (e.code, e.read()[:200])
    except Exception as e:                                    # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)

    if int(j.get("errcode") or 0) == 0:
        return True, "企业微信群机器人已受理"
    return False, "企业微信返回 %s：%s" % (j.get("errcode"), j.get("errmsg"))


def send(cfg, channel, title, content):
    """把消息交给指定通道。返回 (ok, info)。"""
    if channel == "wecom":
        return wecom_send(cfg.get("wecomWebhook"), content,
                          msgtype=cfg.get("wecomMsgType"))
    if channel == "wechat_mp":
        return wechat_mp_send(cfg, title, content)
    if channel == "pushplus":
        return pushplus_send(cfg["token"], title, content)
    if channel == "wxpusher":
        return wxpusher_send(cfg["appToken"], cfg["uids"], title, content)
    return False, "未知通道：%s" % channel


# --------------------------------------------------------------------------
# 组稿
# --------------------------------------------------------------------------
def pick(rows, ids, min_tier=DEFAULT_MIN_TIER):
    """从 rows 里挑出 id 在 ids 中、且档次 <= min_tier 的条目（1=最好）。"""
    by_id = {r.get("id"): r for r in rows}
    out = []
    for i in ids:
        r = by_id.get(i)
        if not r:
            continue
        t = tier(r.get("rank"))
        if t <= min_tier:
            out.append((t, r))
    out.sort(key=lambda x: (x[0], -(int(x[1].get("rank") or 0))))
    return out


def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render(title, pairs):
    """完整 HTML 版正文（给 PushPlus / WxPusher）。"""
    n1 = sum(1 for t, _ in pairs if t == 1)
    parts = ['<div style="font-size:15px;line-height:1.7">']
    parts.append('<b>%s</b><br>' % esc(title))
    parts.append('共 <b>%d</b> 条好车（尊享 %d）<br><br>' % (len(pairs), n1))
    for t, r in pairs:
        color = TIER_COLOR.get(t, "#666")
        price = r.get("price") or "-"
        est = r.get("est") or ""
        ests = (' <s style="color:#999">¥%s</s>' % esc(est)) if est and est != price else ""
        extra = " · ".join(x for x in (r.get("cls"), r.get("body"),
                                       (r.get("seats") or "").strip()) if x)
        line = (
            '<div style="margin:0 0 9px 0">'
            '<span style="display:inline-block;background:%s;color:#fff;'
            'border-radius:4px;padding:1px 6px;font-size:12px">%s</span> '
            '<b>%s</b> <span style="color:#c0392b;font-weight:700">¥%s</span>%s'
            '<br><span style="color:#666;font-size:13px">%s → %s · %s 起 · %s 天</span>'
            '%s'
            '</div>'
        ) % (color, esc(TIER_NAME.get(t, "")), esc(r.get("model")), esc(price), ests,
             esc(r.get("from")), esc(r.get("to")), esc(r.get("bd")), esc(r.get("days")),
             ('<br><span style="color:#888;font-size:12px">%s</span>' % esc(extra))
             if extra else "")
        parts.append(line)
    parts.append("</div>")
    return "".join(parts)


def render_short(pairs, title=None):
    """精简文本版正文（给模板消息：字段越长越容易被微信截断）。"""
    title = title or ("顺风车 · 新增 %d 台好车" % len(pairs))
    shown = pairs[:MP_ITEMS]
    segs = []
    for t, r in shown:
        seg = _dist_txt(r)
        segs.append("%s %s ¥%s %s→%s%s"
                    % (TIER_NAME.get(t, ""), r.get("model") or "",
                       r.get("price") or "-", r.get("from") or "", r.get("to") or "",
                       (" " + seg) if seg else ""))
    content = "；".join(segs)
    rest = len(pairs) - len(shown)
    if rest > 0:
        content += "；另有 %d 台" % rest
    if len(content) > MP_FIELD_MAX:
        content = content[:MP_FIELD_MAX - 1] + "…"
    return title, content


def _dist_txt(r):
    """推送里的一段「距离·天数」标注，例如 `驾车761km·4天`。

    距离优先用**驾车里程**（drive，OSRM 真实路网）；没有则退回直线（km）；
    两者都没有就不显示。天数取 limitTenancyDay（接口字段 days）。
    """
    parts = []
    try:
        drive = int(r.get("drive") or 0)
    except Exception:                                      # noqa: BLE001
        drive = 0
    if drive > 0:
        parts.append("驾车%dkm" % drive)
    else:
        try:
            km = int(r.get("km") or 0)
        except Exception:                                  # noqa: BLE001
            km = 0
        if km > 0:
            parts.append("直线%dkm" % km)
    days = r.get("days")
    if days not in (None, "", 0, "0"):
        parts.append("%s天" % days)
    return "·".join(parts)


def _paginate(item_lines, head_fn, foot_lines, limit):
    """逐行贪心装填 + 页眉页脚，返回 (pages, ranges)。

    ranges[i] = (起点, 终点) 对应该页覆盖的 item_lines 切片下标，调用方据此
    精确标记"哪些车真的发出去了"。超限时**先丢页脚、再丢最后一台车**，
    ranges 同步收缩 —— 被丢的车不会被标记已推，下一轮自动补发。
    """
    reserve = 150
    budget = max(300, limit - reserve)
    chunks, cur, used = [], [], 0
    for ln in item_lines:
        b = len(ln.encode("utf-8")) + 1
        if cur and used + b > budget:
            chunks.append(cur)
            cur, used = [], 0
        cur.append(ln)
        used += b
    chunks.append(cur)
    if not chunks:
        chunks = [[]]
    n = len(chunks)

    pages, ranges, cursor = [], [], 0
    for idx, ch in enumerate(chunks, 1):
        ch = list(ch)
        if ch:
            ch[0] = ch[0].lstrip("\n")                     # 分页后别让首块多出空行
        foot = list(foot_lines) if (idx == n and foot_lines) else []
        while True:
            body = "\n".join([head_fn(idx, n), ""] + ch + ([""] + foot if foot else []))
            if len(body.encode("utf-8")) <= limit:
                break
            if foot:                                   # 先牺牲页脚
                foot = []
            elif len(ch) > 1:                           # 再牺牲最后一台车
                ch.pop()
            else:
                break                                   # 只剩一行，无法再砍
        pages.append(body)
        ranges.append((cursor, cursor + len(ch)))
        cursor += len(ch)
    return pages, ranges


def render_text_paged(pairs, url="", limit=None, title=None):
    """企业微信 **text** 版正文：纯文本，全部列出、不截断。

    为什么必须用 text：官方开发者社区明确「**微信插件不支持 markdown**」，
    用 markdown 发到群里，个人微信侧的微信插件只会显示
    "暂不支持此消息类型，点击前往企业微信查看"。而 text 类型插件可以正常显示。
    text 上限 **2048 字节**（官方，单位是字节），塞不下时自动拆多条连发。

    版式：**一台车固定三行**，档次标在每台车第一行 ——
    因为手机宽度有限，把 7 个字段塞一行必然在随机位置折行，看起来就"乱"：

        1. 【尊享】 问界M9六座版  ¥1
        　 呼伦贝尔 → 北京
        　 761km · 4天 · 10月20日起

    三行各管一件事：① 档次＋车型＋价格 ② 取还车地点 ③ 距离·租期·起租日。
    每行都短，不会折行。档次**逐台标注**（而不是只做组标题）：单档时也不会丢，
    跨页时也不会因为组标题留在上一页而看不到。

    title 可选：汇总模式传「顺风车 · 近 1 小时新增 N 台好车」，不传则用默认文案。

    返回 (pages, ranges)，含义同 render_md_paged。
    """
    limit = int(limit or WECOM_LIMIT["text"])
    total = len(pairs)
    base = title or ("顺风车 · 新增 %d 台好车" % total)

    def head(i, n):
        h = base
        if n > 1:
            h += "（第 %d/%d 条）" % (i, n)
        return h

    foot = ["", "完整看板：%s" % url] if url else []

    blocks = []
    for i, (t, r) in enumerate(pairs, 1):
        seg = []
        if blocks:                                         # 车与车之间空一行
            seg.append("")
        seg.append("%d. 【%s】 %s  ¥%s" % (i, TIER_NAME.get(t, ""),
                                          (r.get("model") or "").strip(),
                                          r.get("price") or "-"))
        seg.append("　 %s → %s" % (r.get("from") or "", r.get("to") or ""))

        bits = []                                          # 第三行：距离 · 租期 · 起租日
        try:
            drive = int(r.get("drive") or 0)
        except Exception:                                  # noqa: BLE001
            drive = 0
        if drive > 0:
            bits.append("%dkm" % drive)
        else:
            try:
                km = int(r.get("km") or 0)
            except Exception:                              # noqa: BLE001
                km = 0
            if km > 0:
                bits.append("直线%dkm" % km)
        days = r.get("days")
        if days not in (None, "", 0, "0"):
            bits.append("%s天" % days)
        bd = (r.get("bd") or "").strip()
        if bd:
            bits.append("%s起" % bd)
        if bits:
            seg.append("　 " + " · ".join(bits))
        blocks.append("\n".join(seg))                      # 一台车 = 一个不可拆块

    return _paginate(blocks, head, foot, limit)


def render_wecom_paged(pairs, url="", msgtype=None, title=None):
    """按配置的正文类型分派：text（默认，微信插件可见）或 markdown（仅企业微信客户端）。"""
    mt = str(msgtype or WECOM_MSGTYPE).strip().lower()
    if mt == "markdown":
        return render_md_paged(pairs, url, title=title)
    return render_text_paged(pairs, url, title=title)


def render_md_paged(pairs, url="", title=None):
    """企业微信 markdown 正文：**一台车一行，全部列出，不做截断**。

    企业微信单条 markdown 上限 4096 字节（官方），所以塞不下时**自动拆成多条**
    连续发送（页眉带 `1/2` 页码），而不是"列前几台 + 点链接看全部"。

    返回 (pages, ranges)：
      pages  —— 每条消息的正文，逐条 ≤ WECOM_MAX_BYTES
      ranges —— ranges[i] = (起点, 终点)，对应 pages[i] 覆盖 pairs 的切片下标
    """
    n1 = sum(1 for t, _ in pairs if t == 1)
    total = len(pairs)
    base = title or ("顺风车 · 新增 %d 台好车" % total)

    def head(i=1, n=1):
        h = "## " + base
        if n1:
            h += '（<font color="warning">尊享 %d</font>）' % n1
        if n > 1:
            h += ' <font color="comment">%d/%d</font>' % (i, n)
        return h

    # 先拼好每台车那一行
    item_lines = []
    for i, (t, r) in enumerate(pairs, 1):
        color = TIER_WECOM_COLOR.get(t, "comment")
        price = r.get("price") or "-"
        route = "%s→%s" % (r.get("from") or "", r.get("to") or "")
        line = '%d. <font color="%s">%s</font> **%s** <font color="warning">¥%s</font> %s' % (
            i, color, TIER_NAME.get(t, ""), r.get("model") or "", price, route)
        seg = _dist_txt(r)
        if seg:
            line += ' <font color="comment">%s</font>' % seg
        bd = (r.get("bd") or "").strip()
        if bd:
            line += ' <font color="comment">%s起</font>' % bd
        item_lines.append(line)

    # 分页：预留页眉/页脚/页码的空间，逐行贪心装填
    limit = WECOM_LIMIT["markdown"]
    reserve = 180
    budget = max(400, limit - reserve)
    chunks, cur, used = [], [], 0
    for ln in item_lines:
        b = len(ln.encode("utf-8")) + 1
        if cur and used + b > budget:
            chunks.append(cur)
            cur, used = [], 0
        cur.append(ln)
        used += b
    chunks.append(cur)
    if not chunks:
        chunks = [[]]
    n = len(chunks)

    pages, ranges, cursor = [], [], 0
    for idx, ch_lines in enumerate(chunks, 1):
        body_lines = [head(idx, n), ""] + list(ch_lines)
        if idx == n and url:
            body_lines += ["", "[打开完整看板](%s)" % url]
        body = "\n".join(body_lines)
        if len(body.encode("utf-8")) > limit:                 # 保险，几乎不会触发
            while len(body.encode("utf-8")) > limit and len(body_lines) > 3:
                body_lines.pop(-1)
                body = "\n".join(body_lines)
        pages.append(body)
        ranges.append((cursor, cursor + len(ch_lines)))
        cursor += len(ch_lines)
    return pages, ranges


def render_md(pairs, url=""):
    """给命令行预览用：把所有分页拼在一起看。"""
    pages, _ = render_md_paged(pairs, url)
    if len(pages) == 1:
        return pages[0]
    return ("\n\n———— 第 %d 条起 ————\n\n").join(
        [pages[0]] + ["（第 %d/%d 条）\n\n%s" % (i, len(pages), p)
                      for i, p in enumerate(pages[1:], 2)])


# --------------------------------------------------------------------------
# 对外：一轮抓取后调用
# --------------------------------------------------------------------------
def _item_brief(t, r):
    """一条推送明细（给 /health 看，方便回答"为什么只推了 N 条"）。"""
    return {"tier": TIER_NAME.get(t), "rank": r.get("rank"), "model": r.get("model"),
            "price": r.get("price"), "from": r.get("from"), "to": r.get("to")}


def _tier_counts(rows, ids):
    """统计这批 id 里的档次分布（含被过滤的入门档）。"""
    by_id = {r.get("id"): r for r in rows}
    out = {}
    for i in ids:
        r = by_id.get(i)
        if not r:
            continue
        k = TIER_NAME.get(tier(r.get("rank")), "?")
        out[k] = out.get(k, 0) + 1
    return out


def last_summary():
    """给 /health 用：最近一轮的推送明细与判定过程。"""
    st = load_state()
    pend = st.get("pendingIds") or []
    return {
        "fresh": st.get("lastFresh"),                       # 本轮真新增条数
        "freshTiers": st.get("lastFreshTiers"),             # 真新增的档次分布（含入门）
        "immediate": st.get("lastImmediate") or 0,          # 「即时推送」本轮发了几台
        "immediateItems": st.get("lastImmediateItems") or [],
        "summary": st.get("lastSummary") or 0,              # 「小时汇总」本轮发了几台
        "summaryItems": st.get("lastSummaryItems") or [],
        "pushed": st.get("lastImmediateItems") or [],       # 兼容旧字段：= 最近一次即时内容
        "channel": st.get("lastChannel"),
        "at": st.get("lastPushAt"),
        "pending": len(pend),                               # 还攒着几台待汇总
        "pendingModels": [r.get("model") for r in pend[:20]],
        "nextSummaryAt": st.get("nextSummaryAt"),           # 下次汇总到点时间
        "watchRoute": st.get("lastWatchRoute"),             # 上次触发的是哪条专线
        "watchItems": st.get("lastWatchItems") or [],       # 该专线推了哪几台
        "watchAt": st.get("lastWatchAt"),
    }


def _label_of(every):
    """把汇总周期翻译成时间段前缀（如「近 1 小时」）。"""
    if every <= 0:
        return "实时"
    if every % 3600 == 0:
        return "近 %d 小时" % (every // 3600)
    if every % 60 == 0:
        return "近 %d 分钟" % (every // 60)
    return "近期"


def _mk_pairs(records, cfg=None):
    """把车源记录排成 [(tier, record)]：先按档次、再按分数，从好到差。"""
    pairs = [(tier(r.get("rank")), r) for r in records if r.get("id")]
    pairs.sort(key=lambda x: (x[0], -(int(x[1].get("rank") or 0))))
    mx = (cfg or {}).get("max_items")
    if mx:
        pairs = pairs[: int(mx)]
    return pairs


def watch_hit(cfg, rows, ids):
    """专线盯车：从**本轮新出现**的车里，筛出命中 `watchRoutes` 的达标车。

    返回 [(route_cfg, pairs), ...]，每条专线一组。配置见 push-config.json：

        "watchRoutes": [{"name": "丽江→大理", "from": "丽江", "to": "大理", "min_tier": 3}]

    · 只认 `ids`（即本轮 fresh）—— 刚加一条专线时，线上已有的存量车**不会**被推出来。
    · 方向严格按 from → to，不做双向（要反向就再加一条）。
    · `min_tier` 缺省沿用全局门槛（3 = 中档以上）。
    """
    routes = cfg.get("watchRoutes") or []
    if not routes or not ids:
        return []
    by_id = {r.get("id"): r for r in rows}
    out = []
    for rt in routes:
        if not isinstance(rt, dict):
            continue
        f = (rt.get("from") or "").strip()
        t = (rt.get("to") or "").strip()
        if not f or not t:
            continue
        mt = int(rt.get("min_tier") or cfg.get("min_tier") or DEFAULT_MIN_TIER)
        got = [r for r in (by_id.get(i) for i in ids)
               if r
               and (r.get("from") or "").strip() == f
               and (r.get("to") or "").strip() == t
               and tier(r.get("rank")) <= mt]
        if got:
            out.append((rt, _mk_pairs(got, cfg)))
    return out


def _deliver(cfg, ch, pairs, title):
    """把一批车通过指定通道发出去。返回 (sent_count, info)。

    · wecom：text/markdown 分页连发（超长自动拆多条），返回**真正发出去**的台数；
    · 其余通道：一条消息发完，成功返回 len(pairs)。
    失败一律返回 0 台 + 原因，绝不假装成功。
    """
    if not pairs:
        return 0, "无内容"
    if ch == "wecom":
        mt = str(cfg.get("wecomMsgType") or WECOM_MSGTYPE).strip().lower()
        pages, ranges = render_wecom_paged(pairs, cfg.get("mpUrl") or "", mt, title=title)
        total = len(pages)
        sent_pages, last_info, fail_info = 0, "", ""
        gap = WECOM_PAGE_GAP if total <= 15 else 3.2      # 限速 20 条/分钟，多时主动让路
        for idx, pg in enumerate(pages):
            ok, info = wecom_send(cfg.get("wecomWebhook"), pg, msgtype=mt)
            if not ok:
                fail_info = info
                break
            sent_pages += 1
            last_info = info
            if idx + 1 < total:
                time.sleep(gap)
        if sent_pages == 0:
            return 0, fail_info
        n = sum(ranges[i][1] - ranges[i][0] for i in range(sent_pages))
        if sent_pages < total:
            return n, "第 %d/%d 条失败：%s" % (sent_pages + 1, total, fail_info)
        return n, (last_info if total == 1 else "已分 %d 条发完（%s）" % (total, last_info))

    if ch == "wechat_mp":
        _, content = render_short(pairs, title=title)
    else:
        content = render(title, pairs)
    ok, info = send(cfg, ch, title, content)
    return (len(pairs), info) if ok else (0, info)


def push_new(rows, new_ids, log=print):
    """一轮抓取后调用。返回 (sent_count, info)。

    两条腿并行（都可独立开关）：
      · **即时推送**（`pushImmediate`，默认开）—— 本轮一出现达标新车就立刻推一条
        「顺风车 · 新增 N 台好车」，这就是"每 10 分钟一条"。
      · **小时汇总**（`push_every_sec`，默认 3600）—— 同一批车同时攒进 `pendingIds`，
        满 1 小时再推一条「顺风车 · 近 1 小时汇总 N 台好车」。设 0 则关闭汇总。

    两条腿内容会重叠（汇总必然包含即时已推过的），这是**有意为之**：即时条用来抢时间，
    汇总条用来一眼看全这一小时。缓冲里存**整条车源记录**，中途下架的也能照常汇总。
    """
    cfg = load_config()
    if not cfg.get("enabled"):
        return 0, "push 未启用"
    ch = active_channel(cfg)
    if ch is None:
        return 0, "未配置可用通道（企业微信 wecomWebhook / 微信测试号 mp* / PushPlus token / WxPusher）"

    st = load_state()
    seen = set(st.get("sentIds") or [])
    fresh = [i for i in (new_ids or []) if i not in seen]
    st["lastFresh"] = len(fresh)
    st["lastFreshTiers"] = _tier_counts(rows, fresh)

    min_tier = int(cfg.get("min_tier") or DEFAULT_MIN_TIER)
    by_id = {r.get("id"): r for r in rows}

    # ---- ① 本轮达标的真新增：并入「待汇总缓冲区」，同时留一份给即时推送 ----
    pending = [r for r in (st.get("pendingIds") or [])
               if isinstance(r, dict) and r.get("id")]
    have = {r.get("id") for r in pending}
    round_new, buffered = [], set()
    for i in fresh:
        r = by_id.get(i)
        if not r or i in have:
            continue
        if tier(r.get("rank")) <= min_tier:
            pending.append(r)
            have.add(i)
            round_new.append(r)
            buffered.add(i)
    if len(pending) > 800:                       # 防无限增长（正常一小时远够）
        pending = pending[-800:]
    st["pendingIds"] = pending

    # 非达标（入门）的新增直接记入已见，往后不再参与任何判定
    plain = [i for i in fresh if i not in buffered]
    if plain:
        st["sentIds"] = list(dict.fromkeys((st.get("sentIds") or []) + plain))

    # ---- ② 节奏参数 ----
    imm = cfg.get("pushImmediate", True)
    if isinstance(imm, str):
        imm = imm.strip().lower() not in ("0", "false", "no", "off", "")
    imm = bool(imm)
    every = int(cfg.get("push_every_sec") or 0)
    now_ms = int(time.time() * 1000)

    st["lastImmediate"] = 0
    st["lastSummary"] = 0
    sent_total, notes = 0, []

    # ---- ③ 即时推送：本轮新到的达标车，立刻发一条 ----
    if imm and round_new:
        pairs = _mk_pairs(round_new, cfg)
        n, info = _deliver(cfg, ch, pairs, "顺风车 · 新增 %d 台好车" % len(pairs))
        st["lastImmediate"] = n
        sent_total += n
        if n:
            st["lastPushAt"] = now_ms
            st["lastImmediateItems"] = [_item_brief(t, r) for t, r in pairs]
            st["lastChannel"] = ch
            notes.append("即时 %d 台" % n)
        else:
            notes.append("即时推送失败：%s" % info)
        # 不论发没发成功都记已见：没发成功的已落在 pending 里，小时汇总会兜底
        st["sentIds"] = list(dict.fromkeys((st.get("sentIds") or []) + list(buffered)))

    # ---- ④ 小时汇总：到点就把缓冲区里这一小时的全部新车推一条 ----
    last_sum = int(st.get("lastSummaryAt") or 0)
    if every > 0 and not last_sum and imm and sent_total:
        last_sum = now_ms                          # 首轮已即时发过同样内容，锚点设到现在
        st["lastSummaryAt"] = last_sum
    due = every > 0 and bool(pending) and (not last_sum or now_ms - last_sum >= every * 1000)
    if due:
        pairs = _mk_pairs(pending, cfg)
        title = "顺风车 · %s汇总 %d 台好车" % (_label_of(every), len(pairs))
        n, info = _deliver(cfg, ch, pairs, title)
        st["lastSummary"] = n
        sent_total += n
        if n >= len(pairs):
            st["pendingIds"] = []
            st["lastSummaryAt"] = now_ms
            st["lastSummaryItems"] = [_item_brief(t, r) for t, r in pairs]
            notes.append("汇总 %d 台" % n)
        else:
            notes.append("汇总失败：%s（保留待补）" % info)
    elif every > 0:
        # 没到点时，顺手记一下下次汇总时间，/health 一眼可见
        if not st.get("lastSummaryAt"):
            st["lastSummaryAt"] = now_ms
        if pending:
            notes.append("已累计 %d 台待汇总" % len(pending))

    if every > 0:
        st["nextSummaryAt"] = int(st.get("lastSummaryAt") or now_ms) + every * 1000

    # ---- ⑤ 专线盯车：配置里指定的线路，本轮一冒头就**单独多推一条** ----
    # 与常规即时推送**有意重叠**（专线的作用就是把它单独拎出来提醒）；
    # 放在汇总之后调用，这样 sent_total 的变化不会影响上面的汇总锚点判定。
    # 只在 fresh 里找 —— 刚加专线时线上已有的存量车不会被翻出来推。
    watch_n = 0
    try:
        hits = watch_hit(cfg, rows, fresh)
    except Exception as exc:                             # noqa: BLE001
        hits = []
        notes.append("专线判定异常：%s" % exc)
    for rt, wpairs in hits:
        name = (rt.get("name") or "").strip() or "%s→%s" % (rt.get("from"), rt.get("to"))
        n, info = _deliver(cfg, ch, wpairs, "%s 专线 · 新增 %d 台" % (name, len(wpairs)))
        if n:
            watch_n += n
            sent_total += n
            st["lastWatchAt"] = int(time.time() * 1000)
            st["lastWatchRoute"] = name
            st["lastWatchItems"] = [_item_brief(t, r) for t, r in wpairs]
            notes.append("%s 专线 %d 台" % (name, n))
        else:
            notes.append("%s 专线失败：%s" % (name, info))

    save_state(st)

    if sent_total:
        log("推送完成：%s（%s）" % ("；".join(notes), ch))
    elif not notes:
        if fresh:
            notes.append("新增 %d 条，但无尊享/高级/中档档次" % len(fresh))
        else:
            notes.append("本轮无新增")
    return sent_total, "；".join(notes)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _probe(cfg):
    cands = []
    if _has_wecom(cfg):
        cands.append("wecom")
    if _has_mp(cfg):
        cands.append("wechat_mp")
    if cfg.get("token"):
        cands.append("pushplus")
    if _has_wx(cfg):
        cands.append("wxpusher")
    if not cands:
        print("✗ 四个通道都没配。请填 push-config.json 的：\n"
              "  · 企业微信 → wecomWebhook\n"
              "  · 微信测试号 → mpAppId / mpAppSecret / mpTemplateId / mpOpenIds\n"
              "  · 或 PushPlus → token\n"
              "  · 或 WxPusher → appToken + uids")
        return 1

    print("逐个通道探活（会真的发一条测试消息）：")
    for name in cands:
        if name == "wecom":
            ok, info = wecom_send(cfg.get("wecomWebhook"),
                                  "顺风车看板 · 通道探活\n企业微信群机器人通道正常 ✅",
                                  msgtype=cfg.get("wecomMsgType"))
        elif name == "wechat_mp":
            ok, info = wechat_mp_send(cfg, "顺风车看板 · 通道探活",
                                      "微信测试号通道正常")
        elif name == "pushplus":
            ok, info = pushplus_send(cfg["token"], "顺风车看板 · 通道探活",
                                     "<b>PushPlus 通道正常</b>")
        else:
            ok, info = wxpusher_send(cfg["appToken"], cfg["uids"],
                                     "顺风车看板 · 通道探活", "<b>WxPusher 通道正常</b>")
        print("  %-10s %s %s" % (name, "✓ 可用" if ok else "✗ 不可用", info))
    print("\n当前生效通道：%s" % (active_channel(cfg) or "（无）"))
    return 0


def _cli():
    arg = sys.argv[1] if len(sys.argv) > 1 else "--test"
    cfg = load_config()
    ch = active_channel(cfg)

    if arg == "--probe":
        return _probe(cfg)

    if arg == "--test":
        if ch is None:
            print("✗ 未找到可用通道。请填 push-config.json：\n"
                  "  · 企业微信 → wecomWebhook\n"
                  "  · 微信测试号 → mpAppId / mpAppSecret / mpTemplateId / mpOpenIds\n"
                  "  · 或 PushPlus → token\n"
                  "  · 或 WxPusher → appToken + uids")
            return 1
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        every = int(cfg.get("push_every_sec") or 0)
        _imm = cfg.get("pushImmediate", True)
        if isinstance(_imm, str):
            _imm = _imm.strip().lower() not in ("0", "false", "no", "off", "")
        _parts = []
        if _imm:
            _parts.append("一有新车就立刻推一条")
        if every > 0:
            _parts.append("每 %d 分钟再汇总一条" % (every // 60))
        cadence = "，".join(_parts) or "（推送已关闭）"
        if ch == "wecom":
            mt = str(cfg.get("wecomMsgType") or WECOM_MSGTYPE).strip().lower()
            title = "顺风车看板 · 推送测试"
            if mt == "markdown":
                content = ("## 顺风车看板 · 推送测试\n"
                           "推送链路已打通 ✅\n\n"
                           "> 发送时间：%s\n"
                           "> 之后每 10 分钟抓一轮，%s（只统计 尊享/高级/中档 的新车）。"
                           % (now, cadence))
            else:
                content = ("顺风车看板 · 推送测试\n"
                           "推送链路已打通 ✅（text 版，微信插件可正常显示）\n\n"
                           "发送时间：%s\n"
                           "之后每 10 分钟抓一轮，%s（只统计 尊享 / 高级 / 中档 的新车）。"
                           % (now, cadence))
        elif ch == "wechat_mp":
            title, content = "顺风车看板 · 推送测试", "推送链路已打通，发送时间 " + now
        else:
            title = "顺风车看板 · 推送测试"
            content = ('<div style="font-size:15px;line-height:1.7">'
                       '<b>推送链路测试</b><br>'
                       '如果你在微信里看到这条，说明「云端 → %s → 微信」已经打通了。<br>'
                       '<span style="color:#666">发送时间：%s</span></div>') % (ch, now)
        ok, info = send(cfg, ch, title, content)
        print(("✓ 发送成功（%s）：" % ch if ok else "✗ 发送失败（%s）：" % ch) + str(info))
        return 0 if ok else 1

    if arg in ("--dry", "--new"):
        try:
            j = json.load(open(DATA_FILE, encoding="utf-8"))
        except Exception as e:                                # noqa: BLE001
            print("✗ 读不到 data.json：%s" % e)
            return 1
        rows = j.get("items") or []
        ids = j.get("newIds") or []
        pairs = pick(rows, ids, int(cfg.get("min_tier") or DEFAULT_MIN_TIER))
        every = int(cfg.get("push_every_sec") or 0)
        _imm = cfg.get("pushImmediate", True)
        if isinstance(_imm, str):
            _imm = _imm.strip().lower() not in ("0", "false", "no", "off", "")
        st = load_state()
        pend = [r for r in (st.get("pendingIds") or []) if isinstance(r, dict)]
        last_sum = int(st.get("lastSummaryAt") or 0)
        print("生效通道：%s" % (ch or "（无）"))
        _ps = []
        if _imm:
            _ps.append("即时推（有新车立刻发）")
        if every > 0:
            _ps.append("每 %d 分钟汇总一条" % (every // 60))
        print("推送节奏：%s" % ("；".join(_ps) or "（全关）"))
        if every > 0:
            if last_sum:
                nxt = last_sum + every * 1000
                left = max(0, int((nxt - time.time() * 1000) / 60000))
                print("上次汇总：%s（约 %d 分钟后到点）"
                      % (time.strftime("%H:%M:%S", time.localtime(last_sum / 1000)), left))
            else:
                print("上次汇总：（还没推过，本轮到点即发）")
            print("待汇总缓冲区：%d 台" % len(pend))
            for r in pend:
                print("   [%s] %-18s ¥%s  %s→%s"
                      % (TIER_NAME.get(tier(r.get("rank"))), r.get("model"),
                         r.get("price"), r.get("from"), r.get("to")))
        print("data.json 共 %d 条，newIds %d 个" % (len(rows), len(ids)))
        print("本轮 newIds 里「尊享/高级/中档」档次 %d 条：" % len(pairs))
        for t, r in pairs:
            print("   [%s] %-18s ¥%s  %s→%s"
                  % (TIER_NAME[t], r.get("model"), r.get("price"),
                     r.get("from"), r.get("to")))
        if arg == "--dry":
            mt = str(cfg.get("wecomMsgType") or WECOM_MSGTYPE).strip().lower()
            pages, ranges = render_wecom_paged(pairs, cfg.get("mpUrl") or "", mt)
            print("\n--- 企业微信 %s 版（**实际发送用的就是这个**；共 %d 条消息，超长自动拆分）---"
                  % (mt, len(pages)))
            for i, p in enumerate(pages, 1):
                if len(pages) > 1:
                    print("  ↓↓↓ 第 %d/%d 条消息（覆盖第 %d-%d 台）↓↓↓"
                          % (i, len(pages), ranges[i - 1][0] + 1, ranges[i - 1][1]))
                print(p)
                print("  [本条 %d 字节，上限 %d]"
                      % (len(p.encode("utf-8")), WECOM_LIMIT.get(mt, 2048)))
            mp, _ = render_md_paged(pairs, cfg.get("mpUrl") or "")
            print("\n--- 对照：markdown 版（颜色好看，但**微信插件不显示**，仅企业微信客户端能看）---")
            print(mp[0][:500])
            print("\n--- 模板消息版（精简，会截断）---")
            t1, c1 = render_short(pairs)
            print(t1)
            print(c1)
            print("\n--- HTML 版（PushPlus / WxPusher）---")
            print(render("顺风车 · 新增 %d 台好车" % len(pairs), pairs)[:600])
        return 0

    print("用法：python push.py [--test|--dry|--new|--probe]")
    return 2


if __name__ == "__main__":
    sys.exit(_cli())

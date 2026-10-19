#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神州租车 apiproxy 加解密 / 请求工具
=====================================
逆向来源：微信小程序 wx33a69c09f340d3e6（神州租车）本地 wxapkg 包
  模块 45610  → 常量表（cid / AES key / 接口域名）
  模块 29170  → 请求封装：组包 C()、解包 h()
  模块 58855  → 签名 S()（导出名 Ur）

协议
----
  POST {BASE}{api}
    header  content-type : application/x-www-form-urlencoded
            appletEncrypt: appletEncrypt
    body    cid=801553&q=<AES密文>&sign=<签名>[&uid=<uid>]

  q      = AES-128-ECB/PKCS7( UTF8(JSON) ) -> base64 -> url-safe
           （+ -> - ，/ -> _ ，去掉尾部 =）
  sign   = MD5( "cid=801553;q=" + q + [";uid=" + uid] + "adsfe3636ttssdt" )
           取 digest 16 字节的 4 个大端 int32（取绝对值）拼成十进制字符串
  响应   {code, status, content, zeusId, uid, ...}
           code==1 && status=="SUCCESS" 时，content 用同一把 key 解密
           得到 {re, status, msg}

用法
----
  python zuche_api.py selftest                  # 本地往返自测（不联网）
  python zuche_api.py decrypt "<content>"       # 解开一段 content
  python zuche_api.py bruteforce "<content>"    # 不知道用哪把 key 时逐个试
  python zuche_api.py probe                     # 打一次免登录接口，验证链路
  python zuche_api.py call <api> '<json>'       # 带参数调用
"""

import base64
import hashlib
import json
import sys

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# --------------------------------------------------------------------------
# 常量（模块 45610）
# --------------------------------------------------------------------------
CID = "801553"                       # hp
KEY_TEXT = "adsfe3636ttssdt"         # ky  → AES/ECB/PKCS7 的密钥（15 字节，左对齐补 0x00）
BASE = "https://apiproxy.zuche.com"  # UE

# 左对齐补 0x00 到 16 字节（对应 JS initKey：WordArray.create(words, 16)）
KEY = KEY_TEXT.encode("utf-8").ljust(16, b"\x00")

# 同模块里出现的其它候选密钥——App 端若与小程序不同，用 bruteforce 逐个试
CANDIDATE_KEYS = {
    "ky (小程序主密钥)": KEY_TEXT,
    "Zq": "zuchewxxcx8#7@8!8m",
    "H_": "velMTKDfJmeAu4cUHBqFOuEa5wujPG6A",
    "mx": "d645fe1f193e93d6418f0b57fa7c67e1",
    "bV": "67cabc428f232a05f12a1ab5",
}


def _to_key(text: str) -> bytes:
    raw = text.encode("utf-8")[:16]
    return raw.ljust(16, b"\x00")


# --------------------------------------------------------------------------
# 对称加解密（模块 29170 里那个 AES 工具类）
# --------------------------------------------------------------------------
def aes_encrypt(plain: str, key: bytes = KEY) -> str:
    """UTF8 字符串 -> AES/ECB/PKCS7 -> base64 标准 -> url-safe 去填充"""
    raw = AES.new(key, AES.MODE_ECB).encrypt(pad(plain.encode("utf-8"), 16))
    b64 = base64.b64encode(raw).decode()
    return b64.replace("+", "-").replace("/", "_").rstrip("=")


def aes_decrypt(cipher: str, key: bytes = KEY) -> str:
    """url-safe base64 -> AES/ECB/PKCS7 -> UTF8 字符串"""
    s = cipher.strip().replace("-", "+").replace("_", "/")
    rem = 4 - len(s) % 4
    if rem < 4:
        s += "=" * rem
    raw = base64.b64decode(s)
    return unpad(AES.new(key, AES.MODE_ECB).decrypt(raw), 16).decode("utf-8")


# --------------------------------------------------------------------------
# 签名（模块 58855 的 S / 导出名 Ur）
# --------------------------------------------------------------------------
def gen_sign(q: str, uid: str = None) -> str:
    src = "cid=%s;q=%s" % (CID, q)
    if uid:
        src += ";uid=%s" % uid
    src += KEY_TEXT

    digest = hashlib.md5(src.encode("utf-8")).digest()

    def word(off: int) -> int:
        v = (digest[off] << 24) | (digest[off + 1] << 16) | (digest[off + 2] << 8) | digest[off + 3]
        if v >= 1 << 31:          # 还原 JS 的 int32 溢出
            v -= 1 << 32
        return abs(v)             # Math.abs

    return "%d%d%d%d" % (word(0), word(4), word(8), word(12))


# --------------------------------------------------------------------------
# 组包 / 解包
# --------------------------------------------------------------------------
def build_form(data: dict = None, uid: str = None, bucket_id_list=None) -> dict:
    payload = dict(data or {})
    if bucket_id_list is not None:
        payload["bucketIdList"] = bucket_id_list
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    q = aes_encrypt(body)
    form = {"cid": CID, "q": q, "sign": gen_sign(q, uid)}
    if uid:
        form["uid"] = uid
    return form


def decrypt_content(content, key: bytes = KEY):
    """content 可能是 str（密文）或已是 dict（明文），统一返回 dict/str"""
    if not content:
        return content
    if isinstance(content, (dict, list)):
        return content

    text = aes_decrypt(content, key)
    if text == "":
        return ""
    try:
        return json.loads(text)
    except ValueError:
        return text


def unwrap(resp: dict, key: bytes = KEY):
    """完整响应对象 -> 业务数据 {re, status, msg}"""
    if not isinstance(resp, dict):
        return resp
    if resp.get("code") == 1 and resp.get("status") == "SUCCESS":
        return decrypt_content(resp.get("content"), key)
    return resp


# --------------------------------------------------------------------------
# 网络调用
# --------------------------------------------------------------------------
def request(api: str, data: dict = None, uid: str = None, key: bytes = KEY,
            timeout: int = 20, debug: bool = False):
    import requests

    # Git Bash (MSYS) 会把 /action/... 当路径转换，这里兜一下
    for marker in ("/action/", "/resource/"):
        pos = api.find(marker)
        if pos > 0:
            api = api[pos:]
            break
    if not api.startswith("/"):
        api = "/" + api
    form = build_form(data, uid)
    if debug:
        print("[请求] POST %s%s" % (BASE, api))
        print("[参数] %s" % json.dumps(form, ensure_ascii=False)[:400], file=sys.stderr)

    r = requests.post(
        BASE + api,
        data=form,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "appletEncrypt": "appletEncrypt",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    raw = r.json()
    if debug:
        print("[原始] %s" % json.dumps(raw, ensure_ascii=False)[:400], file=sys.stderr)
    return unwrap(raw, key)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _cmd_selftest():
    print("KEY = %r  (%d bytes)" % (KEY, len(KEY)))
    samples = [
        '{"re":{"list":[{"cityId":1,"name":"北京"}]},"status":0,"msg":"成功"}',
        '{"pageSize":20,"cityId":1}',
        "",
    ]
    ok = True
    for s in samples:
        q = aes_encrypt(s)
        back = aes_decrypt(q)
        good = back == s
        ok = ok and good
        print("  %s  q=%-58s %s" % ("OK " if good else "BAD", q[:58], repr(back)[:40]))
    print("签名样例 sign('ABC') = %s" % gen_sign("ABC"))
    print("往返自测：%s" % ("通过" if ok else "失败"))
    return 0 if ok else 1


def _cmd_decrypt(arg):
    content = arg
    if content.startswith("@"):
        content = open(content[1:], encoding="utf-8").read().strip()
    obj = decrypt_content(content)
    print(json.dumps(obj, ensure_ascii=False, indent=2) if not isinstance(obj, str) else obj)
    return 0


def _cmd_bruteforce(arg):
    content = arg
    if content.startswith("@"):
        content = open(content[1:], encoding="utf-8").read().strip()
    for name, text in CANDIDATE_KEYS.items():
        try:
            out = aes_decrypt(content, _to_key(text))
            print("[命中] %-18s key=%r" % (name, text))
            print(out[:600])
            return 0
        except Exception as exc:                       # noqa: BLE001
            print("[  -  ] %-18s %s" % (name, type(exc).__name__))
    print("没有候选密钥能解开。App 端可能换了 key，需要重新从 App 包里取。")
    return 1


def _cmd_probe():
    for api in ("/action/carrctapi/order/hometab/v5",
                "/action/carrctapi/order/getTimePickerThreshold/v1"):
        print("=== %s ===" % api)
        try:
            out = request(api, {}, debug=True)
            print(json.dumps(out, ensure_ascii=False)[:800])
            print(">>> 明文解出 = 算法完全正确\n")
            return 0
        except Exception as exc:                       # noqa: BLE001
            print("失败：%s: %s\n" % (type(exc).__name__, exc))
    return 1


def _cmd_call(argv):
    api = argv[0]
    data = json.loads(argv[1]) if len(argv) > 1 else {}
    uid = argv[2] if len(argv) > 2 else None
    out = request(api, data, uid, debug=True)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 0
    cmd, rest = argv[1], argv[2:]
    if cmd == "selftest":
        return _cmd_selftest()
    if cmd == "decrypt":
        return _cmd_decrypt(rest[0])
    if cmd == "bruteforce":
        return _cmd_bruteforce(rest[0])
    if cmd == "probe":
        return _cmd_probe()
    if cmd == "call":
        return _cmd_call(rest)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

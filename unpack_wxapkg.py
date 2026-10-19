#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信 PC 端（Weixin 4.x）小程序包 .wxapkg 解包器
==============================================
实测环境：Weixin 4.0 / Windows / 包目录
  %APPDATA%\\Tencent\\xwechat\\radium\\users\\<hash>\\applet\\packages\\<appid>\\<ver>\\*.wxapkg

包格式（实测）
--------------
  [0:6]        b'V1MMWX'  —— 容器标记，明文
  [6:~1060]    不透明元数据块（不是简单异或，实测任意单字节 XOR 都不可读，应为加密/校验块）
  [~1060:]     XOR 单字节加密的负载；本项目实测密钥恒为 0x65
               负载内部是类 wxapkg 结构：若干条 [nameLen:u32BE][name][offset:u32BE][size:u32BE] 索引 + 文件体

用法
----
  python unpack_wxapkg.py <包目录或.wxapkg> [输出目录]
  python unpack_wxapkg.py --dump <dir>        # 只导出解密后的整块负载（推荐，便于 grep）

依赖：标准库
"""

import os
import re
import sys
import glob

TOKENS = [b"function", b"pages/", b".wxml", b"require(", b"app-service"]
HEADER_LEN = 1060
DEFAULT_KEY = 0x65


def find_key(buf: bytes) -> int:
    """用可读性打分爆破单字节 XOR 密钥"""
    best, best_key = -1, DEFAULT_KEY
    for k in range(256):
        d = bytes(b ^ k for b in buf)
        score = sum(d.count(t) for t in TOKENS)
        if score > best:
            best, best_key = score, k
    return best_key


def decrypt(buf: bytes) -> bytes:
    if buf[:6] != b"V1MMWX":
        return buf
    key = find_key(buf[HEADER_LEN:])
    return bytes(b ^ key for b in buf)


def entry_at(d: bytes, p: int):
    if p + 12 > len(d):
        return None
    nl = int.from_bytes(d[p:p + 4], "big")
    if not (0 < nl <= 512):
        return None
    nm = d[p + 4:p + 4 + nl]
    if len(nm) != nl or not all(32 <= c < 127 for c in nm):
        return None
    off = int.from_bytes(d[p + 4 + nl:p + 8 + nl], "big")
    size = int.from_bytes(d[p + 8 + nl:p + 12 + nl], "big")
    return nm.decode(), off, size, p + 12 + nl


def parse_index(d: bytes):
    """扫描所有能连成链的索引段，遇到断点就向后跳一段继续"""
    files = {}
    p, guard = HEADER_LEN, 0
    while p + 12 < len(d) and guard < 5_000_000:
        guard += 1
        e = entry_at(d, p)
        if e:
            name, off, size, nxt = e
            if off + size <= len(d):
                files.setdefault(name, (off, size))
            p = nxt
            continue
        # 断点：向后找下一个能连成至少 3 条的起点
        jumped = False
        for q in range(p + 1, min(len(d) - 12, p + 4096)):
            if not entry_at(d, q):
                continue
            cur, n = q, 0
            while n < 3:
                x = entry_at(d, cur)
                if not x:
                    break
                cur, n = x[3], n + 1
            if n >= 3:
                p = q
                jumped = True
                break
        if not jumped:
            break
    return files


def unpack_one(path: str, outdir: str, dump_only: bool = False) -> int:
    buf = open(path, "rb").read()
    d = decrypt(buf)
    appid = os.path.basename(os.path.dirname(os.path.dirname(path)))
    tag = "%s__%s" % (appid, os.path.basename(path))

    if dump_only:
        os.makedirs(outdir, exist_ok=True)
        op = os.path.join(outdir, tag + ".plain")
        open(op, "wb").write(d)
        print("  %-44s -> %s (%d bytes)" % (os.path.basename(path), op, len(d)))
        return 1

    files = parse_index(d)
    if not files:
        os.makedirs(outdir, exist_ok=True)
        open(os.path.join(outdir, tag + ".plain"), "wb").write(d)
        print("  %-44s 索引解析失败，已导出整块负载" % os.path.basename(path))
        return 0

    base = os.path.join(outdir, tag)
    n = 0
    for name, (off, size) in files.items():
        rel = name.lstrip("/")
        fp = os.path.join(base, rel)
        if ".." in rel:
            continue
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, "wb").write(d[off:off + size])
        n += 1
    print("  %-44s -> %d 个文件  %s" % (os.path.basename(path), n, base))
    return n


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 0
    dump_only = argv[1] == "--dump"
    target = argv[2] if dump_only else argv[1]
    outdir = argv[3] if dump_only and len(argv) > 3 else (
        argv[2] if len(argv) > 2 else os.path.join(os.getcwd(), "wxapkg_out"))

    paths = ([target] if target.lower().endswith(".wxapkg")
             else sorted(glob.glob(os.path.join(target, "**", "*.wxapkg"), recursive=True)))
    if not paths:
        print("没找到 .wxapkg")
        return 1

    print("共 %d 个包，输出目录 %s\n" % (len(paths), outdir))
    total = 0
    for p in paths:
        try:
            total += unpack_one(p, outdir, dump_only)
        except Exception as exc:                       # noqa: BLE001
            print("  %-44s 失败：%s" % (os.path.basename(p), exc))
    print("\n完成，累计 %d" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

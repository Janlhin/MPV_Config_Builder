# -*- coding: utf-8 -*-
"""把版本号从**唯一来源**刷到需要它的地方。

## 为什么要有它

版本号原来写在两个地方，得手改：

    core/schema.py            VERSION = "0.1.0"     ← 软件里显示的
    electron/package.json     "version": "0.1.0"    ← 打包时用的（安装包文件名）

只改一处的话，会出现「安装包叫 0.2.0-Setup.exe，但软件里显示 0.1.0」——
**两边都看起来正常**，特别难发现。

现在：`core/schema.py` 是唯一来源，改完跑这个脚本，剩下的地方自动跟上。
`tests/test_version.py` 有一条测试钉住两边相等，忘了跑脚本会红。

## 用法

    py tools/sync_version.py          # 同步
    py tools/sync_version.py --check  # 只检查，不改（CI / preflight 用）

## 版本号规则（2026-09-14 定）

    小更新（改文案、修 bug）  0.1.0 → 0.1.1 → 0.1.2
    大更新（加功能）          0.1.x → 0.2.0 → 0.3.0
    觉得能正式推荐给别人了     0.x   → 1.0.0
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.schema import VERSION                                    # noqa: E402

PKG = ROOT / "electron" / "package.json"


def read_pkg_version():
    """读 package.json 里的 version —— 用正则而不是 json.loads。

    为什么不用 json.loads 再 dump 回去：那会把整个文件的缩进、键序、
    以及 npm 自己写进去的字段全部重排一遍，diff 会变成几十行噪音。
    我们只改一个字段，就只动那一行。
    """
    text = PKG.read_text(encoding="utf-8")
    m = re.search(r'^(\s*)"version"\s*:\s*"([^"]*)"', text, re.M)
    if not m:
        return None, None, text
    return m.group(2), m, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查，不写盘")
    args = ap.parse_args()

    if not PKG.is_file():
        print(f"❌ 找不到 {PKG}")
        return 1

    cur, m, text = read_pkg_version()
    if cur is None:
        print(f"❌ {PKG} 里没有 version 字段")
        return 1

    print(f"  唯一来源 core/schema.py : {VERSION}")
    print(f"  electron/package.json   : {cur}")

    if cur == VERSION:
        print("\n✅ 已经一致，不用改")
        return 0

    if args.check:
        print(f"\n❌ 不一致（差了 {cur} → {VERSION}）")
        print("   跑一下：py tools/sync_version.py")
        return 1

    new_text = text[:m.start(2)] + VERSION + text[m.end(2):]
    PKG.write_text(new_text, encoding="utf-8", newline="")
    print(f"\n✅ 已同步 package.json：{cur} → {VERSION}")

    # 复核：真的写进去了吗
    again, _, _ = read_pkg_version()
    if again != VERSION:
        print(f"❌ 写进去了但读出来是 {again}，有问题")
        return 1
    print("   复核通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

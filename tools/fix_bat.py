# -*- coding: utf-8 -*-
"""把 .bat 统一成 Windows 批处理该有的样子：UTF-8 BOM + CRLF。

⚠ 为什么需要它，而不是靠编辑器/git：
  · **CRLF**：Windows 批处理要 CRLF，LF 行为不可靠；
  · **UTF-8 BOM**：文件里有中文 echo，而 `chcp 65001` 要等执行到那一行才生效
    —— 没有 BOM 的话，chcp 之前那行中文已经乱码了。
  · 而且 `.gitattributes` 里写的是 `*.bat text eol=crlf`，git 检出时会转 CRLF，
    但 **BOM 它不管** —— 所以 BOM 必须由文件本身带着。

模型工具（write / edit）写出的是 LF、无 BOM 的 UTF-8，
所以**每次用工具改过 .bat 之后都要跑一遍这个**。

用法：py tools/fix_bat.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"


def fix(p):
    raw = p.read_bytes()
    text = raw.decode("utf-8-sig")                       # 有 BOM 会自动剥掉
    body = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    p.write_bytes(BOM + body)
    b = p.read_bytes()
    lf = b.count(b"\n") - b.count(b"\r\n")
    return b[:3] == BOM, b.count(b"\r\n"), lf


def main():
    targets = sorted(ROOT.glob("*.bat")) + sorted(ROOT.glob("*/*.bat"))
    bad = []
    for p in targets:
        bom, crlf, lf = fix(p)
        ok = bom and lf == 0
        rel = p.relative_to(ROOT)
        print(f"  {'✅' if ok else '❌'} {rel}  BOM={bom} CRLF={crlf} 裸LF={lf}")
        if not ok:
            bad.append(str(rel))
    if bad:
        print(f"\n❌ 还有 {len(bad)} 个没弄好")
        return 1
    print(f"\n✅ {len(targets)} 个 .bat 都是 BOM + CRLF")
    return 0


if __name__ == "__main__":
    sys.exit(main())

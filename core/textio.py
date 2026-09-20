# -*- coding: utf-8 -*-
"""文本读写：编码探测 + 按原编码写回。

mpv.conf 在 Windows 上不保证是 UTF-8：老配置常见 GBK/GB18030，偶尔 Big5。
以前全程 utf-8 读、utf-8 写，结果是「读进来是乱码，写回去还把文件改成 UTF-8」——
用户的注释就这么毁了。这个模块负责：

    1. 读：BOM → UTF-8 → GB18030 → Big5 → 最后才 utf-8 + replace（并标记有损）
    2. 记住原编码 / BOM / 换行风格
    3. 写：按原编码写回（新文件默认 UTF-8 无 BOM）
"""
import codecs
from datetime import datetime
from pathlib import Path

try:                                    # Python 3.8+
    from typing import NamedTuple
except ImportError:                     # pragma: no cover
    NamedTuple = None

BOMS = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)

# 无 BOM 时的尝试顺序：中文 Windows 上 gb18030 覆盖面最广
FALLBACKS = ("gb18030", "big5")

# 这些控制字符出现在纯文本配置里基本说明解错了
_BAD_CHARS = set(range(0x00, 0x09)) | {0x0b, 0x0c} | set(range(0x0e, 0x20)) | {0xfffd}


class TextFile:
    """一个读进来的文本文件：内容 + 还原它需要知道的全部信息。"""

    def __init__(self, text, encoding="utf-8", bom=False, newline="\n",
                 lossy=False, size=0, path="", raw=None):
        self.text = text
        self.encoding = encoding
        self.bom = bom
        self.newline = newline
        self.lossy = lossy          # True = 有字节没能正确解码（会丢内容）
        self.size = size
        self.path = path
        self.raw = raw if raw is not None else text.encode("utf-8", "replace")

    def __repr__(self):
        return (f"<TextFile {Path(self.path).name if self.path else '?'} "
                f"{self.encoding}{'+bom' if self.bom else ''} "
                f"{'有损 ' if self.lossy else ''}{self.size}B>")

    @property
    def encoding_label(self):
        name = {"utf-8-sig": "UTF-8 (BOM)", "utf-8": "UTF-8",
                "gb18030": "GBK / GB18030", "big5": "Big5"}.get(self.encoding, self.encoding)
        if self.lossy:
            name += " · 有字节无法解码"
        return name


def _score(text):
    """解出来的文本有多可疑：可疑字符越少越好。"""
    return sum(1 for ch in text if ord(ch) in _BAD_CHARS)


def sniff(raw):
    """猜编码，返回 (编码, 是否有损)。永远不抛异常。"""
    for bom, enc in BOMS:
        if raw.startswith(bom):
            try:
                raw.decode(enc)
                return enc, False
            except UnicodeDecodeError:
                continue
    try:
        raw.decode("utf-8")
        return "utf-8", False
    except UnicodeDecodeError:
        pass
    best = None
    for enc in FALLBACKS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        bad = _score(text)
        if best is None or bad < best[1]:
            best = (enc, bad)
        if bad == 0:
            break
    if best is not None:
        return best[0], False
    return "utf-8", True


def decode(raw, encoding=None):
    """按指定或猜出来的编码解码，返回 TextFile。"""
    if encoding:
        lossy = False
        bom = False
        if encoding == "utf-8-sig":
            bom, encoding = True, "utf-8"
            raw = raw[len(codecs.BOM_UTF8):] if raw.startswith(codecs.BOM_UTF8) else raw
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            text, lossy = raw.decode(encoding or "utf-8", "replace"), True
    else:
        encoding, lossy = sniff(raw)
        bom = encoding == "utf-8-sig"
        if bom:
            # utf-8-sig 会顺手把 BOM 吃掉，别让它留在正文里
            text = raw.decode("utf-8-sig", "replace" if lossy else "strict")
            encoding = "utf-8"
        elif encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
            bom = True
            text = raw.decode(encoding, "replace" if lossy else "strict")
        else:
            text = raw.decode(encoding, "replace" if lossy else "strict")
    newline = "\r\n" if "\r\n" in text else "\n"
    return TextFile(text, encoding, bom, newline, lossy, len(raw), raw=raw)


def read(path, encoding=None):
    """读文件；文件不存在或读不了返回 None。"""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    tf = decode(raw, encoding)
    tf.path = str(p)
    return tf


def read_text(path, encoding=None, default=""):
    """只要文本内容时的快捷方式。"""
    tf = read(path, encoding)
    return tf.text if tf is not None else default


def encode(text, encoding="utf-8", bom=False, newline=None):
    """把文本编回字节。newline 只影响换行归一化。"""
    if newline:
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
    if encoding == "utf-8" and bom:
        return codecs.BOM_UTF8 + text.encode("utf-8")
    if encoding == "utf-8-sig":
        return codecs.BOM_UTF8 + text.encode("utf-8")
    if encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
        return text.encode(encoding)      # utf-16/32 的 BOM 由 codec 自己处理
    try:
        return text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        # 原文是 GBK，但用户新加了 GBK 编不出来的字（比如 emoji）：退回 utf-8 更安全
        return text.encode("utf-8")


def backup(path):
    """备份文件（*.bak-时间戳），返回备份路径；文件不存在返回 None。

    时间戳用**毫秒**精度并带防撞序号：秒级精度下，同一秒内连点两次「应用」
    会让第二次的备份把第一次覆盖掉 —— 安全网本身失效，而这工具最大的卖点
    就是"写前一定备份"。
    """
    p = Path(path)
    if not p.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]   # 到毫秒
    dst = p.with_name(p.name + f".bak-{stamp}")
    if dst.exists():                       # 极端情况（同毫秒）再加序号
        n = 2
        while dst.exists() and n < 1000:
            dst = p.with_name(p.name + f".bak-{stamp}-{n}")
            n += 1
    dst.write_bytes(p.read_bytes())
    return dst


def write(path, text, encoding="utf-8", bom=False, newline="\n", do_backup=True):
    """按指定编码写回，返回备份路径（没备份就是 None）。"""
    p = Path(path)
    bak = backup(p) if do_backup else None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(encode(text, encoding, bom, newline))
    return bak

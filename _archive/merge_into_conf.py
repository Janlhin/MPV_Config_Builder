# -*- coding: utf-8 -*-
"""把 mpv-lazy 当前 mpv.conf 的选项合并进桌面 mpv1.conf（原地、最小改动）。"""
import re
import shutil
from datetime import datetime
from pathlib import Path

TARGET = Path(r"C:\Users\Janlhin\Desktop\mpv1.conf")
SOURCE = Path(r"C:\Program Files\mpv-lazy\portable_config\mpv.conf")

# 1) 备份
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup = TARGET.with_name(TARGET.name + f".bak-{stamp}")
shutil.copy2(TARGET, backup)

raw = TARGET.read_bytes()
has_bom = raw.startswith(b"\xef\xbb\xbf")
text = raw.decode("utf-8-sig")
newline = "\r\n" if "\r\n" in text else "\n"
lines = text.splitlines()

# 2) 读取要写入的配置
gvals = {}
for ln in SOURCE.read_text(encoding="utf-8-sig", errors="replace").splitlines():
    s = ln.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    gvals[k.strip()] = v.strip()

key_re = re.compile(r"^\s*(#?)\s*([A-Za-z0-9_.\-]+)\s*=")

def find_line(key, active):
    for i, ln in enumerate(lines):
        m = key_re.match(ln)
        if m and m.group(2) == key:
            if active and not m.group(1):
                return i
            if not active and m.group(1):
                return i
    return None

def indent_of(s):
    return s[: len(s) - len(s.lstrip())]

applied = []
appended = []
handled = set()

# 3) glsl-shaders：原文件是 glsl-shaders-append，特殊处理
if "glsl-shaders" in gvals:
    idx = find_line("glsl-shaders-append", True)
    if idx is not None:
        ind = indent_of(lines[idx])
        lines[idx] = ind + "#" + lines[idx].lstrip()
        lines.insert(idx + 1, ind + "glsl-shaders = " + gvals["glsl-shaders"])
        applied.append("glsl-shaders（注释掉原 append 行，新增 glsl-shaders）")
    else:
        idx = find_line("glsl-shaders", True)
        if idx is not None:
            ind = indent_of(lines[idx])
            lines[idx] = ind + "glsl-shaders = " + gvals["glsl-shaders"]
            applied.append("glsl-shaders（替换原行）")
        else:
            appended.append(("glsl-shaders", gvals["glsl-shaders"]))
    handled.add("glsl-shaders")

# 4) 其余键：优先替换已启用行，其次替换被注释的同名行，找不到才追加
for k, v in gvals.items():
    if k in handled:
        continue
    idx = find_line(k, True)
    if idx is None:
        idx = find_line(k, False)
    if idx is not None:
        old = lines[idx].strip()
        ind = indent_of(lines[idx])
        new_line = ind + f"{k} = {v}"
        if old != new_line.strip():
            lines[idx] = new_line
            applied.append(f"{k}: {old} -> {new_line.strip()}")
    else:
        appended.append((k, v))

# 5) 追加缺失项
if appended:
    lines += [
        "",
        " ####################",
        " # 由 MPV Config Builder 写入 #",
        " ####################",
        "",
    ]
    for k, v in appended:
        lines.append(f" {k} = {v}")
    lines.append("")

out = newline.join(lines) + newline
TARGET.write_bytes(out.encode("utf-8-sig" if has_bom else "utf-8"))

print("BACKUP:", backup)
print("APPLIED:")
for x in applied:
    print("  -", x)
print("APPENDED:")
for k, v in appended:
    print("  -", f"{k} = {v}")
print("BOM:", has_bom, "NEWLINE:", repr(newline), "LINES:", len(lines))

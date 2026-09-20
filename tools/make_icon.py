# -*- coding: utf-8 -*-
"""生成应用图标 electron/build/icon.ico（多尺寸，零依赖手写 PNG + ICO 封装）。

## 为什么要自己画

electron-builder 不给图标就用 Electron 默认图标，一眼看过去像"没做完的 Demo"。
但要为这个去装 Pillow 又违背本项目的零依赖习惯（构建期也不想加）。
所以这里手写：标准库 `zlib` + `struct` 就能产出合法 PNG，而 ICO 允许直接内嵌 PNG。

## 画的是什么

深色圆角底 + 蓝紫渐变 + 中间的播放三角 —— 和界面的配色一致
（界面主色 `--accent: #6aa8ff`）。
小尺寸（16/24）下细节会糊，所以三角按尺寸等比缩放，不做像素级微调 ——
16px 下能认出是"播放"就够了。

用法：
    py tools/make_icon.py
产物：
    electron/assets/icon.ico    （多尺寸，给 electron-builder / 窗口图标）
    electron/assets/icon.png    （256px，给 README / 商店页）

⚠ 目录叫 `assets/` 而不是 `build/`：`.gitignore` 里的 `build/` 是**任意层级**匹配，
会把 `electron/build/` 一起忽略掉 —— 图标是源材料，必须入库。
（同一个坑在 packaging/backend.spec 上也踩过一次。）
"""
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "electron" / "assets"

# 界面主色（style.css 的 --accent / --accent-2）
ACCENT = (106, 168, 255)
ACCENT2 = (150, 120, 255)
BG_TOP = (26, 31, 43)
BG_BOT = (16, 19, 25)

# 各尺寸都做一份：Windows 会在不同场合挑不同尺寸（任务栏 32、桌面 48、Alt+Tab 48…）
SIZES = [16, 24, 32, 48, 64, 128, 256]


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rounded_alpha(x, y, n, radius_ratio=0.22):
    """圆角矩形的覆盖率（0..1）。用简单的距离场做 1px 抗锯齿。

    Windows 11 的图标习惯是圆角，直角会显得很旧。
    """
    r = n * radius_ratio
    # 到最近圆角圆心的距离
    cx = min(max(x + 0.5, r), n - r)
    cy = min(max(y + 0.5, r), n - r)
    d = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
    if (x + 0.5) > r and (x + 0.5) < n - r:
        d = abs(y + 0.5 - cy)
    elif (y + 0.5) > r and (y + 0.5) < n - r:
        d = abs(x + 0.5 - cx)
    return max(0.0, min(1.0, r - d + 0.5))


def _play_triangle(x, y, n):
    """播放三角的覆盖率（0..1）。等腰、朝右、居中略偏右（视觉重心）。"""
    # 三角形顶点（相对坐标）
    left = 0.34 * n
    right = 0.72 * n
    top = 0.27 * n
    bottom = 0.73 * n
    mid_y = (top + bottom) / 2
    if x < left or x > right:
        return 0.0
    t = (x - left) / (right - left)
    # 该 x 处的上下边界（从 full 高度收敛到 0）
    half = (bottom - top) / 2 * (1 - t)
    dy = abs(y + 0.5 - mid_y)
    return max(0.0, min(1.0, half - dy + 0.5))


def render(n):
    """渲染一张 n×n 的 RGBA 像素表。"""
    rows = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            a_rect = _rounded_alpha(x, y, n)
            if a_rect <= 0:
                row += bytes((0, 0, 0, 0))
                continue
            # 底：竖直渐变
            bg = _lerp(BG_TOP, BG_BOT, y / max(1, n - 1))
            # 三角：水平渐变（左 accent → 右 accent2），让它有点体积感
            tri = _play_triangle(x, y, n)
            if tri > 0:
                col = _lerp(ACCENT, ACCENT2, (x / max(1, n - 1)))
                r = round(bg[0] * (1 - tri) + col[0] * tri)
                g = round(bg[1] * (1 - tri) + col[1] * tri)
                b = round(bg[2] * (1 - tri) + col[2] * tri)
            else:
                r, g, b = bg
            row += bytes((r, g, b, round(255 * a_rect)))
        rows.append(bytes(row))
    return rows


def png_bytes(n, rows):
    """把像素表编成 PNG（8 位 RGBA，无交错）。"""
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico_bytes(entries):
    """把若干 (尺寸, PNG 字节) 封成 ICO。

    ICO 格式允许每个条目直接内嵌 PNG（Vista 之后都支持），所以不用写 BMP 那套。

        头部  6 字节：reserved(0) type(1=icon) count
        目录  每项 16 字节：宽 高 调色板 保留 平面 位深 数据长度 数据偏移
              宽高为 0 表示 256（一个字节存不下 256）
    """
    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    dir_entries, blobs = b"", b""
    for size, data in entries:
        dim = 0 if size >= 256 else size
        dir_entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                                   len(data), offset)
        blobs += data
        offset += len(data)
    return header + dir_entries + blobs


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for n in SIZES:
        data = png_bytes(n, render(n))
        entries.append((n, data))
        print(f"  {n:>3}px  {len(data):>6} 字节")

    ico = ico_bytes(entries)
    (OUT_DIR / "icon.ico").write_bytes(ico)
    (OUT_DIR / "icon.png").write_bytes(png_bytes(256, render(256)))
    print(f"\n已写出 {OUT_DIR / 'icon.ico'}（{len(ico)} 字节，{len(SIZES)} 个尺寸）")
    print(f"已写出 {OUT_DIR / 'icon.png'}（256px）")


if __name__ == "__main__":
    main()

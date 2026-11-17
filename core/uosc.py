# -*- coding: utf-8 -*-
"""uosc.conf：mpv 界面脚本 uosc 的设置读写。

为什么单独一个模块：`mpv.conf` 管的是「播放行为」，`input.conf` 管的是「按键」，
而进度条粗细、控制栏放哪些按钮、顶栏标题、配色这些**界面长相**，全在
`script-opts/uosc.conf` 里。前两类本工具已经有了，这一类一直是空白。

三条规矩，都是踩过的坑：

① **不认识的行一律原样保留**。uosc.conf 里可能有中文注释、有本工具不认识的
   新版本键、有人手写的奇怪空格。只改用户动过的那几行，其余一个字节都不碰 ——
   「保存一次把注释吃掉了」是最难原谅的 bug。

② **按原编码写回**。uosc.conf 通常是 UTF-8，但用户手工编辑过后可能是 GBK；
   读进来就记住编码 / BOM / 换行，写回照原样（见 `core/textio.py`）。

③ **写前备份、原子替换**。跟 mpv.conf 一样走 `textio.write`（备份 + 原子写），
   写到一半断电也不会留下半截文件。

选项元数据（分类 / 类型 / 默认值 / 中文说明）取自 uosc 官方默认 `uosc.conf`
（`src/uosc.conf`，HEAD 版），不猜、不编。
"""
from pathlib import Path

from . import textio

# ---------------------------------------------------------------- 选项元数据
#
# type：bool（yes/no 开关）/ enum（下拉）/ number（数字）/ text（文本）
# group：界面上的分类导航，共 9 类。

GROUPS = [
    ("timeline", "⏱️ 时间轴", "进度条上方的时间轴：样式、粗细、缓存条与章节热力图"),
    ("progress", "📏 进度条", "未使用时间轴时那条细进度条"),
    ("controls", "🎛️ 控制栏", "控制栏上有哪些按钮、多高、间距"),
    ("volume", "🔊 音量与倍速", "音量条与倍速控件"),
    ("menu", "📋 菜单", "右键菜单 / 选轨菜单的尺寸与搜索"),
    ("topbar", "🪟 顶栏与窗口", "顶部标题栏、窗口边框"),
    ("look", "🎨 外观", "整体缩放、字体、圆角、配色、动画"),
    ("files", "🗂️ 文件与目录", "识别哪些扩展名、打开目录、删除方式"),
    ("misc", "💬 章节 · 语言 · 字幕", "章节区间、界面语言、字幕下载目录"),
]

# (key, group, type, default, 中文说明, choices)
OPTIONS = [
    # ---- 时间轴
    ("timeline_style", "timeline", "enum", "line",
     "时间轴样式：line 细线 / bar 粗条", ("line", "bar")),
    ("timeline_line_width", "timeline", "number", "2",
     "line 样式下时间轴线的粗细（像素）", None),
    ("timeline_size", "timeline", "number", "40",
     "时间轴完全展开时的高度（像素），0 = 不显示", None),
    ("timeline_persistency", "timeline", "text", "",
     "这些状态下时间轴常显，逗号分隔：paused / audio / image / video / idle / windowed / fullscreen", None),
    ("timeline_border", "timeline", "number", "1",
     "时间轴上方分隔线的粗细（像素）", None),
    ("timeline_step", "timeline", "text", "5",
     "在时间轴上滚轮时，每格跳多少秒；加 `!` 后缀表示精确跳转（如 5!）", None),
    ("timeline_cache", "timeline", "bool", "yes",
     "在时间轴上显示流媒体的缓冲进度", None),
    ("timeline_heatmap", "timeline", "enum", "overlay",
     "YouTube 视频的热力图：overlay 叠在轴上 / above 画在轴上方 / no 关闭", ("overlay", "above", "no")),
    ("timeline_mbtn_right", "timeline", "text", "",
     "在时间轴上按鼠标右键时执行的命令；`{time}` 会替换成当前秒数", None),
    # ---- 进度条
    ("progress", "progress", "enum", "windowed",
     "细进度条什么时候显示：windowed 窗口 / fullscreen 全屏 / always 总是 / never 从不",
     ("windowed", "fullscreen", "always", "never")),
    ("progress_size", "progress", "number", "2",
     "细进度条的粗细（像素）", None),
    ("progress_line_width", "progress", "number", "20",
     "细进度条的圆角宽度（像素）", None),
    # ---- 控制栏
    ("controls", "controls", "text",
     "menu,gap,subtitles,audio,speed,space,shuffle,loop-playlist,loop-file,gap,prev,items,next,gap,fullscreen",
     "控制栏上按顺序摆哪些按钮（逗号分隔的规格串，支持缩写、command:、toggle:、cycle: 等写法）", None),
    ("controls_size", "controls", "number", "32",
     "控制栏按钮的大小（像素）", None),
    ("controls_margin", "controls", "number", "8",
     "控制栏与时间轴之间的留白（像素）", None),
    ("controls_spacing", "controls", "number", "2",
     "控制栏按钮之间的间距（像素）", None),
    ("controls_persistency", "controls", "text", "",
     "这些状态下控制栏常显；取值同 timeline_persistency", None),
    # ---- 音量与倍速
    ("volume", "volume", "enum", "right",
     "音量条放哪侧：right 右 / left 左 / none 不显示", ("right", "left", "none")),
    ("volume_size", "volume", "number", "40",
     "音量条的高度（像素）", None),
    ("volume_border", "volume", "number", "1",
     "音量条分隔线的粗细（像素）", None),
    ("volume_step", "volume", "number", "1",
     "在音量条上滚一格改变多少音量", None),
    ("volume_persistency", "volume", "text", "",
     "这些状态下音量条常显；取值同 timeline_persistency", None),
    ("speed_step", "volume", "number", "0.1",
     "在倍速控件上滚一格改变多少倍速", None),
    ("speed_step_is_factor", "volume", "bool", "no",
     "倍速变化按倍数算（yes）还是按加减算（no）", None),
    ("speed_persistency", "volume", "text", "",
     "这些状态下倍速控件常显；取值同 timeline_persistency", None),
    # ---- 菜单
    ("menu_item_height", "menu", "number", "36",
     "菜单每一行的高度（像素）", None),
    ("menu_min_width", "menu", "number", "260",
     "菜单最小宽度（像素）", None),
    ("menu_padding", "menu", "number", "4",
     "菜单内边距（像素）", None),
    ("menu_type_to_search", "menu", "bool", "yes",
     "菜单打开时直接打字就能搜索（yes）；关掉后要按 / 或 Ctrl+F 才进入搜索", None),
    # ---- 顶栏与窗口
    ("top_bar", "topbar", "enum", "no-border",
     "顶部标题栏：always 总是显示 / no-border 仅无边框模式 / never 不显示",
     ("always", "no-border", "never")),
    ("top_bar_size", "topbar", "number", "40",
     "顶栏高度（像素）", None),
    ("top_bar_controls", "topbar", "enum", "right",
     "顶栏上的窗口按钮放哪侧：right / left / no 不显示", ("right", "left", "no")),
    ("top_bar_title", "topbar", "text", "yes",
     "顶栏标题：yes 用 mpv 的媒体标题 / no 不显示 / 或自定义模板字符串", None),
    ("top_bar_alt_title", "topbar", "text", "",
     "备用标题模板，例如 `${filename}`；与主标题相同时自动隐藏", None),
    ("top_bar_alt_title_place", "topbar", "enum", "below",
     "备用标题位置：below 主标题下方 / toggle 点顶栏切换", ("below", "toggle")),
    ("top_bar_flash_on", "topbar", "text", "video,audio",
     "加载这些类型文件时闪一下顶栏：audio / video / image / chapter", None),
    ("top_bar_persistency", "topbar", "text", "",
     "这些状态下顶栏常显；取值同 timeline_persistency", None),
    ("window_border_size", "topbar", "number", "1",
     "无边框模式下 uosc 自己画的窗口边框粗细", None),
    # ---- 外观
    ("scale", "look", "number", "1",
     "整体界面缩放系数（1 = 原始大小）", None),
    ("scale_fullscreen", "look", "number", "1.3",
     "全屏时的界面缩放系数", None),
    ("font_scale", "look", "number", "1",
     "文字缩放系数（跟随 mpv 的 osd-font）", None),
    ("text_border", "look", "number", "1.2",
     "文字与图标直接画在视频上时的描边粗细", None),
    ("border_radius", "look", "number", "4",
     "按钮、菜单等矩形的圆角半径（像素）", None),
    ("color", "look", "text", "",
     "配色覆盖，逗号分隔的 `名称=rgbhex`，例如 `foreground=f0f0f0,background=101010`", None),
    ("opacity", "look", "text", "",
     "透明度覆盖，逗号分隔的 `名称=0~1`，例如 `timeline=0.9,menu=0.95`", None),
    ("refine", "look", "text", "",
     "用一点性能换更精细的效果：text_width（逐字量宽）/ sorting（按语言排序，仅 Windows）", None),
    ("animation_duration", "look", "number", "100",
     "动画时长（毫秒）", None),
    ("flash_duration", "look", "number", "1000",
     "flash-* 命令闪烁的时长（毫秒）", None),
    ("proximity_in", "look", "number", "40",
     "鼠标距离小于这个像素时元素完全显示", None),
    ("proximity_out", "look", "number", "120",
     "鼠标距离大于这个像素时元素完全隐藏", None),
    ("font_bold", "look", "bool", "no",
     "整个界面只用粗体", None),
    ("destination_time", "look", "enum", "playtime-remaining",
     "时间轴上的剩余时间怎么算：total 总时长 / playtime-remaining 按当前倍速 / time-remaining 剩余时长",
     ("total", "playtime-remaining", "time-remaining")),
    ("time_precision", "look", "number", "0",
     "时间戳显示到小数点后几位（0 = 不显示小数）", None),
    ("buffered_time_threshold", "look", "number", "60",
     "缓冲时间低于多少秒时在时间轴上显示，0 = 不显示", None),
    ("autohide", "look", "bool", "no",
     "跟随 mpv 的 cursor-autohide 自动隐藏界面", None),
    ("pause_indicator", "look", "enum", "flash",
     "暂停指示：flash 闪一下 / static 常显 / manual 由命令控制",
     ("flash", "static", "manual")),
    # ---- 文件与目录
    ("stream_quality_options", "files", "text", "4320,2160,1440,1080,720,480,360,240,144",
     "流媒体画质菜单里列出哪些分辨率", None),
    ("video_types", "files", "text",
     "3g2,3gp,asf,avi,f4v,flv,h264,h265,m2ts,m4v,mkv,mov,mp4,mp4v,mpeg,mpg,ogm,ogv,rm,rmvb,ts,vob,webm,wmv,y4m",
     "识别为视频的扩展名（逗号分隔）", None),
    ("audio_types", "files", "text",
     "aac,ac3,aiff,ape,au,cue,dsf,dts,flac,m4a,mid,midi,mka,mp3,mp4a,oga,ogg,opus,spx,tak,tta,wav,weba,wma,wv",
     "识别为音频的扩展名（逗号分隔）", None),
    ("image_types", "files", "text",
     "apng,avif,bmp,gif,j2k,jp2,jfif,jpeg,jpg,jxl,mj2,png,svg,tga,tif,tiff,webp",
     "识别为图片的扩展名（逗号分隔）", None),
    ("subtitle_types", "files", "text",
     "aqt,ass,gsub,idx,jss,lrc,mks,pgs,pjs,psb,rt,sbv,slt,smi,sub,sup,srt,ssa,ssf,ttxt,txt,usf,vt,vtt",
     "加载字幕时列出哪些扩展名（逗号分隔）", None),
    ("playlist_types", "files", "text", "m3u,m3u8,pls,url,cue",
     "识别为播放列表的扩展名（逗号分隔）", None),
    ("load_types", "files", "text", "video,audio,image",
     "自动播放下一个文件时找哪些类型：video / audio / image / playlist / same", None),
    ("default_directory", "files", "text", "~/",
     "打开文件菜单的起始目录；`{drives}` = Windows 盘符列表", None),
    ("show_hidden_files", "files", "bool", "no",
     "目录列表里显示以点开头的隐藏文件", None),
    ("use_trash", "files", "bool", "no",
     "删除文件时移进回收站（需要系统有 trash 工具）", None),
    ("adjust_osd_margins", "files", "bool", "yes",
     "按界面元素的显隐自动调整 mpv 字幕/OSD 的边距", None),
    ("autoload", "files", "bool", "no",
     "没有播放列表时，当前文件播完后自动播同目录下一个文件", None),
    ("shuffle", "files", "bool", "no",
     "uosc 自己的「随机下一个」模式（不改动真实播放列表）", None),
    # ---- 章节 / 语言 / 字幕
    ("chapter_ranges", "misc", "text",
     "openings:30abf964,endings:30abf964,ads:c54e4e80",
     "章节区间标记：`类型:颜色`，逗号分隔（openings / endings / intros / outros / ads）", None),
    ("chapter_range_patterns", "misc", "text", "openings:オープニング;endings:エンディング",
     "识别简单章节区间的额外正则：`类型:模式`", None),
    ("languages", "misc", "text", "slang,en",
     "界面语言优先级列表；`slang` 表示继承 mpv 的 slang 配置", None),
    ("subtitles_directory", "misc", "text", "~~/subtitles",
     "在线字幕下载到哪；路径前加 `!` 表示所有字幕都存这里", None),
    ("disable_elements", "misc", "text", "",
     "整块关掉的界面元素，逗号分隔：window_border / top_bar / timeline / controls / volume / "
     "idle_indicator / audio_indicator / buffering_indicator / pause_indicator", None),
]

# 查找表：key -> 元数据 dict
META = {}
for _key, _group, _type, _default, _zh, _choices in OPTIONS:
    META[_key] = {"key": _key, "group": _group, "type": _type,
                  "default": _default, "zh": _zh, "choices": _choices}

GROUP_LABEL = {g[0]: g[1] for g in GROUPS}
GROUP_DESC = {g[0]: g[2] for g in GROUPS}

REL = "script-opts/uosc.conf"


def candidate_paths(target):
    """目标目录里 uosc.conf 可能在的位置（目标可能指向 portable_config 或 mpv 根）。"""
    if not target:
        return []
    base = Path(target)
    return [base / REL, base / "portable_config" / REL]


def find_path(target):
    """返回 (实际存在的路径或 None, 新建时该用的路径)。"""
    cands = candidate_paths(target)
    for p in cands:
        if p.is_file():
            return p, p
    return None, (cands[0] if cands else Path(REL))


# ---------------------------------------------------------------- 解析

def parse(text):
    """把 uosc.conf 拆成行条目，保留注释 / 空行 / 不认识的行。

    条目：{"kind": "blank"|"comment"|"kv"|"other", "raw": 原行, "key": ..., "value": ...}
    """
    lines = text.splitlines()
    rows = []
    seen = {}
    for no, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s:
            rows.append({"kind": "blank", "raw": raw, "line": no})
            continue
        if s.startswith("#") or s.startswith(";"):
            rows.append({"kind": "comment", "raw": raw, "line": no})
            continue
        if "=" not in s:
            rows.append({"kind": "other", "raw": raw, "line": no})
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        row = {"kind": "kv", "raw": raw, "line": no, "key": key, "value": value}
        meta = META.get(key)
        if meta:
            row.update({"known": True, "group": meta["group"], "type": meta["type"],
                        "zh": meta["zh"], "choices": meta["choices"],
                        "default": meta["default"]})
            if key in seen:
                row["duplicate_of"] = seen[key]
            seen.setdefault(key, no)
        else:
            row.update({"known": False, "group": "unknown", "type": "text",
                        "zh": "", "choices": None, "default": ""})
        rows.append(row)
    return rows, text.endswith(("\n", "\r"))


def load(target, path=None):
    """读一个 uosc.conf，返回给界面用的结构（不写盘）。"""
    p, create_at = find_path(target)
    if path:
        p = Path(path)
    if p is None or not p.is_file():
        return {
            "ok": False,
            "detail": f"目标目录里没有 {REL}。",
            "hint": f"装过 uosc 的整合包才会有这个文件；也可以手动新建：{create_at}",
            "path": str(create_at),
            "exists": False,
            "groups": [{"id": g[0], "name": g[1], "desc": g[2], "count": 0} for g in GROUPS],
            "rows": [],
        }
    tf = textio.read(p)
    if tf is None:
        return {"ok": False, "detail": f"读不了：{p}", "path": str(p), "exists": True}
    rows, _trailing = parse(tf.text)
    warnings = []
    for r in rows:
        if r.get("duplicate_of"):
            warnings.append(f"第 {r['line']} 行的 {r['key']} 与第 {r['duplicate_of']} 行重复，"
                            f"mpv 只用后面那条。")
    if tf.lossy:
        warnings.append("文件里有字节无法按任何已知编码解出来，界面显示可能有乱码；"
                        "保存会按 UTF-8 写回，建议先手工看一眼。")
    counts = {g[0]: 0 for g in GROUPS}
    unknown = 0
    for r in rows:
        if r["kind"] != "kv":
            continue
        if r.get("known"):
            counts[r["group"]] += 1
        else:
            unknown += 1
    groups = [{"id": g[0], "name": g[1], "desc": g[2], "count": counts[g[0]]}
              for g in GROUPS]
    groups.append({"id": "unknown", "name": "❓ 未收录的键", "desc": "uosc 新版本加的键，本工具不认识，原样保留",
                   "count": unknown})
    return {
        "ok": True,
        "path": str(p),
        "exists": True,
        "encoding": tf.encoding_label,
        "lossy": bool(tf.lossy),
        "bom": bool(tf.bom),
        "newline": "CRLF" if tf.newline == "\r\n" else "LF",
        "groups": groups,
        "rows": rows,
        "stats": {"known": sum(counts.values()), "unknown": unknown,
                  "total": sum(1 for r in rows if r["kind"] == "kv")},
        "warnings": warnings,
    }


# ---------------------------------------------------------------- 校验与写回

_TRUE = ("yes", "true", "1", "on")
_FALSE = ("no", "false", "0", "off")


def normalize(key, value):
    """把界面传来的值整理成要写进文件的样子；不合法返回 (None, 原因)。"""
    meta = META.get(key)
    raw = str(value if value is not None else "").strip()
    if meta is None:
        return raw, None                      # 未知键：原样写（界面也不让改）
    kind = meta["type"]
    if kind == "bool":
        low = raw.lower()
        if low in _TRUE:
            return "yes", None
        if low in _FALSE:
            return "no", None
        return None, f"{key} 只能是 yes / no"
    if kind == "enum":
        choices = meta["choices"] or ()
        if raw not in choices:
            return None, f"{key} 只能是 {' / '.join(choices)}"
        return raw, None
    if kind == "number":
        if raw == "":
            return None, f"{key} 不能为空"
        try:
            float(raw)
        except ValueError:
            return None, f"{key} 要填数字，当前是「{raw}」"
        return raw, None
    return raw, None                          # text


def apply_text(text, values):
    """在原文上只改动 values 里出现的键，返回 (新文本, 改动明细, 错误列表)。

    · 值和原文一样 → 不算改动（避免「保存一次多出一条变更」）
    · 文件里没有、但 values 里有的已知键 → 追加到末尾
    · 未知键、注释、空行、怪行 → 一个字节都不动
    """
    rows, trailing_nl = parse(text)
    out_lines = []
    changes, errors = [], []
    used = set()
    for r in rows:
        if r["kind"] != "kv":
            out_lines.append(r["raw"])
            continue
        key = r["key"]
        if key in values and r.get("known"):
            used.add(key)
            new, err = normalize(key, values[key])
            if err:
                errors.append(err)
                out_lines.append(r["raw"])
                continue
            if new != r["value"]:
                changes.append({"key": key, "from": r["value"], "to": new})
                out_lines.append(f"{key}={new}")
            else:
                out_lines.append(r["raw"])
        else:
            out_lines.append(r["raw"])       # 未知键 / 未提交的键：原样
    adds = [k for k in values if k in META and k not in used]
    if adds:
        out_lines.append("")
        out_lines.append("# 以下由 MPV Config Builder 追加")
        for k in adds:
            new, err = normalize(k, values[k])
            if err:
                errors.append(err)
                continue
            out_lines.append(f"{k}={new}")
            changes.append({"key": k, "from": "", "to": new})
    new_text = "\n".join(out_lines)
    if trailing_nl or not text:
        new_text += "\n"
    return new_text, changes, errors


def save(path, values, *, encoding="utf-8", bom=False, newline="\n", dry_run=False):
    """保存 uosc.conf：先校验，再备份 + 原子写；dry_run 只返回新文本。"""
    if not isinstance(values, dict) or not values:
        return {"ok": False, "detail": "没有要改的键"}
    p = Path(path)
    tf = textio.read(p)
    if tf is None:
        return {"ok": False, "detail": f"读不了：{p}"}
    text, changes, errors = apply_text(tf.text, values)
    if errors:
        return {"ok": False, "detail": "；".join(errors), "errors": errors}
    if not changes:
        return {"ok": True, "detail": "没有变化，不用写", "changes": [], "path": str(p)}
    if dry_run:
        return {"ok": True, "text": text, "changes": changes, "path": str(p)}
    report = {}
    try:
        bak = textio.write(p, text, **{"encoding": tf.encoding, "bom": tf.bom,
                                       "newline": tf.newline, "report": report})
    except OSError as e:
        return {"ok": False, "detail": f"写不了 {p.name}：{e}"}
    detail = f"改了 {len(changes)} 个键，已备份" + (f"为 {bak.name}" if bak else "")
    if report.get("fallback"):
        detail += "；原文编码表示不了新内容，已按 UTF-8 写回"
    return {"ok": True, "detail": detail, "changes": changes, "path": str(p),
            "backup": str(bak) if bak else "", "fallback": bool(report.get("fallback"))}


def preview_keys():
    """给「关于/文档」用的统计：收录了多少个 uosc 选项。"""
    return {"count": len(META), "groups": len(GROUPS),
            "keys": sorted(META)}

"""mpv.conf 解析与分析。"""
import re

from .schema import COMMON_OPTIONS, PARAMS, SHADER_OPTION_KEYS, db_known_keys, get_param_meta
from .score import score_active, overall_score, grade_of

SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
INCLUDE_KEYS = ("include", "include-append")
PROFILE_META = ("profile-desc", "profile-cond", "profile-restore")

# 全量选项数据库里的键：用来区分「标准选项但没做界面」和「真的不认识」
DB_KEYS = db_known_keys()


def analyze_config_text(text):
    """解析一段 mpv.conf 文本并返回分析结果（纯函数，可独立测试）。

    只统计**全局区**的选项：
      · `[name]` 小节里的内容属于 profile，单独收集，不参与评分与未知项统计
      · `include` 是文件引用而不是选项，单独收集，不算「重复」也不算「不认识」
    """
    lines = text.splitlines()
    parsed = []
    comment_count = 0
    empty_count = 0
    includes = []
    profiles = []                 # [{name, keys: [(no, k, v)], desc, cond}]
    current = None
    for no, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s:
            empty_count += 1
            continue
        if s.startswith("#") or s.startswith(";"):
            comment_count += 1
            continue
        sec = SECTION_RE.match(s)
        if sec:
            current = {"name": sec.group("name").strip(), "keys": [],
                       "desc": "", "cond": ""}
            profiles.append(current)
            continue
        if s.startswith("--"):
            s = s[2:]
        if "=" in s:
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip()
        else:
            k = s
            v = "yes"
        if not k:
            continue
        if k in INCLUDE_KEYS:
            includes.append(v.strip().strip('"').strip("'"))
            continue
        if current is not None:
            if k in PROFILE_META:
                if k == "profile-desc":
                    current["desc"] = v
                elif k == "profile-cond":
                    current["cond"] = v
                continue
            current["keys"].append((no, k, v))
            continue
        parsed.append((no, k, v))

    known = []
    shaders = []
    unlisted = []
    unknown = []
    blanks = []                   # 值留空的占位行（`vo=` 这种）
    seen = {}
    duplicates = []
    dup_lines = {}                # 键 → 出现过的所有行号（给界面画 ×N 用）
    active = []
    values = {}

    for no, k, v in parsed:
        lk = k.lower()
        dup_lines.setdefault(lk, []).append(no)
        if lk in seen:
            duplicates.append((k, seen[lk], no))
        else:
            seen[lk] = no

        # 空值占位行：mpv 读不到空值，本工具也不会写出去。
        # 不参与评分 —— 否则一份「全是 vo= / scale= 空壳」的教学模板
        # 会被算成"所有高档选项都开着"，报出"GPU 负载等级较高"这种胡话。
        if not v.strip():
            blanks.append((k, no))
            continue

        meta = get_param_meta(k)
        if meta:
            _, name, desc, opts, q, load = meta
            ok = v.lower() in [o.lower() for o in opts]
            if k not in active:
                active.append(k)
            values[k] = v
            known.append({
                "key": k, "value": v, "name": name, "ok": ok,
                "note": "可选值正常" if ok else "非工具预设值（可能仍有效，请确认）",
            })
        elif k in SHADER_OPTION_KEYS:
            shaders.append({"line": no, "key": k, "value": v})
        elif k in COMMON_OPTIONS:
            unlisted.append((k, v))
        elif k in DB_KEYS:
            # 全量数据库认识它：是标准 mpv 选项，只是本工具还没做界面
            unlisted.append((k, v))
        else:
            unknown.append((k, v, no))

    scores = score_active(active)
    quality = scores["quality"]
    sharp = scores["sharp"]
    smooth = scores["smooth"]
    color = scores["color"]
    stability = scores["stability"]
    load = scores["load"]
    overall = overall_score(scores)
    grade = grade_of(overall)

    issues = []
    suggestions = []

    if not parsed:
        issues.append("配置为空：只有空白/注释行，没有可用的配置项。")
        suggestions.append("点击主界面『高质量预设』生成基础配置，或导入一份已有的 mpv.conf。")

    if "vo" not in active:
        issues.append("未设置 vo（视频输出）：MPV 将使用默认输出；建议显式使用 gpu-next 或 gpu。")
    if "hwdec" not in active:
        issues.append("未设置 hwdec（硬件解码）：高分辨率/高码率内容可能占用更多 CPU。")
    if values.get("hwdec", "").lower() == "no":
        issues.append("hwdec=no 表示完全禁用硬件解码，CPU 压力会明显增大。")
    if "scale" not in active:
        suggestions.append("未设置 scale（缩放算法）：可根据画质/负载选择 ewa_lanczossharp、spline36 等。")
    if values.get("scale", "").lower() == "bilinear":
        suggestions.append("scale=bilinear 画质偏低，建议至少 spline36 或 ewa_lanczossharp。")
    if "video-sync" not in active:
        suggestions.append("未设置 video-sync；高刷新率显示可考虑 display-resample。")
    if "interpolation" in active and values.get("interpolation", "").lower() == "yes" and "tscale" not in active:
        issues.append("interpolation=yes 已启用，但未设置 tscale；建议显式选择时间缩放算法（如 mitchell、catmull_rom）。")
    if values.get("sub-ass-override", "").lower() == "yes":
        suggestions.append("sub-ass-override=yes 会覆盖原始字幕样式；如需保留原设计建议 no 或 strip。")
    if "cache" not in active:
        suggestions.append("本地播放可不设 cache；网络流/慢速存储场景建议启用。")
    if "deband" not in active:
        suggestions.append("未启用 deband；渐变区域可能出现色带，可按需开启。")

    if duplicates:
        dup_text = "、".join(f"{k}(第{first}与{second}行)" for k, first, second in duplicates[:6])
        issues.append(f"发现 {len(duplicates)} 处重复配置项：{dup_text}；MPV 通常以后出现的值为准。")
    if unknown:
        unk_text = "、".join(k for k, v, no in unknown[:8])
        issues.append(f"发现 {len(unknown)} 个未识别的选项：{unk_text}；"
                      f"请确认拼写，或是否属于脚本/扩展选项。")
    if blanks:
        bl_text = "、".join(k for k, no in blanks[:8])
        suggestions.append(
            f"{len(blanks)} 行只写了选项名、没填值（{bl_text}"
            f"{'…' if len(blanks) > 8 else ''}）：mpv 读不到空值，本工具也不会把它们写进配置。"
            f"这些行留空对播放没有任何影响 —— 要么填上值，要么删掉。")
    if shaders:
        suggestions.append(f"检测到 {len(shaders)} 条 Shader 配置；Windows 路径含盘符时请确认列表分隔符解析正确。")
    if unlisted:
        suggestions.append(f"{len(unlisted)} 个标准 mpv 选项本工具还没做界面（数据来自全量选项库），"
                           f"它们会原样保留在文件里。")

    if load >= 85:
        issues.append("GPU 负载等级较高，强烈建议实测 render time / dropped frames。")
    elif load >= 65:
        suggestions.append("GPU 负载中等偏高，中高端显卡更稳。")
    else:
        suggestions.append("GPU 负载较轻量，日常播放较稳。")

    if active:
        if overall >= 92:
            suggestions.append("配置较接近极限画质组合，务必以实测性能为准。")
        elif overall >= 82:
            suggestions.append("画质组合较好，可按需微调。")
        elif overall >= 70:
            suggestions.append("配置整体均衡，可进一步优化画质或负载。")
        else:
            suggestions.append("配置偏轻量，可考虑补充缩放、硬件解码等关键项。")
    else:
        suggestions.append("未识别到构建器支持的参数；可点击『导入到构建器』后使用预设。")

    suggestions.append("评分是启发式指标，不代表实际 FPS 或 Render Time；最终应以 MPV stats、GPU Render Time、dropped frames 实测为准。")

    dup_groups = [{"key": next((k for k, f, s in duplicates if k.lower() == lk), lk),
                   "lines": nos, "count": len(nos)}
                  for lk, nos in dup_lines.items() if len(nos) > 1]

    return {
        "line_count": len(lines),
        "comment_count": comment_count,
        "empty_count": empty_count,
        "option_count": len(parsed),
        "known": known,
        "shaders": shaders,
        "unlisted": unlisted,
        "unknown": unknown,
        "blanks": blanks,
        "duplicates": duplicates,
        "duplicate_groups": dup_groups,
        "active": active,
        "includes": includes,
        "profiles": profiles,
        "scores": scores,
        "overall": overall,
        "grade": grade,
        "load": load,
        "issues": issues,
        "suggestions": suggestions,
    }



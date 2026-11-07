# -*- coding: utf-8 -*-
"""VPY 融合（R-3）：把「反交错 + 降噪 + 超分 + 补帧」这些脚本合成一个 .vpy。

为什么需要：mpv 同时只能挂一个 `vf=vapoursynth=...`。想「补帧 + 超分」一起用，
要么用别人写好的多合一脚本，要么自己把管线拼起来 —— 这个模块干后面这件事。

做法（对 mpv-lazy 的脚本结构做了实测，全都是同一个模板）：

    ### 说明注释
    import vapoursynth as vs
    from vapoursynth import core
    import k7sfunc as k7f
    core.num_threads = k7f.vs_t_dft
    clip = video_in
    ############
    # 用户选项 #
    ############
    H_Pre = 1440          <- 选项赋值（原样保留）
    ## 说明注释
    clip = k7f.XXX(clip, ...)   <- 管线（原样保留）
    clip.set_output()

所以最稳的融合方式不是「重写管线」，而是：
  · 每个脚本的选项 + 管线**原样**塞进一个独立函数（自动互相隔离，同名变量不打架）
  · 融合脚本按角色顺序调用这些函数：反交错 → 降噪 → 超分 → 补帧
  · import 与 core.num_threads 去重后提到文件头

这样生成出来的脚本和原脚本行为一致，也看得懂、改得动。
"""
import re
from datetime import datetime
from pathlib import Path

from . import textio
from .i18n import T

MARKER = "由 MPV Config Builder 融合生成"
PREFIX = "_mb_"

# 角色：数字越小越先跑
ROLES = [
    ("deint", "反交错", 0, ("ETC_DEINT", "DEINT")),
    ("denoise", "降噪", 1, ("NR_", "DENOISE")),
    ("superres", "超分", 2, ("SR_", "MIX_UAI")),
    ("memc", "补帧", 3, ("MEMC_", "RIFE", "MVT", "DRBA", "SVP")),
    ("other", "其它", 4, ()),
]
# 这些不是画面处理管线，融合进视频链没有意义
NOT_FUSABLE = {
    "MIX_UVR": "人声/伴奏分离，属于音频处理，不能拼进视频链",
}

# 角色与原因的英文对照（T14）。缺键回退中文。
ROLE_EN = {
    "deint": "Deinterlace",
    "denoise": "Denoise",
    "superres": "Upscale",
    "memc": "MEMC",
    "other": "Other",
    "unfusable": "Audio processing",
}
NOT_FUSABLE_EN = {
    "MIX_UVR": "Vocal/accompaniment separation is audio processing; it cannot be fused into the video chain",
}


def script_role(path):
    """按文件名判断脚本干什么用，返回 (role_id, 中文名, 顺序)。"""
    name = Path(path).stem.upper()
    for prefix, why in NOT_FUSABLE.items():
        if name.startswith(prefix):
            return "unfusable", T("音频处理", ROLE_EN["unfusable"]), 99
    for rid, label, order, hints in ROLES:
        if any(h in name for h in hints):
            return rid, T(label, ROLE_EN.get(rid, label)), order
    return "other", T("其它", ROLE_EN["other"]), 4


def unfusable_reason(path):
    """不能融合时给出原因（能融合返回空串）。"""
    name = Path(path).stem.upper()
    for prefix, why in NOT_FUSABLE.items():
        if name.startswith(prefix):
            return T(why, NOT_FUSABLE_EN.get(prefix, why))
    return ""


def _split_statements(text):
    """按顶层语句切分（括号没闭合就继续往下吃），保留注释行。"""
    out, buf, depth = [], [], 0
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if depth == 0 and not buf:
            if not stripped:
                out.append(("blank", ""))
                continue
            if stripped.startswith("#"):
                out.append(("comment", stripped))
                continue
            buf = [line]
            depth = _depth(line)
            if depth <= 0:
                out.append(("code", "\n".join(buf)))
                buf, depth = [], 0
            continue
        buf.append(line)
        depth += _depth(line)
        if depth <= 0:
            out.append(("code", "\n".join(buf)))
            buf, depth = [], 0
    if buf:
        out.append(("code", "\n".join(buf)))
    return out


def _depth(line):
    """粗略算括号净值（跳过字符串里的括号）。"""
    depth, quote = 0, ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        i += 1
    return depth


def parse_script(text, path=""):
    """解析一个 mpv-lazy 风格的 .vpy，返回它的各个组成部分。"""
    statements = _split_statements(text)
    header, imports, inits, options, pipeline, unknown = [], [], [], [], [], []
    seen_entry = False
    seen_output = False
    for kind, body in statements:
        if kind == "blank":
            if seen_entry and not seen_output:
                pipeline.append("")
            elif not seen_entry:
                header.append("")
            continue
        if kind == "comment":
            if not seen_entry:
                header.append(body)
            elif not seen_output:
                pipeline.append(body)
            continue
        s = body.strip()
        if s.startswith(("import ", "from ")):
            imports.append(s)
            continue
        if re.match(r"^core\.\w+\s*=", s):
            inits.append(s)
            continue
        if re.match(r"^clip\s*=\s*video_in\s*$", s):
            seen_entry = True
            continue
        if re.match(r"^clip\.set_output\s*\(\s*\)\s*$", s):
            seen_output = True
            continue
        if not seen_entry:
            unknown.append(s)
            continue
        if seen_output:
            unknown.append(s)
            continue
        if re.match(r"^[A-Za-z_]\w*\s*=\s*[^=]", s) and "(" not in s.split("=", 1)[1]:
            options.append(s)          # 纯字面量赋值 = 用户选项
        elif "=" in s or "(" in s:
            pipeline.append(s)         # 其余当作管线语句，原样保留
        else:
            unknown.append(s)
    return {
        "path": str(path),
        "name": Path(path).name if path else "（文本）",
        "stem": Path(path).stem if path else "inline",
        "header": [x for x in header if x != ""],
        "imports": imports,
        "inits": inits,
        "options": options,
        "pipeline": [x for x in pipeline],
        "unknown": unknown,
        "has_output": seen_output,
        "has_entry": seen_entry,
    }


def safe_ident(stem):
    """把文件名变成合法的 Python 标识符片段。"""
    return re.sub(r"\W", "_", str(stem)) or "stage"


def plan_fusion(scripts):
    """按角色给出融合顺序，返回 (有序列表, 警告列表)。"""
    items, warnings = [], []
    for s in scripts:
        rid, label, order = script_role(s.get("path", "") or s.get("stem", ""))
        if rid == "unfusable":
            warnings.append(f"{s.get('name')} 不能融合：{unfusable_reason(s.get('path', ''))}")
            continue
        items.append({"script": s, "role": rid, "label": label, "order": order})
    items.sort(key=lambda x: (x["order"], x["script"].get("name", "")))

    labels = [x["label"] for x in items]
    if labels.count("补帧") > 1:
        warnings.append("选了多个补帧脚本：同一时刻只需要一个，融合后帧率会被插两次，建议只留一个。")
    if labels.count("超分") > 1:
        warnings.append("选了多个超分脚本：连续放大两轮既慢又容易出振铃，建议只留一个。")
    for x in items:
        s = x["script"]
        if not s.get("has_output"):
            warnings.append(f"{s.get('name')} 里没找到 clip.set_output()，可能不是标准模板，融合结果需要自己看一眼。")
        if s.get("unknown"):
            warnings.append(f"{s.get('name')} 有 {len(s['unknown'])} 行没看懂，已原样保留。")
    return items, warnings


def build_fused(scripts, source_paths=None, note=""):
    """生成融合脚本文本。scripts 是 parse_script() 的结果列表。"""
    items, warnings = plan_fusion(scripts)
    if not items:
        return {"ok": False, "detail": "没有可融合的脚本", "warnings": warnings}

    lines = [
        "# " + "=" * 58,
        f"# {MARKER}",
        "# 源脚本（按执行顺序）：",
    ]
    for x in items:
        lines.append(f"#   {x['script'].get('name')}　（{x['label']}）")
    lines += [
        f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "# 想撤销：删掉本文件，把 mpv.conf 里的 vf 指回原来的单个脚本即可",
        "# " + "=" * 58,
    ]
    if note:
        lines.append("# " + note)
    lines.append("")

    imports, inits = [], []
    for x in items:
        for imp in x["script"]["imports"]:
            if imp not in imports:
                imports.append(imp)
        for ini in x["script"]["inits"]:
            if ini not in inits:
                inits.append(ini)
    lines += imports
    if inits:
        lines.append("")
        lines += inits
    lines.append("")

    used = {}
    calls = []
    for x in items:
        s = x["script"]
        base = safe_ident(s.get("stem") or s.get("name"))
        used[base] = used.get(base, 0) + 1
        fname = f"_mb_{base}" if used[base] == 1 else f"_mb_{base}_{used[base]}"
        head = [f"# ---- {s.get('name')}（{x['label']}）" + "-" * 4]
        for h in s["header"]:
            head.append("# " + h.lstrip("# ").rstrip())
        lines.append("")
        lines += head
        lines.append(f"def {fname}(clip):")
        pipeline = list(s["pipeline"])
        banner = []                       # 源脚本里「用户选项」的横幅注释，挪到选项前面更通顺
        while pipeline and pipeline[0].strip().startswith("#"):
            banner.append(pipeline.pop(0))
        while pipeline and not pipeline[0].strip():
            pipeline.pop(0)
        body = banner + list(s["options"])
        if body and pipeline:
            body.append("")
        body += pipeline
        # 去掉空行；若整段都是空的就塞一个 pass，否则 def 体为空会语法错误。
        # （以前写成 `[ln for ln in body if ln.strip() != ""] or ["pass"]`，
        #  推导式里的 ln 在条件里一直绑到最后一个元素，末尾是空行时会误判。）
        body = [ln for ln in body if ln.strip()]
        if not body:
            body = ["pass"]
        lines += ["    " + ln if ln.strip() else "" for ln in body]
        lines.append("    return clip")
        calls.append((fname, x["label"]))

    lines += ["", "", "# " + "=" * 58, "# 主流程：按角色顺序串起来", "# " + "=" * 58,
              "clip = video_in"]
    for fname, label in calls:
        lines.append(f"clip = {fname}(clip)          # {label}")
    lines += ["", "clip.set_output()", ""]

    text = "\n".join(lines)
    check = check_syntax(text)
    return {"ok": check["ok"], "text": text, "warnings": warnings, "check": check,
            "stages": [{"name": f, "label": l} for f, l in calls]}


def check_syntax(text):
    """用 compile() 做一次语法体检（不执行，所以不需要装 VapourSynth）。"""
    try:
        compile(text, "<fused.vpy>", "exec")
        return {"ok": True, "detail": "语法检查通过"}
    except SyntaxError as e:
        return {"ok": False, "detail": f"第 {e.lineno} 行语法有问题：{e.msg}"}


def fuse_files(paths, name=None, note=""):
    """读文件 → 融合 → 返回结果（不写盘）。"""
    scripts = []
    for p in paths:
        path = Path(p)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return {"ok": False, "detail": f"读不了 {path.name}：{e}"}
        scripts.append(parse_script(text, path))
    result = build_fused(scripts, note=note)
    stem = name or "fused"
    result["filename"] = f"{PREFIX}{safe_ident(stem)}.vpy"
    return result


def write_fused(target_dir, result, overwrite=False):
    """把融合结果写到 <target_dir>/_mb_xxx.vpy。安全规则：只覆盖自己生成的 _mb_ 文件。"""
    if not result.get("ok"):
        return {"ok": False, "detail": result.get("detail") or "融合结果不合法，没有写文件"}
    d = Path(target_dir)
    if not d.is_dir():
        return {"ok": False, "detail": f"目标目录不存在：{d}"}
    path = d / result["filename"]
    if path.exists():
        old = path.read_text(encoding="utf-8", errors="replace")
        if MARKER not in old and not overwrite:
            return {"ok": False,
                    "detail": f"{path.name} 已存在，而且不是本工具生成的，拒绝覆盖"}
        if not overwrite:
            backup = path.with_name(path.name + ".bak")
            try:
                textio.write_atomic(backup, old.encode("utf-8"))
            except OSError:
                pass
    try:
        textio.write_atomic(path, result["text"].encode("utf-8"))
    except OSError as e:
        return {"ok": False, "detail": f"写入失败：{e}"}
    return {"ok": True, "path": str(path), "name": path.name,
            "detail": f"已生成 {path.name}"}


__all__ = ["parse_script", "plan_fusion", "build_fused", "fuse_files", "write_fused",
           "script_role", "check_syntax", "MARKER", "PREFIX"]

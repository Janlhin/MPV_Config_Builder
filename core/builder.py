# -*- coding: utf-8 -*-
"""把前端状态编译成 mpv.conf 文本。

前端状态（三个模式共用同一个结构，方便互相切换时保留选择）：

    {
      "values":  {"vo": "gpu-next", "scale": "ewa_lanczossharp", ...},
      "shaders": ["~~/shaders/FSRCNNX_x2_16-0-4-1.glsl", ...],   # 顺序即链序
      "memc":    "~~/vs/MEMC_MVT_STD.vpy",                        # 可以为空
      "custom":  "自己写的 key=value 行（地狱模式 / 自定义层）",
    }
"""
from .schema import NATIVE_OPTIONS, PARAMS, format_option_line, format_option_value
from .i18n import T

SHADER_KEY = "glsl-shaders"
# glsl-shaders 的「追加」写法：mpv 手册里 glsl-shader / glsl-shaders-append
# 都是往现有链尾追加，语义与 glsl-shaders（整表替换）不同，写回时必须分开。
SHADER_APPEND_KEYS = ("glsl-shader", "glsl-shaders-append", "glsl-shader-append")
LIST_SHADER_KEYS = (SHADER_KEY,) + SHADER_APPEND_KEYS


def _core_order():
    """"key -> (分类序号, 组内序号)"，用来按界面分组顺序输出。"""
    out = {}
    for ci, items in enumerate(PARAMS.values()):
        for ii, item in enumerate(items):
            out[item[0]] = (ci, ii)
    return out


CORE_ORDER = _core_order()

NATIVE_ORDER = {}
for _ci, (_group, _items) in enumerate(NATIVE_OPTIONS.items()):
    for _ii, _item in enumerate(_items):
        NATIVE_ORDER[_item[0]] = (_ci, _ii)


def _split_shader_appends(values):
    """把 values 里的 append 型 shader 键抽出来，拍平成一个有序列表。

    返回 (剩下的 values, [路径, ...])。
    `glsl-shader` / `glsl-shaders-append` 都是「往链尾追加」语义，
    值可能是 `a.glsl;b.glsl` 这种列表写法，用 split_mpv_list 拆开。
    """
    from .schema import split_mpv_list
    rest, appends = {}, []
    for key, value in values.items():
        if key in SHADER_APPEND_KEYS:
            for path in split_mpv_list(value):
                if path and path not in appends:
                    appends.append(path)
        else:
            rest[key] = value
    return rest, appends


def _fmt(key, value):
    """`key = value`，该加引号就加（含 `#` 这类会被 mpv 当注释的字符时必须加）。

    mpv 手册：`#` 之后一律算注释，所以 `sub-color=#FFD766` 会被截成空值，
    必须写成 `sub-color="#FFD766"`。格式化逻辑统一在 schema.format_option_value，
    writer 的合并写回路径复用同一份，避免两条路径行为不一致。
    """
    return format_option_line(key, value)


def _vf_line(path, label=""):
    """补帧脚本写成 mpv 认的 vf=vapoursynth="..."，别再套一层引号。

    label 是原来配置里带的标签（形如 `@vs:`），有就原样保留 —— 丢了标签会让
    别人脚本里 `vf remove @vs` 之类的引用失效。
    """
    p = str(path).strip().strip('"')
    lbl = str(label or "").strip()
    return f'vf = {lbl}vapoursynth="{p}"'


def _pick_append_key(key=None):
    """追加行用哪个键名写。默认 `glsl-shader`（mpv-lazy 社区更常见的写法）。"""
    return key if key in SHADER_APPEND_KEYS else "glsl-shader"


def _shader_lines(state):
    """shader 链写成 mpv 认的行。

    `glsl-shaders` 是整表替换，`glsl-shader` / `glsl-shaders-append` 是往链尾
    追加 —— 两者语义不同，各自成行，不能合并成一行（合并会改变用户原有的
    追加/替换意图，还会让「先替换再追加」变成一次整表替换）。
    """
    lines = []
    replace = [s for s in (state.get("shaders") or []) if str(s).strip()]
    if replace:
        lines.append(f"{SHADER_KEY} = " + format_option_value(SHADER_KEY, ";".join(replace)))
    seen = {str(s).strip() for s in replace}
    appends = state.get("shader_appends") or []
    if isinstance(appends, dict):            # 兼容老的 {key: [paths]} 结构
        flat = []
        for paths in appends.values():
            flat.extend(paths)
        appends = flat
    # 追加行：保持用户原来的键名（glsl-shader 是更常见的写法）
    key = _pick_append_key(state.get("shader_append_key"))
    for s in appends:
        s = str(s).strip()
        if s and s not in seen:              # 同一文件不必既替换又追加
            seen.add(s)
            lines.append(f"{key} = " + format_option_value(key, s))
    return lines


def _memc_lines(state):
    """vf / vf-append 各自的 vapoursynth 脚本 + 原样保留的普通滤镜链。

    以前 vf 与 vf-append 共用一个 memc 字段、写回时只输出一条 `vf =` —— 结果是
    「一条 vf=vapoursynth= + 一条 vf-append=」的配置被写坏：补帧脚本消失，
    vf-append 的内容被伪装成 vf。更糟的是 `vf-append=format=yuv420p10` 这种
    普通滤镜会被当成脚本路径，写成 `vf = vapoursynth="format=yuv420p10"`。
    现在：脚本按原键写回，普通滤镜链按原键原样吐出。
    """
    lines = []
    memc = str(state.get("memc") or "").strip()
    if memc:
        kind = state.get("memc_kind") or "vf"
        label = str(state.get("memc_label") or "").strip()
        if kind == "vf-append":
            lines.append('vf-append = vapoursynth="' + memc.strip('"') + '"')
        elif label:
            lines.append(_vf_line(memc, label))
        else:
            lines.append('vf = vapoursynth="' + memc.strip('"') + '"')
    elif state.get("vf_filters"):
        # 用户原本就有 vf 滤镜链、且没挂 VS 脚本：原样保留
        lines.append("vf = " + ",".join(state["vf_filters"]))
    for key, field in (("vf-append", "vf_append_filters"), ("af", "af_filters"),
                       ("af-append", "af_append_filters")):
        for item in state.get(field) or []:
            item = str(item).strip()
            if item:
                lines.append(f"{key} = {item}")
    return lines


def _annotate(text, key, note_style, with_hint=True):
    """给一行选项加中文注释（R-25）。

    · style="inline" → `key = value    # 说明`（原文一字不动、行号不变）
    · style="above"  → 上一行放 `# 说明`（适合"打算长期维护这份配置"）
    · 查不到说明 → **不加**，不编造
    追加的 `#` 在引号**外面**，所以不会影响已经带了引号的值。
    """
    from .notes import note_for
    note = note_for(key, style=note_style, with_hint=with_hint)
    if not note:
        return [text]
    if note_style == "inline":
        return [f"{text}    # {note}"]
    return [f"# {note}", text]


def build_config_text(state, title=None, note="",
                      annotate=False, annotate_style="above", with_hint=True):
    """状态 → 配置文本（str）。

    title 缺省用 `schema.FULL_TITLE`（版本号只有一个来源）。
    annotate=True 时给每个选项附一句中文说明（R-25）。
    `annotate_style` 取 "above"（默认，说明在上一行）或 "inline"（行尾）。
    """
    if title is None:
        from .schema import FULL_TITLE
        title = FULL_TITLE
    style = "inline" if annotate_style == "inline" else "above"

    def emit(key, value):
        """一行选项（按需加注释）。"""
        text = _fmt(key, value)
        return _annotate(text, key, style, with_hint) if annotate else [text]

    values = {k: v for k, v in (state.get("values") or {}).items() if str(v).strip()}
    custom = str(state.get("custom") or "").strip()

    # glsl-shader / glsl-shaders-append 是「追加」语义：
    #  · 前端从文本导入时会把它们放进 values → 这里拆出来
    #  · 前端直接传 shader_appends（loader 的产物）→ 保留
    # 两边合起来，且保持顺序、去掉重复。
    values, from_values = _split_shader_appends(values)
    merged_appends = []
    for path in list(state.get("shader_appends") or []) + list(from_values):
        path = str(path).strip()
        if path and path not in merged_appends:
            merged_appends.append(path)
    state = dict(state)
    state["shader_appends"] = merged_appends
    state["shader_append_key"] = _pick_append_key(state.get("shader_append_key"))

    lines = [f"# {title}", T("# 由 MPV Config Builder 生成", "# Generated by MPV Config Builder"), ""]
    if note:
        lines += ["# " + note, ""]

    core = {k: v for k, v in values.items() if k in CORE_ORDER}
    native = {k: v for k, v in values.items() if k in NATIVE_ORDER and k not in CORE_ORDER}
    other = {k: v for k, v in values.items() if k not in CORE_ORDER and k not in NATIVE_ORDER}

    groups = {}
    for key, value in core.items():
        ci = CORE_ORDER[key][0]
        groups.setdefault(ci, []).append((CORE_ORDER[key][1], key, value))
    for ci in sorted(groups):
        cat = list(PARAMS.keys())[ci]
        lines.append(f"# {cat}")
        for _ii, key, value in sorted(groups[ci]):
            lines += emit(key, value)
        lines.append("")

    ngroups = {}
    for key, value in native.items():
        if key in LIST_SHADER_KEYS:
            continue                     # shader 行单独处理（替换 / 追加分开）
        ci = NATIVE_ORDER[key][0]
        ngroups.setdefault(ci, []).append((NATIVE_ORDER[key][1], key, value))
    for ci in sorted(ngroups):
        cat = list(NATIVE_OPTIONS.keys())[ci]
        lines.append(f"# {cat}")
        for _ii, key, value in sorted(ngroups[ci]):
            lines += emit(key, value)
        lines.append("")

    shader_lines = _shader_lines(state)
    if shader_lines:
        lines.append("# Shader / 锐化（顺序 = 处理链顺序；append 型单独成行，保持追加语义）")
        for text in shader_lines:
            lines += _annotate(text, "glsl-shaders", style, with_hint) if annotate else [text]
        lines.append("")

    memc_lines = _memc_lines(state)
    if memc_lines:
        lines.append("# VS 补帧 / 超分")
        for text in memc_lines:
            lines += _annotate(text, "vf", style, with_hint) if annotate else [text]
        lines.append("")

    if other:
        lines.append("# 其它")
        for key in sorted(other):
            lines += emit(key, other[key])
        lines.append("")

    if custom:
        lines.append("# 自定义")
        lines += custom.splitlines()
        lines.append("")

    return "\n".join(lines)


def describe_state(state):
    """把状态汇总成一句人话，用于预览标题。"""
    values = {k: v for k, v in (state.get("values") or {}).items() if str(v).strip()}
    n_shader = len([s for s in (state.get("shaders") or []) if str(s).strip()])
    bits = [f"{len(values)} 个参数"]
    if n_shader:
        bits.append(f"{n_shader} 个 shader")
    if str(state.get("memc") or "").strip():
        bits.append("1 个 vpy")
    return "、".join(bits)


def validate_state(state):
    """检查状态是否有问题，返回 [(级别, 提示), ...]。

    这里做的是「单选项层面」的检查（值是否合法、有没有漏填）；
    选项之间互相打架的问题交给 core.conflicts。

    **空值不算错误，也不写进配置。** 典型场景：教学模板 / 自己搭的骨架配置
    会写成 `vo=` 这种「留空给用户填」的占位行，一份 29 行的模板会报出 29 条
    「值为空」，等于劈头盖脸指责用户 —— 而用户什么都没做错，而且这工具本来
    就不会把空值写进配置（见 build_config_text 的第一行过滤）。
    占位行的数量单独统计，由 full_check 给一句 info 级提示。
    """
    from .schema import validate_native_value
    issues = []
    for key, value in (state.get("values") or {}).items():
        if not str(value).strip():
            continue                     # 占位空行：不是错误
        ok, msg = validate_native_value(key, value)
        if not ok:
            issues.append(("error", f"{key} = {value}：{msg}"))
    shaders = [s for s in (state.get("shaders") or []) if str(s).strip()]
    if len(shaders) > 6:
        issues.append(("warn", f"shader 链有 {len(shaders)} 个，链越长负载越高，建议按需取舍"))
    return issues


def blank_keys(state):
    """值留空的键（占位行）。它们不会被写进配置，只用来给用户一句提示。"""
    return sorted(k for k, v in (state.get("values") or {}).items()
                  if not str(v).strip())


def full_check(state):
    """把单选项校验 + 选项间冲突合并成一份 [(级别, 提示), ...]。

    state.other 是「从现有配置里读出来、但这个界面没有对应勾选项」的键；
    冲突检测必须带上它们 —— 界面不认识 linear-upscaling，mpv 可认识。

    state.profiles 是配置里的 [小节]：小节里的选项只在条件满足时生效，
    但**它们就是用户实际在用的画面参数**。以前完全不参与冲突检测，于是
    `[Anime4K] scale=ewa_lanczossharp` + 全局 `interpolation=yes` 会报"无冲突"，
    而用户看到的正是那套参数打架的结果。这里把小节的值也并进去，
    并在提示里注明来源，免得用户以为是全局设置有问题。
    """
    from .conflicts import conflicts_as_issues, detect_conflicts

    issues = validate_state(state)
    blanks = blank_keys(state)
    if blanks:
        shown = "、".join(blanks[:8]) + ("…" if len(blanks) > 8 else "")
        issues.append(("info",
                       f"{len(blanks)} 项的值是空的（{shown}）："
                       f"这类行不会被写进配置，mpv 也读不到空值。"
                       f"要么填上值，要么把这些行删掉。"))
    merged = dict(state.get("other") or {})
    merged.update({k: v for k, v in (state.get("values") or {}).items() if v is not None})

    # 小节里的值：只补「全局没设」的键，全局设了就按 mpv 的规则以全局为准来判断
    profile_values = {}
    for prof in state.get("profiles") or []:
        for key, value in (prof.get("values") or {}).items():
            if str(value).strip() and key not in merged:
                profile_values.setdefault(key, value)
    for key, value in profile_values.items():
        merged[key] = value

    # shader / 补帧：小节里的也算上（它们同样会被 mpv 应用）
    shaders = list(state.get("shaders") or [])
    for prof in state.get("profiles") or []:
        for s in prof.get("shaders") or []:
            if s and s not in shaders:
                shaders.append(s)
    memc = str(state.get("memc") or "")
    if not memc:
        for prof in state.get("profiles") or []:
            if prof.get("memc"):
                memc = prof["memc"]
                break

    conflicts = detect_conflicts(merged, shaders, memc)
    issues += conflicts_as_issues(conflicts)
    return issues, conflicts


__all__ = ["build_config_text", "describe_state", "validate_state", "full_check"]

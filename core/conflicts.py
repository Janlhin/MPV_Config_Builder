# -*- coding: utf-8 -*-
"""冲突检测：勾选组合里那些「互相打架 / 白设了 / 会静默失效」的搭配。

**每条规则的依据都逐条写在注释里**，而且分三类，注释里标明了是哪一类
（2026-10-09 逐条核对过 —— 之前这里写着"全部来自手册原文"，其实有 7 条不是）：

  · **手册原文** —— 能引出原话的，注释里抄了原句（英文原文 / 中文版译文）。
  · **设计原则** —— 手册管不着的事（shader 链、外挂补帧脚本）。出处是
    《MPV_Shader搭配说明书.md》里写明的处理顺序，不是手册。
  · **逻辑判断** —— 手册给了取值范围或语义，结论由它推出来（注释里附上那句语义）。

核对用的官方手册：`DOCS/man/options.rst`（mpv master），2026-10-09 取的，
sha256 `f802f317e2fa22116984d49a8f814721e320cd55ea5ee27d1a23d32595bfe5f9`。
中文译文取自 `data/mpv_options_zh.json`（mpv_doc-CN，与手册同源）。
**加新规则请照这个格式写清依据** —— "我觉得这样更快"不算依据，误报比不报更烦人。

**结构**（2026-09-14 C-1 重构后）：判定逻辑是 17 个 `_rule_xxx(ctx)` 函数，
文案与元信息集中在文件下半部的规则表 `_RULES`。
**加一条规则 = 写一个判定函数 + 在 `_RULES` 里加一行**，不用动控制流。
改完请跑 `tools/compare_conflicts.py` 对照 `_legacy_detect_conflicts()`。

返回结构（前端直接渲染）：
    {
      "id": "sigmoid_vs_linear",
      "level": "error" | "warn" | "info",
      "title": "一句话结论",
      "detail": "为什么",
      "fix": "怎么改（可空）",
      "keys": ["sigmoid-upscaling", "linear-upscaling"],   # 涉及哪些选项，界面用来标行
    }
"""

import collections as _collections

# 手册标注为「--vo=gpu-next 独占」的选项：vo=gpu 下写了也不生效
GPU_NEXT_ONLY = {
    "gamut-mapping-mode", "target-gamut", "tone-mapping-visualize",
    "allow-delayed-peak-detect", "border-background", "hdr-contrast-recovery",
    "hdr-peak-percentile", "hdr-reference-white", "icc-use-luma", "image-lut",
    "image-subs-hdr-peak", "inverse-tone-mapping", "lut", "sdr-adjust-gamma",
    "sub-hdr-peak", "target-colorspace-hint-mode", "target-colorspace-hint-strict",
    "target-contrast", "target-lut", "treat-srgb-as-power22",
}

# 手册标注为「--vo=gpu 独占」的选项：vo=gpu-next 下不生效
GPU_ONLY = {"corner-rounding", "sharpen", "tone-mapping-max-boost"}

# shader 家族：同一个家族在链里出现多次 = 重复放大
SHADER_FAMILIES = {
    "Anime4K Upscale": ("anime4k upscale", "anime4k_upscale"),
    "FSRCNNX": ("fsrcnnx",),
    "RAVU": ("ravu",),
    "NNEDI3": ("nnedi3",),
    "ArtCNN": ("artcnn",),
    "ESRGAN": ("esrgan",),
    "Ani4Kv2": ("ani4kv2",),
}
SHARPEN_HINTS = ("adaptive_sharpen", "adaptive sharpen", "amd_cas", "amd cas",
                 "qcom_sgeds", "qcom sgeds", "sgeds", "cas")
# 上面那个裸 "cas" 会误伤：文件名里只要含 cas（Cascade、cas_xxx）都算锐化。
# 所以先用词边界匹配，匹配不上才退回子串匹配（并去掉太泛的裸词）。
SHARPEN_WORD_RE = None
try:
    import re as _re
    SHARPEN_WORD_RE = _re.compile(
        r"(?:^|[^a-z0-9])(?:cas|qcom[_ ]?sgeds|adaptive[_ ]?sharpen|amd[_ ]?cas)(?:[^a-z0-9]|$)",
        _re.IGNORECASE)
except Exception:                                    # pragma: no cover
    SHARPEN_WORD_RE = None


def _is_sharpen_shader(path):
    """这个 shader 是不是锐化类。"""
    low = str(path).lower()
    if SHARPEN_WORD_RE is not None and SHARPEN_WORD_RE.search(low):
        return True
    # 长词（不容易误伤）照旧用子串匹配兜底
    return any(h in low for h in
               ("adaptive_sharpen", "adaptive sharpen", "amd_cas", "qcom_sgeds"))

# 会做超分的 vpy 脚本前缀（mpv-lazy 的命名习惯）
VPY_SUPERRES = ("SR_", "MIX_UAI")
VPY_MEMC = ("MEMC_",)


def _val(values, key, default=""):
    return str(values.get(key, default)).strip()


def _num(values, key):
    try:
        return float(_val(values, key))
    except (TypeError, ValueError):
        return None


def _truthy(values, key):
    return _val(values, key).lower() in ("yes", "true", "1", "auto", "always")


def _is_no(values, key):
    return _val(values, key).lower() in ("no", "false", "0", "")


def _shader_families(shaders):
    found = {}
    for path in shaders or []:
        low = str(path).lower()
        for fam, hints in SHADER_FAMILIES.items():
            if any(h in low for h in hints):
                found.setdefault(fam, []).append(path)
    return found


def _legacy_detect_conflicts(values, shaders=None, memc=""):
    """【仅供对照，勿在新代码里调用】C-1 重构之前的实现，原样保留。

    2026-09-14 把这条 154 行的 if 长链改成了下面的规则表（`_RULES`）。改完做了两道等价性证明：

      * `tests/data/conflicts_golden.json` —— 55 个手选用例，逐字段比对（基准在重构前生成）；
      * `tools/compare_conflicts.py`       —— **4699 组系统枚举**（每个选项 × 每种取值、
        两两组合、shader × memc、以及交叉），新旧实现逐字段完全一致。

    为什么留着：它是「重构前到底怎么判的」的唯一在库证据。将来有人怀疑规则表漏了某种搭配，
    可以直接拿它当参照物，不必翻 git 历史。**新的冲突规则一律加进 `_RULES`，不要往这里加。**
    tests 里的 LegacyEquivalenceTest 会持续拿它给规则表对答案。
    """
    values = values or {}
    shaders = [s for s in (shaders or []) if str(s).strip()]
    memc = str(memc or "")
    out = []

    def add(rid, level, title, detail, fix="", keys=()):
        out.append({"id": rid, "level": level, "title": title, "detail": detail,
                    "fix": fix, "keys": list(keys)})

    vo = _val(values, "vo").lower()

    # ---- 缩放：sigmoid 与 linear 不兼容（手册：sigmoid "与 --linear-upscaling 不兼容并取代了它"）
    if _truthy(values, "sigmoid-upscaling") and _truthy(values, "linear-upscaling"):
        add("sigmoid_vs_linear", "warn",
            "sigmoid-upscaling 与 linear-upscaling 同时开启",
            "手册明确写着这两个不兼容，sigmoid 会取代 linear —— 也就是说 linear-upscaling 白设了。",
            "把 linear-upscaling 关掉（或者设成 no），只留 sigmoid-upscaling。",
            ["sigmoid-upscaling", "linear-upscaling"])
    elif _truthy(values, "linear-upscaling"):
        add("linear_upscaling_alone", "info",
            "linear-upscaling 单独开启",
            "手册：这个选项除了测试/特殊目的外通常不推荐，建议改用 sigmoid-upscaling 或两个都关掉。",
            "除非你在做对照实验，否则关掉它。",
            ["linear-upscaling"])

    # ---- 插值补帧：video-sync 必须是 display-*（手册 warning：否则"将被默默禁用"）
    interp = _truthy(values, "interpolation")
    vsync = _val(values, "video-sync").lower()
    if interp and not vsync.startswith("display"):
        add("interp_needs_sync", "error",
            "interpolation=yes 但 video-sync 不是 display- 模式",
            "手册原文：这需要把 video-sync 设为 display- 模式之一，否则插值会被静默禁用 —— "
            "你看到的就是「开了但没效果」。",
            "把 video-sync 设成 display-resample（或 display-resample-vdrop）。",
            ["interpolation", "video-sync"])
    if interp and memc:
        add("interp_with_memc", "warn",
            "内置插值和外挂补帧脚本同时开着",
            "vpy 脚本已经在造中间帧了，mpv 再插一次等于插两遍：画面可能更糊、负载翻倍。",
            "二选一：要么关掉 interpolation，要么不挂补帧脚本。",
            ["interpolation", "vf"])
    if interp and not _val(values, "tscale"):
        add("interp_no_tscale", "info",
            "开了插值但没指定 tscale",
            "tscale 决定时间方向用什么算法重采样，不写就用默认 oversample（最清晰、也最容易抖）。",
            "可以试试 catmull_rom 或 mitchell，比默认更平滑。",
            ["interpolation", "tscale"])

    # ---- 去色带
    if _truthy(values, "deband"):
        it = _num(values, "deband-iterations")
        if it is not None and it <= 0:
            add("deband_zero_iterations", "warn",
                "deband 开着，但 deband-iterations=0",
                "迭代次数为 0 等于不做去色带，开了个寂寞。",
                "改成 1~4；一般 2 就够。",
                ["deband", "deband-iterations"])
        elif it is not None and it > 4:
            add("deband_iterations_high", "info",
                f"deband-iterations={it:g} 偏高",
                "手册：每一步强度下降很快，>4 实际上是无用的，只是更慢。",
                "降到 4 以内。",
                ["deband-iterations"])
        rng = _num(values, "deband-range")
        if it is not None and rng is not None and it >= 3 and rng >= 32:
            add("deband_range_vs_iterations", "info",
                "去色带迭代多 + 半径大，容易糊细节",
                "手册建议：增加 deband-iterations 时应该相应减小 deband-range 来补偿。",
                "把 deband-range 降到 16 左右试试。",
                ["deband-iterations", "deband-range"])

    # ---- 色彩管理：icc-profile 覆盖 target-*（手册原话）
    icc = _val(values, "icc-profile")
    targets = [k for k in ("target-prim", "target-trc", "target-gamut") if _val(values, k)]
    if icc and targets:
        add("icc_profile_vs_target", "warn",
            "icc-profile 与 target-* 同时设置",
            "手册：icc-profile 会覆盖 --target-prim、--target-trc 和 --icc-profile-auto。"
            "这几个 target-* 不生效，只会让人看配置时误会。",
            "用 ICC 校色的话就把 target-prim / target-trc / target-gamut 删掉。",
            ["icc-profile"] + targets)
    if _truthy(values, "icc-profile-auto") and icc:
        add("icc_auto_vs_profile", "warn",
            "icc-profile-auto 与 icc-profile 同时设置",
            "手册：icc-profile 覆盖 icc-profile-auto，自动校色不会生效。",
            "二选一。",
            ["icc-profile-auto", "icc-profile"])
    if _val(values, "tone-mapping").lower() == "hable" and not _truthy(values, "hdr-compute-peak"):
        add("hable_needs_peak", "info",
            "tone-mapping=hable 建议配合 hdr-compute-peak",
            "手册在 hable 条目里写着：如果可能的话，你还应该启用 --hdr-compute-peak 以获得最佳效果。",
            "开 hdr-compute-peak=yes（或 auto）。",
            ["tone-mapping", "hdr-compute-peak"])

    # ---- 渲染器独占项
    if vo == "gpu":
        bad = sorted(k for k in values if k in GPU_NEXT_ONLY)
        if bad:
            add("gpunext_only_with_gpu", "warn",
                f"vo=gpu 下用了 {len(bad)} 个 gpu-next 独占选项",
                "手册把这些标注为「--vo=gpu-next 独占」：用 vo=gpu 时它们不生效（"
                + "、".join(bad[:6]) + ("…" if len(bad) > 6 else "") + "）。",
                "要么把 vo 换成 gpu-next，要么删掉这些项。",
                ["vo"] + bad)
    elif vo == "gpu-next":
        bad = sorted(k for k in values if k in GPU_ONLY)
        if bad:
            add("gpu_only_with_gpunext", "info",
                f"vo=gpu-next 下用了 {len(bad)} 个只有 vo=gpu 支持的选项",
                "手册标注这些是「--vo=gpu 独占」：gpu-next 下不生效（"
                + "、".join(bad) + "）。",
                "删掉，或者临时切回 vo=gpu 用。",
                ["vo"] + bad)

    # ---- shader 链
    fams = _shader_families(shaders)
    if len(fams) > 1:
        add("double_upscale_shaders", "warn",
            "shader 链里有多个超分家族",
            "同时挂了 " + "、".join(sorted(fams)) + " —— 它们都在做放大，串起来等于放大两三轮："
            "细节未必更好，但负载一定翻倍，还容易出振铃。",
            "选一个家族就够了（通用向 FSRCNNX/RAVU，动画向 Anime4K/ArtCNN）。",
            [])
    memc_name = str(memc).replace("\\", "/").split("/")[-1].upper()
    if memc_name.startswith(VPY_SUPERRES) and fams:
        add("vpy_sr_with_shader_sr", "warn",
            "vpy 超分脚本 + shader 超分链同时开着",
            f"脚本 {memc_name} 自己做超分，shader 链里也有超分家族（"
            + "、".join(sorted(fams)) + "），两轮放大会放大噪点和振铃。",
            "留一头：要么只用脚本，要么只用 shader。",
            ["vf"])
    if len(shaders) >= 2:
        idx = [i for i, s in enumerate(shaders) if _is_sharpen_shader(s)]
        if idx and idx[0] < len(shaders) - 1:
            add("sharpen_not_last", "info",
                "锐化 shader 不在链尾",
                "锐化类 shader（Adaptive_sharpen / CAS / SGEDS）放在中间，后面的 shader 会把它"
                "刚锐化出来的边缘再处理一遍，通常不是想要的效果。",
                "用 ↑↓ 把锐化挪到链尾。",
                [])

    # ---- 缓存
    if _is_no(values, "cache") and _val(values, "demuxer-max-bytes"):
        add("cache_off_but_buffer", "info",
            "cache=no 却设了 demuxer-max-bytes",
            "缓存关掉之后这个上限没有意义。",
            "要么把 cache 打开，要么删掉 demuxer-max-bytes。",
            ["cache", "demuxer-max-bytes"])

    level_order = {"error": 0, "warn": 1, "info": 2}
    out.sort(key=lambda x: (level_order.get(x["level"], 3), x["id"]))
    return out


# =====================================================================
# 规则表（C-1）
# ---------------------------------------------------------------------
# 重构前这里是一条 154 行的 if 长链，条件、文案、涉事选项全糊在一起，
# 想核对「第 7 条规则的 keys 写全了没有」得在几百行里翻。
# 现在拆成两部分：
#   * 判定函数 `_rule_xxx(ctx)` —— 只管「什么时候算冲突」；
#   * 规则表 `_RULES`         —— 只管「报什么」：id / 级别 / 结论 / 理由 / 怎么改 / 涉及哪些选项。
# 17 条规则在表里一眼能从头看到尾，加规则 = 写一个判定函数 + 在表里加一行。
#
# 硬约束（tests/test_conflicts_snapshot.py 守着，违反就红）：
#   1. id / level / title / detail / fix / keys 的取值不许改一个字；
#   2. 输出顺序仍由 (level 升序, id 字典序) 决定，和重构前一致。
# =====================================================================


# 判定函数的返回值。用具名字段而不是裸元组 ——
# 重构时踩过：`icc_profile_vs_target` 想额外返回动态 keys，写了 4 元组，
# 而分发代码是固定位置解包，结果 detail 位置塞进了 keys 列表、fix 变空。
# 55 个手选用例全绿、当时的全套测试也全绿，只有 4699 组系统枚举才抓出来。
# 具名之后写错字段名会直接报错，不会再「静默错位」。
_Conflict = _collections.namedtuple("_Conflict", "title detail fix keys")
_Conflict.__new__.__defaults__ = ("", (),)


def _kv(rid, level, keys):
    """给判定函数贴元信息：规则 id、级别、涉及的选项。

    keys 是「界面要标黄哪几行」，不是「判定读了哪些值」——
    比如 double_upscale_shaders 读了 shader 列表，但 shader 没有对应的选项行，
    所以它的 keys 就是空的。别为了「看起来完整」硬塞选项名，
    标错行比不标更让人迷惑。
    """
    def deco(fn):
        fn.rid = rid
        fn.level = level
        fn.keys = tuple(keys)
        return fn
    return deco


def _is_shader_superres(name):
    """vpy 脚本名（已转大写）是不是超分脚本。"""
    return name.startswith(VPY_SUPERRES)


# ---- 缩放 ----
# 依据：手册原文。``--sigmoid-upscaling`` 条目：「This is incompatible with and
#       replaces ``--linear-upscaling``.」（中文版：「这与 --linear-upscaling 不兼容并取代了它」）
@_kv("sigmoid_vs_linear", "warn", ["sigmoid-upscaling", "linear-upscaling"])
def _rule_sigmoid_vs_linear(ctx):
    v = ctx["values"]
    if _truthy(v, "sigmoid-upscaling") and _truthy(v, "linear-upscaling"):
        return _Conflict("sigmoid-upscaling 与 linear-upscaling 同时开启",
                "手册明确写着这两个不兼容，sigmoid 会取代 linear —— 也就是说 linear-upscaling 白设了。",
                "把 linear-upscaling 关掉（或者设成 no），只留 sigmoid-upscaling。")


# 依据：手册原文。``--linear-upscaling`` 条目：「This is not usually recommended
#       except for testing/specific purposes. Users are advised to either enable
#       ``--sigmoid-upscaling`` or keep both options disabled (i.e. scaling in gamma light).」
@_kv("linear_upscaling_alone", "info", ["linear-upscaling"])
def _rule_linear_upscaling_alone(ctx):
    v = ctx["values"]
    # 注意：只在 sigmoid 没开的时候才报，否则上一条已经说清楚了，重复报等于噪音
    if _truthy(v, "linear-upscaling") and not _truthy(v, "sigmoid-upscaling"):
        return _Conflict("linear-upscaling 单独开启",
                "手册：这个选项除了测试/特殊目的外通常不推荐，建议改用 sigmoid-upscaling 或两个都关掉。",
                "除非你在做对照实验，否则关掉它。")


# ---- 插值补帧 ----
# 依据：手册原文。``--interpolation`` 条目里有一段 warning：「This requires setting
#       the ``--video-sync`` option to one of the ``display-`` modes, or it will be
#       silently disabled.」
@_kv("interp_needs_sync", "error", ["interpolation", "video-sync"])
def _rule_interp_needs_sync(ctx):
    if ctx["interp"] and not ctx["video_sync"].startswith("display"):
        return _Conflict("interpolation=yes 但 video-sync 不是 display- 模式",
                "手册原文：这需要把 video-sync 设为 display- 模式之一，否则插值会被静默禁用 —— "
                "你看到的就是「开了但没效果」。",
                "把 video-sync 设成 display-resample（或 display-resample-vdrop）。")


# 依据：**设计判断，手册没有这一条** —— vpy 补帧脚本是 mpv 之外的东西，手册管不着它。
#       推理是本工具自己的：脚本已经在造中间帧，mpv 再插一次就是插两遍。
@_kv("interp_with_memc", "warn", ["interpolation", "vf"])
def _rule_interp_with_memc(ctx):
    if ctx["interp"] and ctx["memc"]:
        return _Conflict("内置插值和外挂补帧脚本同时开着",
                "vpy 脚本已经在造中间帧了，mpv 再插一次等于插两遍：画面可能更糊、负载翻倍。",
                "二选一：要么关掉 interpolation，要么不挂补帧脚本。")


# 依据：一半手册、一半建议，分开说 ——
#       手册事实（``--tscale`` 条目）：「The default is ``oversample``」，
#       且这些取值「listed in increasing order of smoothness/blurriness, with
#       ``bicubic`` being the smoothest/blurriest and ``oversample`` being the
#       sharpest/least smooth」。
#       本工具的建议：按上面那个排序取中间档（catmull_rom / mitchell），**手册没这么说**。
@_kv("interp_no_tscale", "info", ["interpolation", "tscale"])
def _rule_interp_no_tscale(ctx):
    if ctx["interp"] and not _val(ctx["values"], "tscale"):
        return _Conflict("开了插值但没指定 tscale",
                "tscale 决定时间方向用什么算法重采样，不写就用默认 oversample（最清晰、也最容易抖）。",
                "可以试试 catmull_rom 或 mitchell，比默认更平滑。")


# ---- 去色带 ----
# 依据：**逻辑判断**（手册没有直接写"0 等于没开"）—— 但根在手册：
#       ``--deband-iterations=<0..16>`` 的定义是「The number of debanding steps to
#       perform per sample」，0 步自然就是一步都不做。
@_kv("deband_zero_iterations", "warn", ["deband", "deband-iterations"])
def _rule_deband_zero_iterations(ctx):
    it = ctx["deband_iterations"]
    if ctx["deband"] and it is not None and it <= 0:
        return _Conflict("deband 开着，但 deband-iterations=0",
                "迭代次数为 0 等于不做去色带，开了个寂寞。",
                "改成 1~4；一般 2 就够。")


# 依据：手册原文。``--deband-iterations`` 条目：「Note that the strength of each step
#       falls off very quickly, so high numbers (>4) are practically useless.」
@_kv("deband_iterations_high", "info", ["deband-iterations"])
def _rule_deband_iterations_high(ctx):
    it = ctx["deband_iterations"]
    # elif：iterations<=0 时上面那条已经报了，这里不重复
    if ctx["deband"] and it is not None and it > 4:
        return _Conflict(f"deband-iterations={it:g} 偏高",
                "手册：每一步强度下降很快，>4 实际上是无用的，只是更慢。",
                "降到 4 以内。")


# 依据：手册原文。``--deband-range`` 条目：「If you increase the ``--deband-iterations``,
#       you should probably decrease this to compensate.」
@_kv("deband_range_vs_iterations", "info", ["deband-iterations", "deband-range"])
def _rule_deband_range_vs_iterations(ctx):
    it, rng = ctx["deband_iterations"], ctx["deband_range"]
    if ctx["deband"] and it is not None and rng is not None and it >= 3 and rng >= 32:
        return _Conflict("去色带迭代多 + 半径大，容易糊细节",
                "手册建议：增加 deband-iterations 时应该相应减小 deband-range 来补偿。",
                "把 deband-range 降到 16 左右试试。")


# ---- 色彩管理 ----
# 依据：手册原文。``--icc-profile`` 条目：「This option overrides the ``--target-prim``,
#       ``--target-trc`` and ``--icc-profile-auto`` options.」
@_kv("icc_profile_vs_target", "warn", ["icc-profile", "target-prim", "target-trc",
                                       "target-gamut"])
def _rule_icc_profile_vs_target(ctx):
    v, icc = ctx["values"], ctx["icc"]
    targets = [k for k in ("target-prim", "target-trc", "target-gamut") if _val(v, k)]
    if icc and targets:
        # keys 是动态的：只标「实际开了哪几个」target-*
        return _Conflict("icc-profile 与 target-* 同时设置",
                         "手册：icc-profile 会覆盖 --target-prim、--target-trc 和 --icc-profile-auto。"
                         "这几个 target-* 不生效，只会让人看配置时误会。",
                         "用 ICC 校色的话就把 target-prim / target-trc / target-gamut 删掉。",
                         ["icc-profile"] + targets)


# 依据：与上一条同一句手册原文（``--icc-profile`` 覆盖 ``--icc-profile-auto``）。
#       拆成两条是因为用户可能只犯了其中一个，提示语得各说各的。
@_kv("icc_auto_vs_profile", "warn", ["icc-profile-auto", "icc-profile"])
def _rule_icc_auto_vs_profile(ctx):
    if _truthy(ctx["values"], "icc-profile-auto") and ctx["icc"]:
        return _Conflict("icc-profile-auto 与 icc-profile 同时设置",
                "手册：icc-profile 覆盖 icc-profile-auto，自动校色不会生效。",
                "二选一。")


# 依据：手册原文。``--tone-mapping`` 的 hable 分支：「If possible, you should also
#       enable ``--hdr-compute-peak`` for the best results.」
@_kv("hable_needs_peak", "info", ["tone-mapping", "hdr-compute-peak"])
def _rule_hable_needs_peak(ctx):
    v = ctx["values"]
    if _val(v, "tone-mapping").lower() == "hable" and not _truthy(v, "hdr-compute-peak"):
        return _Conflict("tone-mapping=hable 建议配合 hdr-compute-peak",
                "手册在 hable 条目里写着：如果可能的话，你还应该启用 --hdr-compute-peak 以获得最佳效果。",
                "开 hdr-compute-peak=yes（或 auto）。")


# ---- 渲染器独占项 ----
# 依据：手册**逐条标注**。上面那个 GPU_NEXT_ONLY 集合是从选项库里筛出来的 ——
#       手册给这些条目各挂了一句「(``--vo=gpu-next`` only)」（中文版「（--vo=gpu-next 独占）」）。
@_kv("gpunext_only_with_gpu", "warn", ["vo"])
def _rule_gpunext_only_with_gpu(ctx):
    if ctx["vo"] != "gpu":
        return None
    bad = sorted(k for k in ctx["values"] if k in GPU_NEXT_ONLY)
    if not bad:
        return None
    # 正文只列前 6 个（多了会把弹窗撑爆），但**数量报的是全量**，
    # 免得用户以为「就 6 个」。keys 是动态的：vo + 实际命中的那些选项。
    return _Conflict(f"vo=gpu 下用了 {len(bad)} 个 gpu-next 独占选项",
                     "手册把这些标注为「--vo=gpu-next 独占」：用 vo=gpu 时它们不生效（"
                     + "、".join(bad[:6]) + ("…" if len(bad) > 6 else "") + "）。",
                     "要么把 vo 换成 gpu-next，要么删掉这些项。",
                     ["vo"] + bad)


# 依据：同上一类。GPU_ONLY 集合对应手册里标了「(``--vo=gpu`` only)」的条目。
@_kv("gpu_only_with_gpunext", "info", ["vo"])
def _rule_gpu_only_with_gpunext(ctx):
    if ctx["vo"] != "gpu-next":
        return None
    bad = sorted(k for k in ctx["values"] if k in GPU_ONLY)
    if not bad:
        return None
    return _Conflict(f"vo=gpu-next 下用了 {len(bad)} 个只有 vo=gpu 支持的选项",
                     "手册标注这些是「--vo=gpu 独占」：gpu-next 下不生效（"
                     + "、".join(bad) + "）。",
                     "删掉，或者临时切回 vo=gpu 用。",
                     ["vo"] + bad)


# ---- shader 链 ----
# 依据：**设计原则，手册没有这一条** —— shader 链是用户自己搭的，mpv 不做约束。
#       出处《MPV_Shader搭配说明书.md》§1 的处理顺序「超分 → 补帧 → 锐化」：
#       两级放大串在一起，等于把同一件事做两遍（负载翻倍、容易振铃），属于该顺序的反面。
@_kv("double_upscale_shaders", "warn", [])
def _rule_double_upscale_shaders(ctx):
    fams = ctx["shader_families_present"]
    if len(fams) > 1:
        # keys 故意留空：这里说的是 shader 链，而 shader 在界面上没有对应的「选项行」可标
        return _Conflict("shader 链里有多个超分家族",
                "同时挂了 " + "、".join(sorted(fams)) + " —— 它们都在做放大，串起来等于放大两三轮："
                "细节未必更好，但负载一定翻倍，还容易出振铃。",
                "选一个家族就够了（通用向 FSRCNNX/RAVU，动画向 Anime4K/ArtCNN）。")


# 依据：**设计原则**，与上一条同源（脚本超分 + shader 超分 = 两轮放大）。
#       不同的是这里一头是 vpy 脚本、一头是 shader 链，所以单列一条。
@_kv("vpy_sr_with_shader_sr", "warn", ["vf"])
def _rule_vpy_sr_with_shader_sr(ctx):
    fams = ctx["shader_families_present"]
    if _is_shader_superres(ctx["memc_name"]) and fams:
        return _Conflict("vpy 超分脚本 + shader 超分链同时开着",
                f"脚本 {ctx['memc_name']} 自己做超分，shader 链里也有超分家族（"
                + "、".join(sorted(fams)) + "），两轮放大会放大噪点和振铃。",
                "留一头：要么只用脚本，要么只用 shader。")


# 依据：**设计原则**。出处《MPV_Shader搭配说明书.md》§1「最后才做锐化收尾」
#       与 §4「放在最后，只加强纹理不动线条边缘」。
@_kv("sharpen_not_last", "info", [])
def _rule_sharpen_not_last(ctx):
    shaders = ctx["shaders"]
    if len(shaders) >= 2:
        idx = [i for i, s in enumerate(shaders) if _is_sharpen_shader(s)]
        if idx and idx[0] < len(shaders) - 1:
            return _Conflict("锐化 shader 不在链尾",
                    "锐化类 shader（Adaptive_sharpen / CAS / SGEDS）放在中间，后面的 shader 会把它"
                    "刚锐化出来的边缘再处理一遍，通常不是想要的效果。",
                    "用 ↑↓ 把锐化挪到链尾。")


# ---- 缓存 ----
# 依据：**逻辑判断**，根在手册 ``--cache`` 条目：「Use ``--demuxer-max-bytes`` to
#       specify the size of the cache.」—— 缓存都关了，"缓存多大"自然没有意义。
@_kv("cache_off_but_buffer", "info", ["cache", "demuxer-max-bytes"])
def _rule_cache_off_but_buffer(ctx):
    v = ctx["values"]
    if _is_no(v, "cache") and _val(v, "demuxer-max-bytes"):
        return _Conflict("cache=no 却设了 demuxer-max-bytes",
                "缓存关掉之后这个上限没有意义。",
                "要么把 cache 打开，要么删掉 demuxer-max-bytes。")


# ---- 规则表：顺序 = 报出来的顺序（最终还会按 (level, id) 排一次）----
_RULES = (
    _rule_sigmoid_vs_linear,
    _rule_linear_upscaling_alone,
    _rule_interp_needs_sync,
    _rule_interp_with_memc,
    _rule_interp_no_tscale,
    _rule_deband_zero_iterations,
    _rule_deband_iterations_high,
    _rule_deband_range_vs_iterations,
    _rule_icc_profile_vs_target,
    _rule_icc_auto_vs_profile,
    _rule_hable_needs_peak,
    _rule_gpunext_only_with_gpu,
    _rule_gpu_only_with_gpunext,
    _rule_double_upscale_shaders,
    _rule_vpy_sr_with_shader_sr,
    _rule_sharpen_not_last,
    _rule_cache_off_but_buffer,
)

_LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2}


def detect_conflicts(values, shaders=None, memc=""):
    """检查一组选项 / shader / 补帧脚本之间的冲突，返回问题列表。

    返回的每一项都是给前端直接渲染的 dict：
        {id, level, title, detail, fix, keys}
    `keys` 是「界面该标黄哪几行」，可能是空的（比如 shader 链的问题没有对应的选项行）。
    输出顺序固定为 (级别 error→warn→info, 同级别按 id 字典序)。
    """
    values = values or {}
    shaders = [s for s in (shaders or []) if str(s).strip()]
    memc = str(memc or "")

    ctx = {
        "values": values,
        "shaders": shaders,
        "memc": memc,
        "vo": _val(values, "vo").lower(),
        "interp": _truthy(values, "interpolation"),
        "video_sync": _val(values, "video-sync").lower(),
        "deband": _truthy(values, "deband"),
        "deband_iterations": _num(values, "deband-iterations"),
        "deband_range": _num(values, "deband-range"),
        "icc": _val(values, "icc-profile"),
        # 补帧脚本名统一转成「大写 + 只留文件名」，后面按前缀判超分/MEMC
        "memc_name": memc.replace("\\", "/").split("/")[-1].upper(),
        "shader_families_present": _shader_families(shaders),
    }

    out = []
    for rule in _RULES:
        got = rule(ctx)
        if not got:
            continue
        # got.keys 为空元组时回落到规则表里声明的静态 keys（具名结果里 "" 和 () 都是默认值）
        keys = got.keys or rule.keys
        out.append({"id": rule.rid, "level": rule.level, "title": got.title,
                    "detail": got.detail, "fix": got.fix, "keys": list(keys)})
    out.sort(key=lambda x: (_LEVEL_ORDER.get(x["level"], 3), x["id"]))
    return out


def conflicts_as_issues(conflicts):
    """转成「体检」用的 (级别, 文字) 列表格式。"""
    out = []
    for c in conflicts:
        level = {"error": "error", "warn": "warn", "info": "info"}.get(c["level"], "info")
        text = c["title"]
        if c.get("fix"):
            text += f" → {c['fix']}"
        out.append((level, text))
    return out


def conflict_keys(conflicts):
    """所有涉事选项的集合，界面用它给对应行打标记。"""
    keys = set()
    for c in conflicts:
        keys.update(c.get("keys") or [])
    return keys


__all__ = ["detect_conflicts", "conflicts_as_issues", "conflict_keys",
           "GPU_NEXT_ONLY", "GPU_ONLY"]

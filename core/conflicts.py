# -*- coding: utf-8 -*-
"""冲突检测：勾选组合里那些「互相打架 / 白设了 / 会静默失效」的搭配。

每条规则的依据都写在注释里，全部来自 mpv 官方手册（中文版 mpv_doc-CN）原文，
不凭印象加规则 —— 误报比不报更烦人。想加规则请先找到手册原话再写。

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


def detect_conflicts(values, shaders=None, memc=""):
    """检查一组选项 / shader / 补帧脚本之间的冲突，返回问题列表。"""
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

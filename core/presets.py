# -*- coding: utf-8 -*-
"""基础模式预设：内容（动画/真人） × 取向（省电流畅/均衡/最高画质） 共 6 套。

每套预设包含：
    params   直接写入 mpv.conf 的键值
    shaders  shader 槽位，每个槽位是一组候选名（取第一个在当前清单里存在的）
    note     给用户看的一句话说明
"""

# 通用基础项（所有档位共用）
_BASE = {
    "vo": "gpu-next",
    "hwdec": "auto-safe",
    "cache": "yes",
}

from .i18n import T, get_lang

# 省电流畅：几乎不做后处理，优先省电与稳定
_LOW = {
    **_BASE,
    "video-sync": "audio",
    "scale": "bilinear",
    "cscale": "bilinear",
    "dscale": "bilinear",
    "sigmoid-upscaling": "no",
    "correct-downscaling": "no",
    "deband": "no",
    "interpolation": "no",
}

# 均衡：画质与负载折中
_MID = {
    **_BASE,
    "video-sync": "display-resample",
    "scale": "spline36",
    "cscale": "bicubic",
    "dscale": "hermite",
    "sigmoid-upscaling": "yes",
    "correct-downscaling": "yes",
    "deband": "no",
    "interpolation": "no",
}

# 最高画质：锐利缩放 + 补帧 + shader
_HIGH = {
    **_BASE,
    "video-sync": "display-resample",
    "scale": "ewa_lanczossharp",
    "cscale": "ewa_lanczossharp",
    "dscale": "hermite",
    "sigmoid-upscaling": "yes",
    "correct-downscaling": "yes",
    "deband": "yes",
    "interpolation": "yes",
    "tscale": "oversample",
    "hr-seek-framedrop": "no",
}

# shader 槽位（按顺序拼接成 glsl-shaders）
_ANIME_HIGH_SHADERS = [
    ["Anime4K Clamp_Highlights"],
    ["Anime4K Restore_CNN_L", "Anime4K Restore_CNN_M", "Anime4K Restore_CNN_Soft_M"],
    ["Anime4K Upscale_GAN_x2_M", "Anime4K Upscale_GAN_x2_S", "Anime4K Upscale_CNN_x2_M"],
    ["QCOM SGEDS", "Adaptive_sharpen"],
]
_ANIME_MID_SHADERS = [
    ["Anime4K Restore_CNN_Soft_M", "Anime4K Restore_CNN_L"],
    ["QCOM SGEDS", "Adaptive_sharpen"],
]
_REAL_HIGH_SHADERS = [
    ["FSRCNNX x2_16", "FSRCNNX x2_8"],
    ["Adaptive_sharpen"],
]
_REAL_MID_SHADERS = [
    ["FSRCNNX x2_8", "Adaptive_sharpen"],
]

BASIC_PRESETS = {
    ("动画", "省电流畅"): {
        "params": _LOW, "shaders": [],
        "note": "动画 · 省电流畅：只保证流畅播放，几乎不做后处理，适合核显/笔记本。",
    },
    ("动画", "均衡"): {
        "params": _MID, "shaders": _ANIME_MID_SHADERS,
        "note": "动画 · 均衡：轻度修复 + 中等缩放，负载可控。",
    },
    ("动画", "最高画质"): {
        "params": _HIGH, "shaders": _ANIME_HIGH_SHADERS,
        "note": "动画 · 最高画质：锐利缩放 + Anime4K 链 + 60Hz 补帧，需要中高端独显。",
    },
    ("真人影视", "省电流畅"): {
        "params": _LOW, "shaders": [],
        "note": "真人 · 省电流畅：只保证流畅播放，几乎不做后处理。",
    },
    ("真人影视", "均衡"): {
        "params": _MID, "shaders": _REAL_MID_SHADERS,
        "note": "真人 · 均衡：轻量超分，细节与负载折中。",
    },
    ("真人影视", "最高画质"): {
        "params": _HIGH, "shaders": _REAL_HIGH_SHADERS,
        "note": "真人 · 最高画质：锐利缩放 + FSRCNNX + 自适应锐化。",
    },
}

CONTENT_CHOICES = ["动画", "真人影视"]
PREFER_CHOICES = ["省电流畅", "均衡", "最高画质"]

# 预设说明英文对照（T14）。键与 BASIC_PRESETS 同形；缺键回退中文。
PRESET_EN = {
    ("动画", "省电流畅"): "Anime · battery-friendly: smooth playback with almost no post-processing; good for iGPUs / laptops.",
    ("动画", "均衡"): "Anime · balanced: light restoration + mid-tier scaling, controlled load.",
    ("动画", "最高画质"): "Anime · max quality: sharp scaling + Anime4K chain + 60Hz MEMC; needs a mid/high-end GPU.",
    ("真人影视", "省电流畅"): "Live action · battery-friendly: smooth playback with almost no post-processing.",
    ("真人影视", "均衡"): "Live action · balanced: light upscaling, a compromise between detail and load.",
    ("真人影视", "最高画质"): "Live action · max quality: sharp scaling + FSRCNNX + adaptive sharpening.",
}

WRITE_MODE_INCLUDE = "include"
WRITE_MODE_MERGE = "merge"
INCLUDE_FILENAME = "mpv-builder.conf"


def get_basic_preset(content, prefer):
    """返回 (预设字典, 说明文字)；找不到时回退到均衡档。"""
    preset = BASIC_PRESETS.get((content, prefer))
    if preset is None:
        preset = BASIC_PRESETS[("真人影视", "均衡")]
    if get_lang() == "en":
        preset = dict(preset)
        preset["note"] = T(preset["note"], PRESET_EN.get((content, prefer), preset["note"]))
    return preset


def resolve_shader_slots(slots, catalog_names):
    """按槽位挑选实际存在的 shader 名（名字写法不同也能对上）；返回 (选中列表, 缺失说明)。"""
    from .schema import find_named
    picked, notes = [], []
    names = list(catalog_names)
    for slot in slots:
        hit = None
        for want in slot:
            hit = find_named(want, names)
            if hit:
                break
        if hit:
            picked.append(hit)
            names.remove(hit)
        else:
            notes.append("、".join(slot))
    return picked, notes

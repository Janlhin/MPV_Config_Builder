# -*- coding: utf-8 -*-
"""一键组合：把「最锐利 / 最顺滑 / 最强补帧」这些成套餐一次性填进状态。

每套包含：
    params       参数键值
    shader_slots shader 槽位（每个槽位给出候选名，取本机实际存在的第一个）
    memc_slots   补帧脚本槽位（同上，只会选中第一个命中的）
    note         给用户看的一句话
    need         需要用户自己确认的前提（只在界面提示，不阻止）
"""

from .presets import BASIC_PRESETS

COMBOS = [
    {
        "id": "sharp_base",
        "icon": "💎",
        "name": "最锐利基础",
        "note": "只调参数不加 shader：锐利缩放 + 显示同步，几乎所有机器都能跑。",
        "params": {
            "vo": "gpu-next", "gpu-api": "d3d11", "hwdec": "auto-safe",
            "video-sync": "display-resample",
            "scale": "ewa_lanczossharp", "cscale": "ewa_lanczossharp",
            "dscale": "hermite", "sigmoid-upscaling": "yes",
            "correct-downscaling": "yes", "linear-downscaling": "yes",
        },
        "shader_slots": [],
        "memc_slots": [],
    },
    {
        "id": "sharp_anime",
        "icon": "🌸",
        "name": "动漫锐利链",
        "note": "Anime4K 修复 → 放大 → 压高光 → 自适应锐化，动画线稿向。",
        "params": {
            "vo": "gpu-next", "hwdec": "auto-safe",
            "video-sync": "display-resample",
            "scale": "ewa_lanczossharp", "cscale": "ewa_lanczossharp",
            "sigmoid-upscaling": "yes", "deband": "yes",
        },
        "shader_slots": [
            ["Anime4K Clamp_Highlights"],
            ["Anime4K Restore_CNN_M", "Anime4K Restore_CNN_L"],
            ["Anime4K Upscale_GAN_x2_M", "Anime4K Upscale_CNN_x2_M"],
            ["Adaptive_sharpen"],
        ],
        "memc_slots": [],
    },
    {
        "id": "sharp_real",
        "icon": "🎥",
        "name": "真人锐利链",
        "note": "FSRCNNX 通用超分 + 色度还原 + 收尾锐化，真人影视/纪录片向。",
        "params": {
            "vo": "gpu-next", "hwdec": "auto-safe",
            "video-sync": "display-resample",
            "scale": "spline36", "cscale": "bicubic", "dscale": "hermite",
            "sigmoid-upscaling": "yes", "correct-downscaling": "yes",
        },
        "shader_slots": [
            ["KrigBilateral / CfL"],
            ["FSRCNNX x2_16", "FSRCNNX x2_8", "NNEDI3 nns64", "Ani4Kv2 ArtCNN"],
            ["Adaptive_sharpen", "AMD_CAS", "QCOM SGEDS"],
        ],
        "memc_slots": [],
    },
    {
        "id": "sharp_light",
        "icon": "🪶",
        "name": "轻量超分",
        "note": "RAVU + CAS，几乎不挑显卡；笔记本插电时用。",
        "params": {
            "vo": "gpu-next", "hwdec": "auto-safe",
            "scale": "spline36", "cscale": "bicubic", "dscale": "hermite",
            "sigmoid-upscaling": "yes",
        },
        "shader_slots": [
            ["RAVU r3 zoom-ar", "RAVU r2", "NNEDI3 nns64", "Ani4Kv2 ArtCNN"],
            ["AMD_CAS", "Adaptive_sharpen", "QCOM SGEDS"],
        ],
        "memc_slots": [],
    },
    {
        "id": "smooth_builtin",
        "icon": "⏱️",
        "name": "内置补帧",
        "note": "mpv 自带的时间插值，不吃显卡，24fps → 屏幕刷新率的顺滑感。",
        "params": {
            "video-sync": "display-resample",
            "interpolation": "yes", "tscale": "oversample",
            "hr-seek-framedrop": "no",
        },
        "shader_slots": [],
        "memc_slots": [],
    },
    {
        "id": "smooth_rife",
        "icon": "🎞️",
        "name": "RIFE 补帧",
        "note": "目前最强的 AI 补帧档，需要 RTX 显卡与 mpv-lazy 自带的 RIFE 脚本。",
        "params": {
            "video-sync": "display-resample",
            "interpolation": "no",
        },
        "shader_slots": [],
        "memc_slots": [["RIFE_NV", "RIFE_DML", "RIFE_STD"]],
        "need": "NVIDIA RTX 显卡（无 N 卡请改用 RIFE_DML 或 MVT 档）",
    },
    {
        "id": "smooth_mvt",
        "icon": "🧊",
        "name": "MVT 补帧",
        "note": "MVTools 运动补偿，通用性好、负载比 RIFE 低。",
        "params": {"video-sync": "display-resample", "interpolation": "no"},
        "shader_slots": [],
        "memc_slots": [["MVT_LQ", "MVT_MQ"]],
    },
    {
        "id": "hdr_pass",
        "icon": "🌈",
        "name": "HDR / 广色域",
        "note": "按显示器能力配置色彩映射；不确定就先别开，画面可能反而变暗。",
        "params": {
            "target-prim": "auto", "target-trc": "auto", "target-peak": "auto",
            "tone-mapping": "spline", "hdr-compute-peak": "auto",
            "gamut-mapping-mode": "perceptual",
        },
        "shader_slots": [],
        "memc_slots": [],
        "need": "HDR 显示器 + 系统已开启 HDR；SDR 屏请只保留 tone-mapping",
    },
    {
        "id": "clean_deband",
        "icon": "🧹",
        "name": "去色带 / 洁净",
        "note": "压制渐变区域的色带与压缩瑕疵，动画夜景、暗场最明显。",
        "params": {
            "deband": "yes", "deband-iterations": "2", "deband-threshold": "48",
            "deband-range": "16", "deband-grain": "32",
            "dither-depth": "auto", "temporal-dither": "yes",
        },
        "shader_slots": [],
        "memc_slots": [],
    },
]

COMBO_IDS = [c["id"] for c in COMBOS]


def get_combo(combo_id):
    for c in COMBOS:
        if c["id"] == combo_id:
            return c
    return None


def resolve_combo(combo, catalog):
    """把槽位解析成本机实际存在的路径，返回 (shader 路径列表, vpy 路径, 缺失说明)。"""
    from .schema import find_named
    s_names = [x["name"] for x in catalog.get("shaders", [])]
    s_paths = {x["name"]: x.get("path", "") for x in catalog.get("shaders", [])}
    m_names = [x["name"] for x in catalog.get("memc", [])]
    m_paths = {x["name"]: x.get("path", "") for x in catalog.get("memc", [])}

    shaders, missing = [], []
    for slot in combo.get("shader_slots", []):
        hit = None
        for want in slot:
            hit = find_named(want, s_names)
            if hit:
                break
        if hit:
            shaders.append(s_paths[hit])
            s_names.remove(hit)
        else:
            missing.append("、".join(slot))

    memc = ""
    for slot in combo.get("memc_slots", []):
        hit = None
        for want in slot:
            hit = find_named(want, m_names)
            if hit:
                break
        if hit:
            memc = m_paths[hit]
            break
        missing.append("、".join(slot))
    return shaders, memc, missing


__all__ = ["COMBOS", "COMBO_IDS", "get_combo", "resolve_combo", "BASIC_PRESETS"]

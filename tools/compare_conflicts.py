# -*- coding: utf-8 -*-
"""C-1 等价性证明：新规则表 vs 旧 if 长链，逐字段比对。

为什么不能只靠 tests/data/conflicts_golden.json：
那份基准是 55 个**我挑的**用例。挑漏的搭配 = 漏掉的差异。
所以这里换成**系统枚举**：
  A. 每个会被读到的选项 × 每种取值，单独设一次（看单条规则）；
  B. 选项两两组合（看规则之间的相互影响，尤其是 keys 的动态部分）；
  C. shader 列表：单条、两两、三三，覆盖各家族 + 锐化误伤样本；
  D. memc 路径：各种前缀、各种斜杠、大小写、空串；
  E. A~D 的交叉（两两选项 + shader + memc）。

每个用例都同时喂给两个实现，要求：
  * 返回的 dict 列表**逐字段完全相等**（id/level/title/detail/fix/keys，含顺序）；
  * keys 顺序也算 —— 虽然界面用 set 消费，但顺序变了说明实现偷改了构造方式。

用法：py -3 tools/compare_conflicts.py
"""
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.conflicts import (                 # noqa: E402
    GPU_NEXT_ONLY, GPU_ONLY, _legacy_detect_conflicts, detect_conflicts,
)

# 会被 detect_conflicts 读到的选项，以及各自有代表性的取值。
# 取值里故意混入大小写、带空格、非数字、空串、缺省 —— 这些是判定的边界。
VALUES = {
    "vo": ["", "gpu", "GPU", "gpu-next", "GPU-NEXT", "direct3d", " Gpu "],
    "sigmoid-upscaling": ["", "yes", "no", "YES", "auto", "true", "1", "0", "on"],
    "linear-upscaling": ["", "yes", "no", "auto", "1", "off"],
    "interpolation": ["", "yes", "no", "auto", "1", "YES"],
    "video-sync": ["", "audio", "display-resample", "display-resample-vdrop",
                   "display-vdrop", "DISPLAY-RESAMPLE", "desync"],
    "tscale": ["", "mitchell", "catmull_rom", "oversample", "linear"],
    "deband": ["", "yes", "no", "auto", "1"],
    "deband-iterations": ["", "0", "1", "2", "3", "4", "5", "6", "-1", "abc", "2.5"],
    "deband-range": ["", "0", "15", "16", "31", "32", "33", "64", "abc"],
    "icc-profile": ["", "C:/icc/srgb.icc", "~~/icc/x.icc"],
    "icc-profile-auto": ["", "yes", "no", "auto", "1"],
    "target-prim": ["", "bt.709", "auto"],
    "target-trc": ["", "srgb", "auto"],
    "target-gamut": ["", "bt.709", "auto"],
    "tone-mapping": ["", "hable", "Hable", "HABLE", "spline", "bt.2390", "clip"],
    "hdr-compute-peak": ["", "yes", "no", "auto"],
    "cache": ["", "yes", "no", "auto", "1", "0"],
    "demuxer-max-bytes": ["", "512MiB", "0"],
    "gamut-mapping-mode": ["", "clip", "auto"],
    "corner-rounding": ["", "10"],
    "sharpen": ["", "0.5"],
    "tone-mapping-max-boost": ["", "2"],
}
# 只设一次就够、不值得全取的「大集合」选项：随便挑几个代表
EXTRA_SINGLE = [
    "lut", "image-lut", "icc-use-luma", "sdr-adjust-gamma", "hdr-reference-white",
    "treat-srgb-as-power22", "target-colorspace-hint-mode", "inverse-tone-mapping",
    "sub-hdr-peak", "border-background", "allow-delayed-peak-detect",
    "hdr-contrast-recovery", "hdr-peak-percentile", "target-contrast", "target-lut",
    "image-subs-hdr-peak", "tone-mapping-visualize", "target-colorspace-hint-strict",
]

SHADER_SETS = [
    [],
    [""],
    ["   "],
    ["", "  ", ""],
    ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
    ["~~/shaders/FSRCNNX_x2_16-0-4-1.glsl"],
    ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl", "~~/shaders/FSRCNNX_x2_16-0-4-1.glsl"],
    ["~~/shaders/RAVU_Zoom_R3.glsl"],
    ["~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"],
    ["~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl", "~~/shaders/Anime4K_Upscale_CNN_x2_L.glsl"],
    ["~~/shaders/ArtCNN_C4F32.glsl"],
    ["~~/shaders/ESRGAN_x2.glsl"],
    ["~~/shaders/NNEDI3_nns256_win8x6.glsl"],
    ["~~/shaders/Ani4Kv2_ArtCNN_C4F32.glsl"],
    ["~~/shaders/AMD_CAS.glsl"],
    ["~~/shaders/Adaptive_sharpen.glsl"],
    ["~~/shaders/QCOM_SGEDS.glsl"],
    ["~~/shaders/amd_cas.glsl"],
    # 锐化误伤样本：文件名含 cas 子串但不是锐化
    ["~~/shaders/Cascade_Sharpen.glsl"],
    ["~~/shaders/casual_upscale.glsl"],
    ["~~/shaders/Lumiere_CAS_4.glsl", "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
    # 多家族
    ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl", "~~/shaders/RAVU_Zoom_R3.glsl",
     "~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"],
    # 锐化不在链尾 / 在链尾 / 只有一条
    ["~~/shaders/AMD_CAS.glsl", "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
    ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl", "~~/shaders/AMD_CAS.glsl"],
    ["~~/shaders/AMD_CAS.glsl", "~~/shaders/Adaptive_sharpen.glsl"],
    ["~~/shaders/AMD_CAS.glsl", "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
     "~~/shaders/RAVU_Zoom_R3.glsl"],
    ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl", "~~/shaders/AMD_CAS.glsl",
     "~~/shaders/RAVU_Zoom_R3.glsl"],
    # 大小写 / 反斜杠路径
    ["~~\\shaders\\FSRCNNX_x2_8-0-4-1.GLSL"],
    ["C:\\mpv\\shaders\\Anime4K_Upscale_CNN_x2_M.glsl"],
]

MEMC_SETS = [
    "",
    "~~/vs/MEMC_RIFE_NV.vpy",
    "~~/vs/memc_rife_nv.vpy",
    "~~\\vs\\MEMC_RIFE_NV.vpy",
    "C:\\portable_config\\vs\\MEMC_RIFE_NV.vpy",
    "~~/vs/SR_ESRGAN_x2.vpy",
    "~~/vs/sr_esrgan_x2.vpy",
    "~~/vs/MIX_UAI_ESRGAN.vpy",
    "~~/vs/MIX_anything.vpy",
    "~~/vs/SR.vpy",
    "MEMC_RIFE_NV.vpy",
    "SR_ESRGAN_x2.vpy",
    "   ",
]


def call(fn, values, shaders, memc):
    return fn(values, shaders=shaders, memc=memc)


def diff(old, new):
    """返回第一个不同之处，完全相同则 None。"""
    if old == new:
        return None
    if len(old) != len(new):
        return f"条数 {len(old)} != {len(new)}"
    for i, (a, b) in enumerate(zip(old, new)):
        if a != b:
            fa = {k: a[k] for k in a if a[k] != b.get(k)}
            fb = {k: b[k] for k in b if b[k] != a.get(k)}
            return f"第 {i} 条不同 旧={json.dumps(fa, ensure_ascii=False)} 新={json.dumps(fb, ensure_ascii=False)}"
    return "未知差异"


def main():
    cases = []
    # A. 单选项全取值
    for key, vals in VALUES.items():
        for v in vals:
            cases.append(({key: v}, [], ""))
    # A2. 大集合选项各来一次
    for key in EXTRA_SINGLE:
        cases.append(({key: "x"}, [], ""))
        cases.append(({"vo": "gpu", key: "x"}, [], ""))
        cases.append(({"vo": "gpu-next", key: "x"}, [], ""))
    # B. 两两组合（只看同时非空的搭配，否则大部分是 A 的重复）
    keys = list(VALUES)
    for k1, k2 in itertools.combinations(keys, 2):
        for v1 in VALUES[k1]:
            for v2 in VALUES[k2]:
                if v1 and v2:
                    cases.append(({k1: v1, k2: v2}, [], ""))
    # C/D. shader × memc
    for sh in SHADER_SETS:
        for mc in MEMC_SETS:
            cases.append(({}, sh, mc))
    # E. 交叉：A 的每个用例 × 若干 shader/memc 代表
    reps = [([], ""), (["~~/shaders/AMD_CAS.glsl"], ""),
            (["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
              "~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"], "~~/vs/MEMC_RIFE_NV.vpy"),
            (["~~/shaders/RAVU_Zoom_R3.glsl"], "~~/vs/SR_ESRGAN_x2.vpy")]
    base = [(v, [], "") for v in ({k: val} for k, vals in VALUES.items() for val in vals)]
    for values, _, _ in base:
        for sh, mc in reps:
            cases.append((values, sh, mc))

    n_old_hits = 0
    bad = []
    for i, (values, shaders, memc) in enumerate(cases):
        old = call(_legacy_detect_conflicts, values, shaders, memc)
        new = call(detect_conflicts, values, shaders, memc)
        if old:
            n_old_hits += 1
        d = diff(old, new)
        if d:
            bad.append((i, values, shaders, memc, d))

    print(f"用例总数 {len(cases)}（其中 {n_old_hits} 个有输出）")
    if bad:
        print(f"!!! 不一致 {len(bad)} 处：")
        for i, values, shaders, memc, d in bad[:10]:
            print(f"  #{i} values={json.dumps(values, ensure_ascii=False)} "
                  f"shaders={json.dumps(shaders, ensure_ascii=False)} memc={memc!r}")
            print(f"      {d}")
        if len(bad) > 10:
            print(f"  （只显示前 10 处）")
        return 1
    print("新旧实现逐字段完全一致 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

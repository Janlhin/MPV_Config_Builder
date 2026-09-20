# -*- coding: utf-8 -*-
"""生成 tests/data/conflicts_golden.json —— 冲突检测的「行为快照」。

为什么要有这个文件
------------------
2026-09 决定把 core/conflicts.py 里 154 行的 if 长链改写成规则表（C-1）。
改写是纯重构，任何一条规则的 id / 级别 / 文案 / 涉及选项都不许变。
但 detect_conflicts() 的返回值是给前端直接渲染的，字段多、分支密，
光靠 tests/test_conflicts.py 那 32 个 assertIn/assertEqual 挡不住细微漂移
（比如某条规则的 detail 少了一个字、或者两条规则的输出顺序换了）。

所以先用**当前实现**跑一遍固定用例，把逐字段的完整结果存成 JSON 当基准；
重构之后 tests/test_conflicts_snapshot.py 会把结果和这份 JSON 逐字节比对。
基准必须由重构前的代码生成 —— 用重构后的代码生成基准等于自己给自己判卷。

用法
----
    py -3 tools/gen_conflicts_golden.py          # 生成/覆盖基准
    py -3 tools/gen_conflicts_golden.py --check  # 只比对，不写盘

注意：这个脚本会 import core.conflicts，所以重构前后跑出来的东西必须完全一样。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.conflicts import conflict_keys, conflicts_as_issues, detect_conflicts  # noqa: E402

OUT = ROOT / "tests" / "data" / "conflicts_golden.json"

# 固定用例表。设计原则：
#   1. 17 条规则每条至少有一个用例能触发它（由下面的校验 + 测试共同保证）；
#   2. 每条规则的「不该触发」的反面也尽量覆盖，防止重构时条件写反；
#   3. 故意留几个多规则同时命中的用例，用来锁住 level 排序和并列时的 id 排序；
#   4. 边界值（deband-iterations = 4 / 3 / range = 16 / 32）单独列，防止
#      重构时把 >= 写成 >、把 and 写成 or。
CASES = [
    # ---- 0. 干净配置：什么都不该报 ----
    {
        "name": "clean_default",
        "values": {"vo": "gpu-next", "scale": "spline36", "deband": "yes",
                   "deband-iterations": "2", "cache": "yes"},
    },
    {
        "name": "clean_empty",
        "values": {},
    },

    # ---- 1. 缩放：sigmoid_vs_linear / linear_upscaling_alone ----
    {
        "name": "sigmoid_and_linear",
        "values": {"sigmoid-upscaling": "yes", "linear-upscaling": "yes"},
    },
    {
        "name": "linear_alone",
        "values": {"linear-upscaling": "yes"},
    },
    {
        "name": "sigmoid_alone_ok",
        "values": {"sigmoid-upscaling": "yes"},
    },
    {
        "name": "linear_no_is_ok",
        "values": {"linear-upscaling": "no"},
    },

    # ---- 2. 插值：interp_needs_sync / interp_with_memc / interp_no_tscale ----
    {
        "name": "interp_without_display_sync",
        "values": {"interpolation": "yes", "video-sync": "audio", "tscale": "mitchell"},
    },
    {
        "name": "interp_no_video_sync_at_all",
        "values": {"interpolation": "yes", "tscale": "mitchell"},
    },
    {
        "name": "interp_display_sync_but_no_tscale",
        "values": {"interpolation": "yes", "video-sync": "display-resample"},
    },
    {
        "name": "interp_display_sync_with_tscale_ok",
        "values": {"interpolation": "yes", "video-sync": "display-resample",
                   "tscale": "mitchell"},
    },
    {
        "name": "interp_with_memc_script",
        "values": {"interpolation": "yes", "video-sync": "display-resample",
                   "tscale": "mitchell"},
        "memc": "~~/vs/MEMC_RIFE_NV.vpy",
    },

    # ---- 3. 去色带：deband_zero_iterations / _iterations_high / _range_vs_iterations ----
    {
        "name": "deband_off_ignores_iterations",
        "values": {"deband": "no", "deband-iterations": "0"},
    },
    {
        "name": "deband_without_iterations_ok",
        "values": {"deband": "yes"},
    },
    {
        "name": "deband_zero_iterations",
        "values": {"deband": "yes", "deband-iterations": "0"},
    },
    {
        "name": "deband_iterations_at_4_ok",
        "values": {"deband": "yes", "deband-iterations": "4", "deband-range": "16"},
    },
    {
        "name": "deband_iterations_above_4",
        "values": {"deband": "yes", "deband-iterations": "6"},
    },
    {
        "name": "deband_range_boundary_31_no",
        "values": {"deband": "yes", "deband-iterations": "4", "deband-range": "31"},
    },
    {
        "name": "deband_range_boundary_32_yes",
        "values": {"deband": "yes", "deband-iterations": "4", "deband-range": "32"},
    },
    {
        "name": "deband_range_high_but_iterations_low_ok",
        "values": {"deband": "yes", "deband-iterations": "2", "deband-range": "48"},
    },
    {
        "name": "deband_high_iterations_and_range",
        "values": {"deband": "yes", "deband-iterations": "5", "deband-range": "40"},
    },
    {
        "name": "deband_iterations_not_a_number",
        "values": {"deband": "yes", "deband-iterations": "abc"},
    },

    # ---- 4. 色彩管理：icc_profile_vs_target / icc_auto_vs_profile / hable_needs_peak ----
    {
        "name": "icc_profile_with_target",
        "values": {"icc-profile": "C:/icc/srgb.icc", "target-prim": "bt.709"},
    },
    {
        "name": "icc_profile_with_two_targets",
        "values": {"icc-profile": "C:/icc/srgb.icc", "target-trc": "srgb",
                   "target-gamut": "bt.709"},
    },
    {
        "name": "icc_auto_without_profile_ok",
        "values": {"icc-profile-auto": "yes"},
    },
    {
        "name": "icc_auto_and_profile_and_target",
        "values": {"icc-profile-auto": "yes", "icc-profile": "C:/icc/srgb.icc",
                   "target-prim": "bt.709"},
    },
    {
        "name": "hable_without_peak",
        "values": {"tone-mapping": "hable"},
    },
    {
        "name": "hable_with_peak_ok",
        "values": {"tone-mapping": "hable", "hdr-compute-peak": "yes"},
    },
    {
        "name": "hable_uppercase_still_detected",
        "values": {"tone-mapping": "Hable"},
    },
    {
        "name": "spline_tone_mapping_ok",
        "values": {"tone-mapping": "spline"},
    },

    # ---- 5. 渲染器独占项：gpunext_only_with_gpu / gpu_only_with_gpunext ----
    {
        "name": "gpu_with_gpunext_only_option",
        "values": {"vo": "gpu", "gamut-mapping-mode": "clip"},
    },
    {
        "name": "gpu_with_many_gpunext_only_options",
        "values": {"vo": "gpu", "gamut-mapping-mode": "clip", "target-gamut": "bt.709",
                   "lut": "C:/lut.cube", "image-lut": "C:/img.cube",
                   "icc-use-luma": "yes", "sdr-adjust-gamma": "yes",
                   "hdr-reference-white": "203", "treat-srgb-as-power22": "yes"},
    },
    {
        "name": "gpu_alone_ok",
        "values": {"vo": "gpu", "scale": "spline36"},
    },
    {
        "name": "gpunext_with_gpu_only_option",
        "values": {"vo": "gpu-next", "corner-rounding": "10"},
    },
    {
        "name": "gpunext_with_three_gpu_only_options",
        "values": {"vo": "gpu-next", "corner-rounding": "10", "sharpen": "0.5",
                   "tone-mapping-max-boost": "2"},
    },
    {
        "name": "gpunext_with_all_gpu_only_options",
        "values": {"vo": "gpu-next", "corner-rounding": "10", "sharpen": "0.5",
                   "tone-mapping-max-boost": "2", "gamut-mapping-mode": "clip"},
    },
    {
        "name": "vo_uppercase_is_normalised",
        "values": {"vo": "GPU", "gamut-mapping-mode": "clip"},
    },

    # ---- 6. shader 链：double_upscale_shaders / vpy_sr_with_shader_sr / sharpen_not_last ----
    {
        "name": "single_shader_family_ok",
        "values": {},
        "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
    },
    {
        "name": "two_shader_families",
        "values": {},
        "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                    "~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"],
    },
    {
        "name": "two_families_same_family_twice_ok",
        "values": {},
        "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                    "~~/shaders/FSRCNNX_x2_16-0-4-1.glsl"],
    },
    {
        "name": "empty_shader_entries_ignored",
        "values": {},
        "shaders": ["", "   "],
    },
    {
        "name": "vpy_superres_with_shader_superres",
        "values": {},
        "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
        "memc": "~~/vs/SR_ESRGAN_x2.vpy",
    },
    {
        "name": "vpy_superres_without_shader_ok",
        "values": {},
        "memc": "~~/vs/SR_ESRGAN_x2.vpy",
    },
    {
        "name": "vpy_superres_with_only_sharpen_shader_ok",
        "values": {},
        "shaders": ["~~/shaders/AMD_CAS.glsl"],
        "memc": "~~/vs/SR_ESRGAN_x2.vpy",
    },
    {
        "name": "vpy_mix_uai_counts_as_superres",
        "values": {},
        "shaders": ["~~/shaders/RAVU_Zoom_R3.glsl"],
        "memc": "~~/vs/MIX_UAI_ESRGAN.vpy",
    },
    {
        "name": "memc_prefix_is_not_superres",
        "values": {},
        "shaders": ["~~/shaders/RAVU_Zoom_R3.glsl"],
        "memc": "~~/vs/MEMC_RIFE_NV.vpy",
    },
    {
        "name": "sharpen_not_last",
        "values": {},
        "shaders": ["~~/shaders/AMD_CAS.glsl",
                    "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
    },
    {
        "name": "sharpen_at_last_ok",
        "values": {},
        "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                    "~~/shaders/AMD_CAS.glsl"],
    },
    {
        "name": "sharpen_only_one_shader_ok",
        "values": {},
        "shaders": ["~~/shaders/AMD_CAS.glsl"],
    },
    {
        "name": "sharpen_substring_false_positive_guarded",
        "values": {},
        # 文件名里有 cascade，不该被当成锐化（历史上裸 "cas" 子串匹配踩过这个坑）
        "shaders": ["~~/shaders/Cascade_Sharpen.glsl",
                    "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
    },

    # ---- 7. 缓存：cache_off_but_buffer ----
    {
        "name": "cache_off_with_demuxer_buffer",
        "values": {"cache": "no", "demuxer-max-bytes": "512MiB"},
    },
    {
        "name": "cache_missing_with_demuxer_buffer",
        "values": {"demuxer-max-bytes": "512MiB"},
    },
    {
        "name": "cache_on_with_demuxer_buffer_ok",
        "values": {"cache": "yes", "demuxer-max-bytes": "512MiB"},
    },
    {
        "name": "cache_off_without_demuxer_buffer_ok",
        "values": {"cache": "no"},
    },

    # ---- 8. 多规则 + 排序：锁住 level 排序、同级别按 id 排序 ----
    {
        "name": "many_rules_sorted",
        "values": {
            "vo": "gpu",
            "sigmoid-upscaling": "yes", "linear-upscaling": "yes",
            "interpolation": "yes", "video-sync": "audio",
            "deband": "yes", "deband-iterations": "0",
            "icc-profile-auto": "yes", "icc-profile": "C:/icc/srgb.icc",
            "target-prim": "bt.709", "tone-mapping": "hable",
            "gamut-mapping-mode": "clip", "cache": "no",
            "demuxer-max-bytes": "512MiB",
        },
        "shaders": ["~~/shaders/AMD_CAS.glsl",
                    "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                    "~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"],
        "memc": "~~/vs/MEMC_RIFE_NV.vpy",
    },
    {
        "name": "error_outranks_warn",
        "values": {"interpolation": "yes", "sigmoid-upscaling": "yes",
                   "linear-upscaling": "yes", "video-sync": "audio"},
    },
]


def run_case(case):
    conflicts = detect_conflicts(case["values"], shaders=case.get("shaders"),
                                 memc=case.get("memc", ""))
    return {
        # 入参也要存进基准：快照必须自带输入，否则测试没法「原样重放」
        "values": case["values"],
        "shaders": case.get("shaders", []),
        "memc": case.get("memc", ""),
        # 输出：三个对外函数的结果全存
        "conflicts": conflicts,
        "issues": [list(x) for x in conflicts_as_issues(conflicts)],
        "keys": sorted(conflict_keys(conflicts)),
    }


def build():
    return {
        "note": "mpv 配置冲突检测的行为快照（C-1 重构基准）。"
                "由 tools/gen_conflicts_golden.py 生成，禁止手工编辑。",
        "count": len(CASES),
        "cases": [dict({"name": c["name"]}, **run_case(c)) for c in CASES],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只比对，不写盘")
    args = ap.parse_args()

    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n"

    if args.check:
        if not OUT.is_file():
            print(f"[缺失] {OUT}")
            return 1
        cur = OUT.read_text(encoding="utf-8")
        if cur == text:
            print(f"[一致] {len(data['cases'])} 个用例与基准完全相同")
            return 0
        print(f"[不一致] {OUT} 与当前实现不符 —— 重构改动了行为，请逐条核对")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    n_ok = sum(1 for c in data["cases"] if c["conflicts"])
    print(f"[写入] {OUT}  ({len(text.encode('utf-8'))} 字节)")
    print(f"       {len(data['cases'])} 个用例，其中 {n_ok} 个命中至少一条规则")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""冲突检测规则测试。每条规则都要能触发、也要能确认不误报。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.conflicts import (                 # noqa: E402
    conflicts_as_issues, conflict_keys, detect_conflicts,
)


def ids(conflicts):
    return [c["id"] for c in conflicts]


class ConflictTest(unittest.TestCase):
    def test_clean_config_has_no_conflicts(self):
        got = detect_conflicts({"vo": "gpu-next", "scale": "spline36",
                                "deband": "yes", "deband-iterations": "2"})
        self.assertEqual(got, [])

    # ---- 缩放 ----
    def test_sigmoid_vs_linear(self):
        got = detect_conflicts({"sigmoid-upscaling": "yes", "linear-upscaling": "yes"})
        self.assertIn("sigmoid_vs_linear", ids(got))

    def test_linear_alone_is_only_info(self):
        got = detect_conflicts({"linear-upscaling": "yes"})
        self.assertEqual(ids(got), ["linear_upscaling_alone"])
        self.assertEqual(got[0]["level"], "info")

    # ---- 插值 ----
    def test_interpolation_without_display_sync_is_error(self):
        got = detect_conflicts({"interpolation": "yes", "video-sync": "audio"})
        self.assertIn("interp_needs_sync", ids(got))
        self.assertEqual(got[0]["level"], "error")
        self.assertEqual(set(got[0]["keys"]), {"interpolation", "video-sync"})

    def test_interpolation_with_display_sync_ok(self):
        self.assertNotIn("interp_needs_sync",
                         ids(detect_conflicts({"interpolation": "yes",
                                               "video-sync": "display-resample"})))
        self.assertNotIn("interp_needs_sync",
                         ids(detect_conflicts({"interpolation": "yes",
                                               "video-sync": "display-resample-vdrop"})))

    def test_interpolation_with_memc_script(self):
        got = detect_conflicts({"interpolation": "yes", "video-sync": "display-resample"},
                               memc="~~/vs/MEMC_RIFE_NV.vpy")
        self.assertIn("interp_with_memc", ids(got))

    def test_interpolation_without_tscale(self):
        got = detect_conflicts({"interpolation": "yes", "video-sync": "display-resample"})
        self.assertIn("interp_no_tscale", ids(got))

    # ---- 去色带 ----
    def test_deband_zero_iterations(self):
        got = detect_conflicts({"deband": "yes", "deband-iterations": "0"})
        self.assertIn("deband_zero_iterations", ids(got))

    def test_deband_iterations_too_high(self):
        got = detect_conflicts({"deband": "yes", "deband-iterations": "8"})
        self.assertIn("deband_iterations_high", ids(got))

    def test_deband_range_compensation_hint(self):
        got = detect_conflicts({"deband": "yes", "deband-iterations": "3", "deband-range": "32"})
        self.assertIn("deband_range_vs_iterations", ids(got))

    def test_deband_off_means_no_complaints(self):
        got = detect_conflicts({"deband": "no", "deband-iterations": "0"})
        self.assertNotIn("deband_zero_iterations", ids(got))

    # ---- 色彩 ----
    def test_icc_profile_overrides_targets(self):
        got = detect_conflicts({"icc-profile": "C:/x.icc", "target-prim": "bt.2020",
                                "target-trc": "pq"})
        self.assertIn("icc_profile_vs_target", ids(got))
        rule = [c for c in got if c["id"] == "icc_profile_vs_target"][0]
        self.assertIn("target-prim", rule["keys"])
        self.assertIn("target-trc", rule["keys"])

    def test_icc_auto_with_manual_profile(self):
        got = detect_conflicts({"icc-profile-auto": "yes", "icc-profile": "C:/x.icc"})
        self.assertIn("icc_auto_vs_profile", ids(got))

    def test_hable_suggests_compute_peak(self):
        got = detect_conflicts({"tone-mapping": "hable"})
        self.assertIn("hable_needs_peak", ids(got))
        self.assertNotIn("hable_needs_peak",
                         ids(detect_conflicts({"tone-mapping": "hable",
                                               "hdr-compute-peak": "yes"})))

    # ---- 渲染器独占 ----
    def test_gpunext_only_option_with_vo_gpu(self):
        got = detect_conflicts({"vo": "gpu", "target-gamut": "bt.709",
                                "gamut-mapping-mode": "clip"})
        self.assertIn("gpunext_only_with_gpu", ids(got))
        rule = [c for c in got if c["id"] == "gpunext_only_with_gpu"][0]
        self.assertIn("target-gamut", rule["keys"])

    def test_gpu_only_option_with_vo_gpunext(self):
        got = detect_conflicts({"vo": "gpu-next", "sharpen": "0.5"})
        self.assertIn("gpu_only_with_gpunext", ids(got))

    def test_matching_renderer_no_warning(self):
        self.assertEqual(ids(detect_conflicts({"vo": "gpu-next", "target-gamut": "bt.709"})), [])
        self.assertEqual(ids(detect_conflicts({"vo": "gpu", "sharpen": "0.5"})), [])

    # ---- shader 链 ----
    def test_two_upscale_families(self):
        got = detect_conflicts({}, ["~~/shaders/FSRCNNX/FSRCNNX_x2_16.glsl",
                                    "~~/shaders/RAVU/ravu_r3.glsl"])
        self.assertIn("double_upscale_shaders", ids(got))

    def test_single_family_is_fine(self):
        got = detect_conflicts({}, ["~~/shaders/FSRCNNX/FSRCNNX_x2_8.glsl",
                                    "~~/shaders/FSRCNNX/FSRCNNX_x2_16.glsl"])
        self.assertNotIn("double_upscale_shaders", ids(got))

    def test_vpy_superres_with_shader_superres(self):
        got = detect_conflicts({}, ["~~/shaders/FSRCNNX/FSRCNNX_x2_16.glsl"],
                               memc="~~/vs/SR_ARTCNN_NV.vpy")
        self.assertIn("vpy_sr_with_shader_sr", ids(got))

    def test_memc_script_with_shader_is_not_flagged(self):
        got = detect_conflicts({}, ["~~/shaders/FSRCNNX/FSRCNNX_x2_16.glsl"],
                               memc="~~/vs/MEMC_RIFE_NV.vpy")
        self.assertNotIn("vpy_sr_with_shader_sr", ids(got))

    def test_sharpen_not_last(self):
        got = detect_conflicts({}, ["~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl",
                                    "~~/shaders/FSRCNNX/FSRCNNX_x2_8.glsl"])
        self.assertIn("sharpen_not_last", ids(got))

    def test_sharpen_last_is_fine(self):
        got = detect_conflicts({}, ["~~/shaders/FSRCNNX/FSRCNNX_x2_8.glsl",
                                    "~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"])
        self.assertNotIn("sharpen_not_last", ids(got))

    # ---- 缓存 ----
    def test_cache_off_but_buffer_set(self):
        got = detect_conflicts({"cache": "no", "demuxer-max-bytes": "500MiB"})
        self.assertIn("cache_off_but_buffer", ids(got))

    # ---- 结构与排序 ----
    def test_sorted_by_level(self):
        got = detect_conflicts({"interpolation": "yes", "video-sync": "audio",
                               "linear-upscaling": "yes"})
        levels = [c["level"] for c in got]
        self.assertEqual(levels, sorted(levels, key=lambda x: {"error": 0, "warn": 1, "info": 2}[x]))

    def test_shape_and_helpers(self):
        got = detect_conflicts({"interpolation": "yes", "video-sync": "audio"})
        for c in got:
            for field in ("id", "level", "title", "detail", "fix", "keys"):
                self.assertIn(field, c, field)
        issues = conflicts_as_issues(got)
        self.assertTrue(all(len(x) == 2 for x in issues))
        self.assertIn("interpolation", conflict_keys(got))

    def test_empty_state(self):
        self.assertEqual(detect_conflicts({}), [])
        self.assertEqual(detect_conflicts(None, None, ""), [])

    def test_values_may_be_non_string(self):
        got = detect_conflicts({"interpolation": True, "video-sync": "audio",
                                "deband-iterations": 0, "deband": "yes"})
        self.assertIn("interp_needs_sync", ids(got))


class SharpenMatchTest(unittest.TestCase):
    """「锐化 shader 不在链尾」的识别不能靠裸子串 cas 误伤。"""

    def _sharpen_not_last(self, *shaders):
        return "sharpen_not_last" in ids(detect_conflicts({}, list(shaders)))

    def test_real_sharpen_shaders_detected(self):
        for name in ("~~/shaders/AMD_CAS/AMD_CAS.glsl",
                     "~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl",
                     "~~/shaders/QCOM/QCOM_SGEDS_ms_RT.glsl",
                     "~~/shaders/x/amd_cas.glsl"):
            got = self._sharpen_not_last(name, "~~/shaders/b.glsl")
            self.assertTrue(got, f"{name} 应当被认成锐化")

    def test_unrelated_names_not_flagged(self):
        """文件名里恰好含 cas 的（Cascade 等）不该被误认成锐化。"""
        for name in ("~~/shaders/Cascade/Cascade_x2.glsl",
                     "~~/shaders/castle.glsl",
                     "~~/shaders/Anime4K/Anime4K_Restore_CNN_M.glsl"):
            got = self._sharpen_not_last(name, "~~/shaders/b.glsl")
            self.assertFalse(got, f"{name} 被误判成锐化了")

    def test_sharpen_last_is_fine(self):
        self.assertFalse(self._sharpen_not_last("~~/shaders/a.glsl",
                                                "~~/shaders/AMD_CAS.glsl"))

    def test_single_shader_never_flags(self):
        self.assertFalse(self._sharpen_not_last("~~/shaders/AMD_CAS.glsl"))


if __name__ == "__main__":
    unittest.main()

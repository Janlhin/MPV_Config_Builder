# -*- coding: utf-8 -*-
"""分析与评分单元测试。"""
import unittest

from core import analyze_config_text, score_active


class TestAnalyze(unittest.TestCase):
    def test_empty(self):
        r = analyze_config_text("# 只有注释\n\n")
        self.assertEqual(r["option_count"], 0)
        self.assertTrue(r["issues"])
        self.assertIn("配置为空", r["issues"][0])

    def test_known_and_unknown(self):
        text = "vo=gpu-next\nscale=ewa_lanczossharp\n我乱写的=1\nfoo=bar\n"
        r = analyze_config_text(text)
        keys = [x["key"] for x in r["known"]]
        self.assertIn("vo", keys)
        self.assertIn("scale", keys)
        unknown_keys = [k for k, _v, _n in r["unknown"]]
        self.assertIn("foo", unknown_keys)
        self.assertTrue(r["issues"])

    def test_duplicates_detected(self):
        r = analyze_config_text("scale=bilinear\nscale=spline36\n")
        self.assertEqual(len(r["duplicates"]), 1)

    def test_shader_lines_collected(self):
        r = analyze_config_text('glsl-shaders="a.glsl;b.glsl"\nvf=vapoursynth="x.vpy"\n')
        self.assertEqual(len(r["shaders"]), 1)
        self.assertEqual(r["shaders"][0]["key"], "glsl-shaders")
        self.assertIn("a.glsl", r["shaders"][0]["value"])
        # vf 属于标准选项，应被识别（不算未知）
        unknown_keys = [k for k, _v, _n in r["unknown"]]
        self.assertNotIn("vf", unknown_keys)

    def test_scores_in_range(self):
        r = analyze_config_text("vo=gpu-next\nscale=ewa_lanczossharp\ninterpolation=yes\n")
        for name, val in r["scores"].items():
            self.assertGreaterEqual(val, 0)
            self.assertLessEqual(val, 100)
        self.assertGreaterEqual(r["overall"], 0)
        self.assertLessEqual(r["overall"], 100)
        self.assertIn(r["grade"], ("极限画质", "高画质", "均衡", "轻量"))


class TestScore(unittest.TestCase):
    def test_baseline(self):
        s = score_active([])
        self.assertEqual(set(s), {"quality", "sharp", "smooth", "color", "stability", "load"})

    def test_shader_raises_load(self):
        base = score_active([])
        with_shader = score_active(["shader:FSRCNNX x2_16"])
        self.assertGreater(with_shader["load"], base["load"])
        self.assertGreaterEqual(with_shader["sharp"], base["sharp"])

    def test_unknown_shader_is_safe(self):
        s = score_active(["shader:不存在的 shader"])
        self.assertLessEqual(s["load"], 100)

    def test_memc_counts(self):
        base = score_active([])
        with_memc = score_active(["memc:RIFE_NV"])
        self.assertGreater(with_memc["smooth"], base["smooth"])
        self.assertGreater(with_memc["load"], base["load"])


if __name__ == "__main__":
    unittest.main()

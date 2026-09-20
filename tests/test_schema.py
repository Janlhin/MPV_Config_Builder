# -*- coding: utf-8 -*-
"""核心逻辑单元测试：参数表 / 原生选项 / 路径辅助 / 清单构建。"""
import tempfile
import unittest
from pathlib import Path

from core import (
    PARAMS, NATIVE_OPTIONS, NATIVE_TYPES, NATIVE_EDITABLE_TYPES, native_items,
    validate_native_value, get_param_meta,
    norm_mpv_path, split_mpv_list, extract_vapoursynth_path, strip_inline_comment,
    build_shader_catalog, build_memc_catalog, SHADERS, SHADER_PATHS, MEMC_PRESETS,
)


class TestParams(unittest.TestCase):
    def test_core_params_shape(self):
        for cat, items in PARAMS.items():
            self.assertTrue(items, f"{cat} 分类为空")
            for item in items:
                key, label, desc, options, q, load = item
                self.assertTrue(key and label and desc)
                self.assertIsInstance(options, list)
                self.assertTrue(options, f"{key} 没有可选值")

    def test_get_param_meta(self):
        meta = get_param_meta("scale")
        self.assertIsNotNone(meta)
        self.assertEqual(meta[0], "scale")
        self.assertIsNone(get_param_meta("不存在的选项"))


class TestNativeOptions(unittest.TestCase):
    def test_counts(self):
        self.assertGreaterEqual(len(NATIVE_OPTIONS), 6)
        items = native_items()
        self.assertGreaterEqual(len(items), 80)

    def test_keys_unique(self):
        keys = [k for _g, k, _l, _d, _v, _t in native_items()]
        self.assertEqual(len(keys), len(set(keys)), "原生选项有重复 key")

    def test_no_overlap_with_core(self):
        core_keys = {item[0] for items in PARAMS.values() for item in items}
        for _g, key, _l, _d, _v, _t in native_items():
            self.assertNotIn(key, core_keys, f"{key} 同时出现在核心与原生选项里")

    def test_types_declared(self):
        for _g, key, _l, _d, _v, typ in native_items():
            self.assertIn(typ, {"bool", "enum", "int", "float", "str", "color", "list"})
            self.assertIn(key, NATIVE_TYPES)
            if typ in ("bool", "enum"):
                self.assertNotIn(typ, NATIVE_EDITABLE_TYPES)

    def test_validate(self):
        self.assertTrue(validate_native_value("dither-depth", "8")[0])
        # mpv 的 dither-depth 是「命名取值 + 整数」（Choices: no, auto (or an integer)），
        # 所以数字要放行；文字乱写才拦
        self.assertTrue(validate_native_value("dither-depth", "99")[0])
        self.assertFalse(validate_native_value("dither-depth", "很深")[0])
        self.assertTrue(validate_native_value("deband-iterations", "3")[0])
        self.assertFalse(validate_native_value("deband-iterations", "abc")[0])
        self.assertFalse(validate_native_value("deband-iterations", "99")[0])   # 全量库给了 0..16
        self.assertTrue(validate_native_value("scale-antiring", "0.6")[0])
        self.assertFalse(validate_native_value("scale-antiring", "很高")[0])
        self.assertTrue(validate_native_value("sub-color", "#FFD766")[0])
        self.assertFalse(validate_native_value("sub-color", "red")[0])
        self.assertFalse(validate_native_value("volume-max", "")[0])
        # 全量选项库认识的取值也要放行（精选层的建议值不是全集）
        self.assertTrue(validate_native_value("tone-mapping", "st2094-40")[0])
        self.assertFalse(validate_native_value("tone-mapping", "瞎写")[0])
        self.assertTrue(validate_native_value("deband", "yes")[0])
        self.assertFalse(validate_native_value("deband", "maybe")[0])
        # scale 有全量库的真实取值表（39 个 filter），乱写要拦
        self.assertTrue(validate_native_value("scale", "ewa_lanczossharp")[0])
        self.assertFalse(validate_native_value("scale", "随便")[0])
        # 数据库与精选层都没收录的选项一律放行
        self.assertTrue(validate_native_value("完全不存在的选项", "随便")[0])


class TestPathHelpers(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(norm_mpv_path("~~/shaders/A.glsl"), "shaders/a.glsl")
        self.assertEqual(norm_mpv_path('"~~\\shaders\\B.glsl"'), "shaders/b.glsl")
        self.assertEqual(norm_mpv_path("C:/x/y.glsl"), "c:/x/y.glsl")

    def test_split_list(self):
        self.assertEqual(split_mpv_list("a;b;c"), ["a", "b", "c"])
        self.assertEqual(split_mpv_list('"x:y:z"'), ["x", "y", "z"])
        # Windows 盘符不能当成分隔符
        self.assertEqual(split_mpv_list("C:/shaders/a.glsl"), ["C:/shaders/a.glsl"])

    def test_extract_vapoursynth(self):
        self.assertEqual(
            extract_vapoursynth_path('vapoursynth="~~/vs/A.vpy"'), "~~/vs/A.vpy")
        self.assertEqual(
            extract_vapoursynth_path('@lbl:vapoursynth=~~/vs/B.vpy'), "~~/vs/B.vpy")
        self.assertEqual(extract_vapoursynth_path("scale=bilinear"), "scale=bilinear")

    def test_strip_inline_comment(self):
        self.assertEqual(strip_inline_comment("100   # 说明"), "100")
        self.assertEqual(strip_inline_comment('"#FFD766"'), '"#FFD766"')
        self.assertEqual(strip_inline_comment("no"), "no")


class TestCatalogs(unittest.TestCase):
    def test_generic_mode(self):
        shaders = build_shader_catalog(None)
        memc = build_memc_catalog(None)
        self.assertEqual(len(shaders), len(SHADERS))
        self.assertEqual(len(memc), len(MEMC_PRESETS))
        for item in shaders:
            self.assertIn("name", item)
            self.assertIn("path", item)

    def test_lazy_mode_filters_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            pc = Path(tmp)
            (pc / "vs").mkdir()
            # 按 SHADER_PATHS 里的真实相对路径放一个文件
            rel = norm_mpv_path(SHADER_PATHS["RAVU r3 zoom-ar"])
            target = pc / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("//!DESC x\n", encoding="utf-8")
            shaders = build_shader_catalog(pc)
            names = [s["name"] for s in shaders]
            self.assertIn("RAVU r3 zoom-ar", names)
            self.assertNotIn("FSRCNNX x2_16", names)
            # 未收录的额外文件会被自动发现
            (pc / "shaders" / "custom.glsl").write_text("//!DESC y\n", encoding="utf-8")
            names2 = [s["name"] for s in build_shader_catalog(pc)]
            self.assertIn("custom", names2)
            # 缺失清单：本目录里没有的条目
            self.assertTrue(any(not (pc / norm_mpv_path(p)).is_file() for p in SHADER_PATHS.values()))


if __name__ == "__main__":
    unittest.main()

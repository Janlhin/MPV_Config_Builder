# -*- coding: utf-8 -*-
"""VPY 融合（R-3）测试：解析真实 mpv-lazy 脚本 + 合成 + 安全规则。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.vpy import (                       # noqa: E402
    MARKER, PREFIX, build_fused, check_syntax, fuse_files, parse_script,
    plan_fusion, script_role, write_fused,
)

SIMPLE = '''\
### 测试用脚本：放大两倍

import vapoursynth as vs
from vapoursynth import core
import k7sfunc as k7f

core.num_threads = k7f.vs_t_dft
clip = video_in

############
# 用户选项 #
############

H_Pre = 720
Lk_Fmt = False
## 整数，预降低处理源高度
## <True|False> 锁定像素格式

ret = k7f.FMT_CTRL(clip, h_max=1200, h_ret=True)
clip = k7f.FMT_CTRL(clip, h_max=H_Pre, fmt_pix=1 if Lk_Fmt else 0)
clip = k7f.ARTCNN_NV(clip, model=8, gpu=0)
clip.set_output()
'''

MEMC = '''\
### 测试用脚本：补帧

import vapoursynth as vs
from vapoursynth import core
import k7sfunc as k7f

core.num_threads = k7f.vs_t_dft
clip = video_in

H_Pre = 1440
Fps_Num = 2
## 整数，预降低处理源高度

clip = k7f.FMT_CTRL(clip, h_max=H_Pre, fmt_pix=0)
clip = k7f.MVT_LQ(clip, fps_in=container_fps, fps_out=container_fps*2)
clip.set_output()
'''

VS_DIR = Path(r"C:\Program Files\mpv-lazy\portable_config\vs")


class ParseTest(unittest.TestCase):
    def test_parse_structure(self):
        s = parse_script(SIMPLE, "SR_TEST.vpy")
        self.assertEqual(s["name"], "SR_TEST.vpy")
        self.assertIn("import k7sfunc as k7f", s["imports"])
        self.assertEqual(s["inits"], ["core.num_threads = k7f.vs_t_dft"])
        self.assertIn("H_Pre = 720", s["options"])
        self.assertIn("Lk_Fmt = False", s["options"])
        self.assertTrue(any("ARTCNN_NV" in x for x in s["pipeline"]))
        self.assertTrue(s["has_output"])
        self.assertEqual(s["unknown"], [])

    def test_multiline_call_is_one_statement(self):
        text = ("import vapoursynth as vs\nclip = video_in\n"
                "clip = k7f.XXX(clip,\n    a=1,\n    b=2)\nclip.set_output()\n")
        s = parse_script(text, "X.vpy")
        joined = "\n".join(s["pipeline"])
        self.assertIn("a=1", joined)
        self.assertIn("b=2", joined)
        self.assertEqual(len([x for x in s["pipeline"] if x.strip().startswith("clip =")]), 1)

    def test_role_by_filename(self):
        self.assertEqual(script_role("ETC_DEINT_EX.vpy")[0], "deint")
        self.assertEqual(script_role("NR_CCD_STD.vpy")[0], "denoise")
        self.assertEqual(script_role("SR_ARTCNN_NV.vpy")[0], "superres")
        self.assertEqual(script_role("MEMC_RIFE_NV.vpy")[0], "memc")
        self.assertEqual(script_role("MIX_UAI_DML.vpy")[0], "superres")
        self.assertEqual(script_role("MIX_UVR_MAD.vpy")[0], "unfusable")


class FuseTest(unittest.TestCase):
    def _scripts(self):
        return [parse_script(SIMPLE, "SR_TEST.vpy"), parse_script(MEMC, "MEMC_TEST.vpy")]

    def test_order_is_deint_denoise_superres_memc(self):
        scripts = [parse_script(MEMC, "MEMC_TEST.vpy"),
                   parse_script(SIMPLE, "SR_TEST.vpy"),
                   parse_script("clip = video_in\nclip.set_output()\n", "NR_X.vpy"),
                   parse_script("clip = video_in\nclip.set_output()\n", "ETC_DEINT_X.vpy")]
        items, _warn = plan_fusion(scripts)
        self.assertEqual([x["label"] for x in items], ["反交错", "降噪", "超分", "补帧"])

    def test_generated_code_compiles(self):
        r = build_fused(self._scripts())
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["check"]["ok"], r["check"])
        self.assertIn("clip.set_output()", r["text"])
        self.assertIn("clip = video_in", r["text"])

    def test_options_kept_verbatim(self):
        r = build_fused(self._scripts())
        self.assertIn("H_Pre = 720", r["text"])
        self.assertIn("H_Pre = 1440", r["text"])      # 两个脚本的同名变量各自保留
        self.assertIn("k7f.MVT_LQ(clip", r["text"])
        self.assertIn("k7f.ARTCNN_NV(clip", r["text"])

    def test_same_stem_twice_gets_suffix(self):
        a = parse_script(SIMPLE, "SR_X.vpy")
        b = parse_script(SIMPLE, "SR_X.vpy")
        r = build_fused([a, b])
        self.assertIn("def _mb_SR_X(clip):", r["text"])
        self.assertIn("def _mb_SR_X_2(clip):", r["text"])

    def test_imports_deduped(self):
        r = build_fused(self._scripts())
        self.assertEqual(r["text"].count("import k7sfunc as k7f"), 1)
        self.assertEqual(r["text"].count("core.num_threads"), 1)

    def test_warns_on_double_memc(self):
        a = parse_script(MEMC, "MEMC_A.vpy")
        b = parse_script(MEMC, "MEMC_B.vpy")
        r = build_fused([a, b])
        self.assertTrue(any("补帧" in w for w in r["warnings"]))

    def test_unfusable_script_is_rejected(self):
        s = parse_script("clip = video_in\nclip.set_output()\n", "MIX_UVR_MAD.vpy")
        r = build_fused([s])
        self.assertFalse(r["ok"])
        self.assertTrue(any("不能融合" in w for w in r["warnings"]))

    def test_warns_when_output_missing(self):
        s = parse_script("clip = video_in\nclip = k7f.X(clip)\n", "SR_Y.vpy")
        r = build_fused([s])
        self.assertTrue(any("set_output" in w for w in r["warnings"]))

    def test_syntax_check_catches_broken_code(self):
        self.assertFalse(check_syntax("def f(:\n    pass\n")["ok"])


class WriteTest(unittest.TestCase):
    def test_write_and_refuse_foreign_file(self):
        with tempfile.TemporaryDirectory() as d:
            vs = Path(d)
            r = fuse_files([], name="x")
            self.assertFalse(r.get("ok"))
            # 正常写
            scripts = [parse_script(SIMPLE, "SR_TEST.vpy")]
            good = build_fused(scripts)
            good["filename"] = "_mb_fused.vpy"
            w = write_fused(vs, good)
            self.assertTrue(w["ok"], w)
            text = (vs / "_mb_fused.vpy").read_text(encoding="utf-8")
            self.assertIn(MARKER, text)
            # 覆盖自己生成的：允许，并留一份 .bak
            w2 = write_fused(vs, good)
            self.assertTrue(w2["ok"])
            self.assertTrue((vs / "_mb_fused.vpy.bak").is_file())
            # 别人的同名文件：拒绝
            other = parse_script(SIMPLE, "SR_TEST.vpy")
            bad = build_fused([other])
            bad["filename"] = "别人的脚本.vpy"
            (vs / "别人的脚本.vpy").write_text("# 我自己写的\n", encoding="utf-8")
            w3 = write_fused(vs, bad)
            self.assertFalse(w3["ok"])
            self.assertIn("拒绝覆盖", w3["detail"])

    def test_write_into_missing_dir(self):
        r = build_fused([parse_script(SIMPLE, "SR_TEST.vpy")])
        r["filename"] = "_mb_x.vpy"
        self.assertFalse(write_fused(Path("Z:/nope"), r)["ok"])


@unittest.skipUnless(VS_DIR.is_dir(), "本机没有 mpv-lazy 的 vs 目录")
class RealScriptsTest(unittest.TestCase):
    """拿真实脚本跑一遍：能解析、能融合、生成的东西语法正确。"""

    def test_parse_all_real_scripts(self):
        """把本机 vs 目录里的**源脚本**逐个解析一遍。

        ⚠ **必须跳过我们自己生成的融合产物**（`_mb_` 前缀）。
        融合输出的结构天然和源脚本不同 —— 它没有"用户选项"那一段，
        主体是一堆 `_mb_XXX()` 定义，所以拿源脚本的规矩去量它必然失败。
        这个坑真踩过：用户试过一次融合，`vs/` 里留下 `_mb_fused.vpy`，
        这个测试就开始红了，而**代码和生成物都是对的** —— 是测试扫错了对象。
        """
        srcs = [p for p in sorted(VS_DIR.glob("*.vpy"))
                if not p.name.startswith(PREFIX)]
        self.assertTrue(srcs, "vs 目录里一个源脚本都没有？")
        for p in srcs:
            s = parse_script(p.read_text(encoding="utf-8", errors="replace"), p)
            self.assertTrue(s["has_entry"], p.name)
            self.assertTrue(s["has_output"], p.name)
            self.assertTrue(s["options"], f"{p.name} 没解析出用户选项")
            self.assertEqual(s["unknown"], [], f"{p.name} 有没看懂的行")
            self.assertIn("import k7sfunc as k7f", s["imports"], p.name)

    def test_generated_fused_files_are_still_valid_scripts(self):
        """反过来钉住：我们自己生成的产物**本身仍是个完整能用的脚本**。

        和上面那条是一对：上面保证"扫描时跳过产物"，这条保证"产物没问题"
        —— 证明跳过是为了不误判，不是在掩盖生成物有毛病。
        """
        fused = [p for p in sorted(VS_DIR.glob("*.vpy"))
                 if p.name.startswith(PREFIX)]
        if not fused:
            self.skipTest("本机还没有融合产物")
        for p in fused:
            s = parse_script(p.read_text(encoding="utf-8", errors="replace"), p)
            self.assertTrue(s["has_entry"], p.name)
            self.assertTrue(s["has_output"], p.name)
            self.assertIn("import k7sfunc as k7f", s["imports"], p.name)

    def test_fuse_real_four_stage(self):
        want = ["ETC_DEINT_EX.vpy", "NR_CCD_STD.vpy", "SR_ARTCNN_NV.vpy", "MEMC_MVT_LQ.vpy"]
        paths = [VS_DIR / n for n in want]
        if not all(p.is_file() for p in paths):
            self.skipTest("本机缺脚本")
        r = fuse_files(paths, name="test_fused")
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["check"]["ok"], r["check"])
        self.assertEqual([x["label"] for x in r["stages"]],
                         ["反交错", "降噪", "超分", "补帧"])
        self.assertEqual(r["warnings"], [])

    def test_fuse_real_superres_plus_memc(self):
        paths = [VS_DIR / "SR_ARTCNN_NV.vpy", VS_DIR / "MEMC_RIFE_NV.vpy"]
        if not all(p.is_file() for p in paths):
            self.skipTest("本机缺脚本")
        r = fuse_files(paths, name="sr_memc")
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["check"]["ok"])
        self.assertLess(r["text"].index("ARTCNN_NV"), r["text"].index("RIFE_NV"))


if __name__ == "__main__":
    unittest.main()

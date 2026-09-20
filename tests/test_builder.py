# -*- coding: utf-8 -*-
"""core.builder / core.loader 的往返测试：状态 → 文本 → 状态。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.builder import build_config_text, describe_state, validate_state  # noqa: E402
from core.loader import parse_config_text                                   # noqa: E402


class BuilderTest(unittest.TestCase):
    def test_empty_state_still_has_header(self):
        text = build_config_text({})
        self.assertIn("MPV Config Builder", text)
        # 空状态只有注释头，没有任何 key = value
        self.assertFalse([ln for ln in text.splitlines()
                          if ln.strip() and not ln.lstrip().startswith("#")])

    def test_sections_and_order(self):
        text = build_config_text({
            "values": {"scale": "ewa_lanczossharp", "vo": "gpu-next",
                       "deband-iterations": "2", "sub-font": "sans-serif"},
            "shaders": ["~~/shaders/a.glsl", "~~/shaders/b.glsl"],
            "memc": "~~/vs/x.vpy",
        })
        # 分组顺序 = PARAMS（核心层）在前、NATIVE_OPTIONS（原生层）在后，
        # 两个字典内部按各自的声明顺序。
        self.assertLess(text.index("# 视频输出"), text.index("# 缩放"))
        # sub-font 属于核心层的「字幕样式」组（为字幕预览提上来的），
        # 所以它排在核心层里；deband-iterations 在原生层，排在核心层之后。
        self.assertLess(text.index("# 字幕样式"), text.index("# 画质细节"))
        self.assertIn("sub-font = sans-serif", text)
        self.assertIn("glsl-shaders = \"~~/shaders/a.glsl;~~/shaders/b.glsl\"", text)
        self.assertIn('vf = vapoursynth="~~/vs/x.vpy"', text)

    def test_core_groups_come_before_native_groups(self):
        """核心层的组必须全部排在原生层的组之前（PARAMS 先输出）。"""
        text = build_config_text({
            "values": {"vo": "gpu-next", "sub-font": "sans-serif",   # 核心层
                       "deband-iterations": "2", "sub-margin-x": "35"},  # 原生层
        })
        self.assertLess(text.index("# 字幕样式"), text.index("# 画质细节"))
        self.assertLess(text.index("# 字幕样式"), text.index("# 字幕明细"))

    def test_vf_path_with_spaces_is_quoted(self):
        """路径里有空格必须整体加引号：真实 mpv 遇到没引号的会直接
        'Error parsing option vf (option parameter could not be parsed)'。"""
        p = r"C:\Program Files\mpv-lazy\portable_config\vs\_mb_fused.vpy"
        out = build_config_text({"memc": p})
        self.assertIn(f'vf = vapoursynth="{p}"', out)
        line = [x for x in out.splitlines() if x.startswith("vf =")][0]
        self.assertEqual(line.count('"'), 2, line)
        self.assertTrue(line.endswith('"'), line)

    def test_custom_layer_is_appended_raw(self):
        text = build_config_text({"custom": "profile-cond=not playlist\n[my]\nscale=spline36"})
        self.assertIn("profile-cond=not playlist", text)
        self.assertIn("[my]", text)

    def test_lists_get_quoted_once(self):
        text = build_config_text({"values": {"sub-file-paths": "sub;subs"}})
        self.assertIn('sub-file-paths = "sub;subs"', text)
        text2 = build_config_text({"values": {"sub-file-paths": '"sub;subs"'}})
        self.assertIn('sub-file-paths = "sub;subs"', text2)
        self.assertNotIn('""sub', text2)

    def test_empty_values_are_skipped(self):
        text = build_config_text({"values": {"vo": "gpu-next", "scale": "   "}})
        self.assertIn("vo = gpu-next", text)
        self.assertNotIn("scale =", text)

    def test_describe_and_validate(self):
        st = {"values": {"vo": "gpu-next"}, "shaders": ["a.glsl"], "memc": "x.vpy"}
        self.assertIn("1 个参数", describe_state(st))
        bad = validate_state({"values": {"dither": "nope"}})
        self.assertEqual(bad[0][0], "error")
        many = validate_state({"shaders": ["a", "b", "c", "d", "e", "f", "g"]})
        self.assertTrue(any(lv == "warn" for lv, _ in many))

    def test_round_trip(self):
        """状态 → 文本 → 解析回来，键值、shader 链、vpy 都不该变。"""
        state = {
            "values": {"vo": "gpu-next", "gpu-api": "vulkan", "scale": "ewa_lanczossharp",
                       "deband-iterations": "2", "sub-font": "LXGW WenKai Mono Lite"},
            "shaders": ["~~/shaders/Anime4K/Anime4K_Restore_CNN_L.glsl",
                        "~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"],
            "memc": "~~/vs/MEMC_MVT_LQ.vpy",
        }
        text = build_config_text(state)
        back = parse_config_text(text)
        for k, v in state["values"].items():
            self.assertEqual(back["values"].get(k), v, k)
        self.assertEqual(back["shaders"], state["shaders"])
        self.assertEqual(back["memc"], state["memc"])

    def test_parse_ignores_comments_and_unknown(self):
        data = parse_config_text(
            "# 注释\n"
            "vo = gpu-next   # 行尾注释\n"
            "\n"
            "scale=spline36\n"
            "watch-later-options=start,vid\n"
            "#glsl-shaders=\"a.glsl\"\n"
            "vf=vapoursynth=\"~~/vs/x.vpy\"\n"
        )
        self.assertEqual(data["values"]["vo"], "gpu-next")     # 行尾注释被剥掉
        self.assertEqual(data["values"]["watch-later-options"], "start,vid")
        self.assertEqual(data["values"]["scale"], "spline36")
        self.assertNotIn("a.glsl", data["shaders"])            # 注释行不算
        self.assertEqual(data["memc"], "~~/vs/x.vpy")

    def test_parse_accepts_both_list_separators(self):
        self.assertEqual(parse_config_text('glsl-shaders="a.glsl;b.glsl"\n')["shaders"],
                         ["a.glsl", "b.glsl"])
        self.assertEqual(parse_config_text('glsl-shaders="C:/x/a.glsl"\n')["shaders"],
                         ["C:/x/a.glsl"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""外部审查发现的 4 个配置损坏缺陷的回归测试（X-1-1 ~ X-1-4）。

这四条都是「读取现有配置 → 写回」路径上的静默损坏，之前的 199 项测试
一条都没覆盖到 —— 因为往返测试用的是**已经归一化的 state**，
恰好绕过了加载器对 vf / glsl-shader / [profile] 的处理。

对应修复：
    X-1-1  vf 与 vf-append 互相覆盖 → 补帧脚本消失
    X-1-2  glsl-shader / glsl-shaders-append 被并进 glsl-shaders
    X-1-3  merge 写入不认 [profile] 小节边界
    X-1-4  merge 路径绕过引号判断 → 带 # 的颜色值被截成空串
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.builder import build_config_text, full_check, blank_keys            # noqa: E402
from core.loader import parse_config_text                                    # noqa: E402
from core.report import build_report                                         # noqa: E402
from core.writer import apply_params_to_lines, apply_state_to_lines          # noqa: E402


def state_from(text):
    """把配置文本走一遍「加载器 → 状态」，模拟界面读取现有配置。"""
    d = parse_config_text(text)
    return {
        "values": d["values"],
        "shaders": d["shaders"],
        "shader_appends": d["shader_appends"],
        "shader_append_key": d["shader_append_key"],
        "memc": d["memc"],
        "memc_label": d["memc_label"],
        "memc_kind": d["memc_kind"],
        "vf_filters": d["vf_filters"],
        "vf_append_filters": d["vf_append_filters"],
        "af_filters": d["af_filters"],
    }


def active_lines(text):
    """只看生效行（非注释、非空）。"""
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


class VfAppendTest(unittest.TestCase):
    """X-1-1：vf 与 vf-append 不能互相覆盖。"""

    def test_vpy_script_and_filter_append_both_survive(self):
        state = state_from(
            'vo=gpu-next\n'
            'vf=vapoursynth="~~/vs/MEMC_RIFE_NV.vpy"\n'
            'vf-append=format=yuv420p10\n'
        )
        out = active_lines(build_config_text(state))
        self.assertIn('vf = vapoursynth="~~/vs/MEMC_RIFE_NV.vpy"', out,
                      "补帧脚本不能丢")
        self.assertIn("vf-append = format=yuv420p10", out,
                      "vf-append 的内容必须留在 vf-append 上")

    def test_plain_vf_filter_is_not_turned_into_script(self):
        """`vf-append=format=yuv420p10` 不是 VapourSynth 脚本，绝不能被包成 vapoursynth=。"""
        state = state_from('vo=gpu\nvf-append=format=yuv420p10\n')
        joined = "\n".join(active_lines(build_config_text(state)))
        self.assertNotIn("vapoursynth=", joined,
                         "普通滤镜链被误当成脚本路径了")
        self.assertIn("vf-append = format=yuv420p10", joined)

    def test_plain_vf_chain_preserved(self):
        state = state_from("vo=gpu\nvf=lavfi=[crop=1920:1080:0:0]\n")
        joined = "\n".join(active_lines(build_config_text(state)))
        self.assertIn("lavfi=[crop=1920:1080:0:0]", joined)
        self.assertNotIn("vapoursynth=", joined)

    def test_vf_label_survives(self):
        state = state_from('vo=gpu-next\nvf=@vs:vapoursynth="~~/vs/x.vpy"\n')
        self.assertEqual(state["memc_kind"], "vf")
        self.assertEqual(state["memc_label"], "@vs:")
        out = active_lines(build_config_text(state))
        self.assertIn('vf = @vs:vapoursynth="~~/vs/x.vpy"', out)

    def test_vf_append_kind_remembered(self):
        state = state_from('vo=gpu-next\nvf-append=vapoursynth="~~/vs/x.vpy"\n')
        self.assertEqual(state["memc_kind"], "vf-append")
        out = active_lines(build_config_text(state))
        self.assertIn('vf-append = vapoursynth="~~/vs/x.vpy"', out)

    def test_af_chain_preserved(self):
        state = state_from("vo=gpu\naf=lavfi=[dynaudnorm]\n")
        out = active_lines(build_config_text(state))
        self.assertIn("af = lavfi=[dynaudnorm]", out)


class GlslAppendTest(unittest.TestCase):
    """X-1-2：glsl-shader / glsl-shaders-append 与 glsl-shaders 语义不同。"""

    SRC = (
        "vo=gpu-next\n"
        'glsl-shaders="~~/shaders/base.glsl"\n'
        'glsl-shader="~~/shaders/add1.glsl"\n'
        'glsl-shaders-append="~~/shaders/add2.glsl"\n'
    )

    def test_replace_and_append_kept_separate(self):
        state = state_from(self.SRC)
        self.assertEqual(state["shaders"], ["~~/shaders/base.glsl"])
        self.assertEqual(state["shader_appends"],
                         ["~~/shaders/add1.glsl", "~~/shaders/add2.glsl"])

    def test_append_paths_survive_writeback(self):
        out = "\n".join(active_lines(build_config_text(state_from(self.SRC))))
        self.assertIn('glsl-shaders = "~~/shaders/base.glsl"', out)
        for p in ("add1.glsl", "add2.glsl"):
            self.assertIn(p, out, f"{p} 在写回时丢了")

    def test_append_does_not_merge_into_one_line(self):
        """合并成一行会把「先替换再追加」变成一次整表替换。"""
        out = active_lines(build_config_text(state_from(self.SRC)))
        shader_lines = [ln for ln in out if "glsl-shader" in ln]
        self.assertEqual(len(shader_lines), 3, f"应当是 3 行，实际 {shader_lines}")

    def test_append_only(self):
        out = "\n".join(active_lines(
            build_config_text(state_from('glsl-shader="a.glsl"\n'))))
        self.assertIn("a.glsl", out)
        self.assertNotIn("glsl-shaders =", out.replace("glsl-shader =", ""))


class ProfileBoundaryTest(unittest.TestCase):
    """X-1-3：merge 写入只动全局区，不碰 [profile] 小节。"""

    LINES = ["[profile-a]", "scale=bilinear", "", "[profile-b]",
             "scale=catmull_rom", "", "# 全局区", "volume=100"]

    def test_profile_lines_untouched(self):
        new, _ch = apply_params_to_lines(self.LINES, {"scale": "ewa_lanczossharp"})
        self.assertEqual(new[1], "scale=bilinear", "profile-a 里的 scale 被改了")
        self.assertEqual(new[4], "scale=catmull_rom", "profile-b 里的 scale 被改了")

    def test_global_key_appended_when_only_profiles_have_it(self):
        new, ch = apply_params_to_lines(self.LINES, {"scale": "ewa_lanczossharp"})
        self.assertIn("scale = ewa_lanczossharp", "\n".join(new),
                      "全局区没有这个键时应当追加一行")
        self.assertTrue(any("新增" in c for c in ch), ch)

    def test_global_line_still_replaced(self):
        lines = ["scale=bilinear", "[p]", "scale=catmull_rom"]
        new, _ = apply_params_to_lines(lines, {"scale": "spline36"})
        self.assertEqual(new[0], "scale = spline36")
        self.assertEqual(new[2], "scale=catmull_rom")

    def test_comment_keys_skips_profiles(self):
        lines = ["[p]", "scale=bilinear"]
        new, ch = apply_state_to_lines(lines, {}, ["scale"])
        self.assertEqual(new[1], "scale=bilinear", "profile 里的行不该被注释")
        self.assertEqual(ch, [])

    def test_disable_still_comments_global(self):
        """全局区的行照旧能被注释掉（真在 [profile] 里的不行 —— 见上一个用例）。"""
        lines = ["volume=100", "[p]", "scale=x"]
        new, ch = apply_state_to_lines(lines, {}, ["volume"])
        self.assertTrue(new[0].lstrip().startswith("#volume"),
                        f"全局区的行应该被注释掉，实际 {new[0]!r}")
        self.assertIn("volume: 已注释", ch)

    def test_lines_after_section_header_belong_to_it(self):
        """`[p]` 之后、下一个 `[x]` 之前的所有行都属于 p —— 注释分隔行不会结束小节。"""
        lines = ["[p]", "volume=100", "# 只是条注释", "deband=yes"]
        new, ch = apply_state_to_lines(lines, {}, ["volume", "deband"])
        self.assertEqual(new[1], "volume=100")
        self.assertEqual(new[3], "deband=yes")
        self.assertEqual(ch, [])


class MergeQuotingTest(unittest.TestCase):
    """X-1-4：merge 路径必须和 include 路径用同一套引号规则。"""

    def test_hash_value_quoted_on_merge_path(self):
        new, _ = apply_params_to_lines(["vo=gpu"], {"sub-color": "#FFD766"})
        joined = "\n".join(new)
        self.assertIn('sub-color = "#FFD766"', joined,
                      "带 # 的值没加引号会被 mpv 当注释截掉")

    def test_merge_and_include_agree(self):
        """同一条参数，两条写盘路径产出的行必须一致。"""
        key, value = "sub-color", "#FFD766"
        merged, _ = apply_params_to_lines(["vo=gpu"], {key: value})
        merge_line = [ln.strip() for ln in merged if key in ln][0]
        include_line = [ln.strip() for ln in
                        build_config_text({"values": {key: value}}).splitlines()
                        if ln.startswith(key)][0]
        self.assertEqual(merge_line, include_line,
                         "merge 与 include 两条路径的格式化结果不一致")

    def test_roundtrip_keeps_hash_value(self):
        """写回去再读回来，值不能被吃成空串。"""
        new, _ = apply_params_to_lines(["vo=gpu"], {"sub-color": "#FFD766"})
        back = parse_config_text("\n".join(new) + "\n")
        self.assertEqual(back["hash_keys"], [],
                         "工具自己写出了「没加引号的 #」")
        self.assertTrue(back["values"]["sub-color"].strip("#\"") == "FFD766",
                        back["values"]["sub-color"])

    def test_already_quoted_not_double_quoted(self):
        new, _ = apply_params_to_lines(["vo=gpu"], {"sub-color": '"#FFD766"'})
        line = [ln.strip() for ln in new if "sub-color" in ln][0]
        self.assertEqual(line.count('"'), 2, line)

    def test_list_option_quoted(self):
        new, _ = apply_params_to_lines(["vo=gpu"], {"sub-file-paths": "sub;subs"})
        self.assertIn('sub-file-paths = "sub;subs"', "\n".join(new))


class BlankPlaceholderTest(unittest.TestCase):
    """空值占位行（`vo=` 这种）不该被当成错误、也不该参与评分。

    典型来源：教学模板 / 自己搭的骨架配置，把选项名和等号留着让用户填。
    修之前一份 29 行的模板会报 29 条「值为空」错误，还会因为
    「所有高档选项都算开着」而报「GPU 负载等级较高」。
    """

    TEMPLATE = (
        "vo=\nscale=\ncscale=\ndscale=\n"
        "deband=\ndeband-iterations=\ndither=\ndither-depth=\n"
        "interpolation=\ntscale=\ncorrect-downscaling=\n"
    )

    def test_blank_not_an_error(self):
        issues, _ = full_check({"values": parse_config_text(self.TEMPLATE)["values"]})
        errors = [m for lv, m in issues if lv == "error"]
        self.assertEqual(errors, [], f"空值不该报 error：{errors}")

    def test_blank_reported_once_as_info(self):
        issues, _ = full_check({"values": parse_config_text(self.TEMPLATE)["values"]})
        infos = [m for lv, m in issues if lv == "info" and "值是空的" in m]
        self.assertEqual(len(infos), 1, "空值应当合并成一条提示，不是每条一行")

    def test_blank_keys_helper(self):
        st = {"values": parse_config_text(self.TEMPLATE)["values"]}
        self.assertEqual(len(blank_keys(st)), 11)

    def test_blank_does_not_inflate_gpu_load(self):
        """空壳配置不该被算成"所有高档选项都开着"。"""
        r = build_report(text=self.TEMPLATE, name="空壳")
        self.assertTrue(r["ok"])
        self.assertLess(r["scores"]["load"], 40,
                        f"load={r['scores']['load']}，空值在参与评分")
        joined = " ".join(m for _lv, m in r["issues"])
        self.assertNotIn("GPU 负载等级较高", joined)

    def test_blank_counted_in_report(self):
        r = build_report(text=self.TEMPLATE, name="空壳")
        self.assertEqual(r["counts"]["blanks"], 11)
        self.assertEqual(r["counts"]["known"], 0, "空值不该算成「已识别的选项」")

    def test_real_value_still_validated(self):
        """有值的照旧校验 —— 别把空值豁免做成"什么都不查了"。"""
        issues, _ = full_check({"values": {"dither": "nope"}})
        self.assertTrue(any(lv == "error" for lv, _ in issues), issues)
        issues2, _ = full_check({"values": {"scale": "bilinear"}})
        self.assertEqual([lv for lv, _ in issues2 if lv == "error"], [])


if __name__ == "__main__":
    unittest.main()

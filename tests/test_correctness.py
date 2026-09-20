# -*- coding: utf-8 -*-
"""A 类正确性坑的回归测试：编码 / profile 小节 / include 链 / vf 标签。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import textio                       # noqa: E402
from core.builder import build_config_text    # noqa: E402
from core.loader import (                     # noqa: E402
    effective_config, load_config_file, parse_config_text, split_vf_label,
)
from core.writer import (                     # noqa: E402
    apply_params_to_lines, ensure_include_line, merge_into_file, write_lines,
)

GBK_CONF = """\
# 中文注释：这条注释在 GBK 配置里
vo=gpu-next
scale=ewa_lanczossharp
"""

PROFILES = """\
# profile 集合
[speed_limit]
 profile-desc = 限速
 speed = 0.5

[ontop_playback]
 profile-desc = 播放时置顶
 ontop = yes
"""

MAIN_WITH_INCLUDE = """\
vo=gpu-next
include = "~~/profiles_tail.conf"
hwdec=auto-safe
"""

TAIL = """\
hwdec=no
scale=spline36
"""


class TextioTest(unittest.TestCase):
    def test_detect_utf8(self):
        tf = textio.decode("# 注释\nvo=gpu-next\n".encode("utf-8"))
        self.assertEqual(tf.encoding, "utf-8")
        self.assertFalse(tf.lossy)

    def test_detect_utf8_bom(self):
        tf = textio.decode("\ufeffvo=gpu-next\n".encode("utf-8"))
        self.assertTrue(tf.bom)
        self.assertNotIn("\ufeff", tf.text)

    def test_detect_gbk(self):
        tf = textio.decode(GBK_CONF.encode("gb18030"))
        self.assertEqual(tf.encoding, "gb18030")
        self.assertIn("中文注释", tf.text)
        self.assertFalse(tf.lossy)

    def test_roundtrip_keeps_encoding_and_newline(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "mpv.conf"
            p.write_bytes(GBK_CONF.replace("\n", "\r\n").encode("gb18030"))
            tf = textio.read(p)
            self.assertEqual(tf.encoding, "gb18030")
            self.assertEqual(tf.newline, "\r\n")
            textio.write(p, tf.text + "deband=yes\n", tf.encoding, tf.bom, tf.newline)
            raw = p.read_bytes()
            self.assertIn("中文注释：这条注释在 GBK 配置里".encode("gb18030"), raw)
            self.assertEqual(textio.sniff(raw)[0], "gb18030")
            self.assertIn(b"deband=yes", raw)

    def test_lossy_flag_on_broken_bytes(self):
        tf = textio.decode(b"vo=gpu-next\n\xff\xfe\x00bad\n")
        self.assertTrue(tf.lossy or tf.encoding in ("utf-16-le", "utf-16-be"))

    def test_heavy_corruption_is_flagged(self):
        tf = textio.decode(b"\x81\x40\xff\x00\x01\x02\x03\x04")
        self.assertTrue(tf.lossy)


class ProfileTest(unittest.TestCase):
    def test_profile_sections_not_treated_as_global(self):
        data = parse_config_text(PROFILES)
        self.assertEqual(data["values"], {})              # 全局区是空的
        self.assertTrue(data["is_profile_file"])
        names = [p["name"] for p in data["profiles"]]
        self.assertEqual(names, ["speed_limit", "ontop_playback"])
        self.assertEqual(data["profiles"][1]["values"]["ontop"], "yes")
        self.assertEqual(data["profiles"][1]["desc"], "播放时置顶")

    def test_profile_meta_lines_not_leaked(self):
        data = parse_config_text(PROFILES)
        all_keys = {k for p in data["profiles"] for k in p["keys"]}
        self.assertNotIn("profile-desc", all_keys)
        self.assertNotIn("profile-cond", all_keys)

    def test_mixed_file_keeps_global_part(self):
        text = "vo=gpu-next\n[my_profile]\nscale=spline36\n"
        data = parse_config_text(text)
        self.assertEqual(data["values"], {"vo": "gpu-next"})
        self.assertFalse(data["is_profile_file"])
        self.assertEqual(data["profiles"][0]["values"], {"scale": "spline36"})

    def test_load_config_file_warns_for_profile_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "profiles.conf"
            p.write_text(PROFILES, encoding="utf-8")
            data = load_config_file(p)
            self.assertTrue(data["is_profile_file"])
            self.assertTrue(any("profile" in w for w in data["warnings"]))


class IncludeChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "mpv.conf").write_text(MAIN_WITH_INCLUDE, encoding="utf-8")
        (self.dir / "profiles_tail.conf").write_text(TAIL, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_tilde_path_resolves_against_main_dir(self):
        chain = effective_config(self.dir / "mpv.conf")
        names = [f["name"] for f in chain["files"]]
        self.assertEqual(names, ["mpv.conf", "profiles_tail.conf"])

    def test_later_file_wins(self):
        chain = effective_config(self.dir / "mpv.conf")
        self.assertEqual(chain["values"]["hwdec"], "no")       # tail 覆盖了 auto-safe
        self.assertEqual(chain["values"]["scale"], "spline36")
        self.assertEqual(chain["sources"]["hwdec"], "profiles_tail.conf")
        self.assertEqual(chain["sources"]["vo"], "mpv.conf")

    def test_missing_include_is_reported_not_crashed(self):
        (self.dir / "mpv.conf").write_text('include = "~~/nope.conf"\nvo=gpu\n', encoding="utf-8")
        chain = effective_config(self.dir / "mpv.conf")
        self.assertEqual(chain["files"][0]["missing"][0]["target"], "~~/nope.conf")
        self.assertEqual(chain["values"]["vo"], "gpu")

    def test_include_loop_is_bounded(self):
        (self.dir / "a.conf").write_text('include = "~~/b.conf"\nvo=gpu\n', encoding="utf-8")
        (self.dir / "b.conf").write_text('include = "~~/a.conf"\nscale=spline36\n', encoding="utf-8")
        chain = effective_config(self.dir / "a.conf")
        self.assertLessEqual(len(chain["files"]), 24)
        self.assertIn("scale", chain["values"])

    def test_desktop_include_is_skipped(self):
        (self.dir / "mpv.conf").write_text('include = "~~desktop/x.conf"\nvo=gpu\n', encoding="utf-8")
        chain = effective_config(self.dir / "mpv.conf")
        self.assertFalse(chain["files"][0]["missing"])
        self.assertEqual(len(chain["files"]), 1)


class VfLabelTest(unittest.TestCase):
    def test_split_label(self):
        self.assertEqual(split_vf_label('@vs:vapoursynth="~~/vs/x.vpy"'), ("@vs:", "~~/vs/x.vpy"))
        self.assertEqual(split_vf_label('vapoursynth="~~/vs/x.vpy"'), ("", "~~/vs/x.vpy"))
        self.assertEqual(split_vf_label('~~/vs/x.vpy'), ("", "~~/vs/x.vpy"))

    def test_label_survives_roundtrip(self):
        text = 'vo=gpu-next\nvf=@vs:vapoursynth="~~/vs/MEMC_MVT_LQ.vpy"\n'
        data = parse_config_text(text)
        self.assertEqual(data["memc"], "~~/vs/MEMC_MVT_LQ.vpy")
        self.assertEqual(data["memc_label"], "@vs:")
        out = build_config_text({"values": data["values"], "shaders": [],
                                 "memc": data["memc"], "memc_label": data["memc_label"]})
        self.assertIn('vf = @vs:vapoursynth="~~/vs/MEMC_MVT_LQ.vpy"', out)

    def test_no_label_stays_clean(self):
        out = build_config_text({"memc": "~~/vs/x.vpy"})
        self.assertIn('vf = vapoursynth="~~/vs/x.vpy"', out)


class ConfigSyntaxTest(unittest.TestCase):
    """mpv 手册的两条语法规则：`#` 之后全是注释；光杆选项等于 yes。"""

    def test_hash_starts_comment_even_without_space(self):
        from core.schema import strip_inline_comment, needs_quotes
        self.assertEqual(strip_inline_comment("vo=gpu-next  # 说明"), "vo=gpu-next")
        # 手册：没加引号的 # 一律当注释 —— 颜色值必须加引号
        self.assertEqual(strip_inline_comment("sub-color=#FFD766"), "sub-color=")
        self.assertEqual(strip_inline_comment('sub-color="#FFD766"'), 'sub-color="#FFD766"')
        self.assertTrue(needs_quotes("#FFD766"))
        self.assertFalse(needs_quotes('"#FFD766"'))

    def test_color_values_are_written_quoted(self):
        out = build_config_text({"values": {"sub-color": "#FFD766"}})
        self.assertIn('sub-color = "#FFD766"', out)

    def test_unquoted_hash_is_reported(self):
        data = parse_config_text("sub-color=#FFD766\nvo=gpu-next\n")
        self.assertEqual(data["hash_keys"], ["sub-color"])
        self.assertEqual(data["values"]["sub-color"], "")

    def test_properly_quoted_hash_is_kept(self):
        data = parse_config_text('sub-color="#FFD766"\n')
        self.assertEqual(data["hash_keys"], [])
        self.assertEqual(data["values"]["sub-color"], '"#FFD766"')

    def test_bare_option_means_yes(self):
        data = parse_config_text("hwdec\nvo=gpu-next\n")
        self.assertEqual(data["values"]["hwdec"], "yes")


class WriterEncodingTest(unittest.TestCase):
    def test_merge_keeps_gbk(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "mpv.conf"
            p.write_bytes(GBK_CONF.encode("gb18030"))
            changes, backup = merge_into_file(p, {"scale": "spline36"})
            self.assertTrue(changes)
            raw = p.read_bytes()
            self.assertEqual(textio.sniff(raw)[0], "gb18030")
            self.assertIn("scale = spline36", raw.decode("gb18030"))
            self.assertIn("中文注释", raw.decode("gb18030"))
            self.assertTrue(backup and backup.is_file())

    def test_apply_merge_keeps_gbk(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "mpv.conf"
            p.write_bytes(GBK_CONF.encode("gb18030"))
            tf = textio.read(p)
            lines, _ = apply_params_to_lines(tf.text.splitlines(), {"deband": "yes"})
            write_lines(p, lines, tf.newline, template=tf)
            self.assertEqual(textio.sniff(p.read_bytes())[0], "gb18030")
            p.read_bytes().decode("gb18030")           # 能解回来，说明没写坏

    def test_include_line_written_in_original_encoding(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "mpv.conf"
            p.write_bytes(GBK_CONF.encode("gb18030"))
            changed, _backup, _msg = ensure_include_line(p)
            self.assertTrue(changed)
            raw = p.read_bytes()
            self.assertEqual(textio.sniff(raw)[0], "gb18030")
            self.assertIn("mpv-builder.conf", raw.decode("gb18030"))


if __name__ == "__main__":
    unittest.main()

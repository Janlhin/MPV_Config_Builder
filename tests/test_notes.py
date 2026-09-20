# -*- coding: utf-8 -*-
"""R-25（生成时附注释）与 R-28（给已有配置补注释）的测试。

两条都依赖同一个 `core/notes.py` —— 这里也顺带守住"查不到就不编造"这条原则。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import notes                                                        # noqa: E402
from core.annotate import annotate_text, out_name_for, _has_inline_comment    # noqa: E402
from core.builder import build_config_text                                    # noqa: E402
from core.loader import parse_config_text                                     # noqa: E402


class NoteSourceTest(unittest.TestCase):
    def test_known_key_has_note(self):
        self.assertTrue(notes.option_note("vo"))
        self.assertTrue(notes.option_note("scale"))
        self.assertTrue(notes.option_note("deband-iterations"))

    def test_unknown_key_has_no_note(self):
        """不认识就返回空 —— 绝不编造。"""
        for key in ("this-is-not-a-real-option", "cas", "definitely_fake"):
            self.assertEqual(notes.option_note(key), "", key)

    def test_default_suffix_is_stripped(self):
        raw = "每个采样要执行去色带步骤的数量。（默认： 1）。"
        self.assertNotIn("默认", notes.strip_default_suffix(raw))

    def test_inline_shorter_than_above(self):
        note_inline = notes.option_note("watch-later-options", style="inline")
        self.assertLessEqual(len(note_inline), notes.INLINE_LIMIT + 1, note_inline)

    def test_note_is_one_sentence(self):
        n = notes.option_note("window-scale", style="above")
        self.assertLessEqual(len(n), notes.ABOVE_LIMIT + 1)
        self.assertNotIn("\n", n)

    def test_hints_are_real(self):
        """格式提示必须来自库里真实存在的信息。"""
        self.assertIn("~", notes.option_hint("deband-iterations"))       # range 0 to 16
        self.assertIn("#RRGGBB", notes.option_hint("sub-color"))          # 手工补的
        self.assertIn("WxH", notes.option_hint("geometry"))
        self.assertTrue(notes.option_hint("interpolation"))               # 枚举值

    def test_hint_none_when_nothing_known(self):
        self.assertEqual(notes.option_hint("this-is-not-a-real-option"), "")

    def test_coverage_matches_db_meta(self):
        """覆盖率要和库里 meta 对得上（防止我随口写个数字）。"""
        c = notes.coverage()
        from core.options_db import load_db
        db = load_db()
        meta = db.get("meta") or {}
        self.assertEqual(c["total"], meta.get("count"))
        # 我们用的是精选说明 + zh_desc + 手工补充，所以至少不低于"库里现存的有中文条数"
        with_zh_now = sum(1 for v in (db.get("options") or {}).values()
                          if (v.get("zh_desc") or "").strip())
        self.assertGreaterEqual(c["with_note"], with_zh_now)

    def test_special_lines_have_notes(self):
        for key in ("include", "profile-desc", "profile-cond"):
            self.assertTrue(notes.special_note(key), key)


class BuildWithNotesTest(unittest.TestCase):
    STATE = {"values": {"vo": "gpu-next", "scale": "ewa_lanczossharp",
                        "sub-color": '"#FFD766"'}}

    def test_default_is_off(self):
        """不传 annotate 时行为必须与以前完全一样。"""
        text = build_config_text(self.STATE)
        active = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
        self.assertEqual(active, ['vo = gpu-next', 'scale = ewa_lanczossharp',
                                  'sub-color = "#FFD766"'])

    def test_above_style(self):
        text = build_config_text(self.STATE, annotate=True, annotate_style="above")
        lines = text.splitlines()
        i = lines.index("vo = gpu-next")
        self.assertTrue(lines[i - 1].startswith("# "), lines[i - 1])
        self.assertIn("视频输出", lines[i - 1])

    def test_inline_style(self):
        text = build_config_text(self.STATE, annotate=True, annotate_style="inline")
        line = [l for l in text.splitlines() if l.startswith("vo =")][0]
        self.assertIn("    # ", line)
        self.assertTrue(line.startswith("vo = gpu-next"))

    def test_annotated_output_still_parses_to_same_values(self):
        """加了注释之后，解析回来的值不能变 —— 否则注释把配置弄坏了。"""
        for style in ("above", "inline"):
            text = build_config_text(self.STATE, annotate=True, annotate_style=style)
            back = parse_config_text(text)
            self.assertEqual(back["values"]["vo"], "gpu-next", style)
            self.assertEqual(back["values"]["scale"], "ewa_lanczossharp", style)

    def test_quoted_hash_value_survives_annotation(self):
        """带 # 的值加了行尾注释也不能被截断（注释在引号外）。"""
        text = build_config_text({"values": {"sub-color": "#FFD766"}},
                                 annotate=True, annotate_style="inline")
        line = [l for l in text.splitlines() if l.startswith("sub-color")][0]
        self.assertIn('"#FFD766"', line)
        back = parse_config_text(text + "\n")
        self.assertEqual(back["hash_keys"], [])

    def test_unknown_keys_get_no_fake_note(self):
        text = build_config_text({"values": {"totally-fake-key": "1"}},
                                 annotate=True, annotate_style="inline")
        line = [l for l in text.splitlines() if l.startswith("totally-fake-key")][0]
        self.assertNotIn("#", line, "不认识的键不该被编出一条说明")

    def test_own_hint_text_does_not_trigger_hash_warning(self):
        """工具自己生成的提示里含 `#`（如 #RRGGBB），不能被自己的体检误报。

        以前 `parse_config_text` 拿整段（含行尾注释）查"没加引号的 #"，
        于是加了注释之后，一行本来正确的 `sub-color = "#FFD766"` 反而被报成
        「值里有没加引号的 #」。这个 bug 就是被 R-25 的注释引出来的。
        """
        text = build_config_text({"values": {"sub-color": '"#FFD766"'}},
                                 annotate=True, annotate_style="inline")
        self.assertIn("#RRGGBB", text, "提示里确实含 # —— 这才让这个测试有意义")
        back = parse_config_text(text)
        self.assertEqual(back["hash_keys"], [],
                         f"被自己的提示误报了：{back['hash_keys']}")
        self.assertEqual(back["values"]["sub-color"], '"#FFD766"')


class AnnotateTextTest(unittest.TestCase):
    SRC = (
        "# 我的配置\n"
        "vo=gpu-next\n"
        "scale=ewa_lanczossharp   # 我自己写的，别动\n"
        "sub-color=\"#FFD766\"\n"
        "\n"
        "#### 分节线 ####\n"
        "[anime]\n"
        "deband=yes\n"
        "include = \"~~/profiles.conf\"\n"
        "glsl-shaders=\"a.glsl;b.glsl\"\n"
        "vf=vapoursynth=\"~~/vs/x.vpy\"\n"
        "not-a-real-key=1\n"
    )

    def test_only_missing_preserves_existing_comments(self):
        r = annotate_text(self.SRC)
        out = r["text"]
        self.assertIn("# 我自己写的，别动", out)
        # 那一行除了原有注释，不该被追加第二条
        line = [l for l in out.splitlines() if l.startswith("scale=")][0]
        self.assertEqual(line.count("#"), 1, line)

    def test_blank_and_rule_lines_untouched(self):
        r = annotate_text(self.SRC)
        self.assertIn("#### 分节线 ####", r["text"])

    def test_line_count_doubles_only_in_above_mode(self):
        inline = annotate_text(self.SRC, style="inline")["text"].splitlines()
        above = annotate_text(self.SRC, style="above")["text"].splitlines()
        self.assertEqual(len(inline), len(self.SRC.splitlines()),
                         "行尾注释不该改变行号")
        self.assertGreater(len(above), len(inline), "上方注释应当多出若干行")

    def test_special_lines_get_special_wording(self):
        out = annotate_text(self.SRC)["text"]
        self.assertIn("着色器链", out)
        self.assertIn("vapoursynth", out.lower())

    def test_missing_keys_are_reported_not_invented(self):
        r = annotate_text(self.SRC)
        self.assertIn("not-a-real-key", r["stats"]["missing_keys"])
        line = [l for l in r["text"].splitlines() if l.startswith("not-a-real-key")][0]
        self.assertNotIn("#", line, "查不到说明就该留白")

    def test_stats_shape(self):
        s = annotate_text(self.SRC)["stats"]
        for field in ("lines", "added", "skipped", "missing",
                      "profile_lines", "include_lines", "section_lines"):
            self.assertIn(field, s, field)
        self.assertEqual(s["include_lines"], 1)
        self.assertEqual(s["section_lines"], 1)
        self.assertEqual(s["lines"], len(self.SRC.splitlines()) + 1,
                         "文本以换行结尾，split('\\n') 会多出一个空元素")

    def test_profile_lines_flagged(self):
        """[anime] 之后的行要算 profile 行，并在上方注释里注明作用域。"""
        r = annotate_text(self.SRC, style="above")
        self.assertGreater(r["stats"]["profile_lines"], 0)
        self.assertIn("profile", r["text"])

    def test_only_missing_false_would_touch_commented_lines(self):
        """only_missing=False 时允许给已有行尾注释的行再补（行为差异要真实存在）。"""
        a = annotate_text(self.SRC, only_missing=True)["stats"]["added"]
        b = annotate_text(self.SRC, only_missing=False)["stats"]["added"]
        self.assertGreaterEqual(b, a)

    def test_idempotent_for_inline(self):
        """已经补过的行，再补一次不该重复追加（因为已有行尾注释）。"""
        once = annotate_text(self.SRC)["text"]
        twice = annotate_text(once)["text"]
        self.assertEqual(once, twice)

    def test_annotation_does_not_change_parsed_values(self):
        once = annotate_text(self.SRC)["text"]
        a = parse_config_text(self.SRC)
        b = parse_config_text(once)
        self.assertEqual(a["values"], b["values"])
        self.assertEqual(a["includes"], b["includes"])

    def test_out_name(self):
        self.assertTrue(out_name_for("C:/x/mpv.conf").endswith("mpv.说明版.conf"))
        self.assertTrue(out_name_for("/x/conf.txt").endswith("conf.说明版.txt"))

    def test_inline_comment_detector(self):
        self.assertTrue(_has_inline_comment("scale=x  # note"))
        self.assertFalse(_has_inline_comment('sub-color="#FFD766"'),
                         "引号里的 # 不算注释")
        self.assertFalse(_has_inline_comment("scale=x"))


if __name__ == "__main__":
    unittest.main()

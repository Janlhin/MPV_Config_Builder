# -*- coding: utf-8 -*-
"""R-14：行级差异（左右并排）的测试。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.diff import diff_lines, stats, unified                          # noqa: E402


def tags(result):
    return [r["tag"] for r in result["rows"]]


class DiffTest(unittest.TestCase):
    def test_identical(self):
        r = diff_lines("a\nb\nc\n", "a\nb\nc\n")
        self.assertTrue(r["identical"])
        self.assertEqual(r["stats"]["changes"], 0)
        self.assertEqual(set(tags(r)), {"equal"})

    def test_modify_is_paired_not_del_add(self):
        """用户关心"这行被改成什么了"，不是"删一行又加一行"。"""
        r = diff_lines("vo=gpu\n", "vo=gpu-next\n")
        self.assertEqual(tags(r), ["modify"])
        row = r["rows"][0]
        self.assertEqual(row["left"]["text"], "vo=gpu")
        self.assertEqual(row["right"]["text"], "vo=gpu-next")
        self.assertEqual((row["left"]["n"], row["right"]["n"]), (1, 1))

    def test_pure_insertion(self):
        r = diff_lines("a\nc\n", "a\nb\nc\n")
        self.assertEqual(tags(r), ["equal", "add", "equal"])
        add = [x for x in r["rows"] if x["tag"] == "add"][0]
        self.assertIsNone(add["left"])
        self.assertEqual(add["right"]["text"], "b")

    def test_pure_deletion(self):
        r = diff_lines("a\nb\nc\n", "a\nc\n")
        self.assertEqual(tags(r), ["equal", "del", "equal"])
        d = [x for x in r["rows"] if x["tag"] == "del"][0]
        self.assertIsNone(d["right"])

    def test_uneven_replace(self):
        """替换块左右行数不等时，多出来的按纯 add / del 处理。"""
        r = diff_lines("a\nb\nc\n", "a\nX\n")
        self.assertEqual(r["stats"]["modify"], 1)
        self.assertEqual(r["stats"]["del"], 1)
        lefts = [x["left"]["text"] for x in r["rows"] if x["left"]]
        rights = [x["right"]["text"] for x in r["rows"] if x["right"]]
        self.assertIn("b", lefts)
        self.assertIn("c", lefts)
        self.assertIn("X", rights)

    def test_line_numbers_are_1_based(self):
        r = diff_lines("a\nb\n", "a\nb\n")
        self.assertEqual(r["rows"][0]["left"]["n"], 1)
        self.assertEqual(r["rows"][1]["right"]["n"], 2)

    def test_trailing_newline_does_not_add_row(self):
        self.assertTrue(diff_lines("a\nb\n", "a\nb")["identical"],
                        "末尾换行的有无不该算成改动")

    def test_crlf_normalised(self):
        self.assertTrue(diff_lines("a\r\nb\r\n", "a\nb\n")["identical"])

    def test_accepts_lists(self):
        r = diff_lines(["a", "b"], ["a", "c"])
        self.assertEqual(tags(r), ["equal", "modify"])

    def test_empty_before(self):
        r = diff_lines("", "a\nb\n")
        self.assertEqual(r["stats"]["add"], 2)
        self.assertEqual(r["stats"]["del"], 0)

    def test_empty_after(self):
        r = diff_lines("a\nb\n", "")
        self.assertEqual(r["stats"]["del"], 2)

    def test_both_empty(self):
        r = diff_lines("", "")
        self.assertTrue(r["identical"])
        self.assertEqual(r["rows"], [])

    def test_context_trims_unchanged(self):
        before = "\n".join(f"line{i}" for i in range(40)) + "\n"
        after = before.replace("line20", "CHANGED")
        full = diff_lines(before, after)
        trimmed = diff_lines(before, after, context=1)
        self.assertLess(len(trimmed["rows"]), len(full["rows"]))
        self.assertTrue(any(r["tag"] == "modify" for r in trimmed["rows"]))

    def test_stats_shape(self):
        r = diff_lines("a\n", "b\n")
        for k in ("add", "del", "modify", "equal", "changes"):
            self.assertIn(k, r["stats"])
        self.assertEqual(r["stats"]["changes"],
                         r["stats"]["add"] + r["stats"]["del"] + r["stats"]["modify"])

    def test_stats_helper(self):
        self.assertEqual(stats([{"tag": "add"}, {"tag": "add"},
                                {"tag": "equal"}])["changes"], 2)

    def test_unified_text(self):
        u = unified("vo=gpu\n", "vo=gpu-next\n")
        self.assertIn("---", u)
        self.assertIn("+++", u)
        self.assertIn("-vo=gpu", u)
        self.assertIn("+vo=gpu-next", u)


class MergeDiffIntegrationTest(unittest.TestCase):
    """真实场景：merge 写入前后的差异，正是用户要看的那个。"""

    def test_merge_diff_reflects_changes(self):
        from core.writer import apply_state_to_lines
        before = "# 我的\nvo=gpu\nscale=bilinear\nkeep-open=yes\n"
        new_lines, _ = apply_state_to_lines(
            before.splitlines(), {"vo": "gpu-next"}, [])
        r = diff_lines(before, "\n".join(new_lines) + "\n")
        self.assertFalse(r["identical"])
        mods = [x for x in r["rows"] if x["tag"] == "modify"]
        self.assertEqual(len(mods), 1, f"应当只有 vo 被改：{mods}")
        self.assertEqual(mods[0]["left"]["text"], "vo=gpu")
        self.assertEqual(mods[0]["right"]["text"], "vo = gpu-next")
        # 没动过的行必须是 equal（用户一眼能看出"只改了这里"）
        eq = [x["left"]["text"] for x in r["rows"] if x["tag"] == "equal" and x["left"]]
        self.assertIn("keep-open=yes", eq)

    def test_profile_lines_show_as_equal(self):
        """R-26 的效果也要能在 diff 里看出来：profile 里的行不该变成 modify。"""
        from core.writer import apply_state_to_lines
        before = "[p]\nscale=catmull_rom\n"
        new_lines, _ = apply_state_to_lines(before.splitlines(), {"scale": "spline36"}, [])
        r = diff_lines(before, "\n".join(new_lines) + "\n")
        eq_texts = [x["left"]["text"] for x in r["rows"]
                    if x["tag"] == "equal" and x["left"]]
        self.assertIn("scale=catmull_rom", eq_texts,
                      "profile 里的行不该被当成改动")


if __name__ == "__main__":
    unittest.main()

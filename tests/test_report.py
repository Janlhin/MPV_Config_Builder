# -*- coding: utf-8 -*-
"""体检报告的单元测试（不打网络，只走 core.report）。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.report import build_report      # noqa: E402

MESSY = """\
# 一份有毛病的配置
vo=gpu
linear-upscaling=yes
sigmoid-upscaling=yes
interpolation=yes
video-sync=audio
scale=bilinear
scale=spline36
这行没有等号
fake-option-xyz=1
dither-depth=8
"""

GOOD = """\
vo=gpu-next
gpu-api=d3d11
hwdec=auto-safe
video-sync=display-resample
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=yes
deband-iterations=2
"""


class ReportTest(unittest.TestCase):
    def test_text_report_basic_fields(self):
        r = build_report(text=MESSY, name="test.conf")
        self.assertTrue(r["ok"])
        self.assertEqual(r["source"]["name"], "test.conf")
        self.assertGreater(r["source"]["lines"], 5)
        for key in ("counts", "scores", "issues", "suggestions", "conflicts", "values"):
            self.assertIn(key, r)

    def test_detects_conflicts(self):
        r = build_report(text=MESSY, name="test.conf")
        ids = [c["id"] for c in r["conflicts"]]
        self.assertIn("sigmoid_vs_linear", ids)
        self.assertIn("interp_needs_sync", ids)
        # linear-upscaling 不在工具界面的选项表里，但冲突检测必须看得到它
        self.assertIn("linear-upscaling", r["all_values"])

    def test_counts_unknown_and_duplicates(self):
        r = build_report(text=MESSY, name="test.conf")
        self.assertGreaterEqual(r["counts"]["unknown"], 1)
        self.assertGreaterEqual(r["counts"]["duplicates"], 1)
        self.assertTrue(r["detail"]["duplicates"])

    def test_issues_sorted_by_level(self):
        r = build_report(text=MESSY, name="test.conf")
        order = {"error": 0, "warn": 1, "info": 2}
        levels = [order.get(lv, 3) for lv, _ in r["issues"]]
        self.assertEqual(levels, sorted(levels))
        self.assertTrue(any(lv == "error" for lv, _ in r["issues"]))

    def test_clean_config_scores_higher(self):
        bad = build_report(text=MESSY, name="bad.conf")
        good = build_report(text=GOOD, name="good.conf")
        self.assertGreater(good["overall"], bad["overall"])
        self.assertFalse([c for c in good["conflicts"] if c["level"] == "error"])

    def test_file_report_reads_gbk_and_chain(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "mpv.conf").write_text(
                'vo=gpu-next\ninclude = "~~/extra.conf"\nscale=spline36\n', encoding="utf-8")
            (root / "extra.conf").write_bytes("# 中文注释\nhwdec=no\n".encode("gb18030"))
            r = build_report(path=root / "mpv.conf")
            self.assertTrue(r["ok"])
            files = [f["name"] for f in r["chain"]["files"]]
            self.assertEqual(files, ["mpv.conf", "extra.conf"])
            self.assertEqual(r["values"]["hwdec"], "no")
            self.assertEqual(r["sources"]["hwdec"], "extra.conf")
            self.assertIn("GBK", [f["encoding"] for f in r["chain"]["files"]][1])

    def test_missing_file(self):
        r = build_report(path="Z:/nope/mpv.conf")
        self.assertFalse(r["ok"])

    def test_empty_input(self):
        self.assertFalse(build_report(text="")["ok"])

    def test_profile_sections_reported_separately(self):
        text = "vo=gpu-next\n[myprof]\nscale=spline36\n"
        r = build_report(text=text, name="x.conf")
        self.assertEqual(len(r["profiles"]), 1)
        self.assertEqual(r["profiles"][0]["name"], "myprof")
        self.assertNotIn("scale", r["values"])

    def test_report_is_json_serializable(self):
        import json
        r = build_report(text=MESSY, name="x.conf")
        json.dumps(r, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()

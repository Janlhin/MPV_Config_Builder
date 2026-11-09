# -*- coding: utf-8 -*-
"""② 版本级兼容检测：mpv 版本探测（待做 §〇 第 13 项）。

源码里跑永远是对的，坑只在打包产物里 —— 但这个模块是纯函数 + 子进程封装，
用 mock 把子进程替掉就能在任意环境验证，不依赖本机是否装了 mpv。
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import mpv_version


class ParseVersionTest(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(
            mpv_version.parse_version("mpv 0.39.0 (C) 2000-2024 mpv/MPlayer"),
            "0.39.0",
        )

    def test_git_suffix(self):
        self.assertEqual(
            mpv_version.parse_version("mpv 0.38.0-git-abc123 (C) ..."),
            "0.38.0",
        )

    def test_no_match(self):
        self.assertIsNone(mpv_version.parse_version("this is not mpv output"))

    def test_empty(self):
        self.assertIsNone(mpv_version.parse_version(""))


class CompareVersionsTest(unittest.TestCase):
    def test_lt(self):
        self.assertEqual(mpv_version.compare_versions("0.38.0", "0.39.0"), -1)

    def test_eq(self):
        self.assertEqual(mpv_version.compare_versions("0.39.0", "0.39.0"), 0)

    def test_gt(self):
        self.assertEqual(mpv_version.compare_versions("0.39.0", "0.38.0"), 1)

    def test_partial(self):
        # "0.39" 当作 0.39.0，与完整写法相等
        self.assertEqual(mpv_version.compare_versions("0.39", "0.39.0"), 0)


class DetectMpvVersionTest(unittest.TestCase):
    def _fake(self, returncode=0, stdout="", stderr=""):
        fake = mock.Mock()
        fake.returncode = returncode
        fake.stdout = stdout
        fake.stderr = stderr
        return fake

    def test_detect_via_explicit_path(self):
        out = self._fake(
            stdout="mpv 0.39.0-123 (C) 2000-2024 mpv/MPlayer/mplayer2")
        with mock.patch.object(mpv_version.subprocess, "run", return_value=out):
            self.assertEqual(mpv_version.detect_mpv_version("mpv"), "0.39.0")

    def test_detect_returns_none_on_nonzero(self):
        out = self._fake(returncode=1, stderr="error")
        with mock.patch.object(mpv_version.subprocess, "run", return_value=out):
            self.assertIsNone(mpv_version.detect_mpv_version("mpv"))

    def test_detect_returns_none_when_exe_missing(self):
        # 显式路径指向不存在的可执行文件 → FileNotFoundError → 降级 None
        with mock.patch.object(mpv_version.subprocess, "run",
                               side_effect=FileNotFoundError):
            self.assertIsNone(mpv_version.detect_mpv_version("nope"))

    def test_detect_returns_none_when_not_on_path(self):
        # 不传路径且 PATH 上找不到 mpv
        with mock.patch.object(mpv_version.shutil, "which", return_value=None):
            self.assertIsNone(mpv_version.detect_mpv_version())

    def test_find_mpv_first_candidate(self):
        with mock.patch.object(mpv_version.shutil, "which",
                               side_effect=["C:\\mpv\\mpv.exe", None, None]):
            self.assertEqual(mpv_version._find_mpv(), "C:\\mpv\\mpv.exe")


class CaptureMpvOptionsTest(unittest.TestCase):
    SAMPLE = (
        "Options:\n"
        "\n"
        " --ab-loop-a                      Time (default: no)\n"
        " --ad-lavc-o                      Key/value list (default: )\n"
        "    --ad-lavc-o-add\n"
        "    --ad-lavc-o-del\n"
        "    Use --no-border to disable standard decorations.\n"
    )

    def _fake(self, returncode=0, stdout="", stderr=""):
        fake = mock.Mock()
        fake.returncode = returncode
        fake.stdout = stdout
        fake.stderr = stderr
        return fake

    def test_parse_list_options(self):
        keys = mpv_version._parse_list_options(self.SAMPLE)
        self.assertIn("ab-loop-a", keys)
        self.assertIn("ad-lavc-o", keys)
        self.assertIn("ad-lavc-o-add", keys)
        self.assertIn("ad-lavc-o-del", keys)
        # 说明文字（"Use --no-border ..."）不以 -- 开头，不应被当成选项
        self.assertNotIn("no-border", keys)

    def test_capture_via_explicit_path(self):
        with mock.patch.object(mpv_version.subprocess, "run",
                               return_value=self._fake(stdout=self.SAMPLE)):
            res = mpv_version.capture_mpv_options("mpv")
        self.assertIsInstance(res, set)
        self.assertIn("ab-loop-a", res)

    def test_capture_returns_none_on_nonzero(self):
        with mock.patch.object(mpv_version.subprocess, "run",
                               return_value=self._fake(returncode=1, stderr="err")):
            self.assertIsNone(mpv_version.capture_mpv_options("mpv"))

    def test_capture_returns_none_when_exe_missing(self):
        with mock.patch.object(mpv_version.subprocess, "run",
                               side_effect=FileNotFoundError):
            self.assertIsNone(mpv_version.capture_mpv_options("nope"))

    def test_capture_returns_none_when_not_on_path(self):
        with mock.patch.object(mpv_version.shutil, "which", return_value=None):
            self.assertIsNone(mpv_version.capture_mpv_options())


class DiffUnsupportedTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(
            mpv_version.diff_unsupported({"a", "b", "c"}, {"a", "b"}), {"c"})

    def test_unknown_user_options_is_empty(self):
        self.assertEqual(mpv_version.diff_unsupported({"a", "b"}, None), set())

    def test_no_diff(self):
        self.assertEqual(
            mpv_version.diff_unsupported({"a", "b"}, {"a", "b", "x"}), set())


if __name__ == "__main__":
    unittest.main()

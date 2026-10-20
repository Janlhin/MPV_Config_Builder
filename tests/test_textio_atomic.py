# -*- coding: utf-8 -*-
"""原子写与编码回退上报的行为契约（T18）。

这些用例存在的理由：直接 write_bytes 是「先截断再写」，崩一次就毁用户配置。
write_atomic 必须保证：要么旧内容完整、要么新内容完整，且失败不留临时文件。
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import textio


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mb-atomic-"))
        self.p = self.dir / "mpv.conf"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_write_creates_file(self):
        textio.write_atomic(self.p, b"hello")
        self.assertEqual(self.p.read_bytes(), b"hello")

    def test_overwrites_and_leaves_no_tmp(self):
        textio.write_atomic(self.p, b"a")
        textio.write_atomic(self.p, b"b")
        self.assertEqual(self.p.read_bytes(), b"b")
        self.assertEqual(list(self.dir.glob(".*.tmp")), [])

    def test_accepts_str(self):
        textio.write_atomic(self.p, "中文")
        self.assertEqual(self.p.read_bytes(), "中文".encode("utf-8"))

    def test_parent_dir_created(self):
        nested = self.dir / "a" / "b" / "x.conf"
        textio.write_atomic(nested, b"x")
        self.assertEqual(nested.read_bytes(), b"x")

    def test_replace_failure_keeps_original_and_cleans_tmp(self):
        self.p.write_bytes(b"old")
        with mock.patch.object(textio.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                textio.write_atomic(self.p, b"new")
        self.assertEqual(self.p.read_bytes(), b"old")
        self.assertEqual([q.name for q in self.dir.iterdir()], [self.p.name])

    def test_fsync_failure_keeps_original_and_cleans_tmp(self):
        self.p.write_bytes(b"old")
        with mock.patch.object(textio.os, "fsync", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                textio.write_atomic(self.p, b"new")
        self.assertEqual(self.p.read_bytes(), b"old")
        self.assertEqual([q.name for q in self.dir.iterdir()], [self.p.name])

    def test_permission_error_retries_then_succeeds(self):
        self.p.write_bytes(b"old")
        real = textio.os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError("locked by mpv")
            return real(src, dst)

        with mock.patch.object(textio.os, "replace", side_effect=flaky):
            textio.write_atomic(self.p, b"new", retries=2)
        self.assertEqual(self.p.read_bytes(), b"new")
        self.assertEqual(calls["n"], 2)


class EncodeReportTest(unittest.TestCase):
    def test_gbk_no_fallback(self):
        data, used = textio.encode_report("中文", "gb18030")
        self.assertEqual(used, "gb18030")
        self.assertEqual(data, "中文".encode("gb18030"))

    def test_emoji_falls_back_to_utf8_and_is_reported(self):
        # 注意：gb18030 覆盖全部 Unicode（包括 emoji），不会回退；
        # 真正会回退的是 Big5 / GBK 这类窄编码。
        data, used = textio.encode_report("😀", "big5")
        self.assertEqual(used, "utf-8")
        self.assertEqual(data, "😀".encode("utf-8"))

    def test_encode_keeps_old_signature(self):
        self.assertEqual(textio.encode("中文", "gb18030"), "中文".encode("gb18030"))

    def test_write_report_marks_fallback(self):
        d = Path(tempfile.mkdtemp(prefix="mb-enc-"))
        try:
            p = d / "a.conf"
            report = {}
            textio.write(p, "舊內容😀", "big5", False, "\n", report=report)
            self.assertTrue(report["fallback"])
            self.assertEqual(report["encoding"], "utf-8")
            self.assertEqual(p.read_text(encoding="utf-8"), "舊內容😀")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class BackupTest(unittest.TestCase):
    def test_backup_content_identical(self):
        d = Path(tempfile.mkdtemp(prefix="mb-bak-"))
        try:
            p = d / "mpv.conf"
            p.write_bytes(b"content\r\n")
            bak = textio.backup(p)
            self.assertIsNotNone(bak)
            self.assertEqual(bak.read_bytes(), b"content\r\n")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_backup_missing_file_returns_none(self):
        d = Path(tempfile.mkdtemp(prefix="mb-bak-"))
        try:
            self.assertIsNone(textio.backup(d / "nope.conf"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

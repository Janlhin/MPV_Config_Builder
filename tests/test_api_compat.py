# -*- coding: utf-8 -*-
"""api_compat（待做 §〇 第 13 项 ①③）的单元覆盖。

只验「探测 + 比对 + 降级」的组装逻辑；子进程探测本身由
tests/test_mpv_version.py 覆盖。这里用 mock 替掉探测与读库，
不依赖本机装没装 mpv，也不去碰真实的 data/*.json。
"""
import contextlib
import unittest
from unittest import mock

from webui import server
from core import mpv_version as mpv_mod
from core import options_db as db_mod


class ApiCompatTest(unittest.TestCase):
    def _patch(self, version, user_opts, db_keys):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.multiple(
            mpv_mod,
            detect_mpv_version=mock.Mock(return_value=version),
            capture_mpv_options=mock.Mock(return_value=user_opts),
        ))
        stack.enter_context(mock.patch.object(
            db_mod, "load_db",
            return_value={"options": {k: {} for k in db_keys}, "meta": {}}))
        return stack

    def test_scanned_reports_unsupported(self):
        db_keys = {"a", "b", "c"}
        with self._patch("0.39.0", {"a", "b"}, db_keys):
            r = server.api_compat()
        self.assertEqual(r["version"], "0.39.0")
        self.assertTrue(r["scanned"])
        # c 在库里、用户 mpv 没有 → 不支持
        self.assertEqual(set(r["unsupported"]), {"c"})

    def test_no_mpv_downgrades_safely(self):
        db_keys = {"a", "b"}
        with self._patch(None, None, db_keys):
            r = server.api_compat()
        self.assertIsNone(r["version"])
        self.assertFalse(r["scanned"])
        # 版本未知不报警
        self.assertEqual(r["unsupported"], [])

    def test_unknown_user_options_is_empty(self):
        # 拿到了版本、但 list-options 没拿到：等价"版本未知"，同样不报警
        db_keys = {"a", "b"}
        with self._patch("0.39.0", set(), db_keys):
            r = server.api_compat()
        self.assertEqual(r["unsupported"], [])


if __name__ == "__main__":
    unittest.main()

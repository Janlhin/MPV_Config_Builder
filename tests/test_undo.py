# -*- coding: utf-8 -*-
"""写后 10 秒撤销：后端要把这次的备份路径交出来，且按它回滚能真的还原。"""
import tempfile
import unittest
from pathlib import Path

from webui import server


class TestUndoAfterWrite(unittest.TestCase):
    def test_apply_reports_backup_and_restore_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            main = Path(d) / "mpv.conf"
            main.write_text("# 原始内容\n", encoding="utf-8")
            r = server.api_config_apply({
                "target": d,
                "state": {"values": {"scale": "bilinear"}},
                "write_mode": "include",
            })
            self.assertTrue(r["ok"], r)
            self.assertEqual(len(r["backups"]), 1, r)
            self.assertTrue(Path(r["backups"][0]).is_file())

            rr = server.api_restore({"path": r["backups"][0]})
            self.assertTrue(rr["ok"], rr)
            self.assertEqual(main.read_text(encoding="utf-8"), "# 原始内容\n")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""uosc.conf 读写：解析保序、只改该改的、编码与备份。

这一组测试盯的是「保存一次不该弄坏别的东西」——
uosc.conf 里全是用户手写的注释和本工具不认识的新键，
少一条注释、多一行空行，都算事故。
"""
import tempfile
import unittest
from pathlib import Path

from core import uosc, textio


SAMPLE = """\
# uosc 默认配置（节选）
# Display style of current position. available: line, bar
timeline_style=line
timeline_size=40
# 这是用户自己加的中文注释
scale=1
new_widget_from_future=1
"""


class TestParse(unittest.TestCase):
    def test_keeps_comments_blanks_and_unknown(self):
        rows, _ = uosc.parse(SAMPLE)
        kinds = [r["kind"] for r in rows]
        self.assertEqual(kinds.count("comment"), 3)
        self.assertIn("kv", kinds)
        unknown = [r for r in rows if r["kind"] == "kv" and not r.get("known")]
        self.assertEqual([r["key"] for r in unknown], ["new_widget_from_future"])
        self.assertEqual(unknown[0]["group"], "unknown")

    def test_known_keys_carry_metadata(self):
        rows, _ = uosc.parse(SAMPLE)
        by_key = {r["key"]: r for r in rows if r["kind"] == "kv"}
        self.assertEqual(by_key["timeline_style"]["type"], "enum")
        self.assertEqual(by_key["timeline_style"]["choices"], ("line", "bar"))
        self.assertEqual(by_key["scale"]["group"], "look")
        self.assertTrue(by_key["timeline_size"]["zh"])

    def test_duplicate_key_is_flagged(self):
        rows, _ = uosc.parse("scale=1\nscale=2\n")
        self.assertIn("duplicate_of", rows[1])

    def test_line_without_equals_is_untouched(self):
        rows, _ = uosc.parse("这一行没有等号\nscale=1\n")
        self.assertEqual(rows[0]["kind"], "other")


class TestApply(unittest.TestCase):
    def test_only_submitted_key_changes(self):
        text, changes, errors = uosc.apply_text(SAMPLE, {"timeline_size": "48"})
        self.assertEqual(errors, [])
        self.assertEqual(len(changes), 1)
        self.assertIn("timeline_size=48", text)
        self.assertIn("timeline_style=line", text)          # 没提交的键不动
        self.assertIn("# 这是用户自己加的中文注释", text)      # 注释还在
        self.assertIn("new_widget_from_future=1", text)      # 未知键还在

    def test_same_value_is_not_a_change(self):
        text, changes, errors = uosc.apply_text(SAMPLE, {"timeline_size": "40"})
        self.assertEqual(changes, [])
        self.assertEqual(errors, [])
        self.assertEqual(text, SAMPLE)                       # 逐字节相同

    def test_bool_normalized(self):
        text, changes, _ = uosc.apply_text(SAMPLE, {"timeline_cache": "YES"})
        self.assertIn("timeline_cache=yes", text)
        self.assertEqual(changes[0]["to"], "yes")

    def test_enum_and_number_rejected(self):
        _, _, errors = uosc.apply_text(SAMPLE, {"timeline_style": "circle"})
        self.assertTrue(errors and "只能是" in errors[0])
        _, _, errors = uosc.apply_text(SAMPLE, {"timeline_size": "abc"})
        self.assertTrue(errors and "数字" in errors[0])
        _, _, errors = uosc.apply_text(SAMPLE, {"timeline_cache": "maybe"})
        self.assertTrue(errors and "yes" in errors[0])

    def test_missing_key_is_appended(self):
        text, changes, _ = uosc.apply_text(SAMPLE, {"volume": "left"})
        self.assertIn("# 以下由 MPV Config Builder 追加", text)
        self.assertIn("volume=left", text)
        self.assertEqual(changes[0]["from"], "")

    def test_unknown_key_submission_does_not_rewrite(self):
        text, changes, _ = uosc.apply_text(
            SAMPLE, {"new_widget_from_future": "2"})
        self.assertEqual(changes, [])
        self.assertIn("new_widget_from_future=1", text)


class TestSave(unittest.TestCase):
    def _make(self, text=SAMPLE, encoding="utf-8"):
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-")
        d = Path(tmp) / "script-opts"
        d.mkdir(parents=True)
        p = d / "uosc.conf"
        p.write_bytes(text.encode(encoding))
        return Path(tmp), p

    def test_save_writes_backup_and_keeps_text(self):
        root, p = self._make()
        res = uosc.save(p, {"timeline_size": "48"})
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["backup"] and Path(res["backup"]).is_file())
        new = p.read_text(encoding="utf-8")
        self.assertIn("timeline_size=48", new)
        self.assertIn("new_widget_from_future=1", new)
        self.assertIn("# 这是用户自己加的中文注释", new)
        # 备份里是改之前的内容
        self.assertIn("timeline_size=40", Path(res["backup"]).read_text(encoding="utf-8"))

    def test_save_keeps_gbk_encoding(self):
        text = "# 中文注释\nscale=1\n"
        root, p = self._make(text, encoding="gb18030")
        res = uosc.save(p, {"scale": "1.2"})
        self.assertTrue(res["ok"], res)
        self.assertEqual(textio.read(p).encoding, "gb18030")
        self.assertIn("scale=1.2", p.read_text(encoding="gb18030"))

    def test_crlf_is_preserved(self):
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-")
        p = Path(tmp) / "uosc.conf"
        p.write_bytes(b"scale=1\r\ntimeline_size=40\r\n")
        res = uosc.save(p, {"scale": "1.5"})
        self.assertTrue(res["ok"], res)
        raw = p.read_bytes()
        self.assertIn(b"scale=1.5\r\n", raw)
        self.assertFalse(b"\n" in raw.replace(b"\r\n", b""))

    def test_dry_run_does_not_write(self):
        root, p = self._make()
        before = p.read_bytes()
        res = uosc.save(p, {"timeline_size": "48"}, dry_run=True)
        self.assertTrue(res["ok"], res)
        self.assertIn("timeline_size=48", res["text"])
        self.assertEqual(p.read_bytes(), before)
        self.assertFalse(res.get("backup"))       # dry_run 不留备份

    def test_invalid_value_does_not_write(self):
        root, p = self._make()
        before = p.read_bytes()
        res = uosc.save(p, {"timeline_style": "circle"})
        self.assertFalse(res["ok"])
        self.assertEqual(p.read_bytes(), before)

    def test_empty_values_refused(self):
        root, p = self._make()
        res = uosc.save(p, {})
        self.assertFalse(res["ok"])


class TestLoad(unittest.TestCase):
    def test_load_reports_groups_and_stats(self):
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-")
        (Path(tmp) / "script-opts").mkdir()
        (Path(tmp) / "script-opts" / "uosc.conf").write_text(SAMPLE, encoding="utf-8")
        data = uosc.load(tmp)
        self.assertTrue(data["ok"], data)
        self.assertTrue(data["path"].endswith("uosc.conf"))
        self.assertEqual(data["stats"]["unknown"], 1)
        self.assertEqual(len(data["groups"]), len(uosc.GROUPS) + 1)   # + 未收录

    def test_load_without_file_explains_where_to_put_it(self):
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-")
        data = uosc.load(tmp)
        self.assertFalse(data["ok"])
        self.assertIn("script-opts", data["hint"])
        self.assertEqual(data["rows"], [])

    def test_portable_config_subdir_is_also_found(self):
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-")
        d = Path(tmp) / "portable_config" / "script-opts"
        d.mkdir(parents=True)
        (d / "uosc.conf").write_text("scale=1\n", encoding="utf-8")
        data = uosc.load(tmp)
        self.assertTrue(data["ok"], data)

    def test_metadata_covers_every_group(self):
        self.assertEqual(len(uosc.GROUPS), 9)
        for gid in [g[0] for g in uosc.GROUPS]:
            self.assertTrue(any(m["group"] == gid for m in uosc.META.values()), gid)

    def test_missing_file_with_explicit_path_points_there(self):
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-")
        p = Path(tmp) / "portable_config" / "script-opts" / "uosc.conf"
        data = uosc.load(tmp, path=str(p))
        self.assertFalse(data["ok"])
        self.assertEqual(data["path"], str(p))


class TestDefaultFile(unittest.TestCase):
    def test_template_only_writes_valued_defaults(self):
        text, kept = uosc.default_text()
        expected = [k for k, m in uosc.META.items() if m["default"] != ""]
        self.assertEqual(sorted(kept), sorted(expected))
        self.assertIn("MPV Config Builder", text)
        rows, _ = uosc.parse(text)
        kv = [r for r in rows if r["kind"] == "kv"]
        self.assertEqual(len(kv), len(expected))
        self.assertTrue(all(r.get("known") and r["value"] != "" for r in kv))

    def test_create_refuses_to_overwrite(self):
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-")
        p = Path(tmp) / "script-opts" / "uosc.conf"
        first = uosc.create(p, newline="\n")
        self.assertTrue(first["ok"], first)
        self.assertTrue(p.is_file())
        raw = p.read_bytes()
        self.assertNotIn(b"\r\n", raw)          # newline="\n" 时不该自己变 CRLF
        second = uosc.create(p, newline="\n")
        self.assertFalse(second["ok"])
        self.assertEqual(p.read_bytes(), raw)   # 第二次没动文件
        data = uosc.load(tmp)
        self.assertTrue(data["ok"], data)
        self.assertEqual(data["stats"]["unknown"], 0)

    def test_create_makes_missing_dirs_and_crlf(self):
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-")
        p = Path(tmp) / "script-opts" / "uosc.conf"
        res = uosc.create(p, newline="\r\n")
        self.assertTrue(res["ok"], res)
        self.assertTrue(p.parent.is_dir())
        self.assertIn(b"\r\n", p.read_bytes())


class TestCreateApi(unittest.TestCase):
    def test_create_through_api_then_reject_second_and_outside(self):
        from core.schema import load_settings, save_settings
        from webui import server
        tmp = tempfile.mkdtemp(prefix="mpvcb-uosc-api-")
        before = load_settings() or {}
        self.addCleanup(save_settings, before)

        read = server.api_uosc({"target": tmp})
        self.assertFalse(read["ok"])
        self.assertFalse(read["exists"])
        p = read["path"]
        self.assertTrue(p.endswith("uosc.conf"))

        res = server.api_uosc_save({"target": tmp, "path": p, "values": {}, "create": True})
        self.assertTrue(res["ok"], res)
        self.assertTrue(Path(p).is_file())

        again = server.api_uosc_save({"target": tmp, "path": p, "values": {}, "create": True})
        self.assertFalse(again["ok"])

        outside = server.api_uosc_save({"path": r"C:\Windows\uosc.conf",
                                        "values": {}, "create": True})
        self.assertFalse(outside["ok"])
        self.assertIn("安全限制", outside["detail"])


class TestRoutes(unittest.TestCase):
    def test_uosc_routes_are_registered(self):
        from webui import api
        self.assertEqual(api.ROUTES_QUERY["/api/uosc"], "api_uosc")
        self.assertEqual(api.ROUTES_POST["/api/uosc/save"], "api_uosc_save")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""统一搜索：四类结果分组、没有目标目录时只搜静态两类。"""
import tempfile
import unittest
from pathlib import Path

from core import search


class TestGlobalSearch(unittest.TestCase):
    def _target(self):
        tmp = tempfile.mkdtemp(prefix="mpvcb-search-")
        p = Path(tmp)
        (p / "input.conf").write_text(
            "SPACE cycle pause   # 播放/暂停\nq quit\n", encoding="utf-8")
        (p / "scripts").mkdir()
        (p / "scripts" / "uosc.lua").write_text("-- uosc\n", encoding="utf-8")
        (p / "script-opts").mkdir()
        (p / "script-opts" / "uosc.conf").write_text("scale=1\n", encoding="utf-8")
        return str(p)

    def test_empty_query_is_refused(self):
        r = search.search(None, "   ")
        self.assertFalse(r["ok"])

    def test_options_domain_hits_key(self):
        r = search.search(None, "scale")
        self.assertTrue(r["ok"], r)
        ids = [g["id"] for g in r["groups"]]
        self.assertIn("options", ids)
        items = [g for g in r["groups"] if g["id"] == "options"][0]["items"]
        self.assertTrue(any(x["key"].startswith("scale") for x in items))

    def test_uosc_domain_hits_known_key(self):
        r = search.search(None, "timeline")
        groups = {g["id"]: g for g in r["groups"]}
        self.assertIn("uosc", groups)
        keys = [x["key"] for x in groups["uosc"]["items"]]
        self.assertIn("timeline_style", keys)

    def test_keys_domain_reads_target(self):
        r = search.search(self._target(), "pause")
        groups = {g["id"]: g for g in r["groups"]}
        self.assertIn("keys", groups)
        self.assertTrue(any(x["key"] == "SPACE" for x in groups["keys"]["items"]))

    def test_scripts_domain_lists_files(self):
        r = search.search(self._target(), "uosc")
        groups = {g["id"]: g for g in r["groups"]}
        self.assertIn("scripts", groups)
        names = [x["key"] for x in groups["scripts"]["items"]]
        self.assertIn("uosc.lua", names)
        self.assertIn("uosc.conf", names)

    def test_without_target_only_static_domains(self):
        r = search.search(None, "pause")
        ids = [g["id"] for g in r["groups"]]
        self.assertNotIn("keys", ids)
        self.assertNotIn("scripts", ids)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""「我的分组」：拖拽归类后的归属要落盘，且只收合法的组名。"""
import unittest

from core.schema import load_settings, save_settings
from webui import server


class TestTags(unittest.TestCase):
    def setUp(self):
        self.before = load_settings() or {}
        self.addCleanup(save_settings, self.before)

    def test_roundtrip_keeps_valid_only(self):
        res = server.api_tags_set({"tags": {
            "scale": "quality",
            "vo": "common",
            "bad": "nope",          # 不认识的组名 → 丢
            "empty": "",            # 空值 → 丢
            "timeline_style": "subtitle",
        }})
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["count"], 3)
        got = server.api_tags({})
        self.assertEqual(got["tags"]["scale"], "quality")
        self.assertEqual(got["tags"]["vo"], "common")
        self.assertEqual(got["tags"]["timeline_style"], "subtitle")
        self.assertNotIn("bad", got["tags"])

    def test_rejects_non_dict(self):
        res = server.api_tags_set({"tags": ["scale"]})
        self.assertFalse(res["ok"])

    def test_empty_clears_previous(self):
        server.api_tags_set({"tags": {"scale": "quality"}})
        res = server.api_tags_set({"tags": {}})
        self.assertTrue(res["ok"])
        self.assertEqual(server.api_tags({})["tags"], {})


if __name__ == "__main__":
    unittest.main()

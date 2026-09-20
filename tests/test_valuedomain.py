# -*- coding: utf-8 -*-
"""值域（能选什么 / 能不能自己填）的测试。

背景：界面上曾经"建议值非空就渲染成只能选的下拉框"，而那串建议值只是**举例**。
结果 `scale` 只能从手写的 10 个里挑（mpv 实际有 39 个）、
`geometry` / `sub-font` / `volume` 这些自由格式被锁死在几个示例值里。

判据必须来自 mpv 的真实类型表，不是"参数表里写没写值"。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.options_db import load_db                                        # noqa: E402
from core.schema import (                                                  # noqa: E402
    PARAMS, is_free_form, real_values, value_info,
)
from webui import server                                                   # noqa: E402

DB = load_db()["options"]


def core_item(key):
    for x in server.api_options()["core"]:
        if x["key"] == key:
            return x
    return None


class RealValuesTest(unittest.TestCase):
    """库里查得到取值表时，不能被精选层的短列表盖掉。"""

    def test_scale_has_all_39_values(self):
        it = core_item("scale")
        self.assertIsNotNone(it)
        self.assertGreaterEqual(len(it["options"]), 39,
                                "scale 的候选必须是库里那 39 个，不是精选层的 10 个")

    def test_suggest_is_still_the_short_list(self):
        """建议值仍然是精选层那串（界面单独显示），别把它撑大。"""
        it = core_item("scale")
        self.assertLessEqual(len(it["suggest"]), 12)

    def test_video_sync_more_than_suggestions(self):
        it = core_item("video-sync")
        self.assertGreater(len(it["options"]), len(it["suggest"]))
        self.assertIn("display-resample-desync", it["options"])

    def test_options_include_suggestions(self):
        """候选里必须包含建议值 —— 否则会出现"下拉里能选、校验说不行"。"""
        for x in server.api_options()["core"]:
            miss = [v for v in x["suggest"] if v not in x["options"]]
            self.assertEqual(miss, [], f"{x['key']} 的建议值不在候选里：{miss}")


class FreeFormTest(unittest.TestCase):
    """自由格式的项必须允许自己填。"""

    def test_geometry_is_open(self):
        it = core_item("geometry")
        self.assertTrue(it["open"], "geometry 是 Window geometry，应当能自由填")

    def test_free_text_types_are_open(self):
        for key in ("sub-font", "volume", "sub-font-size", "demuxer-max-bytes",
                    "autofit", "autofit-larger", "autofit-smaller"):
            it = core_item(key)
            self.assertTrue(it["open"], f"{key}（库类型自由格式）应当能自由填")

    def test_real_enums_are_closed(self):
        """真枚举必须拦住乱填 —— 不然用户填了 mpv 会报错的值都不知道。"""
        for key in ("scale", "cscale", "dscale", "deband", "cache",
                    "keepaspect-window", "hidpi-window-scale"):
            it = core_item(key)
            self.assertFalse(it["open"], f"{key} 是真枚举，应当只允许固定取值")

    def test_is_free_form_reads_db_type(self):
        self.assertFalse(is_free_form("scale", "enum"))
        self.assertTrue(is_free_form("geometry", "str"))

    def test_unknown_key_is_open(self):
        """库里查不到的类型不瞎判 —— 允许填。"""
        self.assertTrue(is_free_form("完全不存在的选项", "enum"))


class ApiShapeTest(unittest.TestCase):
    def test_core_items_carry_value_domain(self):
        for x in server.api_options()["core"]:
            for f in ("type", "suggest", "options", "open"):
                self.assertIn(f, x, f"{x['key']} 缺字段 {f}")

    def test_db_items_carry_value_domain(self):
        d = server.api_db_options({"limit": 50})
        for x in d["items"]:
            self.assertIn("open", x, x.get("key"))

    def test_types_come_from_db_not_guess(self):
        """type 必须是库里的真类型，不是"建议值是否 yes/no"猜的。"""
        from core.schema import db_option_type
        for key, want in (("sub-font", "str"), ("sub-color", "color"),
                          ("sub-font-size", "float"), ("geometry", "str"),
                          ("scale", "enum")):
            it = core_item(key)
            self.assertEqual(it["type"], want,
                             f"{key} 的界面类型应当是 {want}，实际 {it['type']}")
            self.assertEqual(it["type"], db_option_type(DB[key]))


class FrontendContractTest(unittest.TestCase):
    """前端要按 open / options 渲染，不能再只看建议值。"""

    def setUp(self):
        self.js = (ROOT / "webui" / "static" / "state.js").read_text(encoding="utf-8")

    def test_uses_open_flag(self):
        start = self.js.index("function optRow")
        body = self.js[start:start + 2600]
        self.assertIn("item.open", body, "optRow 没读 open 标记")
        self.assertIn("item.options", body, "optRow 没读完整候选表")

    def test_combobox_via_datalist(self):
        start = self.js.index("function optRow")
        body = self.js[start:start + 2600]
        self.assertIn("datalist", body, "可自填的项应当用 input+datalist 组合框")

    def test_closed_enum_still_select(self):
        start = self.js.index("function optRow")
        body = self.js[start:start + 2600]
        self.assertIn("<select", body, "封闭枚举仍应保留下拉框")

    def test_check_value_respects_open(self):
        start = self.js.index("function checkValue")
        body = self.js[start:start + 1400]
        self.assertIn("item.open", body, "checkValue 没按 open 放行")
        self.assertIn("item.options", body, "checkValue 应当拿完整候选表校验")


if __name__ == "__main__":
    unittest.main()

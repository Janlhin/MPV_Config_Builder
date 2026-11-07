# -*- coding: utf-8 -*-
"""mpv 全量选项数据库测试：解析结果 / 合并质量 / 搜索 / JSON 往返。"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# 允许直接跑本文件（py -3 tests\test_options_db.py），而不只是 -m unittest
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import options_db  # noqa: E402
from core.options_db import DB_PATH, build_db, load_db, search  # noqa: E402

#: 全部测试共用一份内存数据库（构建一次约 0.1s）
#
# ⚠ 为什么这里不能无条件 build_db()：中文手册源文件 options.rst **在仓库外**
# （core/options_db.py 的注释写明了：它只在重新生成选项库时才需要，读取已生成的
# JSON 并不需要）。无条件重建的后果是 —— 在没有那份源文件的机器上，本模块
# **import 就失败**，29 项用例直接消失：CI 首次运行收集到 620 项，本机是 649 项，
# 数字对不上又连带把「文档数字与实测一致」也拖红。
#
# 所以：有源文件就从源重建（连解析器一起测），没有就退回读仓库里已生成的 JSON
# （测的是实际随包发布的那份数据）。两种情况下用例数一致。
BUILT_FROM_SOURCE = options_db._resolve_rst_path().is_file()
if BUILT_FROM_SOURCE:
    DB = build_db()
else:
    DB = load_db()
OPTIONS = DB["options"]
GROUPS = DB["groups"]
META = DB["meta"]

# 中文说明里不允许出现的 RST 残留标记
BAD_MARKUP = (".. note::", ".. warning::", ".. admonition::", "``", "`_", "**")


class TestBuildDb(unittest.TestCase):
    """解析 + 合并的整体质量。"""

    def test_shape(self):
        self.assertEqual(set(DB), {"meta", "groups", "options"})
        self.assertIsInstance(OPTIONS, dict)
        self.assertIsInstance(GROUPS, list)

    def test_top_level_count(self):
        # raw 里 --list-options 输出了 829 个顶层选项
        self.assertGreaterEqual(len(OPTIONS), 800)
        self.assertEqual(META["count"], len(OPTIONS))

    def test_zh_coverage(self):
        with_zh = [k for k, v in OPTIONS.items() if v["zh_desc"]]
        self.assertGreaterEqual(len(with_zh), 650)
        self.assertEqual(META["with_zh"], len(with_zh))

    def test_every_entry_has_schema_keys(self):
        required = {
            "key", "type", "range", "default", "choices", "deprecated",
            "sub_options", "group", "zh_sig", "zh_desc",
        }
        for key, entry in OPTIONS.items():
            self.assertEqual(entry["key"], key)
            self.assertTrue(required <= set(entry), "%s 缺字段" % key)
            self.assertIsInstance(entry["choices"], list)
            self.assertIsInstance(entry["sub_options"], list)
            self.assertIsInstance(entry["deprecated"], bool)
            self.assertTrue(entry["group"], "%s 没有分类" % key)

    def test_groups_are_real_and_used(self):
        self.assertGreaterEqual(len(GROUPS), 10)
        self.assertEqual(len(GROUPS), len(set(GROUPS)), "分类有重复")
        used = {v["group"] for v in OPTIONS.values()}
        self.assertEqual(used, set(GROUPS), "分类列表与选项实际分类不一致")
        self.assertIn("字幕", GROUPS)
        self.assertIn("其它", GROUPS)


class TestParsedFields(unittest.TestCase):
    """具体选项的 type / range / default / choices 解析。"""

    def test_deband_iterations(self):
        entry = OPTIONS["deband-iterations"]
        self.assertEqual(entry["type"], "Integer")
        self.assertEqual(entry["range"], "0 to 16")
        self.assertEqual(entry["default"], "1")
        self.assertFalse(entry["deprecated"])
        self.assertTrue(entry["zh_desc"])
        self.assertIn("色带", entry["zh_desc"])
        self.assertEqual(entry["zh_sig"], "--deband-iterations=<0..16>")
        self.assertEqual(entry["group"], "GPU渲染选项")

    def test_scale(self):
        entry = OPTIONS["scale"]
        self.assertEqual(entry["type"], "Choice")
        self.assertEqual(entry["default"], "lanczos")
        self.assertGreaterEqual(len(entry["choices"]), 20)
        self.assertIn("bilinear", entry["choices"])
        self.assertIn("lanczos", entry["choices"])
        self.assertIn("缩放", entry["zh_desc"])

    def test_hwdec(self):
        entry = OPTIONS["hwdec"]
        self.assertEqual(entry["type"], "String list")
        self.assertEqual(entry["default"], "no")
        self.assertTrue(entry["zh_desc"])
        self.assertIn("硬解码", entry["zh_desc"])

    def test_slang(self):
        entry = OPTIONS["slang"]
        self.assertEqual(entry["type"], "String list")
        self.assertEqual(entry["default"], "")
        self.assertEqual(entry["choices"], [])
        self.assertIn("字幕轨", entry["zh_desc"])
        self.assertEqual(entry["group"], "轨道选择")

    def test_flag_and_range_defaults(self):
        self.assertEqual(OPTIONS["access-references"]["type"], "Flag")
        self.assertEqual(OPTIONS["access-references"]["default"], "yes")
        self.assertEqual(OPTIONS["ad-lavc-ac3drc"]["range"], "0 to 6")
        self.assertEqual(OPTIONS["ad-lavc-ac3drc"]["default"], "0")
        self.assertEqual(OPTIONS["ad-queue-max-secs"]["range"], "0 to any")

    def test_deprecated_flag(self):
        self.assertTrue(OPTIONS["focus-on-open"]["deprecated"])
        self.assertFalse(OPTIONS["scale"]["deprecated"])


class TestSubOptions(unittest.TestCase):
    """子选项必须收在所属顶层选项里，不能混进顶层。"""

    def test_sub_option_not_top_level(self):
        self.assertNotIn("ad-lavc-o-add", OPTIONS)
        self.assertIn("ad-lavc-o", OPTIONS)

    def test_sub_option_listed_under_parent(self):
        subs = OPTIONS["ad-lavc-o"]["sub_options"]
        self.assertIn("--ad-lavc-o-add", subs)
        self.assertIn("--ad-lavc-o-append", subs)
        self.assertEqual(len(subs), 6)

    def test_multiple_parents(self):
        self.assertEqual(len(OPTIONS["alang"]["sub_options"]), 8)
        self.assertEqual(len(OPTIONS["hwdec"]["sub_options"]), 8)
        self.assertIn("--alang-add", OPTIONS["alang"]["sub_options"])

    def test_sub_options_are_double_dash_and_not_top_level(self):
        total = 0
        for key, entry in OPTIONS.items():
            for sub in entry["sub_options"]:
                total += 1
                self.assertTrue(sub.startswith("--"), sub)
                self.assertNotIn(sub[2:], OPTIONS, "%s 混进了顶层" % sub)
        self.assertGreaterEqual(total, 300)


class TestZhText(unittest.TestCase):
    """中文说明的清洗质量。"""

    def test_no_rst_markup_left(self):
        bad = []
        for key, entry in OPTIONS.items():
            desc = entry["zh_desc"]
            if not desc:
                continue
            for token in BAD_MARKUP:
                if token in desc:
                    bad.append((key, token))
            if re.match(r"^\s*\.\.\s+\w+::", desc):
                bad.append((key, "指令块"))
        self.assertEqual(bad, [], "中文说明里有 RST 残留：%s" % bad[:10])

    def test_length_limit(self):
        too_long = [k for k, v in OPTIONS.items() if len(v["zh_desc"]) > 600]
        self.assertEqual(too_long, [])
        self.assertGreater(len(OPTIONS["scale"]["zh_desc"]), 50)

    def test_missing_zh_is_empty_string(self):
        missing = [k for k, v in OPTIONS.items() if v["zh_desc"] == ""]
        self.assertTrue(missing, "应当存在少量对不上中文的选项")
        for key in missing:
            self.assertIsInstance(OPTIONS[key]["zh_desc"], str)


class TestSearch(unittest.TestCase):
    """中文 / 英文模糊搜索。"""

    def test_search_by_chinese(self):
        hits = search(DB, "色带")
        self.assertTrue(hits)
        keys = [h["key"] for h in hits]
        self.assertIn("deband-iterations", keys)
        self.assertTrue(any(k.startswith("deband") for k in keys))

    def test_search_by_key(self):
        hits = search(DB, "deband")
        keys = [h["key"] for h in hits]
        self.assertIn("deband", keys[:2], "选项名精确命中应排最前")

    def test_search_case_insensitive_and_dedup(self):
        upper = [h["key"] for h in search(DB, "HWDEC")]
        lower = [h["key"] for h in search(DB, "hwdec")]
        self.assertEqual(upper, lower)
        self.assertEqual(upper[0], "hwdec")
        self.assertEqual(len(upper), len(set(upper)))

    def test_search_limit(self):
        self.assertEqual(len(search(DB, "字幕", limit=3)), 3)
        self.assertLessEqual(len(search(DB, "字幕", limit=3)),
                             len(search(DB, "字幕")))

    def test_search_empty_and_miss(self):
        self.assertEqual(search(DB, ""), [])
        self.assertEqual(search(DB, "   "), [])
        self.assertEqual(search(DB, None), [])
        self.assertEqual(search(DB, "这个词一定不存在zzz"), [])

    def test_search_accepts_empty_db(self):
        self.assertEqual(search({"options": {}, "groups": [], "meta": {}}, "x"), [])


class TestJsonRoundTrip(unittest.TestCase):
    """JSON 序列化 / 读取。"""

    def test_dump_load_round_trip(self):
        text = json.dumps(DB, ensure_ascii=False, indent=2)
        self.assertIn("色带", text, "JSON 应保留中文字面量")
        self.assertNotIn("\\u", text[:2000])
        self.assertEqual(json.loads(text), DB)

    @unittest.skipUnless(BUILT_FROM_SOURCE,
                         "这一项比的是「重建结果 == 磁盘上的 JSON」，"
                         "没有中文手册源就无从重建 —— 缺件跳过，不算失败")
    def test_generated_json_file_matches(self):
        self.assertTrue(DB_PATH.exists(), "先运行 tools/build.py options-db")
        with open(DB_PATH, "r", encoding="utf-8") as fh:
            on_disk = json.load(fh)
        self.assertEqual(on_disk["meta"]["count"], META["count"])
        self.assertEqual(on_disk["groups"], GROUPS)
        self.assertEqual(set(on_disk["options"]), set(OPTIONS))
        self.assertEqual(on_disk["options"]["scale"], OPTIONS["scale"])

    def test_load_db_reads_file(self):
        loaded = load_db()
        # meta 会因为「滤掉命令行专用选项」而多出 filtered / filtered_note 两个键，
        # 且 count 会被改写成滤完的真实条数（见下面的专门测试）。
        # with_zh 同理 —— 它原本是滤前统计的（726），滤完只剩 714，不同步就会让
        # 界面宣称一个它拿不出来的数字。所以这两个键都跳过逐项比对，
        # 改成下面按「滤完的集合」重新算一遍。
        for k, v in META.items():
            if k in ("count", "with_zh", "with_en"):
                continue
            self.assertEqual(loaded["meta"].get(k), v, k)
        self.assertEqual(loaded["meta"]["count"], len(loaded["options"]))
        self.assertEqual(loaded["meta"]["with_zh"],
                         sum(1 for v in loaded["options"].values() if v.get("zh_desc")),
                         "with_zh 必须跟滤完的集合一致，否则界面会说谎")
        self.assertEqual(loaded["meta"].get("with_en"),
                         sum(1 for v in loaded["options"].values() if v.get("en_desc")),
                         "with_en 必须跟滤完的集合一致")
        self.assertEqual(loaded["groups"], GROUPS)
        self.assertEqual(loaded["options"]["hwdec"], OPTIONS["hwdec"])

    def test_load_db_filters_cli_only_options(self):
        """`mpv --list-options` 里有几条标注 `[not in config files]` 的（--V / --{ / --} 等），
        它们只能用于命令行。写进 mpv.conf 没意义，所以读的时候滤掉。

        这条是拿官方手册反向核对时发现的：库里有 3 项在手册正文里找不到。
        """
        loaded = load_db()
        for k in ("V", "{", "}"):
            self.assertNotIn(k, loaded["options"], f"{k} 是命令行专用，不该出现在配置项里")
        on_disk = json.loads((ROOT / "data" / "mpv_options_zh.json").read_text(encoding="utf-8"))
        self.assertLess(len(loaded["options"]), len(on_disk["options"]),
                        "应当确实滤掉了一些")
        self.assertGreater(len(loaded["options"]), 800, "别把正常选项也滤了")
        self.assertEqual(loaded["meta"]["count"], len(loaded["options"]),
                         "meta.count 必须与滤完的条数一致，否则界面会报错数")
        self.assertIn("not in config files", loaded["meta"].get("filtered_note", ""))

    def test_is_config_option(self):
        self.assertFalse(options_db.is_config_option("V"))
        self.assertFalse(options_db.is_config_option("{", {"raw_sig": "Flag [not in config files]"}))
        self.assertTrue(options_db.is_config_option("vo"))
        self.assertTrue(options_db.is_config_option("scale", {"raw_sig": "Choice"}))

    def test_load_db_without_file_returns_empty_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            original = options_db.load_db
            options_db.reset_cache()  # 清掉缓存，否则会读到真实数据
            try:
                with mock.patch.object(options_db, "DB_PATH", missing):
                    empty = options_db.load_db()
            finally:
                options_db.load_db = original
                options_db.reset_cache()
        self.assertEqual(empty, {"options": {}, "groups": [], "meta": {}})


if __name__ == "__main__":
    unittest.main(verbosity=2)

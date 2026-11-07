# -*- coding: utf-8 -*-
"""后端双语上下文与 T14 各数据源的英文输出（T14）。

## 为什么需要这条测试

T14 的机制是「后端按请求语言直接返回对应文案」（webui/api.py dispatch 每请求
set_lang，core 各数据源经 T() 取词）。这套机制有三类会静默烂掉的点：

1. 线程上下文：dispatch 没设或设错，上一个请求的语言泄漏到下一个；
2. 翻译表与数据脱节：EN 表的 key 拼错 → 静默回退中文，界面不报错；
3. 括号/返回值形状：给 T() 包错括号会把 4 元组返回值变成嵌套 2 元组
   （2026-11-08 实测踩过，tests/test_lazyinstall 的 unpack 抓回来的）。

所以这里用**真的 dispatch**（与传输无关的那层）验每个数据源的 en 输出，
而不是直接调 core 函数——路由、查询参数、语言上下文三件事一起验。
"""
import unittest

from core import i18n
from core.i18n import T, get_lang, set_lang


class I18nContextTest(unittest.TestCase):
    def setUp(self):
        set_lang(None)               # 别的测试类可能在线程上留了语言

    def tearDown(self):
        set_lang(None)

    def test_default_is_chinese(self):
        self.assertEqual(get_lang(), "zh")

    def test_set_en_and_back(self):
        set_lang("en")
        self.assertEqual(get_lang(), "en")
        set_lang(None)
        self.assertEqual(get_lang(), "zh")

    def test_unknown_lang_falls_back_to_chinese(self):
        set_lang("fr")
        self.assertEqual(get_lang(), "zh")

    def test_t_picks_by_lang(self):
        self.assertEqual(T("苹果", "apple"), "苹果")
        set_lang("en")
        self.assertEqual(T("苹果", "apple"), "apple")

    def test_thread_isolation(self):
        import threading

        result = []

        def worker():
            result.append(get_lang())

        set_lang("en")
        th = threading.Thread(target=worker)
        th.start()
        th.join()
        # threading.local：子线程看不到主线程的 en
        self.assertEqual(result, ["zh"])
        self.assertEqual(get_lang(), "en")


class BackendEnglishOutputTest(unittest.TestCase):
    """走真的 dispatch：en 请求返回英文，无 lang 回中文。"""

    def setUp(self):
        import webui.api as api
        self.api = api
        set_lang(None)               # dispatch 会把语言写进当前线程，先复位

    def tearDown(self):
        set_lang(None)               # 泄漏给下一个测试类就是假红/假绿的来源

    def dispatch(self, path, query=None, body=None, method="GET"):
        req = self.api.Request(path=path, method=method,
                               query=dict(query or {}), body=body)
        return self.api.dispatch(req).payload

    def test_options_native_label_en(self):
        d = self.dispatch("/api/options", query={"lang": "en"})
        first = d["native"][0]
        self.assertEqual(first["label"], "Dither depth")
        self.assertTrue(d["groups"][0].isascii(), f"groups 应为英文：{d['groups'][:2]}")

    def test_options_default_chinese(self):
        d = self.dispatch("/api/options")
        self.assertEqual(d["native"][0]["label"], "抖动色深")

    def test_options_core_label_en(self):
        d = self.dispatch("/api/options", query={"lang": "en"})
        core = {x["key"]: x for x in d["core"]}
        self.assertEqual(core["vo"]["label"], "Video output")

    def test_presets_note_en(self):
        out = self.dispatch("/api/presets", query={"lang": "en"})
        for x in out:
            self.assertTrue(x["note"].startswith(("Anime", "Live action")),
                            f"预设 note 应为英文：{x['note'][:40]}")

    def test_combos_name_en(self):
        d = self.dispatch("/api/combos", query={"lang": "en"})
        names = [c["name"] for c in d["combos"]]
        self.assertIn("Sharpest base", names)

    def test_downloads_items_en(self):
        d = self.dispatch("/api/downloads", query={"lang": "en", "target": "N∗exist"})
        # 目标目录不存在也返回 kinds——kind 标签应已是英文
        kinds = [k["label"] for k in d["kinds"]]
        self.assertTrue(all(k.isascii() for k in kinds), str(kinds))

    def test_keys_defaults_label_en(self):
        from core.keys import load_defaults
        set_lang("en")
        try:
            rows = load_defaults()
            labels = {r["label"] for r in rows}
            self.assertNotIn("mpv 内置", labels)
            self.assertIn("mpv built-in", labels)
        finally:
            set_lang(None)


if __name__ == "__main__":
    unittest.main()

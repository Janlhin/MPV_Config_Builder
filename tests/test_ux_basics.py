# -*- coding: utf-8 -*-
"""全站 UX 基线：9 个页面共有的头部/可访问性/链接不能悄悄烂掉。

2026-11-17 走查发现 9 个页面都没有 viewport，窗口缩小时布局不会按设备宽度收敛；
这类问题在桌面宽屏看不出来，只能靠静态检查兜住。
"""
import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"
PAGES = ("index", "basic", "advanced", "expert", "analyze",
         "keys", "downloads", "guide", "hell")


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.buttons = []
        self.hrefs = []
        self._btn = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "button":
            self._btn = {"text": "", "aria": attrs.get("aria-label", ""),
                         "title": attrs.get("title", "")}
        if tag == "a" and attrs.get("href"):
            self.hrefs.append(attrs["href"])

    def handle_data(self, data):
        if self._btn is not None:
            self._btn["text"] += data

    def handle_endtag(self, tag):
        if tag == "button" and self._btn is not None:
            self.buttons.append(self._btn)
            self._btn = None


def _scan(name):
    text = (STATIC / f"{name}.html").read_text(encoding="utf-8")
    s = _Scan()
    s.feed(text)
    return text, s


class UxBaselineTest(unittest.TestCase):
    def test_viewport_on_every_page(self):
        for name in PAGES:
            text, _ = _scan(name)
            self.assertIn('name="viewport"', text, f"{name}.html 缺 viewport")

    def test_document_title(self):
        for name in PAGES:
            text, _ = _scan(name)
            self.assertRegex(text, r"<title[ >]", f"{name}.html 缺 <title>")

    def test_no_duplicate_ids(self):
        for name in PAGES:
            _, s = _scan(name)
            dup = [i for i, n in Counter(s.ids).items() if n > 1]
            self.assertEqual(dup, [], f"{name}.html 有重复 id：{dup}")

    def test_buttons_have_accessible_name(self):
        for name in PAGES:
            _, s = _scan(name)
            bare = [b for b in s.buttons
                    if not (b["text"].strip() or b["aria"] or b["title"])]
            self.assertEqual(bare, [], f"{name}.html 有无名下文的按钮：{bare}")

    def test_internal_links_exist(self):
        for name in PAGES:
            _, s = _scan(name)
            for href in s.hrefs:
                clean = href.split("?")[0].split("#")[0]
                if clean.endswith(".html"):
                    self.assertTrue((STATIC / clean).is_file(),
                                    f"{name}.html 链到不存在的 {href}")


if __name__ == "__main__":
    unittest.main()

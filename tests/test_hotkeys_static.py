# -*- coding: utf-8 -*-
"""快捷键映射表的 rot 守护（R-28 决策 4）。

## 为什么需要这条测试

快捷键层的主操作映射表（api.js 的 `HOTKEY_PRIMARY`）按 `body[data-page]`
把页面映射到按钮选择器。这种表**天生会烂**：哪天某页 HTML 改了按钮 id，
映射就静默失效 —— 按了 Ctrl+S 什么都不发生，而且没有任何报错。
`verify.py hotkeys`（实机）能逮住它，但要本机有 Edge/Chrome 才会跑。

这里补**零依赖的静态检查**：直接解析两张源文件对账。跑测试就会带上。

## 判据边界（窄才不会误报）

* 只对账 `#id` 形状的选择器与 HTML 里的 `id="..."`，不做别的猜测；
* 「危险动作不绑全局键」是 R-28 的裁决，不是实现细节 —— 表里**不许出现**
  hell / downloads / index / guide，谁"好心"加回来这条会红。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "webui" / "static"

# api.js 里 HOTKEY_PRIMARY = { ... }; 这一整块
TABLE_RE = re.compile(r"HOTKEY_PRIMARY\s*=\s*\{(.*?)\}", re.S)
# 表里的条目：页名: '选择器'（允许单引号字符串）
ENTRY_RE = re.compile(r"(\w+)\s*:\s*'([^']+)'")

# R-28 决策 3：危险动作与无主操作页面不映射 Ctrl+S
FORBIDDEN_PAGES = {"hell", "downloads", "index", "guide"}


def parse_table():
    """从 api.js 抽出 {page: selector}。解析不到就断言失败，不静默跳过。"""
    src = (STATIC / "api.js").read_text(encoding="utf-8")
    m = TABLE_RE.search(src)
    if not m:
        raise AssertionError("api.js 里找不到 HOTKEY_PRIMARY 表（被改名/挪走了？同步改本测试）")
    return dict(ENTRY_RE.findall(m.group(1)))


class HotkeyPrimaryTableTest(unittest.TestCase):
    def setUp(self):
        self.table = parse_table()

    def test_table_not_empty(self):
        """表至少要有一条映射 —— 整块被删掉/清空也算 rot。"""
        self.assertGreaterEqual(len(self.table), 4,
                                f"映射表只剩 {len(self.table)} 条，疑似被清空：{self.table}")

    def test_every_selector_exists_in_its_page(self):
        """每个选择器的 id 必须在对应 HTML 里真实存在（防改 id 静默失效）。"""
        for page, sel in sorted(self.table.items()):
            html = STATIC / f"{page}.html"
            assert html.is_file(), f"{page}.html 不存在，但映射表里有它"
            m = re.match(r"^#([A-Za-z][\w-]*)$", sel)
            assert m, f"{page} 的选择器 {sel!r} 不是 #id 形状 —— 本测试只守 #id，请同步扩展判据"
            ids = set(re.findall(r'id="([^"]+)"', html.read_text(encoding="utf-8")))
            self.assertIn(m.group(1), ids,
                          f"{page}.html 里没有 id={m.group(1)!r}：映射表与 HTML 脱节了")

    def test_page_marker_matches(self):
        """表的键必须是页面自己的 data-page —— 键写错 = 永远命中不了。"""
        for page in self.table:
            html = (STATIC / f"{page}.html").read_text(encoding="utf-8")
            self.assertIn(f'data-page="{page}"', html,
                          f"{page}.html 的 body data-page 与映射表键不一致")

    def test_dangerous_pages_have_no_binding(self):
        """危险动作不绑全局键（R-28 决策 3）：谁加回来这条就会红。"""
        leaked = FORBIDDEN_PAGES & set(self.table)
        self.assertEqual(leaked, set(),
                         f"这些页面按 R-28 不许映射 Ctrl+S（危险动作不降触发成本）：{sorted(leaked)}")


if __name__ == "__main__":
    unittest.main()

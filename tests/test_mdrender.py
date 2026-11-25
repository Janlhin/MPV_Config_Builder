# -*- coding: utf-8 -*-
"""极简 Markdown 渲染器测试（它渲染的是仓库里真实的中文文档）。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.mdrender import extract_title, to_html     # noqa: E402


class MdRenderTest(unittest.TestCase):
    def test_headings_and_hr(self):
        out = to_html("# 标题\n\n## 二级\n\n---\n")
        self.assertIn("<h1>标题</h1>", out)
        self.assertIn("<h2>二级</h2>", out)
        self.assertIn("<hr>", out)

    def test_lists(self):
        out = to_html("- 一\n- 二\n\n1. 甲\n2. 乙\n")
        self.assertIn("<ul>", out)
        self.assertIn("<li>一</li>", out)
        self.assertIn("<ol>", out)
        self.assertIn("<li>甲</li>", out)
        self.assertLess(out.index("<ul>"), out.index("<ol>"))

    def test_fenced_code_not_escaped_twice(self):
        out = to_html("```ini\nvo=gpu-next   # 注释\n```\n")
        self.assertIn("<pre", out)
        self.assertIn("vo=gpu-next", out)
        self.assertNotIn("&amp;", out)

    def test_table(self):
        out = to_html("| 键 | 说明 |\n|---|---|\n| vo | 视频输出 |\n")
        self.assertIn("<table>", out)
        self.assertIn("<th>键</th>", out)
        self.assertIn("<td>视频输出</td>", out)

    def test_inline_markup(self):
        out = to_html("这是 `代码` 和 **粗体** 以及 [链接](https://mpv.io/manual/master/)。")
        self.assertIn("<code>代码</code>", out)
        self.assertIn("<strong>粗体</strong>", out)
        self.assertIn('href="https://mpv.io/manual/master/"', out)

    def test_script_tag_is_escaped(self):
        out = to_html("正常文字 <script>alert(1)</script>")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_blockquote(self):
        out = to_html("> 手册原文\n> 第二行\n")
        self.assertIn("<blockquote>", out)
        self.assertIn("手册原文", out)

    def test_extract_title(self):
        self.assertEqual(extract_title("# 入门指南\n\n正文"), "入门指南")
        self.assertEqual(extract_title("没有标题", "默认"), "默认")

    def test_real_docs_render(self):
        """仓库里这几份文档都要能渲染，且不残留 Markdown 标记。"""
        for name in ("user/zh-CN/getting-started.md",
                     "user/zh-CN/acknowledgments.md",
                     "user/zh-CN/shader-guide.md"):
            path = ROOT / "docs" / name
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            html = to_html(text)
            self.assertIn("<h1>", html, name)
            self.assertIn("<h2>", html, name)
            self.assertNotIn("```", html, name)
            self.assertGreater(len(html), 2000, name)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""R-26：「从零创建」与「改现有配置」两种语义的分离。

这一条几乎全在前端，所以测试分两部分：
  ① **结构检查** —— 三个页面都必须有模式开关、主按钮必须带 `data-primary`
     标记（否则切语义时文案/禁用状态不会跟着变）；同一动作不许有两个名字。
  ② **可测的行为** —— `disable`（取消勾选 → 注释掉原行）只在 edit 语义下
     才有意义，这件事后端必须扛得住（前端漏传就是空列表，等价于不注释）。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STATIC = ROOT / "webui" / "static"
# R-26 明确要求带模式开关的三页（地狱/体检/快捷键不参与写配置）
MODE_PAGES = ("basic.html", "advanced.html", "expert.html")


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


class ModeBarStructureTest(unittest.TestCase):
    def test_every_mode_page_has_the_switch(self):
        for name in MODE_PAGES:
            t = read(name)
            self.assertIn('data-mode="create"', t, f"{name} 缺「从零创建」按钮")
            self.assertIn('data-mode="edit"', t, f"{name} 缺「改现有配置」按钮")

    def test_state_pages_have_mode_seg_id(self):
        """加载 state.js 的页面靠 id=modeSeg 让 initModeBar 找到开关。"""
        for name in ("advanced.html", "expert.html"):
            self.assertIn('id="modeSeg"', read(name), name)

    def test_primary_buttons_are_marked(self):
        """主按钮必须带 data-primary，否则 renderModeBar 改不了它的文案/禁用态。"""
        for name in ("advanced.html", "expert.html"):
            t = read(name)
            btns = re.findall(r"<button[^>]*\bdata-primary\b[^>]*>", t)
            self.assertGreaterEqual(len(btns), 2,
                                    f"{name} 主按钮应有顶栏+预览卡两个，实际 {len(btns)}")
            # 顶栏那个要能被 renderModeBar 通过 id 定位；两个都要能被
            # querySelectorAll('[data-primary]') 选中
            self.assertIn('id="applyTop" data-primary', t, name)
            self.assertIn("data-primary", t)

    def test_apply_top_is_wired(self):
        """顶栏主按钮必须接上动作 —— 光有标记不接线，点了没反应。"""
        for name in ("advanced.html", "expert.html"):
            t = read(name)
            self.assertTrue("applyTop" in t and "applyConfig" in t,
                            f"{name} 顶栏主按钮没接 applyConfig")

    def test_one_action_one_name(self):
        """同一个动作不许两个名字：不许再出现「应用修改」当按钮文案。"""
        for name in MODE_PAGES:
            t = read(name)
            self.assertNotIn(">✅ 应用修改<", t,
                             f"{name} 还有「应用修改」按钮 —— R-26 要求统一文案")

    def test_mode_bar_script_present(self):
        js = read("state.js")
        for fn in ("isEditMode", "setMode", "renderModeBar", "initModeBar",
                   "primaryLabel", "blockedByNoSource"):
            self.assertIn(f"function {fn}", js, f"state.js 缺 {fn}")

    def test_mode_is_persisted(self):
        """《路线图》要求 localStorage 记住上次选择。"""
        js = read("state.js")
        save = js[js.index("function saveLocal"):js.index("function loadLocal")]
        self.assertIn("mode: APP.mode", save, "saveLocal 没保存 mode")
        load = js[js.index("function loadLocal"):js.index("function loadLocal") + 700]
        self.assertIn("APP.mode", load, "loadLocal 没恢复 mode")

    def test_disable_only_collected_in_edit_mode(self):
        """R-26 第 3 条：`disable` 只在修改语义下收集。"""
        js = read("state.js")
        start = js.index("function clearOption")
        body = js[start:start + 600]
        self.assertIn("isEditMode()", body,
                      "clearOption 没有按语义判断就收集 disable")

    def test_edit_mode_defaults_to_merge(self):
        js = read("state.js")
        start = js.index("function setMode")
        body = js[start:start + 800]
        self.assertIn("'merge'", body, "edit 语义应默认合并写入")
        self.assertIn("'include'", body, "create 语义应默认独立文件")

    def test_basic_page_has_read_entry(self):
        """R-26 顺带修的毛病：基础模式原来有 merge 开关却没有读取入口。"""
        t = read("basic.html")
        self.assertIn('id="readBtn"', t, "基础模式缺「读取现有配置」入口")
        self.assertIn("readExisting", t)

    def test_page_scripts_parse(self):
        """内联脚本至少不能有括号不平衡这种低级问题。"""
        for name in MODE_PAGES:
            for block in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                                    read(name), re.S):
                for a, b in (("{", "}"), ("(", ")"), ("[", "]")):
                    self.assertEqual(block.count(a), block.count(b),
                                     f"{name} 里有不平衡的 {a}{b}")


class DisableSemanticsTest(unittest.TestCase):
    """后端对 disable 的处理：edit 语义下注释、create 语义下不传即不注释。"""

    def test_disable_comments_global_line(self):
        from core.writer import apply_state_to_lines
        lines = ["vo=gpu-next", "[p]", "scale=x"]
        new, changes = apply_state_to_lines(lines, {}, ["vo"])
        self.assertTrue(new[0].lstrip().startswith("#vo"), new)
        self.assertIn("vo: 已注释", changes)

    def test_empty_disable_is_noop(self):
        """create 语义下前端不收集 disable → 传空列表 → 一个字节都不该动。"""
        from core.writer import apply_state_to_lines
        lines = ["vo=gpu-next", "scale=spline36"]
        new, changes = apply_state_to_lines(lines, {}, [])
        self.assertEqual(new, lines)
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""字幕实时预览（R-2x）的测试。

预览本身是前端 JS，没法在 Python 里跑；所以这里守两件**能用 Python 证伪**的事：

  ① **颜色格式的结论是对的** —— mpv 的 8 位颜色是 `#AARRGGBB`（透明度在**最前**）。
     这条是从 `mpv --list-options` 的默认值反推出来的，不是猜的，所以要有测试钉住：
     哪天有人按 CSS 的直觉（`#RRGGBBAA`）去"修"它，这里会红。

  ② **预览依赖的选项都真的存在、且"从同一份数据渲染"** ——
     预览从 `APP.values` 读，配置也从 `APP.values` 写；只要这些 key 在参数表里，
     两边就不可能不一致（这正是 mpvconfigurator 翻车的地方：预览用 Qt 渲染、
     写盘用另一套格式）。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.options_db import load_db                                        # noqa: E402
from core.schema import NATIVE_OPTIONS, PARAMS                             # noqa: E402

STATIC = ROOT / "webui" / "static"
JS = (STATIC / "state.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


class ColorOrderEvidenceTest(unittest.TestCase):
    """mpv 的 8 位颜色是 `#AARRGGBB`（透明度在**最前**）—— 证据来自 mpv 自己的默认值。

    ⚠ 这一条我一开始判断反了：以为跟 CSS 一样是 RRGGBBAA。是本文件里那几个默认值
    把它证伪的，所以必须留成测试 —— 否则下次还会有人（包括我）想当然改回去。
    """

    def setUp(self):
        self.raw = (ROOT / "_mpv_options_raw.txt").read_text(encoding="utf-8")

    def _default(self, key):
        m = re.search(rf"^\s{{0,1}}--{re.escape(key)}\s+Color\s+\(default:\s*([^)]*)\)",
                      self.raw, re.M)
        return m.group(1).strip() if m else ""

    def test_sub_color_default_is_opaque_white(self):
        """sub-color 默认 #FFFFFFFF。

        · 按 #AARRGGBB：AA=FF 不透明 + RRGGBB=FFFFFF 白 → 不透明的白 ✅
        · 按 #RRGGBBAA：RRGGBB=FFFFFF 白 + AA=FF 不透明 → **也**说得通
        所以光看这一条分不出来，要靠下面的 sub-back-color。
        """
        d = self._default("sub-color")
        self.assertEqual(d, "#FFFFFFFF", f"默认值变了，得重新核对：{d}")

    def test_sub_back_color_default_proves_aa_comes_first(self):
        """sub-back-color 默认 #AF000000 —— 这一条能定案。

        · 按 #AARRGGBB：AA=AF（69% 不透明）+ 000000 黑 → 半透明黑底 ✅ 合理
        · 按 #RRGGBBAA：RRGGBB=AF0000 暗红 + AA=00 全透明 → 看不见的暗红 ❌
        字幕背景框默认就该是半透明黑，所以只能是最前那种解释。
        """
        d = self._default("sub-back-color")
        self.assertEqual(d, "#AF000000", f"默认值变了，得重新核对：{d}")
        self.assertEqual(d[1:3].lower(), "af", "AA 在最前")
        self.assertEqual(d[3:9].lower(), "000000", "RRGGBB 在后面 = 黑")

    def test_osd_selected_color_also_fits_aa_first(self):
        """再来一条旁证：osd-selected-color 默认 #FFFABD2F。

        · #AARRGGBB：FF 不透明 + FABD2F 橙黄 ✅（选中项高亮成橙黄很合理）
        · #RRGGBBAA：FFFABD 桃红 + 2F（18% 不透明）❌
        """
        d = self._default("osd-selected-color")
        if not d:
            self.skipTest("这份 dump 里没有 osd-selected-color")
        self.assertEqual(d[1:3].lower(), "ff")
        self.assertEqual(d[3:9].lower(), "fabd2f")

    def test_our_doc_note_says_alpha_is_first(self):
        """参数表里的说明必须写对顺序。"""
        meta = next((i for items in PARAMS.values() for i in items
                     if i[0] == "sub-color"), None)
        self.assertIsNotNone(meta, "sub-color 应当在核心层（字幕预览要用）")
        desc = meta[2]
        self.assertIn("#AARRGGBB", desc)
        self.assertIn("最前", desc, "要讲清透明度在最前两位")


class PreviewImplementationTest(unittest.TestCase):
    """预览实现的结构约束。"""

    def test_preview_function_exists(self):
        for fn in ("parseMpvColor", "updateSubPreview", "subVal"):
            self.assertIn(f"function {fn}", JS, f"state.js 缺 {fn}")

    def test_reads_from_app_values(self):
        """必须从 APP.values 读 —— 跟写进配置的是同一份数据。"""
        start = JS.index("function subVal")
        body = JS[start:start + 260]
        self.assertIn("APP.values", body,
                      "subVal 没从 APP.values 读，预览会与配置不一致")

    def test_hooked_into_state_change_not_into_inputs(self):
        """挂在 changed() 上（状态变化），而不是挂在输入控件的 oninput —— 
        这样"载入配置后没拖滑块"也会更新（mpvconfigurator 正是在这里丢的值）。"""
        start = JS.index("function changed()")
        body = JS[start:start + 320]
        self.assertIn("updateSubPreview()", body)

    def test_preview_text_differs_when_big(self):
        """它那个"字号很大时换句话"的小设计值得保留。"""
        self.assertIn("SUB_PREVIEW_TEXT", JS)

    def test_stage_css_exists(self):
        for cls in (".subpv-stage", ".subpv-sub", ".subpv-wrap"):
            self.assertIn(cls, CSS, f"style.css 缺 {cls}")

    def test_mounts_into_subtitle_group(self):
        """预览要挂在含字幕键的那一组下面。"""
        self.assertIn("SUB_PREVIEW_KEYS", JS)
        start = JS.index("var SUB_PREVIEW_KEYS")
        block = JS[start:start + 400]
        for key in ("sub-font", "sub-color", "sub-border-color", "sub-back-color"):
            self.assertIn(f"'{key}'", block, f"{key} 应当参与预览")

    def test_all_preview_keys_exist_in_params(self):
        """预览读的每个 key 都必须是真参数 —— 否则永远读到默认值。"""
        all_keys = ({i[0] for v in PARAMS.values() for i in v}
                    | {i[0] for v in NATIVE_OPTIONS.values() for i in v})
        start = JS.index("var SUB_PREVIEW_KEYS")
        block = JS[start:JS.index("};", start) + 2]
        keys = re.findall(r"'([a-z][a-z0-9-]*)'\s*:", block)
        self.assertTrue(keys, "没抽到 key")
        for k in keys:
            self.assertIn(k, all_keys, f"预览用的 {k} 不在参数表里")

    def test_alpha_warning_only_for_the_real_trap(self):
        """警告只在"8 位值看着像把透明度写到后面了"时出现，别到处刷。"""
        start = JS.index("const last2")
        block = JS[start:start + 460]
        self.assertIn("'ff'", block)
        self.assertIn("'00'", block)
        self.assertIn("st.colorWarn", block,
                      "警告文案走语言表键（st.colorWarn），不写死在 JS 里")

    def test_alpha_warning_text_states_the_right_order(self):
        """警告文案（两种语言）都必须说清 #AARRGGBB、透明度在最前两位。

        2026-10-14：文案从 state.js 挪进了 i18n.js 的 st.colorWarn（advanced 轮
        i18n 做深），判定位置随之迁移——用意不变：按 CSS 直觉把顺序"修"成
        RRGGBBAA 要能被发现。现在双语各一份，两份都要守。
        """
        i18n = (STATIC / "i18n.js").read_text(encoding="utf-8")
        warns = re.findall(r"'st\.colorWarn': '([^']*)'", i18n)
        self.assertEqual(len(warns), 2, "st.colorWarn 应当中英各一份")
        for w in warns:
            self.assertIn("AARRGGBB", w, "警告要说清正确顺序")
            self.assertIn("RRGGBBAA", w, "要点破那个错误写法")
        self.assertIn("最前", warns[0], "中文要讲'最前'")
        self.assertIn("first", warns[1], "英文要讲 first")


class SchemaPlacementTest(unittest.TestCase):
    """字幕预览要靠"这些项在进阶模式里就能改"，所以它们在核心层。"""

    CORE_KEYS = ("sub-font", "sub-color", "sub-border-size", "sub-border-color",
                 "sub-shadow-offset", "sub-back-color", "sub-pos")

    def test_subtitle_style_group_in_core(self):
        self.assertIn("字幕样式", PARAMS, "核心层应当有「字幕样式」组")
        keys = [i[0] for i in PARAMS["字幕样式"]]
        for k in self.CORE_KEYS:
            self.assertIn(k, keys, f"{k} 应当在核心层「字幕样式」里")

    def test_no_overlap_with_native(self):
        """挪到核心层之后，原生层不能再留一份（test_schema 也有这条，这里盯字幕）。"""
        native = {i[0] for v in NATIVE_OPTIONS.values() for i in v}
        for k in self.CORE_KEYS:
            self.assertNotIn(k, native, f"{k} 在两层里都有")

    def test_sub_margin_x_stays_native(self):
        """sub-margin-x 只影响左右边距，预览里看不出，故意留在完全体。"""
        native = {i[0] for v in NATIVE_OPTIONS.values() for i in v}
        self.assertIn("sub-margin-x", native)
        core = {i[0] for v in PARAMS.values() for i in v}
        self.assertNotIn("sub-margin-x", core)


if __name__ == "__main__":
    unittest.main()

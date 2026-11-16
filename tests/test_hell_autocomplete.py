# -*- coding: utf-8 -*-
"""地狱模式参数补全（待做 §〇 第 14 项 ①）的判据。

## 为什么要这一份

补全是**纯前端行为**，Python 跑不了那段 JS。所以这里守两侧：

* **静态结构**（`hell.html` 的源码）——零件少一个就是"点了没反应 / 按了没反应"，
  这类错在浏览器里往往连报错都没有（`tests/test_combo.py` 记过同样的教训）。
* **数据源本身**（`api_db_options`）——补全能不能给出 `scale`、`scale` 的取值里有没有
  `ewa_lanczos4sharpest`、bool 项是不是 `yes`/`no`，这些用真接口验，不靠印象。

真机行为（面板真的弹出来、`Tab` 真的替换文本）由 `verify.py ui` 在浏览器里断言。

## 判据边界

只认 hell 页自己的实现，不试图给共用层立规矩 —— 补全只服务这一页（见 `DECISIONS.md`
2026-11-16 条目）。所以断言写的是"这段能力在"，不是"所有页面都得这么写"。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from webui import server                                                   # noqa: E402

STATIC = ROOT / "webui" / "static"
HELL = (STATIC / "hell.html").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


def _function(name):
    """取出 hell.html 里某个函数的源码（到下一个 `function ` / 注释块为止）。"""
    m = re.search(rf"^(?:async )?function {re.escape(name)}\(", HELL, re.M)
    if not m:
        raise AssertionError(f"hell.html 里没有 {name}()（被改名/删了？同步改本测试）")
    rest = HELL[m.start():]
    nxt = re.search(r"\n(?:function |async function |/\* -{10,}|const )", rest[1:])
    return rest[:nxt.start() + 1] if nxt else rest


def _code_only():
    """剥掉 JS 注释。

    必须这么做：本文件要断言"页面里没有 <datalist"，而注释里恰恰要写它来解释
    为什么不用 —— 不剥注释的话，解释本身会把测试弄红（`test_combo.py` 踩过）。
    """
    s = re.sub(r"/\*.*?\*/", "", HELL, flags=re.S)
    return re.sub(r"^\s*//.*$", "", s, flags=re.M)


CODE = _code_only()


class TransportTest(unittest.TestCase):
    """界面里不许直接 fetch('/api/')：传输是可替换的（HTTP / stdio）。"""

    def test_uses_api_transport(self):
        self.assertIn("API.dbOptions(", HELL, "补全没走 API.dbOptions —— 传输层约定破了")
        self.assertNotIn("fetch('/api/", HELL)
        self.assertNotIn('fetch("/api/', HELL)

    def test_not_native_datalist(self):
        """原生 <datalist> 的气泡不在 DOM、不吃 CSS，深色主题下是白底大气泡。"""
        self.assertNotIn("<datalist", CODE)
        self.assertNotIn("list=", CODE)


class PartsPresentTest(unittest.TestCase):
    """面板、列表项、样式三处都得在 —— 少一处就是"弹不出来"或"弹出来是空白"。"""

    def test_panel_created_in_dom(self):
        self.assertIn("className = 'ac-pop'", HELL)
        self.assertIn("document.body.appendChild(acPop)", HELL,
                      "面板必须挂到 body：挂在卡片里会被后面的兄弟节点盖住")
        self.assertIn(".ac-pop", CSS)
        self.assertIn(".ac-item", CSS)

    def test_items_are_text_nodes_not_html(self):
        """候选文字用 textContent 写：拼 HTML 会让说明里的符号变成标签。"""
        self.assertIn("code.textContent = it.value", HELL)
        self.assertIn("desc.textContent = it.desc", HELL)

    def test_type_badge_uses_i18n_keys(self):
        """类型徽标复用已有词条（st.typeBool…），不新写中文。"""
        self.assertIn("st.typeBool", HELL)
        self.assertIn("I18N.t(AC_TYPE_KEYS[it.type])", HELL)


class CaretReplaceTest(unittest.TestCase):
    """补全只替换光标前那段 token，不动整段文本（否则撤销栈一整篇就没了）。"""

    def test_set_range_text(self):
        frame = _function("acAccept")
        self.assertIn("setRangeText(", frame)
        self.assertIn("ctx.start", frame)
        self.assertIn("ctx.end", frame)

    def test_context_uses_caret(self):
        frame = _function("acContext")
        self.assertIn("selectionStart", frame)
        self.assertIn("lastIndexOf('\\n')", frame, "取当前行要用换行位置，不能只看全文")


class KeyboardTest(unittest.TestCase):
    def test_keys(self):
        frame = _function("acKeydown")
        for key in ("ArrowDown", "ArrowUp", "Escape", "Tab", "Enter"):
            self.assertIn(key, frame, f"键盘操作少了 {key}")
        self.assertGreaterEqual(frame.count("preventDefault()"), 3,
                                "箭头/回车不拦默认，光标会跟着跑")

    def test_click_keeps_focus(self):
        """点候选项时先 preventDefault，否则 textarea 失焦 → 面板当场消失。"""
        frame = _function("acShow")
        self.assertIn("addEventListener('mousedown'", frame)
        self.assertIn("preventDefault()", frame)


class SkipContextTest(unittest.TestCase):
    """误弹一次比不弹更烦：注释、小节名、空 token 一律不补。"""

    def test_comment_and_profile_and_empty(self):
        frame = _function("acContext")
        self.assertIn("s[0] === '#'", frame)
        self.assertIn("s[0] === ';'", frame)
        self.assertIn("s[0] === '['", frame)
        self.assertIn("if (!token) return null", frame)


class AsyncSafetyTest(unittest.TestCase):
    def test_stale_response_dropped(self):
        frame = _function("acQuery")
        self.assertIn("acSeq", frame)
        self.assertIn("seq !== acSeq", frame, "晚回来的结果会把新面板盖掉")

    def test_debounced(self):
        frame = _function("acSchedule")
        self.assertIn("setTimeout(acQuery", frame)
        self.assertIn("clearTimeout(acTimer)", frame)

    def test_graceful_when_backend_absent(self):
        """静态模式/后端挂了：接口回 ok:false，页面必须静默，不是 undefined 报错。"""
        code = re.sub(r"//.*$", "", HELL, flags=re.M)
        self.assertGreaterEqual(code.count("r.ok === false"), 2,
                                "键名与取值两条路径都要判 ok:false")

    def test_value_completion_falls_back_to_choices(self):
        frame = _function("acValueList")
        self.assertIn("hit.options", frame)
        self.assertIn("hit.values", frame, "库里没给 options 时要用 choices")


class DataSourceTest(unittest.TestCase):
    """数据源核对：补全靠的就是这三条行为。"""

    def test_prefix_query_returns_scale_first(self):
        r = server.api_db_options({"q": "sca", "limit": 40})
        self.assertTrue(r.get("ok"), r)
        keys = [x["key"] for x in r["items"][:6]]
        self.assertTrue(keys, "前缀查询没有任何结果，补全等于空转")
        self.assertEqual(keys[0], "scale", f"前缀命中最前的不是 scale：{keys}")
        self.assertTrue(all(k.startswith("sca") for k in keys[:6]), keys)

    def test_scale_value_domain(self):
        r = server.api_db_options({"q": "scale", "limit": 6})
        exact = [x for x in r["items"] if x["key"] == "scale"][0]
        self.assertEqual(exact["type"], "enum")
        opts = exact["options"]
        self.assertGreaterEqual(len(opts), 20, f"scale 的取值域只有 {len(opts)} 个？")
        self.assertIn("ewa_lanczos4sharpest", opts)
        self.assertIn("spline36", opts)

    def test_bool_values_are_yes_no(self):
        r = server.api_db_options({"q": "deband", "limit": 3})
        exact = [x for x in r["items"] if x["key"] == "deband"][0]
        self.assertEqual(exact["type"], "bool")
        self.assertEqual(exact["values"], ["yes", "no"])


if __name__ == "__main__":
    unittest.main()

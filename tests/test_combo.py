# -*- coding: utf-8 -*-
"""候选值下拉（自绘组合框）的测试。

## 为什么会有这个东西

`sub-font` 这类项的特点是「有候选值，但也能自己填」。原来用
`<input list="...">` + `<datalist>` 实现，结果深色界面里弹出一个**白底大气泡**。

那个气泡不是页面的一部分：它由浏览器 UI 层绘制，不在 DOM 里，也不吃页面 CSS。
`color-scheme` 是唯一能影响它的旋钮，而在部分 Chromium 版本上对 datalist 无效。
所以改成自己画下拉 —— 输入框保留（自由填不能丢），候选列表用普通 DOM。

## 这里守什么

前端 JS 没法在 Python 里跑，所以只守**能用 Python 证伪**的结构约束：

  ① 老写法真的清干净了 —— 只要还留着 `list=` / `<datalist`，那个白气泡就会回来。
  ② 自绘下拉的每个零件都在（少一个就是"点了没反应"）。
  ③ 候选值走 `data-options` 落到 JS 属性上，且**选值走 input 事件**，
     不绕过 `onOptEvent` —— 绕过去就会出现"预览显示的值"和"真正写盘的值"不一致，
     正是 mpvconfigurator 翻车的那个坑。
  ④ 事件委托挂在 `document` 上，**不能**挂在选项容器上：
     容器每次切分区都会被 `innerHTML` 整块换掉，挂上去的监听会跟着一起没。
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.options_db import load_db                                        # noqa: E402
from webui import server                                                   # noqa: E402

STATIC = ROOT / "webui" / "static"
JS = (STATIC / "state.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


def _fn(name):
    """取出 state.js 里某个顶层函数的源码（到下一个顶层 function 或注释块为止）。"""
    m = re.search(rf"^function {re.escape(name)}\(", JS, re.M)
    if not m:
        raise AssertionError(f"state.js 里没有 {name}()")
    rest = JS[m.start():]
    nxt = re.search(r"\n(?:function |/\* -{10,})", rest[1:])
    return rest[:nxt.start() + 1] if nxt else rest


def _code_only():
    """剥掉 JS 注释。

    必须这么做：本文件要断言"源码里不再有 <datalist"，但**注释里**恰恰要写
    `<datalist>` 来解释为什么不用它 —— 不剥注释的话，解释本身会把测试弄红。
    """
    s = re.sub(r"/\*.*?\*/", "", JS, flags=re.S)     # 块注释
    return re.sub(r"^\s*//.*$", "", s, flags=re.M)   # 行注释


CODE = _code_only()


class NativeDatalistGoneTest(unittest.TestCase):
    """① 老写法必须真的清干净 —— 留着就还是白气泡。"""

    def test_no_datalist_tag_is_rendered(self):
        # 注释里提到 datalist 是可以的（在讲为什么不用它），但不能有真的标签
        self.assertNotIn("<datalist", CODE, "还在渲染 <datalist>，白底大气泡会回来")

    def test_no_input_list_attribute(self):
        self.assertNotIn('list="${esc(dlid)}"', CODE)
        self.assertNotIn("input list=", CODE)
        self.assertNotIn("list=", CODE, "还有 list= 属性？那还是原生气泡")

    def test_comment_still_explains_why(self):
        """剥注释是为了断言代码；但那条"为什么不用 datalist"的解释得留着。"""
        self.assertIn("datalist", JS)
        self.assertIn("气泡", JS)

    def test_optrow_does_not_build_datalist_id(self):
        row = _fn("optRow")
        self.assertNotIn("dlid", row, "optRow 还在拼 datalist 的 id")


class ComboPartsTest(unittest.TestCase):
    """② 自绘下拉的零件一个都不能少。"""

    def test_required_functions_exist(self):
        for fn in ("closeCombo", "placeCombo", "comboHighlight", "comboPick",
                   "comboRender", "openCombo", "comboKeydown", "initCombo"):
            self.assertIn(f"function {fn}", JS, f"state.js 缺 {fn}()")

    def test_optrow_renders_combo_parts(self):
        row = _fn("optRow")
        self.assertIn('class="combo"', row)
        self.assertIn('data-role="combo-toggle"', row)
        self.assertIn("data-options=", row,
                      "候选值没写进 data-options，下拉就是空的")

    def test_options_are_read_back_into_js_property(self):
        """data-* 只能存字符串，过滤时不该反复 JSON.parse。"""
        mnt = _fn("mountOptions")
        self.assertIn("JSON.parse", mnt)
        self.assertIn("_options", mnt)

    def test_css_covers_the_popup(self):
        for cls in (".combo ", ".combo-pop", ".combo-item", ".combo-arrow",
                    ".combo-empty", ".combo-item.active"):
            self.assertIn(cls, CSS, f"style.css 缺 {cls}")
        # 面板要能压住后面的选项行
        pop = CSS[CSS.index(".combo-pop"):]
        self.assertIn("z-index", pop[:400], "面板没设 z-index，会被后面的行盖住")

    def test_popup_mounted_on_body_not_inside_row(self):
        """挂在行内会被 `.opt { position: relative }` 的兄弟行叠住。"""
        opener = _fn("openCombo")
        self.assertIn("document.body.appendChild", opener)
        self.assertIn("combo-pop", opener)


class WiringTest(unittest.TestCase):
    """④ 委托位置：挂 document，别挂会被换掉的容器。"""

    def test_delegation_is_on_document(self):
        init = _fn("initCombo")
        self.assertIn("document.addEventListener", init)
        self.assertNotIn("getElementById", init,
                         "别把委托挂在具体容器上 —— 它会被 innerHTML 换掉")
        self.assertNotIn("comboWired = true;\n  //", init)

    def test_document_is_a_stable_choice(self):
        """说明为什么：选项区宿主确实是每次 render() 整块重建的。

        这条同时是一道"提醒" —— 哪天 advanced.html 不再重建容器了，
        这个理由才失效；在那之前挂 document 是必要且正确的。
        """
        adv = (STATIC / "advanced.html").read_text(encoding="utf-8")
        self.assertIn("host.innerHTML", adv,
                      "选项区宿主不再整体重建了？那可以回来重新审视挂载点")

    def test_init_waits_for_body_to_exist(self):
        """绑定要等 `document.body` 存在。

        state.js 在 `<head>` 里同步加载，脚本执行时 `document.body` **还是 null**；
        而面板要 `document.body.appendChild(...)`。不等的话"聚焦 / 输入 → 开下拉"
        全线静默失败（面板建出来了但没地方挂），页面看起来就是"点了没反应"。
        """
        self.assertIn("document.readyState", JS)
        self.assertIn("'loading'", JS)
        self.assertIn("initCombo", JS)
        # 不能在顶层直接裸跑
        self.assertNotIn("\ninitCombo();", JS,
                         "顶层直接跑了：那时 document.body 还是 null")

    def test_popup_appends_to_body(self):
        self.assertIn("document.body.appendChild", _fn("openCombo"))

    def test_escape_is_consumed_before_drawer(self):
        """Esc 要先关下拉，不能一路冒到抽屉那边顺手把抽屉也关了。"""
        init = _fn("initCombo")
        self.assertIn("stopPropagation", init)
        self.assertIn("true)", init, "要用捕获阶段才能抢在抽屉前面")

    def test_keyboard_navigation_supported(self):
        kd = _fn("comboKeydown")
        for key in ("ArrowDown", "ArrowUp", "Enter", "Escape", "Tab"):
            self.assertIn(key, kd, f"键盘少了 {key}")


class ValuePathTest(unittest.TestCase):
    """③ 选中的值必须走 onOptEvent —— 值的唯一入口，别绕过去。"""

    def test_pick_dispatches_input_event(self):
        pick = _fn("comboPick")
        self.assertIn("dispatchEvent", pick)
        self.assertIn("bubbles: true", pick,
                      "不冒泡就到不了 onOptEvent")

    def test_pick_uses_the_clicked_item_value_not_the_input(self):
        """值要从**被点中的那一项**来。

        ⚠ 原来读的是 `input.value`。可输入框里往往正是过滤关键词
        （敲了 `Wen` 再点 `LXGW WenKai Lite`），于是存进去的是 `Wen` ——
        一个根本不是候选值的字符串，界面上还显示"选好了"。
        这是实机点出来的，不是想出来的。
        """
        pick = _fn("comboPick")
        self.assertIn("input.value = v", pick)
        # 不能拿输入框的旧内容当选中值
        self.assertNotIn("input.value = input.value", pick)
        # 面板项传的是自己那一项的文本
        render = _fn("comboRender")
        self.assertIn("comboPick(s)", render,
                      "面板项必须把自己的值传给 comboPick")

    def test_pick_captures_input_before_closing(self):
        """`closeCombo()` 会把 comboInput 置空 —— 必须先抓在手里再用。

        顺序写反的现象是「点了候选完全没反应」，且不抛任何错，极难查。
        这里取**调用**的位置，不是注释里提到 `closeCombo()` 的位置。
        """
        pick = _fn("comboPick")
        cap = pick.index("const input = comboInput")
        call = re.search(r"^\s*closeCombo\(\);", pick, re.M)
        self.assertIsNotNone(call, "comboPick 里没有调用 closeCombo()")
        self.assertLess(cap, call.start(), "先把 input 抓下来，再关面板")

    def test_pick_closes_before_dispatching(self):
        """关闭要在派发事件**之前**。

        因为 onOptEvent → changed() 会触发下一次渲染；等派发完再关，
        面板会挂在 body 上赖着不走（和页面脱节了，但看起来还在）。
        """
        pick = _fn("comboPick")
        first_close = pick.index("closeCombo()")
        dispatch = pick.index("dispatchEvent")
        self.assertLess(first_close, dispatch,
                        "先关面板，再派发（否则选完面板不消失）")

    def test_pick_guards_against_reopen(self):
        """派发的 input 会命中 openCombo，等于"刚关就又开" —— 要挡掉。"""
        pick = _fn("comboPick")
        self.assertIn("_noReopen", pick)
        init = _fn("initCombo")
        self.assertIn("_noReopen", init,
                      "initCombo 的 input 处理没认这个标记，面板会被弹回来")

    def test_pick_does_not_refocus(self):
        """别在最后 input.focus()：focusin 会把刚收起的面板又开出来。"""
        pick = _fn("comboPick")
        tail = pick[pick.rindex("closeCombo()"):]
        self.assertNotIn("focus()", tail, "收尾不要再 focus，会触发 focusin 重开")

    def test_pick_does_not_touch_app_state_directly(self):
        """直接 setOption 会跳过校验 / 预览 / 冲突体检。"""
        pick = _fn("comboPick")
        self.assertNotIn("setOption(", pick)
        self.assertNotIn("APP.values", pick)

    def test_pick_checks_the_row_when_unchecked(self):
        """未勾选时值控件是藏着的，点候选本身就等于"要这一项"。

        不自动勾选的话，onOptEvent 会因为复选框没勾直接 return ——
        用户点了候选什么都不发生，还得回头猜"是不是要先勾左边那个框"。
        """
        pick = _fn("comboPick")
        self.assertIn("wasOn", pick)
        self.assertIn("box.checked = true", pick)
        self.assertIn("showComboRow", pick)

    def test_onopt_event_still_handles_input(self):
        """onOptEvent 是靠 data-role="value" 认输入框的，组合框里也是这个 role。"""
        row = _fn("optRow")
        self.assertIn('data-role="value"', row)
        self.assertIn("role === 'value'", JS)


class ClickOrderTest(unittest.TestCase):
    """捕获 vs 冒泡的顺序坑（踩了两次，留成测试）。

    面板项的点击处理走**冒泡**（每项自己的 click），而 initCombo 里的委托是
    **捕获**。捕获一定先跑，所以 document 的"点别处就收起"如果不排除面板内部，
    就会先把面板关掉、comboInput 置空，然后项自己的 handler 才跑 —— 拿不到
    input，什么都不做。现象：点候选完全没反应，控制台一片安静。
    """

    def test_document_click_ignores_clicks_inside_the_panel(self):
        init = _fn("initCombo")
        self.assertIn("comboPop.contains(ev.target)", init,
                      "没排除面板内部：捕获会先关掉面板，点击就丢了")
        # 而且要在处理 toggle 之前就 return
        guard = init.index("comboPop.contains(ev.target)")
        toggle = init.index("combo-toggle")
        self.assertLess(guard, toggle, "排除判断要在最前面")

    def test_markup_does_not_use_native_select_for_free_form(self):
        """自由填的项不能用 select（不然又锁死在几个示例值里）。"""
        row = _fn("optRow")
        self.assertIn("!open && options.length", row)
        self.assertIn("<select", row)

    def test_combo_wrapper_is_hidden_together_with_the_input(self):
        """未勾选时**整个 .combo 外壳**要一起藏。

        只藏 input 的话，外壳还在、input 的 rect 全是 0，
        于是面板按 (0,0) 定位飘到页面左上角 —— 真机上就是这么飘的。
        """
        self.assertIn('.opt:not(.on) .opt-head .right .combo', CSS,
                      "style.css 没把 .combo 外壳一起隐藏")
        self.assertIn('.combo.show', CSS, "缺少临时可见态（自动勾选时要用）")

    def test_options_come_from_the_real_api(self):
        """下拉里的候选值 = `/api/options` 每一项的 `options` 字段。

        走**真的接口函数**（`server.api_options()`）而不是我自己猜的库结构 ——
        我第一版就是猜的（以为库里的字段叫 `options`，实际叫 `choices`），
        于是测试红了而代码是对的。测试要断言真实契约，不能断言我的记忆。
        """
        core = server.api_options()["core"]
        self.assertTrue(core, "核心层一个选项都没有？")
        for it in core:
            self.assertIn("options", it, f"{it['key']} 没带 options，下拉会是空的")
            self.assertIn("open", it, f"{it['key']} 没带 open，界面不知道该不该拦值")
            self.assertIsInstance(it["options"], list)

    def test_open_and_options_are_independent(self):
        """`open` 决定"能不能自己敲"，`options` 只是候选 —— 两者不是一回事。

        这条正是当初那个 bug：把"有没有建议值"当成了"能不能自由填"，
        于是 `geometry` / `sub-font` 被锁死在下拉里。
        """
        core = server.api_options()["core"]
        free_with_options = [it for it in core if it["open"] and it["options"]]
        closed = [it for it in core if not it["open"] and it["options"]]
        self.assertTrue(free_with_options,
                        '没有"能自由填、又给了候选"的项了？那组合框白做了')
        self.assertTrue(closed, '没有封闭枚举项了？那原生 select 那条路就没用了')

    def test_open_with_options_only_comes_from_curated_suggestions(self):
        """**带候选值的自由填项，候选只可能来自精选层的建议。**

        mpv 的类型模型就是这样：
          · `Choice` → 库里自带取值表，一定封闭 → 渲染成 select
          · `String` / `Float` / `Integer` … → 库里没有取值表，一定自由填
        所以 `open=True 且 options 非空` 只发生在"库里是自由类型 + 精选层给了
        建议值"的项上。全量库（完全体那 813 条）没有精选建议，
        因此**完全体里不会有带候选值的组合框** —— 这是数据决定的，不是缺陷。

        把这条钉住，免得以后有人看到"完全体下拉是空的"就去硬塞建议值，
        或者反过来以为 combo 没生效。
        """
        from core.options_db import load_db
        db = load_db()["options"]
        enum_like = ("choice", "choices", "flag")
        odd = []
        for key, meta in db.items():
            if not isinstance(meta, dict):
                continue
            choices = [c for c in (meta.get("choices") or []) if str(c).strip()]
            typ = str(meta.get("type") or "").strip().lower()
            if choices and typ not in enum_like:
                # 有取值表却不是枚举型 —— 那 is_free_form 判"能自由填"就与取值表冲突
                odd.append((key, typ, len(choices)))
        self.assertEqual(odd, [],
                         f"这些项库里有取值表却不是枚举型，open 的判据要重新想：{odd[:5]}")

        # Flag 是一个特例：mpv 里它是"开关"，取值表可能为空（yes/no 由类型隐含），
        # 所以只统计，不断言它必须有表。
        flags_without = [k for k, m in db.items()
                         if isinstance(m, dict)
                         and str(m.get("type") or "").strip().lower() == "flag"
                         and not [c for c in (m.get("choices") or []) if str(c).strip()]]
        self.assertGreaterEqual(len(flags_without), 0)

    def test_native_layer_also_carries_options(self):
        """完全体那 800 多项同样要能下拉，不能只有核心层有。"""
        native = server.api_options()["native"]
        self.assertTrue(native)
        with_opts = [it for it in native if it["options"]]
        self.assertTrue(with_opts, "原生层一项候选值都没带出来")

    def test_db_choices_are_actually_reaching_the_ui(self):
        """库里有取值域的选项，其 `choices` 必须变成接口里的 `options`。"""
        db = load_db()["options"]
        with_choices = {k: m["choices"] for k, m in db.items()
                        if isinstance(m, dict) and m.get("choices")}
        self.assertGreater(len(with_choices), 50,
                           "库里带取值域的选项突然变少了，值得看一眼")
        api = {it["key"]: it for it in server.api_options()["native"]
               + server.api_options()["core"]}
        # 抽查前 20 个，允许个别被精选层的建议值覆盖，但必须真的传下来了
        checked = 0
        for key, choices in list(with_choices.items())[:20]:
            it = api.get(key)
            if not it:
                continue          # 不在界面暴露的选项，跳过
            checked += 1
            self.assertTrue(it["options"], f"{key} 库里有 {len(choices)} 个取值，接口里却是空的")
        self.assertGreater(checked, 0, "抽查的选项一个都没进界面？")


if __name__ == "__main__":
    unittest.main()

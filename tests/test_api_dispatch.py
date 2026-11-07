# -*- coding: utf-8 -*-
"""`webui/api.py` 的 dispatch 直测 —— 不起服务、不开端口。

对应的设计记录在 git 历史里（`git show <commit>:specs/transport-dispatch.md`）——
开发文档已清理，只留源码与用户文档。

## 为什么值得单独测

重构最容易出的事是"**行为悄悄变了**"：把 `do_GET`/`do_POST` 抽成一个函数，
顺手就会把某些边角改掉 —— 比如"POST body 解析失败时传空 dict 而不是报 400"
这种细节，没人会记得。所以这里把**分发层的每个可观察行为**都钉住，
而不是只测"能调通"。

⚠ 本文件**不启动 HTTP 服务**：dispatch 是纯函数，构造个请求对象就能测。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from webui import api, server                                        # noqa: E402


class ImportSafetyTest(unittest.TestCase):
    """AC-12：单独导入 api 不能炸（证明没有 server → api → server 的循环导入）。"""

    def test_api_imports_without_server(self):
        import importlib
        import subprocess
        # 在**全新的解释器**里只导入 webui.api —— 同进程内 server 早已被导入，
        # 证明不了"没有循环"。用子进程才作数。
        code = "import sys; sys.path.insert(0, r'%s'); import webui.api as a; " \
               "print(hasattr(a, 'dispatch'), hasattr(a, 'Request'))" % ROOT
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, f"单独导入 webui.api 失败：{r.stderr[-500:]}")
        self.assertEqual(r.stdout.strip(), "True True")


class ScriptModeTest(unittest.TestCase):
    """⚠ **脚本模式**：`py webui\\server.py` 必须真能起来并把接口服务出来。

    这一组是补一个**真实盲区**：本文件其余测试、以及 `test_webui.py`，
    全部走"包导入"（`from webui import server`）。而**用户和启动器走的是脚本模式**
    （`py webui\\server.py`）—— 那是一条完全不同的导入路径。

    实测代价：重构里连续踩了**两个**只在脚本模式炸的相对导入
    （`server.py` 的 `from . import api`、`api.py` 的 `from . import server`），
    **而 573 项测试全绿** —— 因为它只让服务器起来后每个接口回 500，
    单元测试压根没起服务器。

    所以这里**真的起一个进程**（不 mock、不 patch），打一次真实 HTTP。
    慢一点（几秒），但这是唯一能拦住那类 bug 的办法。
    """

    def test_script_mode_serves_api(self):
        import json as _json
        import socket
        import subprocess
        import time
        import urllib.request

        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "webui" / "server.py"),
             "--port", str(port), "--no-window"],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.time() + 25
            last = ""
            while time.time() < deadline:
                if proc.poll() is not None:
                    out, err = proc.communicate(timeout=5)
                    self.fail("脚本模式下服务器直接退出了：\n"
                              + err.decode("utf-8", "replace")[-800:])
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/api/status", timeout=3) as r:
                        data = _json.loads(r.read().decode("utf-8"))
                    self.assertEqual(r.status, 200)
                    self.assertIn("version", data)
                    last = ""
                    break
                except Exception as e:                      # 还没起来，接着等
                    last = str(e)
                    time.sleep(0.4)
            else:
                self.fail(f"脚本模式 25 秒内没起来（最后错误：{last}）")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()

    def test_script_mode_serves_static(self):
        """脚本模式下静态文件也要能取到（`/` 与 `/style.css`）。"""
        import socket
        import subprocess
        import time
        import urllib.request

        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "webui" / "server.py"),
             "--port", str(port), "--no-window"],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.time() + 25
            while time.time() < deadline:
                if proc.poll() is not None:
                    _o, err = proc.communicate(timeout=5)
                    self.fail("服务器退出了：\n" + err.decode("utf-8", "replace")[-600:])
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/style.css", timeout=3) as r:
                        body = r.read()
                    self.assertEqual(r.status, 200)
                    self.assertGreater(len(body), 5000, "style.css 太小了，像是没读到")
                    break
                except Exception:
                    time.sleep(0.4)
            else:
                self.fail("脚本模式 25 秒内没起来")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


class DispatchTestBase(unittest.TestCase):
    """共用：临时往路由表里塞假路由，测完摘掉。

    因为路由表存的是**属性名**（FR-11），所以猴补就是"在 server 上加个临时属性"，
    比替换 lambda 干净得多。
    """

    def setUp(self):
        self._added_attrs = []
        self._saved = {k: dict(v) for k, v in
                       (("G", api.ROUTES_GET), ("Q", api.ROUTES_QUERY),
                        ("P", api.ROUTES_POST))}

    def tearDown(self):
        api.ROUTES_GET.clear(); api.ROUTES_GET.update(self._saved["G"])
        api.ROUTES_QUERY.clear(); api.ROUTES_QUERY.update(self._saved["Q"])
        api.ROUTES_POST.clear(); api.ROUTES_POST.update(self._saved["P"])
        for name in self._added_attrs:
            if hasattr(server, name):
                delattr(server, name)

    def fake(self, name, fn):
        """把一个假处理函数挂到 server 上，返回它的属性名。"""
        setattr(server, name, fn)
        self._added_attrs.append(name)
        return name


class GetTest(DispatchTestBase):
    def test_no_arg_route_returns_payload(self):
        """AC-1：无参 GET，payload 与处理函数返回值逐键相等。"""
        name = self.fake("_t_status", lambda: {"ok": True, "x": 1})
        api.ROUTES_GET["/api/_t"] = name
        r = api.dispatch(api.Request(path="/api/_t", method="GET"))
        self.assertEqual(r.status, 200)
        self.assertEqual(r.payload, {"ok": True, "x": 1})

    def test_no_arg_takes_priority_over_query(self):
        """FR-3：无参表优先。两张表都注册同一路径时，走无参那个。"""
        self.fake("_t_first", lambda: {"which": "no-arg"})
        self.fake("_t_second", lambda q: {"which": "query"})
        api.ROUTES_GET["/api/_t"] = "_t_first"
        api.ROUTES_QUERY["/api/_t"] = "_t_second"
        r = api.dispatch(api.Request(path="/api/_t", method="GET", query={"a": "1"}))
        self.assertEqual(r.payload["which"], "no-arg")

    def test_query_route_receives_flat_dict(self):
        """AC-2：带参路由收到的就是扁平 dict（扁平化由适配器负责）。"""
        got = {}
        self.fake("_t_q", lambda q: got.update(q) or {"ok": True})
        api.ROUTES_QUERY["/api/_t"] = "_t_q"
        api.dispatch(api.Request(path="/api/_t", method="GET",
                                 query={"target": "C:/x", "kind": "font"}))
        self.assertEqual(got, {"target": "C:/x", "kind": "font"})

    def test_unknown_get_is_plain_text_404(self):
        """AC-7 + FR-6：未注册的 GET 返回纯文本 not found（不是 JSON）。"""
        r = api.dispatch(api.Request(path="/api/_nope", method="GET"))
        self.assertEqual(r.status, 404)
        self.assertEqual(r.payload, "not found")
        self.assertFalse(r.json, "纯文本不该走 JSON 序列化")

    def test_static_like_path_is_not_handled_here(self):
        """AC-8 + FR-2：静态文件名也不归 dispatch 管（返回 404 not found）。"""
        for p in ("/index.html", "/style.css", "/state.js", "/"):
            r = api.dispatch(api.Request(path=p, method="GET"))
            self.assertEqual(r.status, 404, p)
            self.assertEqual(r.payload, "not found", p)


class PostTest(DispatchTestBase):
    def test_body_reaches_handler(self):
        """AC-3：POST body 原样交给处理函数。"""
        got = {}
        self.fake("_t_p", lambda b: got.update(b) or {"ok": True})
        api.ROUTES_POST["/api/_t"] = "_t_p"
        r = api.dispatch(api.Request(path="/api/_t", method="POST",
                                     body={"a": 1, "b": "x"}))
        self.assertEqual(r.status, 200)
        self.assertEqual(got, {"a": 1, "b": "x"})

    def test_unknown_post_says_unknown_api(self):
        """AC-6 + FR-5：detail 必须恰好是 "unknown api"（现有测试盯着这个词）。"""
        r = api.dispatch(api.Request(path="/api/_nope", method="POST", body={}))
        self.assertEqual(r.status, 404)
        self.assertEqual(r.payload, {"ok": False, "detail": "unknown api"})

    def test_none_body_becomes_empty_dict(self):
        """EC-3：没有 body 时处理函数收到 {}，不是 None。"""
        got = []
        self.fake("_t_p2", lambda b: got.append(b) or {"ok": True})
        api.ROUTES_POST["/api/_t"] = "_t_p2"
        api.dispatch(api.Request(path="/api/_t", method="POST", body=None))
        self.assertEqual(got, [{}])


class ErrorPathTest(DispatchTestBase):
    def test_handler_exception_becomes_500(self):
        """AC-5 + FR-4：异常 → 500，detail 以 "类名: " 开头。"""
        def boom():
            raise ValueError("坏掉了")
        self.fake("_t_boom", boom)
        api.ROUTES_GET["/api/_t"] = "_t_boom"
        r = api.dispatch(api.Request(path="/api/_t", method="GET"))
        self.assertEqual(r.status, 500)
        self.assertEqual(r.payload["ok"], False)
        self.assertTrue(r.payload["detail"].startswith("ValueError: "),
                        r.payload["detail"])

    def test_traceback_is_not_leaked(self):
        """NFR-4：响应体里不许出现文件路径 / traceback 字样。"""
        def boom():
            raise RuntimeError("内部细节")
        self.fake("_t_boom2", boom)
        api.ROUTES_GET["/api/_t"] = "_t_boom2"
        r = api.dispatch(api.Request(path="/api/_t", method="GET"))
        blob = str(r.payload)
        for leak in ("Traceback", "File \"", ROOT.as_posix()):
            self.assertNotIn(leak, blob, f"泄了 {leak}")

    def test_missing_attribute_name_is_reported_not_crashed(self):
        """AC-10 + FR-11：路由表指向不存在的属性名 → 500 提到 AttributeError。"""
        api.ROUTES_GET["/api/_t"] = "_t_这个属性不存在"
        r = api.dispatch(api.Request(path="/api/_t", method="GET"))
        self.assertEqual(r.status, 500)
        self.assertIn("AttributeError", r.payload["detail"])

    def test_monkeypatch_can_swap_a_real_handler(self):
        """AC-11 + FR-12：猴补真实处理函数也能生效（证明是调用时解析的）。"""
        orig = server.api_status
        def fake_status():
            raise ValueError("被我换掉了")
        server.api_status = fake_status
        try:
            r = api.dispatch(api.Request(path="/api/status", method="GET"))
            self.assertEqual(r.status, 500)
            self.assertIn("被我换掉了", r.payload["detail"])
        finally:
            server.api_status = orig
        # 恢复后行为如常
        r2 = api.dispatch(api.Request(path="/api/status", method="GET"))
        self.assertEqual(r2.status, 200)
        self.assertIn("version", r2.payload)


class MethodTest(DispatchTestBase):
    def test_other_methods_are_not_found(self):
        """EC-5：HEAD / PUT 等未支持的方法 → 404 not found。"""
        for m in ("HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"):
            r = api.dispatch(api.Request(path="/api/status", method=m))
            self.assertEqual(r.status, 404, m)
            self.assertEqual(r.payload, "not found", m)

    def test_default_method_is_get(self):
        """Request 不传 method 时默认 GET（调用方少写一个字段）。"""
        r = api.dispatch(api.Request(path="/api/status"))
        self.assertEqual(r.status, 200)

    def test_handler_returning_none_does_not_crash(self):
        """EC-6：处理函数返回 None 也不崩。"""
        self.fake("_t_none", lambda: None)
        api.ROUTES_GET["/api/_t"] = "_t_none"
        r = api.dispatch(api.Request(path="/api/_t", method="GET"))
        self.assertEqual(r.status, 200)
        self.assertIsNone(r.payload)


class TableIntegrityTest(unittest.TestCase):
    """路由表本身的约束 —— 抽出来之后这些必须还成立。"""

    def test_tables_are_attribute_names(self):
        """FR-11：表里存的是字符串（属性名），不是函数对象。"""
        for tbl, label in ((api.ROUTES_GET, "GET"), (api.ROUTES_QUERY, "QUERY"),
                           (api.ROUTES_POST, "POST")):
            for path, target in tbl.items():
                self.assertIsInstance(target, str,
                                      f"{label} 的 {path} 存的不是属性名：{target!r}")
                self.assertTrue(hasattr(server, target),
                                f"{label} 的 {path} 指向 server.{target}，但它不存在")

    def test_no_path_in_two_tables(self):
        """同一路径不许同时出现在两张表里（否则行为取决于查表顺序）。"""
        g, q, p = set(api.ROUTES_GET), set(api.ROUTES_QUERY), set(api.ROUTES_POST)
        self.assertEqual(g & p, set(), "GET 与 POST 撞了")
        self.assertEqual(g & q, set(), "GET 与 QUERY 撞了")
        self.assertEqual(q & p, set(), "QUERY 与 POST 撞了")

    def test_route_count_matches_before_refactor(self):
        """条数守门：GET 3 / QUERY 13 / POST 26 = 42（T14 后加了 /api/scandirs 与 add/remove，与 verify.py docs 一致）。

        ⚠ 这条**抓到过一次真事故**：搬运路由表时用的正则非贪婪匹配 `^}`，
        而表里有两处跨行的 lambda（里面带 `}`），于是从那里开始整段没匹配干净，
        **三条 QUERY 路由被静默丢掉**（`/api/downloads`、`/api/download/job`、
        `/api/userpresets`）。别的时候测试全绿 —— 因为它们只打自己关心的接口。
        所以这个"数数"的断言不是形式主义。
        """
        self.assertEqual(len(api.ROUTES_GET), 3)
        self.assertEqual(len(api.ROUTES_QUERY), 13)
        self.assertEqual(len(api.ROUTES_POST), 26)
        self.assertEqual(len(api.ROUTES_GET) + len(api.ROUTES_QUERY)
                         + len(api.ROUTES_POST), 42,
                         "接口总数变了 —— 与 verify.py docs 报的 42 对不上")

    def test_all_paths_are_api_paths(self):
        for tbl in (api.ROUTES_GET, api.ROUTES_QUERY, api.ROUTES_POST):
            for path in tbl:
                self.assertTrue(path.startswith("/api/"), path)

    def test_server_no_longer_defines_route_tables(self):
        """FR-9：路由表搬走了，server.py 里不该再有这三张表。"""
        src = (ROOT / "webui" / "server.py").read_text(encoding="utf-8")
        for name in ("ROUTES_GET", "ROUTES_QUERY", "ROUTES_POST"):
            self.assertNotIn(f"{name} = {{", src,
                             f"server.py 里还留着 {name} 的定义（应当只在 webui/api.py）")


class RealRouteSmokeTest(unittest.TestCase):
    """拿真实路由跑几条，确认抽出来之后真的还能用（AC-9 的纯函数版）。"""

    def test_status(self):
        r = api.dispatch(api.Request(path="/api/status", method="GET"))
        self.assertEqual(r.status, 200)
        self.assertIn("title", r.payload)
        self.assertIn("counts", r.payload)

    def test_options(self):
        r = api.dispatch(api.Request(path="/api/options", method="GET"))
        self.assertEqual(r.status, 200)
        self.assertTrue(r.payload["core"])

    def test_combos_needs_target(self):
        """`/api/combos` 原来是 `lambda q: api_combos({...})`，提成具名函数后行为不变。"""
        r = api.dispatch(api.Request(path="/api/combos", method="GET",
                                     query={"target": ""}))
        self.assertEqual(r.status, 200)
        self.assertTrue(r.payload["ok"])

    def test_unknown_api_path_still_404(self):
        r = api.dispatch(api.Request(path="/api/根本没有", method="GET"))
        self.assertEqual(r.status, 404)


if __name__ == "__main__":
    unittest.main()

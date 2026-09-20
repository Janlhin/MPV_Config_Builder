# -*- coding: utf-8 -*-
"""stdio 传输测试（specs/stdio-transport.md 的 AC-1 ~ AC-12）。

分两层：
  * 纯函数层：`handle_line(str) -> dict|None`，喂字符串拿字符串，不起进程（FR-13）；
  * 真进程层：真的 `py webui/server.py --stdio`，灌请求、收 stdout。
    这一层不能省 —— 第一层的测试全绿也证明不了「stdout 里除了协议没有别的东西」，
    而那恰恰是 stdio 模式最容易复发、后果最严重的错（一行日志 = 整个后端失联）。
"""
import json
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from webui import api, stdio                              # noqa: E402


def line(obj):
    """把 dict 变成协议行（跟 Electron 会发的东西一样）。"""
    return json.dumps(obj, ensure_ascii=False)


class NormalizeTest(unittest.TestCase):
    """领域名 → /api/... 的归一化（FR-3）。"""

    def test_domain_name(self):
        self.assertEqual(stdio.normalize("config/load"), "/api/config/load")
        self.assertEqual(stdio.normalize("status"), "/api/status")
        self.assertEqual(stdio.normalize("keys/save"), "/api/keys/save")

    def test_already_prefixed_is_kept(self):
        # 容错：前端要是顺手写了 /api/... 也得认，不然一个前缀就把全线打崩
        self.assertEqual(stdio.normalize("/api/status"), "/api/status")
        self.assertEqual(stdio.normalize("api/status"), "/api/status")

    def test_extra_slashes_and_spaces(self):
        self.assertEqual(stdio.normalize("  /status  "), "/api/status")
        self.assertEqual(stdio.normalize("config/load/"), "/api/config/load/")

    def test_empty(self):
        self.assertEqual(stdio.normalize(""), "")
        self.assertEqual(stdio.normalize(None), "")

    def test_every_domain_name_maps_to_a_real_route(self):
        """把 39 条路由全部按协议发一遍，都该命中真实路由表。

        这条是防"协议和路由表对不上"的 —— 比如以后加了新接口但归一化写错了。
        """
        bad = []
        for table in (api.ROUTES_GET, api.ROUTES_QUERY, api.ROUTES_POST):
            for full in table:
                domain = full[len("/api/"):]
                if stdio.normalize(domain) != full:
                    bad.append((domain, stdio.normalize(domain), full))
        self.assertEqual(bad, [])


class InferMethodTest(unittest.TestCase):
    def test_post_paths(self):
        self.assertEqual(stdio.infer_method("/api/config/load"), "POST")
        self.assertEqual(stdio.infer_method("/api/keys/save"), "POST")

    def test_get_paths(self):
        self.assertEqual(stdio.infer_method("/api/status"), "GET")
        self.assertEqual(stdio.infer_method("/api/backups"), "GET")

    def test_unknown_defaults_to_get(self):
        self.assertEqual(stdio.infer_method("/api/不存在"), "GET")


class HandleLineTest(unittest.TestCase):
    """纯函数层（AC-1 ~ AC-6, AC-10, AC-11）。"""

    def test_status_matches_the_http_path(self):
        """AC-1：同一份数据，stdio 与非 stdio 必须逐键相等。"""
        got = stdio.handle_line(line({"id": 1, "path": "status"}))
        self.assertEqual(got["id"], 1)
        self.assertTrue(got["ok"])
        self.assertEqual(got["data"], api.dispatch(api.Request("/api/status")).payload)

    def test_domain_name_hits_post_route(self):
        """AC-2：config/load 是 POST 路由，不带 method 也该走 POST。"""
        got = stdio.handle_line(line({
            "id": 7, "path": "config/load",
            "body": {"path": str(ROOT / "不存在的文件.conf")}}))
        self.assertEqual(got["id"], 7)
        # 不care 业务结果，只要求它**命中了**这条路由（不是 unknown api）
        self.assertNotIn("unknown api", json.dumps(got, ensure_ascii=False))

    def test_prefixed_path_also_works(self):
        """AC-3：带 /api 前缀也认。"""
        got = stdio.handle_line(line({"id": 2, "path": "/api/status"}))
        self.assertTrue(got["ok"])

    def test_exception_becomes_error_not_crash(self):
        """AC-4：处理函数抛异常 → ok=false，且不泄 traceback。"""
        original = sys.modules["webui.server"].api_status

        def boom():
            raise ValueError("故意炸的")
        sys.modules["webui.server"].api_status = boom
        try:
            got = stdio.handle_line(line({"id": 3, "path": "status"}))
        finally:
            sys.modules["webui.server"].api_status = original
        self.assertFalse(got["ok"])
        self.assertTrue(got["error"].startswith("ValueError: "), got["error"])
        self.assertEqual(got["status"], 500)
        self.assertNotIn("Traceback", json.dumps(got))

    def test_unknown_api(self):
        got = stdio.handle_line(line({"id": 4, "path": "根本没有这个接口"}))
        self.assertFalse(got["ok"])
        self.assertEqual(got["status"], 404)

    def test_bad_json(self):
        """AC-5。"""
        got = stdio.handle_line("{oops")
        self.assertFalse(got["ok"])
        self.assertIn("JSON", got["error"])

    def test_empty_line_produces_nothing(self):
        """AC-6 / FR-7。"""
        self.assertIsNone(stdio.handle_line(""))
        self.assertIsNone(stdio.handle_line("   \n"))
        self.assertIsNone(stdio.handle_line(None))

    def test_json_but_not_an_object(self):
        got = stdio.handle_line("[1,2,3]")
        self.assertFalse(got["ok"])
        self.assertIn("对象", got["error"])

    def test_missing_id(self):
        got = stdio.handle_line(line({"path": "status"}))
        self.assertFalse(got["ok"])
        self.assertIn("id", got["error"])

    def test_missing_path(self):
        got = stdio.handle_line(line({"id": 9}))
        self.assertFalse(got["ok"])
        self.assertIn("path", got["error"])

    def test_bad_method(self):
        got = stdio.handle_line(line({"id": 9, "path": "status", "method": "DELETE"}))
        self.assertFalse(got["ok"])
        self.assertIn("DELETE", got["error"])

    def test_query_values_are_stringified(self):
        """query 里传数字/布尔也得能用（协议是 JSON，什么类型都可能来）。"""
        got = stdio.handle_line(line({"id": 5, "path": "backups",
                                      "query": {"target": 123, "flag": True}}))
        self.assertTrue(got["ok"], got)

    def test_bad_query_type(self):
        got = stdio.handle_line(line({"id": 5, "path": "backups", "query": "不是对象"}))
        self.assertFalse(got["ok"])

    def test_chinese_round_trips(self):
        """AC-10：中文不许变成 \\uXXXX 或乱码。"""
        raw = json.dumps(stdio.handle_line(line({"id": 6, "path": "status"})),
                         ensure_ascii=False)
        self.assertNotIn("\\u", raw)

    def test_bad_line_does_not_poison_the_next(self):
        """AC-11 / NFR-4：坏行之后好行照常。"""
        first = stdio.handle_line("这不是 json")
        second = stdio.handle_line(line({"id": 8, "path": "status"}))
        self.assertFalse(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["id"], 8)


class ServeLoopTest(unittest.TestCase):
    """`serve()` 用假流测，不起进程。"""

    def test_writes_one_line_per_request_and_skips_blanks(self):
        import io
        src = io.StringIO("\n".join([
            line({"id": 1, "path": "status"}),
            "",
            "   ",
            line({"id": 2, "path": "presets"}),
            line({"id": 3, "path": "status"}),
        ]) + "\n")
        out, err = io.StringIO(), io.StringIO()
        rc = stdio.serve(stdin=src, stdout=out, stderr=err)
        self.assertEqual(rc, 0)
        rows = [l for l in out.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(rows), 3)
        ids = [json.loads(r)["id"] for r in rows]
        self.assertEqual(ids, [1, 2, 3])
        for r in rows:
            json.loads(r)                       # 每行都必须是合法 JSON

    def test_serve_turns_on_quiet_stdout(self):
        """serve() 必须把日志改道，否则 stdout 会被污染。"""
        import io
        src = io.StringIO("")
        out, err = io.StringIO(), io.StringIO()
        stdio.serve(stdin=src, stdout=out, stderr=err)
        server = sys.modules["webui.server"]
        self.assertTrue(server.QUIET_STDOUT)
        server.log("这条必须走 stderr")
        self.assertEqual(out.getvalue(), "")                 # stdout 一点都不能脏
        self.assertIn("这条必须走 stderr", err.getvalue())
        # 复位，免得影响别的测试
        server.QUIET_STDOUT = False
        server.LOG_STREAM = None


class RealProcessTest(unittest.TestCase):
    """真起一个 `--stdio` 子进程（AC-7, AC-8, AC-9, AC-12）。

    ⚠ 这一层是**这个 spec 的核心防线**：AC-8（stdout 每一行都是合法 JSON）
    在纯函数层根本测不出来 —— 那条测试才是拦住"谁又加了个 print"的东西。

    用 W2_CHILD 那种递归保护没必要（这个子进程不跑测试），
    但**必须显式给 UTF-8 环境**，否则 Windows 下中文会乱码。
    """

    def _run(self, requests, timeout=60):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        payload = "".join(r + "\n" for r in requests)
        p = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"), "--stdio"],
            input=payload.encode("utf-8"), capture_output=True, cwd=str(ROOT),
            env=env, timeout=timeout)
        return p, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")

    def test_three_requests_then_eof(self):
        """AC-7：三条请求 → 三行响应、id 对应、退出码 0。"""
        p, out, err = self._run([
            line({"id": 1, "path": "status"}),
            line({"id": 2, "path": "presets"}),
            line({"id": 3, "path": "status"}),
        ])
        self.assertEqual(p.returncode, 0, f"退出码 {p.returncode}，stderr=\n{err}")
        rows = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(rows), 3, f"实际 {len(rows)} 行：\n{out}")
        self.assertEqual([json.loads(r)["id"] for r in rows], [1, 2, 3])

    def test_stdout_is_pure_protocol(self):
        """AC-8：**stdout 每一行都必须能 json.loads**。

        这条要是红了，说明有人在 stdio 路径上 print 了东西。
        报错时把脏行打出来，省得还得自己复现。
        """
        p, out, err = self._run([
            line({"id": 1, "path": "status"}),
            "这条不是 json",
            line({"id": 2, "path": "status"}),
        ])
        self.assertEqual(p.returncode, 0)
        for i, raw in enumerate(out.splitlines(), 1):
            if not raw.strip():
                continue
            try:
                json.loads(raw)
            except ValueError as e:
                self.fail(f"stdout 第 {i} 行不是合法 JSON（{e}）：{raw!r}\n"
                          f"完整 stdout：\n{out}")

    def test_chinese_is_not_escaped_or_mangled(self):
        """AC-10：真进程往返后中文仍可读。"""
        p, out, err = self._run([line({"id": 1, "path": "status"})])
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("\\u", out, "中文被转义成 \\uXXXX 了 —— 排查时不好读")

    def test_no_http_banner_and_log_goes_to_stderr(self):
        """AC-9 / FR-11：stdio 模式不开 HTTP 服务。

        判据：**stdout 里不许出现任何 HTTP 痕迹**。
        HTTP 模式一启动就会打 `… web ui → http://127.0.0.1:PORT/` 那行横幅；
        它不在 stdout，说明那条路径压根没走。stdio 模式下 stderr 也**不该**有它
        —— 因为根本没起服务，没有 URL 可报。

        （`log()` 会不会被赶对地方，由上面 ServeLoopTest.test_serve_turns_on_quiet_stdout
        直接验证，不在这里重复。）
        """
        p, out, err = self._run([line({"id": 1, "path": "status"})])
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("http://", out, f"stdout 里出现了 HTTP 痕迹：\n{out}")
        self.assertNotIn("web ui", out)
        self.assertNotIn("http://", err, f"stdio 模式不该有 HTTP 横幅：\n{err}")

    def test_bad_line_then_good_line_across_process(self):
        p, out, err = self._run([
            "{不是 json",
            line({"id": 1, "path": "status"}),
            line({"id": 2, "path": "不存在"}),
            line({"id": 3, "path": "presets"}),
        ])
        self.assertEqual(p.returncode, 0)
        rows = [json.loads(l) for l in out.splitlines() if l.strip()]
        # 第一条是坏行 —— 它连 id 都没解析出来，所以回 id=None（协议上合理：
        # 调用方从这一条就能看出"我发的这行有问题"）
        self.assertEqual([r["id"] for r in rows], [None, 1, 2, 3])
        self.assertFalse(rows[0]["ok"])
        self.assertTrue(rows[1]["ok"])
        self.assertFalse(rows[2]["ok"])          # 不存在的接口
        self.assertTrue(rows[3]["ok"])           # 坏行没有毒到后面的请求


class SeparationTest(unittest.TestCase):
    """stdio 是传输层，**不许**顺带把 HTTP / socket 拖进来（NFR-2）。

    ⚠ 判据必须是 AST，不能是字符串搜索。
    实测踩过：`webui/stdio.py` 的文档串里明明白白写着
    「这个模块**不许 import `http.server` / socket**」——
    用 `"http.server" in 源码` 去判，会被这句**关于禁令的说明**判成违规。
    那种检查比没有还糟：它逼你去删一句正确的注释。
    """

    def _imports(self):
        import ast
        src = (ROOT / "webui" / "stdio.py").read_text(encoding="utf-8")
        mods = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name.split(".")[0])
        return mods

    def test_no_http_or_socket_dependency(self):
        mods = self._imports()
        self.assertNotIn("http", mods, f"stdio.py 不该依赖 http：{sorted(mods)}")
        self.assertNotIn("socket", mods, f"stdio.py 不该依赖 socket：{sorted(mods)}")

    def test_only_expected_dependencies(self):
        """顺便钉住它依赖面有多窄 —— 变宽了要有人知道。"""
        allowed = {"api", "server", "json", "sys", "collections", "typing"}
        extra = self._imports() - allowed
        self.assertEqual(extra, set(),
                         f"stdio.py 多出新依赖 {sorted(extra)}，确认是否必要")


if __name__ == "__main__":
    unittest.main(verbosity=2)

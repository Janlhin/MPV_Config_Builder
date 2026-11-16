# -*- coding: utf-8 -*-
"""Tauri 预览外壳的静态守护（2026-11-16，待做 §〇 第 15 项）。

## 为什么是静态测试，而不是「跑一遍看看」

`cargo build` + 起窗口需要 Rust 工具链、WebView2 和几分钟编译时间 —— 把它绑进
每次提交不现实（`.githooks/pre-commit` 要秒级）。所以这里用测试守住那几条
**违反了也不会红、但会在很久以后咬人**的约定：

* `frontendDist` 必须指回 `webui/static`：一旦有人在 `tauri/` 下复制一份前端，
  副本会漂移，然后「测试全绿、窗口里跑的是另一套页面」（`electron/renderer/`
  踩过这个坑，靠同步脚本兜着；这里选择**根本不复制**）；
* **不开端口**：`main.rs` 里不许出现 `127.0.0.1` / `http://`。图省事让窗口加载
  本地 HTTP，会一步丢掉「不开端口」和 CSP 同源兜底；
* 退出顺序必须是「关 stdin → 等 → 才 kill」。只留 kill 会打断正在写的 `mpv.conf`。

实机那一半在 `tools/verify.py tauri`（真窗口 + CDP + 关窗查孤儿）。
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAURI = ROOT / "tauri"
SRC = TAURI / "src-tauri"
CONF = SRC / "tauri.conf.json"
CARGO = SRC / "Cargo.toml"
MAINRS = SRC / "src" / "main.rs"
CAPS = SRC / "capabilities" / "default.json"


def _conf():
    return json.loads(CONF.read_text(encoding="utf-8"))


def _mainrs():
    return MAINRS.read_text(encoding="utf-8")


def _code_only(src):
    """去掉 `//` / `//!` 注释行再看。

    源码里专门留了一句「别把窗口改成加载本机 HTTP 端口」当警告，那句话里必然
    出现违规字面量。判据该落在**代码**上，不是落在注释上。
    """
    keep = [ln for ln in src.splitlines() if not ln.strip().startswith("//")]
    return "\n".join(keep)


class SkeletonTest(unittest.TestCase):
    """脚手架得在，且是 Tauri 2 那一套。"""

    def test_files_exist(self):
        for f in (CARGO, SRC / "build.rs", CONF, MAINRS, CAPS, TAURI / "package.json"):
            self.assertTrue(f.is_file(), f"缺 {f}")

    def test_cargo_declares_tauri_2(self):
        text = CARGO.read_text(encoding="utf-8")
        self.assertIn('tauri = { version = "2"', text)
        self.assertIn("tauri-build", text)

    def test_build_rs_calls_tauri_build(self):
        self.assertIn("tauri_build::build()", (SRC / "build.rs").read_text(encoding="utf-8"))


class ConfigTest(unittest.TestCase):
    """tauri.conf.json 的几条硬约定。"""

    def test_json_is_valid(self):
        self.assertEqual(_conf()["productName"], "MPV Config Builder")

    def test_frontend_dist_points_at_single_source(self):
        dist = str(_conf()["build"]["frontendDist"]).replace("\\", "/")
        self.assertTrue(dist.endswith("webui/static"), dist)
        self.assertTrue((ROOT / "webui" / "static" / "index.html").is_file())

    def test_preview_does_not_bundle_installers(self):
        self.assertIs(_conf()["bundle"]["active"], False)

    def test_identifier_is_not_scaffold_default(self):
        ident = _conf()["identifier"]
        self.assertTrue(ident)
        self.assertNotIn("com.tauri", ident)

    def test_icons_referenced_exist(self):
        for icon in _conf()["bundle"]["icon"]:
            self.assertTrue((SRC / icon).resolve().is_file(), icon)

    def test_capability_scope_is_minimal(self):
        caps = json.loads(CAPS.read_text(encoding="utf-8"))
        self.assertEqual(caps["permissions"], ["core:default"])
        self.assertEqual(caps["windows"], ["main"])


class TransportTest(unittest.TestCase):
    """传输层：必须走 stdio，不许偷偷开端口。"""

    def test_spawns_backend_over_stdio(self):
        src = _mainrs()
        self.assertIn("server.py", src)
        self.assertIn("--stdio", src)

    def test_no_local_http_anywhere(self):
        code = _code_only(_mainrs())
        # 窗口加载本地地址 = 开端口 + 丢掉 CSP 同源兜底，预览版明确不做
        self.assertNotIn("127.0.0.1", code)
        self.assertNotIn("http://", code)
        self.assertNotIn("WebviewUrl::External", code)

    def test_injects_invoke_bridge(self):
        src = _mainrs()
        self.assertIn("__MPVCB_INVOKE__", src)
        self.assertIn("fn mpvcb_invoke", src)
        # 桥键名必须和前端 api.js 认的那个一致，否则页面会静默退回 fetch
        self.assertIn("__TAURI_INTERNALS__", src)

    def test_request_ids_pair_responses(self):
        src = _mainrs()
        self.assertIn("pending", src)
        self.assertIn("seq.fetch_add", src)


class ShutdownTest(unittest.TestCase):
    """退出路径：先礼后兵，且顺序不能反。"""

    def test_close_stdin_before_kill(self):
        src = _mainrs()
        idx_stdin = src.find("drop(be.stdin")
        idx_kill = src.find("child.kill()")
        self.assertGreater(idx_stdin, 0, "找不到关 stdin 的那一步")
        self.assertGreater(idx_kill, 0, "找不到兜底 kill")
        self.assertLess(idx_stdin, idx_kill, "必须先关 stdin（后端读到 EOF 自己退），再 kill")

    def test_waits_before_giving_up(self):
        src = _mainrs()
        self.assertIn("SHUTDOWN_GRACE", src)
        self.assertIn("try_wait", src)

    def test_kills_on_run_event_exit(self):
        src = _mainrs()
        self.assertIn("RunEvent::Exit", src)
        self.assertIn("shutdown_backend()", src)


class SingleSourceTest(unittest.TestCase):
    """前端只有一份：tauri/ 下不该有 .html/.css/.js 副本。"""

    def test_no_frontend_copies(self):
        copies = [str(p.relative_to(TAURI)) for p in TAURI.rglob("*")
                  if p.is_file() and p.suffix.lower() in (".html", ".css", ".js")
                  and "target" not in p.parts and "node_modules" not in p.parts
                  and "gen" not in p.parts]
        self.assertEqual(copies, [], f"tauri/ 下出现了前端副本：{copies}")

    def test_compile_outputs_are_ignored(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("tauri/src-tauri/target/", text)


class NoMachinePathsTest(unittest.TestCase):
    """不能写死别人机器上的路径（发布自检里那条检查的同一条道理）。"""

    def test_no_hardcoded_paths(self):
        pat = re.compile(r"[CD]:\\(Users|Projects)", re.I)
        for f in (MAINRS, CONF, CAPS, CARGO):
            self.assertIsNone(pat.search(f.read_text(encoding="utf-8")), f.name)


if __name__ == "__main__":
    unittest.main()

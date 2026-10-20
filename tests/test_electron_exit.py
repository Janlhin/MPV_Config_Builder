# -*- coding: utf-8 -*-
"""Electron 退出时序的源码级守护（T25）。

Electron 本身没法在单测里起（需要 node_modules + 显示环境），所以这里钉的是
**源码必须保持的形状**：只删立即 kill 会变孤儿进程，必须 before-quit 等待。
实机验证另见 `python tools/verify.py electron`。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MAIN = ROOT / "electron" / "main.js"


class ElectronExitSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = MAIN.read_text(encoding="utf-8")

    def _shutdown_body(self):
        m = re.search(r"shutdown\(timeoutMs = 1500\) \{(.*?)\n  \}", self.src, re.S)
        self.assertIsNotNone(m, "找不到 shutdown() 实现")
        return m.group(1)

    def test_shutdown_and_killnow_exist(self):
        self.assertIn("killNow()", self.src)
        self.assertIn("shutdown(timeoutMs = 1500)", self.src)

    def test_shutdown_waits_for_exit_before_killing(self):
        body = self._shutdown_body()
        self.assertIn("p.once('exit'", body)
        self.assertIn("setTimeout(() => finish(true)", body)
        self.assertIn("p.stdin.end()", body)
        # 只允许 finish() 里出现一次 p.kill() —— 方法末尾不许再有立即强杀
        self.assertEqual(body.count("p.kill()"), 1, body)

    def test_dead_is_reset_on_spawn(self):
        self.assertRegex(self.src, r"spawn\(\) \{\s*this\.dead = null;")

    def test_before_quit_prevents_default_then_quits(self):
        self.assertIn("e.preventDefault()", self.src)
        self.assertIn("backend.shutdown(1500).then(() => app.quit())", self.src)
        self.assertNotIn("app.on('before-quit', () => backend.kill())", self.src)


if __name__ == "__main__":
    unittest.main()

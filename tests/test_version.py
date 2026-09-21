# -*- coding: utf-8 -*-
"""版本号只有一个来源。

原来的毛病：`core/schema.py` 里 `VERSION` 是 "0.1.0"，但标题用的是另一个常数
`APP_VERSION = "2.0"` —— 界面上同时出现两个版本号，用户会以为装了两个东西。

2026-09-14 用户定：**界面只显示软件版本**，`APP_VERSION` 退成「只给 legacy 用」，
`FULL_TITLE` 不再拼它。并且版本号只有 `core/schema.py` 一个来源，
`electron/package.json` 那边靠 `tools/sync_version.py` 同步（下面有测试钉住）。
"""
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 旧界面 2026-09-14 从仓库根挪进了 legacy/。
# 这些测试盯着的是**两个界面都别各自手写标题/版本**，所以文件挪了也得继续盯 ——
# 挪完不修，它们会从"检查通过"变成"文件找不到"然后直接报错。
TK = ROOT / "legacy" / "mpv_config_builder.py"

from core import schema                                                      # noqa: E402


class VersionSourceTest(unittest.TestCase):
    def test_constants(self):
        self.assertTrue(schema.APP_TITLE)
        self.assertTrue(schema.VERSION)
        # ⚠ 2026-09-14 起 FULL_TITLE **不再拼 APP_VERSION**（用户要求界面只显示
        #    软件版本，不要"2.0"）。APP_VERSION 现在只给 legacy/ 那个旧界面用。
        self.assertEqual(schema.FULL_TITLE, schema.APP_TITLE)

    def test_app_version_still_exists_for_legacy(self):
        """APP_VERSION 是给 legacy/ 留的，**不能删** —— 删了旧界面 import 就崩。

        （我删过一次，legacy 立刻 ImportError。这条测试就是防这个。
        它纯粹是给不维护的旧代码用的显示常数，主界面不该再拼它。）
        """
        self.assertTrue(schema.APP_VERSION)
        src = TK.read_text(encoding="utf-8")
        self.assertIn("APP_VERSION", src,
                      "legacy 不再用 APP_VERSION 了？那这条测试可以删")

    def test_main_ui_does_not_show_generation_number(self):
        """主界面（webui / electron）不许再出现"产品代数"这种东西。"""
        for f in list((ROOT / "webui").glob("*.py")) + \
                list((ROOT / "webui" / "static").glob("*.html")) + \
                list((ROOT / "webui" / "static").glob("*.js")):
            src = f.read_text(encoding="utf-8")
            self.assertNotIn("APP_VERSION", src,
                             f"{f.name} 又在用 APP_VERSION 了 —— 主界面只用 VERSION")

    def test_dunder_version_matches(self):
        """打包工具认 __version__，它必须和 VERSION 一致。"""
        self.assertEqual(schema.__version__, schema.VERSION)

    def test_title_alias(self):
        self.assertEqual(getattr(schema, "TITLE", None), schema.FULL_TITLE)

    def test_version_is_semverish(self):
        self.assertRegex(schema.VERSION, r"^\d+\.\d+(\.\d+)?$")

    def test_package_json_version_matches(self):
        """版本号只有一个来源：`core/schema.py`。

        electron/package.json 那边打包时要用（决定安装包文件名），
        它必须跟着走。两边不一致的话会出现「安装包叫 0.2.0-Setup.exe，
        软件里却显示 0.1.0」—— **两边都看起来正常**，特别难发现。

        改完 schema.py 记得跑：py tools/sync_version.py
        """
        import json
        pkg = ROOT / "electron" / "package.json"
        if not pkg.is_file():
            self.skipTest("没有 electron/package.json")
        data = json.loads(pkg.read_text(encoding="utf-8"))
        self.assertEqual(
            data.get("version"), schema.VERSION,
            "electron/package.json 的 version 和 core/schema.py 不一致"
            " —— 跑一下 py tools/sync_version.py")

    def test_sync_script_agrees(self):
        """同步脚本的 --check 必须是绿的（它还会检查文件真的存在）。"""
        import subprocess
        r = subprocess.run([sys.executable, "-X", "utf8",
                            str(ROOT / "tools" / "sync_version.py"), "--check"],
                           capture_output=True, cwd=str(ROOT),
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(r.returncode, 0,
                         r.stdout.decode("utf-8", "replace")
                         + r.stderr.decode("utf-8", "replace"))

    def test_no_hardcoded_title_left(self):
        """源码里不该再手写完整的 "MPV Config Builder 2.0"。"""
        for f in list((ROOT / "core").glob("*.py")) + [
                ROOT / "webui" / "server.py", TK]:
            src = f.read_text(encoding="utf-8")
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue            # 注释里提到不算
                self.assertNotIn("MPV Config Builder 2.0", line,
                                 f"{f.name}:{i} 还在手写标题")

    def test_tkinter_uses_schema_constants(self):
        src = TK.read_text(encoding="utf-8")
        self.assertIn("FULL_TITLE", src)
        self.assertIn("APP_VERSION", src)
        self.assertIn("VERSION", src)
        # 旧的那种 `APP_TITLE = "..."` 本地重定义不该再有
        self.assertNotIn('APP_TITLE = "', src)

    def test_generated_config_header_uses_title(self):
        from core.builder import build_config_text
        out = build_config_text({"values": {"vo": "gpu-next"}})
        self.assertEqual(out.splitlines()[0], f"# {schema.FULL_TITLE}")

    def test_build_config_text_accepts_explicit_title(self):
        from core.builder import build_config_text
        out = build_config_text({"values": {"vo": "gpu"}}, title="自定义标题")
        self.assertEqual(out.splitlines()[0], "# 自定义标题")

    def test_server_reports_both(self):
        from webui import server
        st = server.api_status()
        self.assertEqual(st["title"], schema.APP_TITLE)
        self.assertEqual(st["version"], schema.VERSION)

    def test_update_module_uses_version(self):
        from core import update
        self.assertEqual(update.VERSION, schema.VERSION)


class DpiHelperTest(unittest.TestCase):
    """M6：Tkinter 那份的 DPI 适配 helper（不建窗口，只测函数）。"""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mcb_dpi", TK)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_dpi_awareness_returns_a_mode(self):
        got = self.m.enable_dpi_awareness()
        self.assertIn(got, ("per-monitor-v2", "per-monitor", "system", ""))

    def test_tk_scaling_in_sane_range(self):
        s = self.m.tk_scaling()
        self.assertGreaterEqual(s, 1.0)
        self.assertLessEqual(s, 3.0)

    def test_dpi_declared_before_window(self):
        """DPI 声明必须在 super().__init__() 之前 —— 建完窗口再声明就晚了。"""
        src = TK.read_text(encoding="utf-8")
        start = src.index("class App(tk.Tk):")
        head = src[start:start + 900]
        i_dpi = head.index("enable_dpi_awareness()")
        i_init = head.index("super().__init__()")
        self.assertLess(i_dpi, i_init,
                        "enable_dpi_awareness 必须在 super().__init__() 之前调用")


if __name__ == "__main__":
    unittest.main()

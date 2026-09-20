# -*- coding: utf-8 -*-
"""P3-4：版本号只有一个来源。

以前的毛病：`core/schema.py` 写 "MPV Config Builder 2.0"、`mpv_config_builder.py`
又手写一遍同一个字符串，而 `VERSION` 是 "0.1.0" —— 标题写 2.0、版本说 0.1.0，
没人说得清到底几版。现在分成两个概念：
    APP_VERSION = "2.0"    产品代数（标题栏、给用户看的）
    VERSION     = "0.1.0"  软件版本（打包 / Release / 更新检测）
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import schema                                                      # noqa: E402


class VersionSourceTest(unittest.TestCase):
    def test_constants(self):
        self.assertTrue(schema.APP_TITLE)
        self.assertTrue(schema.APP_VERSION)
        self.assertTrue(schema.VERSION)
        self.assertEqual(schema.FULL_TITLE,
                         f"{schema.APP_TITLE} {schema.APP_VERSION}")

    def test_dunder_version_matches(self):
        """打包工具认 __version__，它必须和 VERSION 一致。"""
        self.assertEqual(schema.__version__, schema.VERSION)

    def test_title_alias(self):
        self.assertEqual(getattr(schema, "TITLE", None), schema.FULL_TITLE)

    def test_version_is_semverish(self):
        self.assertRegex(schema.VERSION, r"^\d+\.\d+(\.\d+)?$")

    def test_no_hardcoded_title_left(self):
        """源码里不该再手写完整的 "MPV Config Builder 2.0"。"""
        for f in list((ROOT / "core").glob("*.py")) + [
                ROOT / "webui" / "server.py", ROOT / "mpv_config_builder.py"]:
            src = f.read_text(encoding="utf-8")
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue            # 注释里提到不算
                self.assertNotIn("MPV Config Builder 2.0", line,
                                 f"{f.name}:{i} 还在手写标题")

    def test_tkinter_uses_schema_constants(self):
        src = (ROOT / "mpv_config_builder.py").read_text(encoding="utf-8")
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
            "mcb_dpi", ROOT / "mpv_config_builder.py")
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
        src = (ROOT / "mpv_config_builder.py").read_text(encoding="utf-8")
        start = src.index("class App(tk.Tk):")
        head = src[start:start + 900]
        i_dpi = head.index("enable_dpi_awareness()")
        i_init = head.index("super().__init__()")
        self.assertLess(i_dpi, i_init,
                        "enable_dpi_awareness 必须在 super().__init__() 之前调用")


if __name__ == "__main__":
    unittest.main()

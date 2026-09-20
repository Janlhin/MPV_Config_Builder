# -*- coding: utf-8 -*-
"""P2-6：打包后文档/静态文件还能不能找到。

源码里跑永远是对的，坑只在打包产物里 —— 所以这里让 `core.paths` 以为
自己"已经在打包环境里"，看它会不会去 `sys._MEIPASS` 找东西。
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import paths                                                     # noqa: E402


class SourceModeTest(unittest.TestCase):
    def test_not_frozen_in_source(self):
        self.assertFalse(paths.is_frozen())

    def test_root_is_repo(self):
        self.assertEqual(paths.bundle_root(), ROOT)

    def test_key_paths_exist(self):
        self.assertTrue((paths.bundle_root() / "webui" / "static").is_dir())
        self.assertTrue(paths.data_dir().is_dir())
        self.assertTrue((paths.data_dir() / "mpv_options_zh.json").is_file())
        for doc in ("入门指南.md", "致谢与许可.md", "MPV_Shader搭配说明书.md",
                    "产品规划与路线图.md"):
            self.assertTrue(paths.doc_path(doc).is_file(), doc)

    def test_writable_root_is_repo_in_source(self):
        self.assertEqual(paths.writable_root(), ROOT)


class FrozenModeTest(unittest.TestCase):
    """假装跑在 PyInstaller 解包目录里。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = Path(self.tmp.name)
        # 造一个"解包目录"：代码 + 数据 + 文档
        (self.fake / "core").mkdir()
        (self.fake / "webui" / "static").mkdir(parents=True)
        (self.fake / "data").mkdir()
        (self.fake / "data" / "mpv_options_zh.json").write_text(
            '{"meta": {"count": 0}, "options": {}, "groups": []}', encoding="utf-8")
        for doc in ("入门指南.md", "致谢与许可.md"):
            (self.fake / doc).write_text("# 标题\n", encoding="utf-8")
        self._saved = (getattr(sys, "frozen", None), getattr(sys, "_MEIPASS", None))
        sys.frozen = True
        sys._MEIPASS = str(self.fake)

    def tearDown(self):
        frozen, meipass = self._saved
        if frozen is None:
            sys.__dict__.pop("frozen", None)
        else:
            sys.frozen = frozen
        if meipass is None:
            sys.__dict__.pop("_MEIPASS", None)
        else:
            sys._MEIPASS = meipass
        self.tmp.cleanup()

    def test_detects_frozen(self):
        self.assertTrue(paths.is_frozen())

    def test_bundle_root_is_meipass(self):
        self.assertEqual(paths.bundle_root(), self.fake)

    def test_docs_resolve_inside_bundle(self):
        self.assertTrue(paths.doc_path("入门指南.md").is_file())
        self.assertEqual(paths.doc_path("入门指南.md").parent, self.fake)

    def test_data_resolves_inside_bundle(self):
        self.assertTrue((paths.data_dir() / "mpv_options_zh.json").is_file())

    def test_writable_root_is_not_the_temp_bundle(self):
        """⚠ 关键：写盘不能写进临时解包目录（进程一结束就没了）。"""
        self.assertNotEqual(paths.writable_root(), self.fake,
                            "writable_root 不该指到解包目录")
        self.assertEqual(paths.writable_root(),
                         Path(sys.executable).resolve().parent)

    def test_describe_shape(self):
        d = paths.describe()
        for k in ("frozen", "bundle_root", "data_dir", "writable_root", "python"):
            self.assertIn(k, d)
        self.assertTrue(d["frozen"])


class ServerUsesBundleRootTest(unittest.TestCase):
    """server.py 必须用 bundle_root，而不是自己用 __file__ 推。"""

    def test_server_imports_bundle_root(self):
        src = (ROOT / "webui" / "server.py").read_text(encoding="utf-8")
        self.assertIn("from core.paths import bundle_root", src)
        self.assertIn("BASE = bundle_root()", src)

    def test_guide_uses_base(self):
        src = (ROOT / "webui" / "server.py").read_text(encoding="utf-8")
        start = src.index("def api_guide")
        body = src[start:start + 900]
        self.assertIn("BASE / name", body, "文档路径还在用 __file__ 推的 ROOT")
        self.assertIn("is_frozen()", body, "打包后找不到文档时应提示 --add-data")


class OtherModulesUsePathsTest(unittest.TestCase):
    """其他读 data / md 的模块也必须走 core.paths（打包后才找得到）。"""

    def _src(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_keys_uses_data_dir(self):
        src = self._src("core/keys.py")
        self.assertIn("from .paths import data_dir", src)
        self.assertIn("DATA = data_dir()", src)
        self.assertNotIn('Path(__file__).resolve().parent.parent / "data"', src)

    def test_options_db_uses_data_dir(self):
        src = self._src("core/options_db.py")
        self.assertIn("from .paths import bundle_root, data_dir", src)
        self.assertIn("DB_PATH = data_dir()", src)

    def test_options_db_rst_not_hardcoded_username(self):
        """中文手册的 rst 只在作者机器上有，不该写死某个用户名。"""
        src = self._src("core/options_db.py")
        self.assertNotIn("Janlhin", src, "还在写死作者机器路径")
        self.assertIn("DSH_MPV_OPTIONS_RST", src, "应支持用环境变量指定 rst")

    def test_rst_path_env_override(self):
        import importlib
        import os
        from core import options_db
        old = os.environ.get("DSH_MPV_OPTIONS_RST")
        os.environ["DSH_MPV_OPTIONS_RST"] = r"D:\x\options.rst"
        try:
            importlib.reload(options_db)
            self.assertEqual(str(options_db.RST_PATH), r"D:\x\options.rst")
        finally:
            if old is None:
                os.environ.pop("DSH_MPV_OPTIONS_RST", None)
            else:
                os.environ["DSH_MPV_OPTIONS_RST"] = old
            importlib.reload(options_db)

    def test_tkinter_uses_doc_path(self):
        # 旧界面 2026-09-14 挪进了 legacy/；这条检查的本意没变
        # （它必须走 doc_path 而不是用 __file__ 推路径，否则打包后打不开说明书）
        src = self._src("legacy/mpv_config_builder.py")
        self.assertIn("from core.paths import doc_path", src)
        self.assertIn("doc_path(", src)
        self.assertNotIn('with_name("MPV_Shader', src,
                         "说明书还在用 __file__ 推路径，打包后打不开")

    def test_no_module_left_deriving_data_from_file(self):
        """扫一遍：不许再有模块自己用 __file__ 推 data/ 或仓库根。"""
        for f in list((ROOT / "core").glob("*.py")) + [ROOT / "webui" / "server.py"]:
            if f.name == "paths.py":
                continue                       # paths.py 自己就是干这个的
            src = f.read_text(encoding="utf-8")
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                bad = ('parent.parent / "data"' in line
                       or 'parent / "data"' in line.replace("parent.parent", "parent"))
                self.assertFalse(bad, f"{f.name}:{i} 自己推 data 路径：{line.strip()}")


if __name__ == "__main__":
    unittest.main()

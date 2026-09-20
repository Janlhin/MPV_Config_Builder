# -*- coding: utf-8 -*-
"""用户预设（导出/导入/注册表）的测试。

为什么要有这个功能：原来 `saveLocal()` 只存 `target`/`writeMode`/`source`/`mode`，
**`APP.values` 根本没存** —— 刷新一下页面调好的一套就没了，也没法发给别人。
见 `_reference/GitHub同类项目调查.md`（300★ 的 Glow 早就支持导出/导入自定义预设）。

⚠ 所有测试都先把注册表指到临时目录（`set_registry_dir`），
**绝不往仓库的 `presets/` 里写东西**。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import presetfile as pf                                          # noqa: E402


def state(**kw):
    st = {"values": {}, "shaders": [], "memc": "", "disable": []}
    st.update(kw)
    return st


class RegistryIsolation(unittest.TestCase):
    """一组用例共用的临时注册表。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        pf.set_registry_dir(self.tmp.name)

    def tearDown(self):
        pf.set_registry_dir(None)
        self.tmp.cleanup()


class SafeNameTest(unittest.TestCase):
    def test_reserved_chars_become_underscore(self):
        self.assertEqual(pf.safe_name("a/b:c*d?e"), "a_b_c_d_e")
        self.assertEqual(pf.safe_name("我的<预设>"), "我的_预设_")

    def test_path_traversal_is_neutralised(self):
        """⚠ 有人拿 `../../x` 当预设名，不能让它跑出预设目录。"""
        for evil in ("../../etc/passwd", "..\\..\\windows\\system32",
                     "a/../../b", "....//....//x"):
            got = pf.safe_name(evil)
            self.assertNotIn("/", got)
            self.assertNotIn("\\", got)
            self.assertFalse(got.startswith("."), f"{evil!r} -> {got!r} 以点开头")
            # 拼出来的路径必须还在注册表目录里
            self.assertEqual(Path(got).name, got, f"{evil!r} -> {got!r} 还能当路径用")

    def test_windows_reserved_names(self):
        for n in ("CON", "prn", "AUX", "nul", "COM1", "LPT9"):
            self.assertTrue(pf.safe_name(n).startswith("_"), n)

    def test_empty_becomes_fallback(self):
        self.assertEqual(pf.safe_name(""), "preset")
        self.assertEqual(pf.safe_name("   "), "preset")
        self.assertEqual(pf.safe_name("..."), "preset")
        self.assertEqual(pf.safe_name("///"), "preset")

    def test_length_capped(self):
        self.assertLessEqual(len(pf.safe_name("x" * 500)), 80)

    def test_chinese_is_kept(self):
        self.assertEqual(pf.safe_name("我那套看番的"), "我那套看番的")


class BuildPresetTest(unittest.TestCase):
    def test_only_known_keys_survive(self):
        p = pf.build_preset(state(values={"vo": "gpu-next", "": "bad", "a b": "x"}),
                            name="t")
        self.assertEqual(list(p["state"]["values"]), ["vo"])

    def test_empty_values_are_dropped(self):
        p = pf.build_preset(state(values={"vo": "gpu", "scale": "  "}), name="t")
        self.assertEqual(list(p["state"]["values"]), ["vo"])

    def test_shape_is_stable(self):
        p = pf.build_preset(state(values={"vo": "gpu"}), name="n", note="d", app_version="9.9")
        for k in ("kind", "version", "name", "note", "created", "app_version", "state"):
            self.assertIn(k, p)
        for k in ("values", "shaders", "memc", "disable"):
            self.assertIn(k, p["state"])
        self.assertEqual(p["kind"], pf.KIND)
        self.assertEqual(p["version"], pf.VERSION)
        self.assertEqual(p["app_version"], "9.9")


class ValidateTest(unittest.TestCase):
    def test_rejects_foreign_json(self):
        """⚠ 防呆的关键：随便拖个 json 进来要明确拒绝，不能把键当选项名灌进配置。"""
        ok, detail, _ = pf.validate_preset({"name": "别人的配置", "vo": "gpu"})
        self.assertFalse(ok)
        self.assertIn("不是 MPV Config Builder", detail)

    def test_rejects_non_object(self):
        for bad in ([1, 2], "x", 3, None):
            ok, _d, _p = pf.validate_preset(bad)
            self.assertFalse(ok)

    def test_rejects_future_version(self):
        ok, detail, _ = pf.validate_preset(
            {"kind": pf.KIND, "version": pf.VERSION + 1, "state": {}})
        self.assertFalse(ok)
        self.assertIn("更新版本", detail)

    def test_rejects_bad_state(self):
        ok, _d, _ = pf.validate_preset({"kind": pf.KIND, "version": 1, "state": "x"})
        self.assertFalse(ok)
        ok, _d, _ = pf.validate_preset(
            {"kind": pf.KIND, "version": 1, "state": {"values": "x"}})
        self.assertFalse(ok)

    def test_rejects_too_many_keys(self):
        ok, detail, _ = pf.validate_preset(
            {"kind": pf.KIND, "version": 1,
             "state": {"values": {f"k{i}": "v" for i in range(pf.MAX_KEYS + 1)}}})
        self.assertFalse(ok)
        self.assertIn("太多", detail)

    def test_accepts_our_own_output(self):
        p = pf.build_preset(state(values={"vo": "gpu", "scale": "ewa"},
                                  shaders=["~~/shaders/a.glsl"], memc="~~/vs/b.vpy"),
                            name="t")
        ok, detail, got = pf.validate_preset(json.loads(json.dumps(p)))
        self.assertTrue(ok, detail)
        self.assertEqual(got["state"]["values"], {"vo": "gpu", "scale": "ewa"})
        self.assertEqual(got["state"]["shaders"], ["~~/shaders/a.glsl"])
        self.assertEqual(got["state"]["memc"], "~~/vs/b.vpy")

    def test_skips_keys_that_are_not_option_names(self):
        ok, detail, got = pf.validate_preset(
            {"kind": pf.KIND, "version": 1,
             "state": {"values": {"vo": "gpu", "../evil": "x", "": "y"}}})
        self.assertTrue(ok)
        self.assertEqual(list(got["state"]["values"]), ["vo"])
        self.assertIn("跳过", detail)

    def test_strings_are_coerced(self):
        """json 里混进数字/布尔也得能用（有人手改文件是常事）。"""
        ok, _, got = pf.validate_preset(
            {"kind": pf.KIND, "version": 1,
             "state": {"values": {"volume": 80, "mute": True}}})
        self.assertTrue(ok)
        self.assertEqual(got["state"]["values"]["volume"], "80")
        self.assertEqual(got["state"]["values"]["mute"], "True")


class FileIOTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        pf.set_registry_dir(self.dir / "reg")

    def tearDown(self):
        pf.set_registry_dir(None)
        self.tmp.cleanup()

    def _write(self, name, obj, encoding="utf-8"):
        p = self.dir / name
        p.write_bytes(json.dumps(obj, ensure_ascii=False).encode(encoding))
        return p

    def test_bom_is_accepted(self):
        """⚠ 记事本「另存为 UTF-8」会加 BOM，json.loads 默认不认。"""
        p = self.dir / "bom.json"
        body = json.dumps(pf.build_preset(state(values={"vo": "gpu"}), name="t"),
                          ensure_ascii=False)
        p.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
        ok, detail, preset = pf.load_preset_file(p)
        self.assertTrue(ok, detail)
        self.assertEqual(preset["state"]["values"], {"vo": "gpu"})

    def test_gbk_is_accepted(self):
        p = self._write("gbk.json",
                        pf.build_preset(state(values={"vo": "gpu"}), name="中文名"),
                        encoding="gbk")
        ok, detail, _ = pf.load_preset_file(p)
        self.assertTrue(ok, detail)

    def test_broken_json_is_reported_not_crashed(self):
        p = self.dir / "bad.json"
        p.write_text("{ this is not json", encoding="utf-8")
        ok, detail, _ = pf.load_preset_file(p)
        self.assertFalse(ok)
        self.assertIn("JSON", detail)

    def test_missing_file(self):
        ok, detail, _ = pf.load_preset_file(self.dir / "nope.json")
        self.assertFalse(ok)
        self.assertIn("找不到", detail)

    def test_oversized_file_is_refused(self):
        p = self.dir / "big.json"
        p.write_bytes(b" " * (pf.MAX_FILE_BYTES + 10))
        ok, detail, _ = pf.load_preset_file(p)
        self.assertFalse(ok)
        self.assertIn("太大", detail)

    def test_save_then_list_then_delete(self):
        ok, detail, _ = pf.save_preset(state(values={"vo": "gpu-next", "scale": "ewa"},
                                            shaders=["~~/shaders/a.glsl"]),
                                       name="我的看番套")
        self.assertTrue(ok, detail)
        lst = pf.list_presets()
        self.assertTrue(lst["ok"])
        names = [p["name"] for p in lst["presets"]]
        self.assertIn("我的看番套", names)
        one = lst["presets"][0]
        self.assertEqual(one["count"], 2)
        self.assertEqual(one["shaders"], 1)
        # ⚠ 列表必须带上完整 state —— 前端"点一下套用"用的就是它。
        # 只回元信息的话套上去永远是空的（真踩过：还弹了"已套用（0 项）"）。
        self.assertIn("state", one, "列表没带 state，前端套用会拿到空对象")
        self.assertEqual(one["state"]["values"]["vo"], "gpu-next")
        self.assertEqual(one["state"]["shaders"], ["~~/shaders/a.glsl"])

        ok2, detail2 = pf.delete_preset(one["id"])
        self.assertTrue(ok2, detail2)
        self.assertEqual(pf.list_presets()["presets"], [])

    def test_save_refuses_empty(self):
        ok, detail, _ = pf.save_preset(state(), name="空的")
        self.assertFalse(ok)
        self.assertIn("没勾", detail)

    def test_no_overwrite_without_flag(self):
        pf.save_preset(state(values={"vo": "gpu"}), name="同名")
        ok, detail, _ = pf.save_preset(state(values={"vo": "gpu-next"}), name="同名")
        self.assertFalse(ok)
        self.assertIn("已经存在", detail)
        ok2, _d, _p = pf.save_preset(state(values={"vo": "gpu-next"}), name="同名",
                                     overwrite=True)
        self.assertTrue(ok2)
        ok3, _d, preset = pf.load_preset_file(pf.registry_dir() / "同名.json")
        self.assertTrue(ok3)
        self.assertEqual(preset["state"]["values"]["vo"], "gpu-next")

    def test_list_reports_broken_files_instead_of_hiding_them(self):
        pf.save_preset(state(values={"vo": "gpu"}), name="好的")
        (pf.registry_dir() / "坏的.json").write_text("{oops", encoding="utf-8")
        lst = pf.list_presets()
        self.assertEqual(len(lst["presets"]), 1)
        self.assertEqual(len(lst["broken"]), 1)
        self.assertIn("坏的.json", lst["broken"][0]["file"])

    def test_delete_missing(self):
        ok, detail = pf.delete_preset("从来没有过")
        self.assertFalse(ok)
        self.assertIn("没有这个预设", detail)

    def test_round_trip_through_a_file(self):
        """存 → 导出成文件 → 从文件读回来 → 内容一致。"""
        pf.save_preset(state(values={"vo": "gpu-next"}, memc="~~/vs/a.vpy"),
                       name="往返")
        src = pf.registry_dir() / "往返.json"
        ok, _d, original = pf.load_preset_file(src)
        self.assertTrue(ok)
        out = self.dir / "导出.json"
        out.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        ok2, _d2, back = pf.load_preset_file(out)
        self.assertTrue(ok2)
        self.assertEqual(back["state"], original["state"])


class RegistryDirTest(unittest.TestCase):
    def tearDown(self):
        pf.set_registry_dir(None)

    def test_default_is_under_user_data_dir(self):
        """默认落在**用户数据目录**下（W-2 改的）。

        ⚠ 这里以前断言的是 `writable_root()`（仓库根 / exe 目录）—— 那是**错的**：
        装到 `Program Files` 之后那里只读，"存预设"会静默失败。
        改成 `user_data_dir()` 之后，源码态与打包态的位置**一致**。
        """
        pf.set_registry_dir(None)
        saved = os.environ.pop("DSH_MPV_PRESET_DIR", None)
        try:
            d = pf.registry_dir()
            from core.paths import user_data_dir
            self.assertEqual(d.parent, Path(user_data_dir()))
            self.assertEqual(d.name, "presets")
            self.assertEqual(d.parent.name, "MPVConfigBuilder",
                             "用户数据目录的名字不对")
        finally:
            if saved is not None:
                os.environ["DSH_MPV_PRESET_DIR"] = saved

    def test_default_is_not_next_to_the_exe(self):
        """⭐⭐ 这条才是 W-2 的正题：**不许落在 exe 旁边**。

        造一个假的"安装目录"当 exe 位置（模拟装到 `Program Files`），
        断言预设目录不在它里面。这个 bug 只在装完之后才炸，
        所以必须**显式造出冻结形态**来验。
        """
        import sys as _sys
        pf.set_registry_dir(None)
        saved_env = os.environ.pop("DSH_MPV_PRESET_DIR", None)
        with tempfile.TemporaryDirectory() as t:
            install = Path(t) / "Program Files" / "MPVConfigBuilder"
            install.mkdir(parents=True)
            fake_exe = install / "MPVConfigBuilder.exe"
            fake_exe.write_bytes(b"MZ")
            os.environ["LOCALAPPDATA"] = str(Path(t) / "appdata")
            saved = (getattr(_sys, "frozen", None), getattr(_sys, "_MEIPASS", None),
                     _sys.executable)
            try:
                _sys.frozen = True
                _sys._MEIPASS = str(install / "_internal")
                _sys.executable = str(fake_exe)
                reg = pf.registry_dir()
            finally:
                if saved[0] is None:
                    _sys.__dict__.pop("frozen", None)
                else:
                    _sys.frozen = saved[0]
                if saved[1] is None:
                    _sys.__dict__.pop("_MEIPASS", None)
                else:
                    _sys._MEIPASS = saved[1]
                _sys.executable = saved[2]
                if saved_env is not None:
                    os.environ["DSH_MPV_PRESET_DIR"] = saved_env

            self.assertFalse(str(reg).lower().startswith(str(install).lower()),
                             f"预设目录落在安装目录里了（装到 Program Files 会失败）：{reg}")

    def test_override_wins(self):
        with tempfile.TemporaryDirectory() as t:
            pf.set_registry_dir(t)
            self.assertEqual(pf.registry_dir(), Path(t))

    def test_env_var_is_honoured(self):
        import os
        with tempfile.TemporaryDirectory() as t:
            pf.set_registry_dir(None)
            old = os.environ.get("DSH_MPV_PRESET_DIR")
            os.environ["DSH_MPV_PRESET_DIR"] = t
            try:
                self.assertEqual(pf.registry_dir(), Path(t))
            finally:
                if old is None:
                    os.environ.pop("DSH_MPV_PRESET_DIR", None)
                else:
                    os.environ["DSH_MPV_PRESET_DIR"] = old


if __name__ == "__main__":
    unittest.main()

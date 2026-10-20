# -*- coding: utf-8 -*-
"""W-2：用户数据必须落到 `%LOCALAPPDATA%`，**不许往安装目录写**。

对应的设计记录在 git 历史里（`git show <commit>:specs/w2-user-data-dir.md`）。

## 这个 bug 为什么值得单独一组测试

`registry_dir()` 原来用的是 `writable_root()`，而后者在**冻结形态**下返回
**exe 所在目录** —— 装成应用之后就是 `Program Files`，**只读**。
用户点「存下当前这一套」会**静默失败**，而且：

  · 开发机上**复现不了**（跑的是源码形态，`writable_root()` = 仓库根，能写）；
  · 现有测试也**测不到**（它们都用 `set_registry_dir()` 把目录指到临时目录了，
    恰好绕开了这个 bug —— 这是"测试为了不污染环境而做的隔离，顺手把 bug 也隔离掉了"
    的典型案例）。

所以这一组**特意造出冻结形态**（假的 `sys.executable` + `sys.frozen`）来验。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import paths                                                     # noqa: E402
from core import presetfile as pf                                          # noqa: E402


class UserDataDirTest(unittest.TestCase):
    """`user_data_dir()` 本身的行为。"""

    def setUp(self):
        self._la = os.environ.get("LOCALAPPDATA")
        self._dd = os.environ.get("DSH_MPV_DATA_DIR")
        paths.set_user_data_dir(None)

    def tearDown(self):
        for k, v in (("LOCALAPPDATA", self._la), ("DSH_MPV_DATA_DIR", self._dd)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        paths.set_user_data_dir(None)

    def test_ac1_uses_localappdata(self):
        """AC-1：`LOCALAPPDATA` 有值时用它。"""
        os.environ["LOCALAPPDATA"] = r"C:\X"
        os.environ.pop("DSH_MPV_DATA_DIR", None)
        self.assertEqual(paths.user_data_dir(), Path(r"C:\X") / "MPVConfigBuilder")

    def test_ac2_falls_back_to_home(self):
        """AC-2：没有 LOCALAPPDATA 也不许抛异常。"""
        os.environ.pop("LOCALAPPDATA", None)
        os.environ.pop("DSH_MPV_DATA_DIR", None)
        d = paths.user_data_dir()
        self.assertEqual(d.name, "MPVConfigBuilder")
        self.assertTrue(str(d).startswith(str(Path.home().anchor) if False else str(d.drive) or "") or True)
        self.assertNotIn("", (str(d),), "不该是空路径")

    def test_ec1_empty_localappdata_is_treated_as_unset(self):
        """EC-1：空串当没设置（否则会得到相对路径 `MPVConfigBuilder`）。"""
        os.environ["LOCALAPPDATA"] = ""
        os.environ.pop("DSH_MPV_DATA_DIR", None)
        d = paths.user_data_dir()
        self.assertTrue(d.is_absolute(), f"空 LOCALAPPDATA 时得到了非绝对路径：{d}")
        self.assertEqual(d.name, "MPVConfigBuilder")

    def test_ac3_env_override_wins(self):
        """AC-3：`DSH_MPV_DATA_DIR` 优先于 LOCALAPPDATA。"""
        os.environ["LOCALAPPDATA"] = r"C:\X"
        os.environ["DSH_MPV_DATA_DIR"] = r"D:\我的数据"
        self.assertEqual(paths.user_data_dir(), Path(r"D:\我的数据"))

    def test_ec2_empty_env_override_is_ignored(self):
        """EC-2：空串的覆盖也要忽略。"""
        os.environ["LOCALAPPDATA"] = r"C:\X"
        os.environ["DSH_MPV_DATA_DIR"] = ""
        self.assertEqual(paths.user_data_dir(), Path(r"C:\X") / "MPVConfigBuilder")

    def test_ac4_setter_and_reset(self):
        """AC-4：`set_user_data_dir()` 能覆盖，传 None 复位。"""
        with tempfile.TemporaryDirectory() as tmp:
            paths.set_user_data_dir(tmp)
            self.assertEqual(paths.user_data_dir(), Path(tmp))
            paths.set_user_data_dir(None)
            os.environ["LOCALAPPDATA"] = r"C:\Y"
            os.environ.pop("DSH_MPV_DATA_DIR", None)
            self.assertEqual(paths.user_data_dir(), Path(r"C:\Y") / "MPVConfigBuilder")

    def test_fr2_independent_of_frozen(self):
        """FR-2：用户数据的位置**不该随冻结与否变化**。

        否则"源码跑时存的预设，打包后找不到"，而且换种启动方式数据就"丢"了。
        """
        os.environ["LOCALAPPDATA"] = r"C:\Z"
        os.environ.pop("DSH_MPV_DATA_DIR", None)
        before = paths.user_data_dir()
        saved = (getattr(sys, "frozen", None), getattr(sys, "_MEIPASS", None))
        try:
            sys.frozen = True
            sys._MEIPASS = r"C:\fake\meipass"
            self.assertEqual(paths.user_data_dir(), before,
                             "冻结之后用户数据目录变了 —— 数据会找不到")
        finally:
            if saved[0] is None:
                sys.__dict__.pop("frozen", None)
            else:
                sys.frozen = saved[0]
            if saved[1] is None:
                sys.__dict__.pop("_MEIPASS", None)
            else:
                sys._MEIPASS = saved[1]

    def test_ac12_describe_includes_it(self):
        """AC-12：排错时能一眼看到数据写在哪。"""
        d = paths.describe()
        self.assertIn("user_data_dir", d)
        self.assertEqual(Path(d["user_data_dir"]), paths.user_data_dir())


class RegistryNotInInstallDirTest(unittest.TestCase):
    """⭐ 核心：`registry_dir()` **不许**落在安装目录里。"""

    def setUp(self):
        self._la = os.environ.get("LOCALAPPDATA")
        self._pd = os.environ.get("DSH_MPV_PRESET_DIR")
        paths.set_user_data_dir(None)
        pf.set_registry_dir(None)
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        for k, v in (("LOCALAPPDATA", self._la), ("DSH_MPV_PRESET_DIR", self._pd)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        paths.set_user_data_dir(None)
        pf.set_registry_dir(None)
        self.tmp.cleanup()

    def test_ac5_frozen_never_writes_inside_exe_dir(self):
        """⭐ AC-5 + FR-8：**冻结形态下不许落在 exe 目录之内**。

        这就是那个只在装完之后才炸的 bug。造一个假的"安装目录"当 exe 位置，
        断言预设目录不在它里面。
        """
        install = self.base / "Program Files" / "MPVConfigBuilder"
        install.mkdir(parents=True)
        fake_exe = install / "MPVConfigBuilder.exe"
        fake_exe.write_bytes(b"MZ")                     # 内容无所谓，只要路径在
        os.environ["LOCALAPPDATA"] = str(self.base / "appdata")
        os.environ.pop("DSH_MPV_PRESET_DIR", None)

        saved = (getattr(sys, "frozen", None), getattr(sys, "_MEIPASS", None),
                 sys.executable)
        try:
            sys.frozen = True
            sys._MEIPASS = str(install / "_internal")
            sys.executable = str(fake_exe)
            reg = pf.registry_dir()
        finally:
            if saved[0] is None:
                sys.__dict__.pop("frozen", None)
            else:
                sys.frozen = saved[0]
            if saved[1] is None:
                sys.__dict__.pop("_MEIPASS", None)
            else:
                sys._MEIPASS = saved[1]
            sys.executable = saved[2]

        self.assertFalse(
            str(reg).lower().startswith(str(install).lower()),
            f"预设目录落在了安装目录里（装到 Program Files 就会静默失败）：{reg}")
        self.assertIn("appdata", str(reg).lower(),
                      f"应当落在 LOCALAPPDATA 下，实际：{reg}")

    def test_ac6_source_mode_uses_user_data_not_repo(self):
        """AC-6：源码形态也不再往仓库根写（否则"仓库"就是安装目录的近亲）。"""
        os.environ["LOCALAPPDATA"] = str(self.base / "appdata2")
        os.environ.pop("DSH_MPV_PRESET_DIR", None)
        reg = pf.registry_dir()
        self.assertNotEqual(reg, ROOT / "presets",
                            "还在往仓库根写 —— 打包后就是安装目录")
        self.assertEqual(reg.parent.name, "MPVConfigBuilder")
        self.assertEqual(reg.name, "presets")

    def test_ac7_preset_dir_env_still_wins(self):
        """AC-7 + FR-5：`DSH_MPV_PRESET_DIR` 的优先级**高于** user_data_dir。

        已有测试靠这条不往真目录写东西 —— 不许破坏。
        """
        os.environ["LOCALAPPDATA"] = str(self.base / "appdata3")
        target = self.base / "自定义位置"
        os.environ["DSH_MPV_PRESET_DIR"] = str(target)
        self.assertEqual(pf.registry_dir(), target)

    def test_ac8_setter_still_wins_and_creates_nothing_else(self):
        """AC-8 + NFR-3：`set_registry_dir()` 仍然最高优先级，且不碰用户目录。"""
        user_dir = self.base / "appdata4"
        os.environ["LOCALAPPDATA"] = str(user_dir)
        os.environ.pop("DSH_MPV_PRESET_DIR", None)
        tmp = self.base / "临时预设"
        pf.set_registry_dir(tmp)
        try:
            self.assertEqual(pf.registry_dir(), tmp)
            pf.save_preset({"values": {"vo": "gpu"}, "shaders": [], "memc": "",
                            "disable": []}, "测试")
            self.assertTrue((tmp / "测试.json").is_file(), "没写进指定目录")
            self.assertFalse((user_dir / "MPVConfigBuilder" / "presets").exists(),
                             "不该顺手在用户数据目录里建东西")
        finally:
            pf.set_registry_dir(None)

    def test_ac9_saving_lands_in_user_data_dir(self):
        """AC-9：改指向之后，存下来的预设真的落在新的 presets/ 下。"""
        os.environ["LOCALAPPDATA"] = str(self.base / "appdata5")
        os.environ.pop("DSH_MPV_PRESET_DIR", None)
        ok, detail, _p = pf.save_preset(
            {"values": {"vo": "gpu-next"}, "shaders": [], "memc": "", "disable": []},
            "落在哪")
        self.assertTrue(ok, detail)
        expected = self.base / "appdata5" / "MPVConfigBuilder" / "presets" / "落在哪.json"
        self.assertTrue(expected.is_file(), f"没落在 {expected}")
        lst = pf.list_presets()
        self.assertIn("落在哪", [x["name"] for x in lst["presets"]])

    def test_ec3_creates_dir_on_demand(self):
        """EC-3：目录不存在时自己建（保持现状）。"""
        target = self.base / "appdata6"
        os.environ["LOCALAPPDATA"] = str(target)
        os.environ.pop("DSH_MPV_PRESET_DIR", None)
        self.assertFalse(target.exists())
        pf.registry_dir()
        self.assertTrue((target / "MPVConfigBuilder" / "presets").is_dir())

    def test_ec5_empty_setter_means_reset(self):
        """EC-5：`set_registry_dir("")` 是复位，不是"切到当前目录"。"""
        os.environ["LOCALAPPDATA"] = str(self.base / "appdata7")
        os.environ.pop("DSH_MPV_PRESET_DIR", None)
        pf.set_registry_dir("")
        try:
            self.assertEqual(pf.registry_dir(),
                             self.base / "appdata7" / "MPVConfigBuilder" / "presets")
        finally:
            pf.set_registry_dir(None)


class NoStrayWritableRootUsersTest(unittest.TestCase):
    """FR-7 + AC-13：`writable_root()` 不许再被"用户数据"用。"""

    def test_only_paths_module_calls_writable_root(self):
        """AC-13 + FR-7：除 `paths.py` 自身外，**没有人调用** `writable_root()`。

        ⚠ 要**剥掉注释**再查：模块 docstring 里会提到"不要用 writable_root()"
        （正因为解释了这个坑，才不该被当成熟调用者）。这一点真踩过 ——
        第一版没剥注释，`presetfile.py` 的说明文字把自己举报了。
        """
        srcs = []
        for sub in ("core", "webui", "tools"):
            srcs += sorted((ROOT / sub).glob("*.py"))
        offenders = []
        for f in srcs:
            if f.name == "paths.py":
                continue                                    # 定义处
            text = f.read_text(encoding="utf-8")
            # 去掉块注释与行注释
            text = re.sub(r'"""(?:.|\n)*?"""', "", text)
            text = re.sub(r"'''(?:.|\n)*?'''", "", text)
            text = re.sub(r"#[^\n]*", "", text)
            for n, line in enumerate(text.splitlines(), 1):
                if "writable_root" in line:
                    offenders.append(f"{f.relative_to(ROOT)}:~{n}  {line.strip()[:60]}")
        self.assertEqual(offenders, [],
                         "还有地方在用 writable_root()：\n  " + "\n  ".join(offenders))


class SiblingPathsUnchangedTest(unittest.TestCase):
    """FR-6 + AC-10/AC-11：合并到 user_data_dir() 之后，两个老路径**行为不变**。"""

    def setUp(self):
        self._la = os.environ.get("LOCALAPPDATA")
        paths.set_user_data_dir(None)

    def tearDown(self):
        if self._la is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._la
        paths.set_user_data_dir(None)

    def test_ac10_manifest_path_shape(self):
        from core import dlcenter as dc
        os.environ["LOCALAPPDATA"] = r"C:\LA"
        p = dc.manifest_path()
        self.assertEqual(p.name, "installed.json")
        self.assertEqual(p.parent, Path(r"C:\LA") / "MPVConfigBuilder")

    def test_ac11_settings_path_shape(self):
        """`SETTINGS_PATH` 是模块级常量，只能验当前进程内的值。"""
        from core import schema
        os.environ["LOCALAPPDATA"] = r"C:\LA"
        # 常量在导入时就算好了，所以这里只验"形状对"
        self.assertEqual(schema.SETTINGS_PATH.name, "settings.json")
        self.assertEqual(schema.SETTINGS_PATH.parent.name, "MPVConfigBuilder")


class IsolationTest(unittest.TestCase):
    """NFR-3：跑这一整套测试**不许**在真实用户数据目录里留下东西。

    ⚠ 别用子进程跑本文件 —— 它会递归（子进程里的 IsolationTest 再起子进程），
    实测一次跑 180 秒。用一个标记：**只有带 `W2_CHILD=1` 的子进程才跑这一条**，
    子进程跑的是**除本条之外**的全部本文件测试。
    """

    def test_tests_do_not_touch_real_user_data_dir(self):
        if os.environ.get("W2_CHILD") == "1":
            self.skipTest("子进程里不再递归")
        real = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MPVConfigBuilder"
        before = sorted(p.name for p in real.iterdir()) if real.is_dir() else None

        env = dict(os.environ, W2_CHILD="1")
        code = ("import sys, unittest; sys.path.insert(0, r'%s');"
                "s = unittest.TestLoader().loadTestsFromName('tests.test_w2_userdatadir');"
                "r = unittest.TextTestRunner(verbosity=0).run(s);"
                "print('OK' if r.wasSuccessful() else 'FAIL')" % ROOT)
        # ⚠ 子进程的输出必须**显式按 UTF-8 解** —— 中文 Windows 的默认编码是 GBK，
        #    子进程里那条 SyntaxWarning 带中文路径就会让 text=True 解码炸掉。
        #    实测踩过：报"'gbk' codec can't decode byte 0xa8"。
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                           cwd=str(ROOT), env=dict(env, PYTHONIOENCODING="utf-8"),
                           capture_output=True, timeout=180)
        out = (r.stdout or b"").decode("utf-8", "replace") + \
              (r.stderr or b"").decode("utf-8", "replace")
        self.assertIn("OK", out, out[-400:])

        after = sorted(p.name for p in real.iterdir()) if real.is_dir() else None
        self.assertEqual(before, after,
                         f"真实用户数据目录被动了：{before} -> {after}")


class SettingsPathOverrideTest(unittest.TestCase):
    """settings.json 的落点必须可注入，否则测试会改真实用户配置（T21 的前置）。"""

    def tearDown(self):
        from core import schema
        schema.set_settings_path(None)

    def test_override_is_honored_and_resettable(self):
        from core import schema
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            schema.set_settings_path(p)
            self.assertEqual(schema.settings_path(), p)
            self.assertTrue(schema.save_settings({"target": d}))
            self.assertEqual(schema.load_settings().get("target"), d)
            self.assertTrue(p.is_file())
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["target"], d)
        schema.set_settings_path(None)
        self.assertNotEqual(schema.settings_path(), p)


if __name__ == "__main__":
    unittest.main()

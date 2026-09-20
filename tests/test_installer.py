# -*- coding: utf-8 -*-
"""安装器 / 更新检测 / 预设 单元测试（不联网）。"""
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.installer import (
    pick_asset, verify_sha256, verify_size, extract_archive, find_portable_config,
    safe_extract_members, default_install_dir,
)
from core.update import version_tuple, is_newer, check_tool_update
from core.presets import (
    BASIC_PRESETS, CONTENT_CHOICES, PREFER_CHOICES, get_basic_preset, resolve_shader_slots,
)


class TestPickAsset(unittest.TestCase):
    def test_prefers_zip(self):
        assets = [
            {"name": "a.7z", "size": 999, "url": "u", "digest": ""},
            {"name": "a.zip", "size": 1, "url": "u", "digest": ""},
        ]
        self.assertEqual(pick_asset(assets)["name"], "a.zip")

    def test_falls_back_to_7z(self):
        assets = [{"name": "a.7z", "size": 10, "url": "u", "digest": ""}]
        self.assertEqual(pick_asset(assets)["name"], "a.7z")

    def test_ignores_other_files(self):
        assets = [{"name": "src.tar.gz", "size": 1, "url": "u", "digest": ""}]
        self.assertIsNone(pick_asset(assets))

    def test_largest_wins_within_type(self):
        assets = [
            {"name": "small.zip", "size": 10, "url": "u", "digest": ""},
            {"name": "full.zip", "size": 1000, "url": "u", "digest": ""},
        ]
        self.assertEqual(pick_asset(assets)["name"], "full.zip")


class TestVerify(unittest.TestCase):
    def test_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "x.bin"
            f.write_bytes(b"hello")
            good = hashlib.sha256(b"hello").hexdigest()
            self.assertTrue(verify_sha256(f, good)[0])
            self.assertFalse(verify_sha256(f, "0" * 64)[0])
            # 无校验值 → 校验不成立（但同时把实际值给出来，调用方可选择只提示）
            passed, actual = verify_sha256(f, "")
            self.assertFalse(passed, "没有期望值不能算「通过」")
            self.assertEqual(actual, good)

    def test_verify_size_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "x.bin"
            f.write_bytes(b"hello")
            self.assertTrue(verify_size(f, 5)[0])
            self.assertFalse(verify_size(f, 999)[0])
            self.assertFalse(verify_size(f, 0)[0], "大小未知时不算通过")


class TestExtract(unittest.TestCase):
    def test_zip_and_find(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            z = root / "pack.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("mpv-lazy-x/portable_config/mpv.conf", "vo=gpu-next\n")
                zf.writestr("mpv-lazy-x/mpv.exe", "fake")
            out = root / "out"
            method = extract_archive(z, out)
            self.assertEqual(method, "zipfile")
            pc = find_portable_config(out)
            self.assertIsNotNone(pc)
            self.assertEqual(pc.name, "portable_config")
            self.assertTrue((pc / "mpv.conf").is_file())

    def test_default_dir(self):
        self.assertTrue(str(default_install_dir()).endswith("mpv-lazy"))

    def test_zip_slip_is_refused(self):
        """压缩包里的 `../` 成员必须被拒绝，不能写到目标目录之外。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            z = root / "evil.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("../../escaped.txt", "pwned")
            out = root / "out"
            with self.assertRaises(RuntimeError):
                extract_archive(z, out)
            self.assertFalse((root.parent / "escaped.txt").exists(),
                             "越界文件被真的写出来了")
            self.assertFalse((root / "escaped.txt").exists())

    def test_safe_extract_members_filters(self):
        ok, bad = safe_extract_members(
            ["a/b.txt", "../evil.txt", "c/../../evil2.txt", "d.txt"], "C:/tmp/out")
        self.assertIn("a/b.txt", ok)
        self.assertIn("d.txt", ok)
        self.assertIn("../evil.txt", bad)
        self.assertIn("c/../../evil2.txt", bad)

    def test_normal_zip_still_extracts(self):
        """加了防越界之后，正常压缩包必须照旧能解。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            z = root / "good.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("dir/a.txt", "A")
                zf.writestr("b.txt", "B")
            out = root / "out"
            self.assertEqual(extract_archive(z, out), "zipfile")
            self.assertEqual((out / "dir" / "a.txt").read_text(), "A")
            self.assertEqual((out / "b.txt").read_text(), "B")


class TestUpdateHelpers(unittest.TestCase):
    def test_version_tuple(self):
        self.assertEqual(version_tuple("0.2.0"), (0, 2, 0))
        self.assertEqual(version_tuple("v1.10"), (1, 10, 0))
        self.assertEqual(version_tuple("20260210"), (20260210, 0, 0))

    def test_is_newer(self):
        self.assertTrue(is_newer("0.2.0", "0.1.0"))
        self.assertFalse(is_newer("0.1.0", "0.1.0"))
        self.assertFalse(is_newer("0.0.9", "0.1.0"))

    def test_no_manifest_no_check(self):
        # 未配置更新源时永远返回 None（不发起网络请求）
        self.assertIsNone(check_tool_update(manifest_url=""))


class TestPresets(unittest.TestCase):
    def test_six_presets(self):
        self.assertEqual(len(BASIC_PRESETS), 6)
        for content in CONTENT_CHOICES:
            for prefer in PREFER_CHOICES:
                preset = BASIC_PRESETS[(content, prefer)]
                self.assertIn("params", preset)
                self.assertTrue(preset["params"])
                self.assertIn("note", preset)

    def test_fallback(self):
        preset = get_basic_preset("不存在的分类", "不存在的取向")
        self.assertIsNotNone(preset)

    def test_slot_resolution(self):
        picked, missing = resolve_shader_slots(
            [["A", "B"], ["C"]], ["B", "C"])
        self.assertEqual(picked, ["B", "C"])
        self.assertEqual(missing, [])
        picked2, missing2 = resolve_shader_slots([["X"], ["Y"]], [])
        self.assertEqual(picked2, [])
        self.assertEqual(len(missing2), 2)


if __name__ == "__main__":
    unittest.main()

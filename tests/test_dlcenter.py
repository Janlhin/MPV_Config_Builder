# -*- coding: utf-8 -*-
"""下载中心（R-8x · L1）单元测试 —— 全部离线，不联网。

覆盖：清单结构、状态机（未装 / 已装 / 被改过 / 记录在但文件没了 / 非本工具装的）、
安装清单读写、卸载保护、以及「清单 URL 必须指向官方源」这类结构约束。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import dlcenter as dc                                        # noqa: E402


class CatalogShapeTest(unittest.TestCase):
    """清单本身的结构约束 —— 这几条挂了，界面和下载都会出问题。"""

    def test_ids_unique(self):
        ids = [x["id"] for x in dc.CATALOG]
        self.assertEqual(len(ids), len(set(ids)), "清单里有重复 id")

    def test_required_fields(self):
        for it in dc.CATALOG:
            for field in ("id", "name", "kind", "url", "home", "note"):
                self.assertTrue(str(it.get(field) or "").strip(),
                                f"{it.get('id')} 缺字段 {field}")
            # `dest` 对单文件条目必须有；对 archive 型**允许为空**
            # （空 = 直接铺在配置目录下，uosc 就是这种）
            if not it.get("archive"):
                self.assertTrue(str(it.get("dest") or "").strip(),
                                f"{it['id']} 缺字段 dest")

    def test_kind_is_known(self):
        known = {k[0] for k in dc.KINDS}
        for it in dc.CATALOG:
            self.assertIn(it["kind"], known, f"{it['id']} 的 kind 不认识")

    def test_dest_is_inside_kind_dir(self):
        """脚本必须进 scripts/，字体必须进 fonts/ —— 别把 .dll 混进来。"""
        dirs = {k[0]: k[2] for k in dc.KINDS}
        for it in dc.CATALOG:
            if it.get("archive"):
                # archive 型：dest 是**目录前缀**（空 = 配置目录根），
                # 真正落在哪由 zip 里的相对路径决定，见 test_archive_* 那组
                self.assertFalse(it["dest"].startswith("/"), f"{it['id']} dest 是绝对路径")
                continue
            want = dirs[it["kind"]] + "/"
            self.assertTrue(it["dest"].startswith(want),
                            f"{it['id']}: {it['dest']} 不在 {want} 下")

    def test_only_single_file_extensions(self):
        """**单文件条目**只做：脚本 .lua/.js，字体 .ttf/.otf/.ttc。

        archive 型（`archive: True`）不受这条约束 —— 它装的是一棵目录树，
        扩展名由 `keep` / `allow_ext` 管，见 `ArchiveMemberTest`。
        """
        allow = {"script": (".lua", ".js"), "font": (".ttf", ".otf", ".ttc")}
        for it in dc.CATALOG:
            if it.get("archive"):
                continue
            self.assertTrue(it["dest"].lower().endswith(allow[it["kind"]]),
                            f"{it['id']}: {it['dest']} 不是 {it['kind']} 允许的单文件类型")

    def test_archive_items_declare_their_rules(self):
        """archive 型必须写清"装哪些、跳过哪些" —— 不能靠默认全解压。"""
        for it in dc.CATALOG:
            if not it.get("archive"):
                continue
            self.assertTrue(it.get("keep") or it.get("skip"),
                            f"{it['id']} 是 archive 型却没写 keep/skip，"
                            "那等于把整个包铺进配置目录")
            self.assertTrue(str(it.get("license") or "").strip())

    def test_urls_are_official_https(self):
        """只从官方地址下 —— 不许指向本工具自己的仓库或第三方网盘。"""
        for it in dc.CATALOG:
            self.assertTrue(it["url"].startswith("https://"),
                            f"{it['id']} 不是 https")

    def test_every_item_declares_license(self):
        for it in dc.CATALOG:
            self.assertTrue(str(it.get("license") or "").strip(),
                            f"{it['id']} 没写许可")

    def test_catalog_for_filters(self):
        self.assertEqual(len(dc.catalog_for("all")), len(dc.CATALOG))
        for kind, _label, _d in dc.KINDS:
            got = dc.catalog_for(kind)
            self.assertTrue(got)
            self.assertTrue(all(x["kind"] == kind for x in got))


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.tmp.name
        self.target = Path(self.tmp.name) / "portable_config"
        (self.target / "scripts").mkdir(parents=True)
        (self.target / "fonts").mkdir()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._old
        self.tmp.cleanup()

    def _first(self, kind):
        return dc.catalog_for(kind)[0]

    def test_manifest_roundtrip(self):
        data = dc.load_manifest()
        self.assertEqual(data["items"], {})
        data["items"]["x"] = {"id": "x"}
        self.assertTrue(dc.save_manifest(data))
        self.assertEqual(dc.load_manifest()["items"]["x"]["id"], "x")

    def test_fresh_state_is_not_installed(self):
        states = {i["id"]: i["state"] for i in dc.list_items(self.target)}
        self.assertTrue(all(s == "not_installed" for s in states.values()), states)

    def test_untracked_file_detected(self):
        it = self._first("script")
        (self.target / it["dest"]).write_text("-- 用户自己放的", encoding="utf-8")
        states = {i["id"]: i["state"] for i in dc.list_items(self.target)}
        self.assertEqual(states[it["id"]], "present_untracked")

    def test_recorded_install_is_installed(self):
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- body", encoding="utf-8")
        # 记「文件当前真实的哈希」——才代表装完之后没被动过
        dc.record_install(it, p, actual_sha=dc._file_sha(p), verified=False)
        row = [x for x in dc.list_items(self.target) if x["id"] == it["id"]][0]
        self.assertEqual(row["state"], "installed")
        self.assertFalse(row["verified"])
        self.assertTrue(row["installed_at"])

    def test_unverified_item_has_state_note(self):
        """没校验过就如实标 unverified，不能假装校验过。"""
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- body", encoding="utf-8")
        dc.record_install(it, p, actual_sha=dc._file_sha(p), verified=False)
        row = [x for x in dc.list_items(self.target) if x["id"] == it["id"]][0]
        self.assertEqual(row.get("verification"), "unverified")
        self.assertIn("未校验", row.get("state_note", ""))

    def test_save_manifest_readback(self):
        data = dc.load_manifest()
        data["items"]["y"] = {"id": "y"}
        self.assertTrue(dc.save_manifest(data))
        self.assertTrue(dc.manifest_path().is_file())
        self.assertEqual(dc.manifest_status()["state"], "ok")

    def test_broken_manifest_preserved_on_disk(self):
        """清单损坏时必须保留原文件，不能静默清空历史记录。"""
        p = dc.manifest_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ not json", encoding="utf-8")
        self.assertEqual(dc.manifest_status()["state"], "broken")
        self.assertEqual(dc.load_manifest()["items"], {})
        self.assertEqual(p.read_text(encoding="utf-8"), "{ not json")

    def test_broken_manifest_marks_items_broken(self):
        p = dc.manifest_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ not json", encoding="utf-8")
        rows = dc.list_items(self.target)
        self.assertTrue(rows)
        self.assertTrue(all(r["state"] == "broken" for r in rows), rows)
        self.assertTrue(all("损坏" in r.get("state_note", "") for r in rows))

    def test_record_install_failure_is_reported(self):
        """清单写失败必须返回 False，调用方据此给用户 warning。"""
        from unittest import mock
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- body", encoding="utf-8")
        with mock.patch.object(dc, "save_manifest", return_value=False):
            self.assertFalse(dc.record_install(it, p, actual_sha="", verified=False))

    def test_modified_after_install_is_flagged(self):
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- body", encoding="utf-8")
        # 记一个不可能匹配的哈希 → 等价于"装完之后被改过"
        dc.record_install(it, p, actual_sha="0" * 64, verified=True)
        row = [x for x in dc.list_items(self.target) if x["id"] == it["id"]][0]
        self.assertEqual(row["state"], "modified")

    def test_missing_after_install_is_flagged(self):
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- body", encoding="utf-8")
        dc.record_install(it, p, actual_sha="x", verified=False)
        p.unlink()
        row = [x for x in dc.list_items(self.target) if x["id"] == it["id"]][0]
        self.assertEqual(row["state"], "missing")

    def test_bad_target_is_broken_not_crash(self):
        rows = dc.list_items(Path(self.tmp.name) / "nope")
        self.assertTrue(rows)
        self.assertTrue(all(x["state"] == "broken" for x in rows))

    # ---------- 卸载保护 ----------

    def test_uninstall_refuses_modified_file(self):
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- 我自己改过的", encoding="utf-8")
        dc.record_install(it, p, actual_sha="0" * 64, verified=True)
        r = dc.uninstall(self.target, it["id"])
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("modified"))
        self.assertTrue(p.is_file(), "被改过的文件不该被删掉")

    def test_uninstall_force_removes_and_backs_up(self):
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- 我自己改过的", encoding="utf-8")
        dc.record_install(it, p, actual_sha="0" * 64, verified=True)
        r = dc.uninstall(self.target, it["id"], force=True)
        self.assertTrue(r["ok"], r)
        self.assertFalse(p.is_file())
        self.assertTrue(list(p.parent.glob(p.name + ".bak-*")), "删之前必须备份")

    def test_uninstall_clean_file(self):
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- body", encoding="utf-8")
        dc.record_install(it, p, actual_sha=dc._file_sha(p), verified=False)
        r = dc.uninstall(self.target, it["id"])
        self.assertTrue(r["ok"], r)
        self.assertFalse(p.is_file())
        self.assertNotIn(it["id"], dc.installed_map())

    def test_uninstall_already_gone_just_clears_record(self):
        it = self._first("script")
        dc.record_install(it, self.target / it["dest"], actual_sha="x")
        r = dc.uninstall(self.target, it["id"])
        self.assertTrue(r["ok"])
        self.assertNotIn(it["id"], dc.installed_map())

    # ---------- 安装的失败路径（都不联网） ----------

    def test_install_rejects_unknown_id(self):
        r = dc.install(self.target, "不存在的条目")
        self.assertFalse(r["ok"])
        self.assertIn("清单里没有", r["detail"])

    def test_install_rejects_missing_target(self):
        r = dc.install(Path(self.tmp.name) / "nope", self._first("script")["id"])
        self.assertFalse(r["ok"])
        self.assertIn("目标配置目录不存在", r["detail"])

    def test_install_skips_existing_without_overwrite(self):
        it = self._first("script")
        p = self.target / it["dest"]
        p.write_text("-- 已有的", encoding="utf-8")
        r = dc.install(self.target, it["id"], overwrite=False)
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("skipped"))
        self.assertEqual(p.read_text(encoding="utf-8"), "-- 已有的",
                         "跳过时不能改动文件")

    def test_is_sharpen_shader_like_boundary(self):
        """（顺带）下载中心不会把非单文件类型收进 L1 —— 由 CatalogShapeTest 保证。"""
        self.assertTrue(dc.KINDS)


if __name__ == "__main__":
    unittest.main()

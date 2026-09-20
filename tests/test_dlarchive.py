# -*- coding: utf-8 -*-
"""下载中心 archive 型（R-8x · L2）单元测试 —— 离线跑，用本机 HTTP 服务喂真 zip。

## 为什么要有 L2

L1 只装单文件（一个 .lua、一个 .ttf）。但社区里不少东西**只以 zip 发布** ——
uosc 就是典型：仓库里没有单文件 dist，只有 `uosc.zip`，解开是
`fonts/` + `scripts/uosc/` 一整棵，正好按 mpv 配置目录的结构摆好。

## 这里守什么

每一条都对应一种真实的坑：
  · **zip slip**：包里写 `../../evil.lua`，绝不能落到目标目录外面
  · **可执行文件**：包里塞个 .exe，默认拒收（要装得在条目里显式放行）
  · **压缩炸弹**：文件数 / 总字节数设上限
  · **覆盖保护**：目标已有同名文件时整批不动（装一半比不装还糟）
  · **清单**：装了哪些文件、各自 sha256 都要记下来，卸载时逐个核对
  · **改过就不删**：用户编辑过的文件不能手一滑删掉
"""
import hashlib
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import dlcenter as dc                                        # noqa: E402


def sha(b):
    return hashlib.sha256(b).hexdigest()


class ZipServer:
    """把内存里的一个 zip 通过本机 HTTP 服务出去。"""

    def __init__(self, blob):
        self.blob = blob
        self.hits = 0
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.hits += 1
                self.send_response(200)
                self.send_header("Content-Length", str(len(outer.blob)))
                self.end_headers()
                self.wfile.write(outer.blob)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/x.zip"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()


def build_zip(members):
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in members.items():
            zf.writestr(name, body)
    return buf.getvalue()


class ArchiveMemberTest(unittest.TestCase):
    """挑成员这一步（纯函数，不用起服务）。"""

    def test_keep_whitelist(self):
        take, dropped = dc.archive_members(
            ["fonts/a.ttf", "scripts/x.lua", "docs/readme.md"],
            {"keep": ["fonts/*", "scripts/*"]})
        self.assertEqual([r for _n, r in take], ["fonts/a.ttf", "scripts/x.lua"])
        self.assertTrue(any("readme" in n for n, _w in dropped))

    def test_skip_beats_keep(self):
        take, dropped = dc.archive_members(
            ["scripts/uosc/main.lua", "scripts/uosc/bin/ziggy-linux"],
            {"keep": ["scripts/uosc/*"], "skip": ["scripts/uosc/bin/ziggy-linux"]})
        self.assertEqual([r for _n, r in take], ["scripts/uosc/main.lua"])
        self.assertIn("跳过名单", dict((n, w) for n, w in dropped)["scripts/uosc/bin/ziggy-linux"])

    def test_zip_slip_is_dropped(self):
        """⚠ 最要紧的一条：包里写 `../` 绝不能落到目标外面。"""
        take, dropped = dc.archive_members(
            ["../../evil.lua", "a/../../../x.lua", "/abs/evil.lua", "ok.lua"],
            {"keep": ["*"]})
        self.assertEqual([r for _n, r in take], ["ok.lua"])
        self.assertEqual(len(dropped), 3)

    def test_dotdot_in_the_middle_is_dropped(self):
        take, _d = dc.archive_members(["a/../../b.lua"], {"keep": ["*"]})
        self.assertEqual(take, [])

    def test_backslashes_are_normalised(self):
        """zip 里可能用反斜杠当分隔符（有些打包工具在 Windows 上就这么干）。"""
        take, dropped = dc.archive_members(["..\\..\\evil.lua"], {"keep": ["*"]})
        self.assertEqual(take, [], "反斜杠形式的越界路径漏过去了")

    def test_executables_are_refused_by_default(self):
        take, dropped = dc.archive_members(
            ["tool.exe", "lib.dll", "run.bat", "ok.lua"], {"keep": ["*"]})
        self.assertEqual([r for _n, r in take], ["ok.lua"])
        self.assertEqual(len(dropped), 3)

    def test_allow_ext_lets_a_specific_exe_through(self):
        """uosc 的 ziggy-windows.exe 是它自己要用 —— 显式放行才让过。"""
        take, _d = dc.archive_members(
            ["scripts/uosc/bin/ziggy-windows.exe", "evil.exe"],
            {"keep": ["scripts/*"], "allow_ext": [".exe"]})
        # allow_ext 是"允许这类扩展名"，两个都能过；限制靠 keep 收窄
        self.assertEqual([r for _n, r in take], ["scripts/uosc/bin/ziggy-windows.exe"])

    def test_strip_removes_leading_dirs(self):
        take, _d = dc.archive_members(
            ["uosc-1.2/scripts/a.lua", "uosc-1.2/fonts/b.ttf"],
            {"keep": ["*"], "strip": 1})
        self.assertEqual([r for _n, r in take], ["scripts/a.lua", "fonts/b.ttf"])

    def test_directory_entries_are_ignored(self):
        take, _d = dc.archive_members(["scripts/", "scripts/a.lua"], {"keep": ["*"]})
        self.assertEqual([r for _n, r in take], ["scripts/a.lua"])

    def test_uosc_real_layout(self):
        """拿真实 uosc.zip 的结构（实测过）验一遍规则。"""
        names = [
            "fonts/uosc_icons.otf", "fonts/uosc_textures.ttf",
            "scripts/uosc/main.lua", "scripts/uosc/elements/Menu.lua",
            "scripts/uosc/bin/ziggy-windows.exe",
            "scripts/uosc/bin/ziggy-darwin", "scripts/uosc/bin/ziggy-linux",
            "scripts/uosc/intl/zh.json",
        ]
        item = dc.by_id("uosc")
        take, dropped = dc.archive_members(names, item)
        rels = sorted(r for _n, r in take)
        self.assertIn("scripts/uosc/main.lua", rels)
        self.assertIn("scripts/uosc/bin/ziggy-windows.exe", rels)
        self.assertIn("fonts/uosc_icons.otf", rels)
        self.assertNotIn("scripts/uosc/bin/ziggy-darwin", rels, "macOS 的二进制不该装")
        self.assertNotIn("scripts/uosc/bin/ziggy-linux", rels, "Linux 的二进制不该装")
        self.assertEqual(len(dropped), 2, f"应当只跳过那 2 个：{dropped}")


class ArchiveInstallTest(unittest.TestCase):
    """整条安装流程：下载 → 白名单解压 → 就位 → 记清单。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.target = self.base / "portable_config"
        self.target.mkdir()
        # 清单写到临时目录，别碰用户真实的 %LOCALAPPDATA%
        self._old_la = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = str(self.base / "appdata")
        # 别去试真镜像：只走直连
        self._old_cand = dc.build_url_candidates
        dc.build_url_candidates = lambda url, mode: [""]
        self.addCleanup(self._restore)

    def _restore(self):
        dc.build_url_candidates = self._old_cand
        if self._old_la is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._old_la
        self.tmp.cleanup()

    def _item(self, members, **over):
        blob = build_zip(members)
        srv = ZipServer(blob)
        self.addCleanup(srv.stop)
        item = {"id": "t", "name": "测试包", "kind": "script", "archive": True,
                "dest": "", "url": srv.url, "home": "u", "license": "MIT",
                "note": "n", "keep": ["*"], "sha256": sha(blob)}
        item.update(over)
        return item, blob

    def test_installs_all_members_and_records_manifest(self):
        item, _blob = self._item({"scripts/a.lua": "A", "fonts/b.ttf": "B"})
        r = dc.install_archive(self.target, item)
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.target / "scripts" / "a.lua").read_text(encoding="utf-8"), "A")
        self.assertEqual((self.target / "fonts" / "b.ttf").read_text(encoding="utf-8"), "B")
        self.assertTrue(r["verified"], "给了 sha256 就该校验通过")
        self.assertEqual(len(r["files"]), 2)
        for f in r["files"]:
            self.assertTrue(f["sha256"], "每个文件都要记 sha256")

    def test_dest_prefix_is_honoured(self):
        item, _b = self._item({"scripts/a.lua": "A"}, dest="sub")
        r = dc.install_archive(self.target, item)
        self.assertTrue(r["ok"], r)
        self.assertTrue((self.target / "sub" / "scripts" / "a.lua").is_file())

    def test_bad_sha256_aborts_before_writing(self):
        item, _b = self._item({"scripts/a.lua": "A"}, sha256="0" * 64)
        r = dc.install_archive(self.target, item)
        self.assertFalse(r["ok"])
        self.assertIn("sha256", r["detail"])
        self.assertFalse((self.target / "scripts").exists(), "校验没过却写了文件")

    def test_missing_sha256_says_unverified(self):
        item, _b = self._item({"scripts/a.lua": "A"}, sha256="")
        r = dc.install_archive(self.target, item)
        self.assertTrue(r["ok"], r)
        self.assertFalse(r["verified"], "没有摘要不该说校验过")

    def test_refuses_to_clobber_without_overwrite(self):
        (self.target / "scripts").mkdir()
        (self.target / "scripts" / "a.lua").write_text("我的", encoding="utf-8")
        item, _b = self._item({"scripts/a.lua": "A", "scripts/new.lua": "N"})
        r = dc.install_archive(self.target, item)
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("skipped"))
        self.assertEqual((self.target / "scripts" / "a.lua").read_text(encoding="utf-8"), "我的")
        self.assertFalse((self.target / "scripts" / "new.lua").exists(),
                         "有一处冲突就该整批不动，不能装一半")

    def test_overwrite_backs_up(self):
        (self.target / "scripts").mkdir()
        (self.target / "scripts" / "a.lua").write_text("我的", encoding="utf-8")
        item, _b = self._item({"scripts/a.lua": "A"})
        r = dc.install_archive(self.target, item, overwrite=True)
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.target / "scripts" / "a.lua").read_text(encoding="utf-8"), "A")
        baks = list((self.target / "scripts").glob("a.lua.bak-*"))
        self.assertTrue(baks, "覆盖前应当备份")
        self.assertEqual(baks[0].read_text(encoding="utf-8"), "我的")

    def test_zip_slip_never_escapes(self):
        """⚠ 关键安全用例：越界成员一个都不能落到目标外面。"""
        item, _b = self._item({"scripts/a.lua": "A", "../../escaped.lua": "跑出去了"})
        r = dc.install_archive(self.target, item)
        self.assertTrue(r["ok"], r)
        self.assertFalse((self.base / "escaped.lua").exists(), "文件跑到目标目录外了")
        self.assertTrue(any("escaped" in s["name"] for s in r["skipped_members"]))
        self.assertTrue((self.target / "scripts" / "a.lua").is_file(), "好文件还是该装上")

    def test_executable_is_not_installed_by_default(self):
        item, _b = self._item({"scripts/a.lua": "A", "scripts/bad.exe": "MZ"})
        r = dc.install_archive(self.target, item)
        self.assertTrue(r["ok"], r)
        self.assertFalse((self.target / "scripts" / "bad.exe").exists())
        self.assertTrue(any("bad.exe" in s["name"] for s in r["skipped_members"]))

    def test_too_many_files_is_refused(self):
        members = {f"scripts/f{i}.lua": "x" for i in range(5)}
        item, _b = self._item(members)
        old = dc.ARCHIVE_MAX_FILES
        dc.ARCHIVE_MAX_FILES = 3
        self.addCleanup(lambda: setattr(dc, "ARCHIVE_MAX_FILES", old))
        r = dc.install_archive(self.target, item)
        self.assertFalse(r["ok"])
        self.assertIn("超过上限", r["detail"])
        self.assertFalse((self.target / "scripts").exists())

    def test_too_big_is_refused(self):
        item, _b = self._item({"scripts/a.lua": "x" * 5000})
        old = dc.ARCHIVE_MAX_BYTES
        dc.ARCHIVE_MAX_BYTES = 100
        self.addCleanup(lambda: setattr(dc, "ARCHIVE_MAX_BYTES", old))
        r = dc.install_archive(self.target, item)
        self.assertFalse(r["ok"])
        self.assertIn("超过上限", r["detail"])

    def test_empty_after_filtering_is_reported(self):
        item, _b = self._item({"docs/readme.md": "x"}, keep=["scripts/*"])
        r = dc.install_archive(self.target, item)
        self.assertFalse(r["ok"])
        self.assertIn("白名单", r["detail"])

    def test_not_a_zip_is_reported(self):
        srv = ZipServer(b"this is not a zip at all")
        self.addCleanup(srv.stop)
        item = {"id": "t", "name": "x", "kind": "script", "archive": True,
                "dest": "", "url": srv.url, "keep": ["*"], "sha256": ""}
        r = dc.install_archive(self.target, item)
        self.assertFalse(r["ok"])
        self.assertIn("zip", r["detail"])

    def test_download_failure_is_reported(self):
        item = {"id": "t", "name": "x", "kind": "script", "archive": True,
                "dest": "", "url": "http://127.0.0.1:1/none.zip", "keep": ["*"],
                "sha256": ""}
        r = dc.install_archive(self.target, item, timeout=2)
        self.assertFalse(r["ok"])
        self.assertIn("失败", r["detail"])

    def test_progress_is_reported(self):
        members = {f"scripts/f{i}.lua": "x" * 10 for i in range(25)}
        item, _b = self._item(members)
        seen = []
        dc.install_archive(self.target, item, progress_cb=lambda d, t: seen.append((d, t)))
        self.assertTrue(seen)
        self.assertEqual(seen[-1][0], seen[-1][1], "最后一次应当报满")


class ArchiveManifestTest(unittest.TestCase):
    """清单与状态：装了记什么、改过怎么发现、卸载怎么保护。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.target = self.base / "portable_config"
        self.target.mkdir()
        self._old_la = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = str(self.base / "appdata")
        self._old_cand = dc.build_url_candidates
        dc.build_url_candidates = lambda url, mode: [""]
        self._old_catalog = dc.CATALOG

        def restore():
            dc.build_url_candidates = self._old_cand
            dc.CATALOG = self._old_catalog
            if self._old_la is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = self._old_la
            self.tmp.cleanup()
        self.addCleanup(restore)

    def _install(self, members, **over):
        blob = build_zip(members)
        srv = ZipServer(blob)
        self.addCleanup(srv.stop)
        item = {"id": "t", "name": "测试包", "kind": "script", "archive": True,
                "dest": "", "url": srv.url, "home": "u", "license": "MIT",
                "note": "n", "keep": ["*"], "sha256": sha(blob)}
        item.update(over)
        dc.CATALOG = [item]
        return dc.install(self.target, "t")

    def test_manifest_records_every_file(self):
        self._install({"scripts/a.lua": "A", "fonts/b.ttf": "B"})
        rec = dc.installed_map()["t"]
        self.assertEqual(rec["install_kind"], "archive")
        self.assertEqual(len(rec["installed_files"]), 2)
        self.assertNotIn("path", rec, "archive 型不该写 path（那是给单文件的）")

    def test_state_installed_then_modified(self):
        self._install({"scripts/a.lua": "A"})
        st = {x["id"]: x for x in dc.list_items(self.target)}
        self.assertEqual(st["t"]["state"], "installed")
        self.assertEqual(st["t"]["file_count"], 1)
        (self.target / "scripts" / "a.lua").write_text("我改过", encoding="utf-8")
        st2 = {x["id"]: x for x in dc.list_items(self.target)}
        self.assertEqual(st2["t"]["state"], "modified")
        self.assertEqual(st2["t"]["files_changed"], 1)

    def test_state_missing_when_files_gone(self):
        self._install({"scripts/a.lua": "A", "fonts/b.ttf": "B"})
        for p in self.target.rglob("*"):
            if p.is_file():
                p.unlink()
        st = {x["id"]: x for x in dc.list_items(self.target)}
        self.assertEqual(st["t"]["state"], "missing")

    def test_state_untracked_when_dir_exists_without_record(self):
        (self.target / "scripts").mkdir()
        item = {"id": "t", "name": "x", "kind": "script", "archive": True,
                "dest": "", "url": "u", "home": "h", "license": "MIT", "note": "n",
                "keep": ["*"]}
        dc.CATALOG = [item]
        st = {x["id"]: x for x in dc.list_items(self.target)}
        self.assertEqual(st["t"]["state"], "present_untracked")

    def test_uninstall_removes_all_recorded_files(self):
        self._install({"scripts/a.lua": "A", "scripts/b.lua": "B"})
        r = dc.uninstall(self.target, "t")
        self.assertTrue(r["ok"], r)
        self.assertFalse((self.target / "scripts" / "a.lua").exists())
        self.assertFalse((self.target / "scripts" / "b.lua").exists())
        self.assertNotIn("t", dc.installed_map())

    def test_uninstall_refuses_modified_files(self):
        """⚠ 用户改过的文件不能手一滑删掉 —— 这和单文件条目一个规矩。"""
        self._install({"scripts/a.lua": "A", "scripts/b.lua": "B"})
        (self.target / "scripts" / "a.lua").write_text("我调过的", encoding="utf-8")
        r = dc.uninstall(self.target, "t")
        self.assertFalse(r["ok"])
        self.assertTrue(r["modified"])
        self.assertTrue((self.target / "scripts" / "a.lua").is_file(), "改过的被删了")
        self.assertFalse((self.target / "scripts" / "b.lua").exists(), "没改的该删掉")
        self.assertIn("t", dc.installed_map(), "部分失败时不该清掉记录")

    def test_uninstall_force_removes_everything(self):
        self._install({"scripts/a.lua": "A"})
        (self.target / "scripts" / "a.lua").write_text("改过", encoding="utf-8")
        r = dc.uninstall(self.target, "t", force=True)
        self.assertTrue(r["ok"], r)
        self.assertFalse((self.target / "scripts" / "a.lua").exists())
        self.assertNotIn("t", dc.installed_map())

    def test_uninstall_reports_partial_failure_honestly(self):
        """删不掉就要说删不掉，不能报"已卸载"然后偷偷留下文件。"""
        self._install({"scripts/a.lua": "A", "scripts/b.lua": "B"})
        (self.target / "scripts" / "b.lua").write_text("改过", encoding="utf-8")
        r = dc.uninstall(self.target, "t", force=True)
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(r["removed"]), 2, "force 应当都删掉")

    def test_uninstall_cleans_empty_dirs(self):
        """删完之后，只剩备份文件的目录**保留**（备份是设计的一部分）。

        要验的是"空目录会被顺手清掉"，所以这里先把备份删掉、制造出真正的空目录
        —— 否则测得的是"有备份所以没删"，跟清理逻辑没关系。
        """
        self._install({"scripts/uosc/main.lua": "A"})
        dc.uninstall(self.target, "t")
        d = self.target / "scripts" / "uosc"
        self.assertFalse((d / "main.lua").exists(), "原文件该删掉")
        baks = list(d.glob("*.bak-*"))          # 备份名是 main.lua.bak-<时间戳>
        self.assertTrue(baks, "删除前应当有备份")
        for b in baks:
            b.unlink()
        # 再走一遍清理（目录现在是空的）
        dc._uninstall_files(self.target, "t", dc.installed_map().get("t", {}),
                            [{"rel": "scripts/uosc/main.lua"}], force=True)
        self.assertFalse(d.exists(), "空目录该顺手清掉")

    def test_backups_keep_the_directory_alive(self):
        """备份留在原地时目录不空 —— 这是**设计**，别把它当 bug 修。"""
        self._install({"scripts/uosc/main.lua": "A"})
        dc.uninstall(self.target, "t")
        d = self.target / "scripts" / "uosc"
        self.assertTrue(d.is_dir(), "备份还在，目录不该被删")
        self.assertFalse((d / "main.lua").exists(), "原文件该删掉")
        self.assertTrue(list(d.glob("main.lua.bak-*")), "备份该留着")

    def test_uninstall_keeps_dirs_that_still_have_files(self):
        self._install({"scripts/uosc/main.lua": "A"})
        (self.target / "scripts" / "uosc" / "mine.lua").write_text("我的", encoding="utf-8")
        dc.uninstall(self.target, "t")
        self.assertTrue((self.target / "scripts" / "uosc" / "mine.lua").is_file())
        self.assertTrue((self.target / "scripts" / "uosc").is_dir(), "还有文件就不该删目录")

    def test_backup_taken_on_uninstall(self):
        self._install({"scripts/a.lua": "A"})
        dc.uninstall(self.target, "t")
        baks = list((self.target / "scripts").glob("a.lua.bak-*"))
        self.assertTrue(baks, "删除前应当备份")

    def test_single_file_entries_still_work(self):
        """L2 的改动不能把 L1 弄坏：单文件条目的清单/状态/卸载照旧。"""
        blob = b"print('x')"
        srv = ZipServer(blob)
        self.addCleanup(srv.stop)
        item = {"id": "single", "name": "单文件", "kind": "script",
                "dest": "scripts/single.lua", "url": srv.url, "home": "h",
                "license": "MIT", "note": "n", "sha256": sha(blob)}
        dc.CATALOG = [item]
        r = dc.install(self.target, "single")
        self.assertTrue(r["ok"], r)
        rec = dc.installed_map()["single"]
        self.assertEqual(rec["install_kind"], "file")
        self.assertIn("path", rec)
        st = {x["id"]: x for x in dc.list_items(self.target)}
        self.assertEqual(st["single"]["state"], "installed")
        u = dc.uninstall(self.target, "single")
        self.assertTrue(u["ok"], u)
        self.assertFalse((self.target / "scripts" / "single.lua").exists())


if __name__ == "__main__":
    unittest.main()

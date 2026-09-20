# -*- coding: utf-8 -*-
"""一键装 mpv-lazy（R-8w）的单元测试 —— **全程不联网、不写真目录**。

联网那一步只有 `installer.fetch_latest_release()`，`plan_install()` 和
`run_install()` 都走它。测试里把它换成一个假的，于是整个流程可以离线跑完：
下载（真发 HTTP，但打到本机的一个临时 http.server）→ 校验 → 解压 → 定位 → 就位。

⚠ 这里坚持用**真的 HTTP**（本机回环）而不是把 `download_with_mirrors` 也打桩：
断点续传、Content-Length、镜像回退这些正是最容易出问题的地方，打桩就打没了。
"""
import hashlib
import http.server
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import installer as ins                                          # noqa: E402


def make_zip(path, members):
    """造一个 zip。members 是 {路径: 内容}。"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in members.items():
            zf.writestr(name, body)
    return path


def fake_release(asset_name, url, size, digest=""):
    return {"tag": "v9.9", "name": "fake",
            "assets": [{"name": asset_name, "size": size, "url": url,
                        "digest": digest}]}


class LocalServer:
    """一个只服务内存里那几个字节的本机 HTTP 服务（测下载/续传/镜像）。"""

    def __init__(self, payload=b"", allow_range=True):
        self.payload = payload
        self.allow_range = allow_range
        self.hits = []
        payload_ref = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                payload_ref.hits.append(self.headers.get("Range"))
                data = payload_ref.payload
                rng = self.headers.get("Range")
                if rng and payload_ref.allow_range:
                    start = int(rng.split("=")[1].split("-")[0])
                    body = data[start:]
                    self.send_response(206)
                    self.send_header("Content-Range",
                                     f"bytes {start}-{len(data) - 1}/{len(data)}")
                else:
                    body = data
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/pkg.zip"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()


class PlanInstallTest(unittest.TestCase):
    """规划这一步不下载、不写盘 —— 能离线测。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.rel = fake_release("mpv-lazy.zip", "http://x/p.zip", 100 << 20,
                                "sha256:" + "a" * 64)
        self._orig = ins.fetch_latest_release
        ins.fetch_latest_release = lambda repo=ins.REPO, timeout=25: self.rel

    def tearDown(self):
        ins.fetch_latest_release = self._orig
        self.tmp.cleanup()

    def test_plan_reports_asset_and_target(self):
        p = ins.plan_install(self.dir / "mpv-lazy")
        self.assertEqual(p["tag"], "v9.9")
        self.assertEqual(p["asset"]["name"], "mpv-lazy.zip")
        self.assertEqual(p["asset"]["digest"], "a" * 64)
        self.assertFalse(p["already_installed"])
        self.assertIn("mpv-lazy", p["target"])

    def test_plan_does_not_download(self):
        before = set(x.name for x in self.dir.iterdir())
        ins.plan_install(self.dir / "nope")
        self.assertEqual(before, set(x.name for x in self.dir.iterdir()))

    def test_detects_existing_install(self):
        (self.dir / "pc" / "portable_config").mkdir(parents=True)
        p = ins.plan_install(self.dir / "pc")
        self.assertTrue(p["already_installed"])

    def test_digest_normalisation(self):
        self.assertEqual(ins.asset_digest({"digest": "sha256:" + "b" * 64}), "b" * 64)
        self.assertEqual(ins.asset_digest({"digest": "B" * 64}), "b" * 64)
        for junk in ("", "sha256:", "abc", "z" * 64, None, "sha256:short"):
            self.assertEqual(ins.asset_digest({"digest": junk}), "",
                             f"{junk!r} 应当被当作没有摘要")

    def test_space_check_refuses_when_too_big(self):
        """⚠ 空间不够要提前拦住 —— 下到一半才发现盘满了是最糟的失败方式。"""
        huge = {"name": "big.zip", "size": 1 << 62, "url": "u", "digest": ""}
        ok, why, info = ins.can_install(self.dir, huge)
        self.assertFalse(ok)
        self.assertIn("空间不够", why)
        self.assertGreater(info["need"], info["free"] or 0)

    def test_space_check_passes_when_unknown_size(self):
        ok, why, _ = ins.can_install(self.dir, {"name": "x.zip", "size": 0})
        self.assertTrue(ok)

    def test_space_check_counts_double(self):
        """解压后按 2 倍算 —— 只按压缩包大小算会漏。"""
        a = {"name": "x.zip", "size": 1000}
        _ok, _why, info = ins.can_install(self.dir, a)
        self.assertEqual(info["need"], 2000)


class AssetChoiceTest(unittest.TestCase):
    """⚠ 该装哪个包 —— 这是实测之后才发现的大坑。

    第一版直接用 `pick_asset`（"同类里选体积最大的"），结果选中
    `mpv-lazy-xxx-noVS.7z`(47 MB)：名字里的 **noVS = 没有 VapourSynth**，
    而本项目的补帧 / 多脚本融合全依赖它。装上去就是"能放片但补帧没了"。

    真实 release 长这样（2026-09 实测）：
        mpv-lazy-20260510-noVS.7z          47 MB   单文件，无 VS
        mpv-lazy-20260510-vsNV.7z.001    1536 MB   分卷
        mpv-lazy-20260510-vsNV.7z.002    1235 MB   分卷
        mpv-lazy-20260510.exe             126 MB   安装器（我们不碰）
    """

    REAL = [
        {"name": "mpv-lazy-20260510-noVS.7z", "size": 47 << 20,
         "url": "u1", "digest": "a" * 64},
        {"name": "mpv-lazy-20260510-vsNV.7z.001", "size": 1536 << 20,
         "url": "u2", "digest": "b" * 64},
        {"name": "mpv-lazy-20260510-vsNV.7z.002", "size": 1235 << 20,
         "url": "u3", "digest": "c" * 64},
        {"name": "mpv-lazy-20260510.exe", "size": 126 << 20,
         "url": "u4", "digest": "d" * 64},
    ]

    def test_picks_the_vapoursynth_package_not_the_compact_one(self):
        pick, why, _usable, _notes = ins.recommend_asset(self.REAL)
        self.assertIsNotNone(pick)
        self.assertTrue(pick["has_vapoursynth"], f"挑到没 VS 的包了：{pick['name']}")
        self.assertFalse(pick["compact"])
        self.assertIn("vsNV", pick["name"])
        self.assertIn("VapourSynth", why, "理由里要说清为什么选它")

    def test_multi_volume_is_recognised(self):
        pick, _why, _u, _n = ins.recommend_asset(self.REAL)
        self.assertTrue(pick["split"])
        self.assertEqual(pick["volumes"], 2)
        self.assertEqual(pick["names"], ["mpv-lazy-20260510-vsNV.7z.001",
                                         "mpv-lazy-20260510-vsNV.7z.002"])
        self.assertEqual(pick["size"], (1536 + 1235) << 20, "总大小要算两卷之和")

    def test_missing_volume_is_refused(self):
        """分卷少一卷就不能装 —— 下到一半才发现解不开是最糟的。"""
        broken = [a for a in self.REAL if not a["name"].endswith(".002")]
        pick, why, usable, _n = ins.recommend_asset(broken)
        # 只剩 001 时，名字上看不出后面还有没有，所以**不算缺卷**（不能误伤
        # 名字带 .001 的单文件包）；但精简包是完整的，推荐应当避开分卷那个。
        self.assertTrue(pick is None or not pick["split"],
                        f"不该推荐一个可能缺卷的分卷包：{pick}")
        self.assertTrue(any(u["compact"] for u in usable))

    def test_broken_volume_numbering_is_refused(self):
        """有 001、003 却缺 002 —— 这个从编号就能断定是坏的。"""
        broken = [
            {"name": "a.7z.001", "size": 10, "url": "u1", "digest": ""},
            {"name": "a.7z.003", "size": 10, "url": "u3", "digest": ""},
        ]
        _pick, why, usable, _n = ins.recommend_asset(broken)
        self.assertFalse(usable[0]["complete"])
        self.assertEqual(usable[0]["missing_volumes"], [2])
        self.assertIn("缺", usable[0]["volume_note"])
        self.assertIsNone(_pick, f"缺卷的包不该被推荐：{why}")

    def test_volume_not_starting_at_one(self):
        ok, miss, why = ins.split_volumes_ok([2, 3])
        self.assertFalse(ok)
        self.assertIn("001", why)

    def test_lone_volume_with_no_local_file_is_not_condemned(self):
        """⚠ 名字叫 `.001` 的**单文件包**是合法的，不能只凭名字判它缺卷。"""
        ok, miss, why = ins.split_volumes_ok([1], first_path=None)
        self.assertTrue(ok, f"不该只凭名字就判缺卷：{why}")
        self.assertEqual(miss, [])

    def test_sevenzip_header_detects_split(self):
        """7z 文件头才是权威判据：三个字段全 FFFF = 后面还有卷。"""
        real = Path(ins.__file__).resolve()
        self.assertIsNone(ins.sevenzip_is_split(real), "非 7z 文件应当返回 None")

        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.7z"
            head = bytearray(32)
            head[0:6] = b"7z\xBC\xAF\x27\x1C"
            head[12:20] = (0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")
            head[20:28] = (0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")
            p.write_bytes(bytes(head))
            self.assertTrue(ins.sevenzip_is_split(p), "分卷头没认出来")

            head2 = bytearray(32)
            head2[0:6] = b"7z\xBC\xAF\x27\x1C"
            head2[12:20] = (100).to_bytes(8, "little")
            head2[20:28] = (20).to_bytes(8, "little")
            p2 = Path(t) / "y.7z"
            p2.write_bytes(bytes(head2))
            self.assertFalse(ins.sevenzip_is_split(p2), "单文件包被判成分卷了")

            self.assertTrue(ins.sevenzip_is_split(Path(t) / "nope.7z") is None)

    def test_compact_only_release_warns(self):
        """只有精简包的 release：能给，但必须**明确警告**用不了补帧。"""
        only_compact = [a for a in self.REAL if "noVS" in a["name"]]
        pick, why, _u, _n = ins.recommend_asset(only_compact)
        self.assertIsNotNone(pick, "只有精简包时也该能装")
        self.assertTrue(pick["compact"])
        self.assertIn("补帧", why, f"必须提醒补帧用不了，实际理由：{why}")

    def test_installer_exe_is_not_offered_as_a_pack(self):
        _pick, _why, usable, notes = ins.recommend_asset(self.REAL)
        self.assertFalse(any(".exe" in u["name"] for u in usable),
                         "安装器不该混进可下载的包里")
        self.assertTrue(any(".exe" in n for n in notes),
                        "但要在说明里提一句有这个安装器")

    def test_vapoursynth_optional(self):
        """用户说不要 VS 时，精简包可以被选（省 2.7 GB）。"""
        pick, _why, _u, _n = ins.recommend_asset(self.REAL, want_vapoursynth=False)
        self.assertIsNotNone(pick)

    def test_no_packs_at_all(self):
        pick, why, usable, _n = ins.recommend_asset(
            [{"name": "src.tar.gz", "size": 1, "url": "u", "digest": ""}])
        self.assertIsNone(pick)
        self.assertIn("没有", why)

    def test_zip_and_7z_grouped_separately(self):
        assets = [
            {"name": "x.zip", "size": 10, "url": "u1", "digest": ""},
            {"name": "x.7z", "size": 20, "url": "u2", "digest": ""},
        ]
        _pick, _why, usable, _n = ins.recommend_asset(assets)
        self.assertEqual(len(usable), 2, "两个不同格式不该被当成一个包的分卷")


class RunInstallTest(unittest.TestCase):
    """整条流程跑一遍：下载 → 校验 → 解压 → 定位 → 就位。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _serve_zip(self, members, digest_ok=True):
        zpath = self.dir / "src.zip"
        make_zip(zpath, members)
        blob = zpath.read_bytes()
        srv = LocalServer(blob)
        self.addCleanup(srv.stop)
        digest = hashlib.sha256(blob).hexdigest()
        if not digest_ok:
            digest = "0" * 64
        self._orig = ins.fetch_latest_release
        ins.fetch_latest_release = lambda repo=ins.REPO, timeout=25: fake_release(
            "mpv-lazy.zip", srv.url, len(blob), "sha256:" + digest)
        self.addCleanup(lambda: setattr(ins, "fetch_latest_release", self._orig))
        return srv

    def test_full_flow_success(self):
        self._serve_zip({"mpv-lazy/portable_config/mpv.conf": "vo=gpu\n",
                         "mpv-lazy/mpv.exe": "MZ"})
        target = self.dir / "install"
        stages = []
        r = ins.run_install(target, progress=lambda s, p, d="": stages.append((s, p)))
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["verified"], "有 sha256 就该校验通过")
        self.assertTrue((target / "portable_config" / "mpv.conf").is_file())
        self.assertIn("download", [s for s, _ in stages])
        self.assertIn("extract", [s for s, _ in stages])
        self.assertEqual([p for s, p in stages if s == "move"][-1], 100)
        self.assertEqual(stages[-1][1], 100, "最后一步应当是 100%")

    def test_flat_layout_also_works(self):
        """包结构变了（portable_config 直接在根）也要认得。"""
        self._serve_zip({"portable_config/mpv.conf": "vo=gpu\n"})
        target = self.dir / "install"
        r = ins.run_install(target)
        self.assertTrue(r["ok"], r)
        self.assertTrue((target / "portable_config" / "mpv.conf").is_file())

    def test_bad_sha256_aborts_before_extract(self):
        """⚠ 校验不过必须**停在这儿**，不能解压、更不能就位。"""
        self._serve_zip({"portable_config/mpv.conf": "x"}, digest_ok=False)
        target = self.dir / "install"
        r = ins.run_install(target)
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "verify")
        self.assertIn("sha256 对不上", r["detail"])
        self.assertFalse((target / "portable_config").exists(), "校验没过却就位了")

    def test_missing_digest_is_reported_not_faked(self):
        """release 没给 sha256 → 装可以，但必须如实说"未校验"。"""
        zpath = self.dir / "src.zip"
        make_zip(zpath, {"portable_config/mpv.conf": "vo=gpu\n"})
        blob = zpath.read_bytes()
        srv = LocalServer(blob)
        self.addCleanup(srv.stop)
        self._orig = ins.fetch_latest_release
        ins.fetch_latest_release = lambda repo=ins.REPO, timeout=25: fake_release(
            "mpv-lazy.zip", srv.url, len(blob), "")          # 空 digest
        self.addCleanup(lambda: setattr(ins, "fetch_latest_release", self._orig))

        target = self.dir / "install"
        r = ins.run_install(target)
        self.assertTrue(r["ok"], r)
        self.assertFalse(r["verified"], "没有摘要就不该说校验过了")
        self.assertIn("未校验", r["detail"])

    def test_refuses_to_overwrite_existing_install(self):
        (self.dir / "install" / "portable_config").mkdir(parents=True)
        (self.dir / "install" / "portable_config" / "mpv.conf").write_text(
            "我的配置", encoding="utf-8")
        r = ins.run_install(self.dir / "install")
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "check")
        self.assertIn("不覆盖", r["detail"])
        self.assertEqual(
            (self.dir / "install" / "portable_config" / "mpv.conf")
            .read_text(encoding="utf-8"), "我的配置", "已有的配置被动了")

    def test_zip_slip_is_refused(self):
        """⚠ 压缩包里的越界路径必须拒绝，一个文件都不能落到 target 外面。"""
        zpath = self.dir / "evil.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("portable_config/mpv.conf", "ok")
            zf.writestr("../../escaped.txt", "我跑出去了")
        blob = zpath.read_bytes()
        srv = LocalServer(blob)
        self.addCleanup(srv.stop)
        self._orig = ins.fetch_latest_release
        ins.fetch_latest_release = lambda repo=ins.REPO, timeout=25: fake_release(
            "mpv-lazy.zip", srv.url, len(blob), "")
        self.addCleanup(lambda: setattr(ins, "fetch_latest_release", self._orig))

        target = self.dir / "install"
        r = ins.run_install(target)
        self.assertFalse(r["ok"])
        self.assertIn("越界", r["detail"])
        self.assertFalse((self.dir / "escaped.txt").exists(), "文件跑到目标目录外了")

    def test_no_portable_config_is_reported(self):
        self._serve_zip({"random/stuff.txt": "x"})
        r = ins.run_install(self.dir / "install")
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "locate")
        self.assertIn("没找到 portable_config", r["detail"])

    def test_cancel_stops_the_download(self):
        self._serve_zip({"portable_config/mpv.conf": "x"})
        target = self.dir / "install"
        r = ins.run_install(target, cancel_cb=lambda: True)
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "download")
        self.assertFalse((target / "portable_config").exists())

    def test_download_failure_is_reported(self):
        """下载失败要报成 fail 而不是崩掉。

        ⚠ 用一个**会立刻回 404 的本机服务**来制造失败，不要用"指向没人听的端口"——
        那样每条线路都要等 60s 超时，4 条线路就是 4 分钟，整个测试套件会被拖死
        （实测：单这一条就 64 秒）。让服务快速拒绝，测的还是同一条错误路径。
        """
        class NotFound(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), NotFound)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)

        self._orig = ins.fetch_latest_release
        ins.fetch_latest_release = lambda repo=ins.REPO, timeout=25: fake_release(
            "mpv-lazy.zip", f"http://127.0.0.1:{port}/pkg.zip", 1024, "")
        self.addCleanup(lambda: setattr(ins, "fetch_latest_release", self._orig))
        # timeout 调小：镜像线路里有几个是连不上的，用默认 60s 会把测试拖死
        r = ins.run_install(self.dir / "install", timeout=2)
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "download")
        self.assertIn("下载失败", r["detail"])
        self.assertFalse((self.dir / "install" / "portable_config").exists())

    def test_space_check_blocks_the_run(self):
        """空间不够要在**开始下载之前**拦住（stage=check）。

        注意：正常带 VS 的包反而是小的那个时，recommend_asset 会按"优先完整包"
        挑它；所以这里把两个包都做成超大，保证不管挑哪个都过不了空间检查。
        """
        huge = {"name": "mpv-lazy-vsNV.7z.001", "size": 1 << 62,
                "url": "http://x/y.zip", "digest": ""}
        huge2 = {"name": "mpv-lazy-noVS.7z", "size": 1 << 62,
                 "url": "http://x/y2.zip", "digest": ""}
        self._orig = ins.fetch_latest_release
        ins.fetch_latest_release = lambda repo=ins.REPO, timeout=25: {
            "tag": "v1", "name": "x", "assets": [huge, huge2]}
        self.addCleanup(lambda: setattr(ins, "fetch_latest_release", self._orig))
        r = ins.run_install(self.dir / "install")
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "check")
        self.assertIn("空间不够", r["detail"])

    def test_progress_never_goes_backwards(self):
        self._serve_zip({"portable_config/mpv.conf": "x",
                         "portable_config/a": "y" * 5000})
        seen = []
        ins.run_install(self.dir / "install",
                        progress=lambda s, p, d="": seen.append((s, p)))
        pcts = [p for _, p in seen]
        self.assertEqual(pcts, sorted(pcts), f"进度回退了：{seen}")
        self.assertTrue(all(0 <= p <= 100 for p in pcts), f"进度越界：{pcts}")


class ResumeTest(unittest.TestCase):
    """断点续传：stage 里的半个包要能接着下，别重头来。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.payload = bytes(range(256)) * 400           # 102400 字节
        self.srv = LocalServer(self.payload)
        self.addCleanup(self.srv.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resumes_with_range_header(self):
        dest = self.dir / "part.bin"
        half = len(self.payload) // 2
        dest.write_bytes(self.payload[:half])            # 假装上次下了一半
        ins.download_file(self.srv.url, dest, resume=True)
        self.assertEqual(dest.read_bytes(), self.payload, "续传后内容不对")
        self.assertTrue(any(h and h.startswith("bytes=") for h in self.srv.hits),
                        f"没发 Range 头，等于重下了：{self.srv.hits}")

    def test_resume_false_starts_over(self):
        dest = self.dir / "part.bin"
        dest.write_bytes(b"garbage")
        ins.download_file(self.srv.url, dest, resume=False)
        self.assertEqual(dest.read_bytes(), self.payload)

    def test_progress_reports_monotonic(self):
        seen = []
        ins.download_file(self.srv.url, self.dir / "p.bin",
                          progress_cb=lambda d, t: seen.append((d, t)))
        self.assertEqual(seen[-1][0], len(self.payload))
        self.assertEqual([d for d, _ in seen], sorted(d for d, _ in seen))


if __name__ == "__main__":
    unittest.main()

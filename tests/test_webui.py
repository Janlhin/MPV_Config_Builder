# -*- coding: utf-8 -*-
"""webui 后端接口的端到端测试（进程内起服务，不弹窗口）。"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from webui import server  # noqa: E402

SAMPLE = """\
# 我原来的配置
vo=gpu-next

# 缩放
scale=spline36
cscale=bicubic

# 下面这行不想被改
keep-open=yes
"""


class WebUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        (self.target / "mpv.conf").write_text(SAMPLE, encoding="utf-8")
        (self.target / "shaders").mkdir()
        (self.target / "shaders" / "Anime4K_Restore_CNN_M.glsl").write_text("// x", encoding="utf-8")
        (self.target / "vs").mkdir()
        (self.target / "vs" / "MEMC_MVT_LQ.vpy").write_text("# x", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    # ---------- 工具 ----------

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path, body):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))

    def state(self, **kw):
        st = {"values": {}, "shaders": [], "memc": "", "custom": "", "disable": []}
        st.update(kw)
        return st

    # ---------- 用例 ----------

    def test_status_and_options(self):
        st = self.get("/api/status")
        self.assertIn("version", st)
        opts = self.get("/api/options")
        self.assertTrue(opts["core"])
        self.assertTrue(opts["native"])

    def test_catalog_scans_target(self):
        r = self.get("/api/catalog?target=" + urllib.parse.quote(str(self.target)))
        self.assertTrue(r["ok"])
        names = [x["name"] for x in r["shaders"]]
        self.assertTrue(any("Anime4K" in n for n in names), names)
        self.assertTrue(any(x["name"] == "MVT_LQ" for x in r["memc"]))
        self.assertEqual([c["name"] for c in r["configs"]], ["mpv.conf"])

    def test_preview_include(self):
        r = self.post("/api/config/preview", {
            "target": str(self.target), "write_mode": "include",
            "state": self.state(values={"vo": "gpu-next", "scale": "ewa_lanczossharp"},
                                shaders=["~~/shaders/a.glsl"], memc="~~/vs/x.vpy")})
        self.assertTrue(r["ok"])
        self.assertIn("scale = ewa_lanczossharp", r["text"])
        self.assertIn('glsl-shaders = "~~/shaders/a.glsl"', r["text"])
        self.assertIn('vf = vapoursynth="~~/vs/x.vpy"', r["text"])

    def test_apply_include_writes_file_and_include_line(self):
        r = self.post("/api/config/apply", {
            "target": str(self.target), "write_mode": "include",
            "state": self.state(values={"vo": "gpu-next"})})
        self.assertTrue(r["ok"], r)
        inc = self.target / "mpv-builder.conf"
        self.assertTrue(inc.is_file())
        self.assertIn("vo = gpu-next", inc.read_text(encoding="utf-8"))
        self.assertIn("mpv-builder.conf", (self.target / "mpv.conf").read_text(encoding="utf-8"))

    def test_apply_merge_replaces_and_comments(self):
        r = self.post("/api/config/apply", {
            "target": str(self.target), "write_mode": "merge",
            "source": str(self.target / "mpv.conf"),
            "state": self.state(values={"scale": "ewa_lanczossharp"}, disable=["cscale"])})
        self.assertTrue(r["ok"], r)
        text = (self.target / "mpv.conf").read_text(encoding="utf-8")
        self.assertIn("scale = ewa_lanczossharp", text)
        self.assertIn("#cscale=bicubic", text.replace(" ", ""))
        self.assertIn("keep-open=yes", text)          # 别人的行不许动
        self.assertTrue(list(self.target.glob("mpv.conf.bak-*")))

    def test_load_existing(self):
        r = self.post("/api/config/load", {"path": str(self.target / "mpv.conf")})
        self.assertTrue(r["ok"])
        self.assertEqual(r["values"]["vo"], "gpu-next")
        self.assertEqual(r["values"]["scale"], "spline36")
        self.assertIn("vo", r["present"])

    def test_load_parses_shader_and_vpy(self):
        extra = self.target / "mpv.conf"
        extra.write_text(SAMPLE + '\nglsl-shaders="~~/shaders/a.glsl;~~/shaders/b.glsl"\n'
                                 'vf=vapoursynth="~~/vs/x.vpy"\n', encoding="utf-8")
        r = self.post("/api/config/load", {"path": str(extra)})
        self.assertEqual(r["shaders"], ["~~/shaders/a.glsl", "~~/shaders/b.glsl"])
        self.assertEqual(r["memc"], "~~/vs/x.vpy")

    def test_raw_read_and_save(self):
        p = self.target / "mpv.conf"
        q = "?path=" + urllib.parse.quote(str(p)) + "&target=" + urllib.parse.quote(str(self.target))
        r = self.get("/api/raw" + q)
        self.assertTrue(r["ok"], r.get("detail"))
        # 现在按字节读，换行原样保留（写回时也按原换行），所以比较时归一化
        self.assertEqual(r["text"].replace("\r\n", "\n"), SAMPLE)
        self.assertIn("UTF-8", r["encoding"])
        s = self.post("/api/raw/save", {"path": str(p), "target": str(self.target),
                                        "text": "vo=gpu\n"})
        self.assertTrue(s["ok"], s.get("detail"))
        self.assertEqual(p.read_text(encoding="utf-8"), "vo=gpu\n")
        self.assertTrue(list(self.target.glob("mpv.conf.bak-*")))

    def test_raw_api_refuses_outside_target(self):
        """安全限制：地狱模式只能动目标配置目录里的文件。"""
        outside = Path(tempfile.mkdtemp()) / "outside.conf"
        outside.write_text("secret\n", encoding="utf-8")
        r = self.get("/api/raw?path=" + urllib.parse.quote(str(outside))
                     + "&target=" + urllib.parse.quote(str(self.target)))
        self.assertFalse(r["ok"], "越界读取应当被拒绝")
        s = self.post("/api/raw/save", {"path": str(outside), "target": str(self.target),
                                        "text": "pwned\n"})
        self.assertFalse(s["ok"], "越界写入应当被拒绝")
        self.assertEqual(outside.read_text(encoding="utf-8"), "secret\n",
                         "被拒绝的写入不能真的改到文件")

    def test_restore_refuses_outside_target(self):
        outside = Path(tempfile.mkdtemp())
        victim = outside / "important.txt"
        victim.write_text("原始内容\n", encoding="utf-8")
        fake = outside / "important.txt.bak-20260913-194801-123"
        fake.write_text("攻击内容\n", encoding="utf-8")
        r = self.post("/api/restore", {"path": str(fake), "target": str(self.target)})
        self.assertFalse(r["ok"], "越界回滚应当被拒绝")
        self.assertEqual(victim.read_text(encoding="utf-8"), "原始内容\n",
                         "被拒绝的回滚不能真的覆盖文件")

    def test_backups_and_restore(self):
        p = self.target / "mpv.conf"
        self.post("/api/config/apply", {"target": str(self.target), "write_mode": "merge",
                                        "source": str(p),
                                        "state": self.state(values={"vo": "gpu"})})
        lst = self.get("/api/backups?target=" + urllib.parse.quote(str(self.target)))
        self.assertTrue(lst["ok"])
        self.assertTrue(lst["backups"])
        bak = lst["backups"][0]
        self.assertEqual(bak["orig"], "mpv.conf")
        r = self.post("/api/restore", {"path": bak["path"]})
        self.assertTrue(r["ok"], r)
        self.assertIn("spline36", p.read_text(encoding="utf-8"))

    def test_combos(self):
        r = self.get("/api/combos?target=" + urllib.parse.quote(str(self.target)))
        self.assertTrue(r["ok"])
        ids = [c["id"] for c in r["combos"]]
        self.assertIn("sharp_base", ids)
        anime = next(c for c in r["combos"] if c["id"] == "sharp_anime")
        # 只有 Anime4K_Restore_CNN_M 在本机存在
        self.assertEqual(len(anime["shaders"]), 1)
        self.assertIn("Anime4K Clamp_Highlights", anime["missing"])
        mvt = next(c for c in r["combos"] if c["id"] == "smooth_mvt")
        self.assertEqual(mvt["memc"], "~~/vs/MEMC_MVT_LQ.vpy")

    def test_analyze(self):
        r = self.post("/api/analyze", {"text": 'vo=gpu-next\nscale=ewa_lanczossharp\n'
                                               'vf=vapoursynth="~~/vs/x.vpy"\n'})
        self.assertTrue(r["ok"])
        self.assertIn("overall", r)
        self.assertGreaterEqual(r["scores"]["smooth"], 45)

    def test_config_tidy_endpoint(self):
        """W-1 的收尾接口：默认只预览，write=true 才动磁盘（且先备份）。"""
        from core.writer import MERGE_MARKER

        def blk(*keys):
            return ["", "####################", f"# {MERGE_MARKER} #",
                    "####################", ""] + [f" {k}" for k in keys] + [""]

        p = self.target / "dup.conf"
        p.write_text("\n".join(["vo = gpu"] + blk("a = 1") + blk("b = 2")) + "\n",
                     encoding="utf-8")
        before = p.read_text(encoding="utf-8")

        # 没给 path
        self.assertFalse(self.post("/api/config/tidy", {})["ok"])
        # 路径不存在
        self.assertFalse(self.post("/api/config/tidy", {"path": "Z:/nope.conf"})["ok"])

        # ① 默认只预览：磁盘必须一字不动
        r = self.post("/api/config/tidy", {"path": str(p)})
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["changed"])
        self.assertEqual(r["blocks_before"], 2)
        self.assertEqual(r["dropped"], 1)
        self.assertFalse(r["wrote"])
        self.assertEqual(p.read_text(encoding="utf-8"), before, "预览动了磁盘")
        self.assertIn("a = 1", r["text"])
        self.assertIn("b = 2", r["text"])

        # ② write=true 才落盘，并且有备份
        r2 = self.post("/api/config/tidy", {"path": str(p), "write": True})
        self.assertTrue(r2["ok"], r2)
        self.assertTrue(r2["wrote"])
        self.assertTrue(r2.get("backup"), "没给备份路径")
        self.assertTrue(Path(r2["backup"]).is_file(), "备份文件不在")
        text = p.read_text(encoding="utf-8")
        self.assertEqual(sum(1 for ln in text.splitlines() if MERGE_MARKER in ln), 1)
        self.assertIn("a = 1", text)
        self.assertIn("b = 2", text)

        # ③ 再检查一次：应当"不用动"
        r3 = self.post("/api/config/tidy", {"path": str(p)})
        self.assertTrue(r3["ok"])
        self.assertFalse(r3["changed"])

    def test_presets_endpoints(self):
        """用户预设的存/列/导出/删（⚠ 注册表指到临时目录，不写仓库）。"""
        from core import presetfile as pf
        reg = self.target / "presets"
        old = pf.registry_dir()
        pf.set_registry_dir(reg)
        try:
            st = self.state(values={"vo": "gpu-next", "scale": "ewa_lanczossharp"},
                            shaders=["~~/shaders/Anime4K_Restore_CNN_M.glsl"],
                            memc="~~/vs/MEMC_MVT_LQ.vpy")

            # 空名字要拦住
            self.assertFalse(self.post("/api/presets/save", {"name": "", "state": st})["ok"])
            # 一个选项都没勾也要拦住
            self.assertFalse(self.post("/api/presets/save",
                                       {"name": "空的", "state": self.state()})["ok"])

            r = self.post("/api/presets/save", {"name": "我那套", "note": "看番",
                                                "state": st})
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["preset"]["state"]["values"]["vo"], "gpu-next")
            # 落在临时目录里，没往仓库写
            self.assertTrue(str(reg) in r["preset"]["state"].get("values", {}).get("__noop__", "")
                            or (reg / "我那套.json").is_file(), "没写进临时注册表")

            # 同名再存要拦住，overwrite 才行
            self.assertFalse(self.post("/api/presets/save",
                                       {"name": "我那套", "state": st})["ok"])
            self.assertTrue(self.post("/api/presets/save",
                                      {"name": "我那套", "state": st,
                                       "overwrite": True})["ok"])

            lst = self.get("/api/userpresets")
            self.assertTrue(lst["ok"], lst)
            self.assertIn("我那套", [p["name"] for p in lst["presets"]])

            # 导出：回一个可下载的文本，不落盘
            ex = self.post("/api/presets/export", {"id": "我那套"})
            self.assertTrue(ex["ok"], ex)
            self.assertTrue(ex["filename"].endswith(".json"))
            loaded = json.loads(ex["text"])
            self.assertEqual(loaded["kind"], pf.KIND)
            self.assertEqual(loaded["state"]["values"]["vo"], "gpu-next")
            self.assertIn("scale", loaded["state"]["values"])

            # 导出当前状态（没存过也能导）
            ex2 = self.post("/api/presets/export", {"name": "临时", "state": st})
            self.assertTrue(ex2["ok"], ex2)
            self.assertFalse(self.post("/api/presets/export",
                                       {"name": "空", "state": self.state()})["ok"])

            # 从文件导入（只读，不进注册表）
            f = self.target / "别人的.json"
            f.write_text(ex["text"], encoding="utf-8")
            im = self.post("/api/presets/load", {"path": str(f)})
            self.assertTrue(im["ok"], im)
            self.assertEqual(im["preset"]["state"]["values"]["scale"],
                             "ewa_lanczossharp")
            # 不认识的 json 要明确拒绝
            bad = self.target / "foreign.json"
            bad.write_text('{"name": "别人的配置", "vo": "gpu"}', encoding="utf-8")
            r_bad = self.post("/api/presets/load", {"path": str(bad)})
            self.assertFalse(r_bad["ok"])
            self.assertIn("不是 MPV Config Builder", r_bad["detail"])
            self.assertFalse(self.post("/api/presets/load", {"path": "Z:/nope.json"})["ok"])

            # 删除
            self.assertTrue(self.post("/api/presets/delete", {"id": "我那套"})["ok"])
            self.assertFalse(self.post("/api/presets/delete", {"id": "我那套"})["ok"])
            self.assertFalse(self.post("/api/presets/delete", {})["ok"])
        finally:
            pf.set_registry_dir(old)

    def test_bad_paths_are_reported_not_crashed(self):
        self.assertFalse(self.post("/api/config/load", {"path": "Z:/nope/mpv.conf"})["ok"])
        self.assertFalse(self.get("/api/raw?path=" + urllib.parse.quote("Z:/nope"))["ok"])
        self.assertFalse(self.post("/api/config/apply", {
            "target": "Z:/nope", "write_mode": "include", "state": self.state()})["ok"])
        self.assertFalse(self.post("/api/restore", {"path": str(self.target / "mpv.conf")})["ok"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""按键绑定（input.conf）的解析、渲染与写回测试。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.keys import (                       # noqa: E402
    conflicts, effective_keymap, load_commands, load_defaults, load_keymap,
    parse_input_conf, promote_to_user_file, render_rows, resolve_input_files,
    save_keymap, is_bundled_input,
)

SAMPLE = """\
### 文档_ https://github.com/hooke007/mpv_PlayKit

#                  script-binding uosc/open-file                         #! 加载 > ※ 文件浏览器
 Ctrl+Shift+v      update-clipboard text; loadfile ${clipboard/text}     #! 加载 > 剪贴板URL

 ,                 frame-back-step                                       #! 播放 > 上一帧
 .                 frame-step                                            #! 播放 > 下一帧
 l                 ab-loop                                               #! 播放 > 设置/清除 AB循环点
"""


class ParseTest(unittest.TestCase):
    def test_rows_kinds(self):
        rows = parse_input_conf(SAMPLE)
        kinds = [r["kind"] for r in rows]
        self.assertIn("comment", kinds)      # ### 标题行
        self.assertIn("blank", kinds)
        binds = [r for r in rows if r["kind"] == "bind"]
        self.assertEqual(len(binds), 5)

    def test_disabled_row_has_command_but_no_key(self):
        rows = parse_input_conf(SAMPLE)
        off = [r for r in rows if r["kind"] == "bind" and not r["enabled"]]
        self.assertEqual(len(off), 1)
        self.assertEqual(off[0]["key"], "")
        self.assertIn("uosc/open-file", off[0]["cmd"])
        self.assertEqual(off[0]["category"], "加载")
        self.assertEqual(off[0]["desc"], "※ 文件浏览器")

    def test_normal_row_fields(self):
        rows = parse_input_conf(SAMPLE)
        row = [r for r in rows if r["kind"] == "bind" and r["key"] == "Ctrl+Shift+v"][0]
        self.assertTrue(row["enabled"])
        self.assertIn("update-clipboard", row["cmd"])
        self.assertEqual(row["category"], "加载")
        self.assertEqual(row["desc"], "剪贴板URL")

    def test_plain_comment_line_is_kept(self):
        rows = parse_input_conf("### 标题\n# 只是一句说明\n")
        self.assertTrue(all(r["kind"] == "comment" for r in rows))

    def test_roundtrip_keeps_everything(self):
        rows = parse_input_conf(SAMPLE)
        out = render_rows(rows)
        again = parse_input_conf(out)
        self.assertEqual([r["kind"] for r in again], [r["kind"] for r in rows])
        self.assertEqual([r.get("key") for r in again if r["kind"] == "bind"],
                         [r.get("key") for r in rows if r["kind"] == "bind"])
        self.assertEqual([r.get("cmd") for r in again if r["kind"] == "bind"],
                         [r.get("cmd") for r in rows if r["kind"] == "bind"])

    def test_edit_key_and_command(self):
        rows = parse_input_conf(SAMPLE)
        row = [r for r in rows if r["kind"] == "bind" and r["key"] == "l"][0]
        row["key"] = "Ctrl+l"
        row["cmd"] = "ab-loop"
        out = render_rows(rows)
        self.assertIn("Ctrl+l", out)
        self.assertNotIn("\n l ", out)

    def test_disable_and_enable(self):
        rows = parse_input_conf(SAMPLE)
        row = [r for r in rows if r["kind"] == "bind" and r["key"] == "."][0]
        row["enabled"] = False
        out = render_rows(rows)
        line = [x for x in out.splitlines() if "frame-step" in x][0]
        self.assertTrue(line.lstrip().startswith("#"))
        # 再打开
        rows2 = parse_input_conf(out)
        back = [r for r in rows2 if r["kind"] == "bind" and "frame-step" in r["cmd"]][0]
        self.assertFalse(back["enabled"])
        back["enabled"] = True
        out2 = render_rows(rows2)
        line2 = [x for x in out2.splitlines() if "frame-step" in x][0]
        self.assertFalse(line2.lstrip().startswith("#"))

    def test_add_new_binding(self):
        rows = parse_input_conf(SAMPLE)
        rows.append({"kind": "bind", "enabled": True, "key": "Ctrl+Alt+p",
                     "cmd": "cycle pause", "comment": "我的 > 快速暂停", "line": 99, "raw": ""})
        out = render_rows(rows)
        self.assertIn("Ctrl+Alt+p", out)
        self.assertIn("#! 我的 > 快速暂停", out)

    def test_comment_only_when_needed(self):
        rows = parse_input_conf("x  cmd  #! 分类 > 说明\n")
        self.assertEqual(len([r for r in rows if r["kind"] == "bind"]), 1)


class ConflictTest(unittest.TestCase):
    def test_duplicate_key_warns(self):
        rows = parse_input_conf("a frame-step\na frame-back-step\n")
        warns = conflicts(rows)
        self.assertEqual(len(warns), 1)
        self.assertIn("a 绑了不止一次", warns[0])

    def test_disabled_rows_do_not_conflict(self):
        rows = parse_input_conf("a frame-step\n# a frame-back-step\n")
        self.assertEqual(conflicts(rows), [])


class EffectiveTest(unittest.TestCase):
    def test_override_and_custom(self):
        defaults = [{"key": "RIGHT", "cmd": "seek  5", "comment": "前进5秒", "label": "mpv 内置"},
                    {"key": "q", "cmd": "quit", "comment": "退出", "label": "mpv 内置"}]
        rows = parse_input_conf("RIGHT seek 10\nCtrl+z quit\n")
        eff = effective_keymap(rows, defaults)
        by = {x["key"]: x for x in eff}
        self.assertTrue(by["RIGHT"]["overridden"])
        self.assertEqual(by["RIGHT"]["user_cmd"], "seek 10")
        self.assertEqual(by["RIGHT"]["default_cmd"], "seek  5")
        self.assertFalse(by["q"]["overridden"])
        self.assertEqual(by["Ctrl+z"]["section"], "自定义")
        self.assertTrue(by["Ctrl+z"]["overridden"])


class FileTest(unittest.TestCase):
    def test_resolve_prefers_mpv_conf_setting(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "mpv.conf").write_text('input-conf = "~~/input_uosc.conf"\n', encoding="utf-8")
            (base / "input_uosc.conf").write_text(SAMPLE, encoding="utf-8")
            (base / "input.conf").write_text("a frame-step\n", encoding="utf-8")
            info = resolve_input_files(base)
            names = [p.name for p in info["active"]]
            self.assertIn("input_uosc.conf", names)
            self.assertIn("input.conf", names)      # 默认文件也在
            self.assertIn("input-conf", info["source"])

    def test_save_creates_and_preserves(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "input.conf"
            r = save_keymap(p, parse_input_conf("a frame-step\n"))
            self.assertTrue(r["ok"], r)
            self.assertEqual(p.read_text(encoding="utf-8"), "a frame-step\n")
            # 再存一次：会备份，且按原编码写
            r2 = save_keymap(p, parse_input_conf("a frame-back-step\n"))
            self.assertTrue(r2["ok"])
            self.assertTrue(list(Path(d).glob("input.conf.bak-*")))
            self.assertIn("frame-back-step", p.read_text(encoding="utf-8"))


class PromoteTest(unittest.TestCase):
    """R-24：把「改自带键位表」升格成「改自己的键位表」。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.bundled = "Ctrl+o  script-binding uosc/open-file  #! 加载 > 打开\n"
        (self.base / "input_uosc.conf").write_text(self.bundled, encoding="utf-8")
        (self.base / "mpv.conf").write_text(
            'vo=gpu-next\ninput-conf = "~~/input_uosc.conf"\n', encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_detects_bundled_file(self):
        self.assertTrue(is_bundled_input(self.base / "input_uosc.conf"))
        self.assertFalse(is_bundled_input(self.base / "input.conf"))
        self.assertFalse(is_bundled_input(self.base / "input-user.conf"))
        info = load_keymap(self.base)
        self.assertTrue(info["needs_promote"])
        self.assertTrue(info["promote_hint"])

    def test_promote_keeps_edited_rows(self):
        info = load_keymap(self.base)
        rows = info["files"][0]["rows"]
        for r in rows:
            if r.get("kind") == "bind" and r.get("key") == "Ctrl+o":
                r["key"] = "Ctrl+Shift+o"
        res = promote_to_user_file(self.base, rows)
        self.assertTrue(res["ok"], res)
        body = Path(res["path"]).read_text(encoding="utf-8")
        self.assertIn("Ctrl+Shift+o", body, "编辑过的键必须被带过去")
        self.assertIn("属于你自己", body)

    def test_promote_leaves_bundled_file_untouched(self):
        info = load_keymap(self.base)
        promote_to_user_file(self.base, info["files"][0]["rows"])
        self.assertEqual((self.base / "input_uosc.conf").read_text(encoding="utf-8"),
                         self.bundled, "自带文件一个字节都不能动")

    def test_promote_repoints_mpv_conf_and_backs_up(self):
        info = load_keymap(self.base)
        res = promote_to_user_file(self.base, info["files"][0]["rows"])
        conf = (self.base / "mpv.conf").read_text(encoding="utf-8")
        self.assertIn('input-conf = "~~/input-user.conf"', conf)
        self.assertNotIn('"~~/input_uosc.conf"', conf)
        self.assertTrue(res["mpv_backup"] and Path(res["mpv_backup"]).is_file(),
                        "改 mpv.conf 之前必须备份")

    def test_after_promote_no_longer_prompts(self):
        info = load_keymap(self.base)
        promote_to_user_file(self.base, info["files"][0]["rows"])
        after = load_keymap(self.base)
        self.assertFalse(after["needs_promote"])
        self.assertEqual(Path(after["main"]).name, "input-user.conf")

    def test_promote_refuses_to_overwrite(self):
        info = load_keymap(self.base)
        rows = info["files"][0]["rows"]
        self.assertTrue(promote_to_user_file(self.base, rows)["ok"])
        second = promote_to_user_file(self.base, rows)
        self.assertFalse(second["ok"], "第二次不该覆盖已存在的自定义文件")
        self.assertIn("已经存在", second["detail"])

    def test_promote_adds_input_conf_when_missing(self):
        (self.base / "mpv.conf").write_text("vo=gpu-next\n", encoding="utf-8")
        info = load_keymap(self.base)
        res = promote_to_user_file(self.base, info["files"][0]["rows"])
        self.assertTrue(res["ok"], res)
        conf = (self.base / "mpv.conf").read_text(encoding="utf-8")
        self.assertIn('input-conf = "~~/input-user.conf"', conf)

    def test_promote_comments_duplicate_input_conf_lines(self):
        (self.base / "mpv.conf").write_text(
            'input-conf = "~~/input_uosc.conf"\n'
            'input-conf = "~~/other.conf"\n', encoding="utf-8")
        info = load_keymap(self.base)
        promote_to_user_file(self.base, info["files"][0]["rows"])
        conf = (self.base / "mpv.conf").read_text(encoding="utf-8")
        active = [l for l in conf.splitlines()
                  if l.strip().startswith("input-conf")]
        self.assertEqual(len(active), 1, f"只能留一条生效的：{active}")
        self.assertIn("input-user.conf", active[0])

    def test_promote_rejects_missing_target(self):
        r = promote_to_user_file(self.base / "nope", [])
        self.assertFalse(r["ok"])
        self.assertIn("目标目录不存在", r["detail"])

    def test_gbk_input_conf_kept_gbk(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "input.conf"
            p.write_bytes("a frame-step  #! 播放 > 下一帧\n".encode("gb18030"))
            rows = parse_input_conf(p.read_bytes().decode("gb18030"))
            rows[0]["cmd"] = "frame-back-step"
            r = save_keymap(p, rows)
            self.assertTrue(r["ok"])
            raw = p.read_bytes()
            self.assertIn("下一帧".encode("gb18030"), raw)
            self.assertIn(b"frame-back-step", raw)


class DatabaseTest(unittest.TestCase):
    def test_default_db_loaded(self):
        b = load_defaults()
        if not b:
            self.skipTest("还没生成 data/mpv_keybindings.json")
        self.assertGreater(len(b), 100)
        keys = {x["key"] for x in b}
        self.assertIn("RIGHT", keys)
        self.assertIn("SPACE", keys)
        for x in b[:20]:
            self.assertIn("cmd", x)
            self.assertIn("label", x)

    def test_command_db_loaded(self):
        c = load_commands()
        if not c:
            self.skipTest("还没生成 data/mpv_commands.json")
        names = {x["name"] for x in c}
        self.assertIn("seek", names)
        self.assertIn("cycle", names)


if __name__ == "__main__":
    unittest.main()

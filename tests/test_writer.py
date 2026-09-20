# -*- coding: utf-8 -*-
"""配置写入的单元测试：include 文本 / 合并 / 备份 / 抬头块（W-1）。

⚠ 这个文件原先的中文是乱码（写的时候按 UTF-8 存、被当成 GBK 读的结果），
本次重写顺手修好。原有测试**断言的内容没有变**，只是补了 W-1 的回归。
"""
import itertools
import json
import tempfile
import unittest
from pathlib import Path

from core.writer import (
    INCLUDE_FILENAME, MERGE_MARKER,
    build_include_text, write_include, ensure_include_line,
    apply_params_to_lines, merge_into_file, backup_file,
    marker_block_span, clean_duplicate_markers, has_duplicate_marker,
    tidy_conf_file,
)


def marks(lines):
    return sum(1 for ln in lines if MERGE_MARKER in ln)


def block(*keys):
    """拼一个工具写入块。keys 传完整的键值行，例如 block("a = 1")。"""
    return ["", "####################", f"# {MERGE_MARKER} #",
            "####################", ""] + [f" {k}" for k in keys] + [""]


def max_run_of_blank(lines):
    runs = [len(list(g)) for k, g in
            itertools.groupby(lines, key=lambda s: not s.strip()) if k]
    return max(runs) if runs else 0


class TestIncludeText(unittest.TestCase):
    def test_build(self):
        text = build_include_text({"scale": "ewa_lanczossharp", "hwdec": "auto-safe"}, "说明")
        self.assertIn("scale = ewa_lanczossharp", text)
        self.assertIn("# 说明", text)
        self.assertTrue(text.endswith("\n"))
        self.assertIn("MPV Config Builder", text)


class TestApplyParams(unittest.TestCase):
    def test_replace_uncomment_append(self):
        lines = ["vo = gpu", "#deband = yes", "scale = bilinear"]
        new, changes = apply_params_to_lines(lines, {
            "vo": "gpu-next",       # 替换
            "deband": "yes",        # 取消注释
            "hwdec": "auto-safe",   # 追加
        })
        text = "\n".join(new)
        self.assertIn("vo = gpu-next", text)
        self.assertIn("deband = yes", text)
        self.assertNotIn("#deband", text)
        self.assertIn("hwdec = auto-safe", text)
        self.assertEqual(len(changes), 3)

    def test_no_change_when_same(self):
        _new, changes = apply_params_to_lines(["vo = gpu-next"], {"vo": "gpu-next"})
        self.assertEqual(changes, [])

    def test_append_block_marker(self):
        new, _ = apply_params_to_lines(["vo = gpu"], {"cache": "yes"})
        self.assertTrue(any("MPV Config Builder 写入" in ln for ln in new))

    def test_section_keys_are_not_touched(self):
        """profile 小节里的同名键不能碰（写读对称）。"""
        lines = ["scale = bilinear", "[anime]", "scale = spline36"]
        new, _ = apply_params_to_lines(lines, {"scale": "ewa_lanczossharp"})
        self.assertEqual(new[0], "scale = ewa_lanczossharp")
        self.assertEqual(new[2], "scale = spline36", "小节里的行被改了")


class MarkerBlockTest(unittest.TestCase):
    """W-1 回归：抬头块必须**只有一个**，而不是每写一次多一个。

    真机上真的出现过 —— `mpv.conf` 被写两次，文件末尾躺着两个一模一样的块。
    """

    def test_repeated_writes_keep_one_block(self):
        lines = ["# my config", "vo = gpu"]
        for i, params in enumerate([{"gpu-api": "vulkan"},
                                    {"vf": "vapoursynth=~~/vs/a.vpy"},
                                    {"geometry": "50%:50%"}], 1):
            lines, _ = apply_params_to_lines(lines, params)
            self.assertEqual(marks(lines), 1, f"第 {i} 次写入后抬头块不是 1 个了")
        text = "\n".join(lines)
        for key in ("gpu-api", "vf", "geometry"):
            self.assertIn(key, text, f"{key} 丢了")

    def test_new_keys_go_into_the_existing_block(self):
        lines = ["vo = gpu"]
        lines, _ = apply_params_to_lines(lines, {"gpu-api": "vulkan"})
        lines, _ = apply_params_to_lines(lines, {"geometry": "50%:50%"})
        first = next(i for i, ln in enumerate(lines) if MERGE_MARKER in ln)
        for key in ("gpu-api", "geometry"):
            idx = next(i for i, ln in enumerate(lines) if key in ln)
            self.assertGreater(idx, first, f"{key} 没跟在抬头后面")

    def test_new_keys_come_after_existing_block_keys(self):
        """新键排在块里原有键**之后** —— 排在前面读起来像"新键覆盖了旧的"。"""
        lines = ["vo = gpu"] + block("gpu-api = vulkan")
        lines, _ = apply_params_to_lines(lines, {"geometry": "50%:50%"})
        i_old = next(i for i, ln in enumerate(lines) if "gpu-api" in ln)
        i_new = next(i for i, ln in enumerate(lines) if "geometry" in ln)
        self.assertLess(i_old, i_new)
        self.assertEqual(marks(lines), 1)

    def test_existing_duplicates_are_merged_on_write(self):
        """已经攒出来的重复块，下一次写入时顺手合并掉。"""
        lines = ["vo = gpu"] + block("gpu-api = vulkan") + block("vf = x")
        self.assertTrue(has_duplicate_marker(lines))
        lines, _ = apply_params_to_lines(lines, {"geometry": "50%:50%"})
        self.assertEqual(marks(lines), 1)
        text = "\n".join(lines)
        for key in ("gpu-api", "vf", "geometry"):
            self.assertIn(key, text, f"合并时把 {key} 丢了")

    def test_block_after_user_content(self):
        """块后面还有用户自己写的内容时，新键要插进块里，不能甩到用户内容之后。"""
        lines = (["vo = gpu"] + block("gpu-api = vulkan")
                 + ["", "# 用户自己加的", "keep-open = yes"])
        new, _ = apply_params_to_lines(lines, {"geometry": "50%:50%"})
        i_new = next(i for i, ln in enumerate(new) if "geometry" in ln)
        i_user = next(i for i, ln in enumerate(new) if "keep-open" in ln)
        self.assertLess(i_new, i_user, "新键被插到用户内容之后了")
        self.assertIn("keep-open = yes", "\n".join(new))

    def test_no_blank_line_accumulation(self):
        """连写多次不该攒出连续空行。

        ⚠ 会攒的情况：某次写入只**改值不新增**（appended 为空）——
        块不重建、压空行那步被跳过，之前留下的空行就一直留着。
        所以压空行必须无条件做。
        """
        lines = ["vo = gpu"]
        lines, _ = apply_params_to_lines(lines, {"gpu-api": "vulkan"})
        lines, _ = apply_params_to_lines(lines, {"gpu-api": "d3d11"})   # 只改值
        lines, _ = apply_params_to_lines(lines, {"vf": "x"})
        self.assertLessEqual(max_run_of_blank(lines), 1, f"出现连续空行：{lines}")

    def test_scan_does_not_eat_user_content(self):
        """⚠ 关键安全用例：扫描范围不能越过块尾吃进用户内容。

        第一版扫描器会跳过块尾空行继续往下扫，于是块后面那行用户配置
        要么被判成"认不出"、要么（带前导空格时）被当成块里的键搬进工具区。
        """
        lines = (["vo = gpu"] + block("gpu-api = vulkan")
                 + ["", "# 用户自己加的", "keep-open = yes"])
        out, dropped = clean_duplicate_markers(lines)
        self.assertEqual(dropped, 0, "只有一个块，不该清理")
        self.assertEqual(out, lines, "内容被动过了")

    def test_scan_stops_at_first_blank(self):
        """扫描在第一个空行收尾 —— 块后面隔着空行的内容不算块的一部分。

        ⚠ 第一版扫描器会**跳过空行接着找**，于是块尾之后那些东西
        要么被误判成块里的内容，要么（带前导空格时）被当成键搬进工具区。
        """
        from core.writer import _scan_marker_block
        lines = (block("gpu-api = vulkan")
                 + ["", " 这行不是键值对", ""] + block("vf = x"))
        i = next(i for i, ln in enumerate(lines) if MERGE_MARKER in ln)
        _start, end, keys, ok = _scan_marker_block(lines, i)
        self.assertTrue(ok, "块本身是干净的")
        self.assertEqual(keys, [" gpu-api = vulkan"])
        self.assertEqual(lines[end], "", "扫描不该越过块尾那个空行")
        self.assertNotIn(" 这行不是键值对", keys, "块外的东西被当成键了")

    def test_unrecognized_shape_means_leave_it_alone(self):
        """块里真有认不出的行 → 整块不动（宁可留着重复，也不吃用户配置）。"""
        lines = (block("gpu-api = vulkan")[:5]
                 + [" gpu-api = vulkan", " 这行不是键值对", ""]
                 + block("vf = x"))
        out, dropped = clean_duplicate_markers(lines)
        self.assertEqual(dropped, 0)
        self.assertEqual(out, lines, "认不出的块应当原样保留")

    def test_clean_is_idempotent(self):
        lines = ["vo = gpu"] + block("a = 1") + block("b = 2")
        once, d1 = clean_duplicate_markers(lines)
        twice, d2 = clean_duplicate_markers(once)
        self.assertEqual(d1, 1)
        self.assertEqual(d2, 0)
        self.assertEqual(once, twice)

    def test_span_finds_the_block(self):
        lines = ["vo = gpu"] + block("gpu-api = vulkan")
        inside, span = marker_block_span(lines)
        self.assertIsNotNone(span)
        marks_in = [i for i, ln in enumerate(lines) if MERGE_MARKER in ln]
        self.assertTrue(span[0] <= marks_in[0] < span[1])
        key_line = next(i for i, ln in enumerate(lines) if "gpu-api" in ln)
        self.assertIn(key_line, inside, "块里的键行应当被认出来")
        self.assertNotIn(0, inside, "块外的行（vo = gpu）不该算进块里")


class TidyConfFileTest(unittest.TestCase):
    """给用户收拾"已经攒出来的重复块"用的动作。"""

    def _write(self, tmp, lines):
        p = Path(tmp) / "mpv.conf"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_dry_run_does_not_touch_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, ["vo = gpu"] + block("a = 1") + block("b = 2"))
            before = p.read_text(encoding="utf-8")
            r = tidy_conf_file(p, dry_run=True)
            self.assertTrue(r["changed"])
            self.assertEqual(r["dropped"], 1)
            self.assertIn("a = 1", r["text"])
            self.assertIn("b = 2", r["text"])
            self.assertEqual(p.read_text(encoding="utf-8"), before, "dry_run 动了磁盘")

    def test_write_creates_backup_and_merges(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, ["vo = gpu"] + block("a = 1") + block("b = 2"))
            r = tidy_conf_file(p, dry_run=False)
            self.assertTrue(r["backup"])
            self.assertTrue(Path(r["backup"]).is_file(), "没有备份")
            text = p.read_text(encoding="utf-8")
            self.assertEqual(marks(text.splitlines()), 1)
            self.assertIn("a = 1", text)
            self.assertIn("b = 2", text)

    def test_nothing_to_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, ["vo = gpu"] + block("a = 1"))
            r = tidy_conf_file(p, dry_run=True)
            self.assertFalse(r["changed"])
            self.assertEqual(r["blocks_before"], 1)

    def test_missing_file_is_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = tidy_conf_file(Path(tmp) / "没有.conf", dry_run=True)
            self.assertFalse(r["ok"])

    def test_result_is_json_safe(self):
        """返回值要能直接丢给 JSON 接口（Path 不行）。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, ["vo = gpu"] + block("a = 1") + block("b = 2"))
            json.dumps(tidy_conf_file(p, dry_run=False))


class TestFiles(unittest.TestCase):
    def test_backup_and_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "mpv.conf"
            conf.write_text("### 原配置\nvo = gpu\nscale = bilinear\n", encoding="utf-8")
            changes, backup = merge_into_file(conf, {"scale": "spline36", "hwdec": "auto-safe"})
            text = conf.read_text(encoding="utf-8")
            self.assertIn("scale = spline36", text)
            self.assertIn("hwdec = auto-safe", text)
            self.assertIn("### 原配置", text)              # 原注释保留
            self.assertTrue(backup and backup.is_file(), "应当生成备份")
            self.assertEqual(backup.read_text(encoding="utf-8").count("scale = bilinear"), 1)
            self.assertEqual(len(changes), 2)

    def test_merge_twice_keeps_one_block(self):
        """落盘路径也守住只有 1 个块（不只是内存里的 apply）。"""
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "mpv.conf"
            conf.write_text("vo = gpu\n", encoding="utf-8")
            merge_into_file(conf, {"gpu-api": "vulkan"})
            merge_into_file(conf, {"vf": "vapoursynth=~~/vs/a.vpy"})
            self.assertEqual(marks(conf.read_text(encoding="utf-8").splitlines()), 1)

    def test_merge_preserves_encoding(self):
        """GBK 的配置改完还得是 GBK。"""
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "mpv.conf"
            conf.write_bytes("### 中文注释\nvo = gpu\n".encode("gbk"))
            merge_into_file(conf, {"hwdec": "nvdec"})
            raw = conf.read_bytes()
            self.assertIn("中文注释", raw.decode("gbk"), "编码被改掉了")

    def test_include_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            main = target / "mpv.conf"
            main.write_text("vo = gpu\n", encoding="utf-8")
            path, backup = write_include(target, build_include_text({"scale": "spline36"}))
            self.assertTrue(path.is_file())
            changed, main_backup, _msg = ensure_include_line(main)
            self.assertTrue(changed)
            self.assertIn(INCLUDE_FILENAME, main.read_text(encoding="utf-8"))
            self.assertTrue(main_backup and main_backup.is_file())
            # 第二次不应重复追加
            changed2, _b2, _m2 = ensure_include_line(main)
            self.assertFalse(changed2)
            self.assertEqual(main.read_text(encoding="utf-8").count("mpv-builder.conf"), 1)

    def test_backup_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(backup_file(Path(tmp) / "不存在.conf"))


if __name__ == "__main__":
    unittest.main()

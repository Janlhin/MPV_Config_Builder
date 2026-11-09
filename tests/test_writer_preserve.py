# -*- coding: utf-8 -*-
"""MPVLAZY 原生 mpv.conf 不被写丢的安全验证（「代码对比」式逐行比对）。

背景：MPVLAZY 自带 portable_config/mpv.conf，里面是用户的**原生内容**
（头注释、全局键、[profile] 小节、script-opts、与工具同名的键等）。
本文件拿一份贴近真实的原生 mpv.conf，分别走 include / merge 两种写入方式，
逐行比对断言：

  1. include 模式：原生正文一字不改，只在末尾加一行 include + 另写 mpv-builder.conf；
  2. merge  模式：只有工具管理的键被改，[profile] 小节与其余原生行原样保留；
  3. 写前必有备份（mpv.conf.bak-*）；
  4. GBK 编码的原生配置，写回后仍是 GBK（不会被偷偷转成 UTF-8）。

覆盖的就是 webui/server.py 里 _apply_config / api_basic_apply 实际调用的
core.writer 函数（merge_into_file / write_include / ensure_include_line），
所以这条测试等价于「对真实写入路径做原生内容保全的回归」。
"""
import tempfile
import unittest
from pathlib import Path

from core.writer import (
    INCLUDE_FILENAME, INCLUDE_LINE, MERGE_MARKER, SECTION_RE,
    build_include_text, write_include, ensure_include_line,
    merge_into_file,
)

# 一份贴近真实的「MPVLAZY 原生 mpv.conf」：头注释、全局键、与工具同名的键
# （vo / hwdec）、[profile] 小节（里面也有 scale，绝不能动）、script-opts、
# 注释行、空行，一应俱全。
NATIVE = """\
# ============================================================
# MPVLAZY 一键配置（原生内容，下面这些都不该被工具弄丢）
# 这是用户自己的注释
# ============================================================
vo = gpu-next
gpu-api = vulkan
hwdec = auto-safe

profile = gpu-hq

# 字幕
sub-font = "Microsoft YaHei"
sub-font-size = 40

# 工具也会管 scale，但它在 [profile] 里 —— 绝不能动
[anime]
scale = spline36
cscale = bicubic
deband = yes

[shader]
glsl-shaders = "~~/shaders/Anime4K.glsl"

script-opts = osc-layout=top-bar,console-enabled=yes
"""

# 工具这次要写进去的东西：改 hwdec（全局原生键），新增一个全局 scale
# （注意 [anime] 里已有一个 scale，二者必须共存、小节里的不动）。
TOOL_PARAMS = {"hwdec": "no", "scale": "ewa_lanczossharp"}


def _key_of(line):
    """取一行的键名（小写）；注释 / 小节 / 非 key=value 行返回 None。"""
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("[") or "=" not in s:
        return None
    return s.split("=", 1)[0].strip().lower()


def _stripped_set(text):
    return {ln.strip() for ln in text.splitlines() if ln.strip()}


class NativePreserveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        (self.target / "mpv.conf").write_text(NATIVE, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    # ---------- 工具：逐行代码对比 ----------

    def assert_native_survives(self, before, after, managed):
        """核心「代码对比」：before 里每一条非工具管理的原生行，after 必须还在。"""
        after_set = _stripped_set(after)
        for ln in (l.strip() for l in before.splitlines() if l.strip()):
            if _key_of(ln) in managed:
                continue  # 工具管的键单独验证（见各用例），这里不双重计
            self.assertIn(ln, after_set, f"原生内容丢失：{ln!r}")

    # ---------- 1. include 模式：正文一字不改 ----------

    def _include_is_global(self, text):
        """include 行必须落在第一个 [profile] 小节之前（全局区）。"""
        lines = text.splitlines()
        inc_idx = next((i for i, ln in enumerate(lines) if ln.strip() == INCLUDE_LINE), None)
        self.assertIsNotNone(inc_idx, "主配置里没有 include 行")
        for i, ln in enumerate(lines):
            if i < inc_idx and SECTION_RE.match(ln):
                self.fail(f"include 行（第 {inc_idx} 行）落在小节（第 {i} 行）之后，"
                          "会变成仅该 profile 生效、且无法被幂等识别")

    def test_include_keeps_native_body_intact(self):
        params = TOOL_PARAMS
        write_include(self.target, build_include_text(params, "说明"))
        changed, _main_bak, _msg = ensure_include_line(self.target / "mpv.conf")

        after = (self.target / "mpv.conf").read_text(encoding="utf-8")
        after_lines = [l.strip() for l in after.splitlines() if l.strip()]

        # 原生正文逐行都在（include 行除外）
        for ln in (l.strip() for l in NATIVE.splitlines() if l.strip()):
            self.assertIn(ln, after_lines, f"include 模式把原生行弄丢了：{ln!r}")

        # 主配置里只有恰好一行 include（不能重复追加）
        self.assertTrue(changed, "主配置里本应有 include 行被追加")
        self.assertEqual(after_lines.count(INCLUDE_LINE), 1, "include 行出现次数应为 1")

        # include 必须落在全局区（MPVLAZY 以小节结尾，这里最易踩坑）
        self._include_is_global(after)

        # 工具内容在独立文件里；主配置里不该出现工具键（只认得原生 vo 等）
        inc = (self.target / INCLUDE_FILENAME).read_text(encoding="utf-8")
        self.assertIn("hwdec = no", inc)
        self.assertIn("scale = ewa_lanczossharp", inc)
        self.assertNotIn("scale = ewa_lanczossharp", after, "工具键漏进了主配置正文")
        self.assertNotIn("hwdec = no", after, "工具键漏进了主配置正文")

    def test_include_idempotent_does_not_reappend(self):
        """第二次写时主配置里已有 include 行，就不该再动主配置（MPVLAZY 以小节结尾场景）。"""
        write_include(self.target, build_include_text(TOOL_PARAMS, "说明"))
        ensure_include_line(self.target / "mpv.conf")
        body1 = (self.target / "mpv.conf").read_text(encoding="utf-8")

        # 再跑一次 ensure_include_line（模拟重复应用）
        changed, _bak, _msg = ensure_include_line(self.target / "mpv.conf")
        body2 = (self.target / "mpv.conf").read_text(encoding="utf-8")

        self.assertFalse(changed, "已有 include 行时不应再改主配置")
        self.assertEqual(body1, body2, "重复应用不该改动主配置正文")
        self.assertEqual([l.strip() for l in body2.splitlines() if l.strip()].count(INCLUDE_LINE), 1)
        self._include_is_global(body2)

    # ---------- 2. merge 模式：只改工具管理的键 ----------

    def test_merge_only_touches_managed_keys(self):
        changes, backup = merge_into_file(self.target / "mpv.conf", TOOL_PARAMS)
        after = (self.target / "mpv.conf").read_text(encoding="utf-8")
        after_set = _stripped_set(after)

        # ① 非工具管理的原生行逐条都在（这是「代码对比」的断言核心）
        self.assert_native_survives(NATIVE, after, managed={"hwdec"})

        # ② [profile] 小节里的行原样保留（同名的 scale 也不能动）
        self.assertIn("scale = spline36", after_set, "[anime] 里的 scale 被改了")
        self.assertIn("cscale = bicubic", after_set)
        self.assertIn("deband = yes", after_set)
        self.assertIn("[anime]", after_set)
        self.assertIn("[shader]", after_set)
        self.assertIn('glsl-shaders = "~~/shaders/Anime4K.glsl"', after_set)

        # ③ 工具管的键：旧值消失、新值出现（不是「追加重复」，也不是「整行删除」）
        self.assertIn("hwdec = no", after_set, "工具改的 hwdec 新值没出现")
        self.assertNotIn("hwdec = auto-safe", after, "原生 hwdec 旧值没被替换掉")
        self.assertIn("scale = ewa_lanczossharp", after_set, "新增的全局 scale 没出现")

        # ④ 工具内容收在自己的标记块里
        self.assertTrue(any(MERGE_MARKER in ln for ln in after.splitlines()),
                        "merge 模式缺少工具标记块")

        # ⑤ 写前必有备份
        self.assertIsNotNone(backup, "merge 写 mpv.conf 前必须备份")
        self.assertTrue(list(self.target.glob("mpv.conf.bak-*")), "没生成 .bak 备份")

        # ⑥ 确实产生了改动（hwdec 被改）
        self.assertTrue(any("hwdec" in c for c in changes), "changes 应记录 hwdec 改动")

    def test_merge_does_not_touch_section_scale(self):
        """精确回归：全局没有 scale 时，新增的全局 scale 不应污染 [anime] 小节。"""
        merge_into_file(self.target / "mpv.conf", {"scale": "ewa_lanczossharp"})
        after = (self.target / "mpv.conf").read_text(encoding="utf-8")

        # 两个 scale 都得在：小节的 spline36 + 全局的 ewa_lanczossharp
        self.assertIn("scale = spline36", after)
        self.assertIn("scale = ewa_lanczossharp", after)
        # 小节里的那行必须还是 spline36（原值）
        section_scale_line = [ln.strip() for ln in after.splitlines()
                              if ln.strip().startswith("scale = spline36")]
        self.assertEqual(section_scale_line, ["scale = spline36"],
                         "小节里的 scale 被写路径改动了")

    def test_merge_preserves_duplicate_free(self):
        """多次写入仍只保留一个工具标记块（W-1 回归，顺便确认原生行不丢）。"""
        for _ in range(3):
            merge_into_file(self.target / "mpv.conf", TOOL_PARAMS)
        after = (self.target / "mpv.conf").read_text(encoding="utf-8")
        markers = sum(1 for ln in after.splitlines() if MERGE_MARKER in ln)
        self.assertEqual(markers, 1, "工具标记块出现了多次")
        self.assert_native_survives(NATIVE, after, managed={"hwdec"})


class NativeGbkPreserveTest(unittest.TestCase):
    """GBK 原生配置：写回后必须还是 GBK，不能偷偷转 UTF-8。"""

    GBK_NATIVE = (
        "# 用户自己的中文注释（MPVLAZY 老配置常见 GBK）\n"
        "vo = gpu-next\n"
        "hwdec = auto-safe\n"
        "profile = gpu-hq\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        # 以 GBK 字节落地（模拟一份真实的老 GBK mpv.conf）
        (self.target / "mpv.conf").write_bytes(self.GBK_NATIVE.encode("gbk"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_gbk_encoding_is_preserved(self):
        merge_into_file(self.target / "mpv.conf", {"hwdec": "no"})
        raw = (self.target / "mpv.conf").read_bytes()

        # 仍是 GBK：能用 gb18030 解码出中文注释，且不能用 utf-8 严格解码
        self.assertIn("用户自己的中文注释", raw.decode("gb18030"))
        with self.assertRaises(UnicodeDecodeError):
            raw.decode("utf-8")  # 若被偷转 UTF-8，这里就不会抛异常

        # 工具改动也正确落盘（ASCII，GBK 下无碍）
        self.assertIn(b"hwdec = no", raw)

    def test_gbk_native_lines_not_dropped(self):
        merge_into_file(self.target / "mpv.conf", {"hwdec": "no"})
        text = (self.target / "mpv.conf").read_text(encoding="gb18030")
        self.assertIn("vo = gpu-next", text)
        self.assertIn("profile = gpu-hq", text)
        self.assertIn("hwdec = no", text)
        self.assertNotIn("hwdec = auto-safe", text)


if __name__ == "__main__":
    unittest.main()

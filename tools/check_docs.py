# -*- coding: utf-8 -*-
"""文档数字守门人：检查文档里的关键数字是否与实测一致。

为什么要有它：这个项目吃过一次亏 —— README 说 20 个接口、另一份文档说 21 个，
实际 23 个；测试数在三份文档里分别写成 181 / 167 / 199（实际 199）。
人肉维护数字迟早会对不上，所以做成一个能跑的检查。

用法（仓库根目录）：
    py -3 tools/check_docs.py
退出码：0 = 全部一致；1 = 有对不上的地方。

约定：`产品规划与路线图.md` 的「### 结论摘要」一节是**故意保留的历史基线**，
检查会跳过它 —— 别把基线数字刷成现值，那会让"改进了多少"看不出来。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from webui import api, server  # noqa: E402

# ⚠ 路由表在 W-4 之后搬到了 `webui/api.py`（表里存的是 server 里的属性名）。
# 别改回去读 server.ROUTES_* —— 那三张表已经不在那儿了。
routes = len(api.ROUTES_GET) + len(api.ROUTES_QUERY) + len(api.ROUTES_POST)
pages = len(list((ROOT / "webui/static").glob("*.html")))
modules = len([p for p in (ROOT / "core").glob("*.py") if p.name != "__init__.py"])


def count_tests():
    """测试数 —— 用**真的跑一遍**的结果，不是 grep 出来的假数字。

    为什么较真：以前用正则数 `def test*` 会把手写的验证脚本也算进去，
    而那些脚本没有 `TestCase`，`unittest discover` **一个都不会收集**。
    实测过：归档 4 个 `_api_*.py` 之后 `Ran N tests` 一点没变，
    但 grep 出来的数字掉了 25 —— 说明那个数字一直是虚的。
    """
    import io
    import unittest
    suite = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return res.testsRun, len(res.failures) + len(res.errors)


tests, failures = count_tests()

from core.options_db import load_db  # noqa: E402

_db = load_db()
n_options = _db["meta"].get("count", 0)      # 能写进配置的条数（滤掉命令行专用项之后）
n_zh = _db["meta"].get("with_zh", 0)

CHECKS = [
    # 只认「历史上真的出现过的测试数」，不能写 \d{3} —— 那会把 829（选项数）、
    # 726（中文说明数）、117（精选项数）全当成测试数来报。
    # ⚠ 每次测试数变了，**这里也要跟着加**，否则新数字不在白名单里 = 没人守它。
    #
    # ⚠⚠ 白名单有个**天生的盲区**：写错的数字要是不在名单里，就永远匹配不上，
    # 也就永远查不出来（实测：把 424 手滑成 420，这个模式一个字都不匹配，
    # 检查照样报"一致 ✓"）。所以底下还有一条「按上下文兜底」的规则。
    (r"(?<![\d])(181|199|220|222|228|236|259|287|327|352|358|360|392|424|444|476|497|509|547|548|575|595|606|615|645|648|650) 项",
     tests, "测试数"),
    # 兜底：**三位数**的 `N 项` 出现在「测试」附近时，必须等于实测总数。
    #
    # 为什么需要它：白名单只认「曾经出现过的数字」，所以把现值打错一位
    # （424 → 420）会**一个字都匹配不上**，检查照样报"一致 ✓"。实测过。
    # 为什么用"三位数"当判据：实测过全部五份文档，模块分项测试数最大是 **42**
    # （`vpy.py` 17、`conflicts.py` 28、`test_dlcenter.py` 23…），
    # 而总数一直是三位数。所以三位数 ≈ 总数，这个界限不会误伤分项。
    # 若哪天某个模块的分项测试数破百，这条会开始误报 —— 那时再改判据。
    (r"(?<![\d])(\d{3})(?=\s*项)[^\n]{0,12}?测试", tests, "测试数（按上下文）"),
    (r"测试[^\n]{0,12}?(?<![\d])(\d{3})(?=\s*项)", tests, "测试数（按上下文）"),
    (r"(?<![\d])(20|21|23|29|31|32|37|39) 个(?:JSON )?接口", routes, "接口数"),
    (r"（(16|19|20|23|24|25) 个(?:逻辑)?模块）", modules, "模块数"),
    # ⚠ 下面两条是"按说法兜底"，理由和测试数那条一样：白名单只认出现过的数字，
    # 写错的（`19 个核心模块` 而实际 24）永远匹配不上，等于没人守。
    # 实测过：路线图里「19 个核心模块 / 8 个界面页面」和「页面共 8 个」
    # 三处都过期了，而 check_docs 一路报"一致 ✓"。
    (r"(?<![\d])(\d+)\s*个核心模块", modules, "核心模块数"),
    (r"(?<![\d])(\d+)\s*个(?:界面)?页面", pages, "页面数（按说法）"),
    (r"页面共\s*(?<![\d])(\d+)\s*个", pages, "页面数（按说法）"),
    (r"\| 界面页面 \| (\d+) 个", pages, "页面数"),
    # 选项库条数：829 是数据文件里的原始条数（允许出现），813 是界面可用的
    (r"\*\*(\d+) 项全量选项库\*\*", n_options, "选项库条数"),
    (r"(\d+) 项可写进配置的选项", n_options, "选项库条数"),
]


def baseline_span(text):
    """「### 结论摘要」整段是故意保留的历史基线，检查时跳过。"""
    m = re.search(r"^### 结论摘要.*?(?=^### )", text, re.S | re.M)
    return m.span() if m else None


def line_span(text, pos):
    """`pos` 所在那一行的 [起, 止)。用来给匹配做上下文判断。"""
    a = text.rfind("\n", 0, pos) + 1
    b = text.find("\n", pos)
    return a, (len(text) if b < 0 else b)


# 这一行是在讲"删掉了多少东西"时，里面的数字不是现状，跳过。
# 实测踩过：X-4-7 那行写「顶栏逻辑在 4 个页面里各抄了一遍」，被判成"页面数写 4"。
_HISTORICAL_MARKERS = ("已删", "已归档", "曾经", "删掉了", "归档而非删除")


def main():
    print(f"实测: 接口 {routes} / 页面 {pages} / 模块 {modules} / "
          f"测试 {tests}（真的跑了一遍，失败 {failures} 项）")
    print(f"      选项库 {n_options} 项可写进配置（含中文说明 {n_zh} 条）\n")
    bad_total = 0
    # 2026-09-14 清理过一轮开发文档：已完成清单 / 问题清单 / 制作与发布文档都删了
    # （在 git 历史里）。这里只剩真正还在的文档，**加新文档记得同步这份列表**。
    for name in ("README.txt", "README.md", "产品规划与路线图.md",
                 "docs/踩过的坑.md"):
        p = ROOT / name
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8")
        span = baseline_span(t)
        bad = []
        seen = set()
        for pat, want, what in CHECKS:
            for m in re.finditer(pat, t):
                if span and span[0] <= m.start() < span[1]:
                    continue
                a, b = line_span(t, m.start())
                line_text = t[a:b]
                # 「按上下文 / 按说法」那几条：只在讲现状的行上判定
                if "按上下文" in what or "按说法" in what:
                    if any(k in line_text for k in _HISTORICAL_MARKERS):
                        continue
                if "按上下文" in what and "测试" not in line_text:
                    continue
                # ⚠ 还要排掉"数据条数"的说法：`726 项有说明` / `338 项有格式提示`
                # 这类是**选项库的覆盖率**，不是测试数。它们所在的行里往往也带"测试"
                # （表格的"验证方式"列就写着"测试"），只按"这一行有没有测试"判会误报
                # —— 实测踩过：338 被当成测试数报了出来。
                if "按上下文" in what and re.search(r"\d+\s*项有", line_text):
                    continue
                line = t[:m.start()].count("\n") + 1
                key = (line, want)
                if key in seen:
                    continue          # 两条规则命中同一处，只报一次
                seen.add(key)
                got = int(re.search(r"\d+", m.group(0)).group())
                if got != want:
                    bad.append(f"{what} 写 {got} 实际 {want} @{line}行")
        bad_total += len(bad)
        print(f"  {name:26} " + ("一致 ✓" if not bad else "；".join(bad)))
    print(f"\n不一致处: {bad_total}")
    return 1 if bad_total else 0


if __name__ == "__main__":
    sys.exit(main())

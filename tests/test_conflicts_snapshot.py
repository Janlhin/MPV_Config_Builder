# -*- coding: utf-8 -*-
"""冲突检测的**行为快照**测试（C-1 重构的安全网）。

和 tests/test_conflicts.py 的分工：
  * test_conflicts.py  —— 人写的断言，说「这条规则应该在什么时候触发 / 不该触发」，
                          可读性好，但只抽查了几个字段。
  * 本文件             —— 用 tests/data/conflicts_golden.json 做**逐字段**比对：
                          id / level / title / detail / fix / keys、输出顺序、
                          以及 conflicts_as_issues() / conflict_keys() 的派生结果。
                          文案改一个字、顺序换一下都会红。

基准 JSON 由 tools/gen_conflicts_golden.py 在**重构前**跑真实实现生成。
凡是基准和当前实现不一致，先问「是重构改坏了，还是我确实想改行为」——
如果是后者，请在 commit 信息里说明**为什么**要改行为，然后重新生成基准。
"""
import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.conflicts import (                 # noqa: E402
    _RULES, _legacy_detect_conflicts, conflicts_as_issues, conflict_keys,
    detect_conflicts,
)

GOLDEN = ROOT / "tests" / "data" / "conflicts_golden.json"

# 这 17 条是当前全部规则。新增规则时这个数字要一起改（改完记得重新生成基准）。
EXPECTED_RULES = {
    "cache_off_but_buffer",
    "deband_iterations_high",
    "deband_range_vs_iterations",
    "deband_zero_iterations",
    "double_upscale_shaders",
    "gpu_only_with_gpunext",
    "gpunext_only_with_gpu",
    "hable_needs_peak",
    "icc_auto_vs_profile",
    "icc_profile_vs_target",
    "interp_needs_sync",
    "interp_no_tscale",
    "interp_with_memc",
    "linear_upscaling_alone",
    "sharpen_not_last",
    "sigmoid_vs_linear",
    "vpy_sr_with_shader_sr",
}


def _load_golden():
    with GOLDEN.open(encoding="utf-8") as fh:
        return json.load(fh)


# 基准里存了入参（便于重放）和输出；比对只关心输出这三项。
INPUT_FIELDS = ("name", "values", "shaders", "memc")
OUTPUT_FIELDS = ("conflicts", "issues", "keys")


def _want(case):
    return {k: case[k] for k in OUTPUT_FIELDS}


def _run(case):
    """按基准里同一套入参跑一遍当前实现。"""
    conflicts = detect_conflicts(case["values"], shaders=case.get("shaders"),
                                 memc=case.get("memc", ""))
    return {
        "conflicts": conflicts,
        "issues": [list(x) for x in conflicts_as_issues(conflicts)],
        "keys": sorted(conflict_keys(conflicts)),
    }


def _single_target_cases():
    """只开「一个」target-* 的用例。

    这几个是补齐来的：C-1 重构时 `icc_profile_vs_target` 想把动态 keys 一起返回，
    结果 keys 顶掉了 detail 的位置。原来的 55 个手选用例里全是「两个 target 同时开」，
    恰好没覆盖「只开一个」，所以 606 项测试全绿也没发现 ——
    只有 tools/compare_conflicts.py 的 4699 组枚举抓到了。这里把它补上。
    """
    out = []
    for key in ("target-prim", "target-trc", "target-gamut"):
        out.append((f"icc_single_{key}", {"icc-profile": "C:/icc/srgb.icc", key: "bt.709"}))
    return out


class GoldenFileTest(unittest.TestCase):
    """基准文件本身要站得住脚，否则比对通过也没有意义。"""

    def test_golden_exists(self):
        self.assertTrue(GOLDEN.is_file(), f"缺少基准文件：{GOLDEN}")

    def test_golden_covers_every_rule(self):
        data = _load_golden()
        got = {c["id"] for case in data["cases"] for c in case["conflicts"]}
        self.assertEqual(got, EXPECTED_RULES,
                         "基准覆盖的规则和 EXPECTED_RULES 不一致："
                         f"缺 {sorted(EXPECTED_RULES - got)}，多 {sorted(got - EXPECTED_RULES)}")

    def test_golden_has_enough_cases(self):
        data = _load_golden()
        self.assertEqual(data["count"], len(data["cases"]))
        self.assertGreaterEqual(len(data["cases"]), 50)
        # 光有「能触发」的用例不够，还要有「不该触发」的 —— 否则条件写反了也发现不了
        clean = [c for c in data["cases"] if not c["conflicts"]]
        self.assertGreaterEqual(len(clean), 20)

    def test_golden_records_full_detail_text(self):
        """detail 是给用户看的理由，不能被压缩成空串或省略。"""
        data = _load_golden()
        for case in data["cases"]:
            for c in case["conflicts"]:
                self.assertTrue(c["detail"].strip(),
                                f"{case['name']}/{c['id']} 的 detail 是空的")
                self.assertIn(c["level"], ("error", "warn", "info"),
                              f"{case['name']}/{c['id']} 级别非法")


class ConflictSnapshotTest(unittest.TestCase):
    """核心：55 个用例逐个逐字段比对。"""

    @classmethod
    def setUpClass(cls):
        cls.data = _load_golden()

    def test_every_case_matches_golden(self):
        failures = []
        for case in self.data["cases"]:
            want = _want(case)
            got = _run(case)
            if got != want:
                failures.append((case["name"], want, got))
        if failures:
            lines = [f"{len(failures)} / {len(self.data['cases'])} 个用例与基准不符："]
            for name, want, got in failures[:5]:
                lines.append(f"  用例 {name}")
                for field in OUTPUT_FIELDS:
                    if want[field] != got[field]:
                        lines.append(f"    {field} 基准: "
                                     + json.dumps(want[field], ensure_ascii=False))
                        lines.append(f"    {field} 当前: "
                                     + json.dumps(got[field], ensure_ascii=False))
            lines.append("  （只显示前 5 个）")
            self.fail("\n".join(lines))

    def test_id_list_order_is_stable(self):
        """顺序也要锁：level 升序（error→warn→info），同级别按 id 字典序。"""
        order = {"error": 0, "warn": 1, "info": 2}
        for case in self.data["cases"]:
            got = [c["id"] for c in detect_conflicts(case["values"],
                                                     shaders=case.get("shaders"),
                                                     memc=case.get("memc", ""))]
            want = [c["id"] for c in case["conflicts"]]
            self.assertEqual(got, want, f"用例 {case['name']} 的输出顺序变了")
        # 再验一遍排序规则本身，而不是只比值
        for case in self.data["cases"]:
            keys = [(order[c["level"]], c["id"]) for c in case["conflicts"]]
            self.assertEqual(keys, sorted(keys),
                             f"用例 {case['name']} 的基准顺序不满足 (level, id) 排序")

    def test_conflicts_are_independent_objects(self):
        """同一个 case 跑两次不能串味（历史上有过共享可变默认参数的坑）。"""
        case = self.data["cases"][0]
        first = _run(case)["conflicts"]
        second = _run(case)["conflicts"]
        self.assertEqual(first, second)
        if first:
            first[0]["keys"].append("注入的脏数据")
            self.assertNotIn("注入的脏数据", _run(case)["conflicts"][0]["keys"])


class RuleTableTest(unittest.TestCase):
    """规则表本身要立得住 —— 表坏了，后面所有比对都白搭。"""

    def test_table_has_all_rules(self):
        rids = [r.rid for r in _RULES]
        self.assertEqual(len(rids), len(set(rids)), f"规则 id 重复：{rids}")
        self.assertEqual(set(rids), EXPECTED_RULES)

    def test_every_rule_declares_a_known_level(self):
        for r in _RULES:
            self.assertIn(r.level, ("error", "warn", "info"), r.rid)

    def test_static_keys_point_at_real_options(self):
        """规则表里写死的 keys 必须是真选项名 —— 写错了界面会标不中任何一行。"""
        from core.schema import PARAMS  # noqa: PLC0415
        db = json.loads((ROOT / "data" / "mpv_options_zh.json").read_text(encoding="utf-8"))
        known = set(db["options"]) | set(db.get("native_options", {}) or {}) | set(PARAMS)
        # vf 是 builder 里合成的伪键位（挂 shader/脚本用），不是选项库里的真选项
        known.add("vf")
        for r in _RULES:
            for k in r.keys:
                self.assertIn(k, known, f"{r.rid} 的 keys 里有未知选项 {k!r}")

    def test_vo_rule_keys_are_dynamic_not_static(self):
        """两条 gpu 规则的 keys 是动态的（vo + 实际命中的选项），
        静态声明里只该有 vo —— 否则会误导成「固定就这几个」。"""
        for rid in ("gpunext_only_with_gpu", "gpu_only_with_gpunext"):
            rule = next(r for r in _RULES if r.rid == rid)
            self.assertEqual(tuple(rule.keys), ("vo",), rid)


class OutputShapeTest(unittest.TestCase):
    """返回结构是前端直接渲染的契约。"""

    def test_every_item_has_exactly_the_six_contract_keys(self):
        want = {"id", "level", "title", "detail", "fix", "keys"}
        for case in _load_golden()["cases"]:
            for c in detect_conflicts(case["values"], shaders=case.get("shaders"),
                                      memc=case.get("memc", "")):
                self.assertEqual(set(c), want, f"{case['name']}/{c['id']}")
                self.assertIsInstance(c["keys"], list)
                self.assertIsInstance(c["title"], str)
                self.assertIsInstance(c["detail"], str)
                self.assertIsInstance(c["fix"], str)

    def test_values_and_shaders_are_not_mutated(self):
        values = {"vo": "gpu", "gamut-mapping-mode": "clip", "icc-profile": "x"}
        shaders = ["~~/shaders/AMD_CAS.glsl", "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"]
        before_v, before_s = dict(values), list(shaders)
        detect_conflicts(values, shaders=shaders, memc="~~/vs/SR_x.vpy")
        self.assertEqual(values, before_v)
        self.assertEqual(shaders, before_s)

    def test_unknown_x_inputs_do_not_crash(self):
        """野输入不许抛异常 —— 配置文件的取值是我们控制不了的。"""
        weird = [None, 0, 1, [], {}, True, "  ", "\t", "0x10", "nan", "inf", -1]
        for w in weird:
            for key in ("vo", "interpolation", "deband-iterations", "tone-mapping",
                        "icc-profile", "cache", "demuxer-max-bytes"):
                got = detect_conflicts({key: w}, shaders=[w], memc=w)
                self.assertIsInstance(got, list)


class LegacyEquivalenceTest(unittest.TestCase):
    """新旧实现的等价性（守护用）。

    背景：C-1 把 154 行 if 长链改成规则表时，`_legacy_*` 是**重构前原样保留**的实现。
    完整对照在 tools/compare_conflicts.py（4699 组用例，几分钟）；
    单元测试里跑一个**固定种子**的抽样，够便宜、又能长期守住「别再改坏」。
    抽样覆盖已在基准里出现过的每一处输入，另外补上单 target-* 那组（历史盲区）。
    """

    @staticmethod
    def _cases(limit=400):
        cases = []
        seen = set()

        def push(values, shaders, memc):
            key = (json.dumps(values, sort_keys=True, ensure_ascii=False),
                   json.dumps(shaders, ensure_ascii=False), memc)
            if key in seen:
                return
            seen.add(key)
            cases.append((values, shaders, memc))

        for case in _load_golden()["cases"]:
            push(case["values"], case.get("shaders") or [], case.get("memc", ""))
        for _, values in _single_target_cases():
            push(values, [], "")

        # 固定种子的随机组合：选项名和取值都从真实出现过的集合里取
        rnd = random.Random(20260914)
        all_values = [c["values"] for c in _load_golden()["cases"]]
        keys = sorted({k for v in all_values for k in v})
        pool = {k: sorted({v[k] for v in all_values if k in v}) for k in keys}
        shader_pool = [s for c in _load_golden()["cases"] for s in (c.get("shaders") or [])]
        memc_pool = [c.get("memc", "") for c in _load_golden()["cases"]]
        while len(cases) < limit:
            picked = rnd.sample(keys, rnd.randint(1, 4))
            values = {k: rnd.choice(pool[k]) for k in picked}
            shaders = rnd.sample(shader_pool, rnd.randint(0, 3))
            push(values, shaders, rnd.choice(memc_pool))
        return cases

    def test_same_output_as_pre_refactor_implementation(self):
        bad = []
        for values, shaders, memc in self._cases():
            old = _legacy_detect_conflicts(values, shaders=shaders, memc=memc)
            new = detect_conflicts(values, shaders=shaders, memc=memc)
            if old != new:
                bad.append((values, shaders, memc, old, new))
        if bad:
            values, shaders, memc, old, new = bad[0]
            self.fail(f"{len(bad)} 组用例新旧实现不一致，第一组：\n"
                      f"  values={json.dumps(values, ensure_ascii=False)}\n"
                      f"  shaders={json.dumps(shaders, ensure_ascii=False)}\n"
                      f"  memc={memc!r}\n"
                      f"  旧={json.dumps(old, ensure_ascii=False)}\n"
                      f"  新={json.dumps(new, ensure_ascii=False)}")

    def test_single_target_icc_regression(self):
        """回归：只开一个 target-* 时，detail 必须是说明书原文、fix 不能被吞掉。"""
        for name, values in _single_target_cases():
            got = detect_conflicts(values)
            hit = [c for c in got if c["id"] == "icc_profile_vs_target"]
            self.assertEqual(len(hit), 1, name)
            c = hit[0]
            self.assertIn("icc-profile 会覆盖", c["detail"])
            self.assertIn("删掉", c["fix"])
            self.assertEqual(c["keys"], ["icc-profile"] + [k for k in values
                                                           if k != "icc-profile"])


class DerivedHelpersTest(unittest.TestCase):
    """conflicts_as_issues / conflict_keys 是界面直接用的派生结果。"""

    def test_issues_shape(self):
        issues = conflicts_as_issues([{"id": "x", "level": "warn", "title": "标题",
                                       "detail": "d", "fix": "怎么改", "keys": []}])
        self.assertEqual(issues, [("warn", "标题 → 怎么改")])

    def test_issues_without_fix_has_no_arrow(self):
        issues = conflicts_as_issues([{"id": "x", "level": "info", "title": "标题",
                                       "detail": "d", "fix": "", "keys": []}])
        self.assertEqual(issues, [("info", "标题")])

    def test_conflict_keys_unions_case_keys(self):
        got = conflict_keys([{"keys": ["a", "b"]}, {"keys": ["b", "c"]}, {}])
        self.assertEqual(got, {"a", "b", "c"})

    def test_empty_inputs(self):
        self.assertEqual(detect_conflicts(None), [])
        self.assertEqual(detect_conflicts({}, shaders=None, memc=None), [])
        self.assertEqual(conflicts_as_issues([]), [])
        self.assertEqual(conflict_keys([]), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)

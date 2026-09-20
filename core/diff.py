# -*- coding: utf-8 -*-
"""行级差异（R-14）：merge 模式下左右并排的逐行对比。

原来只给「合并后的完整文件」+ 改动条数，用户得自己在两个大文本里找哪几行变了。
这里把差异算成结构化数据，界面照着渲染左右两栏即可。

用一个**统一的**差异算法（`difflib`），返回的每行都带：
    tag    equal / add / del / modify
    left   左栏（原文件）的行号与文本，没有则 None
    right  右栏（合并后）的行号与文本，没有则 None

`modify` 是把相邻的 del+add 配对起来的 —— 用户关心的是"这一行被改成什么了"，
而不是"删了一行又加了一行"。配对的数量不等时，多出来的按纯 add / del 处理。
"""
from difflib import SequenceMatcher


def diff_lines(before, after, context=None):
    """算两份文本的逐行差异。

    before / after 可以是 str（按行拆）或已经是行列表。
    context=None 表示全部返回；给个整数（如 3）则只保留变更附近的若干行。
    """
    a = _as_lines(before)
    b = _as_lines(after)

    matcher = SequenceMatcher(None, a, b, autojunk=False)
    rows = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append(_row("equal", i1 + k, a[i1 + k], j1 + k, b[j1 + k]))
            continue
        if tag == "delete":
            for k in range(i1, i2):
                rows.append(_row("del", k, a[k], None, None))
            continue
        if tag == "insert":
            for k in range(j1, j2):
                rows.append(_row("add", None, None, k, b[k]))
            continue
        # replace：把能配上的配成 modify，多出来的各算各的
        left_n, right_n = i2 - i1, j2 - j1
        paired = min(left_n, right_n)
        for k in range(paired):
            rows.append(_row("modify", i1 + k, a[i1 + k], j1 + k, b[j1 + k]))
        for k in range(i1 + paired, i2):
            rows.append(_row("del", k, a[k], None, None))
        for k in range(j1 + paired, j2):
            rows.append(_row("add", None, None, k, b[k]))

    if context is not None:
        rows = _with_context(rows, int(context))
    return {
        "rows": rows,
        "stats": stats(rows),
        "identical": all(r["tag"] == "equal" for r in rows),
    }


def _as_lines(text):
    if isinstance(text, (list, tuple)):
        return [str(x) for x in text]
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if s.endswith("\n"):
        s = s[:-1]                     # 末尾换行不算多一行空行
    return s.split("\n") if s else []


def _row(tag, aln, atext, bln, btext):
    return {
        "tag": tag,
        "left": {"n": aln + 1, "text": atext} if aln is not None else None,
        "right": {"n": bln + 1, "text": btext} if bln is not None else None,
    }


def stats(rows):
    """改动计数：界面用它显示「改动 N 处」。"""
    out = {"add": 0, "del": 0, "modify": 0, "equal": 0, "changes": 0}
    for r in rows or []:
        out[r["tag"]] = out.get(r["tag"], 0) + 1
    out["changes"] = out["add"] + out["del"] + out["modify"]
    return out


def _with_context(rows, ctx):
    """只保留变更行及其前后各 ctx 行（折叠的部分不返回）。"""
    keep = set()
    for i, r in enumerate(rows):
        if r["tag"] != "equal":
            for k in range(max(0, i - ctx), min(len(rows), i + ctx + 1)):
                keep.add(k)
    return [r for i, r in enumerate(rows) if i in keep]


def unified(before, after, context=3):
    """顺手给一个 unified diff 文本（复制到 issue 里用）。"""
    import difflib
    return "\n".join(difflib.unified_diff(
        _as_lines(before), _as_lines(after),
        fromfile="修改前", tofile="合并后", lineterm="", n=context))


__all__ = ["diff_lines", "stats", "unified"]

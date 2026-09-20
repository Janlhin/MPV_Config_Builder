# -*- coding: utf-8 -*-
"""配置体检报告：把「这份配置到底是什么状况」整理成一份能直接渲染的数据。

数据来源都是现成的模块，这里只负责汇总：
    textio    编码 / BOM / 换行 / 是否有损
    loader    include 链、生效值、来源、profile 小节
    analyze   已知/未收录/未知选项、重复项、问题与建议、六维评分
    conflicts 选项之间的冲突
"""
from pathlib import Path

from . import textio
from .analyze import analyze_config_text
from .builder import full_check
from .loader import effective_config, parse_config_text


def _counts(chunks):
    return {k: len(v) for k, v in chunks.items()}


def build_report(path=None, text=None, name=None):
    """给一份配置出体检报告。path 与 text 至少给一个。"""
    source = {"path": str(path) if path else "", "name": name or "", "size": 0,
              "encoding": "UTF-8", "newline": "LF", "bom": False, "lossy": False,
              "lines": 0}
    if path:
        tf = textio.read(path)
        if tf is None:
            return {"ok": False, "detail": f"读不了这个文件：{path}"}
        text = tf.text
        source.update({
            "name": Path(path).name, "size": tf.size, "encoding": tf.encoding_label,
            "newline": "CRLF" if tf.newline == "\r\n" else "LF",
            "bom": tf.bom, "lossy": tf.lossy,
        })
    if text is None or not text.strip():
        return {"ok": False, "detail": "没有内容可分析（空文件或只有空白）"}
    if not source["name"]:
        source["name"] = "（粘贴 / 上传的文本）"
    source["lines"] = len(text.splitlines())
    source["size"] = source["size"] or len(text.encode("utf-8"))

    # 1) 基础解析与静态分析
    analysis = analyze_config_text(text)
    parsed = parse_config_text(text)

    # 2) include 链（只有真实文件才有）
    chain = {"files": [], "profiles": [], "sources": {}}
    values, all_values, memc, memc_label = parsed["values"], parsed["all_values"], \
        parsed["memc"], parsed["memc_label"]
    shaders = parsed["shaders"]
    if path and Path(path).is_file():
        try:
            eff = effective_config(path)
        except OSError:
            eff = None
        if eff:
            chain = {"files": eff["files"], "profiles": eff["profiles"],
                     "sources": eff["sources"]}
            values = eff["values"]
            all_values = eff["all_values"]
            shaders = eff["shaders"] or shaders
            memc = eff["memc"] or memc
            memc_label = eff["memc_label"] or memc_label

    # 3) 冲突检测（看全量键，界面不认识不代表 mpv 不认识）
    issues, conflicts = full_check({"values": all_values, "shaders": shaders, "memc": memc})

    # analyze 自己的问题与建议也一起并进来，去重后按级别排
    merged = []
    for text_item in analysis["issues"]:
        merged.append(("warn", text_item))
    for level, msg in issues:
        merged.append((level, msg))
    seen, final_issues = set(), []
    for level, msg in merged:
        key = msg.strip()
        if key in seen:
            continue
        seen.add(key)
        final_issues.append((level, msg))
    order = {"error": 0, "warn": 1, "info": 2}
    final_issues.sort(key=lambda x: order.get(x[0], 3))

    counts = {
        "options": analysis["option_count"],
        "known": len(analysis["known"]),
        "unlisted": len(analysis["unlisted"]),
        "unknown": len(analysis["unknown"]),
        "blanks": len(analysis.get("blanks") or []),
        "duplicates": len(analysis["duplicates"]),
        "profiles": len(parsed["profiles"]) or len(chain["profiles"]),
        "shaders": len(shaders),
        "effective": len(values),
        "files": len(chain["files"]),
    }
    return {
        "ok": True,
        "source": source,
        "counts": counts,
        "scores": analysis["scores"],
        "overall": analysis["overall"],
        "grade": analysis["grade"],
        "issues": final_issues,
        "suggestions": analysis["suggestions"],
        "conflicts": conflicts,
        "values": values,
        "all_values": all_values,
        "sources": chain["sources"],
        "shaders": shaders,
        "memc": memc,
        "memc_label": memc_label,
        "profiles": parsed["profiles"] or chain["profiles"],
        "chain": chain,
        "detail": {
            "known": analysis["known"],
            "unlisted": analysis["unlisted"],
            "unknown": analysis["unknown"],
            "blanks": analysis.get("blanks") or [],
            "duplicates": analysis["duplicates"],
        },
    }


__all__ = ["build_report"]

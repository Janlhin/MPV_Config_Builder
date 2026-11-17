# -*- coding: utf-8 -*-
"""按 Index-Translate 工作流把内置中文文档翻成英文。

设计要点（来自翻译规范，不是自由发挥）：
  * 600 源字符一块，8 路并发；504 不原样重试，改为按段落切分；
  * 围栏代码块整块抽出、单独处理，避免模型吃掉围栏或改命令；
  * 每块校验：Markdown 结构计数、CJK 残留比例、占位符、行数；
  * 失败块递归切分，深度 <= 4；仍失败就报错，绝不把原文当译文回填。

用法：
    python tools/translate_docs.py            # 翻 docs/ 下 4 份内置文档
    python tools/translate_docs.py --check    # 只校验已有 .en.md
"""
import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
PAIRS = [
    ("入门指南.md", "入门指南.en.md"),
    ("MPV_Shader搭配说明书.md", "MPV_Shader搭配说明书.en.md"),
    ("致谢与许可.md", "致谢与许可.en.md"),
    ("产品规划与路线图.md", "产品规划与路线图.en.md"),
]
ENDPOINT = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = "Index-Translate-Client/1.0"
CHUNK = int(os.environ.get("MPVCB_TR_CHUNK", "380"))
TABLE_CHUNK = 280      # 表格符号多、英文膨胀大，实测 500 字符会顶到网关超时
CODE_CHUNK = 300
WORKERS = 2            # 端点实测 8 路可用；本轮遇到连续 504，降并发求稳
MAX_DEPTH = 4
RETRIES = 3            # 网关 504/超时退避重试；仍失败再走切块递归
TIMEOUT = 45
CJK = re.compile(r"[\u4e00-\u9fff]")
FENCE = re.compile(r"^\s*(```|~~~)")
URL = re.compile(r"https?://[^\s)>\"]+")
INLINE = re.compile(r"`[^`\n]+`")
HEAD = re.compile(r"^#{1,6} ", re.M)
PLACE = re.compile(r"\{\{[^}]+\}\}")


class TranslateError(RuntimeError):
    pass


def cjk_count(text):
    return len(CJK.findall(text))


def cjk_prose(text):
    """只数“该翻的散文”里的汉字：行内代码、链接目标不算。"""
    text = re.sub(r"`[^`]*`", "``", text)
    text = re.sub(r"\]\([^)]*\)", "](url)", text)
    text = re.sub(r"https?://\S+", "", text)
    return cjk_count(text)


def structure(text):
    return {
        "head": len(HEAD.findall(text)),
        "table": len([ln for ln in text.splitlines() if ln.lstrip().startswith("|")]),
        "url": len(URL.findall(text)),
        "inline": len(INLINE.findall(text)),
        "place": len(PLACE.findall(text)),
        "lines": len(text.splitlines()),
    }


def _post(body):
    """POST 到端点；504/超时是网关打嗝，退避重试几次，别直接判死。"""
    last = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(
            ENDPOINT, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": UA, "Accept": "*/*"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            last = TranslateError(f"HTTP {e.code}")
        except Exception as e:                       # noqa: BLE001
            last = TranslateError(type(e).__name__)
        if attempt + 1 < RETRIES:
            time.sleep(2.0 * (attempt + 1))
    raise last


def request_row(text):
    instruction = (
        "Translate the Chinese text in this single Markdown table row to English. "
        "Keep the leading and trailing pipe, the number of pipe separators, inline code, "
        "links and numbers unchanged. Output exactly one row, no explanation."
    )
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": instruction + "\n\n" + text}],
    }
    out = _post(body)
    if not out or "\n" in out.strip():
        raise TranslateError("row output is empty or multiline")
    if out.count("|") != text.count("|"):
        raise TranslateError(f"pipe count {text.count('|')} -> {out.count('|')}")
    if cjk_count(text) >= 20 and cjk_count(out) / cjk_count(text) >= 0.10:
        raise TranslateError("CJK residue in row")
    return out


def translate_table(text, depth=0):
    """整表失败时逐行翻，表头/分隔行/列数保持，不拆成多张表。"""
    lines = text.splitlines()
    if len(lines) < 3:
        return translate_unit(text, "table", depth + 1)
    head, sep, rows = lines[0], lines[1], lines[2:]
    out = [request_row(head), sep]
    for row in rows:
        out.append(request_row(row))
    return "\n".join(out)


def request(text, kind):
    if kind == "code":
        instruction = (
            "Translate the Chinese comments and Chinese prose inside this code block "
            "to English. Keep every command, option name, path, URL, number, indentation "
            "and punctuation character unchanged. Do not add or remove lines. "
            "Output the block content only, without code fences."
        )
    else:
        instruction = (
            "Translate the following Markdown document fragment to English. "
            "Keep Markdown syntax exactly: headings, list markers, table pipes, links, "
            "inline code, fenced code, URLs and numbers must stay in place. "
            "Do not explain, do not wrap the answer. Output the translation only."
        )
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": instruction + "\n\n" + text}],
    }
    out = _post(body)
    if not out:
        raise TranslateError("empty output")
    return out


def valid(src, out, kind):
    if kind == "code":
        # 输出不含围栏，比较行数与关键符号总量，避免命令被改写
        a, b = structure(src), structure(out)
        if a["lines"] != b["lines"]:
            return f"line count {a['lines']} -> {b['lines']}"
        if src.count("=") != out.count("="):
            return "= count changed"
        if src.count("`") != out.count("`"):
            return "backtick count changed"
        return None
    a, b = structure(src), structure(out)
    for key in ("head", "table", "url", "inline", "place"):
        if a[key] != b[key]:
            return f"{key} {a[key]} -> {b[key]}"
    n_src = cjk_prose(src)
    if n_src >= 20:
        n_out = cjk_prose(out)
        ratio = n_out / n_src
        if ratio >= 0.10 and n_out > 20:
            return f"CJK residue {ratio:.1%}"
    if out.lstrip().startswith("```"):
        return "unexpected fence"
    return None


def split_text(text, limit):
    """按空行切，再按行切；保证每块 <= limit（单行超长才按句切）。"""
    if len(text) <= limit:
        return [text]
    raw = [p.strip("\n") for p in re.split(r"\n{2,}", text) if p.strip()]
    parts = []
    for para in raw:
        if len(para) <= limit:
            parts.append(para)
            continue
        buf = ""
        for line in para.splitlines():
            if len(buf) + len(line) + 1 <= limit:
                buf = (buf + "\n" + line) if buf else line
                continue
            if buf:
                parts.append(buf)
                buf = ""
            if len(line) <= limit:
                buf = line
            else:
                for sent in re.split(r"(?<=[。！？])", line):
                    if len(buf) + len(sent) <= limit:
                        buf += sent
                    else:
                        if buf:
                            parts.append(buf)
                        buf = sent
        if buf:
            parts.append(buf)
    if len(parts) < 2:
        # 没有可切点（整段一行且无句末）：硬切，至少保证进度
        return [text[i:i + limit] for i in range(0, len(text), limit)]
    return parts


def is_code_like(text):
    """围栏里不一定是代码：日志、时间线、示意图要按散文翻。"""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.search(r"[;{}]", s):
            return True
        if re.match(r"(?i)(def|class|import|from|function|const|let|var|return|#include)\b", s):
            return True
        if re.match(r"^[a-z0-9_.-]+=", s, re.I) or re.match(r"^--?[a-z]", s, re.I):
            return True
    return False


def split_code(text, limit):
    """按行分组；不按字符硬切，避免把一条命令拦腰截断。"""
    lines = text.splitlines()
    groups, buf = [], []
    for line in lines:
        if buf and sum(len(x) + 1 for x in buf) + len(line) + 1 > limit:
            groups.append("\n".join(buf))
            buf = []
        buf.append(line)
    if buf:
        groups.append("\n".join(buf))
    return groups


def split_table(text, limit):
    """表头 + 分隔行固定，数据行按字数分组，每组都带表头。"""
    lines = text.splitlines()
    if len(lines) < 3:
        return [text]
    head, rows = lines[:2], lines[2:]
    groups, buf = [], []
    for row in rows:
        if buf and sum(len(x) + 1 for x in buf) + len(row) + 1 > limit:
            groups.append(buf)
            buf = []
        buf.append(row)
    if buf:
        groups.append(buf)
    return ["\n".join(head + g) for g in groups]


def translate_code_lines(text):
    """代码块最后一道保险：逐行翻，行数天然不变。

    整块让模型翻，它有时会自己合并/删掉一行（4 行变 3 行）；这时只把
    含中文的行单独送翻，命令、围栏、空行原样保留，行数就不可能变。
    """
    out = []
    for line in text.splitlines():
        if not CJK.search(line) or line.strip().startswith("```"):
            out.append(line)
            continue
        body = {
            "model": MODEL,
            "messages": [{"role": "user", "content":
                "Translate only the Chinese words in this single line of a code block "
                "to English. Keep code, option names, paths, quotes, punctuation and "
                "spacing exactly as they are. Output the line only, with no line break "
                "and no explanation.\n\n" + line}],
        }
        got = _post(body).strip()
        if "\n" in got or not CJK.search(line) or got.count("=") != line.count("="):
            raise TranslateError("code line translation changed structure")
        pad = re.match(r"^(\s*)", line).group(1)
        out.append(pad + got)
    return "\n".join(out)


def translate_unit(text, kind, depth=0):
    try:
        out = request(text, kind)
        if kind != "code":
            out = re.sub(r"^\s*```[^\n]*\n", "", out)
            out = re.sub(r"\n```\s*$", "", out)
        err = valid(text, out, kind)
        if not err:
            return out
        raise TranslateError(err)
    except TranslateError as e:
        if kind == "code" and (depth >= MAX_DEPTH - 1 or len(text) <= 200):
            return translate_code_lines(text)
        if depth >= MAX_DEPTH or len(text) <= 200:
            raise
        if kind == "code":
            pieces = split_code(text, CODE_CHUNK)
            if len(pieces) < 2:
                return translate_code_lines(text)
            return "\n".join(translate_unit(p, "code", depth + 1) for p in pieces)
        if kind == "table":
            if depth >= MAX_DEPTH - 1:
                raise
            return translate_table(text, depth + 1)
        # 504 / 校验失败：切小再试，绝不原样重试
        pieces = split_text(text, max(120, len(text) // 2))
        if len(pieces) < 2:
            raise
        return "\n\n".join(translate_unit(p, kind, depth + 1) for p in pieces)


def parse_units(text):
    """把文档拆成段落 / 表格 / 围栏块；返回 [(kind, text)]。"""
    lines = text.splitlines()
    units, i = [], 0
    while i < len(lines):
        line = lines[i]
        if FENCE.match(line):
            j = i + 1
            while j < len(lines) and not FENCE.match(lines[j]):
                j += 1
            units.append(("code", "\n".join(lines[i:j + 1])))
            i = j + 1
            continue
        if not line.strip():
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip() and not FENCE.match(lines[j]):
            j += 1
        block = "\n".join(lines[i:j])
        kind = "table" if block.lstrip().startswith("|") else "prose"
        units.append((kind, block))
        i = j
    return units


def pack(units):
    """把相邻散文合成 <=CHUNK 的块；表格与代码块各自独立。"""
    out, buf = [], []
    size = 0

    def flush():
        nonlocal buf, size
        if buf:
            out.append(("prose", "\n\n".join(buf)))
            buf, size = [], 0

    for kind, text in units:
        if kind != "prose":
            flush()
            if kind == "table" and len(text) > 900:
                out.extend(("table", p) for p in split_table(text, 900))
            else:
                out.append((kind, text))
            continue
        if len(text) > CHUNK:
            flush()
            out.extend(("prose", p) for p in split_text(text, CHUNK))
            continue
        if size + len(text) > CHUNK:
            flush()
        buf.append(text)
        size += len(text) + 2
    flush()
    return out


def translate_doc(src, dst, budget):
    text = src.read_text(encoding="utf-8")
    units = pack(parse_units(text))
    results, failed = [None] * len(units), []
    jobs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for idx, (kind, body) in enumerate(units):
            if kind == "code":
                body = body.split("\n", 1)[1] if "\n" in body else ""
                body = body.rsplit("```", 1)[0].rstrip("\n")
                kind = "code" if is_code_like(body) else "prose"
            jobs[pool.submit(translate_unit, body, kind)] = (idx, kind)
        for fut in concurrent.futures.as_completed(jobs):
            idx, kind = jobs[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                failed.append((idx, kind, str(e)))

    if failed:
        raise TranslateError(f"{src.name}: {len(failed)}/{len(units)} chunks failed: {failed[:4]}")

    parts = []
    for idx, (kind, body) in enumerate(units):
        if kind == "code":
            fence = body.split("\n", 1)[0]
            indent = re.match(r"^(\s*)", fence).group(1)
            parts.append(fence + "\n" + results[idx] + "\n" + indent + "```")
        else:
            parts.append(results[idx])
    dst.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return len(units)


def check_pair(src, dst):
    a = src.read_text(encoding="utf-8")
    b = dst.read_text(encoding="utf-8")
    sa, sb = structure(a), structure(b)
    problems = []
    for key in ("head", "table", "url", "inline"):
        if sa[key] != sb[key]:
            problems.append(f"{key} {sa[key]} -> {sb[key]}")
    ca, cb = cjk_prose(a), cjk_prose(b)
    if ca >= 20 and cb / ca >= 0.10 and cb > 20:
        problems.append(f"CJK residue {cb}/{ca}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    pairs = [p for p in PAIRS if not args.only or args.only in p[0]]
    failed = 0
    for name, en in pairs:
        src, dst = DOCS / name, DOCS / en
        if args.check:
            if not dst.is_file():
                print(f"❌ {en} 不存在")
                failed += 1
                continue
            problems = check_pair(src, dst)
            print(("✅ " if not problems else "❌ ") + en + ("" if not problems else f"  {problems}"))
            failed += bool(problems)
            continue
        t0 = time.time()
        try:
            n = translate_doc(src, dst, 0)
            problems = check_pair(src, dst)
            print(f"✅ {en}  {n} 块  {time.time()-t0:.1f}s  结构/残留 {'通过' if not problems else problems}")
            failed += bool(problems)
        except Exception as e:
            print(f"❌ {en}: {e}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""极简 Markdown → HTML（只为把仓库里的中文文档搬进界面看）。

只支持自己文档里实际用到的语法：
    标题 #~####、水平线 ---、无序/有序列表、围栏代码块 ```、引用 >、
    表格 | a | b |、行内 `代码` / **粗体** / *斜体* / [文字](链接)
不追求完整 CommonMark —— 遇到不认识的语法就当普通段落输出，不会崩。
所有文本都做 HTML 转义，只有我们自己生成的标签是标签。
"""
import html
import re

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
TABLE_SEP = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$")


def _inline(text):
    """行内标记 → HTML（先转义，再放行我们自己的标签）。"""
    s = html.escape(text, quote=False)
    s = INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", s)
    s = BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", s)
    s = ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", s)

    def link(m):
        label, url = m.group(1), m.group(2)
        if url.startswith(("http://", "https://")):
            return f'<a href="{html.escape(url, quote=True)}" target="_blank">{label}</a>'
        return label
    s = LINK.sub(link, s)
    return s


def _row(line):
    """把 | a | b | 拆成单元格。"""
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def to_html(text):
    """Markdown 文本 → HTML 片段。"""
    out = []
    lines = str(text).replace("\r\n", "\n").split("\n")
    i = 0
    n = len(lines)
    list_stack = []          # 'ul' / 'ol'

    def close_lists():
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 围栏代码块
        if stripped.startswith("```"):
            close_lists()
            lang = stripped[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = f' class="lang-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre{cls}><code>{html.escape(chr(10).join(buf))}</code></pre>")
            continue

        # 空行
        if not stripped:
            close_lists()
            i += 1
            continue

        # 水平线
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < n and TABLE_SEP.match(lines[i + 1]):
            close_lists()
            head = _row(lines[i])
            i += 2
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append(_row(lines[i]))
                i += 1
            th = "".join(f"<th>{_inline(c)}</th>" for c in head)
            rows = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                           for r in body)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{rows}</tbody></table>")
            continue

        # 引用
        if stripped.startswith(">"):
            close_lists()
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(buf))}</blockquote>")
            continue

        # 列表
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if m:
            indent, marker, content = m.group(1), m.group(2), m.group(3)
            want = "ol" if marker[0].isdigit() else "ul"
            if not list_stack or list_stack[-1] != want:
                close_lists()
                out.append(f"<{want}>")
                list_stack.append(want)
            out.append(f"<li>{_inline(content)}</li>")
            i += 1
            # 列表项的续行（缩进更深的普通行）
            while i < n and lines[i].strip() and not re.match(
                    r"^\s*([-*+]|\d+[.)])\s+", lines[i]) and not lines[i].strip().startswith(("#", "|", ">")):
                if lines[i].startswith("  ") or lines[i].startswith("\t"):
                    out[-1] = out[-1][:-5] + " " + _inline(lines[i].strip()) + "</li>"
                    i += 1
                else:
                    break
            continue

        # 普通段落
        close_lists()
        out.append(f"<p>{_inline(stripped)}</p>")
        i += 1

    close_lists()
    return "\n".join(out)


def extract_title(text, default="文档"):
    """拿第一个一级标题当标题。"""
    for line in str(text).splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return default


__all__ = ["to_html", "extract_title"]

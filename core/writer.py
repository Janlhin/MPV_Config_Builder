# -*- coding: utf-8 -*-
"""配置写入：备份、include 方式、合并方式。

两种写入方式：
    include  生成独立的 mpv-builder.conf，并在主 mpv.conf 里追加一行 include
    merge    直接把键值合并进主 mpv.conf（保留其它内容）

编码一律走 core.textio：读的时候认得出 GBK，写回去还按原编码，不把用户的文件偷偷改成 UTF-8。
"""
import posixpath
import re
from pathlib import Path

from . import textio
from .schema import format_option_line

INCLUDE_FILENAME = "mpv-builder.conf"
INCLUDE_LINE = f'include = "~~/{INCLUDE_FILENAME}"'

# mpv 的 `[name]` 是 profile 小节，里面的选项只在条件满足时生效。
# 合并写入必须认这个边界 —— 否则「改全局 scale」会静默改掉第一个小节里那行。
SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
KEY_RE = re.compile(r"^(\s*)(#?)\s*([A-Za-z0-9_.\-]+)\s*=\s*(.*)$")

HEADER = [
    "# ============================================",
    "# 由 MPV Config Builder 生成（基础模式）",
    "# 想撤销：删掉本文件，并删除主 mpv.conf 里那一行 include 即可",
    "# ============================================",
    "",
]

# 合并写入时，新增的键放在文件末尾这样一个块里，方便用户一眼找到、
# 也方便手工回滚。文案必须和 core/builder.py 的抬头保持一致。
MERGE_MARKER = "由 MPV Config Builder 写入"
_M = re.escape(MERGE_MARKER)
_BAR = r"[#=*\-]{3,}"
MERGE_MARKER_RE = re.compile(rf"^\s*(?:{_BAR}\s*)?#\s*{_M}\s*#?\s*(?:{_BAR})?\s*$")
_BORDER_RE = re.compile(rf"^\s*{_BAR}\s*$")


def _scan_marker_block(lines, i):
    """从抬头行 `i` 扫出整个块，返回 (start, end, keys, ok)。

    块的形状（写出去的就是这个）：
        <可选边框>
        # 由 MPV Config Builder 写入 #
        <可选边框>
        <空行>
         key = value      ← 一个前导空格
         key = value
        <空行>

    ⚠ 两条铁律，都是踩出来的：

    ① **遇到第一个空行就收尾**，不要"跳过空行接着找"。
       我第一版就是跳着找的，结果扫描范围越过了块尾、一头扎进块后面
       用户自己写的内容里 —— 碰上 `keep-open = yes` 这种不带前导空格的
       正常配置行，整块就被判成"认不出"而拒绝处理；更糟的是如果那行
       恰好带前导空格，它会被当成块里的键**搬进工具区**。

    ② 认不出的形状 → `ok=False`，调用方**整块不动**。
       宁可留着重复块让用户手工处理，也不能吃掉人家的配置。
    """
    start = i
    if i - 1 >= 0 and _BORDER_RE.match(lines[i - 1]) and not MERGE_MARKER_RE.match(lines[i - 1]):
        start = i - 1
    end = i + 1
    if end < len(lines) and _BORDER_RE.match(lines[end]) and not MERGE_MARKER_RE.match(lines[end]):
        end += 1
    if end < len(lines) and not lines[end].strip():
        end += 1                          # 吃掉标题后的那一个空行
    keys = []
    ok = True
    while end < len(lines):
        ln = lines[end]
        if not ln.strip():
            end += 1                      # 吃掉块尾空行，到此为止
            break
        if ln.startswith(" ") and "=" in ln:
            keys.append(ln)
            end += 1
            continue
        ok = False
        break
    return start, end, keys, ok


def marker_block_span(lines):
    """(最后一个抬头块里所有行的下标集合, 整块的 [start, end))；没有块返回 (set(), None)。

    用途是 W-1 的核心判断：判断一个键是"已经在块里"还是"要新建"。
    """
    idx = [i for i, ln in enumerate(lines) if MERGE_MARKER_RE.match(ln)]
    if not idx:
        return set(), None
    start, end, _keys, _ok = _scan_marker_block(lines, idx[-1])
    inside = {i for i in range(start, end) if lines[i].strip()
              and not MERGE_MARKER_RE.match(lines[i])
              and not _BORDER_RE.match(lines[i])}
    return inside, (start, end)


def marker_header():
    """抬头块的四行（不含前后空行）。文案必须和 core/builder.py 一致。"""
    return ["####################", f"# {MERGE_MARKER} #", "####################"]


def _compose_marker_section(existing, new_lines):
    """拼出「抬头 + 原有键 + 新键」的完整区块。

    ⚠ 新键放在**原有键之后**。放在之前会把原有内容挤到下面，
    读起来就像"新键覆盖了旧的"—— 虽然 mpv 只认最后一次出现，但语义是反的。
    """
    out = [""] + marker_header() + [""]
    out += [ln for ln in existing if ln.strip()]
    out += [ln for ln in new_lines if ln.strip()]
    out.append("")
    return out


def has_duplicate_marker(lines):
    """块的抬头出现了不止一次（历史遗留，或者块被复制过）。"""
    return sum(1 for ln in lines if MERGE_MARKER_RE.match(ln)) > 1


def _squeeze_blanks(lines):
    """把连续空行压成一个（块重建后接缝处容易多出空行）。"""
    out = []
    for ln in lines:
        if not ln.strip() and out and not out[-1].strip():
            continue
        out.append(ln)
    return out


def clean_duplicate_markers(lines):
    """合并多余的抬头块：把它们的键汇总进**第一个**块，其余块删掉。

    只认这个块自己的规矩（见 `_scan_marker_block`）。任意一个块里有不认识的
    形状就**整体不动**，返回 ([原样], 0)。
    返回 (新行, 删掉了几个块)。
    """
    idx = [i for i, ln in enumerate(lines) if MERGE_MARKER_RE.match(ln)]
    if len(idx) < 2:
        return list(lines), 0

    blocks = []
    for i in idx:
        start, end, keys, ok = _scan_marker_block(lines, i)
        # 只留键行本身 —— 块内原有的空行不带走，否则每写一次就多攒一坨空行
        blocks.append({"start": start, "end": end, "keys": keys, "ok": ok})

    if not all(b["ok"] for b in blocks):
        return list(lines), 0

    first = blocks[0]
    merged = []
    seen = set()
    for b in blocks:
        for k in b["keys"]:
            kk = k.strip()
            if kk not in seen:
                seen.add(kk)
                merged.append(k)

    out = []
    drop = set()
    for b in blocks[1:]:
        drop.update(range(b["start"], b["end"]))
    for i, ln in enumerate(lines):
        if i == first["start"]:
            out.extend(_compose_marker_section(merged, []))
        if i in drop:
            continue
        if first["start"] <= i < first["end"]:
            continue                      # 第一个块的旧内容由上面重建
        out.append(ln)
    # 块整体重建后，接缝处可能多出空行，把连续空行压成一个
    return _squeeze_blanks(out), len(blocks) - 1


def backup_file(path):
    """备份文件，返回备份路径；文件不存在返回 None。"""
    return textio.backup(path)


def read_text(path):
    """按原编码读取（认 UTF-8 / GBK / Big5），失败返回空串。"""
    return textio.read_text(path)


def build_include_text(params, note=""):
    """生成 include 文件内容。"""
    lines = list(HEADER)
    if note:
        lines.append("# " + note)
        lines.append("")
    for key, value in params.items():
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def write_include(target_dir, text, filename=INCLUDE_FILENAME):
    """写入 include 文件（先备份旧文件），返回 (路径, 备份路径)。

    新文件用 UTF-8 无 BOM；如果这个文件已经存在且是别的编码，就跟它保持一致。
    """
    target = Path(target_dir) / filename
    tf = textio.read(target)
    backup = backup_file(target)
    if tf is not None:
        textio.write_atomic(target, textio.encode(text, tf.encoding, tf.bom))
    else:
        textio.write_atomic(target, text.encode("utf-8"))
    return target, backup


def _norm_mpv_value(value):
    """规范化 mpv 的路径值：去引号 / 反斜杠转正斜杠 / 去掉 ./ / 小写。"""
    v = str(value or "").strip().strip('"').strip("'").strip()
    v = v.replace("\\", "/")
    while v.startswith("./"):
        v = v[2:]
    return posixpath.normpath(v).lower() if v else ""


def has_include_line(text):
    """主配置的**全局区**是否已有指向 mpv-builder.conf 的启用 include 行。

    旧实现是 `INCLUDE_FILENAME in text`：注释行、别的 profile 里的引用都会命中，
    于是接口报「已有 include 行」，配置却永远不生效（踩过的坑）。
    """
    lines = text.splitlines()
    where = _section_map(lines)
    want = _norm_mpv_value(f"~~/{INCLUDE_FILENAME}")
    for i, ln in enumerate(lines):
        if where[i] is not None:              # profile 小节里的 include 不算
            continue
        m = KEY_RE.match(ln)
        if not m or m.group(2):               # 注释行不算
            continue
        if m.group(3).lower() not in ("include", "include-append"):
            continue
        value = re.split(r"\s+#", m.group(4), 1)[0]
        if _norm_mpv_value(value) == want:
            return True
    return False


def ensure_include_line(main_conf):
    """确保主 mpv.conf 里有 include 行；返回 (是否修改, 备份路径, 说明)。"""
    main = Path(main_conf)
    tf = textio.read(main)
    text = tf.text if tf is not None else ""
    if has_include_line(text):
        return False, None, "主配置里已有 include 行，未改动"
    backup = backup_file(main) if main.is_file() else None
    body = text.rstrip("\n")
    new_text = (body + "\n\n" if body else "") + INCLUDE_LINE + "\n"
    main.parent.mkdir(parents=True, exist_ok=True)
    if tf is not None:
        textio.write_atomic(main, textio.encode(new_text, tf.encoding, tf.bom, tf.newline))
    else:
        textio.write_atomic(main, new_text.encode("utf-8"))
    return True, backup, "已在主配置末尾追加 include 行"


def _section_map(lines):
    """每一行的归属：某个 profile 小节的名字，或 None（全局区）。

    语义：`[name]` 之前的所有行属于**上一个小节**（或全局区）；
    从 `[name]` 的下一行起属于 name，直到下一个 `[next]`。

    必须这么算，否则会出两类错：
      · 把表头行算进小节 → 扫描时一匹配到 `[p]` 就带着"在小节里"的标记一路走下去，
        后面的全局行全被判成小节的，取消勾选再也注释不掉任何东西；
      · 表头行算成全局 → 它自己会被当成一个 key 去匹配。
    """
    out = []
    current = None
    for ln in lines:
        out.append(current)               # 先记归属，再看这一行是不是新表头
        m = SECTION_RE.match(ln)
        if m:
            current = m.group("name").strip()
    return out


# 追加型键：同名多行是**合法语义**（mpv 会依次追加），不能像普通键那样统一改写。
APPEND_KEYS = {
    "glsl-shader", "glsl-shaders-append", "glsl-shader-append",
    "vf-append", "af-append", "include", "include-append",
}


def _active_rows(lines, where, key, want_sections):
    """全局区（及指定小节）里该键的**全部启用行**，按文件顺序。"""
    rows = []
    for i, ln in enumerate(lines):
        if where[i] is not None and where[i] not in want_sections:
            continue
        m = KEY_RE.match(ln)
        if m and not m.group(2) and m.group(3) == key:
            rows.append((i, m))
    return rows


def apply_params_to_lines(lines, params, sections=None):
    """把键值合并进已有行：替换启用行 → 取消注释同名行 → 追加。返回 (新行, 改动说明)。

    **只改全局区**：`[profile]` 小节里的同名键一律不碰（除非 sections 明确要求）。
    这是与 core.loader 对称的行为 —— loader 读的时候区分小节，writer 写的时候也必须区分，
    否则「改全局 scale」会静默改掉第一个小节里的那行。
    """
    out = list(lines)
    changes = []
    where = _section_map(out)
    want_sections = set(sections or ())

    def find_comment(key):
        for i, ln in enumerate(out):
            if where[i] is not None and where[i] not in want_sections:
                continue                      # profile 小节里的行不动
            m = KEY_RE.match(ln)
            if m and m.group(3) == key and m.group(2):
                return i, m
        return None, None

    appended = []
    for key, value in params.items():
        actives = _active_rows(out, where, key, want_sections)
        if actives:
            if key in APPEND_KEYS:
                # 追加型键：多行是合法语义，只改最后一处（mpv 依次追加）
                i, m = actives[-1]
                old = m.group(4).strip()
                out[i] = m.group(1) + format_option_line(key, value)
                if old != str(value).strip():
                    changes.append(f"{key}: {old} -> {value}")
                if len(actives) > 1:
                    changes.append(f"{key}: 追加型键，只改最后一处")
                continue
            # 普通键：mpv 以**最后一处**为准，读侧（loader）也是这么读的。
            # 所以把所有同名启用行统一改成新值 —— 否则界面显示「已合并」，
            # 播放行为却被后面的旧值覆盖（踩过的坑）。
            olds = []
            for i, m in actives:
                olds.append(m.group(4).strip())
                out[i] = m.group(1) + format_option_line(key, value)
            if len(actives) > 1:
                changes.append(
                    f"{key}: 修正了 {len(actives) - 1} 处重复"
                    f"（{len(actives)} 处同名键已统一）")
            elif olds[0] != str(value).strip():
                changes.append(f"{key}: {olds[0]} -> {value}")
            continue
        idx_comment, m_comment = find_comment(key)
        if idx_comment is not None:
            out[idx_comment] = m_comment.group(1) + format_option_line(key, value)
            changes.append(f"{key}: 取消注释 -> {value}")
        else:
            appended.append(format_option_line(key, value))
            changes.append(f"{key}: 新增 {value}")

    if appended:
        # 先合并历史遗留的重复抬头块（W-1：真机上攒出过两个）。
        out, _merged = clean_duplicate_markers(out)
        inside, span = marker_block_span(out)
        # 块里已经有这个键的行，就当作纯补充丢掉 —— 否则会在同一块里出现两次。
        # 走到 appended 就说明全局区没有它的启用/注释行，但块里可能有一行
        # 认不出来的形状（比如用户手工塞进去的），重复写上去反而更难读。
        existing = {out[i].split("=", 1)[0].strip() for i in inside if "=" in out[i]}
        fresh = [" " + a for a in appended if a.split("=", 1)[0].strip() not in existing]
        if fresh:
            if span is None:
                out = _squeeze_blanks(out + _compose_marker_section([], fresh))
            else:
                # ⚠ 只替换**块本身**，块后面的用户内容原样留在右边。
                # 以前是"在文件末尾追加"，如果用户在块后面又写了东西，
                # 新键就会被甩到用户内容之后 —— 工具区和用户区就搅在一起了。
                kept = [out[i] for i in sorted(inside)]
                out = (out[:span[0]]
                       + _compose_marker_section(kept, fresh)
                       + out[span[1]:])
    # 无论这次有没有新增，都把多余空行压掉 —— 只改值不新增的那次
    # 会把块重建留下来，不压就会一直攒着
    return _squeeze_blanks(out), changes


def merge_into_file(main_conf, params):
    """把键值合并进主配置文件（先备份），返回 (改动列表, 备份路径)。"""
    main = Path(main_conf)
    tf = textio.read(main)
    raw = tf.text if tf is not None else ""
    newline = tf.newline if tf is not None else "\n"
    new_lines, changes = apply_params_to_lines(raw.splitlines(), params)
    backup = backup_file(main) if main.is_file() else None
    main.parent.mkdir(parents=True, exist_ok=True)
    write_lines(main, new_lines, newline, backup=False, template=tf)
    return changes, backup


def comment_keys_in_lines(lines, keys):
    """把指定的键所在「启用行」注释掉（取消勾选时用）。返回 (新行, 改动说明)。

    同样只动全局区：profile 小节里的行不碰。
    """
    if not keys:
        return list(lines), []
    want = set(keys)
    out = list(lines)
    where = _section_map(out)
    changes = []
    for i, ln in enumerate(out):
        if where[i] is not None:
            continue                      # profile 小节里的行不动
        m = KEY_RE.match(ln)
        if not m or m.group(2):            # 已经是注释行，跳过
            continue
        if m.group(3) in want:
            out[i] = m.group(1) + "#" + ln.lstrip()
            changes.append(f"{m.group(3)}: 已注释")
    return out, changes


def apply_state_to_lines(lines, params, disable_keys=(), sections=None):
    """合并参数 + 注释掉被取消勾选的键。返回 (新行, 改动说明)。"""
    new_lines, changes = apply_params_to_lines(lines, params, sections=sections)
    new_lines, more = comment_keys_in_lines(new_lines, disable_keys)
    return new_lines, changes + more


def tidy_conf_file(main_conf, dry_run=True):
    """把配置里重复的「由 MPV Config Builder 写入」抬头块合并成一个。

    为什么要有这个动作：W-1 那个缺陷（写入时无条件在末尾追加抬头）在修之前
    会让每次写入都多一个块 —— 真机上 `mpv.conf` 已经攒了两个。修好写入逻辑
    只保证"以后不再多"，**已经多出来的那两个得有人收拾**，否则用户要手工删。

    dry_run=True 只回报会怎么改，**不碰磁盘**（体检页的预览用）。
    只认这个块自己的规矩，块里有不认识的形状就整块不动 —— 宁可留着重复，
    也不要吃用户的配置。返回 dict：changed / dropped / blocks_before / reason。
    """
    p = Path(main_conf)
    tf = textio.read(p)
    if tf is None:
        return {"ok": False, "changed": False, "dropped": 0,
                "blocks_before": 0, "reason": "读不到文件"}
    lines = tf.text.splitlines()
    before = sum(1 for ln in lines if MERGE_MARKER_RE.match(ln))
    if before < 2:
        return {"ok": True, "changed": False, "dropped": 0,
                "blocks_before": before,
                "reason": "没有重复的抬头块（%d 个），不用动" % before}
    new_lines, dropped = clean_duplicate_markers(lines)
    if not dropped:
        return {"ok": True, "changed": False, "dropped": 0, "blocks_before": before,
                "reason": "有 %d 个抬头块，但里面有认不出的行 —— 整块保留不动，"
                          "请手工处理" % before}
    res = {"ok": True, "changed": True, "dropped": dropped,
           "blocks_before": before, "reason": "合并了 %d 个重复块" % dropped}
    if not dry_run:
        bak = write_lines(p, new_lines, tf.newline, backup=True, template=tf)
        # 返回字符串而不是 Path：这个 dict 要直接丢给 JSON 接口
        res["backup"] = str(bak) if bak else ""
        res["text"] = "\n".join(new_lines) + tf.newline
    else:
        res["text"] = "\n".join(new_lines) + tf.newline
    return res


def write_lines(path, lines, newline="\n", backup=True, template=None, encoding="utf-8",
                bom=False, report=None):
    """写回文件（默认先备份），返回备份路径。

    template 传一个 textio.TextFile 时，按它的原编码 / BOM / 换行写回 —— 这样 GBK 的配置
    改完还是 GBK，不会因为改一行就把整份文件变成 UTF-8。

    report 传 dict 时带回 {"encoding": 实际编码, "fallback": 是否回退 UTF-8}。
    """
    p = Path(path)
    bak = backup_file(p) if (backup and p.is_file()) else None
    body = newline.join(lines) + newline
    if template is not None:
        encoding, bom = template.encoding, template.bom
    data, used = textio.encode_report(body, encoding, bom)
    if report is not None:
        report["encoding"] = used
        report["fallback"] = used != encoding
    textio.write_atomic(p, data)
    return bak

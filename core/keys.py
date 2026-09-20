# -*- coding: utf-8 -*-
"""按键绑定：读 mpv 的 input.conf / input_uosc.conf，改完按原格式写回。

两个来源，缺一不可：
    内置默认   data/mpv_keybindings.json —— 从你自己的 mpv 里问出来的（input-bindings 属性，
               209 条，带真实命令、优先级、来源）。生成脚本见 tools/build_keybindings.py
    当前配置   目标目录里 mpv 实际会读的那个 input 文件（mpv-lazy 是 input_uosc.conf），
               逐行解析成可编辑的行

mpv-lazy 的行格式（比 mpv 官方多了个 `#!` 分类说明，社区习惯）：

    Ctrl+Shift+v      update-clipboard text; loadfile ${clipboard/text}     #! 加载 > 剪贴板URL
    #                 script-binding uosc/open-file                         #! 加载 > ※ 文件浏览器

第二行是「有命令但没绑键」的条目（uosc 菜单用的），键位那一列是空的 —— 显示成未启用，
用户想给它安个键，把键写进去就行。
"""
import json
import re
from pathlib import Path

from . import loader, textio
from .paths import data_dir

# 打包后 data/ 在解包目录里，不能用 __file__ 推（见 core/paths.py）
DATA = data_dir()
BINDINGS_DB = DATA / "mpv_keybindings.json"
COMMANDS_DB = DATA / "mpv_commands.json"

KEYCOL = 17          # 键位列宽（跟 mpv-lazy 的观感保持一致）
COMMENT_SEP = "#!"
LINE_RE = re.compile(r"^(?P<indent>\s*)(?P<off>#)?(?P<body>.*)$")
BIND_RE = re.compile(r"^(?P<key>\S+)\s+(?P<cmd>\S.*)$")
SEPARATOR_RE = re.compile(r"^[-=_*~#\s]*$")


def load_defaults():
    """内置默认绑定（读不到就返回空列表，界面照常能用）。"""
    try:
        data = json.loads(BINDINGS_DB.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data.get("bindings") or []


def load_commands():
    """mpv 的命令表（给「加一条绑定」做候选）。"""
    try:
        data = json.loads(COMMANDS_DB.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data.get("commands") or []


def db_status():
    out = {"bindings": 0, "commands": 0, "mpv": ""}
    try:
        data = json.loads(BINDINGS_DB.read_text(encoding="utf-8"))
        out["bindings"] = (data.get("meta") or {}).get("count", 0)
        out["mpv"] = (data.get("meta") or {}).get("mpv", "")
    except (OSError, ValueError):
        pass
    try:
        out["commands"] = (json.loads(COMMANDS_DB.read_text(encoding="utf-8"))
                           .get("meta") or {}).get("count", 0)
    except (OSError, ValueError):
        pass
    return out


# ---------------------------------------------------------------- 解析

def _split_comment(body):
    """把 `键 命令  #! 说明` 拆开。返回 (键, 命令, 说明)。"""
    comment = ""
    idx = body.find(COMMENT_SEP)
    if idx >= 0:
        comment = body[idx + len(COMMENT_SEP):].strip()
        body = body[:idx]
    body = body.rstrip()
    m = BIND_RE.match(body.strip())
    if not m:
        return "", "", comment
    key = m.group("key")
    cmd = m.group("cmd").strip()
    # mpv 里 `key` 单独一行也可能是命令（没绑键），靠命令表判断不像命令就当键
    if not cmd:
        return key, "", comment
    return key, cmd, comment


def _empty_key_column(body):
    """被注释掉的行：`#` 后面跟了 2 个以上空格 = 键位那一列是空的（只有命令）。"""
    return body[:1] in (" ", "\t") and body[:2].strip() == ""


def _mk_bind(row_no, raw, enabled, key, cmd, comment):
    return {
        "kind": "bind", "line": row_no, "raw": raw, "enabled": enabled,
        "key": key, "cmd": cmd, "comment": comment,
        "category": (comment.split(">")[0].strip() if ">" in comment else ""),
        "desc": (comment.split(">", 1)[1].strip() if ">" in comment else comment),
        # 记下解析时的样子：没改过的行原样写回，绝不重排/重排空格
        "orig": {"enabled": enabled, "key": key, "cmd": cmd, "comment": comment},
    }


def parse_input_conf(text):
    """把 input.conf 解析成可编辑的行列表。"""
    rows = []
    for no, raw in enumerate(str(text).splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            rows.append({"kind": "blank", "line": no, "raw": raw})
            continue
        m = LINE_RE.match(raw)
        off = bool(m.group("off")) if m else False
        body = (m.group("body") if m else raw).rstrip()
        if not body.strip():
            rows.append({"kind": "blank", "line": no, "raw": raw})
            continue
        if off and _empty_key_column(body):
            # mpv-lazy 的「只有命令、没绑键」写法：# + 对齐空格 + 命令
            key, cmd, comment = "", body.strip(), ""
            idx = cmd.find(COMMENT_SEP)
            if idx >= 0:
                comment = cmd[idx + len(COMMENT_SEP):].strip()
                cmd = cmd[:idx].strip()
            if not cmd or SEPARATOR_RE.match(cmd):
                rows.append({"kind": "comment", "line": no, "raw": raw})
                continue
            rows.append(_mk_bind(no, raw, False, key, cmd, comment))
            continue
        key, cmd, comment = _split_comment(body)
        if off and not comment:
            # 没有 #! 的注释行：只有长得像「键 命令」两段的那种，才算「被注释掉的绑定」；
            # ## 开头的标题、`# 一句话说明` 都当普通注释原样保留
            if not cmd or raw.lstrip().startswith("##"):
                rows.append({"kind": "comment", "line": no, "raw": raw})
                continue
        if not cmd and not comment:
            rows.append({"kind": "comment", "line": no, "raw": raw})
            continue
        rows.append(_mk_bind(no, raw, not off, key, cmd, comment))
    return rows


def render_rows(rows, align=None):
    """按原格式生成文本。

    没改过的行**原样写回**（连空格都不动）—— 打开再保存不应该把用户的文件重排一遍。
    改过或新增的行才按统一格式排，align=None 时自动判断原文件是不是对齐写法。
    """
    def unchanged(r):
        orig = r.get("orig")
        if not orig or not r.get("raw"):
            return False
        now = {"enabled": r.get("enabled", True), "key": r.get("key", ""),
               "cmd": r.get("cmd", ""), "comment": r.get("comment", "")}
        return orig == now

    if align is None:
        align = any(re.match(r"^\S+\s{2,}\S", (r.get("raw") or ""))
                    for r in rows if r.get("kind") == "bind" and not unchanged(r))
    width = KEYCOL if align else 1
    if align:
        for r in rows:
            if r.get("kind") == "bind" and r.get("key"):
                width = max(width, len(r["key"]) + 1)
    out = []
    for r in rows:
        if r.get("kind") != "bind":
            out.append(r.get("raw", ""))
            continue
        if unchanged(r):
            out.append(r["raw"])
            continue
        key, cmd = r.get("key", ""), r.get("cmd", "")
        comment = r.get("comment", "")
        if key:
            body = f"{key:<{width}}{cmd}" if width > 1 else f"{key} {cmd}"
        else:
            body = f"{'':<{width}}{cmd}" if width > 1 else cmd
        if comment:
            body = f"{body}    {COMMENT_SEP} {comment}"
        out.append(body if r.get("enabled", True) else "# " + body)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- 文件

def resolve_input_files(target):
    """mpv 实际会读哪个 input 文件？顺带列出目录里所有候选。"""
    base = Path(target) if target else None
    active, available, source = [], [], ""
    if not base or not base.is_dir():
        return {"active": [], "available": [], "source": source}
    try:
        eff = loader.effective_config(base / "mpv.conf")
        values = eff.get("values") or {}
        conf = str(values.get("input-conf", "")).strip()
        if conf:
            source = "mpv.conf 里的 input-conf"
            for part in loader.split_mpv_list(conf):
                active.append(_resolve_conf_path(part, base))
    except Exception:
        pass
    default = base / "input.conf"
    if default.is_file():
        active.append(default)
        source = source or "默认的 input.conf"
    for p in sorted(base.glob("input*.conf")):
        available.append(p)
    for p in active:
        if p not in available:
            available.append(p)
    # 去重、保序
    seen, uniq = set(), []
    for p in active:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return {"active": uniq, "available": available, "source": source}


def _resolve_conf_path(value, base):
    v = str(value).strip().strip('"').strip("'")
    if v.startswith("~~/"):
        return (Path(base) / v[3:]).resolve()
    p = Path(v)
    return p if p.is_absolute() else (Path(base) / v).resolve()


def load_keymap(target):
    """读当前键位表：文件 + 行 + 内置默认 + 冲突提示。"""
    info = resolve_input_files(target)
    files = []
    for p in info["available"]:
        tf = textio.read(p)
        if tf is None:
            continue
        files.append({
            "path": str(p), "name": p.name, "encoding": tf.encoding_label,
            "active": p in info["active"],
            "rows": parse_input_conf(tf.text),
        })
    main = next((f for f in files if f["active"]), files[0] if files else None)
    warnings = []
    if not files:
        warnings.append("目标目录里没有 input.conf，也没有 input-conf 指定的文件 —— "
                        "保存时会新建一个 input.conf。")
    if main:
        warns = conflicts(main["rows"])
        warnings += warns
    return {"ok": True, "source": info["source"], "active": [str(p) for p in info["active"]],
            "files": files, "main": main["path"] if main else "",
            "defaults": load_defaults(), "commands": load_commands(),
            "db": db_status(), "warnings": warnings,
            # R-24：正在改自带键位表时提醒一句（升级会被覆盖）
            "needs_promote": bool(main and needs_promote(main["path"])),
            "promote_name": USER_INPUT_NAME,
            "promote_hint": (f"你正在改的是播放器自带的 {Path(main['path']).name}，"
                             f"升级 mpv-lazy 时会把它覆盖回去。"
                             f"建议另存为 {USER_INPUT_NAME}（你的改动就保住了）"
                             if main and needs_promote(main["path"]) else "")}


def conflicts(rows):
    """同一份文件里同一个键绑了多次：mpv 以后面的为准，前面的白写。"""
    seen, out = {}, []
    for r in rows:
        if r.get("kind") != "bind" or not r.get("enabled") or not r.get("key"):
            continue
        key = r["key"]
        if key in seen:
            out.append(f"{key} 绑了不止一次（第 {seen[key]} 行和第 {r['line']} 行），"
                       f"mpv 只用后面那条。")
        else:
            seen[key] = r["line"]
    return out


# ---------------------------------------------------------------- R-24 落点

# mpv-lazy 自带的键位表。改它 = 下次升级 mpv-lazy 被覆盖。
BUNDLED_INPUT_NAMES = ("input_uosc.conf",)
USER_INPUT_NAME = "input-user.conf"

PROMOTE_HEADER = [
    "# ============================================",
    "# 这份键位表由 MPV Config Builder 生成，属于你自己",
    "# 升级 mpv-lazy / mpv 都不会覆盖它（原文件在 input_uosc.conf，没被动过）",
    "# 想撤销：把 mpv.conf 里的 input-conf 指回 ~~/input_uosc.conf 即可",
    "# ============================================",
    "",
]


def is_bundled_input(path):
    """这个键位表是不是播放器自带的（会被升级覆盖的那种）。"""
    return Path(path).name.lower() in BUNDLED_INPUT_NAMES


def needs_promote(path):
    """要不要提示用户「另存为自己的」—— 正在改自带文件时才提示。"""
    return is_bundled_input(path)


def promote_to_user_file(target, rows, name=USER_INPUT_NAME):
    """把当前编辑结果另存为「你自己的」键位表，并让 mpv.conf 指向它（R-24）。

    为什么需要：现在改的是 mpv-lazy 自带的 `input_uosc.conf`，
    下次升级 mpv-lazy 就把它覆盖回去了 —— 用户改的键全没了，而且毫无提示。

    ⚠ mpv 的 `input-conf` **只能指向一个文件**（是覆盖，不是追加）。
    所以这里只能改 `input-conf` 的值，不能"两个都读"。
    因此必须让用户显式确认 —— 界面上是个独立按钮，不是自动行为。

    返回 {"ok", "detail", "path", "backup", "mpv_conf", "mpv_backup"}。
    """
    target = Path(target)
    if not target.is_dir():
        return {"ok": False, "detail": f"目标目录不存在：{target}"}
    dest = target / name
    if dest.exists():
        return {"ok": False,
                "detail": f"{name} 已经存在了，没有覆盖它 —— "
                          f"想重新生成请先把它删掉或改名"}

    body = "\n".join(PROMOTE_HEADER) + render_rows(rows)
    try:
        dest.write_text(body, encoding="utf-8")
    except OSError as e:
        return {"ok": False, "detail": f"写不了 {name}：{e}"}

    conf = target / "mpv.conf"
    if not conf.is_file():
        return {"ok": True, "path": str(dest), "mpv_conf": "",
                "detail": f"已生成 {name}。但目录里没有 mpv.conf，"
                          f"请手动加一行：input-conf = \"~~/{name}\""}

    tf = textio.read(conf)
    text = tf.text if tf else ""
    if tf is None:
        return {"ok": False, "detail": f"读不了 mpv.conf：{conf}"}

    lines = text.splitlines()
    newline = tf.newline
    want = f'input-conf = "~~/{name}"'
    pat = re.compile(r"^(\s*)(#?)\s*input-conf\s*=", re.IGNORECASE)
    replaced = False
    for i, ln in enumerate(lines):
        if pat.match(ln):
            if not replaced:
                lines[i] = want
                replaced = True
            else:
                lines[i] = "#" + ln.lstrip()   # 多余的 input-conf 行注释掉
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines += ["# 键位表换成了自己的那份（升级 mpv-lazy 不会再覆盖）", want]

    try:
        backup = textio.write(conf, "\n".join(lines) + "\n",
                              tf.encoding, tf.bom, newline)
    except OSError as e:
        return {"ok": False, "detail": f"改不了 mpv.conf：{e}"}
    detail = f"已生成 {name}，并把 mpv.conf 的 input-conf 指过去"
    if backup:
        detail += f"（mpv.conf 已备份 {backup.name}）"
    detail += "。需要重启 mpv 生效。"
    return {"ok": True, "path": str(dest), "mpv_conf": str(conf),
            "mpv_backup": str(backup) if backup else "",
            "detail": detail}


def save_keymap(path, rows, create_if_missing=True):
    """把编辑后的行写回文件（先备份，按原编码写）。"""
    p = Path(path)
    tf = textio.read(p)
    if tf is None and not create_if_missing:
        return {"ok": False, "detail": f"文件不存在：{p}"}
    text = render_rows(rows)
    if tf is None:
        backup = None
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        except OSError as e:
            return {"ok": False, "detail": f"写入失败：{e}"}
        return {"ok": True, "detail": f"已新建 {p.name}", "path": str(p)}
    try:
        backup = textio.write(p, text, tf.encoding, tf.bom, tf.newline)
    except OSError as e:
        return {"ok": False, "detail": f"写入失败：{e}"}
    detail = f"已保存 {p.name}（{len([r for r in rows if r.get('kind') == 'bind'])} 条绑定）"
    if backup:
        detail += f"，原文件备份为 {backup.name}"
    if tf.encoding != "utf-8":
        detail += f"；按原编码 {tf.encoding_label} 写回"
    return {"ok": True, "detail": detail, "path": str(p),
            "backup": str(backup) if backup else ""}


def effective_keymap(rows, defaults):
    """把「内置默认」和「当前配置」合起来看：每个键最终生效什么。"""
    user = {}
    for r in rows:
        if r.get("kind") == "bind" and r.get("key"):
            user.setdefault(r["key"], []).append(r)
    out = []
    for b in defaults:
        key = b.get("key", "")
        mine = user.get(key) or []
        out.append({
            "key": key,
            "default_cmd": b.get("cmd", ""),
            "default_comment": b.get("comment", ""),
            "section": b.get("label", ""),
            "user_cmd": mine[-1]["cmd"] if mine else "",
            "user_line": mine[-1]["line"] if mine else 0,
            "overridden": bool(mine and mine[-1].get("enabled")),
            "disabled": bool(mine and not mine[-1].get("enabled")),
        })
    known = {x["key"] for x in out}
    for key, mine in user.items():
        if key not in known:
            out.append({
                "key": key, "default_cmd": "", "default_comment": "", "section": "自定义",
                "user_cmd": mine[-1]["cmd"], "user_line": mine[-1]["line"],
                "overridden": bool(mine[-1].get("enabled")),
                "disabled": bool(mine and not mine[-1].get("enabled")),
            })
    out.sort(key=lambda x: (x["section"] != "mpv 内置", x["key"]))
    return out


__all__ = ["load_defaults", "load_commands", "db_status", "parse_input_conf",
           "render_rows", "resolve_input_files", "load_keymap", "save_keymap",
           "conflicts", "effective_keymap",
           # R-24
           "is_bundled_input", "needs_promote", "promote_to_user_file",
           "USER_INPUT_NAME", "BUNDLED_INPUT_NAMES"]

# -*- coding: utf-8 -*-
r"""生成按键绑定数据库（data/mpv_keybindings.json + data/mpv_commands.json）。

数据不是抄来的，是**从你自己这份 mpv 里问出来的**：

    mpv --no-config --idle --vo=null --ao=null --script=_dump_bindings.lua

lua 脚本读 `input-bindings` 属性（209 条内置绑定，带命令、注释、优先级、来源 section），
命令表则来自 `mpv --input-cmdlist`（86 条，带参数签名与说明）。

用法：
    py -3 tools\build_keybindings.py ["C:\Program Files\mpv-lazy\mpv.com"]

mpv 升级、或者换了别的 mpv 构建之后重跑一次即可。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LUA = Path(__file__).resolve().parent / "_dump_bindings.lua"

DEFAULT_MPV = r"C:\Program Files\mpv-lazy\mpv.com"
CANDIDATES = [
    DEFAULT_MPV,
    r"C:\Program Files\mpv-lazy\mpv.exe",
    r"C:\Program Files\mpv\mpv.com",
    r"C:\Program Files\mpv\mpv.exe",
]


def find_mpv(explicit=None):
    for p in ([explicit] if explicit else []) + CANDIDATES:
        if p and Path(p).is_file():
            return p
    return None


def mpv_version(mpv):
    try:
        out = subprocess.run([mpv, "--version"], capture_output=True, text=True,
                             timeout=20, encoding="utf-8", errors="replace")
        return (out.stdout or "").splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def dump_bindings(mpv, timeout=40):
    """跑一次 mpv，把 input-bindings 导出成 JSON。"""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "bindings.json"
        env = dict(os.environ, MPV_KEYS_OUT=str(out))
        cmd = [mpv, "--no-config", "--idle", "--vo=null", "--ao=null",
               "--msg-level=all=no", f"--script={LUA}"]
        try:
            subprocess.run(cmd, env=env, timeout=timeout,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            print("mpv 没有在超时前退出（脚本没跑起来？）")
        except OSError as e:
            print(f"起不了 mpv：{e}")
            return {}
        if not out.is_file():
            print("mpv 没写出绑定文件")
            return {}
        return json.loads(out.read_text(encoding="utf-8"))


CMD_LINE = re.compile(r"^(?P<name>[a-z0-9\-]+)\s+(?P<sig>.*?)\s{2,}(?P<desc>.*)$")


def parse_cmdlist(mpv):
    """解析 `mpv --input-cmdlist`：命令名 / 参数签名 / 说明。"""
    try:
        out = subprocess.run([mpv, "--input-cmdlist"], capture_output=True, text=True,
                             timeout=30, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"拿命令表失败：{e}")
        return []
    cmds = []
    for line in (out.stdout or "").splitlines():
        if not line.strip():
            continue
        m = CMD_LINE.match(line.rstrip())
        if m:
            cmds.append({"name": m.group("name"), "sig": m.group("sig").strip(),
                         "desc": m.group("desc").strip()})
        else:
            parts = line.split()
            if parts:
                cmds.append({"name": parts[0], "sig": " ".join(parts[1:]).strip(), "desc": ""})
    # 去掉表头（如果有）
    return [c for c in cmds if c["name"] not in ("name", "命令")]


SECTION_LABEL = {
    "default": "mpv 内置",
    "osc": "内置脚本 osc",
    "window-controls": "内置脚本 window-controls",
    "input": "输入区",
    "encode": "编码模式",
    "showhide": "显示/隐藏",
    "showhide_wc": "显示/隐藏",
}


def main():
    mpv = find_mpv(sys.argv[1] if len(sys.argv) > 1 else None)
    if not mpv:
        print("找不到 mpv（可以传一个路径：py -3 tools\\build_keybindings.py <mpv 路径>）")
        return 1
    print("用的 mpv：", mpv)
    version = mpv_version(mpv)
    print("版本：", version)

    raw = dump_bindings(mpv)
    bindings = []
    for b in raw.get("bindings") or []:
        key = (b.get("key") or "").strip()
        if not key:
            continue
        section = b.get("section") or "default"
        bindings.append({
            "key": key,
            "cmd": (b.get("cmd") or "").strip(),
            "comment": (b.get("comment") or "").strip(),
            "section": section,
            "label": SECTION_LABEL.get(section, section),
            "priority": b.get("priority", 0),
            "weak": bool(b.get("is_weak")),
            "owned": bool(b.get("owner")),
        })
    bindings.sort(key=lambda x: (x["section"] != "default", x["label"], x["key"]))

    cmds = parse_cmdlist(mpv)
    DATA.mkdir(exist_ok=True)
    (DATA / "mpv_keybindings.json").write_text(json.dumps({
        "meta": {
            "source": "mpv --no-config --idle --script=_dump_bindings.lua（读 input-bindings 属性）",
            "mpv": version,
            "count": len(bindings),
            "sections": sorted({b["section"] for b in bindings}),
        },
        "bindings": bindings,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "mpv_commands.json").write_text(json.dumps({
        "meta": {"source": "mpv --input-cmdlist", "mpv": version, "count": len(cmds)},
        "commands": cmds,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"内置绑定 {len(bindings)} 条 / 命令 {len(cmds)} 条")
    print(f"已写入 {DATA / 'mpv_keybindings.json'}")
    print(f"已写入 {DATA / 'mpv_commands.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

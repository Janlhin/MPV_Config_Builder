# -*- coding: utf-8 -*-
r"""MPV Config Builder · Web 界面后端（只用标准库）

启动：
    py -3 webui\server.py

做的事：
    1. 在本机 127.0.0.1 起一个静态服务 + JSON API
    2. 用 Edge/Chrome 的 --app 模式打开一个没有浏览器边框的窗口
    3. 所有真实逻辑都调用 core/ 里的模块，前端只负责展示

不需要安装 pywebview / Rust / Node；将来想换壳，前端不用改。
"""
import json
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent      # 项目根目录（源码运行时的兜底）
sys.path.insert(0, str(ROOT))

from core.paths import bundle_root, is_frozen      # noqa: E402

# 打包后代码与数据在解包目录里，不能用 __file__ 推（见 core/paths.py）
BASE = bundle_root()
STATIC = BASE / "webui" / "static" if is_frozen() else Path(__file__).resolve().parent / "static"

from core.schema import (          # noqa: E402
    APP_TITLE, VERSION, PARAMS, native_items, build_shader_catalog, build_memc_catalog,
    find_lazy_pc, scan_lazy, NATIVE_OPTIONS, LAZY_CANDIDATE_DIRS, db_ui_item,
    PARAMS_EN, CORE_GROUP_EN, NATIVE_EN, NATIVE_GROUP_EN, LAZY_BUNDLED_SHADERS,
)
from core.i18n import T            # noqa: E402
from core.combos import COMBOS_EN  # noqa: E402
from core.schema import load_settings, save_settings  # noqa: E402
from core.presets import (         # noqa: E402
    CONTENT_CHOICES, PREFER_CHOICES, get_basic_preset, resolve_shader_slots,
    WRITE_MODE_INCLUDE, WRITE_MODE_MERGE,
)
from core.writer import (          # noqa: E402
    INCLUDE_FILENAME, build_include_text, write_include, ensure_include_line,
    merge_into_file, apply_params_to_lines, apply_state_to_lines, read_text,
    write_lines, backup_file,
)
from core.loader import load_config_file, parse_config_text, effective_config  # noqa: E402
from core import textio                                     # noqa: E402

# ⚠ `webui/api.py` 必须两种运行方式都能导入：
#   · **直接跑脚本**（`py webui\server.py`）—— 启动器与 Tauri 外壳都这么用；
#     此时没有包上下文，`from . import api` 会报
#     "attempted relative import with no known parent package"；
#   · **被当包导入**（`from webui import server`）—— 测试与 verify.py docs 这么用。
# 实测踩过：第一版只写了相对导入，服务器**直接起不来**，而单元测试全绿
# （因为它们走的是包导入那条路，压根没覆盖脚本模式）。
try:
    from . import api                                       # noqa: E402
except ImportError:                                         # pragma: no cover
    import api                                              # noqa: E402

# 把两个原 lambda 提成的具名函数挂到本模块上（解开循环导入，见 webui/api.py）。
# ⚠ 必须在 import api 之后 —— 这段代码用到 api。
api.install_route_helpers(sys.modules[__name__])
from core.builder import build_config_text, describe_state, validate_state, full_check  # noqa: E402
from core.conflicts import detect_conflicts, conflict_keys       # noqa: E402
from core.report import build_report                         # noqa: E402
from core.vpy import (                                       # noqa: E402
    fuse_files, write_fused, script_role, unfusable_reason, PREFIX, ROLES,
)
from core.keys import (                                      # noqa: E402
    load_keymap, save_keymap, effective_keymap, promote_to_user_file,
)
from core.combos import COMBOS, resolve_combo              # noqa: E402
from core.hardware import detect_all                       # noqa: E402
from core.score import score_active, overall_score, grade_of   # noqa: E402
from core import dlcenter                                    # noqa: E402
from core import search as global_search                     # noqa: E402
from core import uosc                                        # noqa: E402


# ------------------------------------------------- 日志层（M5-E-1）
#
# stdio 模式下 **stdout 是协议流**，多打一行字就会让外壳那边的
# JSON.parse 炸掉、后续响应全部错位。所以所有给人看的话都要走 stderr。
#
# stdio.serve() 一进来就把 QUIET_STDOUT 打开、并把 LOG_STREAM 指到 stderr；
# HTTP 模式（默认）行为不变，仍然打到 stdout。
#
# ⚠ 别在别处直接 print() 了 —— 用 log()。防线是 tests/test_stdio.py 里
# 「stdout 每一行都必须能 json.loads」那条测试。

QUIET_STDOUT = False
LOG_STREAM = None          # None = 用 sys.stdout（HTTP 模式）


def log(msg=""):
    """给人看的输出。stdio 模式下走 stderr，HTTP 模式下走 stdout。"""
    stream = LOG_STREAM
    if stream is None:
        stream = sys.stderr if QUIET_STDOUT else sys.stdout
    try:
        stream.write(str(msg) + "\n")
    except UnicodeEncodeError:
        # 控制台不是 UTF-8 时会把整个后端打崩：日志里有 '→'，而英文版 Windows 的
        # 控制台是 cp1252，编码不了它 —— 2026-10-09 CI 首次运行就是这么红的
        # （本机常年 UTF-8，所以这个缺陷在本机永远复现不出来）。
        # 宁可显示成问号，也不能让服务器起不来。
        enc = getattr(stream, "encoding", None) or "utf-8"
        stream.write(str(msg).encode(enc, "replace").decode(enc, "replace") + "\n")
    try:
        stream.flush()
    except Exception:                                        # pragma: no cover
        pass


# ------------------------------------------------- 下载中心的后台任务表
#
# 下载是长任务（几十 MB / 要重试镜像），不能卡在请求里。
# 发起 → 返回任务 id；前端按 id 轮询进度 → 完成后拿结果。
# 任务只在内存里，进程重启就没了（本来也是一次性动作）。

_JOBS = {}
_JOBS_LOCK = threading.Lock()
_JOB_SEQ = [0]


def _new_job(kind, title):
    with _JOBS_LOCK:
        _JOB_SEQ[0] += 1
        jid = f"j{_JOB_SEQ[0]}"
        _JOBS[jid] = {"id": jid, "kind": kind, "title": title,
                      "state": "running", "done": 0, "total": 0,
                      "percent": 0, "detail": "准备中…", "started": time.time(),
                      "result": None}
        return jid


def _set_job(jid, **kw):
    with _JOBS_LOCK:
        job = _JOBS.get(jid)
        if job:
            job.update(kw)


def _job(jid):
    with _JOBS_LOCK:
        job = _JOBS.get(jid)
        return dict(job) if job else None


def _prune_jobs(keep=40):
    """只留最近的若干条，别让内存无限涨。"""
    with _JOBS_LOCK:
        if len(_JOBS) <= keep:
            return
        for jid in sorted(_JOBS, key=lambda k: _JOBS[k]["started"])[:len(_JOBS) - keep]:
            _JOBS.pop(jid, None)


# ---------------------------------------------------------------- 业务函数

def api_status():
    lazy = find_lazy_pc()
    from core.schema import candidate_dirs
    return {
        "title": APP_TITLE,
        "version": VERSION,
        "lazy_pc": str(lazy) if lazy else "",
        "target": str(lazy) if lazy else "",
        "counts": {
            "core": sum(len(v) for v in PARAMS.values()),
            "native": len(native_items()),
            "shaders": len(build_shader_catalog(lazy)),
            "memc": len(build_memc_catalog(lazy)),
        },
        "hardware": detect_all(),
        "candidates": LAZY_CANDIDATE_DIRS,
        # 带来源与存在性的候选列表，界面可以直接列给用户挑
        "candidate_details": candidate_dirs()[:12],
    }


def api_presets():
    out = []
    for content in CONTENT_CHOICES:
        for prefer in PREFER_CHOICES:
            p = get_basic_preset(content, prefer)
            out.append({"content": content, "prefer": prefer,
                        "note": p["note"], "params": p["params"]})
    return out


def _basic_build(body):
    """按基础模式的选择算出参数与 shader 路径。"""
    target = _resolve_target(body)
    content = body.get("content") or CONTENT_CHOICES[0]
    prefer = body.get("prefer") or PREFER_CHOICES[1]
    preset = get_basic_preset(content, prefer)

    catalog = build_shader_catalog(target if (target and target.is_dir()) else find_lazy_pc())
    names = [x["name"] for x in catalog]
    picked, missing = resolve_shader_slots(preset["shaders"], names)

    paths = []
    for name in picked:
        for item in catalog:
            if item["name"] == name and item.get("path"):
                paths.append(item["path"])
                break
    params = dict(preset["params"])
    if paths:
        params["glsl-shaders"] = '"' + ";".join(paths) + '"'
    return target, preset, params, picked, missing, paths


def api_basic_preview(body):
    target, preset, params, picked, missing, paths = _basic_build(body)
    if not target:
        return {"ok": False, "detail": _LAST_TARGET_ERROR or "先选择 mpv 配置目录"}
    mode = body.get("write_mode") or WRITE_MODE_INCLUDE
    if mode == WRITE_MODE_MERGE:
        main = target / "mpv.conf"
        lines = read_text(main).splitlines()
        _new, changes = apply_params_to_lines(lines, params)
        return {"mode": mode, "text": "\n".join(changes) if changes else "（没有改动）",
                "changes": len(changes), "picked": picked, "missing": missing,
                "note": preset["note"], "params": params, "shader_paths": paths}
    text = build_include_text(params, preset["note"])
    return {"mode": mode, "text": text, "changes": len(params),
            "picked": picked, "missing": missing, "note": preset["note"],
            "params": params, "shader_paths": paths,
            "file": str(target / INCLUDE_FILENAME)}


def api_basic_apply(body):
    target, preset, params, picked, missing, _paths = _basic_build(body)
    if not target or not Path(target).is_dir():
        return {"ok": False,
                "detail": _LAST_TARGET_ERROR or "还没选择 mpv 配置目录，已取消写入"}
    mode = body.get("write_mode") or WRITE_MODE_INCLUDE
    try:
        if mode == WRITE_MODE_MERGE:
            changes, backup = merge_into_file(target / "mpv.conf", params)
            detail = f"已合并 {len(changes)} 处改动到 mpv.conf"
            if backup:
                detail += f"（已备份 {backup.name}）"
        else:
            path, backup = write_include(target, build_include_text(params, preset["note"]))
            changed, main_backup, msg = ensure_include_line(target / "mpv.conf")
            detail = f"已写入 {path.name}"
            detail += "，并在 mpv.conf 追加了 include 行" if changed else f"，{msg}"
            if backup or main_backup:
                detail += "（原文件已备份）"
    except OSError as e:
        return {"ok": False, "detail": f"写入失败：{e}"}
    if missing:
        detail += f"；本机缺少 shader：{'、'.join(missing)}（已跳过）"
    return {"ok": True, "detail": detail, "picked": picked, "missing": missing}


def api_scan(body):
    raw = str(body.get("dir", "") or "").strip()
    if not raw:
        # Path("") 在 Windows 上等于 "."，is_dir() 恒真 —— 以前会去扫进程当前目录
        return {"ok": False, "detail": "还没选择要扫描的目录"}
    root = Path(raw)
    if not root.is_dir():
        return {"ok": False, "detail": "目录不存在"}
    pc = root if root.name.lower() == "portable_config" else (
        root / "portable_config" if (root / "portable_config").is_dir() else root)
    shaders, vpy = scan_lazy(pc)
    return {"ok": True, "pc": str(pc),
            "shaders": [str(p.relative_to(pc).as_posix()) for p in shaders],
            "vpy": [str(p.relative_to(pc).as_posix()) for p in vpy]}


def api_options():
    """给进阶 / 完全体页面用的选项元数据。

    除了 key/label/desc，还给三个**值域**字段（别把它们混起来）：
        values   精选层写的建议值 —— 只是举例，不是全集
        options  这个选项真正允许的取值（库里查得到的话）+ 建议值，去重后
        open     True = 可以自由填值，不限于上面那些
    以前界面只看 values：非空就渲染成只能选的下拉框，于是 `scale` 只能从 10 个
    建议值里挑（mpv 实际有 39 个），`geometry` 这种自由格式也被锁死。
    """
    from core.schema import value_info, db_option_type, _db_entry

    def ui_type(key, curated):
        """界面用哪个类型：**库里的真类型优先**，查不到才按建议值猜。

        以前这里一律按"建议值是 yes/no 就当 bool、否则当 enum"猜，
        把 `geometry`（库类型 Window geometry）、`sub-font`（String）、
        `vo`（Object settings list）这些**本来就能自由填**的项
        全标成 enum，于是界面把它们渲染成只能选的下拉框。
        """
        entry = _db_entry(key)
        if entry:
            return db_option_type(entry)
        return "bool" if (len(curated) == 2 and set(curated) == {"yes", "no"}) else "enum"

    core = []
    for cat, items in PARAMS.items():
        en_pair = None
        for key, label, desc, values, q, load in items:
            tp = ui_type(key, values)
            info = value_info(key, tp, values)
            en_pair = PARAMS_EN.get(key)
            core.append({"group": T(cat, CORE_GROUP_EN.get(cat, cat)),
                         "key": key,
                         "label": T(label, en_pair[0]) if en_pair else label,
                         "desc": T(desc, en_pair[1]) if en_pair else desc,
                         "values": values, "kind": "core", "type": tp,
                         "suggest": info["suggest"], "options": info["options"],
                         "open": info["open"]})
    native = []
    for group, key, label, desc, values, typ in native_items():
        tp = ui_type(key, values) or typ
        info = value_info(key, tp, values)
        en_pair = NATIVE_EN.get(key)
        native.append({"group": T(group, NATIVE_GROUP_EN.get(group, group)),
                       "key": key,
                       "label": T(label, en_pair[0]) if en_pair else label,
                       "desc": T(desc, en_pair[1]) if en_pair else desc,
                       "values": values, "type": tp, "kind": "native",
                       "suggest": info["suggest"], "options": info["options"],
                       "open": info["open"]})
    return {"core": core, "native": native,
            "groups": [T(g, NATIVE_GROUP_EN.get(g, g)) for g in NATIVE_OPTIONS.keys()],
            "db": db_status()}


def db_status():
    """全量选项库的状态（读不到就说读不到，别装作有）。"""
    try:
        from core.options_db import load_db
        db = load_db()
        meta = (db.get("meta") or {})
        return {"available": bool(meta.get("count")),
                "count": meta.get("count", 0),
                "with_zh": meta.get("with_zh", 0),
                # 分组也放这儿：界面读 APP.options.db.groups，以前这里是空的
                "groups": db.get("groups") or [],
                "license": meta.get("license_note", "")}
    except Exception as e:
        return {"available": False, "count": 0, "with_zh": 0, "groups": [], "detail": str(e)}


def api_compat():
    """版本级兼容检测（待做 §〇 第 13 项 ①③）。

    探测用户实际运行的 mpv：版本 + 它支持的参数集合（`mpv --list-options`），
    与参数库比对 —— 库里有、用户 mpv 没有的，就是它**不支持**的参数。

    失败（没装 mpv / 超时 / 非零退出）一律降级：`scanned=False`、
    `unsupported=[]`，界面**不报警**（版本未知不应该误伤用户）。

    设计来源：原方案想从官方 rst 的 ``versionadded`` 抽「引入版本」，但
    官方 rst 没有版本注记（实测 0 处），故改用「运行时选项存在性比对」——
    这能直接回答「你的 mpv 跑不跑得动这个选项」，比静态版本号更准。
    见 `DECISIONS.md` 2026-11-09 的条目。
    """
    from core.mpv_version import (
        detect_mpv_version, capture_mpv_options, diff_unsupported)
    from core.options_db import load_db

    db = load_db()
    db_keys = set((db.get("options") or {}).keys())
    version = detect_mpv_version()
    user_options = capture_mpv_options()
    unsupported = sorted(diff_unsupported(db_keys, user_options))
    return {
        "version": version,
        "unsupported": unsupported,
        # 仅当真的探测到了 mpv（版本或参数任一拿到）才算"扫过"
        "scanned": (version is not None) or (user_options is not None),
    }


def api_db_options(params):
    """全量选项库（829 项）：分页 + 分组过滤 + 搜索，给完全体页面用。"""
    try:
        from core.options_db import load_db, search as db_search
    except Exception as e:
        return {"ok": False, "detail": f"选项库读不了：{e}"}
    db = load_db()
    options = db.get("options") or {}
    if not options:
        return {"ok": False, "detail": "选项库是空的，先跑 tools/build.py options-db 生成"}

    q = (params.get("q") or "").strip()
    group = (params.get("group") or "").strip()
    try:
        limit = max(1, min(int(params.get("limit") or 60), 300))
        offset = max(0, int(params.get("offset") or 0))
    except ValueError:
        limit, offset = 60, 0

    if q:
        items = [x for x in db_search(db, q) if x.get("key") in options] or []
    else:
        order = {g: i for i, g in enumerate(db.get("groups") or [])}
        items = sorted(options.values(),
                       key=lambda x: (order.get(x.get("group"), 99), x.get("key", "")))
    if group and group not in ("全部", "all"):
        items = [x for x in items if x.get("group") == group]

    total = len(items)
    page = items[offset:offset + limit]
    return {
        "ok": True, "total": total, "offset": offset, "limit": limit,
        "groups": db.get("groups") or [],
        "meta": db.get("meta") or {},
        "items": [db_ui_item(x) for x in page],
    }


# ------------------------------------------------- 进阶 / 完全体 / 地狱 模式

_TRUSTED_TARGETS = set()          # 本进程校验并登记过的目标（resolve 后的 str）
_LAST_TARGET_ERROR = ""


def _looks_safe_target(p):
    """一个目录能不能当「可写根」。返回 (ok, why)。

    防的是请求体里塞 target="C:\\" / 仓库根 / 用户目录根，把白名单撑到全盘。
    这不是权限系统，只把明显不该作为 mpv 配置目录的路径挡掉。
    Program Files 下的 mpv-lazy 是**合法**目标，不拦。
    """
    p = Path(p).resolve()
    if not p.is_dir():
        return False, f"目标目录不存在：{p}"
    if p.parent == p:                        # 盘符根 / 文件系统根
        return False, "目标目录不能是盘符根"
    low = [x.rstrip(":\\/").lower() for x in p.parts]
    if len(low) >= 2 and low[0] == "c" and low[1] == "windows":
        return False, "目标目录不能是 Windows 系统目录"
    try:
        root = ROOT.resolve()
        if p == root or root in p.parents or p in root.parents:
            return False, "目标目录不能是仓库目录或它的上级"
    except OSError:
        pass
    try:
        if p == Path.home().resolve():
            return False, "目标目录不能是用户主目录本身"
    except OSError:
        pass
    return True, ""


def _trust_target(raw):
    """校验并登记一个目标目录；成功返回 Path 并记忆，失败返回 None 并记原因。"""
    global _LAST_TARGET_ERROR
    raw = str(raw or "").strip()
    if not raw:
        _LAST_TARGET_ERROR = "还没选择 mpv 配置目录"
        return None
    p = Path(raw)
    if p.name.lower() != "portable_config" and (p / "portable_config").is_dir():
        p = p / "portable_config"
    ok, why = _looks_safe_target(p)
    if not ok:
        _LAST_TARGET_ERROR = why
        return None
    p = p.resolve()
    _TRUSTED_TARGETS.add(str(p))
    _remember_target(p)
    _LAST_TARGET_ERROR = ""
    return p


def _resolve_target(body):
    """目标目录：优先 body.target，其次本机已装的 mpv；顺手记进设置里供下次探测。

    任何进入白名单的目标都必须先过 _trust_target —— 不再把请求体里的字符串
    直接当"可写根"（旧实现正是这样被 CSRF 撑开的）。
    """
    raw = str(body.get("target", "") or "").strip()
    if raw:
        return _trust_target(raw)
    found = find_lazy_pc()
    if found:
        return _trust_target(found)
    _LAST_TARGET_ERROR = "还没选择 mpv 配置目录"
    return None


def _remember_target(target):
    """把用户选过的目录记进 settings.json —— find_lazy_pc 的第一优先级候选。"""
    try:
        from core.schema import load_settings, save_settings
        cur = load_settings() or {}
        path = str(target)
        if cur.get("target") != path:
            cur["target"] = path
            save_settings(cur)
    except Exception:
        pass


def _config_paths(target):
    """目标目录里可能存在配置的位置，给「读取现有配置」下拉用。"""
    if not target or not Path(target).is_dir():
        return []
    base = Path(target)
    found = []
    for rel in ("mpv.conf", INCLUDE_FILENAME, "profiles.conf", "input.conf",
                "script-opts.conf", "mpv.conf.bak",
                "portable_config/mpv.conf", "portable_config/" + INCLUDE_FILENAME):
        p = base / rel
        if p.is_file():
            kind = "profiles" if p.name.lower() == "profiles.conf" else "config"
            found.append({"path": str(p), "name": rel, "kind": kind,
                          "size": p.stat().st_size})
    return found


def api_catalog(params):
    """shader / vpy 实际文件 + 目标目录信息。"""
    target = _resolve_target({"target": params.get("target", "")})
    pc = target if (target and target.is_dir()) else None
    shaders = build_shader_catalog(pc)
    memc = build_memc_catalog(pc)
    return {
        "ok": True,
        "target": str(target) if target else "",
        "is_dir": bool(target and target.is_dir()),
        "shaders": shaders,
        "memc": memc,
        "configs": _config_paths(target),
    }


def api_config_load(body):
    """读取一个已有 mpv.conf，解析成前端状态。

    会跟着 include 一行行走下去，所以能回答「实际生效的是什么」；
    但 [小节]（profile）里的选项单独返回，不会混进全局值里。
    """
    path = str(body.get("path", "") or "").strip()
    if not path:
        target = _resolve_target(body)
        path = str(Path(target) / "mpv.conf") if target else ""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "detail": f"找不到文件：{path}"}
    data = load_config_file(p, deep=body.get("deep", True))
    if not data.get("ok"):
        return data
    chain = data["chain"]
    other = {k: v for k, v in (chain.get("all_values") or {}).items()
             if k not in data["values"]}
    return {
        "ok": True,
        "path": data["path"],
        "name": data["name"],
        "raw": data["raw"],
        "values": data["values"],
        "present": data["present"],
        "other_values": other,
        "unknown_keys": chain.get("unknown") or [],
        "shaders": data["shaders"],
        "memc": data["memc"],
        "memc_label": data["memc_label"],
        "profiles": data["profiles"],
        "is_profile_file": data["is_profile_file"],
        "chain": chain,
        "encoding": data["encoding_label"],
        "lossy": data["lossy"],
        "bom": data["bom"],
        "newline": "CRLF" if data["newline"] == "\r\n" else "LF",
        "warnings": data.get("warnings", []),
        "summary": describe_state(data),
    }


def _preview_config(body):
    """根据状态算出要写入的文本；merge 模式额外给出「合并后的完整文件」。"""
    state = body.get("state") or {}
    target = _resolve_target(body)
    mode = body.get("write_mode") or WRITE_MODE_INCLUDE
    if mode == WRITE_MODE_MERGE and not target:
        return {"ok": False, "detail": _LAST_TARGET_ERROR or "先选择 mpv 配置目录"}
    text = build_config_text(state, note=body.get("note", ""))
    issues, conflicts = full_check(state)
    if mode == WRITE_MODE_MERGE:
        main = Path(str(body.get("source") or (Path(target) / "mpv.conf")))
        tf = textio.read(main)
        raw = tf.text if tf is not None else ""
        newline = tf.newline if tf is not None else "\n"
        new_lines, changes = apply_state_to_lines(
            raw.splitlines(), state.get("values") or {}, state.get("disable") or [])
        merged = newline.join(new_lines) + newline
        # R-14：行级差异（左右并排渲染用）
        from core.diff import diff_lines, unified
        d = diff_lines(raw, merged)
        return {"ok": True, "mode": mode, "target": str(target),
                "source": str(main), "text": text,
                "merged_text": merged,
                "diff": d["rows"], "diff_stats": d["stats"],
                "identical": d["identical"],
                "unified": unified(raw, merged) if not d["identical"] else "",
                "encoding": tf.encoding_label if tf is not None else "（新建文件，UTF-8）",
                "changes": changes, "issues": issues, "conflicts": conflicts,
                "summary": describe_state(state)}
    return {"ok": True, "mode": mode, "target": str(target),
            "file": str(Path(target) / INCLUDE_FILENAME), "text": text,
            "changes": [], "issues": issues, "conflicts": conflicts,
            "summary": describe_state(state)}


def _apply_config(body):
    state = body.get("state") or {}
    target = _resolve_target(body)
    if not target or not Path(target).is_dir():
        return {"ok": False, "detail": f"目标目录不存在：{target}"}
    mode = body.get("write_mode") or WRITE_MODE_INCLUDE
    backs = []
    try:
        if mode == WRITE_MODE_MERGE:
            source = Path(str(body.get("source") or (Path(target) / "mpv.conf")))
            tf = textio.read(source)
            raw = tf.text if tf is not None else ""
            newline = tf.newline if tf is not None else "\n"
            new_lines, changes = apply_state_to_lines(
                raw.splitlines(), state.get("values") or {}, state.get("disable") or [])
            backup = write_lines(source, new_lines, newline, template=tf)
            if backup:
                backs.append(str(backup))
            detail = f"已合并 {len(changes)} 处改动到 {source.name}"
            if backup:
                detail += f"（已备份 {backup.name}）"
            if tf is not None and tf.encoding != "utf-8":
                detail += f"；文件按原编码 {tf.encoding_label} 写回"
        else:
            path, backup = write_include(target, build_config_text(state, note=body.get("note", "")))
            changed, main_backup, msg = ensure_include_line(Path(target) / "mpv.conf")
            detail = f"已写入 {path.name}"
            detail += "，并在 mpv.conf 追加了 include 行" if changed else f"，{msg}"
            if backup or main_backup:
                detail += "（原文件已备份）"
            for b in (backup, main_backup):
                if b:
                    backs.append(str(b))
    except OSError as e:
        return {"ok": False, "detail": f"写入失败：{e}"}
    return {"ok": True, "detail": detail, "mode": mode, "target": str(target),
            "backups": backs}


def api_config_preview(body):
    return _preview_config(body)


def api_config_apply(body):
    return _apply_config(body)


def _inside(path, roots):
    """path 是否落在 roots 里的任意一个目录内（防越界读写）。

    用 Path.resolve() + relative_to 做真正的路径比较 —— 以前静态目录用的是
    字符串 startswith，那是错的做法（/a/static_evil 会通过 /a/static 的前缀检查）。
    """
    try:
        target = Path(path).resolve()
    except (OSError, ValueError):
        return False
    for root in roots:
        if not root:
            continue
        try:
            r = Path(root).resolve()
        except (OSError, ValueError):
            continue
        if target == r:
            return True
        try:
            target.relative_to(r)
            return True
        except ValueError:
            continue
    return False


def _saved_targets():
    """白名单根：安装目录 + 探测到的 mpv + 已保存 / 已登记的目标（全部服务端来源）。"""
    roots = []
    try:
        from core.installer import default_install_dir
        roots.append(Path(default_install_dir()))
    except Exception:
        pass
    t = find_lazy_pc()
    if t:
        roots.append(Path(t))
    try:
        from core.schema import load_settings
        saved = (load_settings() or {}).get("target")
        if saved:
            roots.append(Path(saved))
    except Exception:
        pass
    roots += [Path(x) for x in _TRUSTED_TARGETS]
    return roots


def _allowed_write_roots(extra=None):
    """允许写的目录白名单：**只由服务端状态计算**。

    `extra` 参数保留仅为兼容旧调用，**内容被忽略**：旧实现直接把请求体里的
    target 当白名单根，任意网页 POST target="C:\\" 就能写任意文件（CSRF）。
    """
    return _saved_targets()


def api_raw_read(params):
    """原样读一个文本文件（地狱模式预览 / 手动编辑）。"""
    path = str(params.get("path", "") or "").strip()
    p = Path(path) if path else None
    if not p or not p.is_file():
        return {"ok": False, "detail": f"找不到文件：{path}"}
    if not _inside(p, _allowed_write_roots()):
        return {"ok": False,
                "detail": "只允许读写目标配置目录里的文件（安全限制）。"
                          "要编辑别处的文件，请先把目标目录指到那里。"}
    if p.stat().st_size > 2 * 1024 * 1024:
        return {"ok": False, "detail": "文件超过 2MB，拒绝在界面里编辑"}
    tf = textio.read(p)
    if tf is None:
        return {"ok": False, "detail": f"读不了这个文件：{p}"}
    return {"ok": True, "path": str(p), "text": tf.text, "size": tf.size,
            "encoding": tf.encoding_label, "lossy": tf.lossy,
            "newline": "CRLF" if tf.newline == "\r\n" else "LF"}


def api_raw_save(body):
    """原样保存文本（先备份）。地狱模式专用：不解析、不校验。"""
    path = str(body.get("path", "") or "").strip()
    text = body.get("text")
    if not path or text is None:
        return {"ok": False, "detail": "缺少 path 或 text"}
    p = Path(path)
    if not _inside(p, _allowed_write_roots()):
        return {"ok": False,
                "detail": "只允许写入目标配置目录里的文件（安全限制）。"}
    report = {}
    try:
        tf = textio.read(p) if p.is_file() else None
        newline = tf.newline if tf is not None else "\n"
        lines = str(text).replace("\r\n", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        backup = write_lines(p, lines, newline, template=tf, report=report)
    except OSError as e:
        return {"ok": False, "detail": f"写入失败：{e}"}
    detail = f"已保存 {p.name}"
    if backup:
        detail += f"（已备份 {backup.name}）"
    if tf is not None and tf.encoding != "utf-8":
        if report.get("fallback"):
            detail += (f"；原文编码 {tf.encoding_label} 表示不了新内容，"
                       f"已按 UTF-8 写回")
        else:
            detail += f"；按原编码 {tf.encoding_label} 写回"
    return {"ok": True, "detail": detail, "path": str(p)}


def api_keys(params):
    """按键绑定：当前键位表 + 内置默认 + 命令表。"""
    target = _resolve_target({"target": params.get("target", "")})
    data = load_keymap(target if target and Path(target).is_dir() else None)
    if data.get("main"):
        rows = next((f["rows"] for f in data["files"] if f["path"] == data["main"]), [])
        data["effective"] = effective_keymap(rows, data["defaults"])
    else:
        data["effective"] = effective_keymap([], data["defaults"])
    data["target"] = str(target) if target else ""
    return data


def api_keys_save(body):
    """保存按键绑定（先备份、按原编码写回）。"""
    path = str(body.get("path", "") or "").strip()
    rows = body.get("rows")
    if not path or not isinstance(rows, list):
        return {"ok": False, "detail": "缺少 path 或 rows"}
    bad = [r for r in rows if r.get("kind") == "bind"
           and r.get("enabled") and not str(r.get("cmd", "")).strip()]
    if bad:
        return {"ok": False, "detail": f"有 {len(bad)} 条绑定没写命令，先补上再保存"}
    return save_keymap(path, rows)


def api_keys_promote(body):
    """R-24：把当前键位表另存为「你自己的」，并让 mpv.conf 指向它。

    解决的问题：一直在改的是 mpv-lazy 自带的 `input_uosc.conf`，
    下次升级 mpv-lazy 会被覆盖回去，用户改的键全丢且毫无提示。

    这是个**显式动作**（用户点按钮），不是保存的副作用 —— 因为它会改 mpv.conf。
    """
    target = _resolve_target(body)
    if not target or not Path(target).is_dir():
        return {"ok": False, "detail": f"目标目录不存在：{target}"}
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows:
        return {"ok": False, "detail": "缺少 rows（要保存的键位表内容）"}
    name = str(body.get("name") or "").strip() or None
    return promote_to_user_file(target, rows, **({"name": name} if name else {}))


def api_uosc(params):
    """uosc.conf（`script-opts/` 下）：读出键值 + 分类 + 中文说明。

    只认 `uosc.conf` 这一个文件名、且必须在目标配置目录里 —— 它可不是
    「任意文本编辑器」，别让它变成读写任意文件的通道。
    """
    path = str(params.get("path", "") or "").strip()
    target = _resolve_target({"target": params.get("target", "")})
    if path:
        p = Path(path)
        if p.name.lower() != "uosc.conf":
            return {"ok": False, "detail": "只能读写 uosc.conf"}
        if not _inside(p, _allowed_write_roots()):
            return {"ok": False,
                    "detail": "只允许读写目标配置目录里的文件（安全限制）。"}
        base = p.parent.parent if p.parent.name.lower() == "script-opts" else p.parent
        data = uosc.load(base, path=str(p))
    else:
        if not target:
            return {"ok": False,
                    "detail": _LAST_TARGET_ERROR or "还没选择 mpv 配置目录"}
        data = uosc.load(target)
    data["target"] = str(target) if target else ""
    data["meta"] = uosc.preview_keys()
    return data


def api_uosc_save(body):
    """写 uosc.conf：只改提交上来的键，注释与未知键原样保留。

    `dry_run=true` 只回新文本（界面上先给人看一眼），不落盘、不备份。
    """
    path = str(body.get("path", "") or "").strip()
    values = body.get("values")
    if not path or not isinstance(values, dict):
        return {"ok": False, "detail": "缺少 path 或 values"}
    p = Path(path)
    if p.name.lower() != "uosc.conf":
        return {"ok": False, "detail": "只能写 uosc.conf"}
    if not _inside(p, _allowed_write_roots()):
        return {"ok": False,
                "detail": "只允许写入目标配置目录里的文件（安全限制）。"}
    if not p.is_file():
        if body.get("create"):
            return uosc.create(p, newline=("\r\n" if os.name == "nt" else "\n"))
        return {"ok": False, "detail": f"找不到文件：{p}"}
    return uosc.save(p, values, dry_run=bool(body.get("dry_run")))


def api_search(params):
    """统一搜索：配置项 / uosc / 键位 / 脚本，一次搜完。

    只读：不写任何文件。target 给了才搜键位和脚本，没给就只搜静态两项。
    """
    q = str(params.get("q", "") or params.get("keyword", "") or "").strip()
    target = _resolve_target({"target": params.get("target", "")})
    if not q:
        return {"ok": False, "detail": "输入几个字再搜（键名、中文说明、键位都行）"}
    return global_search.search(target, q)


TAG_GROUPS = ("common", "quality", "performance", "subtitle")


def api_tags(params):
    """读「我的分组」：参数键 → 分组 id。存设置文件，跨会话保留。"""
    s = load_settings() or {}
    tags = s.get("tags") if isinstance(s.get("tags"), dict) else {}
    return {"ok": True, "tags": tags,
            "groups": [{"id": g} for g in TAG_GROUPS], "count": len(tags)}


def api_tags_set(body):
    """写「我的分组」：只收 4 个合法分组 + 键名不超过 64 字，脏数据一律丢掉。"""
    tags = body.get("tags")
    if not isinstance(tags, dict):
        return {"ok": False, "detail": "缺少 tags（键 → 分组）"}
    clean = {}
    for k, v in list(tags.items())[:400]:
        if isinstance(k, str) and isinstance(v, str) and k and len(k) <= 64 \
                and v in TAG_GROUPS:
            clean[k] = v
    s = load_settings() or {}
    s["tags"] = clean
    save_settings(s)
    return {"ok": True, "tags": clean, "count": len(clean),
            "detail": f"已记住 {len(clean)} 个参数的分组"}


def api_report(body):
    """配置体检报告：完整版分析（上传文本或指定文件都行）。"""
    path = str(body.get("path", "") or "").strip()
    text = body.get("text")
    if path and not Path(path).is_file():
        return {"ok": False, "detail": f"找不到文件：{path}"}
    if not path and not text:
        return {"ok": False, "detail": "既没有 path 也没有 text"}
    return build_report(path=path or None, text=text, name=body.get("name") or None)


def api_vpy_fuse(body):
    """VPY 融合：把选中的几个 vs 脚本合成一个 .vpy（默认只预览，不写盘）。"""
    target = _resolve_target(body)
    if not target:
        return {"ok": False, "detail": _LAST_TARGET_ERROR or "先选择 mpv 配置目录"}
    names = body.get("scripts") or []
    if not names:
        return {"ok": False, "detail": "没有选择脚本"}
    vs_dir = Path(target) / "vs"
    paths = []
    for name in names:
        p = Path(name)
        if not p.is_absolute():
            p = vs_dir / name
        if not p.is_file():
            return {"ok": False, "detail": f"找不到脚本：{p}"}
        paths.append(p)
    result = fuse_files(paths, name=body.get("name") or None, note=body.get("note") or "")
    if not result.get("ok"):
        return {"ok": False, "detail": result.get("detail") or result.get("check", {}).get("detail"),
                "warnings": result.get("warnings", [])}
    out = {
        "ok": True,
        "text": result["text"],
        "filename": result["filename"],
        "stages": result["stages"],
        "warnings": result["warnings"],
        "check": result["check"],
        "target": str(vs_dir),
    }
    if body.get("write"):
        wr = write_fused(vs_dir, result, overwrite=bool(body.get("overwrite")))
        out.update(wr)
        out["detail"] = wr.get("detail", "")
    return out


def api_vpy_list(params):
    """列出目标目录 vs/ 下的脚本，带上角色，给融合页多选用。"""
    target = _resolve_target({"target": params.get("target", "")})
    if not target:
        return {"ok": False, "detail": _LAST_TARGET_ERROR or "先选择 mpv 配置目录"}
    vs_dir = Path(target) / "vs"
    if not vs_dir.is_dir():
        return {"ok": False, "detail": f"没有 vs 目录：{vs_dir}"}
    out = []
    for p in sorted(vs_dir.glob("*.vpy")):
        rid, label, order = script_role(p)
        out.append({
            "name": p.name, "path": str(p), "size": p.stat().st_size,
            "role": rid, "role_label": label, "order": order,
            "reason": unfusable_reason(p),
            "fusable": rid != "unfusable",
            "generated": p.name.startswith(PREFIX),
        })
    return {"ok": True, "dir": str(vs_dir),
            "scripts": out,
            "roles": [{"id": r[0], "label": r[1], "order": r[2]} for r in ROLES]}


# ---------------------------------------------------------------- 下载中心

def api_downloads(params):
    """下载中心：清单 + 本机安装状态。"""
    target = _resolve_target({"target": params.get("target", "")})
    if not target or not Path(target).is_dir():
        return {"ok": False, "detail": f"目标目录不存在：{target}",
                "kinds": [{"id": k, "label": T(l, dlcenter.KINDS_EN.get(l, l)), "dir": d} for k, l, d in dlcenter.KINDS],
                "items": []}
    items = dlcenter.list_items(target, params.get("kind", ""))
    return {
        "ok": True,
        "target": str(target),
        "kinds": [{"id": k, "label": T(l, dlcenter.KINDS_EN.get(l, l)), "dir": d} for k, l, d in dlcenter.KINDS],
        "items": items,
        "manifest": str(dlcenter.manifest_path()),
        "counts": {
            "total": len(items),
            "installed": sum(1 for x in items if x["state"] in ("installed", "modified")),
        },
    }


def api_install_plan(body=None):
    """一键装 mpv-lazy 的第一步：**只算不动**。

    返回要装的是哪个 release / 哪个包 / 装到哪 / 盘够不够 / 是不是已经装过了。
    ⚠ 这一步**不下载、不写盘** —— 和补注释、清理写入块一个规矩：
    对用户磁盘动手必须是他显式点的动作，而且要先能预览。
    """
    from core.installer import plan_install, default_install_dir
    body = body or {}
    target = str(body.get("target", "") or "").strip() or str(default_install_dir())
    mirror = body.get("mirror") or "自动（直连 → 镜像）"
    try:
        return dict(plan_install(target, mirror), ok=True,
                    default_dir=str(default_install_dir()))
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": f"读不到最新版本：{type(e).__name__}: {e}",
                "target": target, "default_dir": str(default_install_dir())}


def api_install_start(body):
    """发起一键安装（后台线程），立刻返回任务 id；进度用 /api/download/job 轮询。"""
    from core.installer import default_install_dir, run_install
    target = str(body.get("target", "") or "").strip() or str(default_install_dir())
    mirror = body.get("mirror") or "自动（直连 → 镜像）"

    jid = _new_job("lazy-install", "mpv-lazy 一键安装")

    def work():
        try:
            def cb(stage, percent, detail):
                _set_job(jid, percent=percent, stage=stage,
                         detail=f"[{stage}] {detail}" if detail else stage)

            res = run_install(target, mirror_mode=mirror, progress=cb)
            _set_job(jid, state="ok" if res.get("ok") else "fail",
                     percent=100 if res.get("ok") else 0,
                     detail=res.get("detail", ""), result=res)
        except Exception as e:                   # 后台线程不能把异常丢掉
            _set_job(jid, state="fail", detail=f"{type(e).__name__}: {e}")
        finally:
            _prune_jobs()

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "job": jid, "target": target}


def api_download_start(body):
    """发起一个下载任务（后台线程），立刻返回任务 id。"""
    target = _resolve_target(body)
    item_id = str(body.get("id", "") or "").strip()
    item = dlcenter.by_id(item_id)
    if item is None:
        return {"ok": False, "detail": f"清单里没有这个条目：{item_id}"}
    if not target or not Path(target).is_dir():
        return {"ok": False, "detail": f"目标目录不存在：{target}"}

    jid = _new_job("download", item["name"])
    mirror = body.get("mirror") or "自动（直连 → 镜像）"
    overwrite = bool(body.get("overwrite"))

    def work():
        try:
            def cb(done, total):
                pct = int(done * 100 / total) if total else 0
                _set_job(jid, done=done, total=total, percent=pct,
                         detail=f"{done // 1024} KB"
                                + (f" / {total // 1024} KB" if total else ""))

            res = dlcenter.install(target, item_id, mirror_mode=mirror,
                                   overwrite=overwrite, progress_cb=cb)
            _set_job(jid, state="ok" if res.get("ok") else "fail",
                     percent=100 if res.get("ok") else 0,
                     detail=res.get("detail", ""), result=res)
        except Exception as e:                       # 后台线程不能把异常丢掉
            _set_job(jid, state="fail", detail=f"{type(e).__name__}: {e}")
        finally:
            _prune_jobs()

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "job": jid, "name": item["name"]}


def api_download_job(params):
    """轮询任务进度。"""
    job = _job(str(params.get("id", "") or ""))
    if job is None:
        return {"ok": False, "detail": "没有这个任务（服务可能重启过）"}
    return {"ok": True, "job": job}


def api_download_remove(body):
    """卸载：只删清单里记着、且内容没被改过的文件。"""
    target = _resolve_target(body)
    if not target or not Path(target).is_dir():
        return {"ok": False, "detail": f"目标目录不存在：{target}"}
    return dlcenter.uninstall(target, str(body.get("id", "") or ""),
                              force=bool(body.get("force")))


def api_manifest_open(body):
    """打开安装清单所在位置（排错用）。"""
    p = dlcenter.manifest_path()
    return {"ok": True, "path": str(p), "exists": p.is_file()}


def api_download_check(body):
    """发布前固定动作：把下载清单里的 URL 逐条验一遍。"""
    return {"ok": True, "results": dlcenter.check_links()}


def api_config_tidy(body):
    """收拾配置里重复的「由 MPV Config Builder 写入」抬头块（W-1 的收尾动作）。

    背景：写入逻辑修好之前，每写一次就在末尾追加一整套抬头 —— 真机上
    `mpv.conf` 已经被写两次，于是攒出两个一模一样的块。修好写入只保证
    "以后不再多"，**已经多出来的得有人收拾**，否则用户要手工删。

    默认 `write=False` 只回报会怎么改、**不碰磁盘**（和 R-28 补注释一个规矩：
    对用户文件动手必须是显式动作，不能是某个流程的副作用）。
    """
    path = str(body.get("path", "") or "").strip()
    if not path:
        return {"ok": False, "detail": "没有给 path"}
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "detail": f"找不到文件：{path}"}
    try:
        from core.writer import tidy_conf_file
        r = tidy_conf_file(p, dry_run=not body.get("write"))
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": f"处理失败：{e}"}
    out = {"ok": bool(r.get("ok")), "path": str(p),
           "changed": bool(r.get("changed")), "dropped": r.get("dropped", 0),
           "blocks_before": r.get("blocks_before", 0),
           "detail": r.get("reason", ""), "text": r.get("text", ""),
           "wrote": bool(body.get("write"))}
    if r.get("backup"):
        out["backup"] = r["backup"]
    return out


def api_user_presets(query=None):
    """列出用户自己的预设（存盘的那种，不是内置的 6 套）。

    ⚠ 路径是 `/api/userpresets` 而不是 `/api/presets` —— 后者早就被
    **内置的** 6 套预设占了（基础模式那几个按钮在用，返回一个列表）。
    两条不是一回事：内置的是代码里写死的，用户的是磁盘上自己存的。
    """
    from core.presetfile import list_presets
    try:
        return list_presets()
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": f"读预设目录失败：{e}", "presets": []}


def api_presets_save(body):
    """把当前状态存成一个用户预设。"""
    from core.presetfile import save_preset
    state = body.get("state") or {}
    if not isinstance(state, dict):
        return {"ok": False, "detail": "state 不是对象"}
    name = str(body.get("name", "") or "").strip()
    if not name:
        return {"ok": False, "detail": "给这套预设起个名字吧"}
    try:
        ok, detail, preset = save_preset(
            state, name, note=str(body.get("note", "") or ""),
            app_version=VERSION, overwrite=bool(body.get("overwrite")))
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": f"保存失败：{e}"}
    return {"ok": ok, "detail": detail,
            "preset": preset if ok else None}


def api_presets_delete(body):
    """删掉一个用户预设。"""
    from core.presetfile import delete_preset
    pid = str(body.get("id", "") or "").strip()
    if not pid:
        return {"ok": False, "detail": "没有给 id"}
    ok, detail = delete_preset(pid)
    return {"ok": ok, "detail": detail}


def api_presets_load(body):
    """导入预设：给 `path` 或给 `text` 都行（只读，不写进注册表）。

    · 给 `path`：服务器上的文件（体检页那种"我本机有个文件"的用法）
    · 给 `text`：**浏览器读出来的内容** —— 从网页选文件时只能拿到内容，
      拿不到（也不该信）客户端的路径。校验规则只有 `core/presetfile.py` 一份，
      所以前端读出来交给这里判，别在前端再抄一遍。

    分成"导入"（读进来、套到当前状态）和"存下来"（`/api/presets/save`）两步 ——
    别人发来的一套你可能只想用一次，不想污染自己的预设列表。
    """
    from core.presetfile import load_preset_file, validate_preset
    import json as _json

    text = body.get("text")
    if text is not None and str(text).strip():
        raw = str(text)
        if len(raw.encode("utf-8")) > 2 * 1024 * 1024:
            return {"ok": False, "detail": "内容太大（上限 2 MB）"}
        try:
            data = _json.loads(raw)
        except ValueError as e:
            return {"ok": False, "detail": f"不是合法的 JSON：{e}"}
        ok, detail, preset = validate_preset(data)
        return {"ok": ok, "detail": detail, "preset": preset if ok else None}

    path = str(body.get("path", "") or "").strip()
    if not path:
        return {"ok": False, "detail": "没有给 path，也没有给 text"}
    ok, detail, preset = load_preset_file(path)
    return {"ok": ok, "detail": detail, "preset": preset if ok else None}


def api_presets_export(body):
    """把当前状态或注册表里的某个预设写成文件，返回可下载的内容。

    不直接落盘到任意路径（那是用户自己的事）—— 回一个文本让浏览器下载，
    和「另存为」一个道理，省掉一个"让用户填路径"的环节。
    """
    import json as _json
    from core.presetfile import (build_preset, load_preset_file,
                                 safe_name, registry_dir, KIND, VERSION)
    pid = str(body.get("id", "") or "").strip()
    if pid:
        src = registry_dir() / f"{safe_name(pid)}.json"
        ok, detail, preset = load_preset_file(src)
        if not ok:
            return {"ok": False, "detail": detail}
    else:
        state = body.get("state") or {}
        if not isinstance(state, dict):
            return {"ok": False, "detail": "state 不是对象"}
        preset = build_preset(state, name=str(body.get("name", "") or ""),
                              note=str(body.get("note", "") or ""),
                              app_version=VERSION)
    if not preset["state"]["values"] and not preset["state"]["shaders"] \
            and not preset["state"]["memc"]:
        return {"ok": False, "detail": "一个选项都没勾，导出来是空的"}
    text = _json.dumps(preset, ensure_ascii=False, indent=1)
    fname = safe_name(preset.get("name") or pid or "mpv-preset") + ".json"
    return {"ok": True, "detail": f"导出 {len(preset['state']['values'])} 个选项",
            "filename": fname, "text": text, "kind": KIND, "version": VERSION}


def api_annotate(body):
    """给配置补中文注释（R-28）。

    ⚠ **这个接口只由用户点「✍️ 补注释」时调用。**
    上传 / 体检流程（`/api/report`）不许调它 —— 那不是"用户主动选择"。

    默认 `write=False`：只出预览，磁盘上什么都不产生。
    要落盘必须显式 `write=True`，而且优先另存副本（`out_name`）。
    """
    from core.annotate import annotate_text, out_name_for

    path = str(body.get("path", "") or "").strip()
    text = body.get("text")
    style = "above" if body.get("style") == "above" else "inline"
    only_missing = body.get("only_missing", True)

    tf = None
    if path:
        p = Path(path)
        if not p.is_file():
            return {"ok": False, "detail": f"找不到文件：{path}"}
        tf = textio.read(p)
        if tf is None:
            return {"ok": False, "detail": f"读不了这个文件：{path}"}
        text = tf.text
    if text is None or not str(text).strip():
        return {"ok": False, "detail": "没有内容和可补的注释（空文件或只有空白）"}

    result = annotate_text(str(text), style=style, only_missing=bool(only_missing))
    out = {"ok": True, "text": result["text"], "stats": result["stats"],
           "style": style, "source": path or "（粘贴的文本）"}

    if body.get("write"):
        if not path:
            return dict(out, ok=False, detail="没有给 path，无法写回；请改用另存为")
        write_back = bool(body.get("write_back"))
        target = Path(path) if write_back else Path(out_name_for(path))
        if target.exists() and not write_back and not body.get("overwrite"):
            return dict(out, ok=False,
                        detail=f"{target.name} 已存在；勾选覆盖或改个名字再来")
        try:
            backup = textio.write(target, result["text"],
                                  encoding=tf.encoding, bom=tf.bom,
                                  newline=tf.newline)
        except OSError as e:
            return dict(out, ok=False, detail=f"写入失败：{e}")
        out["out_path"] = str(target)
        out["backup"] = str(backup) if backup else ""
        out["detail"] = (f"已写回 {target.name}（原文件已备份）" if write_back
                         else f"已另存为 {target.name}")
    return out


# ---------------------------------------------------------------- 文档

# 能在线看的文档（白名单，只读仓库 `docs/` 里的这几个）
DOCS = {
    "guide": "user/zh-CN/getting-started.md",
    "shaders": "user/zh-CN/shader-guide.md",
    "thanks": "user/zh-CN/acknowledgments.md",
    "roadmap": "user/zh-CN/roadmap.md",
}

# 英文版在 `docs/user/en/`，文件名与中文版一一对应（见 tools/translate_docs.py）
DOCS_EN = {
    "guide": "user/en/getting-started.md",
    "shaders": "user/en/shader-guide.md",
    "thanks": "user/en/acknowledgments.md",
    "roadmap": "user/en/roadmap.md",
}

# 2026-11-25 起文档按 user/{zh-CN,en}/ 分层存放（根目录只留标准件）。
DOCS_DIR = BASE / "docs"


def api_guide(params):
    """把仓库里的文档渲染成 HTML，给界面里的「指南 / 致谢」页用。"""
    from core.mdrender import extract_title, to_html
    key = (params.get("doc") or "guide").strip()
    lang = (params.get("lang") or "").strip().lower()
    if not key or key not in DOCS:
        return {"ok": False, "detail": f"没有这份文档：{key}",
                "docs": [{"id": k, "name": v} for k, v in DOCS.items()]}
    name = DOCS[key]
    if lang.startswith("en"):
        en_name = DOCS_EN.get(key)
        if en_name and (DOCS_DIR / en_name).is_file():
            name = en_name
    path = DOCS_DIR / name
    if not path.is_file():
        # 打包时忘了带 docs/ 才会走到这里 —— 说清楚怎么修，别只报"找不到"
        extra = ("；打包时要把 docs 目录一起带上："
                 '--add-data "docs;docs"' if is_frozen() else "")
        return {"ok": False, "detail": f"找不到文档文件：{name}{extra}"}
    text = textio.read_text(path)
    return {"ok": True, "doc": key, "file": name,
            "title": extract_title(text, name),
            "html": to_html(text),
            "docs": [{"id": k, "name": v} for k, v in DOCS.items()]}


def api_combos(body):
    """一键组合：按目标目录解析成实际路径。"""
    target = _resolve_target(body)
    pc = target if (target and target.is_dir()) else None
    catalog = {"shaders": build_shader_catalog(pc), "memc": build_memc_catalog(pc)}
    out = []
    for c in COMBOS:
        shaders, memc, missing = resolve_combo(c, catalog)
        en = COMBOS_EN.get(c["id"])
        lazy_only = any(
            s in LAZY_BUNDLED_SHADERS
            for slot in c["shader_slots"] for s in slot)
        out.append({
            "id": c["id"], "icon": c["icon"], "lazy_only": lazy_only,
            "name": T(c["name"], en[0]) if en else c["name"],
            "note": T(c["note"], en[1]) if en else c["note"],
            "need": T(c.get("need", ""), en[2]) if en and en[2] else c.get("need", ""),
            "params": c["params"],
            "shaders": shaders, "memc": memc, "missing": missing,
        })
    return {"ok": True, "combos": out, "target": str(target) if target else ""}


# ---- 扫描源列表（第 7 项）：标准目录 + 手动添加目录，不做全盘扫 ----
def api_scandirs(params):
    """列出 shader/vpy 扫描源：target 的标准目录 + settings 里的手动添加项。"""
    target = _resolve_target({"target": params.get("target", "")})
    pc = target if (target and target.is_dir()) else None
    standard = [str(Path(pc) / "shaders"), str(Path(pc) / "vs")] if pc else []
    return {"ok": True, "standard": standard,
            "extra": list((load_settings() or {}).get("scan_dirs") or [])}


def api_scandirs_add(body):
    d = str(body.get("dir") or "").strip().strip('"')
    if not d or not Path(d).is_dir():
        return {"ok": False, "detail": T("目录不存在：", "Directory does not exist: ") + d}
    st = load_settings() or {}
    dirs = [x for x in (st.get("scan_dirs") or []) if str(x) != d]
    dirs.append(d)
    st["scan_dirs"] = dirs
    return {"ok": save_settings(st), "dirs": dirs}


def api_scandirs_remove(body):
    d = str(body.get("dir") or "").strip().strip('"')
    st = load_settings() or {}
    dirs = [x for x in (st.get("scan_dirs") or []) if str(x) != d]
    st["scan_dirs"] = dirs
    return {"ok": save_settings(st), "dirs": dirs}


def api_backups(params):
    """列出目标目录里的 .bak-时间戳 备份，供版本 / 回滚页面用。"""
    target = _resolve_target({"target": params.get("target", "")})
    if not target or not Path(target).is_dir():
        return {"ok": False, "detail": f"目标目录不存在：{target}"}
    import re as _re
    base = Path(target)
    # 兼容两种时间戳：旧的秒级 20260913-194801，新的毫秒级 20260913-194801-123（可能带 -2 防撞序号）
    pat = _re.compile(r"^(?P<orig>.+?)\.bak-(?P<stamp>\d{8}-\d{6}(?:-\d{3})?(?:-\d+)?)$")
    out = []
    for p in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime if x.is_file() else 0,
                    reverse=True):
        if not p.is_file():
            continue
        m = pat.match(p.name)
        if m:
            out.append({"path": str(p), "name": p.name, "orig": m.group("orig"),
                        "stamp": m.group("stamp"), "size": p.stat().st_size,
                        "mtime": int(p.stat().st_mtime)})
        elif p.name.endswith(".bak"):
            out.append({"path": str(p), "name": p.name, "orig": p.name[:-4],
                        "stamp": "", "size": p.stat().st_size,
                        "mtime": int(p.stat().st_mtime)})
    return {"ok": True, "target": str(base), "backups": out}


def api_restore(body):
    """把某个备份覆盖回原文件（覆盖前先把当前版本也备份一次）。"""
    path = str(body.get("path", "") or "").strip()
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "detail": f"找不到备份：{path}"}
    if not _inside(p, _allowed_write_roots()):
        return {"ok": False,
                "detail": "只允许回滚目标配置目录里的备份（安全限制）。"}
    import re as _re
    m = _re.match(r"^(?P<orig>.+)\.bak-(?:\d{8}-\d{6}(?:-\d{3})?(?:-\d+)?)$", p.name)
    orig_name = m.group("orig") if m else (p.name[:-4] if p.name.endswith(".bak") else "")
    if not orig_name:
        return {"ok": False, "detail": "这个文件名不像备份，拒绝操作"}
    dst = p.with_name(orig_name)
    try:
        keep = backup_file(dst)
        textio.write_atomic(dst, p.read_bytes())
    except OSError as e:
        return {"ok": False, "detail": f"回滚失败：{e}"}
    detail = f"已用 {p.name} 覆盖 {orig_name}"
    if keep:
        detail += f"（当前版本另存为 {keep.name}）"
    return {"ok": True, "detail": detail, "restored": str(dst)}


def api_analyze(body):
    """分析一段配置文本，给进阶页面右侧的体检面板用。"""
    text = str(body.get("text", "") or "")
    if not text.strip():
        return {"ok": False, "detail": "没有内容可分析"}
    data = parse_config_text(text)
    # 空值占位行（`vo=`）不算"已启用"，否则一份空壳模板会被评成"所有高档选项都开着"
    active = [k for k in data["present"]
              if str((data["values"] or {}).get(k, "")).strip()]
    # 评分函数认识 shader:/memc: 前缀，这里把路径还原成它认识的写法
    active += ["shader:" + Path(s).stem for s in data["shaders"]]
    if data["memc"]:
        active += ["memc:" + Path(data["memc"]).stem]
    scores = score_active(active)
    overall = overall_score(scores)
    # 冲突检测要看全量键：界面不认识 linear-upscaling，但 mpv 认识
    issues, conflicts = full_check({"values": data["all_values"],
                                    "shaders": data["shaders"],
                                    "memc": data["memc"],
                                    "profiles": data["profiles"]})
    return {"ok": True, "scores": scores, "overall": overall, "grade": grade_of(overall),
            "active": active, "shaders": data["shaders"], "memc": data["memc"],
            "issues": issues, "conflicts": conflicts}




# ---------------------------------------------------------------- HTTP 层

class Handler(BaseHTTPRequestHandler):
    server_version = "MPVConfigBuilder/" + VERSION
    timeout = 30                              # 读超时：慢连接不再永久占线程
    MAX_BODY = 4 * 1024 * 1024                # 请求体上限：本地 JSON 接口 4MB 足够
    _ORIGIN_HOSTS = ("127.0.0.1", "localhost", "::1")

    def log_message(self, fmt, *args):        # 安静一点
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False))

    def _origin_ok(self):
        """跨源防护：空 Origin（curl / 测试）放行，有值必须是本机同源。

        浏览器对 application/json 的跨站请求会先预检，但 text/plain 的"简单请求"
        不会 —— 所以必须同时要求 Content-Type，两道一起才挡得住 CSRF。
        """
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        try:
            u = urlparse(origin)
        except ValueError:
            return False
        if u.scheme not in ("http", "https") or u.hostname not in self._ORIGIN_HOSTS:
            return False
        return u.port in (None, self.server.server_address[1])

    def _reject(self, code, detail):
        self.close_connection = True
        return self._json({"ok": False, "detail": detail}, code)

    # ---- 以下三个方法：HTTP ↔ 传输无关层的适配器 ----
    #
    # 真正的分发在 `webui/api.py` 的 dispatch() 里（纯函数，不碰 socket）。
    # 这里只做三件事：把 HTTP 请求翻译成 Request、把 Response 发出去、
    # 以及**服务静态文件**（那是 HTTP 特有概念，不进 dispatch，见 FR-2）。

    def _reply(self, resp):
        """把 api.Response 发出去。dict 走 JSON，str 走纯文本。"""
        if resp.json:
            return self._json(resp.payload, resp.status)
        return self._send(resp.status, resp.payload or "",
                          "text/plain; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # API 名字空间交给 dispatch；其它一律当静态文件
        if path.startswith("/api/"):
            query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
            return self._reply(api.dispatch(
                api.Request(path=path, method="GET", query=query)))

        if path == "/":
            path = "/index.html"
        target = (STATIC / path.lstrip("/")).resolve()
        # 用真正的路径包含判断，不用字符串前缀（/a/static_evil 会骗过 /a/static 的前缀检查）
        if not _inside(target, [STATIC]) or not target.is_file():
            return self._send(404, "not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        return self._send(200, target.read_bytes(), ctype)

    def do_POST(self):
        if not self._origin_ok():
            return self._reject(403, "拒绝跨源请求（Origin 不是本机同源）")
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return self._reject(415, "只接受 Content-Type: application/json")
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            if self.headers.get("Transfer-Encoding"):
                return self._reject(411, "不接受分块传输，请给出 Content-Length")
            length = 0
        else:
            try:
                length = int(raw_len)
            except (TypeError, ValueError):
                return self._reject(400, "Content-Length 不是合法整数")
            if length < 0:
                return self._reject(400, "Content-Length 不能为负")
            if length > self.MAX_BODY:
                return self._reject(
                    413, f"请求体超过 {self.MAX_BODY // (1 << 20)} MB 上限")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = None          # dispatch 会补成 {}，保持重构前的宽容行为
        return self._reply(api.dispatch(
            api.Request(path=urlparse(self.path).path, method="POST", body=body)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_window(url):
    """优先用 Edge/Chrome 的 --app 模式开一个没有浏览器边框的窗口。"""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for exe in candidates:
        if Path(exe).is_file():
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860"])
                return True
            except OSError:
                continue
    webbrowser.open(url)
    return False


def main():
    # ---- stdio 模式：给 Tauri 外壳用的，不开端口（M5-E-1 + W-4 第②步）
    if "--stdio" in sys.argv:
        try:
            from . import stdio as _stdio
        except ImportError:                                  # pragma: no cover
            import stdio as _stdio                           # type: ignore
        return _stdio.serve()

    no_window = "--no-window" in sys.argv
    port = 0
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (ValueError, IndexError):
            port = 0
    if not port:
        port = free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    log(f"{APP_TITLE} web ui  →  {url}")
    log("关闭窗口后按 Ctrl+C 结束服务")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if not no_window:
        open_window(url)
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        log("\n已退出")
        httpd.shutdown()


if __name__ == "__main__":
    sys.exit(main())

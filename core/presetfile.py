# -*- coding: utf-8 -*-
r"""用户自己的预设：导出成文件 / 从文件导入 / 存在本地。

## 为什么要有它

原来的 `saveLocal()` 只把 `target` / `writeMode` / `source` / `mode` 存进
localStorage —— **`APP.values` 根本没存**。于是刷新一下页面，辛苦调好的一套就没了；
也没法把"我调好的这套"发给别人。300★ 的同类工具 Glow 早就支持把自定义预设
存成文件导出/导入（见 `_reference/GitHub同类项目调查.md`），这是我们的缺口。

## 为什么是"注册表目录"而不是"浏览器 localStorage"

一开始想纯前端做（localStorage + 下载/上传 json），但那样有两个躲不掉的毛病：
  · 换个浏览器 / 清了站点数据就没了，用户以为是"丢文件"；
  · 想把自己的一套发给别人，只能靠"另存为文件"绕一圈。

所以做成 `预设注册表`：**本地目录里的 json 就是真相**。前端的导出/导入
只是把它变成文件或从文件读回来。文件放在**用户数据目录**下
（`core.paths.user_data_dir()`，即 `%LOCALAPPDATA%\MPVConfigBuilder\presets`）——
**不放在 exe 旁边**：装到 `Program Files` 之后那里是只读的。

## 格式（尽量小、尽量能看懂）

```json
{
  "kind": "mpv-config-builder-preset",
  "version": 1,
  "name": "我那套看番的",
  "created": "2026-09-13T21:00:00",
  "app_version": "0.1.0",
  "state": {
    "values": {"vo": "gpu-next", "scale": "ewa_lanczossharp"},
    "shaders": ["~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_M.glsl"],
    "memc": "~~/vs/MEMC_RIFE_DML.vpy",
    "disable": ["interpolation"]
  }
}
```

`kind` 那一行是**防呆**用的：随便拖一个 json 进来要能明确拒绝，
而不是把里面的键当成选项名灌进配置。
"""
import json
import os
import re
import time
from pathlib import Path

KIND = "mpv-config-builder-preset"
VERSION = 1

# 测试用：把预设目录指到临时目录，别往仓库里写东西
_REGISTRY_OVERRIDE = None

# 选项名：mpv 的键就是小写字母/数字/连字符/下划线/点
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
# 文件名：不允许路径分隔符与 Windows 保留字符，也不允许以点开头
BAD_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}

# 一个预设最多装多少项 —— 防"有人塞个几万行 json 进来"
MAX_KEYS = 2000
MAX_FILE_BYTES = 2 * 1024 * 1024


def registry_dir():
    """用户预设存在哪：`<user_data_dir()>/presets`（即 `%LOCALAPPDATA%\\MPVConfigBuilder\\presets`）。

    ⚠⚠ **不能用 `writable_root()`**（这是 W-2 修的 bug）：冻结形态下它是
    **exe 所在目录** —— 装到 `Program Files` 就是只读，用户点「存下这一套」会
    **静默失败**，而且**只在装完之后才暴露**（开发机上跑的是源码形态，能写，
    所以复现不了；现有测试又都用下面的覆盖把目录指走了，顺手把 bug 也隔离掉了）。
    用户数据一律走 `user_data_dir()`（它不依赖冻结与否，源码与打包下位置一致）。

    两个覆盖途径，优先级**高于** `user_data_dir()`，都是为了**测试不往真目录写东西**：
      · 环境变量 `DSH_MPV_PRESET_DIR`
      · 模块级 `set_registry_dir()`（测试里更顺手，不用改环境）
    """
    global _REGISTRY_OVERRIDE
    if _REGISTRY_OVERRIDE is not None:
        d = Path(_REGISTRY_OVERRIDE)
    else:
        env = (os.environ.get("DSH_MPV_PRESET_DIR") or "").strip()
        if env:
            d = Path(env)
        else:
            from .paths import user_data_dir
            d = Path(user_data_dir()) / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def set_registry_dir(path):
    """把预设目录指到别处（测试/工具用）。传 `None` 或空串恢复默认。"""
    global _REGISTRY_OVERRIDE
    s = str(path).strip() if path is not None else ""
    _REGISTRY_OVERRIDE = Path(s) if s else None


def safe_name(name, fallback="preset"):
    """把用户给的名字洗成一个安全的文件名（不带扩展名）。

    去掉路径分隔符与 Windows 保留字符、掐掉结尾的点和空格
    （Windows 不允许文件名以点或空格结尾），并避开 CON/PRN 这类保留名。

    ⚠ 顺序有讲究：先把分隔符之类的替换成 `_`，**再**掐首尾的点和空格。
    反过来的话 `..\\..\\x` 会先被掐成 `x`（看着挺安全），
    但真正危险的是没被替换干净的那种；而现在替换完再掐，
    `..` 这类只剩点的情况会落回 fallback，目录穿越无从谈起。
    """
    s = BAD_NAME_RE.sub("_", str(name or "")).strip().strip(".")
    s = s.strip()
    if not s or set(s) <= {"_"}:
        s = fallback
    if s.upper() in RESERVED:
        s = "_" + s
    return s[:80]


def build_preset(state, name="", note="", app_version=""):
    """把界面状态打包成一个预设 dict。

    `state` 就是前端那一个 state（values / shaders / memc / disable）。
    只挑我们认识的键 —— 顺手把界面里的临时字段（pending 之类）挡在外面。
    """
    values = {}
    for k, v in (state.get("values") or {}).items():
        k = str(k).strip()
        v = "" if v is None else str(v)
        if KEY_RE.match(k) and v.strip():
            values[k] = v
    shaders = [str(s) for s in (state.get("shaders") or []) if str(s).strip()]
    disable = [str(s) for s in (state.get("disable") or []) if str(s).strip()]
    return {
        "kind": KIND,
        "version": VERSION,
        "name": str(name or "").strip(),
        "note": str(note or "").strip(),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "app_version": str(app_version or ""),
        "state": {
            "values": values,
            "shaders": shaders,
            "memc": str(state.get("memc") or "").strip(),
            "disable": disable,
        },
    }


def validate_preset(data):
    """检查一份导入的数据像不像我们的预设。

    返回 (ok, 说明, 洗干净的预设 或 None)。**不抛异常** —— 调用方要能
    把"这不是我们的文件"当成普通结果显示给用户。
    """
    if not isinstance(data, dict):
        return False, "这个文件的顶层不是 JSON 对象", None
    kind = data.get("kind")
    if kind != KIND:
        return False, (f"这不是 MPV Config Builder 的预设文件"
                       f"（kind = {kind!r}，应当是 {KIND!r}）"), None
    ver = data.get("version")
    if not isinstance(ver, int) or ver < 1:
        return False, f"版本号不对：{ver!r}", None
    if ver > VERSION:
        return False, (f"这份预设是更新版本的工具存的（v{ver}，本工具认到 v{VERSION}），"
                       "升级一下再来"), None
    st = data.get("state")
    if not isinstance(st, dict):
        return False, "预设里没有 state", None

    values = st.get("values") or {}
    if not isinstance(values, dict):
        return False, "state.values 不是对象", None
    if len(values) > MAX_KEYS:
        return False, f"选项太多（{len(values)} 项，上限 {MAX_KEYS}）", None

    clean_values = {}
    skipped = []
    for k, v in values.items():
        k = str(k).strip()
        if not KEY_RE.match(k):
            skipped.append(k)
            continue
        clean_values[k] = "" if v is None else str(v)

    def strlist(x):
        if not isinstance(x, list):
            return []
        return [str(i) for i in x if str(i).strip()][:MAX_KEYS]

    out = build_preset(
        {"values": clean_values, "shaders": strlist(st.get("shaders")),
         "memc": st.get("memc") or "", "disable": strlist(st.get("disable"))},
        name=data.get("name", ""), note=data.get("note", ""),
        app_version=data.get("app_version", ""))
    out["created"] = str(data.get("created") or "") or out["created"]

    detail = f"读入 {len(clean_values)} 个选项"
    if out["state"]["shaders"]:
        detail += f"、{len(out['state']['shaders'])} 个 shader"
    if out["state"]["memc"]:
        detail += "、1 个补帧脚本"
    if skipped:
        detail += f"（跳过 {len(skipped)} 个不像选项名的键）"
    return True, detail, out


def load_preset_file(path):
    """从一个文件读预设。返回 (ok, 说明, 预设 或 None)。"""
    p = Path(path)
    if not p.is_file():
        return False, f"找不到文件：{path}", None
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        return False, f"文件太大（{size // 1024} KB，上限 {MAX_FILE_BYTES // 1024} KB）", None
    try:
        raw = p.read_bytes()
    except OSError as e:
        return False, f"读不了这个文件：{e}", None
    # 认 BOM —— 记事本另存为 UTF-8 会加 BOM，json.loads 不认。
    # 也认 GBK：老用户拿记事本存的 json 可能是 GBK。
    last = None
    data = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            data = json.loads(raw.decode(enc))
            break
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            last = e
    else:
        return False, f"解析不了这个文件（不是合法 JSON）：{last}", None
    if data is None:
        return False, "解析不了这个文件（不是合法 JSON）", None
    return validate_preset(data)


def list_presets():
    """列出注册表里的预设。读不动的文件跳过但**记下来**，不装作没看见。

    ⚠ 每一项都带上完整的 `state`。一开始为了"列表轻一点"只回了元信息
    （个数 / shader 数），结果前端"点一下套用"拿到的是没有 state 的对象，
    套上去永远是空的 —— 还弹了个"已套用（0 项）"的提示，看着像成功了。
    一份预设就是几十个键值对，JSON 里多这几百字节不值得为它埋一个坑。
    """
    out = []
    bad = []
    for f in sorted(registry_dir().glob("*.json")):
        ok, detail, preset = load_preset_file(f)
        if not ok:
            bad.append({"file": f.name, "detail": detail})
            continue
        out.append({
            "id": f.stem,
            "file": str(f),
            "name": preset.get("name") or f.stem,
            "note": preset.get("note", ""),
            "created": preset.get("created", ""),
            "count": len(preset["state"]["values"]),
            "shaders": len(preset["state"]["shaders"]),
            "memc": bool(preset["state"]["memc"]),
            "size": f.stat().st_size,
            "state": preset["state"],       # ← 前端套用要用，别省
        })
    return {"ok": True, "presets": out, "broken": bad, "dir": str(registry_dir())}


def save_preset(state, name, note="", app_version="", overwrite=False):
    """把当前状态存进注册表。返回 (ok, 说明, 预设 或 None)。"""
    preset = build_preset(state, name=name, note=note, app_version=app_version)
    if not preset["state"]["values"] and not preset["state"]["shaders"] \
            and not preset["state"]["memc"]:
        return False, "一个选项都没勾，没什么可存的", None
    stem = safe_name(name or preset["name"], fallback="preset")
    p = registry_dir() / f"{stem}.json"
    if p.exists() and not overwrite:
        return False, f"「{stem}」已经存在了；勾选覆盖或者换个名字", None
    p.write_text(json.dumps(preset, ensure_ascii=False, indent=1), encoding="utf-8")
    return True, f"已存为「{stem}」", preset


def delete_preset(preset_id):
    """删掉注册表里的一个预设。返回 (ok, 说明)。"""
    stem = safe_name(preset_id)
    p = registry_dir() / f"{stem}.json"
    if not p.is_file():
        return False, f"没有这个预设：{stem}"
    try:
        p.unlink()
    except OSError as e:
        return False, f"删不掉：{e}"
    return True, f"已删除「{stem}」"

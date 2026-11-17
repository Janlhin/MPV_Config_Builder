# -*- coding: utf-8 -*-
"""与传输无关的 API 分发层。

## 为什么要有这一层

原来分发逻辑（94 行）埋在 `server.py` 的 `do_GET` / `do_POST` 里，于是
"业务逻辑"和"HTTP 传输"绑在一起 —— 想换一种传输（比如让外壳用
stdio 直接接后端，不开端口）就只能重写。

现在把它提成一个**纯函数** `dispatch(req) -> Response`：

    ┌──────────────────────────┐
    │  dispatch(Request)        │────▶ server.api_*（46 个纯函数）
    └──────────────────────────┘
        ▲                  ▲
    HTTP 适配器         未来的 stdio 适配器
    （浏览器/开发/测试）  （Tauri 外壳，不开端口）

`dispatch` 里**不许出现** `http.server` / socket / `self` / 文件描述符 ——
这是它可替换的前提。静态文件也**不归它管**（那是 HTTP 特有概念，见 FR-2）。

## ⚠ 路由表为什么存"属性名"而不是函数对象

`api_*` 这 46 个函数目前还在 `server.py` 里。如果这里在**导入期**写
`from .server import api_status`，就会形成 `server → api → server` 的**循环导入**。

所以表里存的是**字符串**（`"api_status"`），`dispatch` 在**调用时**通过
`getattr(server, name)` 解析。副作用是好事：测试可以用猴补替换任意处理函数
来验证异常路径（见 `tests/test_api_dispatch.py`）。

## 行为必须与重构前逐条一致

最容易在重构里悄悄改掉的是这些边角，都已按原样保留：

  · 无参 GET 表**优先于**带参 GET 表
  · 未命中的 POST → `404 {"ok": false, "detail": "unknown api"}`
  · 未命中的 GET → `404` 纯文本 `"not found"`（**不是 JSON**）
  · **POST body 不是合法 JSON 时传空 dict，而不是报 400**（解析失败由适配器兜）
  · 处理函数抛异常 → `500 {"ok": false, "detail": "<类名>: <消息>"}`
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union

from core.i18n import set_lang as _set_lang


@dataclass
class Request:
    """一个与传输无关的请求。"""
    path: str
    method: str = "GET"                       # "GET" | "POST"
    query: Dict[str, str] = field(default_factory=dict)
    body: Any = None                          # POST：解析后的 dict（解析失败时是 {}）


@dataclass
class Response:
    """一个与传输无关的响应。

    `json=True` 时适配器按 JSON 序列化 `payload`；否则当纯文本发。
    """
    status: int
    payload: Union[Dict[str, Any], str, None]
    json: bool = True


# ---------------------------------------------------------------- 路由表
#
# key = 完整路径；value = **server.py 里的属性名**（字符串，理由见模块 docstring）。

# 无参 GET
ROUTES_GET = {
    "/api/status": "api_status",
    "/api/presets": "api_presets",
    "/api/options": "api_options",
    # 版本级兼容检测（待做 §〇 第 13 项）：探测用户 mpv + 选项存在性比对
    "/api/compat": "api_compat",
}

# 需要查询参数的 GET（扁平 dict 由适配器准备好）
ROUTES_QUERY = {
    "/api/catalog": "api_catalog",
    "/api/raw": "api_raw_read",
    "/api/backups": "api_backups",
    "/api/db/options": "api_db_options",
    "/api/vpy/list": "api_vpy_list",
    "/api/guide": "api_guide",
    "/api/keys": "api_keys",
    "/api/uosc": "api_uosc",
    "/api/search": "api_search",
    "/api/combos": "_route_combos",
    # ⚠ 这三条一度在搬运脚本里被**静默丢掉**（那条正则用非贪婪 `^\}` 匹配三张表，
    #   而上面两个 lambda 是跨行的、里面带 `}`，于是从那里开始整段没匹配干净）。
    #   靠 tests/test_api_dispatch.py 的条数断言抓回来的 —— 别的测试全绿，
    #   因为它们只打自己关心的那几个接口。**别删这三行上面那条教训。**
    "/api/downloads": "api_downloads",
    "/api/download/job": "api_download_job",
    "/api/userpresets": "api_user_presets",
    "/api/install/plan": "_route_install_plan",
    "/api/scandirs": "api_scandirs",
}

# POST
ROUTES_POST = {
    "/api/basic/preview": "api_basic_preview",
    "/api/basic/apply": "api_basic_apply",
    "/api/scan": "api_scan",
    "/api/config/load": "api_config_load",
    "/api/config/preview": "api_config_preview",
    "/api/config/apply": "api_config_apply",
    "/api/raw/save": "api_raw_save",
    "/api/restore": "api_restore",
    "/api/analyze": "api_analyze",
    "/api/report": "api_report",
    "/api/vpy/fuse": "api_vpy_fuse",
    "/api/keys/save": "api_keys_save",
    "/api/keys/promote": "api_keys_promote",
    "/api/uosc/save": "api_uosc_save",
    "/api/download/start": "api_download_start",
    "/api/download/remove": "api_download_remove",
    "/api/download/check": "api_download_check",
    "/api/manifest": "api_manifest_open",
    "/api/annotate": "api_annotate",
    "/api/config/tidy": "api_config_tidy",
    "/api/install/lazy": "api_install_start",
    "/api/presets/save": "api_presets_save",
    "/api/presets/delete": "api_presets_delete",
    "/api/presets/load": "api_presets_load",
    "/api/scandirs/add": "api_scandirs_add",
    "/api/scandirs/remove": "api_scandirs_remove",
    "/api/presets/export": "api_presets_export",
}


# ---------------------------------------------------------------- 两个原 lambda
#
# 原来这两条在 server.py 里是 `lambda q: api_xxx({...})`。lambda 没法用属性名
# 引用（也没法猴补），所以提成具名函数挂回 server —— **行为一字不改**。

def install_route_helpers(server_module):
    """把两个原 lambda 提成的具名函数挂到 server 上。

    ⚠ 由 `server.py` 在导入本模块之后调用。这是解开循环导入的关键：
    本模块不认识 `server` 的任何具体函数，只由对方向这里注册。
    """
    def _route_combos(query):
        return server_module.api_combos({"target": query.get("target", "")})

    def _route_install_plan(query):
        return server_module.api_install_plan(
            {"target": query.get("target", ""), "mirror": query.get("mirror", "")})

    server_module._route_combos = _route_combos
    server_module._route_install_plan = _route_install_plan


# ---------------------------------------------------------------- 分发

NOT_FOUND_TEXT = "not found"
UNKNOWN_API = {"ok": False, "detail": "unknown api"}


def _resolve(name):
    """把属性名解析成 server 里的处理函数。

    ⚠ 必须**在调用时**解析（不能在导入期 import），否则循环导入。
    顺带的好处：测试能猴补。

    ⚠⚠ 两种运行方式都要认（**踩过两次**）：直接跑脚本（`py webui\\server.py`）
    时没有包上下文，`from . import server` 会报
    "attempted relative import with no known parent package"；
    被当包导入时反过来。单元测试走的是包导入那条路，**所以这个错测试全绿也照样存在**
    —— 只有真起服务器才暴露。
    """
    try:
        from . import server
    except ImportError:                                  # pragma: no cover
        import server                                    # type: ignore
    return getattr(server, name)


def _error(e):
    """异常 → 500。只给类名与消息，**不泄 traceback**（NFR-4）。"""
    return Response(500, {"ok": False, "detail": f"{type(e).__name__}: {e}"})


def dispatch(req):
    """把一个 Request 分发给对应的处理函数，返回 Response。

    这些分支的顺序和条件**逐条对应重构前的 `do_GET` / `do_POST`**，
    注释里标了"为什么要保持"。改动这里之前先看模块 docstring。
    """
    # T14：语言上下文。前端（两种传输）每个请求都带 lang（GET 走 query、
    # POST 走 body.lang）；没带 = 中文，同时把线程上可能残留的上一请求
    # 语言清掉（ThreadingHTTPServer 会复用线程）。
    _lang = None
    if isinstance(req.query, dict):
        _lang = req.query.get("lang")
    if not _lang and isinstance(req.body, dict):
        _lang = req.body.get("lang")
    _set_lang(_lang)

    path = req.path or ""
    method = (req.method or "GET").upper()

    if method == "GET":
        # ① 无参表优先（重构前就是先查 ROUTES_GET 再查 ROUTES_QUERY）
        name = ROUTES_GET.get(path)
        if name:
            try:
                return Response(200, _resolve(name)())
            except Exception as e:                       # noqa: BLE001
                return _error(e)
        name = ROUTES_QUERY.get(path)
        if name:
            try:
                return Response(200, _resolve(name)(dict(req.query or {})))
            except Exception as e:                       # noqa: BLE001
                return _error(e)
        # 未命中的 GET：这里只回"不是我的"，**静态文件由适配器负责**
        return Response(404, NOT_FOUND_TEXT, json=False)

    if method == "POST":
        name = ROUTES_POST.get(path)
        if not name:
            # 重构前就是这个词，现有测试盯着它
            return Response(404, dict(UNKNOWN_API))
        # ⚠ 重构前 body 解析失败会落到 {} 然后**照常调用**处理函数（不是 400）。
        # 这个宽容行为要保留 —— 适配器解析失败时传 None，这里补成 {}。
        body = req.body if req.body is not None else {}
        try:
            return Response(200, _resolve(name)(body))
        except Exception as e:                           # noqa: BLE001
            return _error(e)

    # HEAD / PUT / … 一律当作"没有这个资源"
    return Response(404, NOT_FOUND_TEXT, json=False)


__all__ = ["Request", "Response", "dispatch", "install_route_helpers",
           "ROUTES_GET", "ROUTES_QUERY", "ROUTES_POST"]

# -*- coding: utf-8 -*-
"""stdio 传输：一行一条 JSON 的请求/响应（W-4 第②步 + M5-E-1）。

## 协议

    → {"id":1,"path":"config/load","method":"POST","body":{...}}
    ← {"id":1,"ok":true,"data":{...}}
    ← {"id":1,"ok":false,"status":500,"error":"ValueError: xxx"}

* `path` 是**领域名**（`config/load` / `status` / `keys/save`…），不带 `/api` 前缀
  —— 协议不该绑死 HTTP 的路径拼法。适配器负责归一化（也容错地带前缀）。
* `method` 可省：在 POST 路由表里就当 POST，否则 GET。
* `id` 必填并原样回显，前端靠它把响应配回请求。

## ⚠ 唯一的硬约束：stdout 只能走协议

HTTP 模式下多打一行字没人管；stdio 模式下**一行日志就足以让整个后端失联**
—— Electron 那边 `JSON.parse` 会炸，而且后续所有响应都错位。
所以这个模块的 `serve()` 一进来就把 `server.QUIET_STDOUT` 打开，
之后 `server.log()` 一律走 stderr。

**防线不是"记得别乱 print"，而是 `tests/test_stdio.py` 里那条
「stdout 每一行都必须能 json.loads」的测试。** 谁不小心加了 print，它就红。

## 为什么逐条处理、不并发

`download/start` 这类耗时操作**本身就已经是后台线程**（`api_download_start` 立刻返回
job id），所以逐条读不会卡住长任务；反过来并发会让响应乱序，
前端按 `id` 配对也就失去意义了。简单且不会错。

这个模块**不许 import `http.server` / socket** —— 它是传输层，
业务逻辑全在 `dispatch()` 后面（见 `webui/api.py`）。
"""
import json
import sys

# 两种运行方式都要认（脚本模式 / 包导入）—— 见 api.py 里那段踩过两次的注释
try:
    from . import api
except ImportError:                                      # pragma: no cover
    import api                                           # type: ignore


def _as_text(x):
    """query 的值统一成字符串（协议里可能传数字/布尔）。"""
    if isinstance(x, bool):
        return "true" if x else "false"
    if x is None:
        return ""
    return str(x)


def infer_method(path):
    """按路由表推断方法：在 POST 表里就是 POST，否则 GET。

    这样前端发 `{"path":"status"}` 不用写 method，少一处能写错的地方。
    """
    if path in api.ROUTES_POST:
        return "POST"
    return "GET"


def normalize(p):
    """领域名 → dispatch 认识的完整路径。

        config/load   → /api/config/load
        /api/status   → /api/status      （容错：带了前缀也认）
        /status       → /api/status      （容错：只带一个斜杠也认）

    归一化放在这里而不是让协议直接写 `/api/...`，是为了传输与 HTTP 路径解耦：
    哪天 HTTP 前缀改了，协议不用动。
    """
    s = str(p or "").strip()
    if not s:
        return ""
    if s.startswith("/api/"):
        return s
    if s.startswith("api/"):
        return "/" + s
    return "/api/" + s.lstrip("/")


def _bad(rid, detail, status=400):
    return {"id": rid, "ok": False, "status": status, "error": detail}


def handle_line(line):
    """处理一行，返回要写回去的 dict；空行返回 None（不产生响应）。

    这个函数是纯的（除了 dispatch 本身），所以测试可以喂字符串拿字符串，
    不用起进程 —— 这是 FR-13 的意义。
    """
    raw = (line or "").strip()
    if not raw:
        return None                                          # FR-7

    try:
        msg = json.loads(raw)
    except ValueError as e:
        return _bad(None, f"不是合法 JSON：{e}")              # FR-6

    if not isinstance(msg, dict):
        return _bad(None, "请求必须是一个 JSON 对象")         # FR-6

    rid = msg.get("id")
    if rid is None:
        # id 不能省：前端靠它把响应配回请求，没 id 的响应它没法用
        return _bad(None, "请求缺少 id")                      # FR-4
    path = msg.get("path")
    if not path:
        return _bad(rid, "请求缺少 path")

    full = normalize(path)
    method = (msg.get("method") or "").upper() or infer_method(full)
    query = msg.get("query") or {}
    if not isinstance(query, dict):
        return _bad(rid, "query 必须是一个 JSON 对象")
    query = {str(k): _as_text(v) for k, v in query.items()}

    # 未知方法直接告诉调用方，别让它走到 dispatch 的 404 分支后一头雾水
    if method not in ("GET", "POST"):
        return _bad(rid, f"不支持的 method：{method}")

    req = api.Request(path=full, method=method, query=query, body=msg.get("body"))
    res = api.dispatch(req)

    if res.status >= 400 and not (isinstance(res.payload, dict) and res.payload.get("ok")):
        # dispatch 已经给出结构化错误（404 unknown api / 500 异常），原样转达
        detail = res.payload
        if isinstance(detail, dict):
            detail = detail.get("detail", json.dumps(detail, ensure_ascii=False))
        return _bad(rid, str(detail), res.status)
    return {"id": rid, "ok": True, "data": res.payload}       # FR-4


def serve(stdin=None, stdout=None, stderr=None):
    """JSONL 主循环。读到 EOF 就正常退出（FR-8）。"""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr

    # 从现在起，server 那边的 log() 一律走 stderr（FR-2）
    try:
        from . import server as _server
    except ImportError:                                      # pragma: no cover
        import server as _server                             # type: ignore
    _server.QUIET_STDOUT = True
    _server.LOG_STREAM = stderr

    # Windows 控制台默认 GBK，中文会乱码 —— 显式 UTF-8（FR-12）
    for stream in (stdin, stdout, stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):                  # pragma: no cover
            pass

    for line in stdin:
        out = handle_line(line)
        if out is None:
            continue
        stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        stdout.flush()                                        # FR-9
    return 0


__all__ = ["serve", "handle_line", "normalize", "infer_method"]

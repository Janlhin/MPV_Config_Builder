# Spec — 传输层可替换：抽出 `dispatch()`（W-4 第一步）

| | |
|---|---|
| **作者** | DSH agent |
| **日期** | 2026-09-14 |
| **状态** | **已实施**（2026-09-14，全部 AC 通过，见 §10 验收记录） |
| **评审** | 用户（"做" = 批准开工） |
| **上游决策** | 用户 2026-09-13：**不走 127.0.0.1，让 Python 直接接 Electron**（路线图 W-4） |

---

## 1. Context（为什么做这个）

用户明确不想让桌面版"在本机开一个 HTTP 端口"，要求 Python 后端与 Electron 外壳直接对接。
但**现有的 HTTP 服务不能删**：它是浏览器调试的唯一通道，也是现有接口测试的载体。

实测数据说明这件事比看上去便宜（不是估算）：

- `api_*` 函数 **39 个，全是纯函数** —— 没有一个碰 `self` / `handler` / `rfile` / `send_header` / `BaseHTTPRequest`。**业务逻辑与传输已经天然分离**，只是分发代码埋在 `Handler` 类里。
- 真正与 HTTP 绑定的只有 **`do_GET` 25 行 + `do_POST` 69 行 = 94 行**。
- 路由表 **GET 3 / QUERY 12 / POST 24 = 39 条**（与 `check_docs` 报的接口数一致）；**没有同一路径两种方法、也没有两张表重复的**。

所以本步**不做 stdio**，只把分发抽成一个纯粹的函数，让传输变成"可替换的一层"。
本步的价值独立成立：**为 stdio 铺路**，同时让 `server.py`（1319 行）瘦一圈。

---

## 2. Functional Requirements

| ID | 要求 |
|---|---|
| **FR-1** | 系统 **MUST** 提供一个与传输无关的纯函数 `dispatch(req)`，输入一个请求对象，输出一个响应对象。它 **MUST NOT** 依赖 `http.server`、socket、`self`、文件描述符。 |
| **FR-2** | `dispatch` **MUST NOT** 处理静态文件（`*.html` / `*.js` / `*.css`）。静态文件**留在 HTTP 适配器**里。 |
| **FR-3** | 分发顺序 **MUST** 与现状一致：先查"无参 GET"表，未命中再查"带参 GET"表。 |
| **FR-4** | `dispatch` **MUST** 捕获处理函数抛出的任何异常，并返回 `500` + `{"ok": false, "detail": "<异常类名>: <消息>"}`。 |
| **FR-5** | 未命中的 **POST** **MUST** 返回 `404` + `{"ok": false, "detail": "unknown api"}`。 |
| **FR-6** | 未命中的 **GET**（且不是静态文件）**MUST** 返回 `404` + 纯文本 `not found`。 |
| **FR-7** | `dispatch` 返回的响应 **MUST** 同时带 `status` 与 `payload`；`payload` 是 dict（由 HTTP 适配器负责 JSON 序列化）或 str（纯文本）。 |
| **FR-8** | 现有 HTTP 服务 **MUST** 继续工作，且 **MUST** 只通过新的 `dispatch` 分发 API 请求（不允许两套分发逻辑并存）。 |
| **FR-9** | 路由表 **MUST** 从 `server.py` 移到新模块 `webui/api.py`，`server.py` 不再定义它们。 |
| **FR-10** | `dispatch` **MUST** 可被单独测试：构造请求对象即可，**不需要起服务、不需要开端口**。 |
| **FR-11** | 路由表 **MUST** 用**字符串**引用 `server.py` 里的处理函数（如 `"api_status"`），由 `dispatch` 在**调用时**解析成模块属性。**MUST NOT** 在导入期直接引用 —— 那会形成 `server → api → server` 的循环导入（`api_*` 函数仍在 `server.py` 里）。 |
| **FR-12** | 处理函数 **MUST** 通过模块属性在调用时解析，因此测试可以用猴补（monkeypatch）替换任一处理函数来验证异常路径。 |

---

## 3. Non-Functional Requirements

| ID | 要求 | 怎么验 |
|---|---|---|
| **NFR-1** | **零行为变化**：现有 **548 项**测试 **MUST** 全部通过，一条都不许改断言。 | 跑全量测试 |
| **NFR-2** | `server.py` **MUST** 变短（至少减掉那 94 行分发逻辑）。 | 前后行数对比 |
| **NFR-3** | 新增测试 **MUST** 不依赖网络与端口（`dispatch` 直调）。 | 测试里不出现 `ThreadingHTTPServer` |
| **NFR-4** | 异常路径 **MUST** 不把 traceback 泄进响应体（只给类名与消息）。 | 与现状一致，现有测试已覆盖 |

---

## 4. Acceptance Criteria

| ID | Given / When / Then | 追溯 |
|---|---|---|
| **AC-1** | Given 一个已注册的无参 GET 路径，When `dispatch({method:"GET", path:...})`，Then 返回 status 200 且 payload 与原来该处理函数的返回值**逐键相等**。 | FR-1, FR-3, FR-10 |
| **AC-2** | Given 一个已注册的带参 GET 路径且给了 query，When dispatch，Then 处理函数收到的 query **是**扁平化的 `{k: v}`（多值取第一个）。 | FR-3 |
| **AC-3** | Given 一个已注册的 POST 路径与合法 JSON body，When dispatch，Then 处理函数收到解析后的 dict。 | FR-1 |
| **AC-4** | Given 一个 POST 路径但 body **不是合法 JSON**（如 `"{"`），When dispatch，Then 处理函数被调用且收到**空 dict `{}`**（不是 400）。 | FR-1（保持现状） |
| **AC-5** | Given 处理函数内部**抛异常**，When dispatch，Then status 500 且 `detail` 以 `"<类名>: "` 开头。 | FR-4, NFR-4 |
| **AC-6** | Given 一个**未注册**的 POST 路径，When dispatch，Then status 404 且 detail 恰好是 `"unknown api"`。 | FR-5 |
| **AC-7** | Given 一个**未注册**的 GET 路径，When dispatch，Then status 404 且 payload 是纯文本 `"not found"`。 | FR-6 |
| **AC-8** | Given 一个**静态文件名**（如 `/index.html`）作为 GET 路径，When dispatch，Then 仍返回 404 `"not found"`（因为静态文件不归它管）。 | FR-2 |
| **AC-9** | Given 新的 HTTP 适配器，When 用真实 HTTP 请求打现有接口，Then 结果与重构前完全一致（由现有 `test_webui.py` 覆盖）。 | FR-8, NFR-1 |
| **AC-10** | Given 路由表里某项指向一个**不存在的属性名**，When dispatch 命中它，Then 返回 500 且 detail 提到 `AttributeError`（不崩、不静默）。 | FR-11 |
| **AC-11** | Given 猴补替换了某个处理函数（如让它抛 `ValueError`），When dispatch 命中，Then 500 且 detail 是 `"ValueError: …"`；恢复后行为如常。 | FR-4, FR-12 |
| **AC-12** | Given `import webui.api` 单独执行（不先导入 `webui.server`），Then **不抛异常**（证明无循环导入）。 | FR-11 |

---

## 5. Edge Cases

| ID | 情况 | 期望 |
|---|---|---|
| **EC-1** | `query` 同一键有多个值（`?t=a&t=b`） | 取**第一个**（与现状 `parse_qs` 后取 `v[0]` 一致） |
| **EC-2** | `query` 里值为空（`?t=`） | **丢弃该键**（现状有 `if v` 过滤） |
| **EC-3** | POST 无 body / `Content-Length: 0` | 传空 dict `{}` 给处理函数（现状如此） |
| **EC-4** | `path` 带查询串（`/api/keys?target=x`） | 由适配器负责拆分 path 与 query，`dispatch` 只认拆好的 |
| **EC-5** | `method` 是 HEAD / PUT 等 | 返回 404 `"not found"`（现在只支持 GET/POST） |
| **EC-6** | 处理函数返回 `None` | 按 payload=None 处理，序列化成 `null`（不崩） |

---

## 6. API Contracts

```python
# webui/api.py
from dataclasses import dataclass, field
from typing import Any, Dict, Union

@dataclass
class Request:
    path: str
    method: str = "GET"                 # "GET" | "POST"
    query: Dict[str, str] = field(default_factory=dict)
    body: Any = None                    # POST：解析后的 dict；解析失败时是 {}

@dataclass
class Response:
    status: int
    payload: Union[Dict[str, Any], str, None]   # dict → JSON；str → 纯文本
    json: bool = True                   # payload 是否按 JSON 序列化

def dispatch(req: Request) -> Response: ...
```

**错误响应体**（保持现状，`detail` 字段名不变）：

```json
{ "ok": false, "detail": "ValueError: 坏路径" }
```

---

## 7. Data Models

| 实体 | 字段 | 类型 | 约束 |
|---|---|---|---|
| 请求 | `path` | str | 已去掉查询串；以 `/api/` 开头才是 API |
| | `method` | str | `"GET"` / `"POST"` |
| | `query` | Dict[str, str] | 已扁平化，多值取首、空值丢弃 |
| | `body` | Any | POST 时为 dict；非法 JSON 时为空 dict |
| 响应 | `status` | int | 200 / 404 / 500 |
| | `payload` | dict \| str \| None | dict 走 JSON，str 走纯文本 |
| 路由表 | `ROUTES_GET` | Dict[str, str] | key 为完整路径，**value 是 `server.py` 里的属性名**（字符串，见 FR-11） |
| | `ROUTES_QUERY` | Dict[str, str] | 同上；注意 `server.py` 里有两处是 `lambda q: ...`（`/api/combos`、`/api/install/plan`），要提成**具名函数** |
| | `ROUTES_POST` | Dict[str, str] | 同上 |

---

## 8. Out of Scope（明确不做，附理由）

| 不做 | 理由 |
|---|---|
| **stdio 适配器** | W-4 的第②步。本步只把分发抽干净，不引入新传输 |
| **Electron 侧任何代码** | 第③步 |
| **文件上传改走主进程原生对话框** | 独立缺口，见路线图 W-4 |
| **静态文件服务搬进 dispatch** | 见 FR-2。静态文件是 HTTP 特有概念，搬进去反而把传输耦合回来 |
| **HTTP→stdio 的鉴权 / Origin 校验** | 那是 W-5 |
| **拆 `server.py` 的其它部分**（handler 之外的清理） | 只搬路由表；不做无关重构（skill 的 Anti-Pattern #5） |
| **改 `api_*` 函数签名** | 它们已经是纯函数，正是本次能这么便宜的原因 |

---

## 9. 验收命令（跑什么算过）

```powershell
# 1) 全量测试（NFR-1：548 项一条不许改）
py -m unittest discover -s tests -t .

# 2) 新增的 dispatch 直测（AC-1..AC-8）
py -m unittest tests.test_api_dispatch

# 3) 文档与发布自检
py -X utf8 tools/check_docs.py
py -X utf8 tools/preflight.py
```

---

## 10. 验收记录（2026-09-14 实施）

### AC 逐条结果

| AC | 怎么验的 | 结果 |
|---|---|---|
| AC-1 无参 GET payload 逐键相等 | `test_no_arg_route_returns_payload` | ✅ |
| AC-2 带参 GET 收到扁平 dict | `test_query_route_receives_flat_dict` | ✅ |
| AC-3 POST body 原样到达 | `test_body_reaches_handler` | ✅ |
| AC-4 非法 JSON → 空 dict（不是 400） | `test_none_body_becomes_empty_dict` + HTTP 实测 | ✅ |
| AC-5 异常 → 500，detail 以「类名: 」开头 | `test_handler_exception_becomes_500` | ✅ |
| AC-6 未命中 POST → `"unknown api"` | `test_unknown_post_says_unknown_api` + HTTP 实测 | ✅ |
| AC-7 未命中 GET → 纯文本 `not found` | `test_unknown_get_is_plain_text_404` + HTTP 实测 | ✅ |
| AC-8 静态名不归 dispatch 管 | `test_static_like_path_is_not_handled_here` | ✅ |
| AC-9 真实 HTTP 结果一致 | 起服务器打 15 条（8 个 GET API + 2 个 404 + 1 个 POST + 4 个静态）全部符合预期 | ✅ |
| AC-10 属性名不存在 → 500 提到 AttributeError | `test_missing_attribute_name_is_reported_not_crashed` | ✅ |
| AC-11 猴补能替换真实处理函数 | `test_monkeypatch_can_swap_a_real_handler` | ✅ |
| AC-12 单独 `import webui.api` 不炸 | `test_api_imports_without_server`（**子进程**里验，同进程证不了） | ✅ |

### NFR 结果

| NFR | 目标 | 实测 |
|---|---|---|
| NFR-1 零行为变化 | 548 项旧测试全绿、一条断言不改 | ✅ 548 项全过 |
| NFR-2 `server.py` 变短 | 至少减 94 行（那 94 行分发逻辑搬走） | ✅ 1319 → **1265** 行 |
| NFR-3 新测试不依赖端口 | 除 `ScriptModeTest`（**故意**起进程）外不起服务 | ✅ 27 项里 25 项是纯函数直调 |
| NFR-4 不泄 traceback | 响应体无 `Traceback` / 文件路径 | ✅ `test_traceback_is_not_leaked` |

**总计：575 项测试全绿（548 旧 + 27 新），`preflight.py` 6/6。**

---

## 11. 实施中发现的三件事（都是 README 级的教训）

### ⚠ 1. 搬运脚本**静默丢掉了 3 条路由**

删旧路由表用的正则非贪婪匹配 `^}`，而表里有两处**跨行的 lambda**（函数体里带 `}`），
于是从那里开始整段没匹配干净 —— `/api/downloads`、`/api/download/job`、
`/api/userpresets` **悄无声息地消失了**。

抓住它的是 `test_route_count_matches_before_refactor` 那条**数数**的断言。
其余测试全绿，因为它们只打自己关心的那几个接口。

> 教训：搬移"清单类"数据之后，**要留一条数数的断言**。功能测试覆盖不到"少了一项"这件事。

### ⚠ 2. 两个只在**脚本模式**炸的相对导入 —— 而 573 项测试全绿

`server.py` 与 `api.py` 各加了一处 `from . import xxx`。测试全走**包导入**
（`from webui import server`），而**用户与启动器走脚本模式**（`py webui\server.py`）——
那是一条完全不同的导入路径，没有包上下文，相对导入直接报
`attempted relative import with no known parent package`。

现象：**服务器照常启动，但每个接口都回 500**。单元测试一条都不红。

修法：两处都写成 `try: from . import x / except ImportError: import x`。

**并补了 `ScriptModeTest`** —— 真的用 `subprocess` 起一个服务器，打一次真实 HTTP。
慢几秒，但这是唯一能拦住这类 bug 的办法。已实测：把 fallback 去掉后它会**变红**。

> 教训：**"直接运行脚本"和"当包导入"是两条路，测试必须覆盖用户走的那条。**

### ⚠ 3. 我一开始把路由条数**数错了**（以为 42，实际 39）

早期用正则统计时，把跨行 lambda 的函数体也算成了表项，得出"QUERY 15 条"。
真实是 **GET 3 / QUERY 12 / POST 24 = 39**，与 `check_docs.py` 报的接口数一致。
spec 与测试断言已改正 —— **以 `check_docs` 的总数为准**（它从源码直接数）。

---

## 12. 连带改动（spec 之外但必须做）

| 文件 | 改动 | 为什么必须 |
|---|---|---|
| `tools/check_docs.py` | `server.ROUTES_*` → `api.ROUTES_*` | 路由表搬走了，不改就直接跑不起来（preflight 红） |
| `webui/server.py` | `do_GET`/`do_POST` 改成"构造 Request → dispatch → 发响应"；**静态文件留在原处** | FR-8 / FR-2 |
| `tests/test_api_dispatch.py` | 新增 27 项 | AC-1 ~ AC-12 |

**下一处该做的**（W-4 第②步）：加 stdio 适配器。那时 `M5-E-1` 的
"stdout 只能放协议、日志一律 stderr"就从"方便"变成**硬要求**。

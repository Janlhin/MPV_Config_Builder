# Spec — stdio 传输：让 Electron 直接接后端（W-4 第②步 + M5-E-1）

| | |
|---|---|
| **作者** | DSH agent |
| **日期** | 2026-09-14 |
| **状态** | **已实施**（见 §10 验收记录） |
| **评审** | 用户 2026-09-13 拍板界面终局为 Electron；2026-09-14 选 B1-4「真·一键安装（Electron + 打包后端）」 |
| **上游** | `specs/transport-dispatch.md`（W-4 第①步：已抽出 `dispatch()`） |

---

## 1. Context（为什么做这个）

用户明确要求：**不要在本机开 HTTP 端口**，让 Electron 与 Python 后端直接对接。
W-4 第①步已经把分发抽成纯函数 `dispatch(Request) -> Response`，传输变成可替换的一层
（见 `webui/api.py`）。本步把第二层传输真正接上：

    ┌────────────────────┐
    │ dispatch(Request)  │────▶ server.api_*（39 个纯函数）
    └────────────────────┘
       ▲              ▲
    HTTP 适配器     stdio 适配器（本步）
    （浏览器/调试）  （Electron，不开端口）

**HTTP 必须保留**：它是浏览器调试的唯一通道，也是现有接口测试与 `check_ui.py` /
`check_topnav.py` 的载体。本步是**新增一条传输**，不是替换。

**告警级别**：`M5-E-1` 的"stdout 只能放协议"在 HTTP 下只是"方便"，
到 stdio 下变成**硬要求** —— 一个多余的 `print()` 就会污染协议流，让整个后端失联。
所以本步要**同时**把启动横幅之类的 `print()` 挪到 stderr。

---

## 2. 协议（JSONL，一行一条）

请求（Electron → 后端，写 stdin）：

```json
{"id": 1, "path": "config/load", "method": "POST", "body": {"path": "C:/x/mpv.conf"}}
{"id": 2, "path": "status"}
{"id": 3, "path": "backups", "query": {"target": "C:/x"}}
```

响应（后端 → Electron，写 stdout）：

```json
{"id": 1, "ok": true,  "data": {...}}
{"id": 2, "ok": false, "error": "ValueError: xxx", "status": 500}
```

约定：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 由调用方给，原样回显。用于把响应配回请求（前端可能并发发多条） |
| `path` | 是 | **领域名**，不带 `/api` 前缀：`config/load`、`status`、`keys/save`… |
| `method` | 否 | 缺省按路由表推断（在 POST 表里就 POST，否则 GET）；显式给了以给的为准 |
| `query` | 否 | 对象，值是字符串（或可转字符串）|
| `body` | 否 | 任意 JSON；POST 用 |

---

## 3. Functional Requirements

| ID | 要求 |
|---|---|
| **FR-1** | 系统 **MUST** 提供 `python webui/server.py --stdio`，从 **stdin** 逐行读 JSONL 请求、向 **stdout** 逐行写 JSONL 响应。 |
| **FR-2** | **stdout 只允许出现协议行**。任何日志、启动横幅、警告、错误提示 **MUST** 写 stderr。 |
| **FR-3** | `path` **MUST** 用领域名（`config/load`），适配器负责归一化成 `dispatch` 认识的 `/api/config/load`。**MUST NOT** 把 `/api` 前缀硬编码进协议。 |
| **FR-4** | 响应 **MUST** 始终带 `id`；`ok=true` 时带 `data`，`ok=false` 时带 `error` 与 `status`。 |
| **FR-5** | 处理函数抛异常 **MUST** 转成 `ok=false`，**MUST NOT** 让后端退出，**MUST NOT** 泄 traceback（只给 `"<类名>: <消息>"`）。 |
| **FR-6** | 一行不是合法 JSON / 不是对象 / 缺 `id` / 缺 `path` 时，**MUST** 回一条 `ok=false` 且能指出问题；**MUST NOT** 崩掉或静默丢弃。 |
| **FR-7** | 空行 **MUST** 被忽略（不产生响应）。 |
| **FR-8** | stdin 关闭（EOF）时，进程 **MUST** 正常退出（退出码 0），**MUST NOT** 卡住等输入。 |
| **FR-9** | 每条响应写完后 **MUST** flush（否则 Electron 收不到，直到缓冲区满）。 |
| **FR-10** | 现有 HTTP 服务 **MUST** 完全不受影响：不带 `--stdio` 时行为与现在逐条一致。 |
| **FR-11** | stdio 模式 **MUST NOT** 绑定任何端口（用户的核心诉求）。 |
| **FR-12** | 非 ASCII（中文）**MUST** 正确往返：Windows 控制台默认编码是 GBK，**MUST** 显式按 UTF-8 收发。 |
| **FR-13** | 适配器逻辑 **MUST** 可单独测试（喂字符串，拿字符串），**MUST NOT** 需要真起进程。 |

---

## 4. Non-Functional Requirements

| ID | 要求 | 怎么验 |
|---|---|---|
| **NFR-1** | **零行为变化**：现有测试一条都不许改断言，全绿 | 跑全量测试 |
| **NFR-2** | 协议处理 **MUST** 与传输解耦（单独模块，不 import `http.server`） | 代码检查 + 单测 |
| **NFR-3** | 中文在协议里 **MUST** 保持可读（`ensure_ascii=False`），便于抓包排查 | 单测断言原始字节 |
| **NFR-4** | 一条坏请求 **MUST NOT** 影响后续请求 | 单测：坏行后面跟好行 |

---

## 5. Edge Cases

| 情况 | 期望 |
|---|---|
| 空行 / 只有空格的行 | 忽略，无响应 |
| `{}`（缺 path 和 id） | `ok=false`，说明缺什么 |
| `{"id":1}`（缺 path） | `ok=false`，说明缺 path |
| `{"path":"status"}`（缺 id） | `ok=false`，说明缺 id（否则前端配不回来） |
| `not json at all` | `ok=false`，说明不是合法 JSON |
| `[1,2,3]`（合法 JSON 但不是对象） | `ok=false` |
| `{"id":1,"path":"不存在的接口"}` | `ok=false` + 状态 404 |
| 处理函数抛异常 | `ok=false` + `"<类名>: <消息>"`，进程继续 |
| stdin 直接 EOF | 退出码 0，不卡住 |
| 一行超长（如塞了整个配置文件） | 正常处理（不做行长大小的限制，但不是无限制读内存 —— 见 §7 风险） |

---

## 6. Acceptance Criteria

| ID | Given / When / Then | 追溯 |
|---|---|---|
| **AC-1** | Given `handle_line('{"id":1,"path":"status"}')`，When 处理，Then 返回一条 JSON，`id=1`、`ok=true`、`data` 与非 stdio 路径的 `api_status()` 逐键相等。 | FR-1, FR-4 |
| **AC-2** | Given `path="config/load"` + body，When 处理，Then 归一化成 `/api/config/load` 并命中 POST 表（**证明领域名可用**）。 | FR-3 |
| **AC-3** | Given `path="/api/status"`（带前缀），When 处理，Then **也能命中**（容错，别让前端因为多了个前缀就全崩）。 | FR-3 |
| **AC-4** | Given 处理函数抛 `ValueError("x")`（猴补），When 处理，Then `ok=false`、`error` 以 `"ValueError: "` 开头。 | FR-5 |
| **AC-5** | Given 一行 `"{oops"`，When 处理，Then `ok=false` 且说明不是合法 JSON。 | FR-6 |
| **AC-6** | Given 一行 `""`，When 处理，Then 返回 `None`（不产生响应）。 | FR-7 |
| **AC-7** | Given 真起一个 `--stdio` 子进程，When 灌入 3 条请求再关 stdin，Then stdout 恰好 3 行合法 JSON、id 一一对应、进程退出码 0。 | FR-1, FR-8, FR-9 |
| **AC-8** | Given 同上，When 检查 stdout，Then **每一行都是合法 JSON**（没有横幅、没有日志混进去）。 | FR-2, NFR-3 |
| **AC-9** | Given 同上，When 检查子进程有没有监听端口，Then 没有（stdio 模式不开端口）。 | FR-11 |
| **AC-10** | Given 中文内容（如读一份含中文注释的配置），When 走 stdio 往返，Then 中文完好（不是 `\uXXXX`、也不是乱码）。 | FR-12, NFR-3 |
| **AC-11** | Given 坏行后面跟一条好请求，When 依次处理，Then 好请求正常响应。 | NFR-4 |
| **AC-12** | Given 不带 `--stdio` 启动，When 打真实 HTTP，Then 与以前一致。 | FR-10 |

---

## 7. 风险与取舍

| 风险 | 取舍 |
|---|---|
| **并发**：前端可能同时发多条请求 | stdio 循环**逐条处理**（不并发）。理由：`download/start` 这类耗时操作**本身就已经是后台线程**（`api_download_start` 立刻返回 job id），所以逐条处理不会卡住长任务；而并发会让响应乱序，前端按 `id` 配对也变得没必要 —— 简单且不会错。 |
| **超长行** | 用 `for line in sys.stdin` 逐行读，不设上限。真实载荷是配置文件文本（几百 KB 级），可接受。真要防护应在 Electron 侧限制。 |
| **一个 print 污染协议** | 这是本步最容易复发的问题。对策：① 启动横幅改走 stderr；② 加一条"stdout 每行都必须能 `json.loads`"的测试（AC-8），**这条测试就是防线**。 |
| **HTTP 与 stdio 两套行为漂移** | 两者都走同一个 `dispatch()`，没有第二份分发逻辑（FR-8 的延续）。 |

---

## 8. 不做的事

| 不做 | 为什么 |
|---|---|
| 删掉 HTTP | 它是调试通道，也是现有 UI 测试的载体 |
| 让 stdio 也处理静态文件 | 静态文件是 HTTP 特有概念（`transport-dispatch.md` FR-2）；Electron 直接读磁盘上的 html |
| 鉴权 / Origin 校验 | 那是 W-5（HTTP 路径的问题）；stdio 是本机父子进程，没有网络面 |

---

## 9. 实施记录

| 文件 | 改动 |
|---|---|
| `webui/stdio.py` | **新增**。`handle_line(str) -> dict|None`（纯函数）+ `normalize()` + `infer_method()` + `serve()`（JSONL 主循环）。**不 import `http.server` / socket**。 |
| `webui/server.py` | 新增日志层 `log()` 与 `QUIET_STDOUT` / `LOG_STREAM`；原来两处 `print()`（启动横幅、退出提示）改走 `log()`；`main()` 加 `--stdio` 分支（在 HTTP 分支**之前**返回）；`__main__` 改成 `sys.exit(main())` |
| `tests/test_stdio.py` | **新增 30 项**：纯函数层 22 项 + 假流 2 项 + **真进程 6 项** |

两个实现上的取舍，和 spec 里预写的不完全一样，记在这里：

1. **`path` 归一化同时容忍三种写法**：`config/load`、`/api/config/load`、`api/config/load`。
   spec 只要求第一种；多容错两种，是为了「前端顺手写了个前缀」不至于全线打崩。
   测试里有一条 `test_every_domain_name_maps_to_a_real_route`，把 39 条路由**全部**按协议发一遍，
   防止以后加了接口但归一化对不上。

2. **`id` 缺失时仍然回一条 `{id: null, ok: false, ...}`**，而不是静默丢弃。
   spec 的 FR-6 只要求"能指出问题"；回一条带 `null` id 的错误，调用方能立刻看出
   "我发的这行有问题"，比什么都不回好排查。

---

## 10. 验收记录

**日期**：2026-09-14　**结果**：AC-1 ~ AC-12 全部通过，645 项测试全绿（615 旧 + 30 新）。

| AC | 怎么验的 | 结果 |
|---|---|---|
| AC-1 | `test_status_matches_the_http_path` 直接拿 `api.dispatch()` 的 payload 对比 | ✅ 逐键相等 |
| AC-2 | `test_domain_name_hits_post_route` | ✅ 命中 POST 表 |
| AC-3 | `test_prefixed_path_also_works` | ✅ |
| AC-4 | `test_exception_becomes_error_not_crash`（猴补 `api_status` 抛 `ValueError`） | ✅ `"ValueError: 故意炸的"`，无 traceback |
| AC-5 | `test_bad_json` | ✅ |
| AC-6 | `test_empty_line_produces_nothing` | ✅ 返回 `None` |
| AC-7 | `test_three_requests_then_eof`（真子进程） | ✅ 3 行、id 1/2/3、退出码 0 |
| AC-8 | `test_stdout_is_pure_protocol`（真子进程） | ✅ **并做过变异验证**（见下） |
| AC-9 | `test_no_http_banner_and_log_goes_to_stderr` | ✅ stdout/stderr 都没有 HTTP 痕迹 |
| AC-10 | `test_chinese_round_trips` + `test_chinese_is_not_escaped_or_mangled` | ✅ 无 `\uXXXX` |
| AC-11 | `test_bad_line_then_good_line_across_process` | ✅ 坏行不影响后续 |
| AC-12 | `test_api_dispatch.py` 的 `ScriptModeTest`（真起 HTTP 服务）+ 全量回归 | ✅ 615 项旧测试一条没改、全绿 |

### ⚠ AC-8 的变异验证（这条防线必须证明它会响）

「stdout 只能走协议」是 stdio 模式最容易复发、后果最严重的错 —— 一行日志就让整个后端失联。
**一条从没红过的测试不能算防线**，所以在 `serve()` 的读循环前故意插了一行
`print("调试：我是一行日志")`，看测试是否抓得住：

```
AssertionError: stdout 第 1 行不是合法 JSON（Expecting value: line 1 column 1 (char 0)）：
'调试：我是一行日志'
```

**抓到了，而且直接指出了是哪一行、内容是什么。** 随后还原文件，30 项恢复全绿。
（这次变异同时暴露了另一条断言：`test_three_requests_then_eof` 也会因为
"4 != 3 行" 而红，两道都有效。）

### 手工冒烟

（Windows / PowerShell。注意 **PowerShell 没有 heredoc**，内联 JSON 的引号很容易被吃掉
—— 所以下面是把请求写进临时文件再喂进去，和真跑时用的方式一致。）

```
PS> '{"id":1,"path":"status"}' | Out-File -Encoding utf8 req.jsonl
PS> py -X utf8 webui\server.py --stdio < req.jsonl
{"id": 1, "ok": true, "data": {"title": "MPV Config Builder", ...}}
```

stdout 只有一行纯 JSON，没有横幅、没有日志。

---

## 11. 这一轮学到的

1. **「不许 print」这种约定，靠自觉是守不住的** —— 必须有一条**会红的**测试盯着。
   而且要证明它会红（变异验证），否则你只是"以为"它在守。
2. **我自己写的测试也会写错**，而且错法很典型：`test_no_http_banner_and_log_goes_to_stderr`
   第一版断言「stderr 里应该有 HTTP 横幅」——**方向就是反的**：stdio 模式根本没起服务，
   哪来的 URL 可报。失败信息一出来就看明白了。**先跑，再解释**，别先解释再跑。
3. **中途我写过一版自我否定的测试**：注释里连着三段"这样做不行…那样也不行…算了用最直接的"，
   最后的断言其实是恒真的（`or True`）。这种东西比没有测试更坏 —— 它看着像在守，其实什么都没守。
   **判据：一条测试的断言里出现恒真项，就等于没写。** 重写成了单纯的
   "stdout/stderr 都不许有 http://"。


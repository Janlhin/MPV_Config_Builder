# Spec — Electron 桌面外壳与安装器（B1-4 / M5-E 第⑤步，最后一步）

| | |
|---|---|
| **作者** | DSH agent |
| **日期** | 2026-09-14 |
| **状态** | **已实施**（见 §9 验收记录） |
| **评审** | 用户 2026-09-14 选 B1-4「真·一键安装（Electron + 打包 Python 后端）」 |
| **上游** | `specs/stdio-transport.md`（后端协议）、`specs/backend-packaging.md`（后端 exe） |

---

## 1. Context

用户的目标是「**用户机器上不需要装 Python**」，界面终局是 Electron。
前四步已经就位：后端能 `--stdio` 说话、前端能 `invoke()`、后端已打成独立 exe。
本步把它装进一个真正的桌面应用，并产出安装器。

    ┌─────────────────────────────────────────────┐
    │ MPV Config Builder.exe（Electron 外壳）      │
    │   renderer/  9 个页面（从 webui/static 同步）│
    │   preload.js 唯一的桥：__MPVCB_INVOKE__      │
    │   main.js    spawn + 按 id 配对 + 生命周期   │
    └───────────────┬─────────────────────────────┘
                    │ stdin/stdout（JSONL，**不开端口**）
    ┌───────────────▼─────────────────────────────┐
    │ MPVConfigBuilderBackend.exe（PyInstaller）   │
    │   自带 Python 解释器 —— 用户机器不需要装      │
    └─────────────────────────────────────────────┘

---

## 2. Functional Requirements

| ID | 要求 |
|---|---|
| **FR-1** | 外壳 **MUST** 用 Electron，**MUST** 用 `spawn` 起后端并走 stdio，**MUST NOT** 开任何监听端口。 |
| **FR-2** | `preload.js` **MUST** 是渲染进程唯一的能力来源，**MUST** 只暴露一个调用函数（外加一个只读状态查询）。**MUST NOT** 暴露 `ipcRenderer` / `require` / `fs` / `child_process` 本身。 |
| **FR-3** | `contextIsolation` **MUST** 为 `true`，`nodeIntegration` **MUST** 为 `false`。 |
| **FR-4** | 退出（关窗口 / 菜单退出 / 主进程被杀）时 **MUST** 杀掉后端子进程，**MUST NOT** 留孤儿进程。 |
| **FR-5** | **MUST** 单实例：第二次启动把它带到前面，**MUST NOT** 起第二个后端。 |
| **FR-6** | **MUST** 有原生菜单（文件 / 编辑 / 视图 / 帮助），且**每一项都对应真实动作**（不许放占位项）。 |
| **FR-7** | **MUST** 有应用图标（多尺寸 ico）。 |
| **FR-8** | 页面里的外链 **MUST** 用系统浏览器打开，**MUST NOT** 在应用窗口里导航走。 |
| **FR-9** | 后端崩溃时 **MUST** 让前端收到可显示的错（`{ok:false,error}`），**MUST NOT** 静默卡死。 |
| **FR-10** | 后端 stdout 上出现非 JSON 行时 **MUST** 明确报错到日志（协议被污染是 bug，不许装作没看见）。 |
| **FR-11** | **MUST** 提供 `electron-builder` 安装器（NSIS），安装包 **MUST** 含后端、`LICENSE`、`NOTICE.txt`。 |
| **FR-12** | 页面源文件 **MUST** 保持**单一来源**（`webui/static`），`electron/renderer/` 是构建期复制产物、**MUST NOT** 入库。 |

---

## 3. Non-Functional Requirements

| ID | 要求 | 怎么验 |
|---|---|---|
| **NFR-1** | 开发形态与打包形态**都要能跑** | `tools/check_electron.py` + `tools/check_electron_packaged.py` |
| **NFR-2** | 验证 **MUST** 自动化，不许靠"打开看一眼" | 两个检查脚本走 CDP |
| **NFR-3** | 现有 648 项测试 **MUST** 全绿 | 跑全量 |
| **NFR-4** | `preflight.py` **MUST** 全过 | preflight |
| **NFR-5** | 安装包体积 **MUST** 可控（预期 80–120 MB，Electron 本身 ~180 MB 解包） | 看产物 |
| **NFR-6** | 不含机器专用路径、不含密钥 | `preflight.py` 的老检查 |

---

## 4. Acceptance Criteria

| ID | Given / When / Then | 追溯 |
|---|---|---|
| **AC-1** | Given 开发形态 `electron .`，When 启动，Then 窗口出现且页面**显示出后端给的数据**（版本号 / mpv 目录）。 | FR-1 |
| **AC-2** | Given 同上，When 检查页面里的能力，Then `__MPVCB_INVOKE__` 在、`window.require` 与 `window.process` **都是 undefined**。 | FR-2, FR-3 |
| **AC-3** | Given 同上，When 直接调 `__MPVCB_INVOKE__({path:'status'})`，Then `{ok:true, data.version==='0.1.0'}`。 | FR-1 |
| **AC-4** | Given 同上，When 请求一个不存在的接口，Then `{ok:false, error:...}`（不是抛异常、不是卡住）。 | FR-9 |
| **AC-5** | Given 同上，When 依次打开 9 个页面，Then 每个都有内容且顶栏 3 个入口在。 | FR-12, U-1 |
| **AC-6** | Given 已经开着一个实例，When 再启动一次，Then 后端进程数**仍是 1**。 | FR-5 |
| **AC-7** | Given 应用正在运行，When 关掉它，Then **没有残留的后端进程**。 | FR-4 |
| **AC-8** | Given 打包形态（`release/win-unpacked`），When 启动，Then 页面从 `app.asar` 加载且**数据显示正常**。 | NFR-1 |
| **AC-9** | Given 打包产物，When 检查 `resources/`，Then `backend/`、`LICENSE`、`NOTICE.txt` 都在。 | FR-11 |
| **AC-10** | Given `npm run dist`，When 完成，Then 产出 NSIS 安装器且退出码 0。 | FR-11 |
| **AC-11** | Given 打包形态，When 请求 `options`，Then 能取到选项库（证明 `resources/backend` 里的 `data/` 可读）。 | FR-1 |
| **AC-12** | Given 源码运行，When 跑全量测试与 preflight，Then 全绿（Electron 那套不污染 Python 侧）。 | NFR-3, NFR-4 |

---

## 5. 关键决策与理由

| 决定 | 理由 |
|---|---|
| **`renderer/` 由构建脚本从 `webui/static` 复制** | 9 个页面是浏览器版与 Electron 版**共用**的。存两份副本迟早漂移 —— 而我的实机验证脚本（check_topnav / check_stdio_ui）测的是 `webui/static` 那份，于是会出现「测试全绿，发出去的却是另一套」。一致性由 `tools/check_electron.py` 检查。 |
| **CSP 用会话级 `onHeadersReceived` 注入，不往 HTML 里加 meta** | 同样的单一来源理由。而且页面从 `file://` 载入没有同源兜底，CSP 是真需要（Electron 自己也会报 Security Warning）。 |
| **`connect-src 'none'`** | 页面**不需要**发任何网络请求（后端走 IPC）。把它关死是最强的约束：万一有代码想偷偷联网，会立刻失败而不是静默成功。 |
| **验证靠 CDP 而不是"打开看一眼"** | 前四步反复吃过「看不出来的错才是真错」的亏。GUI 应用尤其如此：窗口能开 ≠ 数据通。 |
| **`--debug-port=N` 是显式开关，默认不开** | 验证需要它；但绝不能默认开一个调试端口。只绑 127.0.0.1。 |

---

## 6. 风险与「没做的事」

| 项 | 状态 |
|---|---|
| **安装器没有实际安装过** | ⚠ **诚实说明**：`npm run dist` 产出了安装器（96.8 MB），**打包形态的 unpacked 目录已完整验证**（13 项全过），但**没有真的双击安装到系统上** —— 那会改用户机器的程序目录与注册表，属于用户该自己决定的事。安装器由 electron-builder 的 NSIS 目标生成，输入是已验证过的 `win-unpacked`。 |
| **没有代码签名** | 未签名 → Windows SmartScreen 会拦一次（"更多信息 → 仍要运行"）。要消除得买证书，不在本轮范围。文档里已注明。 |
| **安装包 96.8 MB** | Electron 本身就要这么大，属于方案固有成本。 |
| **macOS / Linux** | 不做。目标用户是 Windows（README 开头就写了）。 |
| **自动更新** | 不做。没配更新服务器，做了也是摆设。 |

---

## 7. 实施记录

| 文件 | 说明 |
|---|---|
| `electron/main.js` | 主进程：spawn 后端、按 id 配对、生命周期、CSP、单实例、菜单 |
| `electron/preload.js` | 唯一的桥（contextIsolation 开着），只暴露 `__MPVCB_INVOKE__` + `__MPVCB_INFO__` |
| `electron/menu.js` | 原生菜单，每项都有真实动作 |
| `electron/scripts/sync-renderer.js` | 把 `webui/static` 复制到 `electron/renderer`（单一来源） |
| `electron/package.json` | electron-builder 配置；`npm run sync / start / dist` |
| `tools/make_icon.py` | 零依赖手写多尺寸 ico（标准库 zlib+struct，不引 Pillow） |
| `tools/check_electron.py` | 开发形态实机验证（18 项） |
| `tools/check_electron_packaged.py` | 打包形态实机验证（13 项） |
| `.gitignore` | 加 `electron/renderer/`（构建产物，不入库） |

### ⚠ 踩的坑：`tasklist /FI` 在 Python 里永远匹配不到

检查脚本里最初用
`subprocess.run(["tasklist", "/FI", "IMAGENAME eq X.exe", "/NH"])` 数后端进程。

**永远返回 0。** 原因是 Windows 的引号处理：在 cmd 里
`/FI "IMAGENAME eq X.exe"` 是**一个**参数，而 Python 用 list 传参时会拆成
`IMAGENAME` / `eq` / `X.exe` 三个 —— tasklist 不认。

现象极具迷惑性：**同一时刻后端明明活着**（IPC 调得通、`tasklist` 不带过滤器也能看到它），
只有这条检查在报"没有后端进程"。我一开始怀疑是竞态（也确实顺手加了轮询，
那部分改动本身是对的），但加了等待还是 0 —— 才回头去查查询本身。

修法：列全部进程，在 Python 里数。慢一点，但判据是真的。

> 教训：**报错和成功同时出现时，先怀疑检查本身。** 一个"永远不会成功"的断言，
> 比没有断言更糟 —— 它会让你去修根本不存在的问题（我差点去改 spawn 逻辑）。

---

## 8. 验收记录

**日期**：2026-09-14　**结果**：AC-1 ~ AC-12 全部通过。

### 开发形态 `tools/check_electron.py` —— **18 项全绿**

| 验的什么 | 结果 |
|---|---|
| electron 二进制 / 后端 exe / renderer 已同步 | ✅ |
| 窗口创建（调试端口起来） | ✅ |
| 后端进程被拉起来 | ✅ |
| 页面加载 + 渲染出内容（非白屏） | ✅ |
| 顶栏 3 个入口在（U-1 在 Electron 下同样生效） | ✅ `['🩺配置体检','⌨️快捷键','📦下载中心']` |
| **页面显示出后端给的版本号 / mpv 目录** | ✅ `v0.1.0`、含 `portable_config` |
| preload 注入 `__MPVCB_INVOKE__` | ✅ |
| `window.require` / `window.process` 都是 undefined | ✅ |
| IPC 直调 `status` → `{ok:true, version:'0.1.0'}` | ✅ |
| 不存在的接口 → `{ok:false, error:'not found'}` | ✅ |
| 9 个页面都能打开且有内容 | ✅ |
| 单实例：第二次启动后端仍是 1 个 | ✅ |
| 退出后无孤儿后端进程 | ✅ |

### 打包形态 `tools/check_electron_packaged.py` —— **13 项全绿**

| 验的什么 | 结果 |
|---|---|
| `resources/backend/`、`LICENSE`、`NOTICE.txt` 都在 | ✅ |
| 打包后的应用能启动 | ✅ |
| **页面从 `app.asar` 里加载** | ✅ `file:///…/resources/app.asar/renderer/index.html` |
| **打包形态下数据显示正常**（路径解析正确） | ✅ `v0.1.0`、mpv 目录 |
| preload / 顶栏 / contextIsolation 在打包形态下仍生效 | ✅ |
| `options` 能取到选项库（`resources/backend` 里 `data/` 可读） | ✅ `core=36 native=82` |
| 退出后无孤儿后端进程 | ✅ |

### 安装器

`npm run dist` → `electron/release/MPV Config Builder-0.1.0-Setup.exe`（**96.8 MB**），
退出码 0。**未实际安装到系统**（见 §6 的诚实说明）。

### 回归

648 项测试全绿、`preflight.py` 全过（源码侧未被 Electron 影响）。

---

## 9. 这一轮（整个 M5-E）学到的

1. **「能打开」不是判据，「数据通」才是。** 窗口白屏和后端没连上，在任务管理器里
   看起来一模一样。所以每条验证都盯着**页面上的真实数据**（版本号来自 Python）。
2. **报错与成功同时出现，先怀疑检查自己。** `tasklist /FI` 那次，我差点去改
   spawn 逻辑；实际是查询写法在 Windows 上根本不成立。
3. **同一个东西不要存两份。** 9 个页面、CSP、图标都尽量保持单一来源；
   `renderer/` 宁可每次构建复制，也不入库。两份副本的漂移是静默的。

# Spec — 打包 Python 后端为独立 exe（B1-2 / M5-E 的第④步）

| | |
|---|---|
| **作者** | DSH agent |
| **日期** | 2026-09-14 |
| **状态** | **已实施**（见 §9 验收记录） |
| **评审** | 用户 2026-09-14 选 B1-2（PyInstaller 打包后端），终局是 B1-4（Electron + 安装器） |
| **上游** | `specs/stdio-transport.md`（Electron 靠 `--stdio` 接后端） |

---

## 1. Context

用户的目标是「**用户机器上不需要装 Python**」。做法分两层：

    ① 后端：PyInstaller 打成独立 exe（本步）
    ② 外壳：Electron spawn 这个 exe，走 stdio 说话（B1-4，下一步）

本步只做 ①，但**必须为 ② 做好准备** —— 具体就是：打出来的 exe 要能
`--stdio` 正常工作，而且 **stdout 只有协议、没有别的东西**。

**这不是想当然的**：PyInstaller 的 bootloader 在启动时会做一些事
（onefile 要解压到临时目录、会打印进度，`--windowed` 会换掉标准流）。
所以本步有一条专门的验收：**打出来的 exe 走 stdio，stdout 每行仍是合法 JSON**。

---

## 2. 关键决策：onedir 还是 onefile

| | onedir | onefile |
|---|---|---|
| 启动 | 快（~0.2s） | **慢 2–5 秒**（每次都要解压到临时目录） |
| 产物 | 一个目录 | 一个 exe |
| 与 Electron 配合 | 整个目录一起打进安装包，用户看不到 | 单个文件更好塞 |
| **stdio 协议风险** | 无 | **bootloader 可能往 stdout 写解压进度** |

**选 onedir。** 理由：

1. **启动速度直接影响体验** —— 这是 Electron 每次启动都要 spawn 的后端进程，
   每次多等 2–5 秒是不可接受的；onedir 没有这个税。
2. **协议安全** —— stdio 模式下 stdout 是协议流，任何一行杂音都会让前端失联。
   onedir 不需要解压，bootloader 没有理由写 stdout。
3. 产物是给 electron-builder 打进安装包的，**用户永远看不到那堆文件**，
   「单文件好看」在这里没有价值。

> 这条与《制作与发布文档.md》里给 Tkinter 版写的 `--onefile` 不一样，
> 那份是**便携绿色版**（用户直接双击 exe），诉求不同。两处都已注明区别。

---

## 3. Functional Requirements

| ID | 要求 |
|---|---|
| **FR-1** | 系统 **MUST** 提供 `build/backend.spec`，一条 `pyinstaller build/backend.spec` 就能出包。 |
| **FR-2** | 产物 **MUST** 包含：`data/`（3 个 JSON）、`webui/static/`（9 页面 + css/js）、根目录的 `*.md`、`LICENSE`、`NOTICE.txt`。 |
| **FR-3** | 产物 exe **MUST** 支持 `--stdio`，且 **stdout 只有 JSON 协议行**（每行都能 `json.loads`）。 |
| **FR-4** | 产物 exe **MUST** 支持 `--port N` / `--no-window`（HTTP 仍留给调试）。 |
| **FR-5** | 打包后用户数据 **MUST** 仍写到 `%LOCALAPPDATA%\MPVConfigBuilder\`，**MUST NOT** 写进安装目录（W-2 的成果，打包后最容易破）。 |
| **FR-6** | 产物 **MUST NOT** 依赖用户机器上的 Python。 |
| **FR-7** | **MUST NOT** 用 `--windowed`：那会把标准流换掉，stdio 协议直接废。 |
| **FR-8** | 构建脚本 **MUST** 可重复执行（`--noconfirm --clean`），且产物目录在 `.gitignore` 里。 |

---

## 4. Non-Functional Requirements

| ID | 要求 | 怎么验 |
|---|---|---|
| **NFR-1** | `backend.spec` **MUST** 入库（spec 是构建配方，不是产物） | `git ls-files build/backend.spec` |
| **NFR-2** | 打包产物 **MUST** 能被自动验证，不用人肉点 | `tools/check_pack.py` |
| **NFR-3** | 源码运行（`py webui\server.py`）**MUST** 不受影响 | 全量测试 |
| **NFR-4** | 体积可控（预期 15–25 MB，不内嵌 Python 之外的运行时） | 打包后 `du` |

---

## 5. 风险

| 风险 | 对策 |
|---|---|
| **bootloader 污染 stdout** | 本步的 AC-3 专门测这个。真测出来有问题就改用 onedir（本来就是 onedir）+ 检查 bootloader 输出级别 |
| **`--windowed` 被误加** | spec 里显式写 `console=True`，并在文件里注释原因 |
| **打包后才失效的路径** | W-2 已经在源码模式验过 `user_data_dir()`；本步 AC-5 在**打包产物**上再验一次 |
| **`.gitignore` 的 `*.spec` 把配方也忽略了** | 要改 ignore 规则（`*.spec` 太宽）—— 否则构建配方进不了库 |
| **体积膨胀** | 显式 `excludes` 掉用不到的大库（tkinter / numpy / PIL 等） |

---

## 6. Acceptance Criteria

| ID | Given / When / Then | 追溯 |
|---|---|---|
| **AC-1** | Given `pyinstaller build/backend.spec`，When 执行，Then 产出 `dist/MPVConfigBuilderBackend/MPVConfigBuilderBackend.exe` 且退出码 0。 | FR-1 |
| **AC-2** | Given 产物 exe，When `--stdio` 灌入 3 条请求，Then 3 行响应、id 对应、退出码 0。 | FR-3 |
| **AC-3** | Given 同上，When 逐行 `json.loads(stdout)`，Then **每一行都是合法 JSON**（bootloader 没往 stdout 写东西）。 | FR-3 |
| **AC-4** | Given 产物 exe，When 请求 `guide`（读 md）与 `db/options`（读选项库），Then 拿到真实内容（证明 `data/`、`*.md` 都带上了）。 | FR-2 |
| **AC-5** | Given 产物 exe，When 问它用户数据目录，Then 是 `%LOCALAPPDATA%\MPVConfigBuilder`，**不是** exe 所在目录。 | FR-5 |
| **AC-6** | Given 产物 exe，When 在一个**没有 Python 的 PATH** 下跑，Then 正常工作。 | FR-6 |
| **AC-7** | Given 产物 exe，When 用 `--port N --no-window` 起 HTTP，Then 能打到 `/api/status`。 | FR-4 |
| **AC-8** | Given 源码运行，When 跑全量测试，Then 全绿（打包不影响源码路径）。 | NFR-3 |

---

## 7. 不做的事

| 不做 | 为什么 |
|---|---|
| Inno Setup 安装器 | B1-4 选了 electron-builder 做安装包，不再需要 Inno（两份安装器只会打架） |
| 给 Tkinter 版打包 | 用户已定：Tkinter 保留但不维护 |
| 代码签名 | 需要证书，不在本轮范围 |
| UPX 压缩 | 杀软误报率高（文档里已记） |

---

## 8. 实施记录

| 文件 | 说明 |
|---|---|
| `packaging/backend.spec` | **新增**。onedir + `console=True`；数据项由 `ROOT.glob("*.md")` 自动收集（不写死那 4 份） |
| `tools/check_pack.py` | **新增**。21 项端到端验证，跑在**打包产物**上（不是源码） |
| `.gitignore` | `*.spec` 太宽，把构建配方也吃掉了 → 加 `!packaging/*.spec` |

**为什么配方放在 `packaging/` 而不是 `build/`**：`.gitignore` 忽略了整个 `build/`
（那是 PyInstaller 的工作目录），配方放进去会被一起忽略。而**配方是源码，必须入库**。
放在 `packaging/` 就不用写更多例外规则。

**实测体积**：exe 2.2 MB / 整目录 **21.3 MB**（预期 15–25 MB，符合）。

### ⚠⚠ 踩的坑：把 `email` 放进了 `excludes`，exe 直接起不来

第一版 `excludes` 里写了 `email`、`html.parser`、`xml` —— 理由是「我们又不发邮件、
不解析 HTML，这些肯定用不到」。结果：

```
ModuleNotFoundError: No module named 'email'
[PYI-64588:ERROR] Failed to execute script 'server' due to unhandled exception!
```

**`http.server` 依赖 `email`**（解析 HTTP 头用的），而 HTTP 服务是这个程序的传输层之一。

这个 bug 的**现象特别有迷惑性**，值得记下来：
产物 exe 存在、体积正常（21.1 MB）、`data/` `static/` `*.md` `LICENSE` **全都在包里**，
`--port` 起 HTTP 也失败 —— 看起来像"打包漏了资源"，实际是**崩在 import 阶段**，
连一行输出都还没轮到打印。**光看"文件在不在"永远查不出来。**

是 `tools/check_pack.py` 抓到的，因为它要求 **exe 真的把接口打一遍**，而不是只检查文件存在。

> 教训：**排除标准库要格外小心** —— 它们之间的依赖关系不看源码是猜不出来的。
> 现在的 `excludes` 只留确认安全的：第三方大库（numpy/PIL/…）+ 纯开发工具（unittest/pdb/…）。

---

## 9. 验收记录

**日期**：2026-09-14　**结果**：AC-1 ~ AC-8 全部通过（`tools/check_pack.py` 21 项全绿）。

| AC | 怎么验的 | 结果 |
|---|---|---|
| AC-1 | `py -m PyInstaller packaging/backend.spec` | ✅ exit 0，产物在 `dist/MPVConfigBuilderBackend/` |
| AC-2 | 灌 3 条请求给真 exe | ✅ 3 行响应、id `[1,2,3]`、退出码 0 |
| AC-3 | 逐行 `json.loads(stdout)` | ✅ **0 脏行**（bootloader 没污染协议 —— 这是本 spec 最担心的风险，实测过关） |
| AC-4 | 打 `db/options` 与 `guide` | ✅ `total=813`（data/ 生效）、guide html 长度 10252（*.md 生效） |
| AC-5 | 检查 exe 目录有没有 `presets/` / `settings.json` | ✅ 没有（W-2 在冻结下仍成立） |
| AC-6 | 产物 exe 独立运行 | ✅ 全程未使用系统 Python（exe 自带解释器） |
| AC-7 | `--port N --no-window` + 真实 HTTP 打 `/api/status` | ✅ 返回真实版本号 |
| AC-8 | 源码运行全量测试 | ✅ 648 项全绿 |

**另外验了**：包内 11 个关键资源逐个存在（3 个 JSON / 3 个 static 文件 / LICENSE /
NOTICE.txt / 入门指南.md …），体积 21.3 MB 在预期区间。

---

## 10. 这一轮学到的

1. **「文件都在」不等于「能用」** —— 打包类问题的判据必须是**真的把功能跑一遍**。
   这次 exe 崩在 import，资源却一个不少；只查文件的检查会全绿放行。
2. **排除标准库要保守**。`email` / `html.parser` / `xml` 看着无关，实际被
   `http.server` 之类的基础模块依赖。宁可多打几 MB，也不要打出一个起不来的包。
3. **构建配方要入库，且别放在被忽略的目录里**。`*.spec` 这条 ignore 规则很常见，
   而它会把配方一起吃掉 —— 这次就是 `git check-ignore` 才发现的。


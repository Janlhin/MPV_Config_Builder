# AGENTS.md —— 在这个仓库里干活的规矩

> **动手前读完这一页。** 面向任何接手本仓库的人或 AI。
>
> 纪律来源：作者的《用 AI 做项目：强制工程校验方案》v1.3.1。下面是它在**本项目**的
> 落地版（工具链已按本项目实际技术栈替换：Python 标准库 + Electron，不是 TS 栈）。
> 与原文冲突时以原文为准。

## 0. 这是什么

Windows 上的 mpv 配置工具（GPL-3.0）：不播放视频，只负责把 `mpv.conf` 写对。
`core/` 是与界面无关的逻辑，`webui/` 网页界面，`electron/` 桌面外壳。
**只用 Python 标准库**（无第三方依赖）；Node 只在打包 Electron 时使用。

## 1. 三个必须记住的命令

```bat
python tools\verify.py --offline    :: 提交前全量门禁；退出码非 0 不许提交
python tools\verify.py docs         :: 只查文档数字与实测是否一致（快）
python tools\build.py version       :: 改过 core\schema.py 的 VERSION 之后
```

`verify.py help` / `build.py help` 可列出全部子命令。

本仓库的「对错」由**全套单元测试 + `verify.py` 的各项自检**判定，不靠人眼看。
所以"跑过了"必须指得出跑了什么。

### 1.1 CI 跑什么

每次 `push` / PR，CI 在 **Windows runner** 上跑 `python tools/verify.py --offline`
（配置见 `.github/workflows/verify.yml`）。两点别改错：

* **必须 Windows**：顶栏实机检查要 Edge/Chrome、Electron 检查要 `electron.exe`。
  换 Linux 上这两项会退化成「跳过」——跳过不算失败，于是少跑两层却照样绿灯，那是假通过。
* **必须 `--offline`**：外链检查验证的是上游站点可达，与代码改动无关。
  它没被豁免，只是**换时间跑**——每周日单独跑一次含联网的全量（`links` job），同样阻断。

### 1.2 提交门禁（pre-commit，每次 commit 都会跑）

`.githooks/pre-commit` 在每次 `git commit` 时跑 `verify.py precommit`——
**源码可编译 / 暂存文本文件行尾必须 LF / 脚本基线（仓库无 `.bat`/`.cmd`；`.ps1` 带 BOM + CRLF）**，秒级，
任何一项不过就不许提交。

**每个克隆都要开一次** —— `core.hooksPath` 是 Git 的**本地**配置，不会随仓库走：

```bat
git config core.hooksPath .githooks
```

没开的话钩子不会跑，而且你**不会收到任何提示**——所以接手后先确认
`git config --get core.hooksPath` 输出 `.githooks`。

⚠ 门禁里**故意不跑** `docs` 与全套单测：`verify.py docs` 单独跑实测 16 分钟未结束
（2026-10-09，原因待查，见 `TASKS.md` 遗留项）。门禁慢到几分钟，人就会用
`--no-verify` 绕过去——**慢门禁比没门禁更糟**。行为与文档的一致性仍由
`verify.py --offline` 在推送前把关。

## 2. 硬约束

违反下面任何一条都会留下**真实缺陷**，不是风格问题。

### 2.1 文档先行
任何增删改**先改文档、再改代码**。删除文档内容必须说明理由与替代。
本项目吃过"文档与代码不一致"的亏（README 说 20 个接口、实际 23）。

### 2.2 提交前必须跑 verify
`python tools\verify.py --offline` 全绿才允许提交。没跑就不要声称"改完了"。

> ⚠ 命令一律用 `python`，**不要用 `py -3`**：本机 `py -3` 退出 103
> （`No suitable Python runtime found`）—— `py.exe` 存在，但它管理的运行时列表
> 里没有可用的 3.x。文档里历史写法的 `py -3` 当作 `python` 读。

### 2.3 行尾：一律 LF
`.gitattributes` 规定 `* text=auto eol=lf`。**用 Python 脚本改文本必须写
`open(path, "w", encoding="utf-8", newline="\n")`** ——
`Path.write_text()` 在 Windows 上会把 LF 写成 CRLF，然后 `git diff` 全是行尾噪音、
`verify.py docs` 的逐字节读也会读到不一样的内容。

### 2.4 脚本基线：Pwsh-only，仓库无 `.bat`/`.cmd`；`.ps1` 带 BOM + CRLF

**2026-10-14 起，启动器由 `启动.bat` 转为 `启动.ps1`，仓库全面禁用 `.bat`/`.cmd`**
（主规范《用 AI 做项目》把「禁止 cmd/bat、统一 Pwsh 7+」列为**护栏而非调度变量**：
不得为不停机而降级到 cmd，也不得把「是否允许 cmd」列为可放宽选项）。
门禁判据：`verify.py` 的「脚本基线」项（`script_baseline_problems`，全仓库只有这一份规则）。

**`.ps1` 的编码约定与 `.bat` 时代正好相反，别把旧结论套过来**：

1. **必须带 BOM**。Windows PowerShell 5.1 读 UTF-8 无 BOM 的脚本时按系统代码页
   （936）解码，中文一律乱码；Pwsh 7 默认 UTF-8、两种都认。带 BOM 是唯一让
   5.1 / 7 都正确的写法。
2. **CRLF 仍然必须**；`.gitattributes` 只管行尾、不管 BOM。
3. 用工具改完 `.ps1` 之后必须跑 `python tools\build.py ps1`（它保证「有且只有一个
   BOM + 纯 CRLF」，模型工具写出的是 LF、无 BOM）。

用户运行方式（写进 README）：右键 `启动.ps1` →「使用 PowerShell 运行」，或终端里
`pwsh -NoProfile -File .\启动.ps1`。双击 `.ps1` 默认是用记事本打开 —— 这是 Pwsh 的
系统行为，文档里要交代清楚。

**文档化例外（Q-002，2026-10-14 用户裁决）：`.githooks/pre-commit` 保持 sh**。
这不是偏好，是工具链硬限制：Git for Windows 会把 `#!/usr/bin/env pwsh` 钩子转给
PowerShell，但 PowerShell 拒绝用 `-File` 执行**无扩展名**文件，而 git 只认固定名
`pre-commit` —— 两头夹死（实测记录见 `docs/踩过的坑.md`）。钩子本身只是 3 行
分发器（跑 `verify.py precommit`），不含任何判断规则；规则全在 verify.py（Python）
里，「规则只有一份」的纪律不受此例外影响。

### 2.5 界面文档渲染器不支持引用块内嵌表格
`core/mdrender.py` 只支持标题 / 水平线 / 列表 / 围栏代码块 / 引用 / 表格。
**表格不能放在 `>` 引用块里** —— 渲染器会把整段 join 成一行，表变成乱码。用列表代替。
另注意：非 `http(s)` 的 Markdown 链接会被**降级成纯文本**（不会 404，但也点不了）。

### 2.6 数字不要手抄
选项数 / 接口数 / 测试数一律以代码实测为准。`verify.py docs` 会判红，
但它只认自己那几条正则 —— 改了数字，**顺手核一遍相关文档**。

### 2.7 改了测试数，要同步两处
`tools/verify.py` 中 `cmd_docs` 里的**测试数白名单**（历史上出现过的数字），
以及 `README.txt` 的「单元测试（N 项）」。忘了会误报成"不一致"。

### 2.8 版本号只有一个来源
`core/schema.py` 的 `VERSION`。改完跑 `python tools\build.py version`。
`APP_VERSION` 是给**仓外归档的旧界面**留的，主界面不许显示它。

### 2.9 加冲突规则前，先找到手册原话
`core/conflicts.py` 的 17 条规则，每条注释里都标了依据属于三类
（**手册原文 / 设计原则 / 逻辑判断**）。新规则照这个格式写。
**不许凭印象加规则** —— 误报比不报更烦人。改完跑 `python tools\verify.py conflicts`。

### 2.10 不要"顺手统一"
合并/重构**只做收拢，不趁机改逻辑**。发现两个实现相似，加前缀并存，
别在一次机械重构里把它们合并。真实案例：`find_ws` 两个版本一个有诊断信息一个没有，
合并会改变报错内容 —— 而那次重构的目标只是"少几个文件"。

### 2.11 界面文案要走 i18n，不要硬编码中文

**两套机制并存，按情况选**：

1. `data-i18n` / `data-i18n-html` —— **新增整句文案用这个**，键要进 `i18n.js` 的两张表。
2. 词条表 `i18n-zh2en.js` —— **兜底**，按中文原文精确匹配替换。它同时覆盖两种
   `data-i18n` 盖不到的地方：老页面里没标记的静态文字，以及 **`state.js` 运行时生成的
   界面文字**（advanced / expert 的主体内容就是它生成的，属性方案对动态内容无解）。
   因为要兜底，**两个脚本都得加载**，顺序是 `i18n.js` 在前：
   `<script src="i18n.js"></script><script src="i18n-zh2en.js"></script>`

⚠ **词条表只收语义完整的条目**。被标签截断的半句别收 —— 各译各的拼起来语法对、意思不通，
正是「看着通顺但语义错了」那类缺陷。那种要等整句套上 `data-i18n` 再收。

`data-no-i18n` 表示「这不是文案，别翻」—— 文件名、键名、路径之类的标识符。
注意它的语义是**不翻**，所以中文会留着；`verify.py i18n` 统计残留时会跳过它。

**数字不要写进语言包**，用 `{占位符}` 引用 `i18n.js` 里的 `VARS`：
同一个数字在两份语言表里各写一遍，改的时候必然漏一处（§2.6 的老毛病）。

语言包**内嵌在 JS 里，不许改成 fetch JSON**：Electron 用 `loadFile` 从 `file://`
载入页面，`file://` 下 fetch 相对路径的 JSON 会被 CORS 挡掉。

### 2.12 写用户文件一律走 `core.textio.write_atomic`

**禁止新增 `Path.write_text()` / `Path.write_bytes()` 直接落盘**（临时文件、测试夹具除外）：

- 直接写是「先截断目标再写」—— 写一半崩溃 / 断电 / 被强杀，用户的 `mpv.conf`
  就是半截；备份文件在也救不了"原文件已毁"。
- `write_atomic` 走「同目录临时文件 → fsync → `os.replace`」，Windows 同卷成立；
  目标被 mpv / 编辑器占用时抛 `PermissionError` 并自动重试。
- 换行一律 LF（见 §2.3）；编码回退要如实告知用户（`encode_report` / `report=` 出参），
  别再出现"界面说按原编码写回、实际整篇变 UTF-8"。

## 3. 工作纪律

| 纪律 | 在本项目怎么落地 |
|---|---|
| **文档先行** | §2.1 |
| **原子化** | 一次提交只服务一个意图；重构与行为变更分成两个提交；单提交 ≤400 行（机械性变更不受限，但必须独立提交） |
| **校验后即提交** | 通过 `verify.py` 立刻 commit，不积压多轮改动 |
| **歧义必问** | 命中下列情形**停下来构造 2–4 个具体选项问对方**（每个选项写明代价、给出推荐项并排在第一位），禁止猜：需求边界不清 / 多方案取舍不同 / 不可逆操作 / 与既有约定冲突 / 缺乏判据的取舍。**能在代码或文档里读到的不算**，那种先自查 |
| **先搜后造** | 引入任何工具/依赖前先检索，并留证据（用了什么、为什么不用别的方案） |
| **按时清理** | 增量层发现即清；定期层产出独立 `chore:` 提交；**阈值层不得人为抬高标准以求"通过"** |
| **分级删除** | 白名单（本次改动新增的残留、工具确证无引用**且**被测试覆盖、注释掉的代码块）自主删除并在交付说明里列出；灰名单（用户手写代码、公共 API、无测试覆盖的模块、跨模块、一次删超 5 个文件）**先提案等确认**；用途不明 / 无法排除动态引用的一律保留并标 `TODO(verify)`。**禁止先删后报** |

## 4. 交付说明必须四项齐全

1. **改了什么** —— 文件清单 + 一句话意图，逐条对应到提交
2. **验证证据** —— 实际执行的命令与结果（通过 / 失败 / 跳过）
3. **未验证项** —— 因环境、权限、凭据或网络限制没验的部分，**不得隐去**
4. **遗留项** —— 已知问题、需人工确认、建议的下一步

提交信息用 Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`），
正文用英文写清 **why**（不是 what），并列出未验证项。

## 5. 既有约定（别推翻）

- `tools/` **只有 4 个文件**：`build.py`（生成）/ `verify.py`（验证）/
  `uidriver.py`（浏览器驱动，被实机脚本共用）/ `_dump_bindings.lua`。
  **新增验证脚本请加进 `verify.py` 的 `cmd_*` 子命令，不要新建文件。**
- `.githooks/pre-commit` 是**提交门禁的入口，不是规则的存放处**：它只负责把
  `verify.py precommit` 跑起来，判断规则全在 `verify.py` 里。改规则改那里，
  别在钩子文件里堆逻辑——否则「门禁判什么」会有两份答案。
- `electron/renderer/` 是**构建期复制产物**，不要手改 —— 要改改 `webui/static/`。
- 旧 Tkinter 界面已**移出仓库**，归档在 `..\MPV_Config_Builder_legacy\`
  （保留、能在本机跑、有自检，但**不维护**）。不要试图"修"它。
- 界面上能读的 4 份文档由 `webui/server.py` 的 `DOCS` 白名单驱动；
  增删那份清单要改那里，同时改 `tools/verify.py` 的必带文件清单。
- 传输层可替换（HTTP / stdio）：页面里**任何**直接 `fetch('/api/...')` 都会在 Electron
  下**静默失效**，全部走 `API.xxx()`（`tests/test_frontend_transport.py` 静态守着）。

## 6. 接手时先看哪里

1. [`docs/待做.md`](docs/待做.md) §〇 —— 下一步做什么、按什么顺序、为什么是这个顺序
2. [`docs/踩过的坑.md`](docs/踩过的坑.md) —— 实测出来的结论（含"这个检查抓到了什么"）
3. [`README.md`](README.md) —— 怎么跑、目录结构
4. `python tools\verify.py help` —— 有哪些验证手段

> 本文只写"怎么干活"。**"活是什么"在 `docs/待做.md`，"坑是什么"在 `docs/踩过的坑.md`** ——
> 四份文档各有单一职责，不要合并，否则校验规则无法按文件粒度生效。
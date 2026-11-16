# AGENTS.md —— 在这个仓库里干活的规矩

> **动手前读完这一页。** 面向任何接手本仓库的人或 AI。
>
> 本文件是工程规则在**本项目**的
> 落地版（工具链按本项目实际技术栈替换：Python 标准库 + Tauri（Rust 外壳），不是 TS 栈）。
> 本文件是**目录**：只写命令入口、本项目红线与规则章节，不复制规则正文。
> 与原文冲突时以原文为准；本文件更严时以本文件为准。
>
> 2026-11-07 改版：按 v1.20.0 文档上限（≤150 行）拆出三份实现细节文档——
> `docs/平台与写入约定.md`、`docs/i18n-约定.md`、`docs/既有约定.md`。
> 2026-11-17 升到 v1.23.0：补「启动层」登记、Pwsh 7.4+ 基线、根目录白名单与
> 提交信息门禁；度量看板 / 校验矩阵 / 豁免登记在 `docs/度量与门禁.md`。

## 0. 这是什么

Windows 上的 mpv 配置工具（GPL-3.0）：不播放视频，只负责把 `mpv.conf` 写对。
`core/` 与界面无关，`webui/` 网页界面，`tauri/` 桌面外壳（Rust + 系统 WebView2），
`scripts/` 放源码运行入口。**Python 侧只用标准库**（零第三方依赖）；Rust 只在外壳里用。

## 1. 四个必须记住的命令

```powershell
python tools\verify.py --offline    # 提交前全量门禁；退出码非 0 不许提交
python tools\verify.py docs         # 只查文档数字与实测是否一致（慢，推送前跑）
python tools\verify.py layout       # 根目录白名单 + README 目录声明
python tools\build.py version       # 改过 core\schema.py 的 VERSION 之后
```

`verify.py help` / `build.py help` 可列出全部子命令。命令一律用 `python`，
**不要用 `py -3`**：本机 `py -3` 退出 103（`No suitable Python runtime found`）。

### 1.1 CI 跑什么

每次 `push` / PR，CI 在 **Windows runner** 上跑 `python tools/verify.py --offline`
（`.github/workflows/verify.yml`，`shell: pwsh`）。三点别改错：
**必须 Windows**（顶栏实机检查要 Edge/Chrome，换 Linux 会退化成「跳过」= 假通过）；
**必须 `--offline`**（外链检查换时间跑：每周日 `links` job，同样阻断）；
**CI 验的是顶端提交**，不是逐提交重跑——历史里的每个提交由本地钩子负责。

### 1.2 两个本地门禁（每次 commit 都会跑）

`.githooks/pre-commit` → `verify.py precommit`：源码可编译 / 暂存文本 LF / 脚本基线 /
根目录布局 / 版本登记，秒级，一项不过就不许提交。
`.githooks/commit-msg` → `verify.py commitmsg`：首行必须 Conventional Commits
（`Merge` / `Revert` 放行）；暂存改动超 400 行只提示、不拦截。
`core.hooksPath` 是**本地**配置，每个克隆执行一次 `git config core.hooksPath .githooks`；
没开的话钩子不跑，且**收不到任何提示**。

⚠ 门禁里**故意不跑** `docs` 与全套单测：`verify.py docs` 单独跑实测 16 分钟未结束
（2026-10-09，见 `TASKS.md`）。门禁慢到几分钟，人就会用 `--no-verify` 绕过去——
**慢门禁比没门禁更糟**。一致性与单测仍由推送前的 `--offline` 把关。

### 1.3 启动层（钩子、shell）

Git 在 Windows 上由 Git for Windows 的 **`sh`** 执行钩子，而钩子文件名没有扩展名、
PowerShell 的 `-File` 又不接受无扩展名文件（Q-002 实测）。所以：
**钩子只能是 LF 的 sh 薄壳**（只做「找 python + 转发」），业务判断一律留在
`tools/verify.py`（Python）里，规则只有一份。
本项目**不用 husky、不把 npm scripts 当验收入口**——已在 `docs/度量与门禁.md`
登记豁免（补偿通道是 `.githooks` + `core.hooksPath`），到期复核。
自动化入口统一 **PowerShell 7.4+**（`$PSVersionTable` 实测低于 7.4 要升级）；
`.ps1` 基线加一条：脚本里出现原生命令失败判定时，显式设
`$PSNativeCommandUseErrorActionPreference = $false`，不让宿主默认值决定行为。
**不得以「启动层绕不过去」为由引入 `cmd` / `.bat` / `.cmd` 语法**——那是护栏，不是可放宽项。

## 2. 硬约束

违反任何一条都会留下**真实缺陷**，不是风格问题。

### 2.1 文档先行 / 2.2 校验后即提交

任何增删改**先改文档、再改代码**；删除文档内容必须说明理由与替代。
`python tools\verify.py --offline` 全绿才允许提交；没跑就不要声称「改完了」。

### 2.3 行尾：一律 LF

`.gitattributes` 规定 `* text=auto eol=lf`。**用 Python 改文本必须写
`open(path, "w", encoding="utf-8", newline="\n")`**——`Path.write_text()` 在 Windows 上
把 LF 写成 CRLF，`git diff` 全是行尾噪音、`verify.py docs` 的逐字节读也会不一致。

### 2.4 脚本基线：Pwsh-only，仓库无 `.bat`/`.cmd`

2026-10-14 起 `启动.bat` 转为 `.ps1`；2026-11-17 启动器搬到 `scripts\启动.ps1`。
仓库全面禁用 `.bat`/`.cmd`，判据是 `verify.py` 的「脚本基线」项
（`script_baseline_problems`，**全仓库只有这一份规则**）。
`.ps1` 的 BOM / CRLF 约定与「钩子保持 sh」的例外见 `docs/平台与写入约定.md` §一。
**改完 `.ps1` 必须跑 `python tools\build.py ps1`。**

### 2.5 界面文档渲染器不支持引用块内嵌表格

`core/mdrender.py` 只支持标题 / 水平线 / 列表 / 围栏代码块 / 引用 / 表格。
**表格不能放在 `>` 引用块里**（会 join 成一行变乱码）；非 `http(s)` 链接降级成纯文本。

### 2.6 数字不要手抄

选项数 / 接口数 / 测试数一律以实测为准。`verify.py docs` 会判红，但它只认自己那几条正则——
改了数字，**顺手核一遍相关文档**。

### 2.7 改了测试数，要同步两处

`tools/verify.py` 中 `cmd_docs` 的**测试数白名单**（历史上出现过的数字），
以及 `docs/README.zh-CN.md` 的「单元测试（N 项）」。忘了会误报成「不一致」。

### 2.8 版本号只有一个来源

`core/schema.py` 的 `VERSION`。改完跑 `python tools\build.py version`。
`APP_VERSION` 是给**仓外归档的旧界面**留的，主界面不许显示它。
技术栈版本登记在 `README.md` 的「Stack and runtime versions」，
版本文件 `.python-version` 必须与 CI 同源（`verify.py stack` 判）。

### 2.9 根目录白名单（v1.23.0）

根目录**只允许**：五个文档（`README.md` / `AGENTS.md` / `DECISIONS.md` / `TASKS.md` /
`MANIFEST.md`）、`LICENSE`、点文件（`.gitattributes` / `.gitignore` / `.python-version`）、
协作配置目录（`.github/` / `.githooks/`）与已声明的代码/数据目录。
**散文类文件一律进 `docs/`**；白名单外的新条目**先问再放**，并在 `DECISIONS.md` 留痕。
新增目录必须同步写进 README 的「## Layout」（那是 `verify.py layout` 的数据源）。

### 2.10 加冲突规则前，先找到手册原话

`core/conflicts.py` 的 17 条规则，每条注释都标了依据（**手册原文 / 设计原则 / 逻辑判断**）。
新规则照这个格式写。**不许凭印象加规则**——误报比不报更烦人。改完跑
`python tools\verify.py conflicts`。

### 2.11 不要「顺手统一」

合并/重构**只做收拢，不趁机改逻辑**。真实案例：`find_ws` 两个版本一个有诊断信息一个没有，
合并会改变报错内容，而那次重构的目标只是「少几个文件」。

### 2.12 界面文案要走 i18n / 写用户文件走 `write_atomic`

两节全文见 `docs/i18n-约定.md` 与 `docs/平台与写入约定.md` §二。两条要点：
新增整句文案用 `data-i18n`（词条表只收语义完整条目）；写用户文件**禁止**直接
`Path.write_text()`，一律 `core.textio.write_atomic`。

## 3. 工作纪律与度量

条款正文在工程规则，本节只留锚点：原子化、提交与交付闭环
提交闭环、歧义处理 §`ambiguity`、先搜寻后自研 §`search-first`、
冗余清理与分级删除 §`cleanup`。**能在代码或文档里读到的不算歧义**，先自查。

三处比规范更严，直接执行：
- 单提交 ≤400 行；机械性变更（重命名/格式化/依赖升级）不受限，但必须独立提交。
- 阈值层**不得人为抬高标准以求「通过」**。
- 灰名单删除（用户手写代码、公共 API、无测试覆盖、跨模块、一次删超 5 个文件）
  **先提案等确认**，禁止先删后报。

度量看板、缺陷类型 × L1–L4 校验矩阵、逐项豁免（含到期复核）见
`docs/度量与门禁.md`；豁免三条件：代码内标注 + CI 豁免清单 + 到期时间。

## 4. 交付说明四项齐全

改了什么 / 验证证据（实际执行的命令与结果）/ 未验证项（不得隐去）/ 遗留项。
末尾附一行**当前未决议清单**，没有则写「当前无待裁决项」。
提交信息用 Conventional Commits，正文写清 **why**（不是 what）。

## 5. 既有约定

`tools/` 只允许 4 个文件、门禁入口在 `.githooks`、前端只有 `webui/static` 一份
（`tauri.conf.json` 的 `frontendDist` 直接指过去，不许复制副本）、传输层必须走 `API.xxx()`
——六条结构性约束见 `docs/既有约定.md`。**改动前必读。**

## 6. 接手时先看哪里

`TASKS.md`（队列与台账：先看「未完成队列」与「被阻塞」）→ `DECISIONS.md`（为什么这么定）
→ `docs/既有约定.md`（结构性约束与实测判据）→ `README.md`（怎么跑、目录结构、技术栈版本）
→ `python tools\verify.py help`（验证手段）。

> 本文只写「怎么干活」；「活是什么」在 `TASKS.md`，「坑是什么」在 `docs/既有约定.md` 的「实测判据」。

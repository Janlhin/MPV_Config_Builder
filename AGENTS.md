# AGENTS.md —— 在这个仓库里干活的规矩

> **动手前读完这一页。** 面向任何接手本仓库的人或 AI。
>
> 本文件是工程规则在**本项目**的
> 落地版（工具链按本项目实际技术栈替换：Python 标准库 + Electron，不是 TS 栈）。
> 本文件是**目录**：只写命令入口、本项目红线与规则章节，不复制规则正文。
> 与原文冲突时以原文为准；本文件更严时以本文件为准。
>
> 2026-11-07 改版：原 212 行，按 v1.20.0 文档上限（≤150 行）拆出三份实现细节文档——
> `docs/平台与写入约定.md`（`.ps1` 编码、原子写）、`docs/i18n-约定.md`（两套文案机制）、
> `docs/既有约定.md`（不要推翻的结构性约束）。规则效力不变，位置变了。

## 0. 这是什么

Windows 上的 mpv 配置工具（GPL-3.0）：不播放视频，只负责把 `mpv.conf` 写对。
`core/` 是与界面无关的逻辑，`webui/` 网页界面，`electron/` 桌面外壳。
**只用 Python 标准库**（无第三方依赖）；Node 只在打包 Electron 时使用。

## 1. 三个必须记住的命令

```powershell
python tools\verify.py --offline    # 提交前全量门禁；退出码非 0 不许提交
python tools\verify.py docs         # 只查文档数字与实测是否一致（快）
python tools\build.py version       # 改过 core\schema.py 的 VERSION 之后
```

`verify.py help` / `build.py help` 可列出全部子命令。

本仓库的「对错」由**全套单元测试 + `verify.py` 的各项自检**判定，不靠人眼看——所以「跑过了」必须指得出跑了什么。

> ⚠ 命令一律用 `python`，**不要用 `py -3`**：本机 `py -3` 退出 103
> （`No suitable Python runtime found`）。文档里历史写法的 `py -3` 当作 `python` 读。

### 1.1 CI 跑什么

每次 `push` / PR，CI 在 **Windows runner** 上跑 `python tools/verify.py --offline`
（`.github/workflows/verify.yml`，`shell: pwsh`）。三点别改错：

* **必须 Windows**：顶栏实机检查要 Edge/Chrome、Electron 检查要 `electron.exe`。换 Linux 上
  这两项会退化成「跳过」——跳过不算失败，于是少跑两层却照样绿灯，那是假通过。
* **必须 `--offline`**：外链检查验证的是上游站点可达，与代码改动无关。它没被豁免，只是
  **换时间跑**——每周日单独跑一次含联网的全量（`links` job），同样阻断。

### 1.2 提交门禁（pre-commit，每次 commit 都会跑）

`.githooks/pre-commit` 跑 `verify.py precommit`：**源码可编译 / 暂存文本文件行尾必须 LF /
脚本基线（无 `.bat`/`.cmd`；`.ps1` 带 BOM + CRLF）**，秒级，任何一项不过就不许提交。
`core.hooksPath` 是**本地**配置、不随仓库走，每个克隆都要执行一次
`git config core.hooksPath .githooks`——没开的话钩子不会跑，且**收不到任何提示**。

⚠ 门禁里**故意不跑** `docs` 与全套单测：`verify.py docs` 单独跑实测 16 分钟未结束
（2026-10-09，原因待查，见 `TASKS.md`）。门禁慢到几分钟，人就会用 `--no-verify` 绕过去——
**慢门禁比没门禁更糟**。行为与文档的一致性仍由 `verify.py --offline` 在推送前把关。

## 2. 硬约束

违反下面任何一条都会留下**真实缺陷**，不是风格问题。

### 2.1 文档先行 / 2.2 校验后即提交

任何增删改**先改文档、再改代码**；删除文档内容必须说明理由与替代。
本项目吃过「文档与代码不一致」的亏（README 说 20 个接口、实际 23）。
`python tools\verify.py --offline` 全绿才允许提交；没跑就不要声称「改完了」。

### 2.3 行尾：一律 LF

`.gitattributes` 规定 `* text=auto eol=lf`。**用 Python 脚本改文本必须写
`open(path, "w", encoding="utf-8", newline="\n")`** —— `Path.write_text()` 在 Windows 上会把
LF 写成 CRLF，然后 `git diff` 全是行尾噪音、`verify.py docs` 的逐字节读也会读到不一样的内容。

### 2.4 脚本基线：Pwsh-only，仓库无 `.bat`/`.cmd`

2026-10-14 起启动器由 `启动.bat` 转为 `启动.ps1`，仓库全面禁用 `.bat`/`.cmd`。
工程规则把「禁止 cmd/bat、统一 Pwsh 7+」列为**护栏而非调度变量**：不得为不停机而降级到 cmd，
也不得把「是否允许 cmd」列为可放宽选项。门禁判据是 `verify.py` 的「脚本基线」项
（`script_baseline_problems`，**全仓库只有这一份规则** —— 不要再写一个 PowerShell 版检查器，
那会让同一条规则有两个真相源）。

`.ps1` 的 BOM / CRLF 约定与「钩子保持 sh」的例外（Q-002 裁决）见
`docs/平台与写入约定.md` §一。**改完 `.ps1` 必须跑 `python tools\build.py ps1`。**

### 2.5 界面文档渲染器不支持引用块内嵌表格

`core/mdrender.py` 只支持标题 / 水平线 / 列表 / 围栏代码块 / 引用 / 表格。**表格不能放在 `>` 引用块里**
（渲染器把整段 join 成一行，表变成乱码，用列表代替）；非 `http(s)` 的 Markdown 链接会被降级成纯文本。

### 2.6 数字不要手抄

选项数 / 接口数 / 测试数一律以代码实测为准。`verify.py docs` 会判红，
但它只认自己那几条正则 —— 改了数字，**顺手核一遍相关文档**。

### 2.7 改了测试数，要同步两处

`tools/verify.py` 中 `cmd_docs` 里的**测试数白名单**（历史上出现过的数字），
以及 `README.txt` 的「单元测试（N 项）」。忘了会误报成「不一致」。

### 2.8 版本号只有一个来源

`core/schema.py` 的 `VERSION`。改完跑 `python tools\build.py version`。
`APP_VERSION` 是给**仓外归档的旧界面**留的，主界面不许显示它。

### 2.9 加冲突规则前，先找到手册原话

`core/conflicts.py` 的 17 条规则，每条注释里都标了依据属于三类
（**手册原文 / 设计原则 / 逻辑判断**）。新规则照这个格式写。
**不许凭印象加规则** —— 误报比不报更烦人。改完跑 `python tools\verify.py conflicts`。

### 2.10 不要「顺手统一」

合并/重构**只做收拢，不趁机改逻辑**。发现两个实现相似，加前缀并存，
别在一次机械重构里把它们合并。真实案例：`find_ws` 两个版本一个有诊断信息一个没有，
合并会改变报错内容 —— 而那次重构的目标只是「少几个文件」。

### 2.11 界面文案要走 i18n / 2.12 写用户文件走 `write_atomic`

两节全文见 `docs/i18n-约定.md` 与 `docs/平台与写入约定.md` §二。两条要点：
新增整句文案用 `data-i18n`（词条表只收语义完整的条目）；写用户文件**禁止**直接
`Path.write_text()`，一律 `core.textio.write_atomic`。

## 3. 工作纪律

条款正文在工程规则，本节只留锚点：原子化、提交与交付闭环、
歧义处理 §`ambiguity`、先搜寻后自研 §`search-first`、冗余清理与分级删除 §`cleanup`。
**「能在代码或文档里读到的不算歧义」**，那种先自查。

三处比规范更严，直接执行：

- 单提交 ≤400 行；机械性变更（重命名/格式化/依赖升级）不受限，但必须独立提交。
- 阈值层**不得人为抬高标准以求「通过」**。
- 灰名单删除（用户手写代码、公共 API、无测试覆盖、跨模块、一次删超 5 个文件）
  **先提案等确认**，禁止先删后报。

## 4. 交付说明四项齐全

改了什么 / 验证证据（实际执行的命令与结果）/ 未验证项（不得隐去）/ 遗留项。
末尾附一行**当前未决议清单**，没有则写「当前无待裁决项」。
提交信息用 Conventional Commits，正文写清 **why**（不是 what）。

## 5. 既有约定

`tools/` 只允许 4 个文件、门禁入口在 `.githooks`、`electron/renderer/` 是构建产物、
传输层必须走 `API.xxx()` —— 六条结构性约束见 `docs/既有约定.md`。**改动前必读。**

## 6. 接手时先看哪里

`docs/待做.md` §〇（下一步做什么、按什么顺序）→ `docs/踩过的坑.md`（实测结论）→
`README.md`（怎么跑、目录结构）→ `python tools\verify.py help`（有哪些验证手段）。

> 本文只写「怎么干活」；「活是什么」在 `docs/待做.md`，「坑是什么」在 `docs/踩过的坑.md`。

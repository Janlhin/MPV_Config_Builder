# AGENTS.md — 本仓库的 AI 协作入口

> 这是**目录**，不是手册：只放入口、红线、约定与链接；实现细节在 `docs/`，按链接到达。
> 行数上限 **150 行**；超限即视为把正文搬进来，必须拆到 `docs/` 再改为链接。
> 2026-11-25：规则改为自持；补门禁机制、验证证据、反应式自查与版本策略四节。

## 0. 这是什么

Windows 上的 mpv 配置工具（GPL-3.0）：不播放视频，只负责把 `mpv.conf` 写对。
`core/` 与界面无关，`webui/` 网页界面，`tauri/` 桌面外壳（Rust + 系统 WebView2），
`scripts/` 放源码运行入口。**Python 侧只用标准库**（零第三方依赖）；Rust 只在外壳里用。

## 1. 强制命令入口

| 用途 | 命令 | 期望 |
|---|---|---|
| 提交前全量门禁 | `python tools\verify.py --offline` | 退出码 0 |
| 文档数字与实测一致 | `python tools\verify.py docs` | 退出码 0（推送前跑，不进 precommit） |
| 根目录白名单 + README 目录声明 | `python tools\verify.py layout` | 退出码 0 |
| 版本同源 | `python tools\verify.py stack` | 退出码 0 |
| 单测 | `python -m unittest discover -s tests -t .` | 退出码 0 |
| 版本文件同步 | `python tools\build.py version` | 改过 `core/schema.py` 的 `VERSION` 后跑 |

`verify.py help` / `build.py help` 可列出全部子命令。命令一律用 `python`，**不要用 `py -3`**
（本机 `py -3` 退出 103）。CI 在 **Windows runner** 跑 `verify.py --offline`
（`.github/workflows/verify.yml`，`shell: pwsh`）：必须 Windows（实机检查在 Linux 会退化成
「跳过」= 假通过）；必须 `--offline`（外链每周日单独 job，同样阻断）；CI 验顶端提交，
历史提交由本地钩子负责。

两个本地门禁：`.githooks/pre-commit` → `verify.py precommit`；`.githooks/commit-msg` →
`verify.py commitmsg`。`core.hooksPath` 是本地配置，每个克隆执行一次
`git config core.hooksPath .githooks`；不开则钩子静默不跑。慢检查（`docs`、全量单测）
留在推送前——门禁慢到几分钟，人就会用 `--no-verify` 绕过去。

启动层：Git 在 Windows 上用 **`sh`** 执行钩子，钩子只能是 LF 薄壳（找 python + 转发），
业务判断全在 `verify.py`。本项目**不用 husky / npm 验收入口**（已在 `docs/engineering/quality.md`
登记豁免）。自动化入口统一 **PowerShell 7.4+**；`.ps1` 的原生失败判定显式设
`$PSNativeCommandUseErrorActionPreference = $false`。**不得以「启动层绕不过去」引入
`cmd` / `.bat` / `.cmd` 语法。**

## 2. 红线（违反即回滚）

- **文档先行**：任何增删改先改文档、再改代码；删除文档内容必须说明理由与替代。
- **校验后提交**：`verify.py --offline` 全绿才允许提交；禁止 `--no-verify`、注释测试、抬阈值求通过。
- **原子化**：一次提交只服务一个意图；单提交 ≤400 行，机械性变更（重命名/格式化/依赖升级）
  不受限但必须独立提交。
- **行尾一律 LF**：用 Python 改文本必须 `open(..., newline="\n")`；`Path.write_text()`
  在 Windows 会写 CRLF。
- **脚本基线**：仓库无 `.bat` / `.cmd`；`.ps1` 为 UTF-8 带 BOM + CRLF；改完跑 `build.py ps1`。
- **根目录白名单**：只允许标准根文档（`README` / `AGENTS` / `CONTRIBUTING` /
  `SECURITY` / `CHANGELOG`）与三个封存指针（`DECISIONS` / `TASKS` / `MANIFEST`）、
  `LICENSE`、点文件、`.github/` / `.githooks/` 与已声明目录；散文一律进 `docs/`；
  新目录必须同步写进 README 的 `## Layout`（`verify.py layout` 的数据源）。
- **版本只有一个来源**：`core/schema.py` 的 `VERSION`；改完跑 `build.py version`；
  `.python-version` 与 CI 同源（`verify.py stack` 判）；`APP_VERSION` 只给仓外旧界面，
  主界面不许显示。
- **数字不手抄**：选项数 / 接口数 / 测试数一律实测；改测试数要同步 `verify.py` 的
  测试数白名单与 `docs/user/zh-CN/README.md`。
- **界面文案走 i18n**；写用户文件走 `core.textio.write_atomic`，禁止直接 `Path.write_text()`。
- **界面文档渲染器只支持**标题 / 水平线 / 列表 / 围栏代码块 / 引用 / 表格；**表格不能放进 `>` 引用块**
  （会 join 成一行变乱码）；非 `http(s)` 链接降级为纯文本。
- **冲突规则要有依据**：`core/conflicts.py` 每条注释标「手册原文 / 设计原则 / 逻辑判断」，
  不许凭印象加；改完跑 `verify.py conflicts`。
- **不要「顺手统一」**：合并/重构只做收拢，不趁机改逻辑。
- **删除分级**：白名单（自己新增的残留、注释代码、有测试覆盖的废弃）自主删并列账；
  灰名单（用户手写、公共 API、无测试、跨模块、一次删 >5 文件）先提案等确认；
  黑名单（用途不明、可能动态引用、`.git` 历史）保留并标 `TODO(verify)`。**禁止先删后报。**
- **不新增运行时依赖**：引入前按「先搜寻后自研」检索并留痕（见 §3）。

## 3. 工作纪律

- **歧义必须问**：需求边界不清、多方案取舍不同、不可逆操作、涉及外部资源、与既有约定冲突、
  根目录新增文件/目录——命中任一先问，给 2–4 个具体选项 + 推荐项，等答复。
  能在代码或文档里查到的**不算歧义**，先自查。
- **先搜寻，后自研**：标准库 → 已有依赖 → 包注册表 → 代码托管平台 → 现成工具 →
  借鉴后重写 → 完全自研，不得跳级；走到最后一步要写「检索过什么、为什么不用」。
- **清理三层触发**：增量（本次改动产生的残留随提交清）、定期（两周一次）、阈值（超规模即立项）；
  过期文档、投机抽象、空转包装层、重复实现，清理独立成 `chore:` 提交。

## 4. 门禁机制三条约束

1. **机械判定与推理判定分层**：确定性检查交脚本（有退出码），语义判断交评审；
   不得用「我看过了」替代机械检查，也不得用脚本结论冒充语义正确。
2. **警告与阻断分离**：警告不得显示为通过，阻断不得降级为警告；代码级豁免必须三条件——
   代码内标注 `verify-exempt: <理由> ref:<issue>`、CI 豁免清单、到期时间；流程级豁免
   （工具/通道未接入）登记在 `docs/engineering/quality.md`，带到期复核。
3. **防死循环**：门禁不检查自己产生的文件；修复建议不得递归触发自身；超时与重试有上限。

## 5. 验证证据四个条件

- **本次产生**：不是上次的、也不是别人（含子 agent）报告里的结论。
- **命令可复现**：给出命令原文与退出码。
- **输出支持结论**：跑过了不等于结论成立，输出要能对上断言。
- **不确定即标注**：未执行、跳过、只验证一半，写「未验证」及原因，不得隐去。

## 6. 反应式自查（三类对象）

- **生产代码**：写前查同类实现与接口形状；写后查契约、边界与失败路径；评审时对照本文。
- **测试**：每个测试自证存在价值；mock 只在系统边界；断言不得与被测实现同源（假通过）。
- **文档**：文档是一组可核查的断言；代码与文档冲突时以代码为真相，随后改文档并留痕。

## 7. 版本与依赖策略

- **选新**：默认当前受支持的最新稳定版；预览版须先过准入（有回归与兼容证据）。
- **锁定**：`.python-version`、`Cargo.lock`、`tauri/Cargo.toml`、README 技术栈表；CI 与本地同源。
- **升级前五个动作**：读变更说明 → 查已知回归 → 独立 `chore(deps):` 提交 → 跑 `verify` 全链
  → 跨主版本写入 `docs/adr/`。禁止裸 `latest`，禁止「先升到最新试试」。

## 8. 交付说明四项

改了什么（文件 + 意图，对应提交）/ 验证证据（命令原文 + 退出码）/ 未验证项（不得隐去）/
遗留项。末尾附一行**当前待裁决项**，没有则写「当前无待裁决项」。
提交信息用 Conventional Commits，正文写 **why** 而不是 what。

## 9. 文档地图

- `README.md` —— 是什么、怎么跑、目录结构、技术栈版本、验收标准
- `docs/README.md` —— 文档总索引（四层：user / engineering / adr / compliance）
- `docs/engineering/architecture.md` —— 运行时形状、边界、已登记偏差
- `docs/engineering/quality.md` —— 当前门禁、基线、豁免与到期复核
- `docs/engineering/constraints.md` —— 结构约束
- `docs/engineering/pitfalls.md` —— 实测判据（原「踩过的坑」）
- `docs/engineering/platform.md` —— `.ps1` BOM/CRLF、钩子保持 sh、`write_atomic`
- `docs/engineering/i18n.md` —— `data-i18n` 与词典兜底两套机制
- `docs/engineering/release.md` —— 打包链路与发布检查
- `docs/adr/` —— 一条决策一个文件；旧决策冻结在 `docs/_archive/legacy-governance-2026-11-25/`
- `docs/compliance/` —— 第三方来源登记 + `SHA256SUMS`
- `docs/user/{zh-CN,en}/` —— 界面能读的四份产品文档（中英分目录）

## 10. 待裁决

见 GitHub Issues 与 `docs/_archive/legacy-governance-2026-11-25/TASKS.md`（历史队列）。
执行中撞到新歧义，按 §3 登记，不猜。

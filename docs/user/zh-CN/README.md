# MPV Config Builder

[English](../../../README.md) · **中文说明**（本页） · 打包与发布详版见 [release.md](../../engineering/release.md)

**把 mpv 的 813 个选项摊开给你调，还告诉你哪个和哪个打架。**

一个 Windows 上的 mpv 配置工具：不播放视频，只负责把 `mpv.conf` 写对。
勾选项 → 实时预览 → 生成配置，写前自动备份，随时可撤。

界面默认跟随系统语言：中文系统显示中文，其它系统显示英文（目前只有中英两套）。
顶栏可以随时切换；切过一次之后，就以你的选择为准。

> 面向的是 **mpv-lazy**（[mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit)）用户 ——
> 已经有懒人包了，缺的是「我想改点东西，但不知道改哪个」。
>
> **原版 mpv 也能用** —— 指向任意配置目录即可。mpv-lazy 用户体验最完整：
> 组合依赖的 shader 包懒人包里都带（依赖项会在界面里标出）。

---

## 它解决什么

现有的 mpv 配置工具都是「挑几十个常见选项给你调」。这个不一样：

| | 常见的一键配置工具 | 本项目 |
|---|---|---|
| 覆盖的选项 | 几十个（同类工具最多 74 个） | **813 个**（全量库） |
| 冲突检测 | 没有 | **17 条规则**，每条注明手册原文 |
| 选项说明 | 没有或靠联网查 | **715 条中文说明**内嵌（原始 727 条，12 条随命令行专用项滤除） |
| 会不会写出已废弃的选项 | 会 | 读取时**滤掉** 16 条命令行专用项，并标出 deprecated |

## 怎么用

### 桌面版（Tauri 外壳）

**Releases 里目前没有已签名的安装包。** 2026-11-16 桌面外壳从 Electron 换成 Tauri
（`3.0.0-alpha.6`）；Tauri 侧的打包已经配置好，但当前产物未签名，也还没有发布到
Releases。想要窗口形态就自己编一份：

```powershell
cd tauri\src-tauri
cargo build
.\target\debug\mpv-config-builder.exe
```

要生成安装包，在 `tauri\` 下运行 `cargo tauri build`。详细步骤与后续打包计划见
[release.md](../../engineering/release.md)。

需要 Rust 工具链 + WebView2（Win10/11 自带）。

### 从源码跑（需要 Python 3.13，只用标准库，不用 `pip install`）

在项目根目录**右键 `scripts\启动.ps1` →「使用 PowerShell 运行」**，或在终端里：

```powershell
pwsh -NoProfile -File .\scripts\启动.ps1
```

它会起一个本地服务并自动打开浏览器。也可以手动：

```powershell
python webui\server.py
```

> 执行策略提示：若「使用 PowerShell 运行」被策略拦截，以当前用户跑一次
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 即可（只放行本机脚本）。
> 双击 `.ps1` 默认是用记事本打开 —— 这是 Windows 的系统行为，请用右键或终端。

四档模式：**基础**（4 问向导）→ **进阶**（常用参数 + Shader 链 + 补帧）→
**完全体**（813 项全量搜索）→ **地狱**（裸写文本框，不给护栏但写前仍备份）。

另外还有**配置体检**：拖入一份 mpv.conf，报告编码 / include 链 / profile /
未知项 / 重复项 / 冲突 / 六维评分。

> 旧的 Tkinter 界面已**移出仓库**（2026-10-09），归档在仓库旁边
> `..\MPV_Config_Builder_legacy\` —— 保留但不维护，那份归档里有 `自检.py` 可以当场
> 证明它还能跑。仓库里那份已删，git 历史里还留着。

## 功能

- **四档模式**，从「只想能看片」到「我要调 shader 链」
- **配置体检**：17 条冲突规则 + 六维评分 + 逐行 diff
- **字幕实时预览**：调 `sub-font` / `sub-color` / `sub-border-*` 时立刻看到效果
- **Shader 链编排**：按本机实际存在的文件解析，自动判断顺序
- **多脚本融合**：把反交错 + 降噪 + 超分 + 补帧合成一个 `.vpy`
- **一键装 mpv-lazy**：从官方 release 取最新版，自动**选对包**（完整包 vs 无 VapourSynth 的精简包）、逐卷下载、校验、解压
- **下载中心**：脚本 / 字体 / 整包（如 uosc）一键装，装过什么能看能卸
- **uosc 设置编辑器**：`script-opts/uosc.conf` 的 74 个已知键分 9 类可视化编辑，注释与不认识的键原样保留，写前备份
- **配置无损写回**：认得出 UTF-8 / GBK / Big5，按**原编码**写回，只动全局区不碰 `[profile]` 小节
- **你自己的预设**：存下来、导出、发给别人（存在 `%LOCALAPPDATA%`，不进安装目录）
- **快捷键编辑**：改的是你自己的 `input-user.conf`，mpv-lazy 自带的那个文件一个字节都不动
- **全站搜索（Ctrl+K）**：配置项 / uosc 设置 / 键位 / 脚本一次搜完，按来源分组，点一下复制键名
- **我的分组**：拖参数行首的 ⠿ 到「常用 / 画质 / 性能 / 字幕」，归属记进设置文件（只影响归类显示，不改写盘顺序）
- **写后 10 秒撤销**：保存配置后弹一条撤销条，点一下按刚生成的备份回滚；鼠标停在条上时倒计时会暂停

## 为什么值得信任它改你的配置

这个工具动的是你的文件，所以规矩写在代码里也写在测试里：

- **写前必备份**，文件名带时间戳
- **落盘是原子的**：同目录临时文件 + `os.replace`，断电/强杀也不会留下半截配置
- **取消勾选 ≠ 删除**：只是注释掉，原文件里那行还在
- **只动全局区**：`[profile]` 小节里的同名键一律不碰
- **按原编码写回**：不会把 GBK 的配置偷偷改成 UTF-8
- **不覆盖已有安装**：一键装 mpv-lazy 时，目标已有 `portable_config` 就拒绝
- **用户改过的不删**：卸载时逐个文件核对哈希，你编辑过的会保留并告诉你

## 跑测试

```powershell
python -m unittest discover -s tests -t .
python -X utf8 tools\verify.py          # 发布前自检
```

`verify.py` 一次跑完：单元测试、源码可编译、文档数字与实测一致、发行必带文件、
许可文件内容、无机器专用路径、下载清单链接可访问、顶栏常驻入口（真浏览器）、
Tauri 外壳（实机那半要 `cargo build` 出 exe 才跑）。

界面相关的实机验证（需要本机有 Edge/Chrome，脚本会自己起后端）：

```powershell
python tools\verify.py topnav     # 9 个页面的顶栏入口
python tools\verify.py stdio      # 9 个页面跑在 stdio 通道上
python tools\verify.py tauri      # Tauri 外壳（静态 18 项；实机要 exe）
```

每次 `push` 与 PR 都会在 CI 上跑一遍上面的自检，配置在
[`.github/workflows/verify.yml`](../../../.github/workflows/verify.yml)。
runner 是 Windows —— 顶栏实机检查要 Edge/Chrome、Tauri 检查要 `cargo build` 出的 exe，
换 Linux 上这两项会退化成「跳过」，绿灯就成了假的。
外链可达性不与代码提交绑定，改为每周日单独跑一次。

## 路线图：UI/UX 升级与架构重建

> **状态：提案，尚未落地。** 当前 0.x 仍是 Tauri 3 外壳 + Python 3.13 标准库后端
> + 9 个静态页面。下面写的是方向，不是已完成功能。

### UI/UX：从九个页面到一个工作台（下一步）

九个页面功能是齐的，但「页面思维」太重：想改一项，得先知道它归哪一页。下一版
准备换成一个**信号路径工作台**，可点击原型在
[`webui/prototypes/MPV配置工作台原型.html`](../../../webui/prototypes/MPV配置工作台原型.html)。

- 导航按 mpv 真实的处理顺序：**解码 → 缩放 → Shader → 同步 → 音频 → 字幕 →
  性能**，不按功能清单排。
- 同一张工作台，**三档深度**（概览 / 调校 / 全量）与**两档密度**；深度只决定
  「露多少」，不决定「能不能」。
- 右侧常驻**监视器**：配置 / 差异 / 体检 / 写入；`Ctrl+K` 命令面板搜选项、分段
  和动作。
- 每次改动都有**改动胶片**和退路；写入前把目标、diff、改动数、备份路径摆在一起。
- 动效只解释状态变化；尊重 `prefers-reduced-motion`。

原型可点击，但用的是示例数据，写入只做模拟。要通过下面这些闸门才替换旧界面：

1. 方向先被接受：信号路径导航、三档深度、监视器，不看教程也能明白。
2. 做一张**功能对照表**，覆盖九个页面的全部功能；快捷键、下载中心、体检、
   uosc、地狱模式都不能悄悄丢。
3. 做**数据适配层**接现有 API；新界面和旧页面可以按路由共存。
4. 一次切一个面，旧页面保留一个完整发布周期做回退。
5. 只在对齐、键盘可达、写入安全都验证通过后，才删旧页面。

**不做的目标**：只换皮的「九个页面美化」，或砍成几个开关的「傻瓜版」。简化的是
路径，不是能力；813 项深度必须还在。

### 架构：分阶段重建，不做一次性大爆炸（后置、有闸门）

**现状**：Python 3.13（仅标准库）负责 `core/` 与 HTTP/stdio 传输；Tauri 外壳是
Rust；前端是静态文件。Rust 后端迁移（T17）**已封存**——没有 Rust 后端 crate，
也没有在推进；结论与封存记录见
[`docs/_archive/legacy-governance-2026-11-25/DECISIONS.md`](../../_archive/legacy-governance-2026-11-25/DECISIONS.md)。若解封，按
已定的 B 档：保留 API 契约，把 `core/` + 传输换 Rust，迁移期用 Python 当 oracle。

1. **Spike**：搬一条竖切片（解析 → 计算 → 返回 JSON）。JSON 输出、单二进制体积、
   冷启动三项都要和 Python 版对得上；一项不达标就停，不投入第二期。
2. **按模块搬**：先纯计算，再解析 / 生成，再网络 / 安装 / 硬件；每组带 Python
   生成的 golden 夹具，现有测试继续当外层门禁。
3. **切默认**：现有 HTTP 与 stdio 接口在 Rust 后端全绿后，Rust 设为默认；Python
   后端保留一个版本做回滚。
4. **打包**：把 Rust sidecar 放进 Tauri bundle；在一台没装 Python 的机器上实装
   验证。
5. **清理**：回滚窗口和安装器检查都过了，才删 Python；打包、CI、文档同一次提交
   改口径。

这**不是**回到 Electron、Node.js 或 React SPA；目标仍是原生 WebView2 桌面工具。
打包、原生菜单、单实例锁、标题栏行为另账跟踪，本计划不顺手扩大范围。

**本轮重建不做**：macOS / Linux 版、自动更新、买代码签名证书、全盘扫描 shader；
要做必须先有新决定。

## 目录结构

```
core/          与界面无关的逻辑（29 个模块）
webui/         网页界面
  server.py      本地服务 + JSON API（48 个接口，只用标准库）
               加 --stdio 就不开端口，改用一行一条 JSON 的协议（给 Tauri 外壳用）
  api.py         与传输无关的分发层（HTTP 与 stdio 共用）
  stdio.py       stdio 传输：stdout 只走协议，日志一律 stderr
  static/        9 个页面
tauri/         Tauri 桌面外壳（Rust + 系统 WebView2；安装包暂未出，见打包文档）
  src-tauri/     Rust 侧：spawn 后端走 stdio、注入同名 __MPVCB_INVOKE__、
                 直接加载 webui/static（不复制第二份）；cargo build 后跑 exe
packaging/     PyInstaller 配方（把后端打成独立 exe）
scripts/       源码运行入口（`启动.ps1`，唯一的启动器）
tests/         单元测试
tools/         build.py（生成）/ verify.py（验证）/ translate_docs.py（翻译）/
               gen_compliance.py（哈希台账）/ uidriver.py（浏览器驱动共用）
.github/       CI：push / PR 在 Windows runner 上跑一遍发布前自检
docs/          文档树：user/{zh-CN,en}/ + engineering/ + adr/ + compliance/ + _archive/
data/          内置数据（选项库 / 键位 / 命令 / mpv 原始输出）
```

仓库根目录只放标准件（`README.md` / `AGENTS.md` / `CONTRIBUTING.md` /
`SECURITY.md` / `CHANGELOG.md`），以及三个指向封存档案的旧账指针
（`DECISIONS.md` / `TASKS.md` / `MANIFEST.md`）、许可证、点文件和目录；
散文类文件一律进 `docs/`，`verify.py layout` 会与 `git ls-files` 比对。

## 许可

**GPL-3.0** —— 全文见 [`LICENSE`](../../../LICENSE)。

为什么是 GPL-3.0：随包分发的 `data/mpv_options_zh.json` 内嵌了 **727 条来自
[mpv_doc-CN](https://github.com/hooke007/mpv_doc-CN) 的中文选项说明**（GPL-3.0），
而 GPL-3.0 具传染性。

第三方内容的来源与许可汇总在 [`NOTICE.txt`](../../compliance/NOTICE.txt)。
本项目**不内置、不转发**任何第三方二进制 —— 下载中心只在用户点击时从各项目的
**官方地址**取。

---

**非官方第三方工具**，与 mpv / mpv-lazy 及其作者无隶属关系。

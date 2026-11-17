# MPV Config Builder

[English](../README.md) · **中文说明**（本页） · 打包与发布详版见 [打包与发布.md](打包与发布.md)

**把 mpv 的 813 个选项摊开给你调，还告诉你哪个和哪个打架。**

一个 Windows 上的 mpv 配置工具：不播放视频，只负责把 `mpv.conf` 写对。
勾选项 → 实时预览 → 生成配置，写前自动备份，随时可撤。

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
| 选项说明 | 没有或靠联网查 | **714 条中文说明**内嵌（原始 726 条，12 条随命令行专用项滤除） |
| 会不会写出已废弃的选项 | 会 | 读取时**滤掉** 16 条命令行专用项，并标出 deprecated |

## 怎么用

### 桌面版（Tauri 外壳）

**目前没有安装包。** 2026-11-16 桌面外壳从 Electron 换成 Tauri（`3.0.0-alpha.6`），
Electron 连同上一个安装包产线一起被移除；Tauri 侧的打包（`bundle.active`）还没开启，
所以 Releases 里暂时没有可下的 `Setup.exe`。想要窗口形态就自己编一份：

```powershell
cd tauri\src-tauri
cargo build
.\target\debug\mpv-config-builder.exe
```

需要 Rust 工具链 + WebView2（Win10/11 自带）。详细步骤与后续打包计划见
[打包与发布.md](打包与发布.md)。

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
- **写后 12 秒撤销**：保存配置后弹一条撤销条，点一下按刚生成的备份回滚

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
python tools\verify.py tauri      # Tauri 外壳（25 项，含窗口与关窗实测）
```

每次 `push` 与 PR 都会在 CI 上跑一遍上面的自检，配置在
[`.github/workflows/verify.yml`](../.github/workflows/verify.yml)。
runner 是 Windows —— 顶栏实机检查要 Edge/Chrome、Tauri 检查要 `cargo build` 出的 exe，
换 Linux 上这两项会退化成「跳过」，绿灯就成了假的。
外链可达性不与代码提交绑定，改为每周日单独跑一次。

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
tools/         build.py（生成）/ verify.py（验证）/ uidriver.py（浏览器驱动共用）
.github/       CI：push / PR 在 Windows runner 上跑一遍发布前自检
docs/          用户文档（界面能读的 4 份、中英 README、NOTICE.txt）+ 实测结论
data/          内置数据（选项库 / 键位 / 命令 / mpv 原始输出）
```

仓库根目录**只放**五个文档（`README.md` / `AGENTS.md` / `DECISIONS.md` /
`TASKS.md` / `MANIFEST.md`）、许可证、点文件和上面这些目录；散文类文件一律进
`docs/`，`verify.py layout` 会与 `git ls-files` 比对。

## 许可

**GPL-3.0** —— 全文见 [`LICENSE`](../LICENSE)。

为什么是 GPL-3.0：随包分发的 `data/mpv_options_zh.json` 内嵌了 **726 条来自
[mpv_doc-CN](https://github.com/hooke007/mpv_doc-CN) 的中文选项说明**（GPL-3.0），
而 GPL-3.0 具传染性。

第三方内容的来源与许可汇总在 [`NOTICE.txt`](NOTICE.txt)。
本项目**不内置、不转发**任何第三方二进制 —— 下载中心只在用户点击时从各项目的
**官方地址**取。

---

**非官方第三方工具**，与 mpv / mpv-lazy 及其作者无隶属关系。

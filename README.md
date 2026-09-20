# MPV Config Builder

**把 mpv 的 813 个选项摊开给你调，还告诉你哪个和哪个打架。**

一个 Windows 上的 mpv 配置工具：不播放视频，只负责把 `mpv.conf` 写对。
勾选项 → 实时预览 → 生成配置，写前自动备份，随时可撤。

> 面向的是 **mpv-lazy**（[mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit)）用户 ——
> 已经有懒人包了，缺的是「我想改点东西，但不知道改哪个」。

---

## 它解决什么

现有的 mpv 配置工具都是「挑几十个常见选项给你调」。这个不一样：

| | 常见的一键配置工具 | 本项目 |
|---|---|---|
| 覆盖的选项 | 几十个（同类工具最多 74 个） | **813 个**（全量库） |
| 冲突检测 | 没有 | **17 条规则**，每条注明手册原文 |
| 选项说明 | 没有或靠联网查 | **726 条中文说明**内嵌 |
| 会不会写出已废弃的选项 | 会 | 读取时**滤掉** 16 条命令行专用项，并标出 deprecated |

## 怎么用

### 普通用户：装桌面版（不需要 Python）

从 Releases 下载 `MPV Config Builder-<版本>-Setup.exe`，双击安装即可。
装完桌面会出现图标，双击就能用 —— **本机不需要装 Python**。

> ⚠ 安装包**没有代码签名**，Windows 会拦一次 SmartScreen 提示：
> 点「更多信息」→「仍要运行」。

### 从源码跑（需要 Python 3.8+，只用标准库，不用 `pip install`）

```bat
双击  启动.bat
```

它会起一个本地服务并自动打开浏览器。也可以手动：

```bat
py -3 webui\server.py
```

四档模式：**基础**（4 问向导）→ **进阶**（常用参数 + Shader 链 + 补帧）→
**完全体**（813 项全量搜索）→ **地狱**（裸写文本框，不给护栏但写前仍备份）。

另外还有**配置体检**：拖入一份 mpv.conf，报告编码 / include 链 / profile /
未知项 / 重复项 / 冲突 / 六维评分。

> 旧的 Tkinter 界面在 `legacy/`（保留但不维护，见 `legacy/README.md`）。

## 功能

- **四档模式**，从「只想能看片」到「我要调 shader 链」
- **配置体检**：17 条冲突规则 + 六维评分 + 逐行 diff
- **字幕实时预览**：调 `sub-font` / `sub-color` / `sub-border-*` 时立刻看到效果
- **Shader 链编排**：按本机实际存在的文件解析，自动判断顺序
- **多脚本融合**：把反交错 + 降噪 + 超分 + 补帧合成一个 `.vpy`
- **一键装 mpv-lazy**：从官方 release 取最新版，自动**选对包**（完整包 vs 无 VapourSynth 的精简包）、逐卷下载、校验、解压
- **下载中心**：脚本 / 字体 / 整包（如 uosc）一键装，装过什么能看能卸
- **配置无损写回**：认得出 UTF-8 / GBK / Big5，按**原编码**写回，只动全局区不碰 `[profile]` 小节
- **你自己的预设**：存下来、导出、发给别人（存在 `%LOCALAPPDATA%`，不进安装目录）
- **快捷键编辑**：改的是你自己的 `input-user.conf`，mpv-lazy 自带的那个文件一个字节都不动

## 为什么值得信任它改你的配置

这个工具动的是你的文件，所以规矩写在代码里也写在测试里：

- **写前必备份**，文件名带时间戳
- **取消勾选 ≠ 删除**：只是注释掉，原文件里那行还在
- **只动全局区**：`[profile]` 小节里的同名键一律不碰
- **按原编码写回**：不会把 GBK 的配置偷偷改成 UTF-8
- **不覆盖已有安装**：一键装 mpv-lazy 时，目标已有 `portable_config` 就拒绝
- **用户改过的不删**：卸载时逐个文件核对哈希，你编辑过的会保留并告诉你

## 跑测试

```bat
py -m unittest discover -s tests -t .
py -X utf8 tools\preflight.py        :: 发布前自检
```

`preflight` 一次跑完：单元测试、源码可编译、文档数字与实测一致、发行必带文件、
许可文件内容、无机器专用路径、下载清单链接可访问、顶栏常驻入口（真浏览器）、
Electron 外壳与打包形态（装了 `electron/node_modules` 才跑）。

界面相关的实机验证（需要本机有 Edge/Chrome，脚本会自己起后端）：

```bat
py -3 tools\check_topnav.py        :: 9 个页面的顶栏入口
py -3 tools\check_stdio_ui.py      :: 9 个页面跑在 stdio 通道上
py -3 tools\check_electron.py      :: Electron 开发形态
```

## 目录结构

```
core/          与界面无关的逻辑（25 个模块，两个界面共用）
webui/         网页界面
  server.py      本地服务 + JSON API（39 个接口，只用标准库）
               加 --stdio 就不开端口，改用一行一条 JSON 的协议（给 Electron 用）
  api.py         与传输无关的分发层（HTTP 与 stdio 共用）
  stdio.py       stdio 传输：stdout 只走协议，日志一律 stderr
  static/        9 个页面
electron/      Electron 桌面外壳（安装器从这里出）
  main.js        spawn 后端走 stdio、退出杀子进程、单实例、CSP
  preload.js     唯一的桥，只暴露 __MPVCB_INVOKE__
  renderer/      构建期从 webui/static 复制（不入库）
packaging/     PyInstaller 配方（把后端打成独立 exe）
legacy/        旧 Tkinter 界面（保留但不维护）
tests/         单元测试
tools/         构建选项库 / 文档数字守门人 / 发布前自检 / 实机验证
docs/          实测出来的结论（踩过的坑）
data/          内置数据（选项库 / 键位 / 命令）
```

## 许可

**GPL-3.0** —— 全文见 [`LICENSE`](LICENSE)。

为什么是 GPL-3.0：随包分发的 `data/mpv_options_zh.json` 内嵌了 **726 条来自
[mpv_doc-CN](https://github.com/hooke007/mpv_doc-CN) 的中文选项说明**（GPL-3.0），
而 GPL-3.0 具传染性。

第三方内容的来源与许可汇总在 [`NOTICE.txt`](NOTICE.txt)。
本项目**不内置、不转发**任何第三方二进制 —— 下载中心只在用户点击时从各项目的
**官方地址**取。

---

**非官方第三方工具**，与 mpv / mpv-lazy 及其作者无隶属关系。

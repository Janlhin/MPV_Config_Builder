# MANIFEST —— 第三方来源登记

**单一职责**：登记本项目引入或分发的第三方**数据 / 文本 / 运行时获取的资源**的来源与哈希。
与 `NOTICE.txt` 的分工：**本文件面向审计者**（来源、哈希、用途、是否入库）；
`NOTICE.txt` **面向分发者**（许可与归属的成段说明）。两者不重复。
许可的「为什么」在 `DECISIONS.md`。

> 建文件说明（2026-10-09）：本仓库此前缺这个文件（主规范四个文档之一）。
> 首批条目全部来自实测命令，不凭印象填写。

## 一、本项目的基本原则

**不内置、不转发任何第三方二进制。**
下载中心里的脚本 / 字体 / 整包，**只在用户点击时从各项目的官方地址取**，
仓库内不留副本、不镜像、不改包。因此这一类条目**没有本地 SHA256**——
它们从未落盘到仓库。这一点是设计选择，不是登记遗漏（见 `DECISIONS.md`「给谁用」条目）。

## 二、随仓库分发的内置内容

| 内容 | 文件 | 来源 | 许可 | 实测字节 | 实测 SHA256 | 用途 |
|---|---|---|---|---|---|---|
| GPL-3.0 许可全文 | `LICENSE` | `https://raw.githubusercontent.com/spdx/license-list-data/main/text/GPL-3.0-only.txt` | GPL-3.0 | **34,960** | `a1e40f21474230ccce72c4f2cc1b825c7ea01f460de611863d5be513cb5aa381` | 履行 GPL-3.0 分发义务；打包产物必须随附 |
| ├ 其中上游原文部分 | 前 34,674 字节 | 同上 | GPL-3.0 | 34,674 | `fb981668c18a279e285fc4d83fba1e836cc84dd4daa73c9697d3cfd2d8aca6e0` | **已实测核验**：与 `NOTICE.txt` 声明的哈希一致 |
| └ 本项目附加说明 | 末 286 字节 | 本项目自写 | GPL-3.0 | 286 | — | 说明为何是 GPL-3.0（传染性来源） |
| 中文选项说明 | `data/mpv_options_zh.json` | mpv_doc-CN（hooke007 维护，mpv 官方手册中文翻译） | **GPL-3.0** | 578,048 | `88a419571369dea5fb79295437f519dcee4d36e0ace6f147a12d0f1cc4123d2f` | 界面内嵌的 **726 条**中文说明 |

**哈希复现方式**：

```
python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('LICENSE').read_bytes()).hexdigest())"
python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('LICENSE').read_bytes()[:34674]).hexdigest())"
python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('data/mpv_options_zh.json').read_bytes()).hexdigest())"
```

`LICENSE` 的完整性另由门禁守着——`python tools/verify.py --offline` 的
「许可文件内容（GPL-3.0 全文 + 归属）」一项会在每次校验时判定。

**许可为何是 GPL-3.0**：`data/mpv_options_zh.json` 的 726 条中文说明来自 mpv_doc-CN（GPL-3.0），
GPL-3.0 具传染性，分发这份衍生数据即要求整个分发物按 GPL-3.0 走。详见 `NOTICE.txt` 与 `DECISIONS.md`。

## 三、运行时从官方地址获取（**不入库**，无本地哈希）

来源清单的**唯一真相源是 `core/dlcenter.py`**，界面上显示的许可也取自那里。
下表是 2026-10-09 从该文件提取的登记，改动清单时**以代码为准**：

| 条目 | 官方来源 | 许可 | 用途 |
|---|---|---|---|
| uosc | `https://github.com/tomasklaen/uosc/releases/latest/download/uosc.zip`（仓库 `https://github.com/tomasklaen/uosc`） | 见上游 | 现代化 OSC 界面；zip 解开为 `fonts/` + `scripts/uosc/` |
| thumbfast | `https://raw.githubusercontent.com/po5/thumbfast/master/thumbfast.lua`（仓库 `https://github.com/po5/thumbfast`） | 见上游 | 进度条悬停缩略图预览；需 uosc 或 osc 配合，单独放无反应 |
| mpv 官方 lua 脚本 | `https://raw.githubusercontent.com/mpv-player/mpv/master/TOOLS/lua/{autoload,autodeint,autocrop,pause-when-minimize,skip-logo}.lua` | mpv 项目许可 | 自动加载 / 自动反交错 / 自动裁剪 等 |
| LXGW WenKai Lite | `https://github.com/lxgw/LxgwWenKai-Lite` | SIL OFL 1.1 | 字幕字体（装到 `<配置目录>/fonts/`） |

**为什么没有 SHA256**：这些条目在用户点击时才从上游拉取，仓库不保存副本，
因此不存在可登记的本地哈希。上游 rolling release（如 `.../releases/latest/download/`）
本身也不提供固定哈希。**这是已知的留痕缺口**，缓解方式见下节。

## 四、已知缺口（诚实登记，不掩盖）

1. **运行时获取的条目无哈希校验** —— 用户下载到的内容未与任何哈希比对。
   上游为 rolling release 时，`latest` 指向的内容还会随时间变化。
2. **无一键复现脚本** —— 主规范要求「配一键复现脚本」，目前只有 `LICENSE` 的哈希可命令行复现
   （见第二节），内置数据依赖手工执行上述三条命令。
3. **上游许可未落库** —— 表中「见上游」的条目，其许可写在 `core/dlcenter.py` 的清单里并在界面显示，
   但本文件未逐条转抄（转抄会腐化，故只登记来源地址）。

> 缺口 1、2 已登记为任务队列中的改进项，见 `TASKS.md`。

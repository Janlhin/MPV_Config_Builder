# mpvconfigurator 0.2 评估（别人写的同类工具）

> 来源：`C:\Users\Janlhin\Downloads\Archives\mpvconfigurator-0.2.zip`（1.1 MB / 73 个文件）
> 解压在 `%TEMP%\mpvcfg02\`（临时目录，会被系统清理）
> 项目：`haasnhoff/mpvconfigurator` —— C++ / Qt5，GPLv2，自称 beta，**已停止维护**

## 它是什么

给 mpv 生成 `mpv.conf` 的图形工具，用 Qt Designer 的 `.ui` 文件堆了 **16 个标签页**：

```
tabvideo / tabaudio / tabsubtitle / tabscreenshot / tabosc /
tabosd / tabwindow / tabmisc / tabextensions / unknownsettingstab / tabconfig
```

外加「未知/自定义设置」页 —— 读进来的配置里不认识的键，原样列出来让用户自己编辑。

## 结论先说：**不能拿它的代码或素材**

1. **许可不兼容**。它是 **GPLv2**，你的项目最终要选 GPL-3.0（因为内置了 mpv_doc-CN 的中文数据）。
   **GPLv2 与 GPLv3 不兼容** —— 不能把它的代码/图标/图片并进你的项目。
2. **它的图标是版权作品**。`icon_windows.ico`（6 个尺寸 16→256）、`icon.png`（256×256 RGBA）、
   `icon.icns` 规格正好是你 M5 需要的，但**不能直接拿来用**，除非你整体改成 GPLv2。
   → 建议自己画或买一个，别为了省事引入许可冲突。
3. **它的代码质量它自己都承认**：README 的 FAQ 里有一条
   「Your code is absolutely horrible」→「This is my second major C++ project」。
   而且它把 `accessibleName` / `accessibleDescription` 拿来当"难以解析的选项"的覆盖手段，
   注释写着 *"This is obviously not how accessible stuff should be used, but you know what? Fuck it."*

## ⚠ 最重要的发现：它内置的英文手册是 **mpv 0.5 时代**的

`src/man/` 里有 7 份 rst（共 1.4 MB / 5700 行），其中 `options.rst` 就是 mpv 官方手册的
英文原文 `DOCS/man/options.rst` —— **正好是 `core/options_db.py` 里 `RST_PATH` 一直想找的文件**。

**但它是十年前的。** 实测证据（拿你的 `_mpv_options_raw.txt` 对照）：

| 检查 | 结果 |
|---|---|
| 它列的选项名 | 391 个 |
| 与你的选项库交集 | 273 个（覆盖你库里 **32%**） |
| **它独有、你的 mpv 里已经不存在的** | **118 个 —— 全部 118 个都不存在了** |
| 它有 `--gpu-api` 吗 | ❌ 没有 |
| 它有 `--vo=gpu-next` 吗 | ❌ 没有 |
| 它有 `--tone-mapping` 吗 | ❌ 没有 |

那 118 个里全是 `cache-backbuffer` / `ass-vsfilter-aspect-compat` / `cdda-*` 这类
早被删掉或改名的东西，说明这份快照对应 **mpv 0.5（约 2014–2015）**。

**所以：不能用它做英文说明。** 想要英文说明，得从**当前版本**的 mpv 源码取
`DOCS/man/options.rst`（<https://github.com/mpv-player/mpv>），或者从
<https://mpv.io/manual/master/> 抓。

## 值得借鉴的两点（思想，不是代码）

### 0. 它的字幕预览很好，滑块有 bug —— 已经借鉴并改进

**字幕预览（值得学）**：`tabsubtitle.cpp` 用 `QGraphicsSimpleTextItem` + pen 当描边、
brush 当填充、`QGraphicsDropShadowEffect` 做阴影，三个滑块 `valueChanged` 就重画。
字号拖过 90 时文字会变成 `"I am a special BIG subtitle."`。

**滑块（别学）**：`sliderSetting::getValue()` 返回的是**旁边那个 QLabel 的文本**，
不是 `slider->value()`；而 label 的初值写死在 `.ui` 里、只有 `sliderMoved`
（鼠标拖动）才更新。后果：

| 场景 | 写进配置的值 |
|---|---|
| 勾上但没拖滑块 | `.ui` 里写死的初值（如 `55`） |
| 载入配置后没动滑块再保存 | **旧值**（`setValue()` 不触发 `sliderMoved`） |

**我们的实现**（`webui/static/state.js` 的 `updateSubPreview`）避开了这两点：
值统一从 `APP.values` 读（和写进 mpv.conf 的同一份），更新挂在 `changed()`
这个已有的"状态变了"钩子上，不依赖任何输入控件的事件。

### ⚠ 颜色透明度顺序：这里我判断反过一次，记下来

`QColor::HexArgb` 输出 `#AARRGGBB`（透明度在前）。我一开始以为 mpv 要的是
`#RRGGBBAA`（跟 CSS 一样），还据此认定它写错了。

**是我错了。** 拿 `mpv --list-options` 的 11 个 8 位颜色默认值一定案就清楚了：

| 选项 | 默认 | `#AARRGGBB` 解释 | `#RRGGBBAA` 解释 |
|---|---|---|---|
| `sub-color` | `#FFFFFFFF` | 不透明的白 ✅ | 白+全透明（也说得通） |
| `sub-back-color` | `#AF000000` | 69% 不透明的黑 ✅ | **全透明的暗红** ❌ |
| `osd-selected-color` | `#FFFABD2F` | 不透明的橙黄 ✅ | 桃红+18% ❌ |

所以 **mpv 的 8 位颜色是 `#AARRGGBB`（透明度在最前）**，
`data/mpv_options_zh.json` 里那句「Alpha 是用 #AARRGGBB 来表示的」**是对的**；
而 6 位的 `#RRGGBB` 是普通顺序。**两套顺序不一样**，极容易写反。

结论已写成测试钉住（`tests/test_subpreview.py` 的 `ColorOrderEvidenceTest`），
免得下次又有人（包括我）想当然改回去。

### 1. 运行时解析手册出 tooltip —— 它的做法，你的做法更好

它的 `setting::parseSetting()` 在**运行时**打开 `./man/*.rst`，用正则找出这个选项那一段，
拼成 tooltip；找不到就显示"Please look it up in the manual"。

你的做法（预解析成 `data/mpv_options_zh.json` + 精选层手写说明）**明显更优**：
- 不用每次起界面都读 1.4 MB 文本
- 说明质量可控（726 条人工翻译，不是正则抠出来的）
- 但它的**兜底话术**值得学：查不到就**明说查不到**，而不是编一句

> 你的工具已经是这个思路了（`core/notes.py` 的"查不到就不加注释"）。
> 这次算是一个外部印证：**别赌手册版本，也别编说明。**

### 2. 「未知设置」页 —— 你已经有等价物且更细

它把所有不认识的键丢进一个可编辑列表，原样写回。你的做法更进一步：

| | mpvconfigurator | 你的工具 |
|---|---|---|
| 不认识的键 | 一个列表，原样保留 | 分三类：`unknown`（真不认识）/ `unlisted`（标准选项但没做界面）/ `known` |
| 依据 | 无（只有它硬编码的那些 checkbox） | 全量选项库 813 项 + `COMMON_OPTIONS` |
| 自定义层 | 有（纯文本列表） | 有（`custom`，且预览里可见） |
| profile | ❌ 不处理 | ✅ 单独返回，不污染全局值 |
| include 链 | ❌ 不跟随 | ✅ 跟随 8 层 / 24 文件，标明来源 |
| 备份/回滚 | ❌ | ✅ `.bak-时间戳` + 一键回滚 |
| 冲突检测 | ❌ | ✅ 17 条规则，注明手册依据 |

## 你的工具 vs 它（功能面对比）

| 能力 | mpvconfigurator 0.2 | MPV Config Builder |
|---|---|---|
| 选项界面 | 16 个标签页（硬编码 checkbox） | 813 项全量库 + 搜索/分组/分页 |
| 选项说明 | 从 10 年前的 rst 正则抠 | 726 条中文说明（精选层人工写） |
| 一键组合 / 预设 | ❌ | ✅ 9 套组合 + 6 套预设 |
| shader / vpy 清单 | ❌ | ✅ 按本机实际文件生成 |
| 冲突检测 | ❌ | ✅ 17 条 |
| 配置体检 | ❌ | ✅ 六维评分 + include 链 + profile |
| 备份 / 回滚 | ❌ | ✅ |
| 编码安全 | ❌（UTF-8 假定） | ✅ 认 GBK/Big5/BOM，按原编码写回 |
| VPY 融合 | ❌ | ✅ |
| 快捷键编辑 | ❌ | ✅ 含 209 条默认键位对照 |
| 下载 / 一键安装 | ❌ | ✅（L1 已完成；安装器在旧 Tkinter 里） |
| 平台 | Win / macOS / Linux | Windows 10/11 |
| 许可 | GPLv2 | **待定（见 `LICENSE.txt`）** |

## 那这个 zip 该怎么处置

**价值有限，但别急着删。** 建议：

1. **不要并入项目**（许可不兼容 + 代码质量差 + 手册过时）
2. 如果只是想"有个同类工具对照看看"，就留在 `Downloads\Archives\` 里，需要时解压看
3. **唯一值得单独留下来的是那份 10 年前的 `options.rst`** —— 作为"手册会过时"的实证：
   你项目里那条"829 项全量库要能重新生成"的设计（`tools/build_options_db.py`）
   正是为了避免这种下场。可以在文档里引它当例子。
4. 想要英文说明的话，正确路径是：**从当前版本 mpv 源码取 `DOCS/man/options.rst`**，
   喂给已有的 `tools/build_options_db.py` 解析器（它已经会解析这个格式）。

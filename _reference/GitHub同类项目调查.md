# GitHub 同类项目调查（2026-09 会话）

**问题**：这个项目在 GitHub 上有没有同类的？

**结论先说**：有，但**极稀有且大多已停止维护**。写「mpv 配置」的仓库有几百个，
但其中 **99% 是「配置集合」（别人手写的 mpv.conf，拿来抄），不是「配置工具」**。
真正意义上的同类工具，用 GitHub 翻遍也就 **个位数**，而且三个主要对手里
两个已经 5～10 年没动了。

**这反而是好消息**：这个项目所在的格子是空的 —— 下面有数据支撑。

---

## 一、生态全貌：配置集合 ≫ 配置工具

用 GitHub 官方 search API 跑了 14 组关键词（脚本见本文末尾），结果非常一致：

| 关键词 | 结果数 | 说明 |
|---|---|---|
| `mpv.conf` | **523** | 绝大多数是"我的 mpv 配置"仓库 |
| `topic:mpv-config` | 104 | 同上 |
| `mpv configurator` | **3** | ← 真正的工具，只有 3 个 |
| `mpv config generator` | **3** | 同上 |
| `mpv configuration tool gui` | **0** | 一个都没有 |
| `mpv options gui` | **0** | 一个都没有 |
| `mpv profile editor` | 1（且是误命中） | 一个都没有 |

对比一下体量差：

| 类型 | 代表 | 星数 |
|---|---|---|
| **配置集合**（大头） | [hooke007/mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit)（= mpv-lazy 本体） | **7,597★** |
| | [dyphire/mpv-config](https://github.com/dyphire/mpv-config) | 1,879★ |
| | [Zabooby/mpv-config](https://github.com/Zabooby/mpv-config) | 567★ |
| | [hl2guide/better-mpv-config](https://github.com/hl2guide/better-mpv-config) | 383★ |
| **完整播放器**（不是配置工具） | [422658476/MPV-EASY-Player](https://github.com/422658476/MPV-EASY-Player) | 1,433★ |
| | [celluloid-player/celluloid](https://github.com/celluloid-player/celluloid) | 1,464★ |
| **打包套件**（配置 + 二进制 + 脚本） | [stax76/mpv-hero](https://github.com/stax76/mpv-hero) | 138★ |
| **配置生成器**（← 我们的格子） | [MattMcManis/Glow](https://github.com/MattMcManis/Glow) | **300★** |
| | [haasnhoff/mpvconfigurator](https://github.com/haasnhoff/mpvconfigurator) | 153★ |
| | [vishal-joshy/radiance](https://github.com/vishal-joshy/radiance) | 3★ |

> ⚠️ **一个重要修正**：`stax76/mpv-hero` 有 138★ 且**很活跃**（最后提交 2025-11），
> 光看描述容易以为是竞品。查了 README 才确认：它是**打包套件**
> （原版 mpv + uosc/thumbfast/recent-menu 等脚本 + 现成配置），
> **不含任何配置生成界面**。所以它和 mpv-lazy 是同类，不是我们的同类。

---

## 二、真正的同类工具，逐个看

| 项目 | 星 | 语言 | 许可 | 最后提交 | 状态 |
|---|---|---|---|---|---|
| [MattMcManis/Glow](https://github.com/MattMcManis/Glow) | **300** | C# / WPF | GPL-3.0 | **2020-12-25** | ⚠️ **停滞 5 年** |
| [haasnhoff/mpvconfigurator](https://github.com/haasnhoff/mpvconfigurator) | 153 | C++ / Qt | GPL-2.0 | **2015-10-17** | ❌ **停滞 10 年** |
| [eshoyfer/mpvconfigurator](https://github.com/eshoyfer/mpvconfigurator) | 1 | C++ / Qt | GPL-2.0 | 2015-08-11 | ❌ 上面那个的 fork |
| [vishal-joshy/radiance](https://github.com/vishal-joshy/radiance) | 3 | TypeScript | MIT | 2022-08-28 | ⚠️ README 还是 Create React App 默认模板，像是没做完 |
| [Watashi199/mpv-subtitle-config-generator](https://github.com/Watashi199/mpv-subtitle-config-generator) | 0 | JS | - | **2026-06-26** | 🆕 只做**字幕**，不动其它选项 |
| [SelwynHP/shader-configurator-mpv](https://github.com/SelwynHP/shader-configurator-mpv) | 2 | C# | - | 2021-01-10 | 只做 **shader profile** |

**读出来的三件事**：

1. **没有一个"全量选项 + 网页界面"的。** Glow 是桌面 WPF（Windows only，还要装
   .NET Framework 4.5）；mpvconfigurator 是桌面 Qt；radiance 是网页但没做完。
2. **两个主力都绑定在过时的 mpv 上。** 这正是我们之前评估
   `mpvconfigurator-0.2.zip` 时踩到的那条：它内置的是 **mpv 0.5 时代（约 2014）**
   的选项表，391 个选项里只有 273 个今天还存在。
3. **许可都是 GPL，且都比我们打算用的 GPL-3.0 更麻烦**：Glow 是 GPL-3.0（兼容），
   mpvconfigurator 是 **GPL-2.0-only**（与 GPL-3.0 **不兼容**，所以那两份
   C++ 源码一行都不能抄 —— 见 `_reference/mpvconfigurator-0.2-评估.md`）。

---

## 三、Glow 的实测体量（最接近的对手）

把 Glow 浅克隆下来数了一遍（`git clone --depth 1`，87 个文件）：

| 维度 | Glow | 本项目 |
|---|---|---|
| 覆盖的 mpv 选项 | **74 个**（从 `source/Glow/Generators/*.cs` 里抽出真正写进配置的键） | **813 个可写进配置**（全量库）/ 117 个精选 |
| 界面 | 桌面 WPF，Windows only，需 .NET Framework 4.5 | 浏览器，零依赖 Python 标准库起服务 |
| 运行依赖 | 编译好的 exe（要 .NET） | Python 3.8+（连第三方包都不用） |
| 档位 | Preset：Ultra / High / Medium / Low | 基础 / 进阶 / 完全体 / 地狱 + 配置体检 |
| 配置体检 / 冲突检测 | ❌ 没有 | ✅ 17 条冲突规则，每条注明手册原文 |
| 选项说明 | ❌ 界面里没有中文说明 | ✅ 726 条中文说明（来自 mpv_doc-CN） |
| 值域校验 | ❌ 靠下拉框限死 | ✅ 区分"封闭枚举"与"自由填"，自由填的也校验格式 |

### ⚠️ 关键发现：Glow 会写出「已经不存在的选项」

拿我这边的权威库（`data/mpv_options_zh.json`，来自 `mpv --list-options`）核对它
那 74 个键：

```
Glow 写了 74 个选项
  mpv 0.41 里已经没有的: 10 个
    cache-backbuffer, cache-default, cache-file, cache-file-size,
    cache-initial, cache-seek-min, opengl-fbo-format,
    osc-layout, osc-seekbarstyle, softvol-max
  仍存在但已标记弃用的: 2 个
    sub-ass-force-style, sub-ass-hinting
```

而且这 10 个**不是潜伏在界面里的死代码，是真的会写进 mpv.conf**：

| 文件 | 里面有哪些已删除的选项 |
|---|---|
| `Generators/Stream.cs` | `cache-backbuffer` / `cache-default` / `cache-file` / `cache-file-size` / `cache-initial` / `cache-seek-min` |
| `Generators/OSC.cs` | `osc-layout` / `osc-seekbarstyle` |
| `Generators/Video.cs` | `opengl-fbo-format` |
| `Generators/Audio.cs` | `softvol-max` |

**为什么这段值得写下来**：这正是本项目的 `core/options_db.py` 那套
「读取时滤掉不在配置文件里的选项 + 标出 deprecated」要解决的问题。
`cache-*` 那批是 mpv 0.36 前后被 `demuxer-max-bytes` 系列取代的 ——
一个 2020 年停更的工具，用户今天拿来生成配置，得到的是一堆 mpv 报 unknown option 的行。

---

## 四、可借鉴的（Glow 做对的地方）

| 它的做法 | 我们要不要 | 备注 |
|---|---|---|
| **"设为 default 就把该行从配置里去掉"** | ✅ **已经有了** | 就是这个项目的 `disable`（合并模式里注释掉/不写）。当初设计时还有点犹豫，现在有个 300★ 的成熟工具用同一套心智模型，可以放心 |
| 自动找到或创建正确的 config 目录 | ✅ 已有 | `core/paths.py` 的 `find_lazy_pc()` 等 |
| 预设可导出/导入成 ini 文件 | 🟡 可以考虑 | 我们有 6 套预设 + 9 套组合，但**预设是内置的，用户存不下来**。这是个真实的缺口，见 §五 |
| 自绘颜色选择器 | ✅ 已有更好的 | 我们的字幕实时预览比它那个强（而且避开了它读 QLabel 文本取值那个 bug） |

## 五、结论与建议

### 定位：这个格子是空的

一句话总结差异：

> **现有的 mpv 配置工具都是"挑几十个常见选项给你调"；这个项目是"把 mpv 的 813 个
> 选项全部摊开，还告诉你哪个和哪个打架"。**

具体三条别人没有的：

1. **全量选项覆盖** —— 813 项（对手最多 74 项），且**能分辨哪些选项今天还存在**
   （对手会写出 10 个已删除的选项）。
2. **网页界面 + 零依赖** —— 对手要么是 Windows-only 桌面程序（Glow / mpvconfigurator），
   要么是没做完的网页（radiance）。"跑一条 `py -3 webui/server.py` 就开"这件事没有竞品。
3. **配置体检 + 冲突检测** —— 17 条规则、每条注明手册原文。这个功能在所有同类里**一个都没有**。

### 风险：不是来自同类工具，而是来自配置集合

`hooke007/mpv_PlayKit` 有 7,597★，是这个生态里事实上的标准。用户的实际选择是
「下载 mpv-lazy 懒人包」而不是「找个工具自己配」。所以：

- **本项目应该明确定位成 mpv-lazy 的配套工具，而不是替代品**（这一点在
  `产品规划与路线图.md` §1.2 已经定过，这次调查确认那个决定是对的）。
- 「以 mpv-lazy 为底座」不是局限，而是**唯一合理的切入点**：用户已经有 lazy 包了，
  缺的是"我想改点东西但不知道改哪个"。

### 从对手的失败里能学到什么

| 对手 | 怎么停的 | 对我们的提醒 |
|---|---|---|
| Glow | 2020 年后没动，选项表固化了 | **选项库必须能重新生成**（`tools/build_options_db.py`），不能手写死在代码里 |
| mpvconfigurator | 2015 年后没动，第 2 轮评估已确认它内置的是 mpv 0.5 时代的表 | 同上；另外它是 Qt/C++，**跨不过去**（GPL-2.0-only 与 GPL-3.0 不兼容，源码一行都不能抄） |
| radiance | README 还是脚手架默认内容 | 别在"技术栈炫技"上耗时间，界面能用比框架新重要 |

### 挖出来的两个待办（不紧急，但记下来）

1. **用户预设的保存/导入** —— Glow 支持把自定义预设存成 ini。我们有 6 套内置预设
   但用户**存不下来自己调好的那套**。已有 `localStorage` 存了 target/writeMode，
   但**没有存 values**。这是个不算大的功能，价值明确。
2. **考虑去 `awesome-mpv`（2,271★）提 PR** —— 那是 mpv 生态的精选清单，
   上面这些工具都在里面。发布后如果想被找到，这是最直接的入口。

---

## 附：调查怎么跑的（可复现）

```powershell
# GitHub API 搜索 + 细看（零依赖，脚本本轮临时写的，跑完已删）
py -3 -c "..."      # search/repositories 跑 14 组关键词，输出存 _gh_found.json

# Glow 源码实测（浅克隆，只读）
git clone --depth 1 https://github.com/MattMcManis/Glow.git %TEMP%\glow-src
```

⚠️ **环境限制**：`web_fetch` 把 `github.com` 也判成非公网 IP 拒了
（和 `mpv.io` / `hooke007.github.io` 一样）。**Python 直连是通的**，
GitHub search API 未登录限流 10 次/分钟，所以脚本里每次查询之间 `sleep 7`。
这条经验已经记在 `_reference/README.md`。

⚠️ 引用的星数/提交日期是 **2026-09 抓的**，会变；结论（哪个格子是空的）比数字稳。

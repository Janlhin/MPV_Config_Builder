# Field-tested pitfalls

> Active engineering note. These are field-tested conclusions, not guesses. They were
> originally part of `docs/既有约定.md`; the archive keeps the historical copy.
> Treat them as checks to repeat, not as a rulebook to quote.

## 实测判据
（原 `docs/踩过的坑.md`，2026-11-17 并入）

> 这些是**实测出来的**，不是看代码猜的；完整过程在 git 历史（2026-11-17 之前的 `踩过的坑.md`）。
> 判据比结论更值钱：下次遇到同类问题，先照着验一遍。

**mpv 本身**

- 8 位颜色是 `#AARRGGBB`（透明度在前）；`#` 之后一律算注释 → 颜色值必须写成 `"#RRGGBB"`。
- 光写选项名 = `=yes`；`vf=` 路径含空格必须整体加引号（否则 mpv 报解析失败）。
- 未改动的行可以逐字节原样写回；include 链里引的都是 profile（跟随 include 不会污染全局值）。

**下载 / mpv-lazy**

- 完整包是分卷，`-noVS` 包不能要；"选体积最大的"会挑错。分卷是否齐全读 **7z 文件头**
  （三个字段全 `0xFF…FF` 表示后面还有卷）。
- `uosc.zip` 里 11.3 MB 是别的平台二进制（`ziggy-darwin` + `ziggy-linux`）；Windows 只留 `ziggy-windows.exe`。

**界面 / i18n**

- 原生 `<datalist>` 气泡不在 DOM、不吃 CSS、截图抓不到 → 只能自绘（`tests/test_combo.py` 钉死）。
- 只测一种传输等于没测"传输可替换"：4 处直连 `fetch` 在浏览器里全正常，stdio 下静默失效。
- 页面报"剩余汉字"可能是后端返回的数据串 → 先 CDP dump 归因，**别拿前端词典去盖后端字符串**。
- `data-i18n-ph` 会被词典兜底覆写回原文；未标记的静态文案一律走词典。
- 运行时拼的字符串要过两道关：英文态渲染 + 切语言时的词典重扫（长词条优先）。
- "切后剩 0 汉字"只测了切换那一刻；confirm / toast 这类操作后才出现的串要单独 grep。
- 构建时取一次文本会把语言冻在加载那一刻 → **存键不存文本**，渲染时现取。
- 切语言重绘必须走缓存响应，不能重新请求（否则丢用户未保存的编辑）。
- `grid-template-rows` 展开动画要三层结构（容器 padding / 裸裁剪层 / 视觉层）；
  收起后剩一条缝 = 漏算了 margin 或 padding。

**测试 / 验证方法**

- 高风险重构用**系统枚举**，不靠手挑用例（55 个手选用例全绿，4699 组枚举立刻抓出真 bug）。
- 报错和成功同时出现时先怀疑检查本身 —— 一个永远不会成功的断言比没有断言更糟。
- 字符串匹配会撞文档串（注释里写着"不许 import http.server"被判违规）→ 改用 AST 判据。
- "文件都在"不等于"能用"：打包产物齐全但崩在 import，只有真起进程才看得见。
- `where py` 成功 ≠ `py -3` 能跑；判断"在不在"不够，必须真跑一下解释器。
- 固定 sleep 是 CI 间歇红的来源：等条件，别等时长；红过一次要翻全部运行历史判断是竞态还是真缺陷。
- 实机检查只要触发"写"，先把最外层 I/O 换成桩 —— 页面会自己探测环境并自动填 target。
- 钩子不能写成 `.ps1`：Git for Windows 用 `-File` 执行无扩展名文件，被扩展名校验卡死（Q-002）。
- 断点续传必须验对方真的回了 `206` + 起始字节匹配，否则截断重下。
- `Path("")` 在 Windows 上等于当前目录；`Path.write_text()` 默认按平台写 CRLF 且非原子。
- 随技术栈移除的历史教训（原文见 git）：`.bat` BOM / cmd 预读头部、`ELECTRON_RUN_AS_NODE` 污染、
  GPU 进程崩溃、Electron 打包。

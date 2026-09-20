# _archive —— 不再参与运行的历史文件

**这里的东西不会被任何代码引用，也不参与测试与打包。** 保留而不是删除的理由：
这个目录**不是 git 仓库**，删掉就没有 `git checkout` 可以找回来了。

想彻底清空：确认过下面每一行都不需要之后，直接删掉整个 `_archive\` 即可。

---

## tests/ —— 手工验证脚本（4 个）

| 文件 | 原来干什么 | 为什么归档 |
|---|---|---|
| `_api_smoke.py` | 打一遍后端接口看通不通 | 需要**手工先起服务**并传端口（默认 `127.0.0.1:8791`）；`tests/test_webui.py` 已经在进程内起服务做了同样的事，而且是自动跑的 |
| `_api_a_class.py` | 验证 include 链 / profile / 编码 | 写死了 `C:\Program Files\mpv-lazy\portable_config`，**换台机器就跑不了**；同样内容在 `test_correctness.py` 里有覆盖 |
| `_api_conflicts.py` | 验证冲突检测出现在预览接口里 | 同上（需要手工起服务 + 传端口） |
| `_api_keys.py` | 按键绑定接口端到端 | 同上 |

**共同问题**：它们都不含 `unittest.TestCase`，所以 `unittest discover` **一个都不会收集**
（`Ran N tests` 里从来没有它们），属于"写了但从来没自动跑过"的脚本。
现在的 352 项测试里已经覆盖了它们要验的东西。

---

## prototype/ —— 最初的界面原型（7 个文件）

`index.html` / `basic.html` / `advanced.html` / `expert.html` / `hell.html`
/ `style.css` / `README.md`

它自己的 README 第一句就写着「**这不是程序**，只是用来确认观感的静态页面」。

**为什么归档**：设计意图已经全部落地到 `webui/static/`（而且更强：真后端、真数据、
9 个页面、31 个接口）。留着会让"`webui/static/` 才是真的界面"这件事变得模糊 ——
两个目录里都有 `advanced.html` / `expert.html`，很容易点错。

**里面唯一还有点价值的是** `prototype/README.md` 的那张「这一版想确认的 10 个设计点」
表格 —— 那是观感演进的历史记录。想看就直接翻这个文件。

---

## merge_into_conf.py（1 个）

一次性的机器专用脚本：把 mpv-lazy 的 mpv.conf 合并进桌面上的 `mpv1.conf`。
里面写死了两个绝对路径（`C:\Users\...\Desktop\mpv1.conf`、`C:\Program Files\mpv-lazy\...`）。

**⚠ 归档前先做了迁移**：它第 50–66 行有一段**正确处理 `glsl-shaders-append`** 的逻辑
（注释掉原 append 行、新增 `glsl-shaders`），而 `core/writer.py` 当时是缺这段的
（就是 X-1-2 那个回归）。这段意图现在已经由 `core/loader.py`
（替换型 `glsl-shaders` 与追加型 `glsl-shader*` 分开跟踪）+ `core/builder.py:_shader_lines()`
覆盖，并且有 `tests/test_config_loss.py` 的回归测试守着。

**先迁移、后归档**的顺序不能反 —— 否则就是"把唯一的正确实现证据删了"。

---

## 没有归档、但看着像该归档的

| 东西 | 为什么留着 |
|---|---|
| `_mpv_options_raw.txt` | 名字带 `_` 像临时文件，但 `core/options_db.py` 用它重建 829 项选项库。**删了就无法重建** |
| `tests/__init__.py` | 0 字节，但删掉之后 `unittest discover -s tests` 直接报 `ImportError: Start directory is not importable`，**352 项一个都跑不了** |
| `_shots/` | 13 张界面截图，1.8 MB。`README.txt` 没引用它，但**打包发布时需要截图**（M5 要用） |
| `MPV_实机配置分析报告.md`、`mpv1配置分析报告.md` | 一次性分析产物，但记录了真实 mpv-lazy 配置长什么样 —— 「`glsl-shaders-append` 是原生默认写法」这个结论就是从这来的，是 X-1-2 的依据 |

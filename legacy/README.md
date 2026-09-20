# legacy —— 旧界面（Tkinter），保留但不维护

**这里的代码还能跑，但不再接收新功能。** 新界面在仓库根的 `webui/`（网页版）
与 `electron/`（桌面版）。

> ⚠ 别把这里和 `_archive/` 搞混：
> **`legacy/` 是还能运行的旧版本**（有测试盯着、`preflight.py` 会编译它），
> **`_archive/` 是不再参与运行的历史文件**。

---

## 里面有什么

| 文件 | 说明 |
|---|---|
| `mpv_config_builder.py` | 旧界面主程序（2166 行，Tkinter）。**下载器与一键安装最初只在这里**，后来网页版也做了（R-8w） |
| `启动.bat` | 启动器。会先 `cd` 到**仓库根**再启动 —— 因为它要 import `core\`、读 `data\` 与根目录的 `*.md` |

## 怎么跑

双击 `legacy\启动.bat` 就行（需要本机有 Python 3）。

它做的事：`cd` 到仓库根 → `py -3 legacy\mpv_config_builder.py`。
**不先退到仓库根会出问题**：程序要靠 `core\` 和 `data\`，那些都不在 `legacy\` 下。

## 为什么放在 legacy/ 而不是删掉

2026-09-14 决定「**保留但不维护**」（用户选择 E1-2）。放进 `legacy/` 的理由：

1. **入口不再打架**。以前仓库根同时躺着 `启动.bat`（旧）和 `启动(新版界面).bat`（新），
   名字上分不出哪个是主线，双击错了也不知道。
2. **一眼看得出新旧**。根目录剩下的都是共用的（`core/` `data/` `webui/` `tests/`）
   或新的（`electron/`）。

## ⚠ 搬进来时改了一处代码，值得知道

`mpv_config_builder.py` 原来**没有设 `sys.path`** —— 它能 `from core.paths import ...`
纯粹是因为启动器 `cd` 到了仓库根，靠"当前工作目录碰巧在 `sys.path` 上"。

这种隐式依赖换个启动方式就断（比如从别处 import 它、或 IDE 里直接运行）。
所以搬进来时在文件开头补了一段 **`sys.path` 补丁**（带冻结判别，
打包形态走 `sys._MEIPASS` 那条路），并留了注释说明为什么。

## 哪些东西还在盯着它（别以为它没人管）

| 谁 | 盯什么 |
|---|---|
| `tools/preflight.py` | 编译它、扫它有没有机器专用绝对路径 |
| `tests/test_version.py` | 它必须用 `core/schema.py` 的标题与版本常量，不许自己手写 |
| `tests/test_paths.py` | 它读说明书必须走 `doc_path()`，不许用 `__file__` 推 |

这三条都是**防漂移**的：新旧两个界面共用 `core/`，任何一边自己抄一份常量都会出问题。

## 已知状态

- **M6（Tkinter 的 DPI 适配）已明确「不做」** —— 它是保留品，不投入维护成本。
- 打包（PyInstaller / Inno Setup）**没有为它维护配方**；`packaging/backend.spec`
  打的是网页版的后端。旧版要打包得自己写 spec（《制作与发布文档.md》§五 有旧记录）。

# Spec — 用户数据落到 `%LOCALAPPDATA%`，不往安装目录写（W-2）

| | |
|---|---|
| **作者** | DSH agent |
| **日期** | 2026-09-14 |
| **状态** | **已实施**（2026-09-14，全部 AC 通过，见 §10） |
| **上游** | 路线图 §4.1 **W-2**（🔴 高，标记为「打包前必须修」） |

---

## 1. Context（为什么做这个）

`core/paths.py: writable_root()` 在**冻结（打包）形态**下返回 **exe 所在目录**。
而 `core/presetfile.py: registry_dir()` 拿它存用户预设：

```python
d = Path(writable_root()) / "presets"
```

源码运行没事（就是仓库根）。**但装成应用之后就是 `Program Files` 下 → 只读。**
后果：用户点「存下当前这一套」**静默失败**（`mkdir` 抛权限错），
而且**只在装完之后才暴露** —— 开发机上根本复现不了（开发者账号往往有权限，
或者根本没走冻结路径）。

**同一仓库里已经有正确做法**，而且不止一处：

| 位置 | 现在写在哪 |
|---|---|
| `core/schema.py: SETTINGS_PATH` | `%LOCALAPPDATA%\MPVConfigBuilder\settings.json` ✅ |
| `core/dlcenter.py: manifest_path()` | `%LOCALAPPDATA%\MPVConfigBuilder\installed.json` ✅ |
| `core/installer.py: default_install_dir()` | `%LOCALAPPDATA%\mpv-lazy` ✅ |
| **`core/presetfile.py: registry_dir()`** | **`<writable_root>/presets`** ❌ ← 就它一个错的 |

所以顺带解决**重复**：那条 `%LOCALAPPDATA%\MPVConfigBuilder\` 的拼法抄了三遍。

---

## 2. Functional Requirements

| ID | 要求 |
|---|---|
| **FR-1** | `core/paths.py` **MUST** 提供 `user_data_dir()`，返回**用户级数据目录**：`%LOCALAPPDATA%\MPVConfigBuilder`；拿不到 `LOCALAPPDATA` 时退回 `Path.home()/"MPVConfigBuilder"`。 |
| **FR-2** | `user_data_dir()` **MUST NOT** 依赖 `is_frozen()` —— 用户数据的位置**在源码运行与打包运行下必须一致**（这样预设在两种形态间可以互通，也不会出现"换种启动方式就找不到数据"）。 |
| **FR-3** | `user_data_dir()` **MUST** 允许两层覆盖，且**优先于**环境变量默认值：① 环境变量 `DSH_MPV_DATA_DIR`；② `paths.set_user_data_dir(path)`（测试与工具用，传 `None` 复位）。 |
| **FR-4** | `presetfile.registry_dir()` **MUST** 改为 `<user_data_dir()>/presets`，**不再**用 `writable_root()`。 |
| **FR-5** | `presetfile` **MUST** 保留现有的两个覆盖途径（`DSH_MPV_PRESET_DIR` 与 `set_registry_dir()`），它们的优先级**高于** `user_data_dir()`。**已有测试靠这个不往真目录写东西，不许破坏。** |
| **FR-6** | `dlcenter.manifest_path()` 与 `schema.SETTINGS_PATH` **SHOULD** 改为复用 `user_data_dir()`，消除三份重复。行为必须不变（`installed.json` / `settings.json` 的名字与父目录不变）。 |
| **FR-7** | `writable_root()` **MUST** 保留（它仍有正确用途：导出/另存到 exe 旁边），但**MUST NOT** 再被任何"用户数据"写入使用。 |
| **FR-8** | 冻结形态下，`registry_dir()` 指向的路径 **MUST NOT** 落在 `sys.executable` 所在目录之内。 |

---

## 3. Non-Functional Requirements

| ID | 要求 | 怎么验 |
|---|---|---|
| **NFR-1** | 现有 **575 项**测试全绿，一条断言不改。 | 跑全量 |
| **NFR-2** | 源码运行下，预设默认位置从"仓库根 `presets/`"**变为** `%LOCALAPPDATA%\MPVConfigBuilder\presets\`。这是**有意的行为变更**，必须在文档里写明。 | 测试 + 文档 |
| **NFR-3** | 测试 **MUST NOT** 往真实的 `%LOCALAPPDATA%\MPVConfigBuilder\` 写任何东西。 | 逐项检查测试用的覆盖 |
| **NFR-4** | `paths.describe()` **SHOULD** 增加 `user_data_dir` 一项，方便排错时一眼看出数据写在哪。 | 读 `api_status` 输出 |

---

## 4. Acceptance Criteria

| ID | Given / When / Then | 追溯 |
|---|---|---|
| **AC-1** | Given 设了 `LOCALAPPDATA=C:\X`，When 调 `user_data_dir()`，Then 返回 `C:\X\MPVConfigBuilder`。 | FR-1 |
| **AC-2** | Given **没有** `LOCALAPPDATA`，When 调 `user_data_dir()`，Then 返回 `<home>\MPVConfigBuilder`（不抛异常）。 | FR-1 |
| **AC-3** | Given 设了 `DSH_MPV_DATA_DIR`，When 调 `user_data_dir()`，Then 返回该值（**优先于** `LOCALAPPDATA`）。 | FR-3 |
| **AC-4** | Given 调了 `set_user_data_dir(tmp)`，When 调 `user_data_dir()`，Then 返回 `tmp`；再 `set_user_data_dir(None)` 后恢复按环境变量算。 | FR-3 |
| **AC-5** | Given **冻结形态**（`is_frozen()` 为真、`sys.executable` 指向假 exe），When 调 `registry_dir()`，Then 结果**不在** exe 所在目录之下。 | FR-4, FR-8 |
| **AC-6** | Given 源码形态，When 调 `registry_dir()`，Then 也不是仓库根的 `presets/`（而是用户数据目录下的）。 | FR-4, NFR-2 |
| **AC-7** | Given 设了 `DSH_MPV_PRESET_DIR`，When 调 `registry_dir()`，Then 返回该值（**优先于** `user_data_dir()`）。 | FR-5 |
| **AC-8** | Given 调了 `set_registry_dir(tmp)`，When 存/列/删预设，Then 全在 `tmp` 里，用户数据目录**不被创建**。 | FR-5, NFR-3 |
| **AC-9** | Given 改了 `user_data_dir()` 的指向，When 存一个预设，Then 文件落在新指向的 `presets/` 下。 | FR-4 |
| **AC-10** | Given 默认设置，When 调 `dlcenter.manifest_path()`，Then 文件名仍是 `installed.json`、父目录仍是 `%LOCALAPPDATA%\MPVConfigBuilder`。 | FR-6 |
| **AC-11** | Given 默认设置，When 读 `schema.SETTINGS_PATH`，Then 文件名仍是 `settings.json`、父目录仍是 `%LOCALAPPDATA%\MPVConfigBuilder`。 | FR-6 |
| **AC-12** | Given 源码形态，When 调 `describe()`，Then 含 `user_data_dir` 键且值等于 `user_data_dir()`。 | NFR-4 |
| **AC-13** | Given `writable_root()`，When grep 全仓库，Then**除 `paths.py` 自身与文档/注释外**没有调用者。 | FR-7 |

---

## 5. Edge Cases

| ID | 情况 | 期望 |
|---|---|---|
| **EC-1** | `LOCALAPPDATA` 是空串 | 当作没设置（退回 home），**不是** `Path("")/"MPVConfigBuilder"` |
| **EC-2** | `DSH_MPV_DATA_DIR` 是空串 | 同上，忽略 |
| **EC-3** | 用户数据目录不存在 | `registry_dir()` 负责 `mkdir(parents=True, exist_ok=True)`（保持现状） |
| **EC-4** | 目录不可写（权限错） | 抛出可读的异常/返回失败，**不允许**静默假装成功 |
| **EC-5** | `set_registry_dir("")` 传空串 | 视同 `None`（复位），不是"切到当前目录" |
| **EC-6** | 已存在的旧仓库根 `presets/` 目录 | **不自动迁移、不删除** —— 但要在文档里告诉用户"老位置的文件请自己挪"，并给出一条命令 |

---

## 6. API Contract

```python
# core/paths.py
def user_data_dir() -> Path:
    """用户级数据目录：%LOCALAPPDATA%\\MPVConfigBuilder（拿不到就 ~/MPVConfigBuilder）。"""

def set_user_data_dir(path) -> None:
    """覆盖（测试/工具用）。传 None 复位。"""

# 环境变量：DSH_MPV_DATA_DIR（优先于 LOCALAPPDATA 默认值）
```

---

## 7. Data Models（受影响的位置）

| 文件 | 现在 | 改后 |
|---|---|---|
| `<user_data>/settings.json` | `schema.SETTINGS_PATH`（已是） | 不变（改走 `user_data_dir()`） |
| `<user_data>/installed.json` | `dlcenter.manifest_path()`（已是） | 不变（改走 `user_data_dir()`） |
| **`<user_data>/presets/*.json`** | **`<writable_root>/presets/`** | **改** |

---

## 8. Out of Scope

| 不做 | 理由 |
|---|---|
| **自动迁移旧 `presets/`** | 源码运行下的旧位置就在仓库根，用户自己一眼能看到；自动搬文件属于"对用户数据动手"，违反本项目一贯的"显式动作"原则。给文档 + 一条命令即可（EC-6）。 |
| **改 `writable_root()` 本身** | 它对"导出到 exe 旁边"仍有正确用途（FR-7）。 |
| **`installer.default_install_dir()`** | 它写的是 `%LOCALAPPDATA%\mpv-lazy`（**mpv 的**目录，不是本工具的），语义不同，不该合并。 |
| **把 `%LOCALAPPDATA%` 做成可配置的 GUI 选项** | 现在没这个需求；环境变量已经够测试与高级用户用。 |

---

## 9. 验收命令

```powershell
py -m unittest discover -s tests -t .      # NFR-1：575 项不许改
py -m unittest tests.test_paths tests.test_presetfile
py -X utf8 tools/check_docs.py
py -X utf8 tools/preflight.py
```

---

## 10. 验收记录（2026-09-14 实施）

### AC 逐条结果

| AC | 怎么验的 | 结果 |
|---|---|---|
| AC-1 用 `LOCALAPPDATA` | `test_ac1_uses_localappdata` | ✅ |
| AC-2 没有 `LOCALAPPDATA` 退回 home、不抛异常 | `test_ac2_falls_back_to_home` | ✅ |
| AC-3 `DSH_MPV_DATA_DIR` 优先 | `test_ac3_env_override_wins` | ✅ |
| AC-4 `set_user_data_dir()` 能覆盖/复位 | `test_ac4_setter_and_reset` | ✅ |
| AC-5 ⭐ 冻结形态下不在 exe 目录内 | `test_ac5_frozen_never_writes_inside_exe_dir`（造假安装目录 + 假 `sys.executable`） | ✅ |
| AC-6 源码形态也不再写仓库根 | `test_ac6_source_mode_uses_user_data_not_repo` | ✅ |
| AC-7 `DSH_MPV_PRESET_DIR` 优先 | `test_ac7_preset_dir_env_still_wins` | ✅ |
| AC-8 `set_registry_dir()` 优先且不碰用户目录 | `test_ac8_setter_still_wins_and_creates_nothing_else` | ✅ |
| AC-9 存下来的预设真落在新位置 | `test_ac9_saving_lands_in_user_data_dir` | ✅ |
| AC-10 `manifest_path()` 形状不变 | `test_ac10_manifest_path_shape` | ✅ |
| AC-11 `SETTINGS_PATH` 形状不变 | `test_ac11_settings_path_shape` | ✅ |
| AC-12 `describe()` 含 `user_data_dir` | `test_ac12_describe_includes_it` | ✅ |
| AC-13 除 `paths.py` 外无 `writable_root()` 调用者 | `test_only_paths_module_calls_writable_root` | ✅ |

### NFR 结果

| NFR | 目标 | 实测 |
|---|---|---|
| NFR-1 旧测试全绿 | 575 项一条断言不改 | ⚠ **改了 1 条**（见下） |
| NFR-2 预设默认位置变更，写进文档 | — | ✅ 见 §11 |
| NFR-3 测试不碰真实用户目录 | — | ✅ `IsolationTest` 子进程前后比对；实跑后确认真目录只剩原有的 `settings.json` |
| NFR-4 `describe()` 增加一项 | — | ✅ |

**总计：595 项测试全绿（575 旧 + 20 新）。**

### ⚠ 唯一改掉的那条旧断言

`tests/test_presetfile.py::test_default_is_under_writable_root` 断言的是
"预设目录在 `writable_root()` 下" —— **那正是本 spec 要修的错误行为**。
它留着就说明 bug 还在。已改名为 `test_default_is_under_user_data_dir`，
并**顺带加了一条更强的** `test_default_is_not_next_to_the_exe`
（显式造冻结形态验证）。

这不是"为了过测试而改测试"：旧断言编码的是被交付的缺陷。

---

## 11. 行为变更（用户需要知道）

**用户预设的存放位置变了：**

| | 旧位置 | 新位置 |
|---|---|---|
| 源码运行 | `<仓库根>/presets/` | `%LOCALAPPDATA%\MPVConfigBuilder\presets\` |
| 打包运行 | **`<exe 目录>/presets/`（只读，会失败）** | 同上（**一致**） |

**老用户怎么办**：源码运行下，旧的预设就在仓库根的 `presets/` 里，
**不会自动迁移**（自动搬用户数据违反本项目"对用户数据只做显式动作"的原则）。
手动挪一条命令：

```powershell
move "presets\*.json" "$env:LOCALAPPDATA\MPVConfigBuilder\presets\"
```

好处是：**源码态与打包态位置一致**，所以"源码跑时存的预设，装成应用后还能用"。

---

## 12. 实施中发现的教训

### 为什么这个 bug 能活这么久：两个隔离恰好把 bug 也隔离掉了

`registry_dir()` 走 `writable_root()` 是**一直就错**的，但一直没被发现，因为：

1. **开发机跑的是源码形态** → `writable_root()` = 仓库根，**能写**，看不出问题；
2. **所有测试都用 `set_registry_dir()` 把目录指到临时目录** → 恰好绕开了那条错误路径。

这是"**为了不污染环境而做的隔离，顺手把被测行为也隔离掉了**"的典型。
所以本次新增的测试**特意造出冻结形态**（假 `sys.executable` + `sys.frozen`），
而不是继续用覆盖绕开。

### 三处重复的路径拼法

`%LOCALAPPDATA%\MPVConfigBuilder\` 这个拼法原本散在 `schema.py`、
`dlcenter.py`、`installer.py`。前两处已统一到 `user_data_dir()`。
`installer.py` 那条**故意不动** —— 它写的是 `%LOCALAPPDATA%\mpv-lazy`
（**mpv 的**目录，不是本工具的），语义不同。

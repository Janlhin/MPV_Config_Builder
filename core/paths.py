# -*- coding: utf-8 -*-
"""路径解析：让"数据文件在哪"在**源码运行**与**打包运行**下都成立。

为什么需要单独一个模块：打包（PyInstaller）之后，代码和数据会被放进一个临时目录，
`Path(__file__).parent.parent` 那套算法会指到**解包目录**里 —— 如果打包时没把
`data/` 与 `docs/` 一起带上，界面里的"文档/致谢"页就会 404，而且只有在打包产物里
才会发现（源码跑永远是对的）。这个坑就是《问题清单》P2-6 记的那条。

约定（打包时必须照做，见 docs/engineering/release.md）：

    源码运行   repo/                        ← 本文件在 repo/core/paths.py
    打包运行   sys._MEIPASS/                ← PyInstaller 的解包目录
               ├── core/  webui/            （代码）
               ├── data/                    （必须 --add-data）
               └── docs/                    （必须 --add-data，界面文档在这里）

所以打包命令里必须带上：
    --add-data "data;data"  --add-data "docs;docs"
"""
import os
import sys
from pathlib import Path


def is_frozen():
    """现在是不是跑在打包产物里。"""
    return bool(getattr(sys, "frozen", False))


def bundle_root():
    """代码与数据所在的根目录。

    · 打包后：`sys._MEIPASS`（onefile 是解包临时目录，onedir 是 exe 同级的 _internal）
    · 源码运行：仓库根目录（本文件的上一级）
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        # 没有 _MEIPASS（比如某些 onedir 配置）：退回 exe 所在目录
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir():
    """`data/*.json` 所在目录（找不到就返回候选路径，由调用方判存在）。"""
    return bundle_root() / "data"


def doc_path(name):
    """`docs/` 里的某份界面文档（打包后是解包目录 `docs/` 里的同名文件）。

    2026-11-25 起界面文档按 `user/{zh-CN,en}/` 分层；调用方传入相对
    `docs/` 的路径（例如 ``user/zh-CN/getting-started.md``），不要只写文件名。
    """
    return bundle_root() / "docs" / name


def writable_root():
    """**可以往里写**的目录（"导出 / 另存为"这类**用户可见的落点**）。

    打包后 `bundle_root()` 是临时解包目录 —— 往那里写会随进程结束消失，
    所以导出/另存用这个（优先 exe 同目录，源码运行就是仓库根）。

    ⚠⚠ **不要拿它存"用户数据"**（预设、设置、安装清单这类）。
    冻结形态下它是 **exe 所在目录** —— 装到 `Program Files` 就是**只读**，
    写入会**静默失败**，而且**只在装完之后才暴露**（开发机上复现不了）。
    用户数据一律用 `user_data_dir()`。
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# 用户数据目录的覆盖（测试与工具用；传 None 复位）
_USER_DATA_OVERRIDE = None


def user_data_dir():
    """**用户级数据目录**：`%LOCALAPPDATA%\\MPVConfigBuilder`。

    放预设、设置、安装清单这类"属于这个用户"的东西。三条规矩，每条都对应一个真实的坑：

    ① **不依赖 `is_frozen()`** —— 用户数据的位置在源码运行与打包运行下**必须一致**，
       否则"源码跑时存的预设，打包后找不到"，换种启动方式数据就像丢了。

    ② **拿不到 `LOCALAPPDATA` 就退回 `~/MPVConfigBuilder`**，不能抛异常；
       **空串要当成没设置** —— 否则 `Path("")/"MPVConfigBuilder"` 会变成**相对路径**，
       写到哪全看当前工作目录（这是最阴的一种错）。

    ③ **覆盖优先于环境变量默认值**：`DSH_MPV_DATA_DIR` → `set_user_data_dir()`。
       两个覆盖途径是给测试用的 —— **测试绝不能往真实用户目录写东西**。

    原来这条 `%LOCALAPPDATA%\\MPVConfigBuilder\\` 的拼法在 `schema.py` 与
    `dlcenter.py` 里各抄了一遍，现在统一到这儿。
    """
    if _USER_DATA_OVERRIDE is not None:
        return Path(_USER_DATA_OVERRIDE)
    env = (os.environ.get("DSH_MPV_DATA_DIR") or "").strip()
    if env:
        return Path(env)
    base = (os.environ.get("LOCALAPPDATA") or "").strip() or str(Path.home())
    return Path(base) / "MPVConfigBuilder"


def set_user_data_dir(path):
    """把用户数据目录指到别处（测试/工具用）。传 `None` 或空串复位。"""
    global _USER_DATA_OVERRIDE
    s = str(path).strip() if path is not None else ""
    _USER_DATA_OVERRIDE = Path(s) if s else None


def describe():
    """给"关于"页/排错用：把关键路径一次说清。"""
    return {
        "frozen": is_frozen(),
        "bundle_root": str(bundle_root()),
        "data_dir": str(data_dir()),
        "writable_root": str(writable_root()),
        "user_data_dir": str(user_data_dir()),
        "python": sys.executable,
    }


__all__ = ["is_frozen", "bundle_root", "data_dir", "doc_path",
           "writable_root", "user_data_dir", "set_user_data_dir", "describe"]

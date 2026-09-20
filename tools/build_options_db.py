# -*- coding: utf-8 -*-
"""重新生成 mpv 全量选项数据库 JSON。

用法::

    py -3 tools\\build_options_db.py

mpv 升级后重新导出 ``mpv.com --list-options > _mpv_options_raw.txt``，
再跑一次本脚本即可刷新 ``data/mpv_options_zh.json``。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.options_db import DB_PATH, build_db  # noqa: E402


def main():
    db = build_db()
    meta = db["meta"]

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(db, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    size_kb = DB_PATH.stat().st_size / 1024
    print(
        "顶层 %d 项 / 有中文 %d 项 / 分类 %d 个"
        % (meta["count"], meta["with_zh"], len(db["groups"]))
    )
    print("已写入 %s（%.1f KB）" % (DB_PATH, size_kb))
    print("分类：" + "、".join(db["groups"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""按键绑定接口的端到端验证：读真实文件 + 往临时目录写。

用法：py -3 tests/_api_keys.py http://127.0.0.1:端口
"""
import json
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8811"
REAL = Path(r"C:\Program Files\mpv-lazy\portable_config")

fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("  OK  " if ok else " FAIL ") + name + ("  " + str(detail) if detail else ""))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# 1) 读真实配置
r = get("/api/keys?target=" + urllib.parse.quote(str(REAL)))
show("读取键位表", r.get("ok"), f"主文件={Path(r.get('main','')).name} 来源={r.get('source')}")
binds = [x for f in r["files"] for x in f["rows"] if x["kind"] == "bind"]
show("解析出行", len(binds) >= 100, f"{len(binds)} 条绑定")
show("内置默认带命令", len(r["defaults"]) > 100 and bool(r["defaults"][0]["cmd"]),
     f"{len(r['defaults'])} 条，例：{r['defaults'][0]['key']} -> {r['defaults'][0]['cmd']}")
show("命令表可用", len(r["commands"]) > 50, f"{len(r['commands'])} 条")
show("生效视图", len(r["effective"]) >= len(r["defaults"]),
     f"{len(r['effective'])} 行，被覆盖 {len([x for x in r['effective'] if x['overridden']])} 个键")
show("无冲突", r["warnings"] == [], r["warnings"])

# 2) 往临时目录写（不碰真实文件）
tmp = Path(tempfile.mkdtemp())
try:
    (tmp / "mpv.conf").write_text('input-conf = "~~/input_test.conf"\n', encoding="utf-8")
    src = REAL / "input_uosc.conf"
    shutil.copy2(src, tmp / "input_test.conf")
    before = (tmp / "input_test.conf").read_bytes()

    r2 = get("/api/keys?target=" + urllib.parse.quote(str(tmp)))
    show("临时目录也能读", r2["main"].endswith("input_test.conf"), r2["main"])

    rows = next(f["rows"] for f in r2["files"] if f["path"] == r2["main"])
    # 未改动直接保存 → 文件应当一字不变
    s = post("/api/keys/save", {"path": r2["main"], "rows": rows})
    show("原样保存成功", s.get("ok"), s.get("detail"))
    show("未改动的文件逐字节一致", (tmp / "input_test.conf").read_bytes() == before)

    # 真改一条再存
    target = next(x for x in rows if x["kind"] == "bind" and x["key"] == "l")
    target["key"] = "Ctrl+l"
    target["comment"] = "播放 > 我改的"
    s2 = post("/api/keys/save", {"path": r2["main"], "rows": rows})
    show("改一条后保存", s2.get("ok"), s2.get("detail"))
    text = (tmp / "input_test.conf").read_text(encoding="utf-8")
    show("新键写进去了", "Ctrl+l" in text and "播放 > 我改的" in text)
    show("自动备份", bool(list(tmp.glob("input_test.conf.bak-*"))))
    others = [x for x in rows if x["kind"] == "bind" and x["key"] not in ("Ctrl+l", "")]
    show("其它行没被动过", all((x["raw"] in text) for x in others[:20]))

    # 空命令要拦住
    bad = [dict(x) for x in rows]
    victim = next(x for x in bad if x["kind"] == "bind" and x["enabled"] and x["cmd"])
    victim["cmd"] = "   "
    s3 = post("/api/keys/save", {"path": r2["main"], "rows": bad})
    show("空命令被拒绝", not s3.get("ok"), s3.get("detail"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n失败项：" + str(fails))
sys.exit(1 if fails else 0)

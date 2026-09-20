# -*- coding: utf-8 -*-
"""针对 A 类修复的接口级验证：读 mpv.conf 的 include 链、profile、编码。"""
import json
import sys
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8801"
TARGET = r"C:\Program Files\mpv-lazy\portable_config"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("  OK  " if ok else " FAIL ") + name + ("  " + str(detail) if detail else ""))


cat = get("/api/catalog")
print("可选配置：", [(c["name"], c["kind"]) for c in cat["configs"]])

r = post("/api/config/load", {"path": TARGET + r"\mpv.conf"})
show("读 mpv.conf", r.get("ok"))
print("  编码:", r.get("encoding"), "换行:", r.get("newline"), "全局键:", len(r.get("values", {})))
print("  include 链:", [(f["name"], f["count"], f["encoding"]) for f in r["chain"]["files"]])
print("  生效键数:", r["chain"]["effective_count"], " profile 数:", len(r["profiles"]))
show("include 链被跟随", len(r["chain"]["files"]) > 1, [f["name"] for f in r["chain"]["files"]])
# mpv-lazy 的 include 目标都是 profile 集合：它们不该往全局值里塞任何东西
show("include 里的 profile 不污染全局值",
     all(v == "mpv.conf" for v in r["chain"]["sources"].values()),
     f"来源文件集合={sorted(set(r['chain']['sources'].values()))}")
show("include 过来的 profile 也在链里可见", len(r["chain"]["profiles"]) >= 7,
     [x["name"] for x in r["chain"]["profiles"]][:8])
show("vf 标签解析", r.get("memc_label") is not None, f"label={r.get('memc_label')!r} memc={r.get('memc')!r}")

p = post("/api/config/load", {"path": TARGET + r"\profiles.conf"})
show("读 profiles.conf", p.get("ok"))
show("profile 文件不污染全局值", p["values"] == {}, f"values={p['values']} profiles={len(p['profiles'])}")
show("profile 名单完整", len(p["profiles"]) >= 5, [x["name"] for x in p["profiles"]][:8])
show("有 profile 警告", any("profile" in w for w in p["warnings"]), p["warnings"][:1])
first = p["profiles"][0]
show("profile 带自己的选项", bool(first["values"]), f"{first['name']} -> {first['values']}")

raw = get("/api/raw?path=" + urllib.parse.quote(TARGET + r"\mpv.conf"))
show("raw 读带回编码信息", "encoding" in raw, raw.get("encoding"))

pv = post("/api/config/preview", {"target": TARGET, "write_mode": "merge",
                                 "source": TARGET + r"\mpv.conf",
                                 "state": {"values": {"scale": "spline36"}, "shaders": [],
                                           "memc": "", "disable": []}})
show("merge 预览带写回编码", bool(pv.get("encoding")), pv.get("encoding"))

print("\n失败项：" + str(fails))
sys.exit(1 if fails else 0)

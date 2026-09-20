# -*- coding: utf-8 -*-
"""端到端检查 webui 后端接口（不起浏览器，直接打 HTTP）。"""
import json
import sys
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def show(name, ok, detail=""):
    print(("  OK  " if ok else " FAIL ") + name + ("  " + str(detail) if detail else ""))
    return ok


fails = 0
st = get("/api/status")
fails += not show("status", bool(st.get("title")), f"{st['title']} v{st['version']} lazy={st['lazy_pc']!r}")
print("       counts:", st["counts"])

cat = get("/api/catalog")
fails += not show("catalog", cat.get("ok"), f"target={cat['target']!r} shaders={len(cat['shaders'])} memc={len(cat['memc'])} configs={[c['name'] for c in cat['configs']]}")

opts = get("/api/options")
fails += not show("options", bool(opts.get("core")), f"core={len(opts['core'])} native={len(opts['native'])}")

combos = get("/api/combos")
fails += not show("combos", combos.get("ok"), f"{len(combos['combos'])} 套")
for c in combos["combos"]:
    print(f"       {c['icon']} {c['name']}: shader={len(c['shaders'])} memc={c['memc'] or '-'} missing={c['missing']}")

state = {
    "values": {"vo": "gpu-next", "scale": "ewa_lanczossharp", "deband-iterations": "2",
               "sub-font": "sans-serif"},
    "shaders": [c["shaders"][0] for c in combos["combos"] if c["shaders"]][:2],
    "memc": next((c["memc"] for c in combos["combos"] if c["memc"]), ""),
    "custom": "profile-cond=not playlist",
    "disable": [],
}
pv = post("/api/config/preview", {"target": cat["target"], "write_mode": "include", "state": state})
fails += not show("config/preview", pv.get("ok"), f"summary={pv.get('summary')} issues={pv.get('issues')}")
print("---- 预览文本 ----")
print(pv.get("text", "")[:1200])
print("------------------")

an = post("/api/analyze", {"text": pv.get("text", "")})
fails += not show("analyze", an.get("ok"), f"综合={an.get('overall')} / {an.get('grade')} {an.get('scores')}")

raw = get("/api/raw?path=" + urllib.parse.quote(str(cat["target"]) + "/mpv.conf"))
fails += not show("raw 读", raw.get("ok"), f"{raw.get('size')} B")

ld = post("/api/config/load", {"path": str(cat["target"]) + "/mpv.conf"})
fails += not show("config/load", ld.get("ok"), f"present={len(ld.get('present', []))} shaders={len(ld.get('shaders', []))} memc={ld.get('memc')!r}")

print("\n失败项：" + str(fails))
sys.exit(1 if fails else 0)

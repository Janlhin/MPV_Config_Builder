# -*- coding: utf-8 -*-
"""接口级验证：冲突检测有没有真的出现在预览接口里。"""
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8802"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def show(name, ok, detail=""):
    print(("  OK  " if ok else " FAIL ") + name + ("  " + str(detail) if detail else ""))
    return ok


fails = 0
state = {
    "values": {"vo": "gpu", "interpolation": "yes", "video-sync": "audio",
               "sigmoid-upscaling": "yes", "linear-upscaling": "yes",
               "icc-profile": "C:/x.icc", "target-trc": "pq",
               "deband": "yes", "deband-iterations": "0"},
    "shaders": ["~~/shaders/FSRCNNX/FSRCNNX_x2_16_0_4_1.glsl",
                "~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_M.glsl"],
    "memc": "~~/vs/MEMC_RIFE_NV.vpy",
}
r = post("/api/config/preview", {"target": "", "write_mode": "include", "state": state})
fails += not show("预览返回冲突字段", "conflicts" in r, f"{len(r.get('conflicts', []))} 条")
for c in r.get("conflicts", []):
    print(f"       [{c['level']}] {c['title']}")
print("  体检条目：")
for lv, msg in r.get("issues", []):
    print(f"       ({lv}) {msg}")

clean = {"values": {"vo": "gpu-next", "scale": "spline36"}, "shaders": [], "memc": ""}
r2 = post("/api/config/preview", {"target": "", "write_mode": "include", "state": clean})
fails += not show("干净配置没有冲突", r2.get("conflicts") == [], r2.get("conflicts"))

a = post("/api/analyze", {"text": "vo=gpu\nlinear-upscaling=yes\nsigmoid-upscaling=yes\n"})
fails += not show("analyze 也带冲突", bool(a.get("conflicts")), len(a.get("conflicts", [])))

print("\n失败项：" + str(fails))
sys.exit(1 if fails else 0)

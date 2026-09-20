# -*- coding: utf-8 -*-
r"""实机验证「我自己的预设」（advanced.html 的「快速预设」分区）。

跑法（仓库根目录）：
    py -3 webui\server.py --port 8765 --no-window     # 另开一个窗口
    py -3 tools\check_presets.py

为什么值得单独验：预设这套东西前后端各一半 —— 后端有 40 多项单元测试，
但"点按钮到底有没有反应、存完列表刷不刷新、导出的文件能不能再导回来"
只有真跑才知道。

⚠ 它会往**用户数据目录**写文件（W-2 之后是
`%LOCALAPPDATA%\MPVConfigBuilder\presets`，**不是仓库根的 `presets/`**），
所以脚本**先问运行中的服务**那个目录在哪、确认是空的才继续，跑完再清掉。
"""
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # 仓库根（本文件在 tools/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from uidriver import launch, connect, wait_page, stop, Checker   # noqa: E402

SHOTS = ROOT / "_shots"
PORT = 9225
BASE = "http://127.0.0.1:8765"
URL = BASE + "/advanced.html#preset"


def preset_dir_from_server():
    """问运行中的服务：预设目录到底在哪。

    不自己拼路径 —— W-2 之后它是 `%LOCALAPPDATA%\\MPVConfigBuilder\\presets`，
    而这是**服务端**根据 `core.paths.user_data_dir()` 决定的（还受
    `DSH_MPV_DATA_DIR` 影响）。脚本再猜一遍迟早对不上。
    """
    try:
        with urllib.request.urlopen(f"{BASE}/api/userpresets", timeout=10) as r:
            d = json.loads(r.read().decode("utf-8"))
        p = d.get("dir")
        return Path(p) if p else None
    except Exception:
        return None


def main():
    # ⚠ 预设目录在 W-2 之后是**用户数据目录**（`%LOCALAPPDATA%\MPVConfigBuilder\presets`），
    # **不是仓库根的 `presets/`** —— 那是重构前的旧位置。
    # 所以这里要问**运行中的服务**它到底用哪个目录，不能自己猜。
    reg = preset_dir_from_server()
    if reg is None:
        sys.exit("⚠ 读不到预设目录（服务没起来？先按文件头那两行起服务）")
    # ⚠ 空目录不算 —— 打开预设卡片本身就会建出 `presets/`（list_presets 会 mkdir），
    # 所以"目录存在"根本不代表"里面有你的预设"。只看有没有文件。
    if reg.exists() and any(reg.iterdir()):
        sys.exit(f"⚠ {reg} 里已经有东西了 —— 先挪开再跑，"
                 "免得把测试预设和你自己的混在一起")
    check = Checker()
    proc = launch(PORT)
    try:
        c = connect(PORT)
        wait_page(c, URL)

        def shot(name):
            c.shot(SHOTS / name)

        print("== 卡片渲染 ==")
        check("「我自己的预设」卡片在", c.js("!!document.getElementById('myPresetCard')"))
        check("按钮和文件框都在", c.js("""(() => ['myPresetName','myPresetSave',
            'myPresetExport','myPresetImport','myPresetFile','myPresetBtns']
            .every(i => !!document.getElementById(i)))()"""))
        check("接线成功（onclick / onchange 都挂上了）", c.js("""(() => {
            const b = document.getElementById('myPresetSave');
            const f = document.getElementById('myPresetFile');
            return typeof b.onclick === 'function' && typeof f.onchange === 'function';
        })()"""))
        empty_hint = c.js("document.getElementById('myPresetBtns').textContent") or ""
        check("空列表时给了说明（不是一片空白）", "还没有存过预设" in empty_hint,
              empty_hint[:50])
        shot("40_我的预设_空.png")

        print("== 存一套 ==")
        c.js("""(() => {
          setOption('vo', 'gpu-next');
          setOption('scale', 'ewa_lanczossharp');
          APP.shaders = ['~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_M.glsl'];
          changed();
        })()""")
        time.sleep(0.4)
        check("当前状态里有 3 项要存",
              c.js("countPresetItems(currentPresetState())") == 3)
        c.js("document.getElementById('myPresetName').value = '看番那套'")
        c.js("document.getElementById('myPresetSave').click()")
        time.sleep(1.2)
        lst = c.js("""(() => {
          const box = document.getElementById('myPresetBtns');
          return {text: box.textContent, n: box.querySelectorAll('button').length};
        })()""")
        check("列表里出现了新预设", lst["n"] == 1 and "看番那套" in lst["text"],
              json.dumps(lst, ensure_ascii=False)[:100])
        check("名字框被清空", c.js("document.getElementById('myPresetName').value") == "")
        check("磁盘上真有这个文件", (reg / "看番那套.json").is_file())
        saved = json.loads((reg / "看番那套.json").read_text(encoding="utf-8"))
        check("文件内容对得上",
              saved["state"]["values"].get("vo") == "gpu-next"
              and len(saved["state"]["shaders"]) == 1,
              json.dumps(saved["state"], ensure_ascii=False)[:110])
        shot("41_我的预设_存好了.png")

        print("== 同名再存要问一句 ==")
        c.js("window.confirm = () => true")
        c.js("setOption('vo', 'gpu')")
        time.sleep(0.3)
        c.js("document.getElementById('myPresetName').value = '看番那套'")
        c.js("document.getElementById('myPresetSave').click()")
        time.sleep(1.2)
        again = json.loads((reg / "看番那套.json").read_text(encoding="utf-8"))
        check("确认后覆盖成功", again["state"]["values"].get("vo") == "gpu",
              str(again["state"]["values"].get("vo")))
        check("还是只有一个预设", c.js(
            "document.getElementById('myPresetBtns').querySelectorAll('button').length") == 1)

        c.js("window.confirm = () => false")
        c.js("document.getElementById('myPresetName').value = '看番那套'")
        c.js("document.getElementById('myPresetSave').click()")
        time.sleep(1.0)
        still = json.loads((reg / "看番那套.json").read_text(encoding="utf-8"))
        check("点取消就不覆盖", still["state"]["values"].get("vo") == "gpu")

        print("== 套用回当前状态 ==")
        c.js("window.confirm = () => true")
        c.js("clearAll()")
        time.sleep(0.6)
        before = c.js("""(() => ({vo: APP.values['vo'] || null,
            n: Object.keys(APP.values).length}))()""")
        # ⚠ 预设卡片在页面靠下，按钮可能落在视口外 —— 不滚过去的话
        # CDP 派发的真实鼠标事件打在视口外，等于没点（踩过：y=1182 > 900 视口）。
        c.js("document.getElementById('myPresetBtns').scrollIntoView({block:'center'})")
        time.sleep(0.5)
        box = c.js("""(() => { const b = document.querySelector('#myPresetBtns button');
            if (!b) return null; const r = b.getBoundingClientRect();
            return {x: Math.round(r.left + r.width/2),
                    y: Math.round(r.top + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height)}; })()""")
        check("预设按钮在视口内（真实鼠标点得到）",
              bool(box) and 0 < box["y"] < 900 and box["w"] > 0,
              json.dumps(box, ensure_ascii=False))
        if box and box["w"] > 0:
            c.click(box["x"], box["y"])
        time.sleep(1.2)
        after = c.js("""(() => ({vo: APP.values['vo'] || null,
            shaders: APP.shaders.length}))()""")
        check("真实鼠标点一下就套上了", after["vo"] == "gpu" and after["shaders"] == 1,
              f"之前 {json.dumps(before, ensure_ascii=False)}"
              f" 之后 {json.dumps(after, ensure_ascii=False)}")

        # 事件路径之外，再直接验一次"套用"本身 —— 上面那条万一被重渲染的
        # 时序影响（卡片是异步渲染出来的），这条能明确区分"功能坏了"还是"点空了"
        c.js("clearAll()")
        time.sleep(0.5)
        direct = c.js("""(() => {
          const r = {ok: true};
          try { applyMyPreset({id: '看番那套', name: '看番那套',
            state: {values: {vo: 'gpu-next', scale: 'ewa'}, shaders: [], memc: '', disable: []}}); }
          catch (e) { r.ok = false; r.err = String(e); }
          return {ok: r.ok, err: r.err || '', vo: APP.values['vo'] || null};
        })()""")
        check("applyMyPreset 本身工作正常", direct["ok"] and direct["vo"] == "gpu-next",
              json.dumps(direct, ensure_ascii=False))

        print("== 导出 ==")
        c.js("""(() => {
          window._dl = null;
          const orig = HTMLAnchorElement.prototype.click;
          HTMLAnchorElement.prototype.click = function () {
            if (this.download) { window._dl = this.download; return; }
            return orig.apply(this, arguments);
          };
        })()""")
        # ⚠ 导出的入口在**列表项**上（每个预设各有一个 ⬇️），不是卡片底下那个按钮 ——
        # 底下那个导的是"当前状态"。同样要先滚进视口再点。
        c.js("""(() => { const b = document.querySelector('#myPresetBtns [data-op="export"]');
            if (b) b.scrollIntoView({block: 'center'}); })()""")
        time.sleep(0.5)
        eb = c.js("""(() => { const b = document.querySelector('#myPresetBtns [data-op="export"]');
            if (!b) return null; const r = b.getBoundingClientRect();
            return {x: Math.round(r.left + r.width/2),
                    y: Math.round(r.top + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height)}; })()""")
        check("导出按钮在视口内", bool(eb) and 0 < eb["y"] < 900 and eb["w"] > 0,
              json.dumps(eb, ensure_ascii=False))
        if eb and eb["w"] > 0:
            c.click(eb["x"], eb["y"])
        time.sleep(1.2)
        check("触发下载且文件名跟预设名一致", c.js("window._dl") == "看番那套.json",
              str(c.js("window._dl")))

        print("== 导出当前状态（卡片底下的按钮）==")
        # ⚠ 这一条必须在**状态非空**时跑：clearAll() 之后就"没东西可导"，
        # 后端会正当地拒绝（"一个选项都没勾"），那是设计不是 bug。
        # 顺序写反过一次，白排查了一轮。
        c.js("""(() => { setOption('vo', 'gpu-next');
            setOption('scale', 'ewa_lanczossharp'); changed(); })()""")
        time.sleep(0.5)
        c.js("window._dl = null")
        c.js("document.getElementById('myPresetExport').click()")
        time.sleep(1.2)
        dl2 = c.js("window._dl")
        check("卡片底下的按钮导的是当前状态",
              isinstance(dl2, str) and dl2.endswith(".json"), str(dl2))

        c.js("clearAll()")
        time.sleep(0.4)
        c.js("window._dl = null")
        c.js("document.getElementById('myPresetExport').click()")
        time.sleep(1.0)
        check("清空后导出被正当拒绝（不是导出个空文件）",
              c.js("window._dl") is None, str(c.js("window._dl")))

        print("== 导入（走 /api/presets/load 的 text 分支）==")
        good = {"kind": "mpv-config-builder-preset", "version": 1, "name": "别人给的",
                "state": {"values": {"vo": "gpu-next", "hwdec": "nvdec"},
                          "shaders": [], "memc": "", "disable": []}}
        r = c.js("(async () => await API.userPresetLoad({text: %s}))()"
                 % json.dumps(json.dumps(good, ensure_ascii=False)))
        check("合法内容能导入", r and r.get("ok"),
              json.dumps(r, ensure_ascii=False)[:120])
        bad = {"name": "别人的配置", "vo": "gpu"}
        r2 = c.js("(async () => await API.userPresetLoad({text: %s}))()"
                  % json.dumps(json.dumps(bad, ensure_ascii=False)))
        check("别的 json 被明确拒绝", r2 and not r2.get("ok"))
        check("拒绝理由说得清",
              "不是 MPV Config Builder" in ((r2 or {}).get("detail") or ""),
              ((r2 or {}).get("detail") or "")[:70])
        r3 = c.js("(async () => await API.userPresetLoad({text: '{ not json'}))()")
        check("坏 JSON 也被拦住而不是崩掉", r3 and not r3.get("ok"))

        print("== 删除 ==")
        c.js("""(() => { const b = document.querySelector(
            '#myPresetBtns [data-op="del"]'); if (b) b.click(); })()""")
        time.sleep(1.2)
        check("删完列表空了", c.js(
            "document.getElementById('myPresetBtns').querySelectorAll('button').length") == 0)
        check("磁盘上的文件也没了", not (reg / "看番那套.json").exists())

        return check.done()
    finally:
        stop(proc)
        if reg.exists():
            shutil.rmtree(reg, ignore_errors=True)
            print(f"（已清理测试用的 {reg}）")


if __name__ == "__main__":
    sys.exit(main())

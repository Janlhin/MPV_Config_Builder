# -*- coding: utf-8 -*-
"""自绘候选下拉的实机验证（CDP，零依赖）。

跑法（仓库根目录）：
    py -3 webui\\server.py --port 8765 --no-window     # 另开一个窗口
    py -3 tools\\check_ui.py

为什么非要真机跑一遍：
  · 白底大气泡之所以改不动，正因为它不在 DOM 里、截图工具也抓不到。
    换成自绘之后它就进了 DOM —— **"能截到"本身就是"已经脱离浏览器 UI 层"的证据**。
  · 光靠读代码会漏掉布局与事件顺序的问题。开发时漏过两次：
      ① 未勾选的行把 input 单独藏了、外壳还在，`getBoundingClientRect()` 全是 0，
         面板按 (0,0) 定位飘到页面左上角；
      ② 面板项的点击走冒泡、document 的委托走捕获，捕获先把面板关掉，
         项自己的 handler 拿不到 input，于是"点候选完全没反应"。
    两个都只有真跑才看得见（第一个还能靠截图，第二个连报错都没有）。

⚠ 需要本机有 Edge 或 Chrome。
截图落在仓库根的 `_shots/`。
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent      # 仓库根（本文件在 tools/ 下）
SHOTS = ROOT / "_shots"
PORT = 9222
URL = "http://127.0.0.1:8765/advanced.html#g:字幕样式"


def find_browser():
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(c):
            return c
    sys.exit("没找到 Edge / Chrome")


class CDP:
    """极简 WebSocket 客户端（只够用 CDP：文本帧、无分片、服务端帧不掩码）。"""

    def __init__(self, ws_url):
        import socket
        u = urlparse(ws_url)
        s = socket.create_connection((u.hostname, u.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
                   "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
                   ).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += s.recv(4096)
        assert b"101" in buf.split(b"\r\n")[0], buf[:200]
        self.sock, self.buf, self.n = s, buf.split(b"\r\n\r\n", 1)[1], 0

    def _frame(self, payload):
        data, mask = payload.encode(), os.urandom(4)
        n = len(data)
        hdr = b"\x81"
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + n.to_bytes(2, "big")
        else:
            hdr += bytes([0x80 | 127]) + n.to_bytes(8, "big")
        self.sock.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _exact(self, n):
        out = self.buf
        while len(out) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError
            out += chunk
        self.buf = out[n:]
        return out[:n]

    def _read(self):
        _, b1 = self._exact(2)
        ln = b1 & 0x7F
        if ln == 126:
            ln = int.from_bytes(self._exact(2), "big")
        elif ln == 127:
            ln = int.from_bytes(self._exact(8), "big")
        return self._exact(ln).decode("utf-8", "replace")

    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self._frame(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self._read())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(str(r["exceptionDetails"])[:400])
        return r.get("result", {}).get("value")

    def click(self, x, y):
        for t in ("mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=t, x=x, y=y,
                      button="left", clickCount=1)

    def key(self, name, vk):
        self.call("Input.dispatchKeyEvent", type="rawKeyDown", key=name, code=name,
                  windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        self.call("Input.dispatchKeyEvent", type="keyUp", key=name, code=name,
                  windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)


def center(c, sel, idx=None):
    expr = (f"(() => {{ const els = document.querySelectorAll({sel!r});"
            f" const el = els[{idx if idx is not None else 0}];"
            " if (!el) return null; const r = el.getBoundingClientRect();"
            " return {x: Math.round(r.left + r.width/2),"
            "         y: Math.round(r.top + r.height/2),"
            "         w: Math.round(r.width), h: Math.round(r.height)}; })()")
    return c.js(expr)


def panel(c):
    return c.js("""(() => {
      const p = document.querySelector('.combo-pop');
      if (!p) return {open:false};
      const cs = getComputedStyle(p), r = p.getBoundingClientRect();
      return {open:true, items: p.querySelectorAll('.combo-item').length,
              text: [...p.querySelectorAll('.combo-item')].map(x=>x.textContent),
              bg: cs.backgroundColor, color: cs.color, z: cs.zIndex,
              rect: [Math.round(r.left), Math.round(r.top),
                     Math.round(r.width), Math.round(r.height)]};
    })()""")


def main():
    SHOTS.mkdir(exist_ok=True)
    profile = tempfile.mkdtemp(prefix="dsh-cdp-")
    proc = subprocess.Popen([
        find_browser(), "--headless=new", f"--remote-debugging-port={PORT}",
        f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
        "--window-size=1440,900", "--hide-scrollbars",
        "--force-device-scale-factor=1", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fails = []

    def check(label, cond, detail=""):
        print(("  ✅ " if cond else "  ❌ ") + label + (f"  {detail}" if detail else ""))
        if not cond:
            fails.append(label)

    try:
        ws = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=1) as f:
                    tabs = json.load(f)
                page = next((t for t in tabs if t["type"] == "page"), None)
                if page:
                    ws = page["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not ws:
            sys.exit("浏览器没起来")

        c = CDP(ws)
        c.call("Page.enable")
        c.call("Runtime.enable")
        c.call("Page.navigate", url=URL)
        time.sleep(4.0)

        def shot(name):
            r = c.call("Page.captureScreenshot", format="png")
            (SHOTS / name).write_bytes(base64.b64decode(r["data"]))

        print("== 结构 ==")
        check("选项区渲染出来了", c.js("!!document.querySelector('.opt')"))
        check("监听已绑定（document._comboWired）", c.js("!!document._comboWired"))
        check("主题是深色", c.js("getComputedStyle(document.documentElement).colorScheme") == "dark")
        info = c.js("""(() => {
          const row = [...document.querySelectorAll('.opt')].find(r => r.dataset.key === 'sub-font');
          const input = row.querySelector('[data-role="value"]');
          return {tag: input.tagName, hasList: input.hasAttribute('list'),
                  opts: (input._options || []).length,
                  arrow: !!row.querySelector('[data-role="combo-toggle"]'),
                  noDatalist: !document.querySelector('datalist')};
        })()""")
        check("sub-font 用 input 而不是 select", info["tag"] == "INPUT")
        check("没有 list= 属性（白气泡的来源）", not info["hasList"])
        check("页面里没有 <datalist> 元素", info["noDatalist"])
        check("候选值已经进了 JS 属性", info["opts"] == 3, f"opts={info['opts']}")
        check("有下拉箭头按钮", info["arrow"])

        print("== 未勾选的行：控件理应整体隐藏（外壳不能留） ==")
        hid = c.js("""(() => {
          const row = document.querySelector('.opt[data-key="sub-font"]');
          const combo = row.querySelector('.combo');
          const arrow = row.querySelector('[data-role="combo-toggle"]');
          const ar = arrow ? arrow.getBoundingClientRect() : null;
          return {on: row.classList.contains('on'),
                  comboHidden: getComputedStyle(combo).display === 'none',
                  arrowW: ar ? Math.round(ar.width) : null};
        })()""")
        check("未勾选时整行没有值控件", (not hid["on"]) and hid["comboHidden"],
              json.dumps(hid, ensure_ascii=False))
        check("外壳一起隐藏，箭头也没有几何（否则面板会飘到 0,0）",
              hid["arrowW"] == 0, f"arrowW={hid['arrowW']}")

        print("== 【未勾选】直接点候选：应当自动勾选并写进配置 ==")
        # 控件是隐藏的，用程序勾选是不行的 —— 要模拟"用户展开后点了一项"。
        # 这条正是最初那个死胡同：选了却没生效，用户完全不知道为什么。
        c.js("""(() => { const row = document.querySelector('.opt[data-key="sub-font"]');
          openCombo(row.querySelector('[data-role="value"]')); })()""")
        time.sleep(0.4)
        dbg = c.js("""(() => {
          const p = document.querySelector('.combo-pop');
          if (!p) return {open:false};
          const els = [...p.querySelectorAll('.combo-item')];
          const r = p.getBoundingClientRect();
          const hit = els.map(e => { const q = e.getBoundingClientRect();
            return {t:e.textContent, box:[Math.round(q.left),Math.round(q.top),
              Math.round(q.width),Math.round(q.height)],
              pe: getComputedStyle(e).pointerEvents, vis: getComputedStyle(e).visibility}; });
          const el = document.elementFromPoint(Math.round(r.left+20), Math.round(r.top+30));
          return {open:true, popRect:[Math.round(r.left),Math.round(r.top),
                    Math.round(r.width),Math.round(r.height)],
                  items:hit, topMost: el ? (el.className || el.tagName) : null};
        })()""")
        print("     诊断:", json.dumps(dbg, ensure_ascii=False))
        shot("26_未勾选_下拉.png")
        # 把事件顺序记下来：到底是没触发 click，还是触发了但 comboPick 没跑
        c.js("""(() => {
          window._evlog = [];
          const it = document.querySelectorAll('.combo-item')[1];
          ['mousedown','mouseup','click','pointerdown','pointerup'].forEach(t =>
            it.addEventListener(t, e => window._evlog.push(t + '@' + e.target.textContent), true));
          const oc = window.comboPick;
          window.comboPick = function (v) { window._evlog.push('comboPick(' + v + ')'); return oc.apply(this, arguments); };
          return true;
        })()""")
        it0 = center(c, '.combo-item', 1)
        want0 = c.js("document.querySelectorAll('.combo-item')[1].textContent")
        c.click(it0["x"], it0["y"])
        time.sleep(0.6)
        print("     事件顺序:", c.js("JSON.stringify(window._evlog)"))
        auto = c.js("""(() => { const row = document.querySelector('.opt[data-key="sub-font"]');
          return {value: row.querySelector('[data-role="value"]').value,
                  checked: row.querySelector('[data-role="check"]').checked,
                  rowOn: row.classList.contains('on'),
                  inValues: APP.values['sub-font'] === undefined ? null : APP.values['sub-font']}; })()""")
        check("点候选项会自动勾选（不是死胡同）", auto["checked"], json.dumps(auto, ensure_ascii=False))
        check("值进了输入框", auto["value"] == want0, f"{auto['value']} vs {want0}")
        check("值进了 APP.values（会写进配置）", auto["inValues"] == want0, str(auto["inValues"]))
        shot("22_组合框_选中.png")

        # 复位成未勾选，继续测"已勾选"那条路（下拉默认是藏着的）
        c.js("""(() => { const row = document.querySelector('.opt[data-key="sub-font"]');
          const b = row.querySelector('[data-role="check"]');
          b.checked = false; b.dispatchEvent(new Event('change', {bubbles:true}));
          closeCombo(); })()""")
        time.sleep(0.4)

        print("== 勾选后才显示控件（一屏多看一倍选项的设计） ==")
        c.js("""(() => { const row = document.querySelector('.opt[data-key="sub-font"]');
          const b = row.querySelector('[data-role="check"]');
          b.checked = true; b.dispatchEvent(new Event('change', {bubbles:true})); })()""")
        time.sleep(0.5)
        shown = c.js("""(() => {
          const row = document.querySelector('.opt[data-key="sub-font"]');
          const combo = row.querySelector('.combo');
          const input = row.querySelector('[data-role="value"]');
          const r = input.getBoundingClientRect();
          return {on: row.classList.contains('on'),
                  comboShown: getComputedStyle(combo).display !== 'none',
                  rect: [Math.round(r.left), Math.round(r.top),
                         Math.round(r.width), Math.round(r.height)]};
        })()""")
        check("勾选后控件出现", shown["on"] and shown["comboShown"],
              json.dumps(shown, ensure_ascii=False))
        check("输入框有真实几何（不是 0×0）",
              shown["rect"][2] > 0 and shown["rect"][3] > 0, str(shown["rect"]))

        print("== 打开下拉：点箭头 ==")
        ab = center(c, '.opt[data-key="sub-font"] [data-role="combo-toggle"]')
        check("箭头按钮有几何尺寸", ab and ab["w"] > 0 and ab["h"] > 0, str(ab))
        c.click(ab["x"], ab["y"])
        time.sleep(0.5)
        p = panel(c)
        check("面板打开了", p.get("open"), json.dumps(p, ensure_ascii=False))
        if p.get("open"):
            check("候选值都在", p["items"] == 3, str(p.get("text")))
            check("面板是深色（不是白气泡）", p["bg"] == "rgb(23, 28, 38)", p["bg"])
            check("文字是浅色", p["color"] == "rgb(232, 235, 242)", p["color"])
            # 关键：面板要贴在这个输入框旁边，不能飘到 (0,0)
            inp = shown["rect"]
            near = abs(p["rect"][0] - inp[0]) <= 12 and abs(p["rect"][1] - (inp[1] + inp[3])) <= 12
            check("面板贴在输入框下方（没飘到左上角）", near,
                  f"面板{p['rect']} vs 输入框{inp}")
            check("面板宽度不小于输入框", p["rect"][2] >= inp[2],
                  f"{p['rect'][2]} vs {inp[2]}")

        print("== 过滤 ==")
        c.js("""(() => { const i = document.querySelector('.opt[data-key="sub-font"] [data-role="value"]');
                  i.value='Micro'; i.dispatchEvent(new Event('input', {bubbles:true})); })()""")
        time.sleep(0.4)
        fl = c.js("""(() => { const p = document.querySelector('.combo-pop');
          return {n: p.querySelectorAll('.combo-item').length,
                  empty: !!p.querySelector('.combo-empty'),
                  emptyText: (p.querySelector('.combo-empty')||{}).textContent || ''}; })()""")
        check("过滤没结果时给提示而不是空白", fl["n"] == 0 and fl["empty"], str(fl))
        shot("20_组合框_过滤无结果.png")

        c.js("""(() => { const i = document.querySelector('.opt[data-key="sub-font"] [data-role="value"]');
                  i.value='Wen'; i.dispatchEvent(new Event('input', {bubbles:true})); })()""")
        time.sleep(0.4)
        fl2 = c.js("""[...document.querySelectorAll('.combo-item')].map(x=>x.textContent)""")
        check("过滤 'Wen' 命中 LXGW", fl2 == ["LXGW WenKai Lite"], str(fl2))

        c.js("""(() => { const i = document.querySelector('.opt[data-key="sub-font"] [data-role="value"]');
                  i.value=''; i.dispatchEvent(new Event('input', {bubbles:true})); })()""")
        time.sleep(0.4)
        shot("21_组合框_展开.png")

        print("== 点击选择（已勾选的行） ==")
        it = center(c, '.combo-item', 2)
        picked_text = c.js("document.querySelectorAll('.combo-item')[2].textContent")
        c.click(it["x"], it["y"])
        time.sleep(0.6)
        res = c.js("""(() => ({
          value: document.querySelector('.opt[data-key="sub-font"] [data-role="value"]').value,
          popOpen: !!document.querySelector('.combo-pop'),
          checked: document.querySelector('.opt[data-key="sub-font"] [data-role="check"]').checked,
          rowOn: document.querySelector('.opt[data-key="sub-font"]').classList.contains('on'),
          inValues: APP.values['sub-font'] === undefined ? null : APP.values['sub-font']
        }))()""")
        check("值填进了输入框", res["value"] == picked_text, f"{res['value']} vs {picked_text}")
        check("选完就收起面板", not res["popOpen"])
        check("复选框保持勾选", res["checked"])
        check("rows 标记为已选", res["rowOn"])
        check("值真的进了 APP.values（会写进配置）",
              res["inValues"] == picked_text, str(res["inValues"]))
        shot("22b_组合框_点击选中.png")

        print("== 键盘 ==")
        c.js("document.querySelector('.opt[data-key=\"sub-font\"] [data-role=\"value\"]').click()")
        time.sleep(0.3)
        if not c.js("!!document.querySelector('.combo-pop')"):
            c.js("openCombo(document.querySelector('.opt[data-key=\"sub-font\"] [data-role=\"value\"]'))")
        time.sleep(0.3)
        check("面板已开（键盘测试前置）", c.js("!!document.querySelector('.combo-pop')"))
        if c.js("!!document.querySelector('.combo-pop')"):
            c.key("ArrowDown", 40)
            k1 = c.js("(() => { const a=document.querySelector('.combo-item.active');"
                      " return a ? a.textContent : null; })()")
            c.key("ArrowDown", 40)
            k2 = c.js("(() => { const a=document.querySelector('.combo-item.active');"
                      " return a ? a.textContent : null; })()")
            check("ArrowDown 能逐项往下走", k1 is not None and k2 is not None and k1 != k2,
                  f"{k1} → {k2}")
            c.key("ArrowUp", 38)
            k3 = c.js("(() => { const a=document.querySelector('.combo-item.active');"
                      " return a ? a.textContent : null; })()")
            check("ArrowUp 能往回走", k3 == k1, f"{k3} vs {k1}")
            shot("23_组合框_键盘高亮.png")

            print("== Esc：关下拉，但不能顺手也关抽屉 ==")
            c.js("openDrawer({key:'sub-font', label:'字幕字体', desc:'键盘测试'})")
            time.sleep(0.4)
            drawer_before = c.js("document.getElementById('drawer').classList.contains('open')")
            c.key("Escape", 27)
            time.sleep(0.4)
            check("Esc 关掉了下拉", not c.js("!!document.querySelector('.combo-pop')"))
            check("Esc 之后抽屉还开着（没被误关）",
                  c.js("document.getElementById('drawer').classList.contains('open')"),
                  f"之前={drawer_before}")
            c.js("closeDrawer()")

        print("== 点别处收起 ==")
        c.js("openCombo(document.querySelector('.opt[data-key=\"sub-font\"] [data-role=\"value\"]'))")
        time.sleep(0.3)
        was = c.js("!!document.querySelector('.combo-pop')")
        c.js("document.getElementById('secTitle').click()")
        time.sleep(0.3)
        check("点白处后面板收起",
              was and not c.js("!!document.querySelector('.combo-pop')"))

        print("== 浅色主题 ==")
        c.js("document.documentElement.dataset.theme='light'")
        c.js("openCombo(document.querySelector('.opt[data-key=\"sub-font\"] [data-role=\"value\"]'))")
        time.sleep(0.5)
        lp = panel(c)
        check("浅色主题下面板跟着变浅", lp.get("open") and lp["bg"] == "rgb(255, 255, 255)",
              str(lp.get("bg")))
        shot("24_组合框_浅色.png")
        c.js("document.documentElement.dataset.theme='dark'")
        c.js("closeCombo()")

        print("== 完全体页面（原生层）也要能用 ==")
        c.call("Page.navigate", url="http://127.0.0.1:8765/expert.html")
        time.sleep(4.0)
        # 完全体默认只渲染一个分组（每屏几十项），搜索框只挂在「全部选项」那一屏。
        c.js("""(() => {
          const chip = document.querySelector('[data-sec="dbsearch"], [data-id="dbsearch"]');
          if (chip) chip.click();
        })()""")
        time.sleep(1.0)
        found = c.js("""(() => {
          const inp = document.getElementById('q');
          if (!inp) return false;
          inp.value = 'dither';
          inp.dispatchEvent(new Event('input', {bubbles:true}));
          return true;
        })()""")
        if not found:
            c.js("""(async () => { DB.q = 'dither'; await loadDb(true); })()""")
        time.sleep(3.0)
        e1 = c.js("""(() => {
          const rows = [...document.querySelectorAll('.opt')];
          const withOpts = [...document.querySelectorAll('.opt input[data-options]')];
          const withSel = [...document.querySelectorAll('.opt select[data-role="value"]')];
          const nonEmpty = withOpts.filter(i => (i._options||[]).length);
          return {keys: rows.map(r => r.dataset.key),
                  opts: withOpts.length, sels: withSel.length,
                  nonEmpty: nonEmpty.length,
                  empty: withOpts.length - nonEmpty.length,
                  sample: nonEmpty.slice(0,3).map(i => ({k: i.closest('.opt').dataset.key,
                    n: (i._options||[]).length}))};
        })()""")
        check("完全体渲染出来了", len(e1["keys"]) > 0, json.dumps(e1["keys"], ensure_ascii=False))
        check("封闭枚举走原生 select", e1["sels"] > 0, str(e1["sels"]))
        check("自由填的项走组合框（input）", e1["opts"] > 0, str(e1["opts"]))

        # 完全体这里没有任何"带候选值的组合框" —— 这不是 bug，是数据决定的：
        # mpv 的类型系统里 Choice/Flag 一律自带取值表（=> 封闭，走 select），
        # String/Float/Integer 一律没有（=> 自由填，候选只能来自精选层的建议值）。
        # 而完全体暴露的是 813 条原始库条目，**没有精选层建议**，所以 options 全空。
        # 直接把这条不变量钉住：哪天有人往完全体里硬塞建议值，这里会红。
        check("完全体没有'带候选值的组合框'（符合 mpv 类型模型，不是缺陷）",
              e1["nonEmpty"] == 0 and e1["empty"] == e1["opts"],
              f"nonEmpty={e1['nonEmpty']} empty={e1['empty']} opts={e1['opts']}")

        # 0 候选的下拉仍应能打开并给出"没有候选值"的说明（不能是空白）
        first = c.js("""(() => {
          const i = document.querySelector('.opt input[data-options]');
          if (!i) return null;
          const row = i.closest('.opt');
          row.querySelector('[data-role="check"]').checked = true;
          row.classList.add('on');
          const combo = row.querySelector('.combo');
          if (combo) combo.classList.add('show');
          const r = i.getBoundingClientRect();
          return {key: row.dataset.key, x: Math.round(r.left + r.width/2),
                  y: Math.round(r.top + r.height/2)};
        })()""")
        time.sleep(0.4)
        c.click(first["x"], first["y"])
        time.sleep(0.5)
        ep = panel(c)
        check(f"完全体 {first['key']} 的下拉能打开", ep.get("open"),
              json.dumps(ep, ensure_ascii=False)[:200])
        if ep.get("open"):
            check("完全体面板同样是深色（不是白气泡）",
                  ep["bg"] == "rgb(23, 28, 38)", ep["bg"])
            note = c.js("""(() => { const e = document.querySelector('.combo-empty');
              return e ? e.textContent : null; })()""")
            check("没有候选值时给说明而不是空白", bool(note), str(note))
            shot("25_完全体_组合框.png")

        print()
        if fails:
            print(f"❌ {len(fails)} 项没过：")
            for f in fails:
                print("   - " + f)
            sys.exit(1)
        print("✅ 全部通过")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()

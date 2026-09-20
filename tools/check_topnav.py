# -*- coding: utf-8 -*-
"""U-1 实机验证：9 个页面的顶栏是否都有「体检 / 快捷键 / 下载中心」常驻入口。

为什么要真机跑：这个功能**完全是 JS 注入的**，静态看 HTML 一个入口都看不到。
只有让真实浏览器把 api.js 跑一遍，才能知道注入有没有生效、有没有撞上页面自己的
变量或 DOM 结构（下载中心的入参就叫 target，正是这类坑的高发区）。

顺带验证「当前页」那一条是不可点的指示、其它两条是真链接。

用法（会自己起一个临时后端，端口自动挑）：
    py -3 tools/check_topnav.py
"""
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from uidriver import Checker, connect, launch, stop, wait_page   # noqa: E402

SHOTS = ROOT / "_shots"
PAGES = [
    ("index.html", "index"), ("basic.html", "basic"), ("advanced.html", "advanced"),
    ("expert.html", "expert"), ("analyze.html", "analyze"), ("keys.html", "keys"),
    ("downloads.html", "downloads"), ("guide.html", "guide"), ("hell.html", "hell"),
]
WANT = [("analyze.html", "配置体检", "🩺"),
        ("keys.html", "快捷键", "⌨️"),
        ("downloads.html", "下载中心", "📦")]
# 哪个页面是「导航页」——在这几页上必须有一条不可点的「当前页」指示
NAV_PAGES = {"analyze": "analyze.html", "keys": "keys.html", "downloads": "downloads.html"}

# 每页读一次顶栏：返回注入结果的原始结构，判定都放在 Python 里做
PROBE = """
(() => {
  const nav = document.querySelector('.topnav');
  if (!nav) return {found: false};
  const pill = el => ({
    tag: el.tagName.toLowerCase(),
    label: (el.querySelector('span:not(.topnav-ico):not(.topnav-dot)') || {}).textContent || '',
    href: el.getAttribute('href') || '',
    ico: (el.querySelector('.topnav-ico') || {}).textContent || '',
    clickable: el.tagName.toLowerCase() === 'a',
    current: el.getAttribute('aria-current') === 'page'
  });
  return {
    found: true,
    page: document.body.dataset.page || '',
    items: [...nav.children].map(pill),
    // 也看一眼页面本身有没有报错（注入代码抛异常的话这里会体现出来）
    hasTopbar: !!document.querySelector('.topbar')
  };
})()
"""


# 读「实际生效的样式」。为什么要这一项：
# 第一版给导航项套了 class="btn small topnav-link"，然后在 CSS 里写
# `.topnav-link{border:none;background:none}` —— 权重同为 (0,2,0) 但 `.btn.small`
# 在后面，把导航项全变成了带框的按钮，当前页那条更是「按钮框 + 下划线」两套视觉打架。
# 光看截图只会以为"样式没调好"，是读计算样式才定位到根因的。
# 这条断言就是防止有人（包括我）再把按钮 class 加回来。
STYLE_PROBE = """
(() => {
  const pick = el => {
    const cs = getComputedStyle(el), a = getComputedStyle(el, '::after');
    return {cls: el.className, borderW: cs.borderTopWidth, bg: cs.backgroundColor,
            color: cs.color, weight: cs.fontWeight,
            afterBg: a.backgroundColor, afterH: a.height, afterContent: a.content};
  };
  const nav = document.querySelector('.topnav');
  return {
    links: [...nav.querySelectorAll('.topnav-link')].map(pick),
    cur: nav.querySelector('.topnav-cur') ? pick(nav.querySelector('.topnav-cur')) : null
  };
})()
"""

ACCENT_RGB = "rgb(106, 168, 255)"
TRANSPARENT = "rgba(0, 0, 0, 0)"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(port):
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"),
         "--port", str(port), "--no-window"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as f:
                json.load(f)
            return proc
        except Exception:
            if proc.poll() is not None:
                sys.exit("后端启动失败（进程已退出）")
            time.sleep(0.4)
    proc.kill()
    sys.exit("后端 30 秒内没起来")


def main():
    port, cdp_port = free_port(), free_port()
    srv = browser = None
    c = Checker()
    try:
        srv = start_server(port)
        print(f"后端已起：http://127.0.0.1:{port}\n")
        browser = launch(cdp_port)
        cdp = connect(cdp_port)
        SHOTS.mkdir(exist_ok=True)

        base = f"http://127.0.0.1:{port}/"
        for name, page in PAGES:
            wait_page(cdp, base + name, wait_s=2.2)
            got = cdp.js(PROBE)
            print(f"—— {name} ——")
            if not c(f"{name}：顶栏注入了 .topnav", bool(got.get("found"))):
                continue
            # 链接地址：**可点的那两条**必须地址正确；
            # 当前页那条是不可点的 span，本来就该没有 href（空串才是对的）
            items = got["items"]
            labels = [i["label"] for i in items]
            c(f"{name}：三个入口齐全，顺序一致",
              labels == [w[1] for w in WANT], f"实际 {labels}")

            icons = {i["label"]: i["ico"] for i in items}
            c(f"{name}：图标正确",
              all(icons.get(lbl) == ico for _, lbl, ico in WANT), f"实际 {icons}")

            bad_href = []
            for href, lbl, _ in WANT:
                it = next((i for i in items if i["label"] == lbl), None)
                if it is None:
                    bad_href.append(f"{lbl}=缺失")
                elif it["current"]:
                    if it["href"]:
                        bad_href.append(f"{lbl}=当前页却带了地址 {it['href']!r}")
                elif it["href"] != href:
                    bad_href.append(f"{lbl}={it['href']!r} 应为 {href!r}")
            c(f"{name}：链接地址正确（可点的对、当前页无地址）",
              not bad_href, "；".join(bad_href))

            # 当前页那一条必须不可点，其它两条必须可点
            cur = [i for i in items if i["current"]]
            if page in NAV_PAGES:
                c(f"{name}：当前页显示为不可点指示",
                  len(cur) == 1 and not cur[0]["clickable"],
                  f"current={[(i['label'], i['clickable']) for i in cur]}")
                want_lbl = next(lbl for href, lbl, _ in WANT if href == NAV_PAGES[page])
                c(f"{name}：当前页指示指向自己（{want_lbl}）",
                  len(cur) == 1 and cur[0]["label"] == want_lbl,
                  f"current={[i['label'] for i in cur]}")
            else:
                c(f"{name}：不是导航页，不应有「当前页」标记", not cur,
                  f"current={[i['label'] for i in cur]}")
                c(f"{name}：三个入口都可点",
                  all(i["clickable"] for i in items),
                  f"实际 {[(i['label'], i['clickable']) for i in items]}")
            c(f"{name}：页面保留了顶栏", got["hasTopbar"])

            # 样式：导航项必须是"文字"，不能带上按钮的边框底色
            st = cdp.js(STYLE_PROBE)
            bad = []
            for i, li in enumerate(st["links"]):
                if li["borderW"] != "0px":
                    bad.append(f"第{i+1}项有边框 {li['borderW']}")
                if li["bg"] != TRANSPARENT:
                    bad.append(f"第{i+1}项有底色 {li['bg']}")
                if "btn" in li["cls"]:
                    bad.append(f"第{i+1}项还带着按钮 class: {li['cls']}")
            c(f"{name}：导航项没有按钮样式（无边框/无底色）", not bad, "；".join(bad))

            if st["cur"]:
                cur_ok = (st["cur"]["color"] == ACCENT_RGB
                          and st["cur"]["afterBg"] == ACCENT_RGB
                          and st["cur"]["afterH"] == "2px"
                          and st["cur"]["afterContent"] != "none"
                          and st["cur"]["borderW"] == "0px"
                          and "btn" not in st["cur"]["cls"])
                c(f"{name}：当前页是主色 + 2px 下划线，且不带按钮框", cur_ok,
                  f"color={st['cur']['color']} 下划线={st['cur']['afterBg']}/"
                  f"{st['cur']['afterH']} 边框={st['cur']['borderW']} cls={st['cur']['cls']}")
            cdp.shot(str(SHOTS / f"60_顶栏_{page}.png"))
        print()
        return c.done()
    finally:
        stop(browser)
        if srv:
            srv.terminate()
            try:
                srv.wait(timeout=10)
            except Exception:
                srv.kill()


if __name__ == "__main__":
    raise SystemExit(main())

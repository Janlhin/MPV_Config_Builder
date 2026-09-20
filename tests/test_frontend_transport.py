# -*- coding: utf-8 -*-
"""前端不许绕过 API 层直连 HTTP（W-4 第③步的结构性防线）。

## 为什么需要这条测试

第③步把传输换成 stdio 之后，**页面里任何一处 `fetch('/api/...')` 都会在
Electron 下静默失效** —— 因为 stdio 模式下根本没有 HTTP 服务。
而这种错**在浏览器里开发时完全看不出来**（浏览器下 fetch 照样通）。

实测：改传输时有 4 处直连被漏掉 ——
`index.html`（status）、`state.js`（catalog）、`expert.html`（db/options）、
`guide.html`（guide）。是 `tools/check_stdio_ui.py`（真浏览器 + 真 stdio 后端）
逮出来的。但那个脚本要本机有 Edge/Chrome，不是每次都会跑。

所以这里补一条**零依赖的静态检查**：直接扫源码里有没有 `fetch('/api/...')`。
它不需要浏览器、不需要起服务，跑测试就会带上。

## 为什么只扫 `/api/` 而不扫所有 fetch

`api.js` 自己**必须**用 fetch（HTTP 模式就是它的实现）。所以规则是：
**除了 `api.js`（传输层本身），任何地方都不许直接 fetch `/api/`。**
只查 `/api/` 前缀，别的一律不管 —— 判据窄一点才不会变成"天天误报然后被无视"。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "webui" / "static"

# 传输层自己：它就是干这个的
ALLOWED = {"api.js"}

# 匹配 fetch('/api/...') / fetch("/api/...") / fetch(`/api/...`)
PATTERN = re.compile(r"""fetch\(\s*[`'"]/api/""")

# 排除掉注释行 —— 我在几处改动里写了「不要直接 fetch」的注释，
# 里面带着这个形状的字样（比如 state.js 那句"不能直接 fetch"）。
# 不排除的话会被自己的注释绊倒。
COMMENT_LINE = re.compile(r"^\s*(//|/\*|\*|<!--)")


class NoDirectApiFetchTest(unittest.TestCase):
    def test_pages_do_not_fetch_api_directly(self):
        offenders = []
        for f in sorted(list(STATIC.glob("*.js")) + list(STATIC.glob("*.html"))):
            if f.name in ALLOWED:
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if COMMENT_LINE.match(line):
                    continue
                if PATTERN.search(line):
                    offenders.append(f"{f.name}:{i}: {line.strip()[:100]}")
        if offenders:
            self.fail(
                "有代码绕过 API 层直接 fetch('/api/...') —— 这在 Electron 的 stdio "
                "通道下会静默失效（那种模式下没有 HTTP 服务）。请改用 API.xxx()：\n  "
                + "\n  ".join(offenders))

    def test_allowlist_file_still_uses_fetch(self):
        """反向验证：规则不是把 api.js 整个排除掉就完事 —— HTTP 模式仍要能用。

        如果哪天 api.js 里连 fetch 都没有了，这条会红，提醒我这条 allowlist
        已经失去意义（说明传输层被换掉了，规则也该跟着改）。
        """
        src = (STATIC / "api.js").read_text(encoding="utf-8")
        self.assertIn("fetch(", src, "api.js 里居然没有 fetch —— HTTP 传输是不是被删了？")

    def test_the_guard_actually_matches_this_shape(self):
        """自检：正则确实认得出我们要拦的写法。

        （光靠"现在没人违规"证明不了防线有效 —— 那种测试在正则写错时也是绿的。）
        """
        for sample in ("const r = await fetch('/api/status')",
                       'await fetch("/api/keys?target=x")',
                       "fetch(`/api/guide?doc=${d}`)"):
            self.assertRegex(sample, PATTERN, f"没认出来：{sample}")
        # 负样本：非 /api 的 fetch 不该被拦
        for sample in ("fetch('https://example.com/x')",
                       "fetch('/__bridge__')",
                       "fetch('data.json')"):
            self.assertNotRegex(sample, PATTERN, f"误报：{sample}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

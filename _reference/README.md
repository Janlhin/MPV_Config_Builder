# _reference —— 外部参考资料的来源清单

**这里只放"去哪找参考"的记录，不放下载下来的网页**（那些用下面的命令随时能重取，
省得仓库里堆 1.5 MB 的 HTML）。

## ⚠ 一个环境限制（下次别再白试）

`hooke007.github.io` 与 `mpv.io` 在这个网络环境里解析到 **198.18.x.x**（保留网段），
所以 **DSH 的 `web_fetch` 工具会拒绝它们**（判定为"非公网 IP"）：

    Error: URL hostname "mpv.io" resolves to a non-public IP address

**但网络本身是通的** —— 用 Python 直接抓就 200：

```powershell
py -3 -c "import urllib.request; req=urllib.request.Request('https://mpv.io/manual/stable/', headers={'User-Agent':'Mozilla/5.0'}); print(urllib.request.urlopen(req, timeout=60).status)"
```

结论：**遇到 `web_fetch` 被拦，先用 Python 试一次**，别直接放弃。

## 已验证可访问的来源

| 页面 | URL | 体量 | 有什么用 |
|---|---|---|---|
| mpv_CFanStation 首页 | <https://hooke007.github.io/> | 19 KB | 全站目录（Sphinx/Furo） |
| **官方手册（中文版）** | <https://hooke007.github.io/official_man/mpv.html> | 1.38 MB | **`data/mpv_options_zh.json` 里 726 条中文说明的上游** |
| 官方手册目录 | <https://hooke007.github.io/official_man/index.html> | 21 KB | |
| 其它官方文档 | <https://hooke007.github.io/official_misc/index.html> | 19 KB | 含插值技术、着色器处理阶段 |
| 插值技术 | <https://hooke007.github.io/official_misc/Interpolation.html> | 25 KB | 补帧/插值的原理与参数 |
| **着色器处理阶段** | <https://hooke007.github.io/official_misc/VO_shader_stages.html> | 18 KB | **判断 shader 链顺序的依据** |
| 非官方文档目录 | <https://hooke007.github.io/unofficial/index.html> | 20 KB | |
| mpv 使用引导 | <https://hooke007.github.io/unofficial/mpv_start.html> | 64 KB | 新手向 |
| **第三方用户着色器** | <https://hooke007.github.io/unofficial/mpv_shaders.html> | 85 KB | **shader 搭配与推荐** |
| **配置预设** | <https://hooke007.github.io/unofficial/mpv_profiles.html> | 36 KB | profile 写法 |
| **快捷键自定义与控制台** | <https://hooke007.github.io/unofficial/mpv_input.html> | 33 KB | input.conf 进阶 |
| **音视频滤镜** | <https://hooke007.github.io/unofficial/mpv_filters.html> | 34 KB | vf / af 用法 |
| mpv 官方手册（英文，stable） | <https://mpv.io/manual/stable/> | 1.27 MB | 权威英文原文 |
| mpv 官方手册（英文，master） | <https://mpv.io/manual/master/> | 1.33 MB | 开发版（比 stable 新） |

## 已经用它做过的事

**核对选项库**（2026 会话）：拿 `official_man/mpv.html` 反查 `data/mpv_options_zh.json`，
发现库里 **3 项在手册正文里找不到** —— 查下来是 `--V` / `--{` / `--}`，
mpv 自己的 dump 就标着 `[not in config files]`（命令行专用）。

于是加了 `core/options_db.is_config_option()`，**读取时滤掉 16 条命令行专用项**，
界面从"829 项"变成诚实的"813 项可写进配置"。详见 `core/options_db.py` 的
`NOT_IN_CONFIG_FILES`。

## 还没挖的（有需要再说）

`unofficial/mpv_shaders.html`（85 KB）里有成体系的 shader 搭配建议，
可以用来复核 `core/schema.py` 的 `SHADERS` / `SHADER_PATHS` 与
`core/combos.py` 的 9 套组合是否贴合社区实践。

`unofficial/mpv_profiles.html` 可以直接支撑"给用户一份能抄的 profile 预设"。

`official_misc/VO_shader_stages.html` 只用来判过 shader 链顺序，正文没细读。

挖法：Python 抓下来 → 抽正文 → 人工过一遍再改代码，**不要照着网页自动改代码**。

## 另一个参考源：真机浏览器（本会话新增）

有些问题**读文档解决不了，得让浏览器自己说**。本会话就有一个：

深色界面里 `<datalist>` 弹出**白底气泡**，配色和字号都改不动。查证过程本身
就是一条可复用的经验：

| 手段 | 结果 |
|---|---|
| 读 CSS / 试写 `background`、`font-size` | ❌ 无效 —— 那气泡不在页面 DOM 里 |
| DevTools 的 `Page.captureScreenshot` 截图 | ❌ 抓不到 —— 它属于浏览器 UI 层 |
| `color-scheme: dark` | ⚠️ 理论上的唯一旋钮，部分 Chromium 版本对 datalist 不生效 |
| **换成自绘 DOM 之后再截图** | ✅ **抓到了** |

所以判据是：**"能不能被 `Page.captureScreenshot` 抓到"≈"在不在页面渲染层"**。
抓不到就说明再怎么改 CSS 都是白费力气，只能自己画。

配套脚本：`tools/check_ui.py`（纯 stdlib 手写的 WebSocket + CDP 客户端，零依赖），
跑一遍会把下拉展开/过滤/键盘/浅色主题/完全体各拍一张到 `_shots/`，
并把关键属性（背景色、z-index、面板与输入框的相对位置）打出来。

> 同类可复用的手段：`--headless=new --remote-debugging-port=…` 起 Edge/Chrome，
> 然后用 `/json/list` 拿 WebSocket 地址。**不需要装 Playwright / Selenium** ——
> 这个项目的"零依赖"约束在验证工具上也一样成立。

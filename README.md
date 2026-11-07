# MPV Config Builder

[中文说明](README.zh-CN.md) · **English**

**Puts all 813 mpv options on the table, and tells you which ones fight each other.**

A Windows mpv configuration tool: it does not play video — it makes sure your
`mpv.conf` is written correctly. Tick options → live preview → generate, with an
automatic backup before every write and a one-line undo path.

> Built for **mpv-lazy** ([mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit))
> users — people who already have the bundle and just want "I want to change
> something, but I don't know which knob".

---

## What problem it solves

Existing mpv configurators hand you a few dozen common options. This one is different:

| | Typical one-click tools | This project |
|---|---|---|
| Options covered | a few dozen (at most 74) | **813** (full database) |
| Conflict detection | none | **17 rules**, each annotated with the manual's wording |
| Option descriptions | none or web lookups | **714 built-in Chinese descriptions** (726 raw, 12 dropped with CLI-only options) |
| Can it write deprecated options | yes | CLI-only options are **filtered on read** (16) and deprecated ones are flagged |

The UI is Chinese-first with a full English interface (switch in the top bar);
backend messages follow the UI language too.

## Usage

### Regular users: install the desktop build (no Python needed)

Download `MPV Config Builder-<version>-Setup.exe` from Releases and install.
No local Python required.

> ⚠ The installer is **not code-signed**, so Windows shows a SmartScreen prompt
> once: click "More info" → "Run anyway".

### From source (Python 3.8+, stdlib only, no `pip install`)

Right-click `启动.ps1` → "Run with PowerShell", or in a terminal:

```powershell
pwsh -NoProfile -File .\启动.ps1
```

It starts a local server and opens the browser. Manually:

```
python webui\server.py
```

> Execution policy: if "Run with PowerShell" is blocked, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once (local scripts only).
> Double-clicking a `.ps1` opens Notepad by default — that is Windows behavior; use
> right-click or a terminal.

Four tiers: **Basic** (4-question wizard) → **Advanced** (key params + shader
chain + MEMC) → **Full** (search all 813 options) → **Hell** (raw text box, no
guardrails but still backed up before writing). Plus **Checkup**: drop in an
mpv.conf and get encoding / include chain / profiles / unknown keys / duplicates /
conflicts / a six-axis score.

## Features

- **Four tiers**, from "I just want it to play" to "I want to tune the shader chain"
- **Config checkup**: 17 conflict rules + six-axis score + line diff
- **Live subtitle preview**: see `sub-font` / `sub-color` / `sub-border-*` changes instantly
- **Shader chain editor**: resolved against files that actually exist on your machine
- **Multi-script fusion**: merges deinterlace + denoise + upscale + MEMC into one `.vpy`
- **One-click mpv-lazy install**: picks the right package (full vs no-VapourSynth),
  downloads volumes, verifies, extracts
- **Download centre**: scripts / fonts / bundles (e.g. uosc) with install records and uninstall
- **Lossless config writing**: recognizes UTF-8 / GBK / Big5, writes back in the
  original encoding, only touches the global section, never `[profile]` sections
- **Your own presets**: save, export, share (stored in `%LOCALAPPDATA%`, not the install dir)
- **Keybinding editor**: edits your `input-user.conf`; mpv-lazy's own file is not touched

## Why you can trust it with your config

This tool edits your files, so the rules live in the code and the tests:

- **Backup before every write**, filename timestamped
- **Atomic writes**: temp file in the same directory + `os.replace` — a crash
  never leaves half a config
- **Unticking ≠ deleting**: the line is commented out, still in the file
- **Global section only**: same-named keys inside `[profile]` sections are never touched
- **Original encoding preserved**: a GBK config is never silently converted to UTF-8
- **Never overwrites an existing install**: one-click mpv-lazy refuses when
  `portable_config` already exists
- **User-edited files are kept on uninstall**: each file is hash-checked; edited ones survive and you are told

## Tests

```
python -m unittest discover -s tests -t .
python tools\verify.py          :: pre-release gate (add --offline to skip network checks)
```

`verify.py` runs everything: unit tests, compile check, docs-vs-reality numbers,
release files, license content, no machine-specific paths, download-list links,
topbar (real browser), Electron shell and packaged forms (the latter two only
when `electron/node_modules` exists). Browser-based checks also cover the i18n
switch, statusbar, context menu, keyboard shortcuts and animations.

CI runs the same gate on every push/PR (Windows runner):
[`.github/workflows/verify.yml`](.github/workflows/verify.yml).

Packaging steps: [docs/打包与发布.md](docs/打包与发布.md) (Chinese).

## Layout

```
core/          UI-agnostic logic (26 modules)
webui/         web UI
  server.py      local server + JSON API (39 endpoints, stdlib only)
  api.py         transport-agnostic dispatch (shared by HTTP and stdio)
  stdio.py       stdio transport: protocol on stdout, logs on stderr
  static/        9 pages
electron/      Electron shell (the installer comes from here)
  main.js        spawns the backend over stdio, single instance, CSP, custom titlebar
  preload.js     the narrow bridge: __MPVCB_INVOKE__ / __MPVCB_INFO__ / __MPVCB_WINDOW__
  renderer/      copied from webui/static at build time (not in git)
packaging/     PyInstaller recipe (standalone backend exe)
tests/         unit tests
tools/         build.py (generate) / verify.py (verify) / uidriver.py (browser driver)
.github/       CI: push / PR runs the pre-release gate on Windows
docs/          field-tested conclusions (pitfalls) + packaging & release
data/          bundled data (options DB / keybindings / commands)
AGENTS.md      house rules for working in this repo — read it before changing code
```

## License

**GPL-3.0** — full text in [`LICENSE`](LICENSE).

Why GPL-3.0: the bundled `data/mpv_options_zh.json` embeds **726 Chinese option
descriptions from [mpv_doc-CN](https://github.com/hooke007/mpv_doc-CN)**
(GPL-3.0), and GPL-3.0 is viral.

Third-party sources and licenses are summarized in [`NOTICE.txt`](NOTICE.txt).
This project **bundles and forwards no third-party binaries** — the download
centre only fetches from each project's official address when you click.

---

**Unofficial third-party tool**, not affiliated with mpv / mpv-lazy or their authors.

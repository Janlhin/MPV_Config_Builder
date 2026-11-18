# MPV Config Builder

[中文说明](docs/README.zh-CN.md) · **English**

**Puts all 813 mpv options on the table, and tells you which ones fight each other.**

A Windows mpv configuration tool: it does not play video — it makes sure your
`mpv.conf` is written correctly. Tick options → live preview → generate, with an
automatic backup before every write and a one-line undo path.

> Built for **mpv-lazy** ([mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit))
> users — people who already have the bundle and just want "I want to change
> something, but I don't know which knob".
>
> Works with **vanilla mpv** too — point it at any config directory. mpv-lazy
> users get the most out of it: the shader packs its combos reference are
> pre-bundled there (combos that need them are flagged in the UI).

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

### Desktop build (Tauri shell)

**There is no signed installer published in Releases right now.** The desktop shell moved from Electron to Tauri (`3.0.0-alpha.6`) on 2026-11-16; Tauri bundling is configured, but the current build is unsigned and no installer has been published yet. Build it yourself if you want the window:

```powershell
cd tauri\src-tauri
cargo build
.\target\debug\mpv-config-builder.exe
```

For a local installer, run `cargo tauri build` from `tauri\`. Needs a Rust
toolchain + WebView2 (built into Win10/11). Details and the release plan:
[docs/打包与发布.md](docs/打包与发布.md) (Chinese).

### From source (Python, stdlib only, no `pip install`)

Right-click `scripts\启动.ps1` → "Run with PowerShell", or in a terminal:

```powershell
pwsh -NoProfile -File .\scripts\启动.ps1
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
- **uosc settings editor**: `script-opts/uosc.conf` — 74 known keys in 9 categories,
  comments and unknown keys left byte-for-byte, backup before every write
- **Lossless config writing**: recognizes UTF-8 / GBK / Big5, writes back in the
  original encoding, only touches the global section, never `[profile]` sections
- **Your own presets**: save, export, share (stored in `%LOCALAPPDATA%`, not the install dir)
- **Keybinding editor**: edits your `input-user.conf`; mpv-lazy's own file is not touched
- **Global search** (`Ctrl+K`): options, uosc settings, keybindings and scripts in one
  result list, grouped by source
- **My groups**: drag a parameter's handle onto 常用 / 画质 / 性能 / 字幕; the
  assignment is remembered in settings (display only — write order is unchanged)
- **10-second undo**: after saving, an undo bar rolls back using the backup just created;
  it pauses while your mouse hovers over it

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
topbar (real browser), and the Tauri shell (its live half only when
`tauri/src-tauri/target/debug` has been built). Browser-based checks also
cover the i18n switch, statusbar, context menu, keyboard shortcuts and animations.

CI runs the same gate on every push/PR (Windows runner):
[`.github/workflows/verify.yml`](.github/workflows/verify.yml).

Packaging steps: [docs/打包与发布.md](docs/打包与发布.md) (Chinese).

## Roadmap: UI/UX upgrade and architecture rebuild

> **Status: proposal, not shipped.** The current 0.x build is still a Tauri 3 shell
> + Python 3.13 stdlib backend + nine static pages. The plan below describes where
> the rebuild is going, not what the app already does.

### UI/UX: from nine pages to one workbench (next)

The nine pages are feature-complete, but page-shaped: to change one setting you
first have to know which page owns it. The proposed replacement is a
**signal-path workbench**, prototyped in
[`webui/prototypes/MPV配置工作台原型.html`](webui/prototypes/MPV配置工作台原型.html).

- Navigation follows mpv's real pipeline: **decode → scale → shader → sync →
  audio → subtitles → performance**, not a feature menu.
- One workbench has **three depths** (overview / tune / full) and **two densities**.
  Depth changes what is exposed, never what the tool can do.
- A persistent monitor shows **config / diff / health / write**. A command
  palette (`Ctrl+K`) reaches options, stages and actions.
- Every change gets a visible change strip and a way back. Before writing, the
  target, diff, change count and backup path are shown together.
- Motion only explains a state change; `prefers-reduced-motion` is respected.

The prototype is clickable but uses sample data and simulates writes. It does not
replace the current UI until these gates pass:

1. The direction is accepted: signal-path navigation, three depths and the
   monitor are understandable without a tutorial.
2. A parity map covers every function of the nine pages; nothing is silently
   dropped (keybindings, downloads, checkup, uosc, hell mode included).
3. A data adapter talks to the existing API; the new surface and old pages can
   coexist behind a route switch.
4. Cut over one surface at a time; keep the old pages as fallback through a full
   release cycle.
5. Delete the old pages only after parity, keyboard access and write-safety
   checks pass.

**Not the goal:** a prettier nine-page skin, or a simplified "few switches" app
that hides the 813-option depth. The simplification is of the path, not the
capability.

### Architecture: staged rebuild, not a big-bang rewrite (later, gated)

**Current baseline:** Python 3.13 (stdlib only) owns `core/` and the HTTP/stdio
transport; the Tauri shell is Rust; the frontend is static files. The Rust backend
migration (T17) is **sealed** — there is no Rust backend crate and no active work
on it. If it is unsealed, the agreed shape is B: keep the API contract and move
`core/` + transport to Rust, with Python kept as the oracle during migration.

1. **Spike:** move one vertical slice (parse → compute → return JSON). Compare
   JSON output with Python, binary size and cold start. Stop if any of the three
   misses its target.
2. **Module migration:** pure computation first, then parsers/builders, then
   network / install / hardware. Each module ships with golden fixtures generated
   from Python; the existing tests stay as the outer gate.
3. **Cut over:** all existing HTTP and stdio endpoints are green against the Rust
   backend; Rust becomes the default while the Python backend stays as a rollback
   for one release.
4. **Packaging:** put the Rust sidecar inside the Tauri bundle and verify a clean
   install on a machine with no Python.
5. **Cleanup:** remove the Python backend only after the rollback window and the
   installer checks pass. Update packaging, CI and docs in the same change.

The rebuild is **not** a return to Electron, Node.js or a React SPA. The target
stays a native WebView2 desktop tool. Packaging, native menu, single-instance lock
and title-bar behaviour are tracked separately; this plan does not silently
re-scope them.

**Not planned in this rebuild:** macOS/Linux builds, auto-update, buying a
code-signing certificate, or a full-disk shader scan. These remain out of scope
until a new decision explicitly adds them.

## Stack and runtime versions

The gate (`verify.py layout`) checks the declared directories below against
`git ls-files`, and `verify.py stack` compares `.python-version` with CI.

| | Version / file | Notes |
|---|---|---|
| Language (backend + tools) | **Python 3.13** | `.python-version`; CI uses the same value |
| Package manager / lock | **none** (stdlib only) | no `requirements.txt`, no virtualenv |
| Desktop shell | **Tauri 3.0.0-alpha.6** | `tauri/src-tauri/Cargo.toml`, `Cargo.lock` is the lock |
| Shell entry | **PowerShell 7.4+** | `.ps1` files only; `.cmd` / `.bat` are forbidden |
| Browser / UI | system **WebView2** | no Node.js, no npm build step |

The desktop shell is intentionally pinned to Tauri 3.0.0-alpha.6 (pre-release);
upgrade only through a `chore(deps):` commit that records the decision.

## Layout

Top-level directories and what they are for (declared here because the gate
compares this list with what actually exists):

```
core/          UI-agnostic logic (26 modules)
webui/         web UI
  server.py      local server + JSON API (42 endpoints, stdlib only)
  api.py         transport-agnostic dispatch (shared by HTTP and stdio)
  stdio.py       stdio transport: protocol on stdout, logs on stderr
  static/        9 pages
tauri/         Tauri shell (Rust + system WebView2; no installer yet — see packaging doc)
  src-tauri/     Rust side: spawns the backend over stdio, injects the same __MPVCB_INVOKE__,
                 loads webui/static directly (no second copy); `cargo build` then run the exe
packaging/     PyInstaller recipe (standalone backend exe)
scripts/       source-run entry (`启动.ps1`) — the only launcher
tests/         unit tests
tools/         build.py (generate) / verify.py (verify) / uidriver.py (browser driver)
docs/          user docs (the four documents the UI renders, both READMEs, NOTICE.txt)
               + field-tested conclusions (pitfalls) + packaging & release
data/          bundled data (options DB / keybindings / commands / raw mpv dump)
.github/       CI: push / PR runs the pre-release gate on Windows
.githooks/     local commit gates (pre-commit, commit-msg) — thin `sh` shells
```

The root holds **only** the five documents (`README.md`, `AGENTS.md`,
`DECISIONS.md`, `TASKS.md`, `MANIFEST.md`), the license, dotfiles and these
directories; prose files belong under `docs/`. Anything new at the root has to
be approved first, and `verify.py layout` fails otherwise.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/) are enforced by
`.githooks/commit-msg` (`verify.py commitmsg`): one intent per commit, refactors
kept apart from behaviour changes, and commits over 400 lines are flagged.
CI validates the **tip commit** of a branch rather than every commit on the
default branch (the local hook covers the rest).

## License

**GPL-3.0** — full text in [`LICENSE`](LICENSE).

Why GPL-3.0: the bundled `data/mpv_options_zh.json` embeds **726 Chinese option
descriptions from [mpv_doc-CN](https://github.com/hooke007/mpv_doc-CN)**
(GPL-3.0), and GPL-3.0 is viral.

Third-party sources and licenses are summarized in [`docs/NOTICE.txt`](docs/NOTICE.txt).
This project **bundles and forwards no third-party binaries** — the download
centre only fetches from each project's official address when you click.

---

**Unofficial third-party tool**, not affiliated with mpv / mpv-lazy or their authors.

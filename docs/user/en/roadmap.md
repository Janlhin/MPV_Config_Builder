# MPV Config Builder Product Guide

> **This document is for users**: what this tool is, why it is built this way, what the four modes are,
> and why it dares to touch your configuration files.

Development records are not kept here. Where to find them:

- Work not yet done and decisions already made (with reasons) → `TASKS.md` and `DECISIONS.md`
- Conclusions from real testing (the pitfalls we hit) → the "measured criteria" section of [`docs/engineering/pitfalls.md`](../../engineering/pitfalls.md)
- Process, "what we were thinking back then" → git history (`git log`)

> **It was split once on 2026-10-09**: this document used to run to 1109 lines, about 980 of which were development records
> (milestone schedules, to-do lists, external-review fix logs, technical design drafts). That part has been moved out —
> whatever was still useful went into the two files above, and whatever was finished stayed in git history. What remains is below.

---

## 1. Product Positioning

### 1.1 In One Sentence

> **An mpv configurator for ordinary people**: no need to understand shaders, no need to wrestle with scripts.
> Install it and you get an mpv that "looks good, handles subtitles properly, and plays smoothly".

### 1.2 Why "build on mpv-lazy"

Stock mpv is close to a half-finished product: no polished OSD, no shaders, ugly subtitles, conservative
caching, and frame interpolation / super-resolution all require you to install scripts and VapourSynth yourself.
mpv-lazy has already packaged all of that:

| Something the user would otherwise suffer through | Already in mpv-lazy |
|---|---|
| OSD / controller (uosc) | ✅ |
| Practical scripts (auto-load, thumbnails, etc.) | ✅ |
| Shader directory + ready-made shaders | ✅ |
| VapourSynth + k7sfunc + frame-interpolation scripts + Python | ✅ |
| A complete mpv.conf with Chinese comments | ✅ |

**Conclusion**: the tool does not need to teach users how to build an mpv ecosystem. It only needs to

1. **get it installed** (one-click install)
2. **shape it into the best fit for this particular machine** (visual configuration)

### 1.3 Public Wording vs the Actual Path

- Publicly: any mpv works (if we detect one, we use it)
- Actually: **the default is to guide the user into installing mpv-lazy**, because that is the only path that guarantees "it works right after installation"
- If an existing mpv / mpv.net is detected, we fall back to a "generic mode", but the features and experience are weaker

---

## 2. The Four Modes

### 2.1 Positioning Table

| | **Basic mode** | **Advanced mode** | **Complete edition** | **Hell mode** |
|---|---|---|---|---|
| For whom | Total beginners | Knows a little, wants to tune it | Geeks, deep tinkerers | People who just want to edit the file |
| Goal | A usable mpv in 5 minutes | Tune common parameters visually | Full control + custom layer + versioning | Read and write the target file without fuss |
| Interface | Single-page wizard | Sidebar + parameters + live preview | Full option library + search + custom layer | A plain text box |
| Terminology | Plain language only | Plain language beside option names | Option names and value ranges directly | No explanations |
| Default | ✅ first launch | When an existing config is detected | Manual switch | Manual switch (easter egg) |

### 2.2 Basic Mode Flow (single-page wizard)

```
① Where is your mpv?
   ● Not installed → [go to the download center and install mpv-lazy in one click] (download → extract → locate the config directory)
   ○ Installed → auto-detect / pick the directory manually

② Your hardware?
   Resolution [auto-detected 1920x1080 ▾]   Refresh rate [auto-detected 60Hz ▾]
   GPU        [auto-detected NVIDIA ▾]      (detection failed → user picks "not sure")

③ What do you mainly watch?   ○ Anime   ○ Live-action   ○ Both

④ What matters more?   ○ Power-saving / smooth   ○ Balanced   ○ Maximum quality

        [Generate config]
            ↓
   write the include file + automatic backup → show "what changed"
```

**Includes**: rendering/decoding, scaling level, subtitle basics, cache, window
**Excludes**: shader names, VapourSynth, any jargon

### 2.3 Advanced Mode

Sidebar (7 groups of core parameters + shader chain + frame-interpolation scripts + writing/output + scan/download + about/acknowledgments)
+ 6 presets + 9 one-click combinations + live preview / score / health check / write method on the right.

Tweak the subtitle items (`sub-font` / `sub-color` / `sub-border-*` / `sub-pos`…) and the preview updates
immediately — preview and config read the same state, so "the preview looked right but the saved file was wrong" cannot happen.

### 2.4 Complete Edition (Advanced plus the following)

- **The full mpv option library**: 829 entries, of which **813 can be written into a config**
  (16 command-line-only entries filtered out), **714 have Chinese descriptions** (726 originally, 12 removed with the command-line items)
- The full library page supports search, filtering by 24 groups, and paging; there are also **117 curated items** as quick everyday entry points
- Custom layer: add options the library does not have, written through as-is
- Multi-script fusion: combine super-resolution + frame interpolation into a single `.vpy`
- Conflict detection: **17 rules**, each with its basis written in the comments of `core/conflicts.py`
  (classified as "manual text / design principle / logical inference", no hand-waving)
- Config health check (`analyze.html`): drop in an mpv.conf and get a report on encoding, the include chain,
  profiles, unknown keys, duplicates, conflicts, and a six-dimension score — read-only the whole way, not one character written

### 2.5 Rules for the Four Modes Living Together

1. **They share one config file**: all four write the same include, so switching modes loses nothing
2. **They share one core**: parsing / merging / writing / backup / download exist once; the mode only decides how much UI is exposed
3. **You can move up or down at any time**: configs generated by Basic remain editable after switching to Complete
4. **Default mode**: first launch opens Basic; if an existing config is detected, Advanced opens
5. **"About / Acknowledgments" entry**: reachable from all four modes (bottom of the sidebar); the text is in [acknowledgments.md](../zh-CN/acknowledgments.md)
6. **Hell mode has no guardrails**: no validation, no explanations; the only thing kept is the `.bak` backup before writing (the safety floor)

### 2.6 What Each of the Nine Pages Does

| Page | File | What it does |
|---|---|---|
| Mode selection | `index.html` | Pick a mode; local directories and versions at a glance; direct links to the 9 combinations; health-check entry |
| Basic mode | `basic.html` | Four-question wizard → preview → one-click generate |
| Advanced mode | `advanced.html` | Common parameters, shader chain (reorderable), frame interpolation single-choice and fusion, presets, combinations, scan, read/write |
| Complete edition | `expert.html` | The 813-entry full library (search / 24 groups / paging), custom layer, version rollback |
| Config health check | `analyze.html` | Drop in or pick a file → report (encoding / include chain / profiles / unknown keys / duplicates / conflicts / score); also "add comments" |
| Keyboard shortcuts | `keys.html` | Edit keybindings, compare against built-in defaults, write changes into your own config |
| Download center | `downloads.html` | One-click mpv-lazy install; scripts / shaders / fonts / full packages in one click; see and uninstall what was installed |
| Manuals | `guide.html` | Read the repository's Chinese documents online (including this one) |
| Hell mode | `hell.html` | List the directory → read the original → save raw text (still keeps a `.bak` before writing) |

### 2.7 The Data-Safety Floor

We are touching the user's files, so every item below has code and tests behind it:

| Scenario | Before | Now |
|---|---|---|
| Config is GBK/Big5 | Read as mojibake, written back as UTF-8 (comments destroyed) | `core/textio.py` detects the encoding, **writes back in the original encoding**, and flags "lossy" |
| Config contains `[profile]` sections | Keys inside the section were read into the UI as global options; applying them changed global behavior | `profiles` are returned separately, never mixed into global values; loading one requires an explicit choice and warns that it becomes global |
| Config contains `include` | Ignored entirely, so the "current state" shown in the UI was not what mpv actually did | Follows the include chain, and marks which file every key comes from and which included files are missing |
| `vf=@label:vapoursynth=` | The label was eaten, breaking other people's script references on write-back | Labels preserved exactly (`memc_label`) |
| Options the UI does not know | Everything was "unrecognized", a flood of false positives | Check the 813-entry library first; standard options become "the tool has no UI yet", and only genuinely unknown keys are unknown |
| Writing | — | Backup is mandatory before writing (timestamped); **unticking ≠ deleting**, it only comments the line out; same-name keys inside `[profile]` are never touched; one-click mpv-lazy install refuses to proceed when a `portable_config` already exists |

## 3. Development Roadmap (long-term direction)

> This section records only **direction and gates**; concrete actions and status live in `TASKS.md`, and reasons live in `DECISIONS.md`.

- **Current stage: 0.x ("still building")**. The 1.0.0 gate = installer pipeline restored (Tauri-side `bundle.active` + backend
  sidecar) + custom title bar / native menu / single-instance lock completed + English UI usable.
- **Web edition (item 12)**: **stopped** (user decision, 2026-11-17). The slices already landed (`pages.yml`, static category layer,
  read-only expert, guide fallback, index banner, redirect page) stay as they are; no deeper degradation of the four pages, and no Pages requirement.
- **Switching the backend to Rust (T17, evaluated)**: the conclusion is option B — replace `core/` + the HTTP layer with Rust, leave the 9 pages and 48 endpoints alone;
  three phases (spike → move module by module with Python as the oracle → switch the default and delete Python). **Code untouched, waiting for a go-ahead**;
  the conclusion and cost accounting are in the 2026-11-17 entry of `DECISIONS.md`.
- **Not doing**: macOS / Linux builds, auto-update, buying a code-signing certificate, whole-disk shader scanning —
  reasons are in the 2026-09-14 entry of `DECISIONS.md`.

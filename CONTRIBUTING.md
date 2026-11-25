# Contributing

This is a Windows desktop tool: Python 3.13 (standard library only) backend,
Tauri shell, static WebView2 frontend. There is **no** `pip install` step for
the runtime and no Node/npm build step for the UI.

## Quick start

```powershell
python webui\server.py
```

or:

```powershell
pwsh -NoProfile -File .\scripts\启动.ps1
```

## Development tools

The shipped runtime is still standard-library-only. The lint/test/coverage tools
are development dependencies:

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check core webui tools tests
python -m coverage run --source=core,webui -m pytest -q
python -m coverage report --fail-under=75
```

`ruff` currently runs a phase-1 ratchet (syntax and undefined names); broader
rules are a follow-up. `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`
and `cargo test` live under `tauri/src-tauri/`.

## Before you open a PR

```powershell
python -m unittest discover -s tests -t .
python tools\verify.py --offline
```

`verify.py --offline` is the authoritative gate. A green unit-test run alone is
not enough: the gate also checks docs-vs-code numbers, layout, version
consistency, release files and browser UI behavior.

## Where things live

- `core/` — UI-agnostic logic, parsers, writers, option database.
- `webui/` — local HTTP/stdio server and static pages.
- `tauri/` — desktop shell; it loads `webui/static` directly, no duplicate copy.
- `tools/` — `build.py`, `verify.py`, `translate_docs.py`, `gen_compliance.py`, `uidriver.py`.
- `requirements-dev.txt` — pinned Ruff / pytest / coverage; development only.
- `docs/` — see [`docs/README.md`](docs/README.md) for the four-drawer map.

## Commit rules

- Conventional Commits: `type(scope): summary`.
- One intent per commit. Do not mix a refactor with a behavior change.
- Run the pre-commit hook locally: `git config core.hooksPath .githooks`.
- Do not use `--no-verify` to get past a red gate.

## Decisions

Architecture/governance decisions go to [`docs/adr/`](docs/adr/README.md), one
file per decision. Do not append to the old `DECISIONS.md`; it is a pointer to
the frozen archive.

## Scope reminders

- No new runtime third-party Python dependencies. Tooling dependencies belong
  in the development environment, not in the shipped runtime.
- Keep the app’s document reader in mind: it supports headings, lists, tables,
  blockquotes and fenced code, not Mermaid or arbitrary HTML.
- File writes must use `core.textio.write_atomic`; backup-before-write is a
  product guarantee.

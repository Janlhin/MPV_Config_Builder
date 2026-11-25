# Quality gates

## Authority

The authoritative local gate is:

```powershell
python tools\verify.py --offline
```

It runs the unit tests, compile check, docs-vs-code numbers, required release
files, license content, root layout, version consistency, browser UI checks and
the Tauri static checks. The GitHub Actions `verify` workflow runs the same gate
on a Windows runner.

## Baseline (dated, not a live counter)

At 2026-11-25, before the documentation rebuild:

- `python -m unittest discover -s tests -t .` → **830 tests, 1 skip, OK**
- `python tools\verify.py --offline` → exit code 0 (recorded in the previous
  session; the rebuild must preserve it)
- After the documentation rebuild on 2026-11-25, `python tools\verify.py --offline`
  → exit code 0 again (830 tests, 1 skip; all static and browser gates green)
- Toolchain pass: `pytest` → 829 passed, 1 skipped; coverage (core + webui)
  → 84%, gate 80%; Ruff phase-1 gate passes; `cargo fmt --check`,
  `cargo clippy --all-targets -- -D warnings` and `cargo test` pass.

These numbers are a dated baseline. Do not copy them into new prose as if they
were live. The live number belongs to the command output and CI artifacts.

## Gate status after toolchain phase 1

| Gate | Status | Notes |
|---|---|---|
| Unit tests | ✅ | 830 tests, 1 skip at the dated baseline; pytest also collects them |
| Docs vs code numbers | ✅ | `verify.py docs` |
| Root layout / version consistency | ✅ | `verify.py layout` / `stack` |
| Browser UI smoke | ✅ | real-browser checks in `verify.py` |
| Lint (Ruff) | ✅ | phase-1 ratchet: `E9` / `F63` / `F7` / `F82`; broader rules follow |
| Formatting (Ruff format) | ⛔ | baseline would reformat 82 files; mechanical follow-up |
| Type checking | ⛔ | 9 / 1559 defs annotated at the audit; use a ratchet, not `mypy --strict` |
| Coverage | ✅ | core + webui baseline 84%; gate 80% |
| Rust fmt/clippy/test | ✅ | `quality` workflow and local commands |
| Dependency updates | ✅ | Dependabot config (pip, cargo, GitHub Actions) |
| Link check for all docs | ⚠ | `verify.py docs` covers the app docs and README, not every engineering page |

## Rules for this page

1. This page will be generated from CI artifacts in the toolchain phase. Until
   then, keep it short and mark dates.
2. A warning must not be displayed as a pass. A blocking gate must not be
   downgraded to a warning.
3. Exemptions are code-level (`verify-exempt: <reason> ref:<issue>`) or
   process-level (tool not wired, with a review date). Process exemptions live
   here, not in a separate hand-maintained dashboard.
4. Do not add a gate that cannot be run locally or in CI.

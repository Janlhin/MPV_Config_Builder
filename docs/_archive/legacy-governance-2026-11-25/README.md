# Legacy governance archive — frozen 2026-11-25

> **Status: historical, non-normative.** These files were frozen at commit
> `bdc0a3e1214f9f6008bd2391f0004c961e25451b` before the repository moved to the
> current four-layer documentation model.
>
> Do **not** follow these documents as active rules. They are kept for audit,
> blame and historical context only. Active entry points:
>
> - `../../../README.md` — project overview
> - `../../../AGENTS.md` — AI collaboration entry
> - `../../README.md` — documentation index
> - `../../engineering/` — current engineering docs
> - `../../adr/` — current decisions

## What is in this box

| Path | Former role |
|---|---|
| `DECISIONS.md` | Append-only decision log (53 entries) |
| `TASKS.md` | Task queue and open-question ledger |
| `MANIFEST.md` | Third-party source ledger (hand-maintained) |
| `AGENTS-v1.md` | Pre-rebuild AI entry (copy) |
| `docs/度量与门禁.md` | Metrics dashboard, validation matrix, exemptions |
| `docs/既有约定.md` | Structural constraints and field-tested lessons |
| `docs/平台与写入约定.md` | Platform and atomic-write conventions |
| `docs/i18n-约定.md` | i18n mechanism conventions |
| `docs/打包与发布.md` | Packaging and release checklist |

## Rules for this directory

1. Read-only: do not edit, move, rename, or delete files here.
2. CI, link checks, formatters and linters must exclude this directory.
3. Nothing here may be treated as a current rule, source of truth, or template.
4. New decisions go to `docs/adr/`; new work goes to GitHub Issues / `ROADMAP.md`.
5. The original files are kept byte-for-byte except for this index; SHA-256
   values are in `MANIFEST.sha256`.

## Note on visibility

This is an **archive**, not a deletion. Anyone with repository access can read
these files. If the goal is to remove them from history entirely, that requires
a separate history-rewrite or repository migration decision; it is not done by
moving them here.

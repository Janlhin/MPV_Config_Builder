# 0001 Archive legacy governance and rebuild the docs tree

- Status: accepted
- Date: 2026-11-25
- Deciders: repository owner

## Context

The repository had grown a large hand-maintained governance layer: a decision
log, a task queue, a third-party manifest, a metrics dashboard, and several
convention documents. The layer was useful, but it was maintained by hand and
had started to drift from the code. Examples found during the audit:

- `MANIFEST.md` recorded stale byte counts and SHA-256 values for `LICENSE` and
  `data/mpv_options_zh.json`;
- `docs/既有约定.md` said `tools/` had four files while it had five, and named
  five files over 800 lines while at least eight exceeded that threshold;
- `README.md` said 26 core modules while the tree had 30 `.py` files (29
  functional modules).

The problem was not that the documents were old. The problem was that
hand-written tables had become a second, unverified source of truth.

## Decision

1. Freeze the old governance layer at commit `bdc0a3e`:
   - annotated tag `archive/legacy-governance-2026-11-25`;
   - branch `archive/legacy-governance`;
   - bundle backup outside the repository;
   - original files under `docs/_archive/legacy-governance-2026-11-25/`.
2. Keep the old files readable but non-normative. Do not delete them and do not
   treat them as current rules.
3. Rebuild the active documentation as four drawers: `user/`, `engineering/`,
   `adr/`, `compliance/`.
4. Replace hand-maintained numbers with generated/CI-derived values where
   possible. The first rebuild step fixes the stale values; later steps wire
   the generators.
5. Preserve code behavior and the 830-test baseline. Documentation moves must
   update the app whitelist, translation pairs, packaging spec, layout checks
   and tests in the same change.

## Consequences

- History and blame are preserved; old links get pointer stubs.
- Old documents remain visible in the archive. This is a freeze, not a
  history rewrite. Removing them from history would require a separate
  decision and a force-push/migration.
- Active docs are shorter and have a single entry point.
- The next work is toolchain modernization (ruff, pytest, coverage,
  pre-commit, CI split), not more prose.

## Supersedes

None. This is the first ADR.

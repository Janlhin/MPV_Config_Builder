# Changelog

All notable user-visible changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
the project’s single `VERSION` source.

## [Unreleased]

### Changed

- Documentation tree rebuilt into `user/`, `engineering/`, `adr/` and
  `compliance/` drawers; product docs moved to bilingual `docs/user/{zh-CN,en}/`
  paths with English slugs.
- Legacy governance layer (`DECISIONS.md`, `TASKS.md`, `MANIFEST.md`, metrics
  dashboard and convention docs) frozen under
  `docs/_archive/legacy-governance-2026-11-25/` and marked non-normative.
- Root docs now point to the archive/new drawers instead of carrying the old
  long-form ledgers.

### Added

- `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `docs/README.md`,
  `docs/adr/`, `docs/compliance/`.

### Fixed

- Corrected stale third-party byte counts/hashes in the active compliance
  ledger (the archived `MANIFEST.md` keeps the historical values).

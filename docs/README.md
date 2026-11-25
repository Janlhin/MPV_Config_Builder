# Documentation

This directory is the active documentation tree. The old governance layer is
frozen under [`_archive/legacy-governance-2026-11-25/`](_archive/legacy-governance-2026-11-25/README.md)
and is **historical, not normative**.

## Start here

- [Project README](../README.md) — what the tool is, how to run it, stack, layout
- [AGENTS.md](../AGENTS.md) — AI collaboration entry
- [CONTRIBUTING.md](../CONTRIBUTING.md) — development setup and contribution flow
- [SECURITY.md](../SECURITY.md) — vulnerability reporting and security scope
- [CHANGELOG.md](../CHANGELOG.md) — user-visible changes

## Four drawers

| Drawer | What belongs there | Entry |
|---|---|---|
| `user/` | Product docs rendered by the app and read by users | [`user/zh-CN/README.md`](user/zh-CN/README.md) · [`user/en/`](user/en/) |
| `engineering/` | Architecture, quality, platform, i18n, release, constraints, pitfalls | [`engineering/architecture.md`](engineering/architecture.md) |
| `adr/` | One decision per file; superseded decisions stay in place | [`adr/README.md`](adr/README.md) |
| `compliance/` | Third-party ledger, NOTICE, machine-checkable hashes | [`compliance/third-party.md`](compliance/third-party.md) |

## Old path → new path

| Old path | New path |
|---|---|
| `docs/README.zh-CN.md` | `docs/user/zh-CN/README.md` |
| `docs/入门指南.md` / `.en.md` | `docs/user/zh-CN/getting-started.md` / `docs/user/en/getting-started.md` |
| `docs/MPV_Shader搭配说明书.md` / `.en.md` | `docs/user/zh-CN/shader-guide.md` / `docs/user/en/shader-guide.md` |
| `docs/产品规划与路线图.md` / `.en.md` | `docs/user/zh-CN/roadmap.md` / `docs/user/en/roadmap.md` |
| `docs/致谢与许可.md` / `.en.md` | `docs/user/zh-CN/acknowledgments.md` / `docs/user/en/acknowledgments.md` |
| `docs/打包与发布.md` | `docs/engineering/release.md` |
| `docs/既有约定.md` | `docs/engineering/constraints.md` + `docs/engineering/pitfalls.md` |
| `docs/平台与写入约定.md` | `docs/engineering/platform.md` |
| `docs/i18n-约定.md` | `docs/engineering/i18n.md` |
| `docs/度量与门禁.md` | `docs/engineering/quality.md` |
| `docs/NOTICE.txt` | `docs/compliance/NOTICE.txt` |

The old paths that the app or external links may still use have small pointer
files; they are not the source of truth.

## Archive

- [`_archive/legacy-governance-2026-11-25/README.md`](_archive/legacy-governance-2026-11-25/README.md)
- Frozen at commit `bdc0a3e`; tag `archive/legacy-governance-2026-11-25`;
  branch `archive/legacy-governance`.
- CI, link checks and formatters must exclude `_archive/`.

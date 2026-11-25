# ADR index

Architecture and governance decisions live here, one file per decision. An
ADR is accepted when it is merged; a later ADR can supersede it, but the old
file stays in place.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-archive-legacy-governance.md) | Archive legacy governance and rebuild the docs tree | Accepted |

Template for a new ADR:

```markdown
# NNNN Title

- Status: proposed / accepted / superseded by ADR-NNNN
- Date: YYYY-MM-DD
- Deciders: ...

## Context
## Decision
## Consequences
```

Keep the decision short. The detailed “how” belongs in `docs/engineering/`;
the historical record belongs in `docs/_archive/`.

# Architecture

## Runtime shape

```text
Tauri shell (Rust + system WebView2)
        │  spawns / supervises
        ▼
Python backend (3.13, standard library only)
        │  HTTP in browser mode, stdio in the desktop shell
        ▼
webui/static (classic scripts, no Node/npm build step)
        │
        ├── core/      UI-agnostic logic, file parsing/writing, option database
        ├── data/      bundled option/keybinding/command data
        └── docs/      user docs rendered by the in-app reader
```

The desktop shell does not ship a second copy of the frontend; it points at
`webui/static` directly. That is a deliberate single-source rule, not an
accident.

## Boundaries

- `core/` must not import `webui/`, `tauri/`, `tools/` or `tests/`.
- The web UI talks to the backend through `API.xxx()` methods, never through
  page-level `fetch('/api/...')`. The latter works in browser mode and silently
  fails over the stdio transport.
- User-file writes go through `core.textio.write_atomic`; backup-before-write is
  part of the contract, not an optional wrapper.
- The in-app document reader only understands headings, horizontal rules,
  lists, fenced code, blockquotes and tables. Mermaid and arbitrary HTML are not
  supported; diagrams for GitHub/docs sites are separate from in-app content.

## Known deviations (registered, not templates)

- `webui/server.py` still mixes application services and HTTP adaptation; new
  endpoints should not add more of that coupling.
- `webui/static/state.js` still exposes one global `APP`; new writes go through
  `patch(partial)`.
- The frontend has no build step. That keeps the runtime dependency-free, but
  it also means type checking and module boundaries need explicit tooling
  (planned in the quality track), not a compiler.
- Tauri is pinned to `3.0.0-alpha.6`. The Rust backend migration is sealed;
  do not unseal it as a side effect of a docs or packaging change.

## Non-goals

- No Electron/Node runtime, no React SPA, no big-bang rewrite.
- No macOS/Linux build, auto-update or code-signing certificate in the current
  scope.
- No silent re-scope of the UI/UX workbench; it has its own gates.

See [`constraints.md`](constraints.md), [`pitfalls.md`](pitfalls.md) and
[`release.md`](release.md) for the enforceable details.

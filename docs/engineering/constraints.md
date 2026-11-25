# Structural constraints

> Active engineering note. Derived from the archived `docs/既有约定.md` on 2026-11-25;
> the archive remains the historical record. This page describes current boundaries,
> not a frozen copy of the old rules.

## 结构性约束（2026-10-20 架构复核的结论）

- **分层方向**：`core/` 不许 import `webui/` / `tauri/` / `tools/` / `tests/`（`verify.py deps` 判）。
  但 `webui/server.py` 至今把应用层与 HTTP 适配同居、`api.py` 还反向 `getattr(server, …)`
  —— 这是**已登记偏差**（T28），不是可以照着抄的范式；新接口别再往这层堆。
- **传输门面**：页面只经 `API.xxx()`；`API.get('/api/…')` 这类字面量是历史写法，新代码用具名方法。
- **前端状态**：`webui/static/state.js` 只有一份全局 `APP`；新增写入走 `patch(partial)`，
  别再散落 `APP.x = …`（约 30 处历史直接赋值属已登记偏差）。
- **Module size is a diagnostic, not a gate.** The old 800-line budget is archived. Split a module when it has more than one responsibility; enforce boundaries with code review and, later, `import-linter`.
- **Single definition**: one hooks entry, one frontend copy, two transports (HTTP / stdio).

/* Preload：渲染进程与主进程之间唯一的桥（contextIsolation 开着）。
 *
 * ⚠ 这个文件是**安全边界**，所以刻意做得极窄。现暴露三个入口，各自形状锁死：
 *   1. `__MPVCB_INVOKE__` —— 只能发我们定义好的后端请求形状（领域名 path）。
 *   2. `__MPVCB_INFO__` —— 只读环境信息（版本号、后端是否活着），无副作用。
 *   3. `__MPVCB_WINDOW__.setOverlayTheme('light'|'dark')` —— 自绘标题栏（R-29）
 *      的 overlay 配色切换。**只收枚举**，色值表在主进程；传别的值会被拒。
 *   **不暴露** ipcRenderer 本身、不暴露 fs / child_process / require、
 *   不暴露任何能拼出任意 IPC 通道名的东西 —— 页面拿到的能力就这么多。
 *
 * 前端 api.js 的 `hasInvoke()` 就是在看 1 在不在：
 *   在 → 走 IPC → 主进程 → 后端的 stdio
 *   不在（普通浏览器）→ 走 fetch → 本地 HTTP 服务
 * 两条路返回**同一种形状**，所以 9 个页面都不知道自己在哪种传输下。
 */
const { contextBridge, ipcRenderer } = require('electron');

/** 只允许这几条协议路径的书写形状：领域名（config/load）或带一次前导斜杠 */
function normalizePath(p) {
  const s = String(p || '').trim();
  return s.replace(/^\/+/, '').replace(/^api\//, '');
}

contextBridge.exposeInMainWorld('__MPVCB_INVOKE__', async (req) => {
  if (!req || typeof req !== 'object') {
    return { ok: false, error: '请求必须是一个对象' };
  }
  const path = normalizePath(req.path);
  if (!path) return { ok: false, error: '请求缺少 path' };

  const payload = {
    path,
    method: req.method === 'POST' || req.method === 'GET' ? req.method : undefined,
    query: (req.query && typeof req.query === 'object') ? req.query : {},
    body: req.body
  };

  try {
    const res = await ipcRenderer.invoke('mpvcb:invoke', payload);
    if (!res || typeof res !== 'object') {
      return { ok: false, error: '主进程返回了无法识别的响应' };
    }
    return res;
  } catch (e) {
    // 通道本身坏了（主进程挂了 / handler 抛了）—— 也得给页面一个能显示的错
    return { ok: false, error: '与主进程通信失败：' + (e && e.message ? e.message : e) };
  }
});

/** 一点只读的环境信息（版本号、后端是否活着）——给状态提示用，没有副作用 */
contextBridge.exposeInMainWorld('__MPVCB_INFO__', async () => {
  try {
    return await ipcRenderer.invoke('mpvcb:info');
  } catch (e) {
    return { electron: true, backendAlive: false, backendError: String(e) };
  }
});

/** 自绘标题栏（R-29）：overlay 配色切换。只收 'light' | 'dark' 枚举，
    色值表在主进程 —— 渲染进程传不了任意颜色，桥面不加自由度 */
contextBridge.exposeInMainWorld('__MPVCB_WINDOW__', {
  setOverlayTheme: (theme) => ipcRenderer.invoke('mpvcb:overlay', theme)
});

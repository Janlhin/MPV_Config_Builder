/* MPV Config Builder · Electron 主进程
 *
 * 职责（按重要性）：
 *   1. spawn Python 后端，**用 stdio 说话，不开任何端口**（用户的明确要求）
 *   2. 把渲染进程的 invoke 请求转给后端，按 id 配对响应
 *   3. 退出时确保子进程被杀掉（否则会留下孤儿进程占着文件）
 *   4. 单实例（两次双击不要开出两个后端）
 *   5. 原生菜单 + 窗口
 *
 * ⚠ 这里**没有** `--inspect` / 远程调试端口之类的监听；除了必要的一次性
 *    `ipcMain.handle`，进程不对外开放任何入口。
 */
const { app, BrowserWindow, ipcMain, Menu, shell, dialog, session } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const readline = require('node:readline');
const { buildMenu } = require('./menu');

const IS_DEV = process.argv.includes('--dev');

// 可选：开一个**本地**远程调试端口，给自动化验证用（tools/check_electron.py 靠它）。
//
// ⚠ 默认**不开**。只有显式传 `--debug-port=N` 才开 —— 而且只绑 127.0.0.1。
//    这个开关存在的意义是：GUI 应用没法用普通命令行验证，
//    而"我打开看了一眼"不算验证（前几步的教训：看不出来的错才是真错）。
const dbgArg = process.argv.find((a) => a.startsWith('--debug-port='));
const DEBUG_PORT = dbgArg ? Number(dbgArg.split('=')[1]) || 0 : 0;
if (DEBUG_PORT > 0) {
  app.commandLine.appendSwitch('remote-debugging-port', String(DEBUG_PORT));
  app.commandLine.appendSwitch('remote-allow-origins', `http://127.0.0.1:${DEBUG_PORT}`);
}

/* ---------------------------------------------------------------- 路径
 *
 * 三种运行形态，后端的落点不一样：
 *   打包后          resources/backend/MPVConfigBuilderBackend.exe   ← extraResources
 *   开发（已打包）  ../dist/MPVConfigBuilderBackend/...             ← 仓库里的产物
 *   开发（源码）    ../webui/server.py                              ← 直接跑源码，调试后端方便
 *
 * ⚠ 路径统一用 process.resourcesPath / __dirname 推导，**不许写死盘符**
 *   （preflight.py 有一条检查会拦机器专用绝对路径）。
 */

function repoRoot() {
  return path.resolve(__dirname, '..');
}

function resolveBackend() {
  if (app.isPackaged) {
    const exe = path.join(process.resourcesPath, 'backend',
      'MPVConfigBuilderBackend.exe');
    return { cmd: exe, args: ['--stdio'], kind: 'packaged' };
  }
  // 开发：优先用打好的 exe（和最终形态一致），没有就退回源码
  const exe = path.join(repoRoot(), 'dist', 'MPVConfigBuilderBackend',
    'MPVConfigBuilderBackend.exe');
  if (fs.existsSync(exe)) return { cmd: exe, args: ['--stdio'], kind: 'dev-exe' };

  const py = process.env.MPVCB_PYTHON || 'python';
  return {
    cmd: py,
    args: [path.join(repoRoot(), 'webui', 'server.py'), '--stdio'],
    kind: 'dev-source'
  };
}

/* ------------------------------------------------------------- 安全策略
 *
 * 页面从 `file://` 载入 —— 没有同源限制兜底，一旦被注入了什么东西，
 * 它就能读整个磁盘。所以这里补一条 CSP。
 *
 * 为什么用**会话级 onHeadersReceived** 而不是往 9 个 HTML 里加 <meta>：
 * 那些 HTML 是浏览器版与 Electron 版共用的同一份文件（webui/static），
 * 往里塞 Electron 专用的 meta 标签就等于让两份用途互相污染。
 * 在这里注入，单一来源还是单一来源。
 *
 * `script-src` 必须带 'unsafe-inline'：那 9 个页面都是**内联脚本**
 * （<script> 直接写在 html 里），不是外链模块。这是既有设计，不改。
 * 'unsafe-eval' 不给 —— 我们自己没用到 eval，留着只是徒增风险。
 */
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "connect-src 'none'",      // ⚠ 后端走 IPC，页面**不需要**发任何网络请求
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'"
].join('; ');

function installCsp() {
  session.defaultSession.webRequest.onHeadersReceived((details, cb) => {
    // 只给本地页面加，别影响将来可能有的外链
    if (!String(details.url).startsWith('file://')) return cb({});
    cb({ responseHeaders: { ...details.responseHeaders, 'Content-Security-Policy': [CSP] } });
  });
}

/* ------------------------------------------------------- 后端进程管理 */

class Backend {
  constructor() {
    this.proc = null;
    this.pending = new Map();     // id -> {resolve, timer}
    this.seq = 0;
    this.dead = null;             // 死了就把原因记下来，后续请求直接返回它
  }

  spawn() {
    const { cmd, args, kind } = resolveBackend();
    console.log(`[backend] 启动（${kind}）：${cmd} ${args.join(' ')}`);
    if (!fs.existsSync(cmd) && kind !== 'dev-source') {
      throw new Error(`找不到后端：${cmd}\n先跑：py -m PyInstaller packaging/backend.spec`);
    }

    this.proc = spawn(cmd, args, {
      cwd: path.dirname(cmd),
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }
    });

    // stdout = 协议流，一行一条 JSON
    readline.createInterface({ input: this.proc.stdout }).on('line', (line) => {
      this.onLine(line);
    });

    // stderr = 日志。原样转到主进程的控制台，方便排查（**绝不解析**）
    readline.createInterface({ input: this.proc.stderr }).on('line', (line) => {
      console.log(`[backend] ${line}`);
    });

    this.proc.on('error', (e) => this.onExit(`启动失败：${e.message}`));
    this.proc.on('exit', (code, signal) => {
      this.onExit(`后端退出（code=${code} signal=${signal}）`);
    });
  }

  onLine(line) {
    const s = line.trim();
    if (!s) return;
    let msg;
    try {
      msg = JSON.parse(s);
    } catch (e) {
      // 后端把非协议内容写进了 stdout —— 这是 bug，别装作没看见
      console.error(`[backend] stdout 出现了非 JSON 行（协议被污染）：${s.slice(0, 200)}`);
      return;
    }
    const slot = this.pending.get(msg.id);
    if (!slot) {
      console.error(`[backend] 收到无人认领的响应 id=${msg.id}`);
      return;
    }
    this.pending.delete(msg.id);
    clearTimeout(slot.timer);
    slot.resolve(msg);
  }

  onExit(reason) {
    this.dead = reason;
    console.error(`[backend] ${reason}`);
    for (const [, slot] of this.pending) {
      clearTimeout(slot.timer);
      slot.resolve({ ok: false, error: reason });
    }
    this.pending.clear();
  }

  /** 发一条请求，等它的响应。返回协议对象（{ok,data} 或 {ok:false,error}）。 */
  call(req, timeoutMs = 120000) {
    if (this.dead) return Promise.resolve({ ok: false, error: this.dead });
    if (!this.proc || !this.proc.stdin.writable) {
      return Promise.resolve({ ok: false, error: '后端没有在运行' });
    }
    this.seq += 1;
    const id = this.seq;
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        resolve({ ok: false, error: `后端超时（${timeoutMs} ms）：${req.path}` });
      }, timeoutMs);
      this.pending.set(id, { resolve, timer });
      try {
        this.proc.stdin.write(JSON.stringify({ ...req, id }) + '\n');
      } catch (e) {
        clearTimeout(timer);
        this.pending.delete(id);
        resolve({ ok: false, error: `写入后端失败：${e.message}` });
      }
    });
  }

  /** 关掉后端。先礼后兵：关 stdin 让它自然退出，超时就杀。 */
  kill() {
    const p = this.proc;
    this.proc = null;
    if (!p) return;
    try { p.stdin.end(); } catch (e) { /* 已经关了 */ }
    const t = setTimeout(() => {
      try { p.kill(); } catch (e) { /* 已经没了 */ }
    }, 1500);
    p.on('exit', () => clearTimeout(t));
    try { p.kill(); } catch (e) { /* 已经没了 */ }
  }
}

const backend = new Backend();

/* ------------------------------------------------------------- 窗口 */

let win = null;

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#101319',
    show: false,
    autoHideMenuBar: false,
    icon: path.join(__dirname, 'assets', 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      // 前端代码是我们自己的，但**仍然不关隔离**：
      // 关掉 contextIsolation 等于把 Node 全能力交给页面，没必要冒这个险
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,           // preload 要 require('electron')，sandbox 下不行
      spellcheck: false
    }
  });

  win.once('ready-to-show', () => win.show());

  // 页面里的外链一律用系统浏览器打开，不要在应用窗口里跳走
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('file://')) {
      e.preventDefault();
      if (/^https?:/i.test(url)) shell.openExternal(url);
    }
  });

  Menu.setApplicationMenu(buildMenu({
    isDev: IS_DEV,
    onReload: () => win && win.reload(),
    onToggleDevTools: () => win && win.webContents.toggleDevTools(),
    onAbout: showAbout,
    onOpenDocs: () => shell.openExternal(
      'https://github.com/Janlhin/MPV_Config_Builder'),
    onOpenUserData: () => openUserDataDir()
  }));

  // renderer/ 是 `npm run sync` 从 webui/static/ 复制来的（单一来源，别手改）
  const indexHtml = path.join(__dirname, 'renderer', 'index.html');
  if (!fs.existsSync(indexHtml)) {
    dialog.showErrorBox('缺少前端文件',
      `找不到 ${indexHtml}\n\n先跑一次：npm run sync`);
    app.quit();
    return;
  }
  win.loadFile(indexHtml);
  if (IS_DEV) win.webContents.openDevTools({ mode: 'detach' });
  win.on('closed', () => { win = null; });
}

/** 打开用户数据目录（%LOCALAPPDATA%\MPVConfigBuilder）—— 排查问题时很有用 */
function openUserDataDir() {
  const base = process.env.LOCALAPPDATA || app.getPath('userData');
  const dir = path.join(base, 'MPVConfigBuilder');
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch (e) { /* 建不出来就让 shell 报错 */ }
  shell.openPath(dir);
}

function showAbout() {
  dialog.showMessageBox(win, {
    type: 'info',
    title: '关于 MPV Config Builder',
    message: 'MPV Config Builder',
    detail: [
      `版本 ${app.getVersion()}`,
      '',
      '把 mpv 配置写对：勾选项 → 生成 mpv.conf，写前备份，随时可撤。',
      '所有配置解析、生成、体检都在本机完成，不联网、不上传。',
      '',
      '许可：GPL-3.0-only',
      '第三方内容与来源见 NOTICE.txt'
    ].join('\n'),
    buttons: ['好']
  });
}

/* -------------------------------------------------------------- IPC
 *
 * 渲染进程只拿到这一个通道：`mpvcb:invoke`。
 * 它收 {path, method, query, body}，转给后端，**原样**把协议对象还回去。
 * 前端 api.js 的 invokeVia() 消费的就是这个形状。
 */

ipcMain.handle('mpvcb:invoke', async (_event, req) => {
  if (!req || typeof req !== 'object' || !req.path) {
    return { ok: false, error: '请求缺少 path' };
  }
  return backend.call({
    path: String(req.path),
    method: req.method || undefined,
    query: req.query || {},
    body: req.body
  });
});

/** 让前端能问一句「我在 Electron 里吗、后端活着吗」——状态栏/报错提示用 */
ipcMain.handle('mpvcb:info', async () => ({
  electron: true,
  version: app.getVersion(),
  backendAlive: !backend.dead,
  backendError: backend.dead,
  userDataDir: path.join(process.env.LOCALAPPDATA || '', 'MPVConfigBuilder')
}));

/* ------------------------------------------------------------ 生命周期 */

// 单实例：第二次双击把它带到前面，而不是再开一个后端
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.whenReady().then(() => {
    installCsp();
    try {
      backend.spawn();
    } catch (e) {
      dialog.showErrorBox('后端没有启动', String(e.message || e));
      app.quit();
      return;
    }
    createWindow();
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on('window-all-closed', () => {
  // Windows 上关窗口就是退出（macOS 的习惯在这里不适用）
  app.quit();
});

// 退出前杀掉后端 —— 否则会留下孤儿进程占着配置目录
app.on('before-quit', () => backend.kill());
app.on('will-quit', () => backend.kill());
process.on('exit', () => backend.kill());

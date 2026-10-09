/* MPV Config Builder · 前端与 Python 后端的桥
   所有真实逻辑都在 Python 的 core/ 里，这里只负责发请求与渲染。

   ---------- 两种传输，界面无感（W-4 第②③步）----------

   HTTP     浏览器里直接开页面用（开发 / 调试 / 实机测试脚本）。
   stdio    Electron 里用：外壳 spawn 后端，一行一条 JSON 走管道，**不开端口**。

   切换点在 `invoke()`：只要 `window.__MPVCB_INVOKE__` 存在就走 stdio，否则 fetch。
   这个全局由 Electron 的 preload 注入 —— **页面自己不知道跑在哪种传输下**，
   也不需要知道。所以下面 39 个方法一个都不用改。

   ⚠ 两种传输的**错误形状必须一致**：
   后端 HTTP 模式回 `{ok:false, detail:"..."}`，stdio 协议回 `{ok:false, error:"..."}`。
   页面里 64 处都在读 `r.detail`，所以 invoke() 负责把 `error` 映射成 `detail`
   —— 否则 Electron 下每个报错都会显示成 undefined。 */

/** 有没有 Electron 给的调用通道。没有就是普通浏览器。 */
function hasInvoke() {
  return typeof window !== 'undefined'
    && typeof window.__MPVCB_INVOKE__ === 'function';
}

/** 把 `/api/download/job?id=3&x=1` 拆成 {path, query}。
    三种传输（HTTP / stdio）都要用同一套拆法，所以只写一处。 */
function splitUrl(url) {
  const s = String(url || '');
  const i = s.indexOf('?');
  if (i < 0) return { path: s, query: {} };
  const query = {};
  for (const piece of s.slice(i + 1).split('&')) {
    if (!piece) continue;
    const eq = piece.indexOf('=');
    const k = decodeURIComponent(eq < 0 ? piece : piece.slice(0, eq));
    // ⚠ 同名参数取**第一个**（与后端 parse_qs 的用法一致），不是最后一个
    if (k in query) continue;
    const v = eq < 0 ? '' : piece.slice(eq + 1);
    query[k] = decodeURIComponent(v.replace(/\+/g, ' '));
  }
  return { path: s.slice(0, i), query };
}

/** 走 stdio 通道发一条请求，返回跟 HTTP 一模一样的形状。 */
async function invokeVia(method, url, body) {
  const { path, query } = splitUrl(url);
  let res;
  try {
    res = await window.__MPVCB_INVOKE__({
      path: path.replace(/^\/api\//, ''),   // 协议用领域名，不带 /api 前缀
      method,
      query,
      body
    });
  } catch (e) {
    // 通道本身坏了（后端进程死了、管道断了）—— 也得给页面一个能显示的错
    return { ok: false, detail: '后端连接中断：' + (e && e.message ? e.message : e) };
  }
  if (!res || typeof res !== 'object') {
    return { ok: false, detail: '后端返回了无法识别的响应' };
  }
  if (res.ok) return res.data;
  // 形状对齐：协议给的是 error，页面读的是 detail
  return { ok: false, detail: res.error || '未知错误' };
}

const API = {
  /** 发一条请求。这是唯一的出口 —— 39 个方法全部经过它。 */
  async invoke(method, url, body) {
    if (hasInvoke()) return invokeVia(method, url, body);
    const r = method === 'POST'
      ? await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body || {})
        })
      : await fetch(url);
    return r.json();
  },
  async get(path) {
    return API.invoke('GET', path);
  },
  async post(path, body) {
    return API.invoke('POST', path, body);
  },
  status: () => API.get('/api/status'),
  presets: () => API.get('/api/presets'),
  // 全量选项库的分页查询（expert 页的搜索/翻页）
  dbOptions: (p) => API.get('/api/db/options?' + new URLSearchParams(p || {}).toString()),
  // 在线渲染仓库里的文档（guide 页）
  guide: (doc) => API.get('/api/guide?doc=' + encodeURIComponent(doc || '')),
  // 用户自己的预设（磁盘上存的）—— 和上面那 6 套内置的不是一回事
  userPresets: () => API.get('/api/userpresets'),
  userPresetSave: (b) => API.post('/api/presets/save', b),
  userPresetDelete: (b) => API.post('/api/presets/delete', b),
  userPresetLoad: (b) => API.post('/api/presets/load', b),
  userPresetExport: (b) => API.post('/api/presets/export', b),
  configTidy: (b) => API.post('/api/config/tidy', b),
  // 一键装 mpv-lazy（R-8w）：plan 只算不动，start 才真下
  installPlan: (target, mirror) => API.get('/api/install/plan'
    + (target ? '?target=' + encodeURIComponent(target) : '')
    + (mirror ? (target ? '&' : '?') + 'mirror=' + encodeURIComponent(mirror) : '')),
  installStart: (b) => API.post('/api/install/lazy', b),
  options: () => API.get('/api/options'),
  basicPreview: (b) => API.post('/api/basic/preview', b),
  basicApply: (b) => API.post('/api/basic/apply', b),
  scan: (dir) => API.post('/api/scan', { dir }),
  catalog: (target) => API.get('/api/catalog' + (target ? '?target=' + encodeURIComponent(target) : '')),
  configLoad: (path) => API.post('/api/config/load', { path }),
  configPreview: (b) => API.post('/api/config/preview', b),
  configApply: (b) => API.post('/api/config/apply', b),
  analyze: (text) => API.post('/api/analyze', { text }),
  report: (b) => API.post('/api/report', b),
  restore: (path) => API.post('/api/restore', {
    path, target: (typeof APP !== 'undefined' && APP.target) || ''
  }),
  backups: (target) => API.get('/api/backups'
    + (target ? '?target=' + encodeURIComponent(target) : '')),
  downloads: (target, kind) => API.get('/api/downloads'
    + (target ? '?target=' + encodeURIComponent(target) : '')
    + (kind ? (target ? '&' : '?') + 'kind=' + encodeURIComponent(kind) : '')),
  downloadStart: (b) => API.post('/api/download/start', b),
  downloadJob: (id) => API.get('/api/download/job?id=' + encodeURIComponent(id)),
  downloadRemove: (b) => API.post('/api/download/remove', b),
  keys: (target) => API.get('/api/keys'
    + (target ? '?target=' + encodeURIComponent(target) : '')),
  keysSave: (b) => API.post('/api/keys/save', b),
  keysPromote: (b) => API.post('/api/keys/promote', b),
  annotate: (b) => API.post('/api/annotate', b),
  rawRead: (path) => API.get('/api/raw?path=' + encodeURIComponent(path || '')
    + '&target=' + encodeURIComponent((typeof APP !== 'undefined' && APP.target) || '')),
  rawSave: (path, text) => API.post('/api/raw/save', {
    path, text, target: (typeof APP !== 'undefined' && APP.target) || ''
  })
};

/* ---------- 小工具 ---------- */

function esc(s) {
  // 引号也要转义：这个函数不只用在文本位置，还用在 value="..." / title="..." 里
  // （state.js 的选项输入框就是）。只转 & < > 的话，一个带引号的值
  // ——比如工具自己写出的 sub-color="#FFD766"——会把属性提前闭合，
  // 输入框渲染成空的，用户看到还以为配置丢了。
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** 把 mpv.conf 文本着色成 HTML（注释灰、键蓝、值绿） */
function paintConf(text) {
  return String(text || '').split('\n').map(line => {
    const t = line.trim();
    if (!t) return '';
    if (t.startsWith('#')) return `<span class="c">${esc(line)}</span>`;
    const i = line.indexOf('=');
    if (i < 0) return esc(line);
    const k = line.slice(0, i);
    const v = line.slice(i + 1);
    return `<span class="k">${esc(k)}</span>=<span class="v">${esc(v)}</span>`;
  }).join('\n');
}

function toast(msg, kind) {
  let box = document.getElementById('toast');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toast';
    // 放右下角、不吃点击、报错自动变长：不挡预览正文
    box.style.cssText = `position:fixed;right:22px;bottom:18px;
      background:var(--panel);border:1px solid var(--border);color:var(--text);
      padding:10px 15px;border-radius:12px;box-shadow:var(--shadow);z-index:99;
      max-width:min(420px,42vw);font-size:13px;line-height:1.5;
      transition:opacity .18s, transform .18s;opacity:0;transform:translateY(6px);
      pointer-events:none`;
    document.body.appendChild(box);
  }
  box.textContent = msg;
  box.style.borderColor = kind === 'err' ? 'var(--danger)'
    : kind === 'ok' ? 'var(--ok)' : 'var(--border)';
  box.style.opacity = '1';
  box.style.transform = 'none';
  clearTimeout(box._t);
  box._t = setTimeout(() => {
    box.style.opacity = '0';
    box.style.transform = 'translateY(6px)';
  }, kind === 'err' ? 6000 : 2600);
}

/** 长路径中间省略，但保住盘符和结尾；鼠标悬停看全路径 */
function shortPath(p, head, tail) {
  p = String(p == null ? '' : p);
  head = head == null ? 14 : head;
  tail = tail == null ? 24 : tail;
  if (p.length <= head + tail + 1) return p;
  return p.slice(0, head) + '…' + p.slice(p.length - tail);
}

function pickValue(containerId) {
  const el = document.querySelector(`#${containerId} .pick.on`);
  return el ? el.dataset.value : '';
}

function initThemeBtn() {
  document.querySelectorAll('[data-theme-toggle]').forEach(b => {
    b.onclick = () => {
      const r = document.documentElement;
      r.dataset.theme = r.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('mpvcb-theme', r.dataset.theme); } catch (e) {}
    };
  });
}

/* ---------- 顶栏常驻入口（U-1） ----------

   起因：这三处入口原本只写在 index.html 的卡片里，进了任何内页就再也看不见，
   想切去体检/快捷键/下载中心只能先退回首页 —— 用户原话是「只在第一页很容易视而不见」。

   做法：和 advanced/expert 的侧栏一样，**在这一处定义、由 JS 注入到每个页面**。
   9 个页面全都加载了 api.js，所以不用去改 9 份 HTML 里的 topbar 副本
   （复制 9 遍的话，以后加一个入口就得记得改 9 处，迟早漏一个）。

   ⚠ 两个坑：
   1. api.js 在 </body> 前加载，那时 .topbar 已经解析完了，可以直接插；
   2. 变量名别用 target / _ / A 这种通用名 —— downloads.html 的入参就叫 target，
      撞了会静默改掉页面行为。所以这里统一用 TOPBAR_* / HERE_ / isHere() 前缀。

   另外：每个页面里「指向自己」的那个链接会跳过不渲染
   （在体检页上再显示一个「配置体检」按钮，点了什么也不会发生，很怪）。 */

const TOPBAR_LINKS = [
  {
    href: 'analyze.html', icon: '🩺', label: '配置体检', title: '不用改任何东西，出一份体检报告',
    isHere: () => document.body.dataset.page === 'analyze'
  },
  {
    href: 'keys.html', icon: '⌨️', label: '快捷键', title: '改 mpv 实际在用的键位表',
    isHere: () => document.body.dataset.page === 'keys'
  },
  {
    href: 'downloads.html', icon: '📦', label: '下载中心', title: '脚本 / 字体 / 一键装 mpv-lazy',
    isHere: () => document.body.dataset.page === 'downloads'
  }
];

/** body 的 data-page 是哪个页面（写错了就等于没有「当前页」判断，不影响功能） */
function PAGE_() {
  return (document.body && document.body.dataset.page) || '';
}

/** 这个入口是不是当前页 —— 用 body 的 data-page 判断，不用 location.pathname，
    因为页面既能用 http:// 打开、也能被 Electron 用 file:// 载入 */
function isHere(item) {
  try { return !!item.isHere(); } catch (e) { return false; }
}

function initTopbarNav() {
  const bar = document.querySelector('.topbar');
  if (!bar || bar.querySelector('.topnav')) return;   // 没有顶栏 / 已经注入过

  const wrap = document.createElement('div');
  wrap.className = 'topnav';
  wrap.setAttribute('role', 'navigation');
  wrap.setAttribute('aria-label', '常驻入口');

  TOPBAR_LINKS.forEach(item => {
    const here = isHere(item);
    if (here) {
      // 当前页显示成不可点的指示，而不是直接隐藏 ——
      // 隐藏的话在体检页上只看得到「快捷键 / 下载中心」两个，
      // 看不出这里其实是一组三项导航（用户抱怨的正是「视而不见」）。
      const span = document.createElement('span');
      // ⚠ 不要加 btn/small 类：它们是按钮样式，权重 (0,2,0) 会压过 .topnav-cur，
      // 结果当前页那条变成「圆角按钮框 + 下划线」两套视觉打架（实测踩过）
      span.className = 'topnav-cur';
      span.title = '你正在这一页';
      span.setAttribute('aria-current', 'page');
      span.innerHTML = `<span class="topnav-ico" aria-hidden="true">${item.icon}</span>`
        + `<span>${item.label}</span><span class="topnav-dot" aria-hidden="true">✓</span>`;
      wrap.appendChild(span);
      return;
    }
    const a = document.createElement('a');
    a.className = 'topnav-link';        // 同上：不加 btn 类
    a.href = item.href;
    a.title = item.title;
    a.innerHTML = `<span class="topnav-ico" aria-hidden="true">${item.icon}</span>`
      + `<span>${item.label}</span>`;
    wrap.appendChild(a);
  });

  // 插入位置：在 .spacer 之后、各页自己的操作按钮之前 ——
  // 靠右但不跟「生成配置」这种主操作抢位置
  const spacer = bar.querySelector('.spacer');
  if (spacer && spacer.nextSibling) bar.insertBefore(wrap, spacer.nextSibling);
  else bar.appendChild(wrap);
}

function initTheme() {
  try {
    const t = localStorage.getItem('mpvcb-theme');
    if (t) document.documentElement.dataset.theme = t;
  } catch (e) {}
  initThemeBtn();
}

function promptTarget() {
  const cur = (APP && APP.target) || '';
  const v = prompt('mpv 配置目录（一般是 portable_config）：', cur);
  if (v !== null) setTarget(v.trim());
}

/* ---------- 语言切换按钮 ----------

   和顶栏（U-1）完全是同一个道理：9 个页面全都加载了 api.js，所以切换入口
   **在这一处定义、由 JS 注入到每个页面**，不用去改 9 份 HTML 里的 topbar 副本
   （复制 9 遍的话，以后改这个按钮就得记得改 9 处，迟早漏一个）。

   ⚠ 两个前提，踩过才知道：
   1. 页面必须先加载 `i18n.js` + `i18n-zh2en.js`，否则 `window.I18N` 不存在。
      这种页面**直接不注入** —— 宁可没有按钮，也不要一个点了没反应的按钮。
   2. 页面自己已经写了 `[data-lang-toggle]` 的就跳过，免得出现两个按钮。 */

function initLangToggle() {
  if (!window.I18N) return;
  const bar = document.querySelector('.topbar');
  if (!bar || bar.querySelector('[data-lang-toggle]')) return;
  const b = document.createElement('button');
  b.className = 'btn small';
  b.setAttribute('data-lang-toggle', '');
  bar.appendChild(b);
  window.I18N.bindToggle();
}

/* ---------- 状态栏 / 后端离线提示 / 请求进度（界面打磨第一批） ----------

   起因（用户原话）：「后端挂了**白屏，什么都不说**，用户以为软件坏了」、
   「看不到当前配置文件路径、改动几处、后端是否活着」、
   「读配置、扫描 shader 目录时像卡死」。
   三样东西回答的是同一个问题：**现在到底怎么了**。所以放在一起做。

   ⚠ 为什么写在 api.js 里，不新建文件：9 个页面全都加载了 api.js
   （顶栏 / 主题 / 语言切换都在这里），加在这里等于**零 HTML 改动**；
   新建 statusbar.js 就得给 9 份 HTML 各加一个 script 标签，
   以后改一处要记得改 9 处 —— 正是顶栏那条注释里写过的教训。

   可测试性：`MPVCB.ping()` 单独暴露出来，测试里把 `API.status` 换成抛错的桩
   就能验证离线横幅。别想着"把后端进程杀掉再测" —— 服务没了页面也加载不出来。 */

const SB = {
  bar: null, banner: null, busy: null,
  inflight: 0, timer: null, alive: null, changes: null, target: ''
};

/** 取一条翻译；i18n.js 没加载时退回中文（中文是原文，本来就不用翻） */
function SBT(key, fallback, vars) {
  try { return window.I18N ? window.I18N.t(key, vars) : fallback; } catch (e) { return fallback; }
}

function initStatusbar() {
  if (document.querySelector('.statusbar')) return;
  const bar = document.createElement('div');
  bar.className = 'statusbar';
  bar.innerHTML =
    '<span class="sb-target" title=""></span>' +
    '<span class="sb-spacer"></span>' +
    '<span class="sb-changes"></span>' +
    '<span class="sb-backend"><i class="sb-dot"></i><span class="sb-text"></span></span>';
  document.body.appendChild(bar);
  document.body.classList.add('has-statusbar');
  SB.bar = bar;
  SB.busy = null;
  const busy = document.createElement('div');
  busy.className = 'busy-bar';
  busy.style.width = '0';
  document.body.appendChild(busy);
  SB.busy = busy;

  // 切语言后这两处是 JS 写的，DOM 属性刷不到，得手动重画
  document.addEventListener('i18n:change', paintStatusbar);
  paintStatusbar();
}

function paintStatusbar() {
  if (!SB.bar) return;
  const t = SB.bar.querySelector('.sb-target');
  const c = SB.bar.querySelector('.sb-changes');
  const s = SB.bar.querySelector('.sb-backend .sb-text');
  if (t) { t.textContent = SB.target ? SB.target : SBT('status.targetEmpty', '未选择'); t.title = SB.target || ''; }
  if (c) {
    c.textContent = (SB.changes === null || SB.changes === undefined)
      ? '' : SBT('status.changes', '改动 ' + SB.changes + ' 处', { changes: SB.changes });
  }
  if (s) {
    s.textContent = SB.alive === false ? SBT('status.backendOff', '后端没响应')
      : SB.alive === true ? SBT('status.backendOn', '后端在线')
      : SBT('status.backendUnknown', '后端状态未知');
  }
}

/** 页面用这个告诉状态栏：目标是谁、改了几处 */
window.MPVCB = window.MPVCB || {};
MPVCB.setTarget = function (p) { SB.target = p || ''; paintStatusbar(); };
MPVCB.setChanges = function (n) { SB.changes = (n === null || n === undefined) ? null : n; paintStatusbar(); };
MPVCB.busy = function (on) {
  SB.inflight = Math.max(0, SB.inflight + (on ? 1 : -1));
  if (SB.busy) SB.busy.style.width = SB.inflight > 0 ? '60%' : '100%';
  if (SB.inflight === 0 && SB.busy) {
    // 跑满了再收：宽度先到 100% 再淡出，比直接归零更像"做完了"
    setTimeout(function () { if (SB.inflight === 0 && SB.busy) SB.busy.style.opacity = '0'; }, 180);
    setTimeout(function () {
      if (SB.inflight === 0 && SB.busy) { SB.busy.style.width = '0'; SB.busy.style.opacity = '1'; }
    }, 420);
  }
};

/** 请求在飞的时候显示顶部进度条：39 个 API 方法全部经过 API.invoke，
    所以在这里包一层，全站都有反馈，不用每个页面自己写 */
const _rawInvoke = API.invoke.bind(API);
API.invoke = async function (method, url, body) {
  MPVCB.busy(true);
  try {
    return await _rawInvoke(method, url, body);
  } finally {
    MPVCB.busy(false);
  }
};

function showOffline() {
  if (SB.banner) return;
  const b = document.createElement('div');
  b.className = 'offline-banner';
  b.innerHTML = '<span class="ob-text"></span><button class="btn small ob-retry"></button>';
  document.body.appendChild(b);
  SB.banner = b;
  b.querySelector('.ob-retry').onclick = function () { MPVCB.ping(); };
  paintBanner();
  document.addEventListener('i18n:change', paintBanner);
}

function paintBanner() {
  if (!SB.banner) return;
  SB.banner.querySelector('.ob-text').textContent = SBT('status.offline', '后端没有响应，界面还在但读不到配置');
  SB.banner.querySelector('.ob-retry').textContent = SBT('status.retry', '重试');
}

function hideOffline() {
  if (SB.banner) { SB.banner.remove(); SB.banner = null; }
  document.removeEventListener('i18n:change', paintBanner);
}

/** 探一次后端。抛错 = 离线：状态栏变红 + 顶部横幅 */
MPVCB.ping = async function () {
  try {
    const r = await API.status();
    SB.alive = !!(r && r.title);
    if (SB.alive) {
      if (r.target && !SB.target) SB.target = r.target;
      hideOffline();
    } else {
      showOffline();
    }
  } catch (e) {
    SB.alive = false;
    showOffline();
  }
  if (SB.bar) {
    SB.bar.classList.toggle('is-on', SB.alive === true);
    SB.bar.classList.toggle('is-off', SB.alive === false);
  }
  paintStatusbar();
  return SB.alive;
};

function initBackendWatch() {
  MPVCB.ping();
  if (!SB.timer) SB.timer = setInterval(function () { MPVCB.ping(); }, 15000);
}

/* ---------- 右键菜单 ----------

   起因（待做.md §一）：「想恢复默认 / 复制选项名 / 看手册原文，无从下手」。
   做成**通用组件** `MPVCB.contextMenu(items, x, y)`，任何页面都能用；
   右键 `.opt` 行的默认菜单在这里定义 —— 一处定义，expert / advanced 都生效。

   ⚠ 动作全靠**模拟已有控件的点击**（勾选框 / 那个 `i` 按钮），
     不去碰 state.js 的内部状态 —— 否则这里就得知道选项怎么算值，
     而那正是 §2.10 警告过的"顺手统一"。 */

function escTxt(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (ch) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
  });
}

const CTX = { el: null };

function closeContextMenu() {
  if (!CTX.el) return;
  CTX.el.remove();
  CTX.el = null;
  document.removeEventListener('click', onDocClickCtx, true);
  document.removeEventListener('keydown', onKeyCtx, true);
}

function onDocClickCtx() { closeContextMenu(); }
function onKeyCtx(e) {
  if (e.key === 'Escape') { e.stopPropagation(); closeContextMenu(); }
}

window.MPVCB.contextMenu = function (items, x, y) {
  closeContextMenu();
  const list = (items || []).filter(Boolean);
  if (!list.length) return;
  const m = document.createElement('div');
  m.className = 'ctx-menu';
  m.setAttribute('role', 'menu');
  m.innerHTML = list.map(function (it) {
    return '<button class="ctx-item" role="menuitem" data-act="' + escTxt(it.act) + '">'
      + escTxt(it.label) + '</button>';
  }).join('');
  document.body.appendChild(m);
  // 别跑出视口：先量一次再定位
  const r = m.getBoundingClientRect();
  m.style.left = Math.max(4, Math.min(x, window.innerWidth - r.width - 8)) + 'px';
  m.style.top = Math.max(4, Math.min(y, window.innerHeight - r.height - 8)) + 'px';
  m.addEventListener('click', function (ev) {
    const b = ev.target.closest('.ctx-item');
    if (!b) return;
    const it = list.filter(function (i) { return i.act === b.dataset.act; })[0];
    closeContextMenu();
    if (it && typeof it.run === 'function') it.run();
  });
  CTX.el = m;
  // 延后一帧再挂"点别处就关"的监听：否则打开菜单的那次 click 自己就会把它关掉
  setTimeout(function () {
    document.addEventListener('click', onDocClickCtx, true);
    document.addEventListener('keydown', onKeyCtx, true);
  }, 0);
};

function copyText(t) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(t).catch(function () { copyFallback(t); });
    return;
  }
  copyFallback(t);
}

function copyFallback(t) {
  const ta = document.createElement('textarea');
  ta.value = t;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch (e) {}
  ta.remove();
}

/** 右键 .opt 行的菜单项。动作全部委托给已有控件，不碰 state.js 的内部状态 */
function optMenuItems(row) {
  const key = row.dataset.key || '';
  const items = [
    { act: 'copykey', label: SBT('ctx.copyKey', '复制选项名'), run: function () { copyText(key); } }
  ];
  const val = (window.MPVCB && APP.values) ? APP.values[key] : undefined;
  if (val !== undefined && val !== '') {
    items.push({ act: 'copyval', label: SBT('ctx.copyValue', '复制当前值'),
      run: function () { copyText(String(val)); } });
  }
  if (row.classList.contains('on')) {
    items.push({ act: 'reset', label: SBT('ctx.reset', '恢复默认（取消勾选）'),
      run: function () {
        const cb = row.querySelector('input[data-role="check"]');
        if (cb && cb.checked) cb.click();          // 走页面自己的事件链，别直接改 DOM
      } });
  }
  items.push({ act: 'info', label: SBT('ctx.info', '完整说明'),
    run: function () {
      const b = row.querySelector('[data-role="info"]');
      if (b) b.click();
    } });
  return items;
}

function initContextMenu() {
  document.addEventListener('contextmenu', function (e) {
    const row = (e.target && e.target.closest) ? e.target.closest('.opt') : null;
    if (!row) return;                              // 其它地方仍用浏览器默认菜单
    e.preventDefault();
    window.MPVCB.contextMenu(optMenuItems(row), e.clientX, e.clientY);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initTopbarNav();
  initTheme();
  initLangToggle();
  initStatusbar();
  initBackendWatch();
  initContextMenu();
});

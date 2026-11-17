/* MPV Config Builder · 前端与 Python 后端的桥
   所有真实逻辑都在 Python 的 core/ 里，这里只负责发请求与渲染。

   ---------- 两种传输，界面无感（W-4 第②③步）----------

   HTTP     浏览器里直接开页面用（开发 / 调试 / 实机测试脚本）。
   stdio    Tauri 外壳里用：外壳 spawn 后端，一行一条 JSON 走管道，**不开端口**。

   切换点在 `invoke()`：只要 `window.__MPVCB_INVOKE__` 存在就走 stdio，否则 fetch。
   这个全局由 Tauri 的注入脚本（main.rs 里的 INIT_SCRIPT）提供 —— **页面自己不知道跑在哪种传输下**，
   也不需要知道。所以下面 39 个方法一个都不用改。

   ⚠ 两种传输的**错误形状必须一致**：
   后端 HTTP 模式回 `{ok:false, detail:"..."}`，stdio 协议回 `{ok:false, error:"..."}`。
   页面里 64 处都在读 `r.detail`，所以 invoke() 负责把 `error` 映射成 `detail`
   —— 否则外壳下每个报错都会显示成 undefined。 */

/** 有没有外壳给的调用通道。没有就是普通浏览器。 */
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
  // 版本级兼容检测（待做 §〇 第 13 项）：探测到的 mpv 版本 + 它不支持的参数集合
  compat: () => API.get('/api/compat'),
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

/** 写完之后 12 秒内一键撤回（R-28）。
    只对「刚刚这一次写入」生效：拿后端返回的备份路径调 /api/restore。
    撤回本身也会先备份当前版本，所以撤错了还能再回来 —— 不是把文件删了。 */
function offerUndo(backs, seconds) {
  if (!backs || !backs.length) return;
  seconds = seconds || 12;
  let bar = document.getElementById('undoBar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'undoBar';
    bar.className = 'undo-bar';
    document.body.appendChild(bar);
  }
  bar.innerHTML = `<span>${I18N.t('undo.hint', { n: seconds })}</span>
    <button type="button" class="btn small" data-role="undo">${I18N.t('undo.action')}</button>`;
  let left = seconds;
  const tick = setInterval(() => {
    left -= 1;
    const s = bar.querySelector('span');
    if (s) s.textContent = I18N.t('undo.hint', { n: Math.max(0, left) });
    if (left <= 0) stop();
  }, 1000);
  function stop() { clearInterval(tick); bar.remove(); }
  bar.onclick = async e => {
    if (!e.target.closest('[data-role="undo"]')) return;
    stop();
    let bad = '';
    for (const p of backs) {
      const r = await API.post('/api/restore', { path: p });
      if (!r.ok) bad = r.detail || p;
    }
    toast(bad ? I18N.t('undo.fail', { d: bad }) : '✅ ' + I18N.t('undo.done'), bad ? 'err' : 'ok');
  };
}

/** 长路径中间省略，但保住盘符和结尾；鼠标悬停看全路径 */
function shortPath(p, head, tail) {
  p = String(p == null ? '' : p);
  head = head == null ? 14 : head;
  tail = tail == null ? 24 : tail;
  if (p.length <= head + tail + 1) return p;
  return p.slice(0, head) + '…' + p.slice(p.length - tail);
}

/** 保存/应用成功的按钮回执（R-27）：绿色 ✓ 覆盖层 600ms 自淡出。
    覆盖层是 absolute 的，只动 opacity/transform，不挤动布局、不阻塞点击。
    ⚠ 此处 MPVCB 尚未在状态栏段初始化，必须走 window 挂载 */
window.MPVCB = window.MPVCB || {};
MPVCB.ack = function (btn) {
  if (!btn || !btn.classList) return;
  btn.classList.remove('ack-ok');
  void btn.offsetWidth;                // 强制回流：连续保存也能重启动画
  btn.classList.add('ack-ok');
  clearTimeout(btn._ackT);
  btn._ackT = setTimeout(function () { btn.classList.remove('ack-ok'); }, 620);
};

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
      // 通知自绘标题栏（R-29）同步 overlay 配色；浏览器里没有监听者，无副作用
      document.dispatchEvent(new CustomEvent('mpvcb:theme'));
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
    因为页面既能用 http:// 打开、也能被外壳用资源协议载入 */
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

/* ---------- 自绘标题栏（R-29）—— 2026-11-16 随 Electron 一起移除 ----------

   原来是给 Electron 的 `titleBarStyle: 'hidden'` 配的：页面顶栏顶上去当拖拽区、
   窗口三键由系统 overlay 绘制、主题经 `__MPVCB_WINDOW__` 推给主进程换色。
   Electron 整体移除后这三个前提都没了（Tauri 用的是系统标题栏），留着就是死代码
   —— 唯一效果是给 <html> 挂一个谁也不再消费的 `in-electron` 类。
   将来若在 Tauri 侧补自绘标题栏（R-29 的后续项），重新按 Tauri 的窗口 API 写。 */

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
    '<span class="sb-backend"><i class="sb-dot"></i><span class="sb-text"></span></span>' +
    '<button class="sb-keys" type="button" title=""></button>';
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
  const kb = SB.bar.querySelector('.sb-keys');
  if (kb) {
    kb.textContent = '? ' + SBT('hk.statusHint', '快捷键');
    kb.title = SBT('hk.statusHintTitle', '看有哪些键盘快捷键');
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
    所以在这里包一层，全站都有反馈，不用每个页面自己写。
    同时在这里**统一附上当前语言**（T14）：GET 走 query、POST 走 body.lang，
    后端据此返回对应语言的文案；I18N 没加载时缺省，后端回中文。
    静态模式（Q-006 裁决 A，第 12 项）：探测不到后端时 API.invoke 直接失败，
    页面各自降级；静态数据走 API.staticData（相对路径取仓库里的 JSON），
    **故意用 fetch** —— 上面「不许直接 fetch」的规矩针对的是外壳 stdio
    通道下的后端调用；静态模式按定义没有后端，fetch 仓库静态文件是唯一路径。 */
const _rawInvoke = API.invoke.bind(API);
API.invoke = async function (method, url, body) {
  MPVCB.busy(true);
  try {
    if (MPVCB.STATIC) {
      return { ok: false, detail: I18N.t('static.mode'), static: true };
    }
    const lang = (typeof window.I18N === 'object' && window.I18N.lang) ? window.I18N.lang() : '';
    if (lang && lang !== 'zh-CN') {
      if (method === 'POST') {
        body = Object.assign({}, body || {}, { lang: lang });
      } else {
        url = url + (url.indexOf('?') < 0 ? '?' : '&') + 'lang=' + encodeURIComponent(lang);
      }
    }
    return await _rawInvoke(method, url, body);
  } finally {
    MPVCB.busy(false);
  }
};

/* ---------- 静态模式（Q-006 裁决 A：github.io 映射） ----------

   部署形态 = 仓库根直接上 GitHub Pages：页面在 /webui/static/，
   数据 JSON 在 /data/（**不复制**，仓库里只有一份），文档 md 在仓库根。
   页面加载后探测一次 /api/status：
   · 通了 → 一切照旧（本地服务 / 外壳）
   · 不通（Pages / file://）→ MPVCB.STATIC = true，API.invoke 统一返回
     「静态模式」响应，页面用它降级；需要数据的页面走 API.staticData。

   staticData 按候选路径依次试（仓库根部署 → 静态目录部署），命中即缓存。 */

MPVCB.STATIC = false;
const _staticCache = {};
API.probeStatic = async function () {
  try {
    const r = await _rawInvoke('GET', '/api/status');
    if (r && r.ok !== false) return false;          // 后端在，不是静态模式
  } catch (e) { /* 探测失败 = 没后端 */ }
  MPVCB.STATIC = true;
  return true;
};
API.staticData = async function (name) {
  if (_staticCache[name]) return _staticCache[name];
  const candidates = ['../data/' + name, 'data/' + name];
  for (const rel of candidates) {
    try {
      const resp = await fetch(rel);
      if (!resp.ok) continue;
      const data = await resp.json();
      _staticCache[name] = data;
      return data;
    } catch (e) { /* 试下一个候选路径 */ }
  }
  return null;
};
/* 加载即分类：GitHub Pages 等静态托管（https + 非本机）不可能有本机后端，
   直接判静态；本机形态（localhost / 资源协议）再异步探测一次兜底。
   api.js 在页面内联脚本之前执行，所以页面 boot() 发起的第一个调用就已带上
   正确的分类，不会闪一次错误横幅。 */
(function () {
  const h = location.hostname;
  if (location.protocol === 'https:' && h && !/^(localhost|127\.)/.test(h)) {
    MPVCB.STATIC = true;
    return;
  }
  API.probeStatic().then((isStatic) => { MPVCB.STATIC = isStatic; });
})();

API.staticText = async function (name) {
  const candidates = ['../' + name, name];
  for (const rel of candidates) {
    try {
      const resp = await fetch(encodeURI(rel));
      if (!resp.ok) continue;
      return await resp.text();
    } catch (e) { /* 试下一个候选路径 */ }
  }
  return null;
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

/* ---------- 键盘快捷键层（界面打磨·第一切片，R-28） ----------

   起因（待做.md §一）：「基本全靠鼠标，改一个选项要点半天」。
   放在 api.js 的理由与顶栏 / 状态栏 / 右键菜单完全相同：9 页共用一处定义，
   零 HTML 改动。方案、集合与边界见 DECISIONS.md 2026-11-08（R-28），要点：

   · Ctrl+S = 本页主操作；? = 帮助面板；Esc = 关面板；
     ↓/↑ = 选项行之间移动焦点（锚点 = 行内勾选框）；Enter = 展开该行说明；
     Space 勾选是浏览器原生行为，不实现。
   · 危险动作不绑全局键：hell 的覆盖写入、downloads 的开始安装**不在表里** ——
     全局键的本质是降低触发成本，而那两页的设计恰恰是给危险动作加摩擦。
   · 打字优先：焦点在文本输入控件里时 ?/↓↑/Enter 一律不拦；
     Ctrl+S 例外（「保存」语义在输入框里同样成立）。
   · 映射表是单一来源，HTML 改 id 会让它静默失效 —— 由静态测试
     （id 必须真实存在）+ verify.py hotkeys（按键后按钮真的被点了）双层守护。 */

const HOTKEY_PRIMARY = {
  basic: '#applyBtn',
  advanced: '#applyTop',
  expert: '#applyTop',
  analyze: '#analyzeFile',
  keys: '#saveBtn'
  // hell（#save 直接覆盖写入）/ downloads（#lzGo 开始安装）按 R-28 故意缺席；
  // index / guide 没有主操作。缺席页面的 Ctrl+S 不拦浏览器默认。
};

const HK = { el: null };

function hotkeyVisible(el) {
  return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
}

/** 焦点是否在「打字」的控件里。勾选框 / 按钮不算 —— 方向键导航要能用它们当锚点 */
function hotkeyIsTextInput(t) {
  if (!t || !t.tagName) return false;
  if (t.isContentEditable) return true;
  const tag = t.tagName.toLowerCase();
  if (tag === 'textarea') return true;
  if (tag !== 'input') return false;
  const type = (t.getAttribute('type') || 'text').toLowerCase();
  return type !== 'checkbox' && type !== 'radio' && type !== 'button';
}

/** 本页主操作按钮；没有映射 / 被禁用 / 不可见时返回 null（按键就不做任何事） */
function hotkeyPrimaryBtn() {
  const sel = HOTKEY_PRIMARY[PAGE_()];
  if (!sel) return null;
  const b = document.querySelector(sel);
  if (!b || b.disabled || !hotkeyVisible(b)) return null;
  return b;
}

/** 可见的选项行勾选框（方向键的锚点）。expert 的空视图没有 .opt 行，自然不生效 */
function hotkeyRowBoxes() {
  return Array.prototype.filter.call(
    document.querySelectorAll('.opt input[data-role="check"]'), hotkeyVisible);
}

function hotkeyFocusRow(dir) {
  const boxes = hotkeyRowBoxes();
  if (!boxes.length) return false;
  const cur = document.activeElement;
  const row = (cur && cur.closest) ? cur.closest('.opt') : null;
  const i = row ? boxes.findIndex(function (b) { return b.closest('.opt') === row; }) : -1;
  // 没有任何行被聚焦时，↓ 从第一行开始；↑ 无处可去就不动
  let next = i < 0 ? (dir > 0 ? 0 : -1) : i + dir;
  if (next < 0 || next >= boxes.length) return false;
  boxes[next].focus();
  boxes[next].closest('.opt').scrollIntoView({ block: 'nearest' });
  return true;
}

/* ---- 帮助面板：只列本页真实生效的条目（不吹不存在的能力） ---- */

function hkEntries() {
  const list = [];
  if (HOTKEY_PRIMARY[PAGE_()]) {
    list.push(['Ctrl + S', SBT('hk.primary', '触发本页主操作（生成配置 / 保存）')]);
  }
  if (document.querySelector('.opt input[data-role="check"]')) {
    list.push(['\u2193 / \u2191', SBT('hk.nav', '在选项之间移动')]);
    list.push(['Space', SBT('hk.toggle', '勾选 / 取消勾选')]);
    list.push(['Enter', SBT('hk.info', '看这一行的完整说明')]);
  }
  list.push(['?', SBT('hk.help', '打开本面板')]);
  list.push(['Esc', SBT('hk.esc', '关闭面板')]);
  return list;
}

function paintHotkeyHelp() {
  if (!HK.el) return;
  HK.el.querySelector('.hk-title').textContent = SBT('hk.title', '键盘快捷键');
  HK.el.querySelector('.hk-close').textContent = SBT('hk.close', '关闭');
  HK.el.querySelector('.hk-list').innerHTML = hkEntries().map(function (it) {
    return '<div class="hk-row"><kbd>' + escTxt(it[0]) + '</kbd>'
      + '<span>' + escTxt(it[1]) + '</span></div>';
  }).join('');
}

function toggleHotkeyHelp(force) {
  const want = (force === undefined) ? !HK.el : !!force;
  if (want && !HK.el) {
    const p = document.createElement('div');
    p.className = 'hotkey-help';
    p.innerHTML = '<div class="hk-card" role="dialog" aria-label="">'
      + '<div class="hk-head"><span class="hk-title"></span>'
      + '<button class="btn small hk-close" type="button"></button></div>'
      + '<div class="hk-list"></div></div>';
    document.body.appendChild(p);
    HK.el = p;
    p.querySelector('.hk-close').onclick = function () { toggleHotkeyHelp(false); };
    p.addEventListener('click', function (e) { if (e.target === p) toggleHotkeyHelp(false); });
    paintHotkeyHelp();
    // 面板是 JS 渲染的，切语言后 DOM 属性刷不到，得手动重画（同状态栏）
    document.addEventListener('i18n:change', paintHotkeyHelp);
  } else if (!want && HK.el) {
    HK.el.remove();
    HK.el = null;
    document.removeEventListener('i18n:change', paintHotkeyHelp);
  }
}

function onHotkeyKey(e) {
  if (e.ctrlKey || e.metaKey) {
    if ((e.key === 's' || e.key === 'S') && !e.altKey && !e.shiftKey) {
      // 打字时也放行：保存语义在输入框里同样成立（R-28 决策 5）。
      // 没有映射的页面不拦 —— 浏览器默认行为保持原样。
      const b = hotkeyPrimaryBtn();
      if (b) { e.preventDefault(); b.click(); }
    }
    return;
  }
  if (e.altKey) return;
  if (e.key === '?') {
    if (hotkeyIsTextInput(e.target)) return;   // 搜索框里打 ? 必须还是打字
    e.preventDefault();
    toggleHotkeyHelp();
    return;
  }
  if (e.key === 'Escape') {
    if (HK.el) { e.preventDefault(); toggleHotkeyHelp(false); }
    return;                                    // 右键菜单的 Esc 有自己的处理，不掺和
  }
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    if (hotkeyIsTextInput(e.target)) return;
    if ((e.target.tagName || '').toLowerCase() === 'select') return;  // 下拉自己的方向键
    if (!hotkeyRowBoxes().length) return;      // 没有选项行的页面放行原生滚动
    e.preventDefault();
    hotkeyFocusRow(e.key === 'ArrowDown' ? 1 : -1);
    return;
  }
  if (e.key === 'Enter') {
    if (hotkeyIsTextInput(e.target)) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'button' || tag === 'a' || tag === 'select') return;  // 它们自己响应 Enter
    const row = (e.target.closest) ? e.target.closest('.opt') : null;
    const info = row ? row.querySelector('[data-role="info"]') : null;
    if (!info) return;
    e.preventDefault();
    info.click();
  }
}

function initHotkeys() {
  document.addEventListener('keydown', onHotkeyKey);
  const kb = document.querySelector('.sb-keys');
  if (kb) kb.onclick = function () { toggleHotkeyHelp(); };
}

/* ---------- 全站搜索（配置项 / uosc / 键位 / 脚本）----------

   9 个页面都能用：入口按钮和弹层在这里定义一次，由 api.js 注入，
   不用去改 9 份 HTML。搜的是后端 /api/search，只读，不写任何文件。 */

function copyText(text) {
  const done = () => toast('已复制：' + text, 'ok');
  const fail = () => toast('复制失败，请手动选中：' + text, 'err');
  try {
    navigator.clipboard.writeText(text).then(done).catch(fail);
  } catch (e) {
    fail();
  }
}

async function runGlobalSearch(q) {
  const out = document.getElementById('gsearchOut');
  if (!out) return;
  if (!q.trim()) { out.innerHTML = '<p class="note">输入关键词后回车。</p>'; return; }
  out.innerHTML = '<p class="note">搜索中…</p>';
  const target = (window.APP && APP.target) || '';
  const url = '/api/search?q=' + encodeURIComponent(q)
    + (target ? '&target=' + encodeURIComponent(target) : '');
  const r = await API.get(url);
  if (!r.ok) { out.innerHTML = `<p class="note danger">${esc(r.detail)}</p>`; return; }
  if (!r.total) {
    out.innerHTML = `<p class="note">没找到「${esc(q)}」。键名、中文名都能搜；
      键位与脚本要先在页面里选过目标目录才会出现。</p>`;
    return;
  }
  out.innerHTML = r.groups.map(g => `<div class="gsearch-group">
    <div class="gsearch-gname">${esc(g.name)}</div>
    ${g.items.map(it => `<button class="gsearch-item" data-copy="${esc(it.copy)}">
      <code>${esc(it.key)}</code>
      <span>${esc(it.title)}</span>
      <small>${esc(it.page_label)} · 点击复制</small>
    </button>`).join('')}
  </div>`).join('');
}

function closeGlobalSearch() {
  const mask = document.getElementById('gsearchMask');
  if (mask) mask.style.display = 'none';
}

function openGlobalSearch() {
  let mask = document.getElementById('gsearchMask');
  if (!mask) {
    mask = document.createElement('div');
    mask.id = 'gsearchMask';
    mask.className = 'gsearch-mask';
    mask.innerHTML = `<div class="gsearch-box" role="dialog" aria-label="全站搜索">
      <div class="gsearch-head">
        <input id="gsearchInput" type="search" spellcheck="false"
          placeholder="搜配置项 / uosc / 键位 / 脚本，回车开始">
        <button class="btn small" id="gsearchClose" type="button">关闭</button>
      </div>
      <div id="gsearchOut" class="gsearch-results"><p class="note">输入关键词后回车。</p></div>
    </div>`;
    document.body.appendChild(mask);
    mask.addEventListener('click', e => {
      if (e.target === mask || e.target.closest('#gsearchClose')) { closeGlobalSearch(); return; }
      const it = e.target.closest('[data-copy]');
      if (it && it.dataset.copy) copyText(it.dataset.copy);
    });
    mask.querySelector('#gsearchInput').addEventListener('keydown', e => {
      if (e.key === 'Enter') runGlobalSearch(e.target.value);
      if (e.key === 'Escape') closeGlobalSearch();
    });
  }
  mask.style.display = 'flex';
  const inp = mask.querySelector('#gsearchInput');
  inp.value = '';
  setTimeout(() => inp.focus(), 0);
}

function initGlobalSearch() {
  const bar = document.querySelector('.topbar');
  if (!bar || bar.querySelector('.gsearch-btn')) return;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'gsearch-btn';
  btn.title = '全站搜索（Ctrl+K）：配置项 / uosc / 键位 / 脚本';
  btn.setAttribute('aria-label', btn.title);
  btn.textContent = '🔎';
  // 挂在顶栏容器而不是 .topnav 列表里：搜索不是导航项，别影响「三入口」检查
  bar.appendChild(btn);
  btn.onclick = openGlobalSearch;
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      openGlobalSearch();
    }
  });
}

/* Tauri 窗口：无边框自绘标题栏 + 右侧窗口按钮。
   浏览器里没有 __TAURI_INTERNALS__，这段是空转，不影响网页版。 */
function initTauriChrome() {
  const internals = window.__TAURI_INTERNALS__;
  if (!internals || typeof internals.invoke !== 'function') return;
  document.documentElement.classList.add('tauri-shell');
  const bar = document.querySelector('.topbar');
  if (bar) bar.setAttribute('data-tauri-drag-region', '');
  const controls = document.createElement('div');
  controls.className = 'win-controls';
  controls.innerHTML =
    '<button class="win-btn" data-win="menu" title="菜单" aria-label="菜单">☰</button>' +
    '<button class="win-btn" data-win="min" title="最小化" aria-label="最小化">—</button>' +
    '<button class="win-btn" data-win="max" title="最大化" aria-label="最大化">□</button>' +
    '<button class="win-btn win-close" data-win="close" title="关闭" aria-label="关闭">✕</button>';
  controls.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-win]');
    if (!btn) return;
    const action = btn.dataset.win;
    if (action === 'menu') internals.invoke('mpvcb_menu').catch(() => {});
    else internals.invoke('mpvcb_window', { action }).catch(() => {});
  });
  (bar || document.body).appendChild(controls);
}

function bootUI() {
  initTauriChrome();
  initTopbarNav();
  initGlobalSearch();
  initTheme();
  initLangToggle();
  initStatusbar();
  initBackendWatch();
  initContextMenu();
  initHotkeys();
}

/* 脚本如果是在 DOMContentLoaded 之后才执行（Tauri 资源加载快时会发生），
   再挂监听就永远不会触发 —— 直接看 readyState 决定跑不跑。 */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootUI);
} else {
  bootUI();
}



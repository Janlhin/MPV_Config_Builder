/* MPV Config Builder · 前端与 Python 后端的桥
   所有真实逻辑都在 Python 的 core/ 里，这里只负责发请求与渲染。 */

const API = {
  async get(path) {
    const r = await fetch(path);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
    return r.json();
  },
  status: () => API.get('/api/status'),
  presets: () => API.get('/api/presets'),
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

document.addEventListener('DOMContentLoaded', initTheme);

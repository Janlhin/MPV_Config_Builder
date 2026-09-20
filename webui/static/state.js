/* MPV Config Builder · 三个模式共用的状态与渲染
   状态结构（和后端 core/builder.py 一致）：
     mode    'create' | 'edit'  ← R-26：我现在是"从零创建"还是"改现有配置"
     values  {key: value}     勾选并填了值的选项
     shaders [path, ...]      glsl 链，顺序即执行顺序
     memc    "~~/vs/x.vpy"    只能选一个
     disable [key, ...]       加载现有配置后被取消勾选的键（**只在 edit 语义下收集**）
     custom  "自定义 key=value 行"
*/

/* 用 var 而不是 const：顶层 var 会挂到 window 上，方便调试与自动化检查 */
var APP = {
  target: '',
  mode: 'create',       // R-26：create=从零创建 / edit=改现有配置
  writeMode: 'include',
  source: '',
  values: {},
  shaders: [],
  memc: '',
  memcLabel: '',        // vf 里原来带的标签（@vs: 之类），别弄丢
  profiles: [],         // 当前加载的文件里的 [小节]
  otherValues: {},      // 读进来的配置里，界面没有对应勾选项的键（只参与冲突检测）
  vpyList: [],          // 目标目录 vs/ 里的脚本（融合面板用）
  vpyError: '',
  fusedPath: '',
  disable: [],
  pending: [],          // 勾了但还没填值的键：只提示，不写进配置
  conflicts: [],        // 选项之间的冲突（来自后端 full_check）
  conflictKeys: {},     // key -> 级别，用来在行上打标记
  custom: '',
  loaded: false,        // 是否已经"读取现有配置"过（edit 语义下必须先读）
  catalog: { shaders: [], memc: [], configs: [] },
  options: { core: [], native: [], groups: [] },
  onStateChange: null
};

/* ---------------- R-26：创建 / 修改 两种语义 ---------------- */

/** 当前是不是"改现有配置"语义。 */
function isEditMode() { return APP.mode === 'edit'; }

/** 主按钮该叫什么 —— 同一个动作只能有一个名字。 */
function primaryLabel() { return isEditMode() ? '应用修改' : '生成配置'; }

/** 预览卡标题。 */
function previewTitle() {
  return isEditMode() ? '合并后的完整文件' : '将生成的配置';
}

/** 切换语义。默认写入方式跟着变，但用户手动改过就不硬拽（见 setWriteMode）。 */
function setMode(mode) {
  const next = mode === 'edit' ? 'edit' : 'create';
  if (next === APP.mode) return;
  APP.mode = next;
  if (next === 'edit') {
    APP.writeMode = 'merge';        // 改现有配置 → 默认改原文件
  } else {
    APP.writeMode = 'include';      // 从零创建 → 默认独立 include 文件
    APP.disable = [];               // 创建语义下不该去注释别人的行
  }
  saveLocal();
  if (typeof renderModeBar === 'function') renderModeBar();
  if (typeof setWriteMode === 'function') setWriteMode(APP.writeMode);
  if (typeof changed === 'function') changed();
}

/**
 * 有没有「勾了但还没填值」的项。这些项不会被写进配置。
 * 创建语义下只提示；修改语义下也不写（值都没有，没法写）。
 */
function pendingCount() { return (APP.pending || []).length; }

/** edit 语义下、还没读取现有配置时，主按钮该不该禁用。 */
function blockedByNoSource() {
  return isEditMode() && !APP.loaded && !APP.source;
}

/** 在页面上渲染「🆕 从零创建 ｜ ✏️ 改现有配置」那一条。 */
function renderModeBar() {
  const seg = document.getElementById('modeSeg');
  if (seg) {
    seg.querySelectorAll('button').forEach(b => {
      b.classList.toggle('on', b.dataset.mode === APP.mode);
    });
  }
  const hint = document.getElementById('modeHint');
  if (hint) {
    if (isEditMode() && !APP.loaded && !APP.source) {
      hint.innerHTML = '✏️ 改现有配置：先点「📂 读取现有配置」，' +
        '否则主按钮不可用（避免你以为在读文件、其实在凭空生成）。';
      hint.className = 'note warn-text';
    } else if (isEditMode()) {
      hint.innerHTML = `✏️ 改现有配置：只改你动过的键，` +
        `原文件其它内容与注释都保留。取消勾选 = 把原来那行<b>注释掉</b>。`;
      hint.className = 'note';
    } else {
      hint.innerHTML = '🆕 从零创建：生成一份新配置。取消勾选只是<b>不写这一项</b>，' +
        '不会去动你已有的文件。';
      hint.className = 'note';
    }
  }
  // 主按钮文案统一
  document.querySelectorAll('[data-primary]').forEach(b => {
    b.textContent = (b.dataset.primaryIcon || '✅') + ' ' + primaryLabel();
    b.disabled = blockedByNoSource();
    b.title = blockedByNoSource() ? '先读取现有配置' : '';
  });
}

/** 接上「创建 / 修改」开关的事件（三个页面共用）。 */
function initModeBar() {
  const seg = document.getElementById('modeSeg');
  if (seg) {
    seg.onclick = e => {
      const b = e.target.closest('button');
      if (b) setMode(b.dataset.mode);
    };
  }
  renderModeBar();
}

/* ---------------- 本地记忆 ---------------- */

function saveLocal() {
  try {
    localStorage.setItem('mpvcb', JSON.stringify({
      target: APP.target, writeMode: APP.writeMode, source: APP.source,
      mode: APP.mode
    }));
  } catch (e) { /* 隐私模式下忽略 */ }
}

function loadLocal() {
  try {
    const raw = localStorage.getItem('mpvcb');
    if (raw) {
      const o = JSON.parse(raw);
      APP.target = o.target || '';
      APP.mode = o.mode === 'edit' ? 'edit' : 'create';
      APP.writeMode = o.writeMode || 'include';
      APP.source = o.source || '';
    }
  } catch (e) { /* 忽略 */ }
}

/* ---------------- 状态读写 ---------------- */

function setOption(key, value) {
  value = String(value == null ? '' : value);
  APP.pending = APP.pending.filter(k => k !== key);
  if (!value.trim()) { delete APP.values[key]; }
  else { APP.values[key] = value; }
  APP.disable = APP.disable.filter(k => k !== key);
  changed();
}

function clearOption(key) {
  APP.pending = APP.pending.filter(k => k !== key);
  if (key in APP.values) {
    delete APP.values[key];
    // R-26：`disable`（取消勾选 → 把原文件那一行注释掉）**只在改现有配置时收集**。
    // 从零创建时记这个毫无意义，只会在合并预览里冒出一堆莫名的注释动作。
    if (isEditMode() && !APP.disable.includes(key)) APP.disable.push(key);
  }
  changed();
}

function markPending(key) {
  if (!APP.pending.includes(key)) APP.pending.push(key);
  changed();
}

function hasOption(key) { return Object.prototype.hasOwnProperty.call(APP.values, key); }
function isOn(key) { return hasOption(key) || APP.pending.includes(key); }

function setState(partial) {
  Object.assign(APP, partial);
  changed();
}

function changed() {
  if (typeof APP.onStateChange === 'function') APP.onStateChange();
  updateSubPreview();          // 字幕预览：跟状态走，不跟输入控件走
  refreshPreview();
}

/** 页面重新渲染（各页面把自己的渲染函数挂到 APP.onRender） */
function rerender() {
  if (typeof APP.onRender === 'function') APP.onRender();
}

/* ---------------- 网络 ---------------- */

async function loadCatalog() {
  const q = APP.target ? ('?target=' + encodeURIComponent(APP.target)) : '';
  const r = await fetch('/api/catalog' + q).then(x => x.json());
  if (r.ok) APP.catalog = r;
  return r;
}

async function loadOptions() {
  if (APP.options.core.length) return APP.options;
  APP.options = await API.options();
  return APP.options;
}

async function loadExistingConfig(path) {
  const r = await API.post('/api/config/load', { path: path || APP.source || APP.target });
  if (!r.ok) { toast('❌ ' + r.detail, 'err'); return r; }
  APP.values = Object.assign({}, r.values);
  APP.otherValues = Object.assign({}, r.other_values || {});
  APP.shaders = (r.shaders || []).slice();
  APP.memc = r.memc || '';
  APP.memcLabel = r.memc_label || '';
  APP.profiles = r.profiles || [];
  APP.source = r.path;
  APP.loaded = true;                  // R-26：edit 语义下"读过文件了"才允许应用
  APP.disable = [];
  APP.pending = [];
  saveLocal();
  renderLoadInfo(r);
  renderModeBar();
  changed();
  let msg = `✅ 已读取 ${r.name}：${r.summary}`;
  if (APP.profiles.length) msg += `；另有 ${APP.profiles.length} 个 profile 没动，需要的话在右边单独载入`;
  toast(msg, 'ok');
  (r.warnings || []).forEach((w, i) => setTimeout(() => toast('⚠ ' + w, 'err'), 1200 + i * 1200));
  return r;
}

/** 加载完把「这文件是什么来头」讲清楚：编码、include 链、profile */
function renderLoadInfo(r) {
  const box = document.getElementById('chainHint');
  if (box) {
    if (!r) { box.innerHTML = ''; }
    else {
      const files = (r.chain && r.chain.files) || [];
      const bits = [];
      bits.push(`编码 <b>${esc(r.encoding || 'UTF-8')}</b> · 换行 ${esc(r.newline || 'LF')}`);
      if (files.length > 1) {
        bits.push('跟随 include 读到 ' + files.length + ' 个文件：'
          + files.map(f => `${esc(f.name)}<span class="muted">(${f.count})</span>`).join(' · '));
      } else if (files.length === 1) {
        bits.push('没有 include 其它文件');
      }
      if (r.chain && r.chain.files) {
        const missing = (r.chain.files[0] && r.chain.files[0].missing) || [];
        if (missing.length) {
          bits.push(`<span class="warn-text">⚠ ${missing.length} 个 include 指向的文件不存在：`
            + missing.map(m => esc(m.target)).join('、') + '</span>');
        }
      }
      box.innerHTML = bits.join('<br>');
    }
  }
  const bar = document.getElementById('profileBar');
  if (bar) {
    if (!r || !APP.profiles.length) { bar.style.display = 'none'; }
    else {
      bar.style.display = '';
      const cnt = document.getElementById('profileCount');
      if (cnt) cnt.textContent = APP.profiles.length;
      const sel = document.getElementById('profileSel');
      if (sel) {
        sel.innerHTML = APP.profiles.map((p, i) =>
          `<option value="${i}">${esc(p.name)}${p.desc ? ' · ' + esc(p.desc) : ''}`
          + `（${Object.keys(p.values || {}).length} 项）</option>`).join('');
      }
    }
  }
}

/** 把某个 profile 的选项搬进界面：明确告诉用户它们会变成全局 */
function loadProfile(index) {
  const p = APP.profiles[+index];
  if (!p) return;
  const vals = p.values || {};
  const n = Object.keys(vals).length;
  if (!n) { toast(`profile「${p.name}」里没有可识别的选项`, 'err'); return; }
  APP.values = Object.assign({}, APP.values, vals);
  APP.disable = []; APP.pending = [];
  changed();
  toast(`已载入 profile「${p.name}」的 ${n} 项 —— `
    + `它原本只在 ${p.cond ? '条件满足时' : '被调用时'} 生效，写进配置后就是全局生效了`, 'err');
}

let _previewTimer = null;
function refreshPreview() {
  clearTimeout(_previewTimer);
  _previewTimer = setTimeout(doPreview, 160);
}

/* ---------------- R-14：逐行对比 ---------------- */

var DIFF = { rows: [], shown: false };

/** 渲染行级差异（左右并排）。tag: equal / add / del / modify */
function renderDiff(rows) {
  DIFF.rows = rows || [];
  const box = document.getElementById('diffBox');
  if (!box) return;
  if (!DIFF.rows.length) { box.innerHTML = ''; return; }
  const cell = (side, cls) => {
    const n = side ? side.n : '';
    const t = side ? side.text : '';
    return `<span class="dl">${n === '' ? '' : n}</span>`
      + `<span class="dt ${cls}">${esc(t) || '&nbsp;'}</span>`;
  };
  box.innerHTML = '<div class="diff">' + DIFF.rows.map(r => {
    const cls = r.tag === 'modify' ? 'mod' : r.tag;
    return `<div class="drow ${cls}">`
      + `<span class="dside">${cell(r.left, 'left')}</span>`
      + `<span class="dside">${cell(r.right, 'right')}</span>`
      + `</div>`;
  }).join('') + '</div>';
}

/** 切换「合并后的完整文件」/「逐行对比」。 */
function toggleDiff() {
  const pre = document.getElementById('preview');
  const box = document.getElementById('diffBox');
  const btn = document.getElementById('diffToggle');
  if (!pre || !box) return;
  DIFF.shown = !DIFF.shown;
  pre.style.display = DIFF.shown ? 'none' : '';
  box.style.display = DIFF.shown ? '' : 'none';
  if (btn) btn.textContent = DIFF.shown ? '📄 看完整文件' : '🔀 逐行对比';
}

/** 根据预览结果决定「逐行对比」按钮该不该出现。 */
function updateDiffToggle(r) {
  const btn = document.getElementById('diffToggle');
  const box = document.getElementById('diffBox');
  if (!btn) return;
  const has = r.mode === 'merge' && (r.diff || []).length;
  btn.style.display = has ? '' : 'none';
  if (!has) {
    box.style.display = 'none';
    if (box) box.innerHTML = '';
    DIFF.shown = false;
    const pre = document.getElementById('preview');
    if (pre) pre.style.display = '';
    btn.textContent = '🔀 逐行对比';
    return;
  }
  renderDiff(r.diff);
  const st = r.diff_stats || {};
  btn.textContent = DIFF.shown
    ? '📄 看完整文件'
    : `🔀 逐行对比（${st.changes || 0} 处）`;
}

async function doPreview() {
  const box = document.getElementById('preview');
  if (!box) return;
  if (!APP.target) { box.textContent = '（先选目标目录）'; return; }
  const r = await API.post('/api/config/preview', payload());
  if (!r.ok) { box.textContent = r.detail || '预览失败'; return; }
  const empty = countValues() === 0 && !String(APP.custom || '').trim();
  const shown = (r.mode === 'merge' && r.merged_text) ? r.merged_text : r.text;
  box.innerHTML = paintConf(shown) + (empty
    ? '\n<span class="c"># 还没有勾选任何选项 —— 左边随便点一个，这里就实时变</span>' : '');
  const title = document.getElementById('previewTitle');
  if (title) {
    // 标题跟着「创建 / 修改」语义走，而不是只看写入方式
    title.textContent = r.mode === 'merge'
      ? `合并后的完整文件（${r.changes.length} 处改动）` : previewTitle();
  }
  const c = document.getElementById('changeCount');
  if (c) c.textContent = r.mode === 'merge' ? String(r.changes.length) : String(countValues());
  const f = document.getElementById('previewFile');
  if (f) {
    const full = r.mode === 'merge' ? r.source : r.file;
    f.textContent = shortPath(full, 12, 20);
    f.title = full || '';
  }
  const ph = document.getElementById('pendingHint');
  if (ph) ph.innerHTML = APP.pending.length
    ? `<span class="warn-text">⚠ ${APP.pending.length} 项勾选了但没填值，不会被写入</span>` : '';
  const eh = document.getElementById('encodingHint');
  if (eh) {
    eh.textContent = r.mode === 'merge' && r.encoding
      ? `按原编码写回：${r.encoding}` : '';
  }
  renderIssues(r.issues || [], r.conflicts || []);
  updateDiffToggle(r);
  if (empty) {
    const sbox = document.getElementById('scoreBox');
    if (sbox) sbox.innerHTML = '<p class="note">配置里还没有内容，先勾几个选项再看评分。</p>';
  } else {
    analyze(shown);
  }
}

function payload(extra) {
  return Object.assign({
    target: APP.target,
    write_mode: APP.writeMode,
    source: APP.source,
    state: {
      values: APP.values,
      other: APP.otherValues,   // 现有配置里界面没有对应勾选项的键，只参与冲突检测
      shaders: APP.shaders,
      memc: APP.memc,
      memc_label: APP.memcLabel,
      custom: APP.custom,
      disable: APP.disable
    }
  }, extra || {});
}

function countValues() {
  return Object.keys(APP.values).length + (APP.memc ? 1 : 0)
    + (APP.shaders.length ? APP.shaders.length : 0);
}

async function applyConfig() {
  if (!APP.target) { toast('请先选目标配置目录', 'err'); return; }
  // R-26：edit 语义下必须先读取现有配置 —— 否则你以为在读文件、其实在凭空生成，
  // 而且 merge 会把生成结果写进那个"没读过"的文件。
  if (blockedByNoSource()) {
    toast('「改现有配置」模式下要先点「📂 读取现有配置」', 'err');
    return;
  }
  if (APP.writeMode === 'merge' && !APP.source) {
    toast('合并模式需要先「读取现有配置」', 'err'); return;
  }
  const r = await API.post('/api/config/apply', payload());
  toast((r.ok ? '✅ ' : '❌ ') + r.detail, r.ok ? 'ok' : 'err');
  if (r.ok) doPreview();
}

async function analyze(text) {
  const r = await API.post('/api/analyze', { text });
  const box = document.getElementById('scoreBox');
  if (!r.ok || !box) return;
  const s = r.scores || {};
  box.innerHTML = `
    <div class="kv">
      <span class="muted">综合</span><b>${r.overall} / 100 · ${r.grade}</b>
      <span class="muted">清晰度</span><b>${s.quality}</b>
      <span class="muted">锐度</span><b>${s.sharp}</b>
      <span class="muted">流畅度</span><b>${s.smooth}</b>
      <span class="muted">色彩</span><b>${s.color}</b>
      <span class="muted">GPU 负载</span><b>${s.load}</b>
    </div>
    <p class="note" style="margin-top:8px">⚠ 评分为启发式估算，请以 mpv 的 stats（按 <code>i</code> 再按 <code>2</code>）实测为准</p>`;
}

function renderIssues(issues, conflicts) {
  const box = document.getElementById('issueBox');
  APP.conflicts = conflicts || [];
  APP.conflictKeys = {};
  APP.conflicts.forEach(c => (c.keys || []).forEach(k => { APP.conflictKeys[k] = c.level; }));
  markConflictRows();
  if (!box) return;
  if (!issues.length) {
    box.innerHTML = '<p class="note">✅ 没有发现明显问题</p>';
    return;
  }
  const icon = { error: '❌', warn: '⚠', info: 'ℹ️' };
  const cls = { error: 'danger', warn: 'warn', info: '' };
  box.innerHTML = issues.map(([lv, msg]) =>
    `<p class="note ${cls[lv] || ''}">${icon[lv] || '·'} ${esc(msg)}</p>`).join('');
}

/** 把涉事选项在行上标出来（重新渲染不会丢，因为渲染时也读 APP.conflictKeys） */
function markConflictRows() {
  document.querySelectorAll('.opt').forEach(row => {
    const lv = APP.conflictKeys[row.dataset.key];
    const head = row.querySelector('.opt-head');
    if (!head) return;
    const old = head.querySelector('.conflict-flag');
    if (!lv) { if (old) old.remove(); return; }
    const label = { error: '❌ 冲突', warn: '⚠ 冲突', info: 'ℹ️ 提示' }[lv] || '⚠ 冲突';
    if (old) { old.textContent = label; old.className = `badge choice conflict-flag lv-${lv}`; }
    else {
      const b = document.createElement('span');
      b.className = `badge choice conflict-flag lv-${lv}`;
      b.textContent = label;
      b.title = '点右边的 i 看说明；下方「评估与体检」里有完整原因和改法';
      head.insertBefore(b, head.querySelector('.right'));
    }
  });
}

/* ---------------- 选项行渲染 ---------------- */

const TYPE_BADGE = {
  bool: ['flag', '开关'], enum: ['choice', '枚举'], int: ['int', '整数'],
  float: ['int', '小数'], str: ['', '文本'], color: ['color', '颜色'], list: ['', '列表']
};

function optRow(item, index) {
  const key = item.key;
  const on = isOn(key);
  const need = APP.pending.includes(key);
  const val = hasOption(key) ? APP.values[key] : '';
  const typ = item.type || (item.values && item.values.length && isBoolValues(item.values) ? 'bool' : 'enum');
  const badge = TYPE_BADGE[typ] || ['', '文本'];
  // suggest = 精选层写的建议值（只是举例）；options = 真正允许的取值（库里查得到的话）
  const suggest = item.suggest || item.values || [];
  const options = item.options || item.values || [];
  const open = item.open === undefined
    ? ['int', 'float', 'str', 'color', 'list'].includes(typ) || !suggest.length
    : !!item.open;

  // 值控件：
  //   封闭枚举（只有固定取值）→ 原生下拉框
  //   其它（自由类型 / 能自己填的）→ **组合框**：下拉给候选、也能自己敲
  // 以前是"建议值非空就渲染成下拉"，于是 `geometry`、`sub-font`、`volume`
  // 这些本该自由填的项被锁死在几个示例值里。
  let control;
  if (!open && options.length) {
    const opts = options.map(v =>
      `<option value="${esc(v)}"${String(v) === String(val) ? ' selected' : ''}>${esc(v)}</option>`).join('');
    control = `<select data-role="value"><option value="">（选一个值）</option>${opts}</select>`;
  } else {
    // 候选列表自己画（见 openCombo 的注释：原生 datalist 的气泡没法跟着主题走）
    control = `<span class="combo"><input type="text" data-role="value" value="${esc(val)}"
      data-options="${esc(JSON.stringify(options))}"
      placeholder="${esc(suggest[0] || item.range || '')}" style="min-width:130px" autocomplete="off"
      spellcheck="false">${options.length
        ? '<button type="button" class="combo-arrow" data-role="combo-toggle" tabindex="-1" '
          + 'title="展开候选值">▼</button>'
        : ''}</span>`;
  }

  const list = suggest.length
    ? `<div class="note" style="margin-top:4px">建议值：${suggest.map(v => `<code>${esc(v)}</code>`).join(' ')}</div>`
    : '';
  // 候选比建议多时说明"不止这几个"，说清楚免得用户以为只有这些
  const more = (options.length > suggest.length)
    ? `<div class="note" style="margin-top:4px">这个选项实际有 <b>${options.length}</b> 个可选值`
      + `（上面只是常用建议）—— 输入框可以下拉看全部，也可以直接敲。</div>`
    : '';
  const freeHint = (open && options.length)
    ? `<div class="note" style="margin-top:4px">也可以自己填：不限于上面这些值。</div>`
    : '';
  const lv = (APP.conflictKeys || {})[key];
  const flag = lv
    ? `<span class="badge choice conflict-flag lv-${lv}" title="与其它选项冲突，看下方体检">`
      + `${lv === 'error' ? '❌ 冲突' : lv === 'warn' ? '⚠ 冲突' : 'ℹ️ 提示'}</span>`
    : '';
  const extra = [];
  if (item.default !== undefined && item.default !== '' && item.kind === 'db') {
    extra.push(`<span class="badge" title="mpv 的默认值">默认 ${esc(item.default)}</span>`);
  }
  if (item.deprecated) extra.push('<span class="badge color">已弃用</span>');
  const hint = need
    ? `<span class="warn-text">⚠ 已勾选，但还没填值 —— 填了才会写进配置</span>`
    : esc(item.desc || '');
  return `<div class="opt${on ? ' on' : ''}${lv ? ' has-conflict' : ''}" data-key="${esc(key)}"
    data-kind="${esc(item.kind || '')}" data-idx="${index}">
    <div class="opt-head">
      <input type="checkbox" data-role="check"${on ? ' checked' : ''}>
      <label data-role="label">${esc(item.label)}</label>
      ${item.label === key ? '' : `<span class="key">${esc(key)}</span>`}
      <span class="badge ${badge[0]}">${badge[1]}</span>
      ${extra.join('')}
      ${flag}
      <div class="right">${control}
        <button class="icon-btn" data-role="info" title="完整说明">i</button>
      </div>
    </div>
    <div class="hint" data-role="hint">${hint}</div>
    <div class="expand" data-role="expand">${list}${more}${freeHint}${item.range
      ? `<div class="note" style="margin-top:4px">取值范围：<code>${esc(item.range)}</code></div>` : ''}</div>
  </div>`;
}

function isBoolValues(values) {
  return values.length === 2 && values.includes('yes') && values.includes('no');
}

function mountOptions(container, items) {
  container.innerHTML = items.map((it, i) => optRow(it, i)).join('');
  // 候选值从 data-options 收进 JS 属性：data-* 只能存字符串，每次过滤都
  // JSON.parse 一遍太亏，而且下拉要从属性直接拿列表。
  container.querySelectorAll('input[data-options]').forEach(el => {
    try { el._options = JSON.parse(el.dataset.options) || []; }
    catch (e) { el._options = []; }
  });
  container.oninput = onOptEvent;
  container.onchange = onOptEvent;
  container.onclick = onOptEvent;
  markConflictRows();
  // 字幕那几项下面挂一个实时预览（值从 APP.values 读，跟写进配置的是同一份）
  if (items.some(it => it.key in SUB_PREVIEW_KEYS)) {
    const host = document.createElement('div');
    host.id = 'subPreviewHost';
    container.appendChild(host);
    updateSubPreview();
  }
}

/* ---------------- 候选值下拉（自绘组合框） ----------------
 *
 * 起因：`sub-font` 这类"能自己填、也给了候选"的项，原来用 `<input list>` +
 * `<datalist>` 实现。结果输入框下面弹出一个**白底大气泡**，跟深色主题完全对不上。
 *
 * 那个气泡是浏览器自己画的 UI，有两个绕不过去的性质：
 *   · 它**不在页面 DOM 里** —— 连截图工具（DevTools 的 Page.captureScreenshot）
 *     都抓不到它，因为它属于浏览器 UI 层而不是渲染出来的页面。
 *   · 它**不吃页面 CSS** —— 无论怎么写 `background` / `font-size` 都改不动。
 * 唯一的主题旋钮是 `color-scheme`，而它在部分 Chromium 版本上对 datalist 无效。
 *
 * 所以自己画一个：输入框保留（自由填不能丢），候选列表用普通 DOM 渲染。
 * 面板挂在 `document.body` 上用 fixed 定位 —— 挂在行内会被后面这些行盖住
 * （`.opt` 有 `position: relative`，兄弟行会按 z-index 叠在上面）。
 */

var comboPop = null;        // 当前展开的面板（同时只会有一个）
var comboInput = null;      // 面板对应的输入框
var comboActive = -1;       // 键盘高亮的第几项

/** 关掉当前面板。事件监听顺带摘掉，免得越堆越多。 */
function closeCombo() {
  if (comboPop) comboPop.remove();
  comboPop = null;
  comboInput = null;
  comboActive = -1;
  window.removeEventListener('scroll', closeCombo, true);
  window.removeEventListener('resize', closeCombo);
}

/** 把面板贴到输入框下面。装不下就往上翻，宽度不窄于输入框。 */
function placeCombo() {
  if (!comboPop || !comboInput) return;
  const r = comboInput.getBoundingClientRect();
  const w = Math.max(r.width, 170);
  comboPop.style.width = w + 'px';
  const tall = Math.min(comboPop.scrollHeight, 230) + 10;
  const below = window.innerHeight - r.bottom;
  const left = Math.max(4, Math.min(r.left, window.innerWidth - w - 8));
  comboPop.style.left = left + 'px';
  if (below >= tall + 6 || below >= r.top) {
    comboPop.style.top = (r.bottom + 3) + 'px';
    comboPop.style.maxHeight = Math.max(90, Math.min(230, below - 10)) + 'px';
  } else {
    comboPop.style.maxHeight = Math.max(90, Math.min(230, r.top - 10)) + 'px';
    comboPop.style.top = Math.max(4, r.top - 3 - parseInt(comboPop.style.maxHeight, 10)) + 'px';
  }
}

function comboHighlight(i) {
  if (!comboPop) return;
  const items = comboPop.querySelectorAll('.combo-item');
  if (!items.length) { comboActive = -1; return; }
  comboActive = Math.max(0, Math.min(i, items.length - 1));
  items.forEach((el, n) => el.classList.toggle('active', n === comboActive));
  items[comboActive].scrollIntoView({ block: 'nearest' });
}

/**
 * 选中一个候选值。`v` 是**被点中的那一项的值**，不是输入框当前的内容。
 *
 * ⚠ 这里踩过一个坑：原来直接读 `input.value`。但输入框里往往正是过滤用的关键词
 * （比如敲了 `Wen` 再点 `LXGW WenKai Lite`），于是存进去的是 `Wen` ——
 * 一个根本不是候选值的字符串，而且看起来"选成功了"。
 * 所以值只能从**被点中的那一项**来。
 *
 * 值统一走 `input` 事件，不直接改状态 —— 值的唯一入口是 onOptEvent，
 * 绕过去就会出现"预览 / 冲突体检用的值"和"真正写进配置的值"不一致。
 */
function comboPick(v) {
  v = String(v);
  // ⚠ 先把 input 抓在手里，**不要**在这里 closeCombo —— 关闭放到最后统一做。
  //   `closeCombo()` 会把 comboInput 置空，顺序写反的后果是"点了候选完全没反应"，
  //   而且不报错，极难查（这个坑真踩过）。
  const input = comboInput;
  if (!input) { closeCombo(); return; }

  const row = input.closest('.opt');
  const box = row && row.querySelector('[data-role="check"]');
  const wasOn = !!(box && box.checked);

  input.value = v;
  // ⚠ 关闭要放在**派发事件之前**，两个原因：
  //   ① 下面派发的 input 会命中 openCombo（见 initCombo），等于"刚关就又开"，
  //      所以用 _noReopen 挡掉那一次；
  //   ② onOptEvent 里会走 changed() → 重新渲染选项行，整个页面根节点被换掉 ——
  //      面板挂在 body 上活了下来，但已经和页面脱节。放在派发之后关，
  //      就会出现"选完面板还赖着不走"。
  input._noReopen = true;
  closeCombo();
  try {
    if (box && !wasOn) {
      // 未勾选的行值控件本来是藏着的，用 change 让它按"勾选并填值"整体走一遍：
      // 只派发 input 的话，onOptEvent 会因为复选框没勾而直接 return，
      // 用户点了候选却什么都没发生（这正是最早那个"选了没反应"的死胡同）。
      showComboRow(row);
      box.checked = true;
      box.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  } finally {
    delete input._noReopen;
  }
  // 注意：这里**不要**再 input.focus()。点是点在输入框上的，焦点本来就在；
  // 而 focus() 会触发 focusin → openCombo，把刚收起的面板又弹回来。
  closeCombo();
}

/** 让这一行的值控件立刻可见（不等 onOptEvent 走完重新渲染）。 */
function showComboRow(row) {
  if (!row) return false;
  row.classList.add('on');
  const combo = row.querySelector('.combo');
  if (combo) combo.classList.add('show');
  return !!combo;
}

function comboRender() {
  if (!comboPop || !comboInput) return;
  const all = comboInput._options || [];
  const q = String(comboInput.value || '').trim().toLowerCase();
  const cur = String(comboInput.value || '').trim();
  // 输入框里已经是某个候选的原值时，不要拿它去过滤（否则下拉只剩一条自己）
  const hit = all.filter(v => String(v).toLowerCase() === q).length > 0;
  const list = (!q || hit)
    ? all
    : all.filter(v => String(v).toLowerCase().includes(q));
  const show = list.slice(0, 400);

  comboPop.textContent = '';
  if (!show.length) {
    const d = document.createElement('div');
    d.className = 'combo-empty';
    d.textContent = q ? '没有匹配的候选值 —— 直接敲你自己的值就行' : '没有候选值';
    comboPop.appendChild(d);
  } else {
    show.forEach(v => {
      const s = String(v);
      const d = document.createElement('div');
      d.className = 'combo-item' + (s === cur ? ' sel' : '');
      d.textContent = s;
      d.title = s;
      d.addEventListener('mouseenter', () => {
        comboActive = -1;                     // 鼠标接管高亮
        comboPop.querySelectorAll('.combo-item')
          .forEach(e => e.classList.remove('active'));
        d.classList.add('active');
      });
      d.addEventListener('mousedown', ev => ev.preventDefault());  // 别让输入框先失焦
      d.addEventListener('click', () => comboPick(s));
      comboPop.appendChild(d);
    });
    if (list.length > show.length) {
      const d = document.createElement('div');
      d.className = 'combo-empty';
      d.textContent = `候选值太多，只显示前 ${show.length} 个（继续输入可以缩小范围）`;
      comboPop.appendChild(d);
    }
  }
  comboActive = -1;
  placeCombo();
}

function openCombo(input) {
  if (comboInput === input && comboPop) return;
  closeCombo();
  comboInput = input;
  comboPop = document.createElement('div');
  comboPop.className = 'combo-pop';
  comboPop.addEventListener('mousedown', ev => ev.stopPropagation());
  document.body.appendChild(comboPop);
  comboRender();
  // 页面 / 面板一滚动，fixed 坐标就过期了 —— 直接关掉，比跟丢好
  window.addEventListener('scroll', closeCombo, true);
  window.addEventListener('resize', closeCombo);
}

/** 组合框的键盘操作。返回 true = 这次按键已被吃掉。 */
function comboKeydown(ev) {
  if (!comboPop) {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      const opts = ev.target._options || [];
      if (opts.length) { openCombo(ev.target); return true; }
    }
    return false;
  }
  if (ev.key === 'ArrowDown') { comboHighlight(comboActive + 1); return true; }
  if (ev.key === 'ArrowUp') { comboHighlight(comboActive - 1); return true; }
  if (ev.key === 'Home') { comboHighlight(0); return true; }
  if (ev.key === 'End') {
    comboHighlight(comboPop.querySelectorAll('.combo-item').length - 1);
    return true;
  }
  if (ev.key === 'Enter' || ev.key === 'Tab') {
    const el = comboPop.querySelector('.combo-item.active');
    if (!el) return false;                  // 没选中的就按原样放行（Enter 提交 / Tab 跳走）
    comboPick(el.textContent);
    return ev.key === 'Enter';
  }
  if (ev.key === 'Escape') { closeCombo(); return true; }
  return false;
}

/* 事件委托挂在 `document` 上。
   为什么不挂 `#panes`：那是选项区的宿主，每次切分区都会被 `innerHTML = ...`
   整块换掉（advanced.html 的 render()），挂在上面的监听会跟着一起没。
   挂 document 就一次性管到底。
   用捕获阶段：Escape 要先给下拉用，不能让它一路冒到抽屉那边先关抽屉。 */
function initCombo() {
  if (document._comboWired) return;
  document._comboWired = true;   // 设了标记，重复调用无副作用

  document.addEventListener('click', ev => {
    const inPop = comboPop && comboPop.contains(ev.target);
    if (inPop) return;              // 面板内的点击由那一项自己的 handler 处理
    const toggle = ev.target.closest && ev.target.closest('[data-role="combo-toggle"]');
    if (toggle) {
      ev.preventDefault();
      const box = toggle.closest('.combo');
      const input = box && box.querySelector('[data-role="value"]');
      if (!input) return;
      if (comboInput === input && comboPop) closeCombo(); else openCombo(input);
      return;
    }
    if (!ev.target.closest || !ev.target.closest('.combo')) closeCombo();  // 点别处收起
  }, true);

  document.addEventListener('input', ev => {
    if (ev.target.dataset && ev.target.dataset.options) {
      // comboPick 正在派发这个事件：刚选完不该把面板又弹回来
      if (ev.target._noReopen) return;
      openCombo(ev.target);
      comboRender();
    }
  }, true);

  document.addEventListener('focusin', ev => {
    if (ev.target.dataset && ev.target.dataset.options) openCombo(ev.target);
  }, true);

  document.addEventListener('focusout', ev => {
    if (!comboPop) return;
    const to = ev.relatedTarget;
    if (to && (comboPop.contains(to) || to === comboInput)) return;
    // 点面板里的项时 mousedown 已经 preventDefault，这里不会误关
    closeCombo();
  }, true);

  document.addEventListener('keydown', ev => {
    if (comboKeydown(ev)) { ev.preventDefault(); ev.stopPropagation(); }
  }, true);

  document.addEventListener('mousedown', ev => {
    if (!comboPop) return;
    if (comboPop.contains(ev.target) || ev.target === comboInput) return;
    if (ev.target.closest && ev.target.closest('.combo')) return;
    closeCombo();
  }, true);
}

/*
 * ⚠ 一个踩了两次的顺序坑，记在这儿：
 *
 *   面板的点击处理走的是**冒泡**（每项自己的 click），而上面那些委托是**捕获**。
 *   捕获一定先跑，于是：
 *     · document 的 click 捕获先把面板关掉 → comboInput 被置空
 *     · 然后项自己的 click 才跑 → 拿不到 input → 什么都不发生
 *   现象就是"点了候选完全没反应"，而且控制台一片安静，特别难查。
 *
 *   所以：捕获里的"点别处就收起"必须**排除面板内部**（上面的 inPop 判断），
 *   而 comboPick 也要先把 input 抓在手里再 closeCombo。
 *   两条都留着 —— 少任何一条这个 bug 都会回来。
 */

/**
 * 绑定的时机。
 *
 * ⚠ 这里踩过一个坑：state.js 是在 `<head>` 里同步加载的，脚本执行时
 * `document.body` **还是 null**。而面板要 `document.body.appendChild(...)`，
 * 于是"聚焦 / 输入 → 开下拉"全线静默失败：面板建出来了，但没地方挂，
 * 页面看起来就是"点了没反应"。而且不报错，特别难猜。
 * 所以必须等文档解析完再绑。
 */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCombo);
} else {
  initCombo();
}

/* ---------------- 字幕实时预览 ----------------
 *
 * 为什么要它：调字幕样式本来要「改配置 → 开 mpv → 找个有字幕的片子 → 看 →
 * 不满意 → 回去改」。有个实时预览，这个循环就没了。
 *
 * ⚠ 铁律：**预览和配置必须从同一份数据渲染**（都读 APP.values）。
 * 反面教材：mpvconfigurator 的预览读的是 Qt 滑块旁边那个 QLabel 的文本
 * （只在 `sliderMoved` 时更新），配置却从滑块对象取 —— 拖过一下才一致，
 * 载入配置后没动过的值两边就不一样。用户看到的是"预览是对的、存下去是错的"，
 * 而且完全不知道要拖一下才能对上。
 *
 * ℹ️ 顺带纠正一条我先前记错的：mpv 的 8 位颜色是 `#AARRGGBB`（透明度在**最前**），
 * 跟 `QColor::HexArgb` 一致 —— 它那块**没写错**，错的是我。
 * 证据见 `tests/test_subpreview.py` 的 `ColorOrderEvidenceTest`。
 */

/** 参与预览的选项 */
var SUB_PREVIEW_KEYS = {
  'sub-font': 1, 'sub-font-size': 1, 'sub-color': 1, 'sub-border-color': 1,
  'sub-border-size': 1, 'sub-shadow-offset': 1, 'sub-shadow-color': 1,
  'sub-back-color': 1, 'sub-pos': 1, 'sub-margin-x': 1,
};

var SUB_PREVIEW_TEXT = '这是字幕预览效果 Subtitle Preview 0123';

/** 解析 mpv 的颜色值。返回 {css, warn}。
 *
 * mpv 的颜色写法：
 *   #RRGGBB        6 位，不透明
 *   #AARRGGBB      8 位，**透明度在最前两位**（不是最后！）
 *   r/g/b 或 r/g/b/a   0.0~1.0 的分量写法
 *
 * 8 位那套的字节顺序是拿 `mpv --list-options` 的默认值定的，11 个 8 位默认值
 * 全部吻合「AA 在前」：
 *     sub-color        #FFFFFFFF  = 不透明的白      （若 AA 在后 → 全透明的白，矛盾）
 *     sub-back-color   #AF000000  = 69% 不透明的黑  （若 AA 在后 → 全透明的暗红，矛盾）
 *     osd-selected-color #FFFABD2F = 不透明的橙黄    （若 AA 在后 → 桃红+18%，矛盾）
 * 而 6 位那套就是普通的 #RRGGBB（CSS 顺序）。
 *
 * ⚠ 两套顺序不一样，极容易写反。所以这里在 8 位值"看着像写反了"时给提示。
 */
function parseMpvColor(v) {
  const s = String(v == null ? '' : v).trim().replace(/^["']|["']$/g, '');
  if (!s) return { css: '', warn: '' };

  let m = /^#([0-9a-fA-F]{6})$/.exec(s);
  if (m) return { css: '#' + m[1], warn: '' };

  // 8 位：#AARRGGBB —— 透明度在前两位。
  // 结尾 (?![\da-fA-F]) 防回溯，保证"恰好 8 位"才算。
  m = /^#([0-9a-fA-F]{8})(?![\da-fA-F])/.exec(s);
  if (m) {
    const hex = m[1];
    const aa = hex.slice(0, 2), rgb = hex.slice(2);
    const r = parseInt(rgb.slice(0, 2), 16);
    const g = parseInt(rgb.slice(2, 4), 16);
    const b = parseInt(rgb.slice(4, 6), 16);
    const alpha = parseInt(aa, 16) / 255;
    const css = `rgba(${r},${g},${b},${Math.round(alpha * 1000) / 1000})`;

    // 写反了的典型长相：末两位是 FF/00 而前两位不是（说明用户把透明度放最后了）。
    // 只在"前两位不是常见 alpha"时提示，避免正常值刷屏。
    const last2 = hex.slice(6).toLowerCase();
    const first2 = hex.slice(0, 2).toLowerCase();
    let warn = '';
    if ((last2 === 'ff' || last2 === '00') && first2 !== 'ff' && first2 !== '00') {
      const swapped = last2 + hex.slice(0, 6);
      warn = `mpv 的 8 位颜色是 #AARRGGBB（透明度在**最前**两位），不是 #RRGGBBAA。`
        + `你写的 ${s} 会被当成「透明度 ${Math.round(parseInt(aa, 16) / 255 * 100)}%」。`
        + `若想表达「不透明」请写 #FF${hex.slice(0, 6)}，或直接用 6 位的 #${hex.slice(0, 6)}。`;
    }
    return { css, warn };
  }

  // r/g/b 或 r/g/b/a
  const parts = s.split('/').map(x => Number(x));
  if (parts.length >= 3 && parts.every(x => !isNaN(x))) {
    const [r, g, b, a] = parts;
    const to255 = x => Math.max(0, Math.min(255, Math.round(Number(x) * 255)));
    const al = (parts.length >= 4 && !isNaN(a)) ? Math.max(0, Math.min(1, Number(a))) : 1;
    return { css: `rgba(${to255(r)},${to255(g)},${to255(b)},${al})`, warn: '' };
  }
  return { css: '', warn: `看不懂这个颜色值：${s}` };
}

function subVal(key, fallback) {
  const v = APP.values[key];
  return (v === undefined || v === null || String(v).trim() === '') ? fallback : String(v).trim();
}

/** 把当前字幕设置画成一小块预览。 */
function updateSubPreview() {
  const host = document.getElementById('subPreviewHost');
  if (!host) return;

  const font = subVal('sub-font', 'sans-serif');
  const size = subVal('sub-font-size', '55');
  const color = parseMpvColor(subVal('sub-color', '#FFFFFFFF'));
  const back = parseMpvColor(subVal('sub-back-color', '#00000000'));
  const borderC = parseMpvColor(subVal('sub-border-color', '#FF000000'));
  const shadowC = parseMpvColor(subVal('sub-shadow-color', '#FF000000'));
  const borderW = Number(subVal('sub-border-size', '3')) || 0;
  const shadowO = Number(subVal('sub-shadow-offset', '0')) || 0;
  const pos = Number(subVal('sub-pos', '100'));
  const marginX = Number(subVal('sub-margin-x', '0')) || 0;

  const warns = [color.warn, back.warn, borderC.warn, shadowC.warn].filter(Boolean);

  // 注意：字号用 px 除以 2 是为了在小预览块里看得下（mpv 的 55 是给整屏用的）
  const px = Math.max(10, Math.min(48, Math.round((Number(size) || 55) / 2)));
  const bottom = isNaN(pos) ? 8 : Math.max(2, Math.min(60, Math.round((100 - pos) * 0.6 + 8)));

  host.innerHTML = `
    <div class="subpv-wrap">
      <div class="subpv-stage">
        <div class="subpv-meta">预览（按当前设置实时渲染）</div>
        <div class="subpv-sub" style="
          font-family:${esc(font)};
          font-size:${px}px;
          color:${color.css || '#fff'};
          ${back.css && back.css !== 'rgba(0,0,0,0)' ? `background:${back.css};` : ''}
          ${borderW > 0 && borderC.css ? `-webkit-text-stroke:${Math.max(0.5, borderW / 2)}px ${borderC.css};` : ''}
          ${shadowO !== 0 && shadowC.css ? `text-shadow:${Math.round(shadowO * 2)}px ${Math.round(shadowO * 2)}px 2px ${shadowC.css};` : ''}
          bottom:${bottom}px;
          ${marginX ? `left:${Math.max(4, Math.min(40, Math.round(marginX / 4)))}px;right:${Math.max(4, Math.min(40, Math.round(marginX / 4)))}px;` : 'left:12px;right:12px;'}
        ">${esc(SUB_PREVIEW_TEXT)}</div>
      </div>
      <p class="note" style="margin-top:6px">
        样式来自 <code>sub-font</code> / <code>sub-font-size</code> / <code>sub-color</code>
        / <code>sub-border-*</code> / <code>sub-shadow-offset</code> / <code>sub-back-color</code>
        / <code>sub-pos</code>。
        实际观感还与片源分辨率、窗口大小、以及 ASS 字幕自带的样式有关 ——
        ASS 字幕默认<b>不</b>吃这些设置（见 <code>sub-ass-override</code>）。
      </p>
      ${warns.length ? `<div class="note warn-text" style="margin-top:6px">⚠ ${
        warns.map(esc).join('<br>⚠ ')}</div>` : ''}
    </div>`;
}


function onOptEvent(ev) {
  const row = ev.target.closest('.opt');
  if (!row) return;
  const key = row.dataset.key;
  const item = findItem(key, row.dataset.kind);
  const role = ev.target.dataset.role;
  // i 按钮的开 / 关由 initDrawerGestures 统一处理，这里不再插手
  if (ev.type === 'click' && role === 'info') { ev.preventDefault(); return; }
  if (ev.type === 'click' && (role === 'hint' || role === 'label')) {
    ev.preventDefault();
    const ex = row.querySelector('[data-role="expand"]');
    if (ex) ex.classList.toggle('open');
    return;
  }
  if (role !== 'check' && role !== 'value') return;
  if (role === 'check') {
    if (ev.target.checked) {
      const input = row.querySelector('[data-role="value"]');
      const v = String(input.value || '').trim();
      const bad = checkValue(item, v);
      if (bad) {
        markPending(key);
        row.classList.add('on');
        setRowHint(row, item, bad);
      } else if (v) {
        setOption(key, v);
        row.classList.add('on');
        setRowHint(row, item, '');
      } else {        // 不给默认值：乱填一个值比不填更危险，明确告诉用户还差一步
        markPending(key);
        row.classList.add('on');
        setRowHint(row, item, '');
        input.focus();
        if (input.tagName === 'SELECT') toast(`给「${item ? item.label : key}」选一个值才会写进配置`, '');
      }
    } else {
      clearOption(key);
      row.classList.remove('on', 'bad');
      const combo = row.querySelector('.combo');
      if (combo) combo.classList.remove('show');   // 取消勾选：值控件收回去
      setRowHint(row, item, '');
    }
    return;
  }
  if (role === 'value') {
    if (!row.querySelector('[data-role="check"]').checked) return;
    const v = String(ev.target.value || '').trim();
    const bad = checkValue(item, v);
    if (bad) {
      // 不合法的值不写进配置，只留红框和提示
      if (hasOption(key)) { delete APP.values[key]; APP.disable = APP.disable.filter(k => k !== key); }
      markPending(key);
      setRowHint(row, item, bad);
      if (ev.type === 'change') toast(`❌ ${key}：${bad}`, 'err');
      return;
    }
    setRowHint(row, item, '');
    if (v) {
      setOption(key, v);
      setRowHint(row, item, '');      // setOption 会把 pending 清掉，提示要跟着更新
    } else {
      markPending(key);
      setRowHint(row, item, '');
    }
  }
}

function findItem(key, kind) {
  const curated = (APP.options.core || []).concat(APP.options.native || []);
  const dbItem = (APP.dbIndex || {})[key];
  // 同一项可能两边都有（精选层 + 全量库），按这一行实际用的那份取，
  // 否则会出现「下拉里能选、校验却说不合法」的怪事
  if (kind === 'db') return dbItem || curated.find(x => x.key === key);
  return curated.find(x => x.key === key) || dbItem;
}

/** 把一批全量选项库条目记下来，抽屉才能显示它们的中文说明 */
function indexDbItems(items) {
  APP.dbIndex = APP.dbIndex || {};
  (items || []).forEach(x => { APP.dbIndex[x.key] = x; });
}

/* ---------------- 就地校验（不往返后端，输入时立刻给红框） ---------------- */

const RE_INT = /^-?\d+$/;
const RE_FLOAT = /^-?\d+(\.\d+)?$/;
const RE_COLOR = /^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$/;

function checkValue(item, v) {
  if (!item) return '';
  v = String(v == null ? '' : v).trim();
  if (!v) return '';
  const t = item.type;
  if (t === 'int' && !RE_INT.test(v)) return '这里要填整数';
  if (t === 'float' && !RE_FLOAT.test(v)) return '这里要填数字';
  if (t === 'color' && !RE_COLOR.test(v)) return '颜色要写成 #RRGGBB 或 #AARRGGBB';

  // 只有**封闭枚举**才拦值。判据是后端的 open 标记（最终来自 mpv 的类型表），
  // 不是"参数表里写没写建议值" —— 以前拿建议值当白名单，导致
  // `scale` 只能填手写的那 10 个（mpv 实际有 39 个）、
  // `geometry` 这种自由格式也被拒。
  const open = item.open === undefined
    ? ['int', 'float', 'str', 'color', 'list'].includes(t) || !(item.values || []).length
    : !!item.open;
  if (open) return '';
  if (t !== 'enum' && t !== 'bool') return '';

  // 能填的集合 = 库里真实取值 + 精选层建议（两者取并，避免"建议里有、表里没有"被误拒）
  const allowed = (item.options && item.options.length)
    ? item.options : (item.values || []);
  if (!allowed.length) return '';
  if (allowed.map(String).includes(v)) return '';
  const shown = allowed.slice(0, 14).join(' / ') + (allowed.length > 14 ? ' …' : '');
  return `这个选项只能填固定取值：${shown}`;
}

/** 一行只能显示一条提示：值不合法 > 还没填值 > 原本的说明 */
function setRowHint(row, item, badMsg) {
  const hint = row.querySelector('[data-role="hint"]');
  if (!hint) return;
  const key = row.dataset.key;
  row.classList.toggle('bad', !!badMsg);
  if (badMsg) {
    hint.innerHTML = `<span class="bad-text">❌ ${esc(badMsg)} —— 这样写 mpv 会报错，先改对再写</span>`;
  } else if (APP.pending.includes(key)) {
    hint.innerHTML = '<span class="warn-text">⚠ 已勾选，但还没填值 —— 填了才会写进配置</span>';
  } else {
    hint.innerHTML = esc((item && item.desc) || '');
  }
}

/* ---------------- 抽屉 ---------------- */

function openDrawer(item) {
  const d = document.getElementById('drawer');
  if (!d) return;
  d.dataset.key = item.key || '';
  d.querySelector('h3').innerHTML = `${esc(item.label || item.key)} <span class="key">${esc(item.key)}</span>`;
  const sig = d.querySelector('.sig');
  if (sig) sig.textContent = `--${item.key}${item.type ? '=<' + item.type + '>' : ''}`;
  const body = d.querySelector('.body');
  if (body) {
    body.innerHTML = `<p class="muted">${esc(item.desc || '（暂无说明）')}</p>`
      + ((item.values && item.values.length)
        ? `<div class="sec"><h4>建议取值</h4><p class="muted">${item.values.map(v => `<code>${esc(v)}</code>`).join('　')}</p></div>`
        : '');
  }
  const fill = d.querySelector('[data-role="fill"]');
  if (fill) {
    const rec = (item.values && item.values[0]) || '';
    fill.style.display = rec ? '' : 'none';
    fill.onclick = () => { setOption(item.key, rec); rerender(); toast(`已填入 ${item.key} = ${rec}`, 'ok'); };
  }
  d.classList.add('open');
  markInfoButtons(d.dataset.key);
}

function closeDrawer() {
  const d = document.getElementById('drawer');
  if (!d || !d.classList.contains('open')) return;
  d.classList.remove('open');
  d.dataset.key = '';
  markInfoButtons('');
}

/** 当前打开的那一项，它的 i 按钮变成 ×，其它恢复成 i */
function markInfoButtons(key) {
  document.querySelectorAll('[data-role="info"]').forEach(b => {
    const row = b.closest('.opt');
    const on = !!key && !!row && row.dataset.key === key;
    b.classList.toggle('active', on);
    b.textContent = on ? '×' : 'i';
    b.title = on ? '收起说明（双击 / 右键任意处也能关）' : '完整说明';
  });
}

/** 关闭手势：点别的 i、再点同一个 i、Esc、右键任意处、点抽屉以外的地方 —— 都会收起 */
function initDrawerGestures() {
  const d = document.getElementById('drawer');
  if (!d || d._wired) return;
  d._wired = true;

  document.addEventListener('click', ev => {
    const infoBtn = ev.target.closest('[data-role="info"]');
    if (infoBtn) {
      ev.preventDefault();
      // 抽屉开着时，点任何一个 i（包括它自己的）都只负责收起；
      // 想换一项看，就再点一次那个 i。
      if (d.classList.contains('open')) { closeDrawer(); return; }
      const row = infoBtn.closest('.opt');
      const key = row ? row.dataset.key : '';
      openDrawer(findItem(key, row && row.dataset.kind) || { key, label: key, desc: '' });
      return;
    }
    if (!d.classList.contains('open')) return;
    if (ev.target.closest('#drawer')) return;      // 抽屉里的操作不算
    closeDrawer();                                  // 勾选框、下拉、标签、空白…一律收起
  }, true);

  document.addEventListener('dblclick', ev => {
    if (ev.target.closest('[data-role="info"]')) closeDrawer();
  });

  document.addEventListener('contextmenu', ev => {
    if (!d.classList.contains('open')) return;      // 没开抽屉就保留系统右键菜单
    if (ev.target.closest('#drawer')) return;       // 抽屉里保留，方便复制文字
    ev.preventDefault();
    closeDrawer();
  });

  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') closeDrawer();
  });
}

document.addEventListener('DOMContentLoaded', initDrawerGestures);

/* ---------------- shader 链 / vpy ---------------- */

function addShader(path) {
  if (!path) return;
  if (APP.shaders.includes(path)) { toast('这个 shader 已经在链里了', 'err'); return; }
  APP.shaders.push(path);
  changed();
}

function moveShader(i, d) {
  const j = i + d;
  if (j < 0 || j >= APP.shaders.length) return;
  const t = APP.shaders[i];
  APP.shaders[i] = APP.shaders[j];
  APP.shaders[j] = t;
  changed();
}

function delShader(i) { APP.shaders.splice(i, 1); changed(); }

function setMemc(path) {
  // 手动选脚本就等于换掉了原来那条 vf，标签不再保留
  APP.memcLabel = '';
  APP.memc = APP.memc === path ? '' : path;
  changed();
}

/** 打开「补帧脚本」页面时的准备工作：读一遍 vs 目录，读完再渲染一次面板 */
async function prepareFusion() {
  if (!APP.vpyList || !APP.vpyList.length) {
    await loadVpyList();
    if (APP.vpyList.length) { rerender(); return; }   // 让面板带着脚本列表重画一次
  }
  initFusionPanel();
}

/* ---------------- VPY 融合（R-3） ---------------- */

const ROLE_BADGE = {
  deint: ['flag', '反交错'], denoise: ['int', '降噪'], superres: ['choice', '超分'],
  memc: ['color', '补帧'], other: ['', '其它'], unfusable: ['color', '不能融合']
};

async function loadVpyList() {
  const r = await API.get('/api/vpy/list' + (APP.target ? '?target=' + encodeURIComponent(APP.target) : ''))
    .catch(() => ({ ok: false, detail: '读取失败' }));
  APP.vpyList = r.ok ? (r.scripts || []) : [];
  APP.vpyError = r.ok ? '' : (r.detail || '');
  return r;
}

/** 融合面板：给「补帧脚本 / Shader 链」页面复用 */
function fusionPanelHtml() {
  const list = APP.vpyList || [];
  if (!list.length) {
    return `<div class="card">
      <h2>🔗 多脚本融合</h2>
      <p class="note">${APP.vpyError
        ? '❌ ' + esc(APP.vpyError)
        : '目标目录里没有 <code>vs/</code> 脚本可选。'}</p></div>`;
  }
  const rows = list.map((s, i) => `<div class="radio-item${s.fusable ? '' : ' disabled'}"
      data-vpy="${i}" style="${s.fusable ? '' : 'opacity:.5;cursor:not-allowed'}">
      <input type="checkbox" data-role="vpy" data-i="${i}" ${s.fusable ? '' : 'disabled'}>
      <div style="min-width:0"><div>${esc(s.name)}
        ${s.generated ? '<span class="badge choice">本工具生成</span>' : ''}</div>
        <small>${esc(s.role_label)} · ${s.size} B</small></div>
      <span class="badge ${(ROLE_BADGE[s.role] || ['', ''])[0]}" style="margin-left:auto"
        title="${esc(s.reason || s.role_label)}">${esc(s.role_label)}</span>
    </div>`).join('');
  return `
  <div class="card">
    <h2>🔗 多脚本融合（把「补帧 + 超分」合成一个 .vpy）</h2>
    <p class="note">mpv 同时只能挂一个 vapoursynth 脚本。勾几个脚本，这里按
      <b>反交错 → 降噪 → 超分 → 补帧</b> 串成一个 <code>_mb_xxx.vpy</code>：
      每个脚本的用户选项与管线原样保留、各自独立，原脚本一个都不动。</p>
    <div class="radio-list" id="fuseList" style="margin-top:10px">${rows}</div>
    <div class="picker">
      <input type="text" id="fuseName" placeholder="文件名（留空就是 fused）" style="min-width:170px">
      <button class="btn" id="fusePreview">🔍 预览</button>
      <button class="btn primary" id="fuseWrite">💾 写进 vs 目录</button>
    </div>
    <p class="note" id="fuseWarn" style="margin-top:8px"></p>
    <pre class="conf" id="fuseOut" style="display:none;margin-top:10px;max-height:40vh"></pre>
    <div class="actions" id="fuseUse" style="display:none">
      <button class="btn primary" id="fuseUseBtn">✅ 就用这个脚本</button>
      <button class="btn" id="fuseCopy">📋 复制代码</button>
    </div>
  </div>`;
}

function selectedVpy() {
  return [...document.querySelectorAll('#fuseList [data-role="vpy"]:checked')]
    .map(x => APP.vpyList[+x.dataset.i]).filter(Boolean);
}

async function fuseSelected(write) {
  const picked = selectedVpy();
  if (picked.length < 2) { toast('至少勾两个脚本才需要融合', 'err'); return null; }
  const nameEl = document.getElementById('fuseName');
  const r = await API.post('/api/vpy/fuse', {
    target: APP.target, scripts: picked.map(x => x.path),
    name: (nameEl && nameEl.value.trim()) || '', write: !!write, overwrite: false
  });
  const out = document.getElementById('fuseOut');
  const warn = document.getElementById('fuseWarn');
  const useBox = document.getElementById('fuseUse');
  if (warn) {
    warn.innerHTML = (r.warnings || []).map(w => `<span class="warn-text">⚠ ${esc(w)}</span>`).join('<br>')
      || (r.check ? `✅ ${esc(r.check.detail || '')}` : '');
  }
  if (!r.ok) { toast('❌ ' + (r.detail || '融合失败'), 'err'); return r; }
  if (out) { out.style.display = ''; out.textContent = r.text; }
  if (useBox) useBox.style.display = '';
  if (write && r.path) {
    APP.fusedPath = r.path;
    toast(`✅ ${r.detail}，可以用「就用这个脚本」挂上`, 'ok');
  } else {
    APP.fusedPath = (APP.target ? APP.target.replace(/[\\/]$/, '') + '\\vs\\' : '') + r.filename;
    toast('已生成预览，确认没问题再写进 vs 目录', '');
  }
  return r;
}

function initFusionPanel() {
  const list = document.getElementById('fuseList');
  if (!list) return;
  list.onclick = e => {
    const row = e.target.closest('[data-vpy]');
    if (!row || !row.querySelector('input').disabled) return;
    toast('这个脚本是音频处理，不能拼进视频链', 'err');
  };
  const pv = document.getElementById('fusePreview');
  if (pv) pv.onclick = () => fuseSelected(false);
  const wr = document.getElementById('fuseWrite');
  if (wr) wr.onclick = () => fuseSelected(true);
  const use = document.getElementById('fuseUseBtn');
  if (use) use.onclick = () => {
    if (!APP.fusedPath) return;
    setMemc(APP.fusedPath.replace(/^.*[\\/]vs[\\/]/i, '~~/vs/'));
    toast('已把融合脚本挂上（记得点「应用修改」写进配置）', 'ok');
    rerender();
  };
  const cp = document.getElementById('fuseCopy');
  if (cp) cp.onclick = async () => {
    try {
      await navigator.clipboard.writeText(document.getElementById('fuseOut').textContent);
      toast('已复制', 'ok');
    } catch (e) { toast('复制失败，请手动选中', 'err'); }
  };
}

/* ---------------- 目标目录 ---------------- */

function setTarget(dir) {
  APP.target = dir || '';
  saveLocal();
  loadCatalog().then(() => { if (APP.onCatalog) APP.onCatalog(); });
  changed();
}

function configOptions() {
  const list = APP.catalog.configs || [];
  if (!list.length) return '<option value="">（目录里还没有配置文件）</option>';
  return list.map(c => `<option value="${esc(c.path)}">${esc(c.name)}`
    + `${c.kind === 'profiles' ? '（profile 集合）' : ''} · ${c.size} B</option>`).join('');
}

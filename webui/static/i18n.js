/* i18n —— 机制层
 * ============================================================================
 * 第 1 步只搭机制（框架 + 语言切换 + index.html 当样板），**不翻完 1098 处** ——
 * 翻完是第 3 步，见 docs/待做.md §〇。
 *
 * ── 三个设计决定，改之前先看 ────────────────────────────────────────────
 *
 * 1. 语言包**内嵌在 JS 里，不用 fetch 去取 JSON**
 *    Electron 用 win.loadFile() 从 file:// 载入页面（electron/main.js），
 *    file:// 下 fetch 相对路径的 JSON 会被 CORS 挡掉。
 *    所以翻译表只能跟着 <script src="i18n.js"> 一起进页面。
 *
 * 2. 不做两套 HTML
 *    9 个页面变 18 份、改一处要改两遍 —— 正是本项目一直在避免的「同一份东西存两份」。
 *    做法是 data-i18n 属性 + 运行时切换（docs/待做.md §四 第 7 条已拍板）。
 *
 * 3. 数字只有一份来源
 *    AGENTS.md §2.6「数字不要手抄」。同一个数字若在两份语言包里各写一遍，
 *    改的时候必然漏一处。所以数字一律走 {占位符}，值只在 VARS 里出现一次。
 *
 * ── 检索留痕（主规范「先搜寻后自研」）───────────────────────────────────
 *    检索过：i18next（零运行时依赖、生态最全，但 ~16KB 且要插件才完整）、
 *            Rosetta（298 字节、极简）、polyglot.js（Airbnb，轻量）、
 *            vanilla-i18n（零依赖、data-i18n 属性方案）。
 *    为什么不用：前三个都要在 file:// 下额外解决加载问题，而本项目只要
 *    「属性标记 + 运行时替换」这点能力 —— 引入依赖换来的只是体积和一份
 *    需要被维护的第三方代码。采纳 vanilla-i18n 的**思路**（data-i18n 属性），
 *    不引入它的代码（本文件自写，约 120 行）。
 */

(function () {
  'use strict';

  var STORE_KEY = 'mpvcb-lang';
  var DEFAULT_LANG = 'zh-CN';
  var SUPPORTED = ['zh-CN', 'en'];

  /* 数字的唯一来源。两种语言都用 {n} 引用它 —— 别在 DICT 里再写一遍数字。
   * TODO(i18n): 829 是数据文件里的原始条数、813 是界面可写进配置的条数，
   *   209 是 mpv 内置默认键位条数。这三个值应当改由后端 API 提供，
   *   现在先放常量（否则同一个数字会在两处腐烂）。见 TASKS.md T13。 */
  var VARS = {
    optsTotal: 829,
    keyCount: 209
  };

  var DICT = {
    'zh-CN': {
      'lang.name': '中文',
      'lang.switch': '切换语言',

      'app.title': 'MPV Config Builder · 选择模式',

      'topbar.downloadLazy': '📥 下载 mpv-lazy',
      'topbar.theme': '🌓 切换主题',
      'topbar.target': '目标：',
      'topbar.detecting': '检测中…',
      'topbar.notFound': '未检测到 mpv-lazy',
      'topbar.backendDown': '（后端未启动）',

      'index.h1': '选择使用模式',
      'index.sub': '四个模式共用同一套配置逻辑，随时可以来回切换，已勾的选择不会丢',

      'mode.basic.h2': '基础模式',
      'mode.basic.p': '4 个问题，选完就有一套能用的配置',
      'mode.basic.li1': '不用懂任何参数',
      'mode.basic.li2': '自动探测本机 mpv-lazy',
      'mode.basic.li3': '只挑内容类型与档位',

      'mode.advanced.h2': '进阶模式',
      'mode.advanced.p': '核心参数 + Shader 链 + 补帧脚本',
      'mode.advanced.li1': '6 套预设与 9 套一键组合',
      'mode.advanced.li2': 'Shader 链可排序、可增删',
      'mode.advanced.li3': '边勾边看生成的 mpv.conf',

      'mode.expert.h2': '完全体',
      'mode.expert.p': '核心 + 原生选项 + 自定义层，搜索即用',
      'mode.expert.li1': '中文说明、类型、建议值',
      'mode.expert.li2': '自定义 key=value 与 profile 段',
      'mode.expert.li3': '版本 / 回滚：一键还原备份',

      'mode.hell.h2': '地狱模式',
      'mode.hell.p': '直接编辑目标文件的文本框',
      'mode.hell.li1': '不校验、不解释、不拦你',
      'mode.hell.li2': '写入前仍留一份 .bak 备份',
      'mode.hell.li3': '给真的知道自己要干什么的人',

      'card.guide.h2': '🧭 第一次用？先看这个',
      'card.guide.note': '不知道 <code>mpv.conf</code> 该放哪儿、配置怎么写、改坏了怎么救 —— 这篇入门指南从「文件放哪儿」讲到「三条退路」，都是人话。',
      'card.guide.btn1': '📖 打开入门指南',
      'card.guide.btn2': '✨ Shader 搭配说明书',
      'card.guide.btn3': '🙏 致谢与许可',

      'card.keys.h2': '⌨️ 想改快捷键？',
      'card.keys.note': 'mpv 实际在读的那份键位表（mpv-lazy 是 <code>input_uosc.conf</code>）会逐条列出来，可以直接改键、改命令、停用某条；下面还列着 mpv 的 <b>{keyCount} 条</b>内置默认键位做对照。没动过的行保存时一个空格都不会变。',
      'card.keys.btn': '⌨️ 打开快捷键编辑',

      'card.analyze.h2': '🩺 只想看看我现在这份配置怎么样？',
      'card.analyze.note': '不用改任何东西，把 <code>mpv.conf</code> 丢进去（或从本机目录里选），出一份体检报告：哪里会出错、哪些搭配在打架、include 链到底读了什么。',
      'card.analyze.btn1': '🩺 打开配置体检',
      'card.analyze.btn2': '🎛️ 直接去改配置',

      'card.dl.h2': '📦 想装几个好用的脚本 / 字体？',
      'card.dl.note': '从各项目的<b>官方地址</b>下载 mpv 脚本（自动连播、跳片头、裁黑边…）与中文字幕字体，直接放进 <code>scripts\\</code> 和 <code>fonts\\</code>。装过什么本机有清单，随时能卸。',
      'card.dl.btn': '📦 打开下载中心',

      'card.combo.h2': '⚡ 直接打开一套组合',
      'card.combo.note': '下面这些链接会带着组合直接进进阶模式，省得一层层点。',

      'combo.sharp_base': '💎 最锐利基础',
      'combo.sharp_anime': '🌸 动漫锐利链',
      'combo.sharp_real': '🎥 真人锐利链',
      'combo.sharp_light': '🪶 轻量超分',
      'combo.smooth_builtin': '⏱️ 内置补帧',
      'combo.smooth_rife': '🎞️ RIFE 补帧',
      'combo.smooth_mvt': '🧊 MVT 补帧',
      'combo.hdr_pass': '🌈 HDR',
      'combo.clean_deband': '🧹 去色带',

      'index.footer': '所有页面都接的是真实后端：勾选 → 生成 mpv.conf → 写入前自动备份。完全体里是 <b>{optsTotal} 项 mpv 全量选项库</b>（搜索 / 24 分组 / 分页），另有自定义层与版本回滚。下载与一键安装目前只在旧版界面（双击 <code>启动.bat</code>）。'
    },

    'en': {
      'lang.name': 'English',
      'lang.switch': 'Switch language',

      'app.title': 'MPV Config Builder · Choose a mode',

      'topbar.downloadLazy': '📥 Download mpv-lazy',
      'topbar.theme': '🌓 Toggle theme',
      'topbar.target': 'Target:',
      'topbar.detecting': 'Detecting…',
      'topbar.notFound': 'mpv-lazy not found',
      'topbar.backendDown': '(backend not running)',

      'index.h1': 'Choose a mode',
      'index.sub': 'All four modes share the same config logic — switch back and forth any time, your selections are kept',

      'mode.basic.h2': 'Basic',
      'mode.basic.p': 'Four questions, and you walk away with a working config',
      'mode.basic.li1': 'No need to understand any option',
      'mode.basic.li2': 'Detects your local mpv-lazy automatically',
      'mode.basic.li3': 'Pick content type and quality tier only',

      'mode.advanced.h2': 'Advanced',
      'mode.advanced.p': 'Core options + shader chain + frame interpolation',
      'mode.advanced.li1': '6 presets and 9 one-click combos',
      'mode.advanced.li2': 'Reorder, add and remove shaders',
      'mode.advanced.li3': 'Watch mpv.conf build as you tick',

      'mode.expert.h2': 'Full',
      'mode.expert.p': 'Core + native options + a custom layer, searchable',
      'mode.expert.li1': 'Chinese descriptions, types, suggested values',
      'mode.expert.li2': 'Custom key=value and profile sections',
      'mode.expert.li3': 'Versioning / rollback: restore any backup in one click',

      'mode.hell.h2': 'Hell',
      'mode.hell.p': 'A raw text box straight onto the target file',
      'mode.hell.li1': 'No validation, no explanation, nothing stops you',
      'mode.hell.li2': 'Still writes a .bak before touching anything',
      'mode.hell.li3': 'For people who actually know what they are doing',

      'card.guide.h2': '🧭 First time here? Start with this',
      'card.guide.note': 'Not sure where <code>mpv.conf</code> goes, how to write it, or how to recover if you break it — this guide walks from "where does the file live" to "your three ways back out", in plain language.',
      'card.guide.btn1': '📖 Open the guide',
      'card.guide.btn2': '✨ Shader pairing notes',
      'card.guide.btn3': '🙏 Credits and licence',

      'card.keys.h2': '⌨️ Want to change keybindings?',
      'card.keys.note': 'The keybinding file mpv actually reads (for mpv-lazy that is <code>input_uosc.conf</code>) is listed line by line — change keys, change commands, or disable an entry. mpv\'s <b>{keyCount} built-in</b> defaults are listed below for reference. Lines you never touch are written back byte for byte.',
      'card.keys.btn': '⌨️ Open keybinding editor',

      'card.analyze.h2': '🩺 Just want to see how my config looks?',
      'card.analyze.note': 'Change nothing — drop in an <code>mpv.conf</code> (or pick one from your machine) and get a health report: what will break, which pairs conflict, and what the include chain actually pulled in.',
      'card.analyze.btn1': '🩺 Open config checkup',
      'card.analyze.btn2': '🎛️ Go edit the config',

      'card.dl.h2': '📦 Want some good scripts or fonts?',
      'card.dl.note': 'Downloads mpv scripts (autoplay, intro skip, autocrop…) and Chinese subtitle fonts from each project\'s <b>official source</b>, straight into <code>scripts\\</code> and <code>fonts\\</code>. Everything installed is listed locally and can be uninstalled.',
      'card.dl.btn': '📦 Open download centre',

      'card.combo.h2': '⚡ Jump straight into a combo',
      'card.combo.note': 'These links open Advanced mode with the combo already applied — no clicking through layers.',

      'combo.sharp_base': '💎 Sharpest base',
      'combo.sharp_anime': '🌸 Anime sharpen chain',
      'combo.sharp_real': '🎥 Live-action sharpen chain',
      'combo.sharp_light': '🪶 Light upscaling',
      'combo.smooth_builtin': '⏱️ Built-in interpolation',
      'combo.smooth_rife': '🎞️ RIFE interpolation',
      'combo.smooth_mvt': '🧊 MVT interpolation',
      'combo.hdr_pass': '🌈 HDR',
      'combo.clean_deband': '🧹 Debanding',

      'index.footer': 'Every page talks to the real backend: tick → generate mpv.conf → auto-backup before writing. Full mode exposes the <b>{optsTotal}-option mpv library</b> (search / 24 groups / paging), plus a custom layer and version rollback. Downloads and one-click install are still only in the legacy UI (double-click <code>启动.bat</code>).'
    }
  };

  var current = DEFAULT_LANG;

  /** 取当前语言的翻译表（缺语言就退回默认语言，不会白屏） */
  function table(lang) {
    return DICT[lang] || DICT[DEFAULT_LANG];
  }

  /** 把 {name} 替换成 VARS 里对应的值 —— 数字只有一份来源 */
  function fill(s) {
    return String(s).replace(/\{(\w+)\}/g, function (m, k) {
      return Object.prototype.hasOwnProperty.call(VARS, k) ? String(VARS[k]) : m;
    });
  }

  /**
   * t('card.keys.note') —— 取一条翻译。
   * 当前语言缺这条就退回默认语言，保证界面永远有字。
   */
  function t(key, extra) {
    var s = table(current)[key];
    if (s === undefined) s = table(DEFAULT_LANG)[key];
    if (s === undefined) return key;          // 两条都没有：显示 key 本身，比空白好排查
    var vars = extra || VARS;
    return String(s).replace(/\{(\w+)\}/g, function (m, k) {
      return Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m;
    });
  }

  /**
   * 把翻译刷进 DOM。
   *   data-i18n         → textContent（纯文本，安全）
   *   data-i18n-html    → innerHTML（译文里有 <code> / <b> 才用这个）
   *   data-i18n-title   → title 属性
   *   data-i18n-ph      → placeholder
   */
  function apply(root) {
    var scope = root || document;

    scope.querySelectorAll('[data-i18n]').forEach(function (el) {
      el.textContent = t(el.getAttribute('data-i18n'));
    });
    scope.querySelectorAll('[data-i18n-html]').forEach(function (el) {
      el.innerHTML = t(el.getAttribute('data-i18n-html'));
    });
    scope.querySelectorAll('[data-i18n-title]').forEach(function (el) {
      el.title = t(el.getAttribute('data-i18n-title'));
    });
    scope.querySelectorAll('[data-i18n-ph]').forEach(function (el) {
      el.placeholder = t(el.getAttribute('data-i18n-ph'));
    });

    // data-i18n-opt：在字符串里带一个「语言名」占位，用于切换按钮的自身文案
    scope.querySelectorAll('[data-i18n-langname]').forEach(function (el) {
      el.textContent = t('lang.name');
    });

    document.documentElement.lang = current;
  }

  function readStored() {
    try { return localStorage.getItem(STORE_KEY); } catch (e) { return null; }
  }

  function persist(lang) {
    try { localStorage.setItem(STORE_KEY, lang); } catch (e) {}
  }

  /** 切换语言：刷 DOM → 记偏好 → 让页面自己补刷动态内容 */
  function setLang(lang, opts) {
    if (SUPPORTED.indexOf(lang) < 0) lang = DEFAULT_LANG;
    current = lang;
    apply();
    if (!opts || opts.persist !== false) persist(lang);
    // 页面里由 JS 动态生成的文字（版本号、目标路径、错误提示）不在 DOM 属性上，
    // 派个事件让各页自己重刷一遍
    document.dispatchEvent(new CustomEvent('i18n:change', { detail: { lang: lang } }));
    return lang;
  }

  /** 下一个语言（只有两种，切来切去就够用；将来加语言这里要改成菜单） */
  function next() {
    var i = SUPPORTED.indexOf(current);
    return SUPPORTED[(i + 1) % SUPPORTED.length];
  }

  /** 给切换按钮接上事件，并把按钮自身文案刷成当前语言名 */
  function bindToggle(root) {
    var scope = root || document;
    scope.querySelectorAll('[data-lang-toggle]').forEach(function (b) {
      b.addEventListener('click', function () {
        setLang(next());
        b.textContent = '🌐 ' + t('lang.name');
      });
      b.textContent = '🌐 ' + t('lang.name');
      b.title = t('lang.switch');
    });
  }

  // 页面一解析完就刷一遍。i18n.js 放在 </body> 前，那时 DOM 已经就绪，
  // 但为保险起见两种时机都处理（和 api.js 一个思路）。
  function boot() {
    var saved = readStored();
    if (saved && SUPPORTED.indexOf(saved) >= 0) current = saved;
    apply();
    bindToggle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.I18N = {
    t: t,
    apply: apply,
    setLang: setLang,
    next: next,
    bindToggle: bindToggle,
    lang: function () { return current; },
    supported: SUPPORTED.slice(),
    vars: VARS
  };
})();

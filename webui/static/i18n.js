/* i18n —— 机制层
 * ============================================================================
 * 第 1 步只搭机制（框架 + 语言切换 + index.html 当样板），**不翻完 1098 处** ——
 * 翻完是第 3 步，见 docs/待做.md §〇。
 *
 * ── 三个设计决定，改之前先看 ────────────────────────────────────────────
 *
 * 1. 语言包**内嵌在 JS 里，不用 fetch 去取 JSON**
 *    页面可能从 file:// 或外壳的资源协议载入；file:// 下 fetch 相对路径的
 *    JSON 会被 CORS 挡掉，资源协议也未必通。
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
 * ── 检索留痕（工程规则：先搜寻后自研）───────────────────────────────────
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

  /* 运行时才填的占位名 —— 值由调用方传进来（`t(key, {changes: 3})`），
     这里只登记名字，让 `verify.py i18n` 的占位符检查认得它们、
     不去误报成漏填。别把默认值写在这里：那会变成第二个真相源。
     2026-10-14 下载中心做深一轮，新增 total/installed/n/path/when/what/
     need/free/mirror/method/detail/bad —— 那一页的列表计数、确认对话框、
     安装计划面板都是带数运行时拼串。 */
  var RUNTIME_VARS = ['changes', 'size', 'lines', 'chars',
    'total', 'installed', 'n', 'path', 'when', 'what', 'need', 'free',
    'mirror', 'method', 'detail', 'bad', 'd',
    // 2026-10-14 advanced 轮：state.js 共用层的带数拼串
    'name', 'summary', 'enc', 'nl', 'v', 'pct', 'six', 'label', 'key',
    'rec', 'msg', 'shown', 'count', 'cond',
    // 进阶页：预设/扫描结果里的标识符与计数
    'files', 'g', 'id', 'pc',
    // 快捷键页：行数/键位/命令/文件名
    'as', 'binds', 'shown', 'cmd',
    // 2026-11-17 全量英文化：库统计的筛选说明、回滚确认的目标路径
    'q', 'hit', 'scope', 'zh', 'target'];

  var DICT = {
    'zh-CN': {
      'lang.name': '中文',
      'lang.switch': '切换语言',

      'status.targetEmpty': '未选择',
      'status.changes': '改动 {changes} 处',
      'status.backendOn': '就绪',
      'status.backendOff': '服务未响应',
      'status.backendUnknown': '检查中…',
      'analyze.emptyTitle': '还没有体检结果',
      'analyze.emptyBody': '选上面一份配置，或把 mpv.conf 直接拖进来，结果会显示在这里。',
      'status.offline': '后端没有响应：界面还在，但读不到配置',
      'status.retry': '重试',

      'api.connLost': '后端连接中断：',
      'api.badResponse': '后端返回了无法识别的响应',
      'api.unknownError': '未知错误',
      'pick.targetPrompt': 'mpv 配置目录（一般是 portable_config）：',
      'toast.copied': '已复制：',
      'toast.copyFail': '复制失败，请手动选中：',
      'gs.hint': '输入关键词后回车。',
      'gs.searching': '搜索中…',
      'gs.empty': '没找到匹配项。键名、中文名都能搜；键位与脚本要先在页面里选过目标目录才会出现。',
      'gs.title': '全站搜索',
      'gs.placeholder': '搜配置项 / uosc / 键位 / 脚本，回车开始',
      'gs.close': '关闭',
      'gs.clickCopy': '点击复制',
      'guide.enNotice': '界面已切换成英文，但内置文档正文目前只有中文版本。',
      'guide.brand': '文档',
      'guide.switchMode': '切换模式',
      'guide.loading': '正在读取…',
      'guide.readFailed': '读取失败',
      'doc.guide': '入门指南',
      'doc.shaders': 'Shader 搭配说明书',
      'doc.thanks': '致谢与许可',
      'doc.roadmap': '产品说明',
      'gs.tip': '全站搜索（Ctrl+K）：配置项 / uosc / 键位 / 脚本',
      'win.menu': '菜单',
      'win.min': '最小化',
      'win.max': '最大化',
      'win.close': '关闭',

      'ctx.copyKey': '复制选项名',
      'ctx.copyValue': '复制当前值',
      'ctx.reset': '恢复默认（取消勾选）',
      'ctx.info': '完整说明',

      // 键盘快捷键层（api.js，R-28）。帮助面板是 JS 渲染的，
      // 走 SBT() 取词 + i18n:change 重画，与 status.* 同一模式
      'hk.title': '键盘快捷键',
      'hk.close': '关闭',
      'hk.primary': '触发本页主操作（生成配置 / 保存）',
      'hk.nav': '在选项之间移动',
      'hk.toggle': '勾选 / 取消勾选',
      'hk.info': '看这一行的完整说明',
      'hk.help': '打开本面板',
      'hk.esc': '关闭面板',
      'hk.statusHint': '快捷键',
      'hk.statusHintTitle': '看有哪些键盘快捷键',

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

      // 地狱模式页的整句。这三句在 HTML 里都是**完整的一段**（只含 <code> / <b>
      // 内联标签），所以走 data-i18n / data-i18n-html 套整句，不进词条表 ——
      // 词条表按原文精确匹配，被标签截断的半句译出来会「语法对、意思不通」。
      'hell.dangerNote': '⚠ 不校验、不解释。唯一的保险是写入前自动生成的 <code>.bak-时间戳</code> 文件（想彻底裸写，自己把备份删掉即可）。',
      'hell.whoP': '有人不需要向导、不需要中文说明、不需要冲突检测 —— 他们要的就是一个直接编辑目标文件的文本框和一个不啰嗦的窗口。把这些人塞进完全体里天天点确认弹窗，反而更烦。',
      'hell.positionP': '所以这一页的定位是：<b>把所有护栏都拿掉的那一档</b>。',
      'hell.banner': '🔥 <b>这里没有护栏</b>：不校验语法、不合并、不提示冲突、不做中文解释。\n    写坏了 mpv 打不开属于正常现象，请自己留好退路。',
      // 这三条是**运行时拼出来的**（行数 / 字符数 / 文件大小），只能走键位表 + 占位符。
      // 数字一律用花括号占位符引用、值由调用方传进来 —— 不在语言表里写死（§2.6 同款毛病）。
      // ⚠ 注释里别写「大括号 + 中文」当示例：`verify.py i18n` 扫占位符的正则是
      //    \{(\w+)\}，而 Python 的 \w **匹配中文**，会把注释里的示例当成真占位符报红。
      'hell.readOk': '已读取 {size} B',
      'hell.sizeHint': '{lines} 行 · {chars} 字符',
      'hell.sizeHintTab': '{lines} 行 · {chars} 字符 · 含 Tab',

      // 基础模式页的整句。modeHint 两态是**运行时 innerHTML 写入**的（setMode），
      // 走键位表 + I18N.t()；HTML 里的初始句挂 data-i18n-html 与它共用同一键，
      // 保证两条路径（静态标记 / 动态重写）写出来的是同一句话。
      'basic.modeHintCreate': '🆕 从零创建：生成一份新配置。取消勾选只是<b>不写这一项</b>，不会去动你已有的文件。',
      'basic.modeHintEdit': '✏️ 改现有配置：先点下面的「读取现有配置」。合并写入只改勾选的键，原文件里其它内容与注释都保留。',
      'basic.p1Sub': '没装也没关系，可以一键装一个配好的 mpv-lazy（该功能目前在旧版界面里）',
      // 整句收录：句内「分辨率」「刷新率」有短词条，逐节点兜底会把整句切得中英混杂
      'basic.p2Note': '这一步目前只做展示，还没写进配置（预设暂不区分分辨率与刷新率）',

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

      // ---------- 进阶模式（advanced.html，2026-10-14 做深一轮） ----------
      // 侧栏分区（固定那几项；g: 分区的名字是后端 group 字段，按设计不翻）
      'adv.secPreset': '快速预设',
      'adv.secPresetSub': '选一套现成的，再逐项微调',
      'adv.secShader': 'Shader 锐化',
      'adv.secShaderSub': '顺序就是处理链顺序，越靠后越接近收尾',
      'adv.secMemc': '补帧脚本',
      'adv.secMemcSub': '只选一个：补帧与超分脚本不能同时叠加',
      'adv.secOutput': '写入 / 输出',
      'adv.secOutputSub': '写到哪里、怎么写、怎么撤销',
      'adv.secTools': '扫描与下载',
      'adv.secToolsSub': '看看本机到底有哪些 glsl / vpy',
      'adv.secAbout': '关于 / 致谢',
      'adv.secAboutSub': '数据来源与许可',
      'adv.secGroupSub': '勾选即写入；不勾选的选项完全不会出现在配置里',
      // 静态 HTML（词条表盖不全的半句包 span 走 data-i18n）
      'adv.profileBarA': '这份文件里有',
      'adv.profileBarB': '个 profile（只在条件满足时生效）：',
      // 预览卡那行「改动 N 处 · 写入 X」：两个文本节点被 <b>/<code> 切断，
      // 不整句收录的话短条目「写入」会把后半截切成「处 · Write」
      'adv.changesLabel': '改动',
      'adv.changesUnit': '处 · 写入',
      'adv.drawerTitle': '说明',
      'adv.writeHintInclude': '生成 <code>mpv-builder.conf</code>，并在主配置里加一行 include。',
      'adv.writeHintMerge': '把勾选的键合并进现有 <code>mpv.conf</code>，取消勾选的键会被注释掉。',
      'adv.previewModeInclude': '独立 include 文件（想卸载删文件即可）',
      'adv.previewModeMerge': '合并进现有 mpv.conf',
      'adv.writeIncludeLabel': '独立 include 文件（推荐）',
      'adv.writeMergeLabel': '合并进现有 mpv.conf',
      // 预设 / 组合 / 我的预设
      'adv.presetH2': '🌸 内容 × 档位',
      'adv.presetNote': '六个预设就是基础模式那六套。点一下把参数填进下面的页面，可以继续改。',
      'adv.comboH2': '⚡ 一键组合',
      'adv.comboNote': '每个组合是「参数 + shader 链 + 补帧脚本」的成套搭配，按本机实际存在的文件解析。',
      'adv.comboLoading': '（解析中…）',
      'adv.comboLazy': '依赖 mpv-lazy 自带 shader',
      'adv.scanDirs': '扫描目录（第 7 项：列表制，不做全盘扫）',
      'adv.scanDirPlaceholder': '添加一个目录，例如 D:/shaders',
      'adv.scanDirAdd': '添加目录',
      'adv.scanDirStandard': '标准目录',
      'ob.title': '第一次来？先花 10 秒',
      'ob.goalQ': '你要干嘛？',
      'ob.goalCreate': '从零开始配',
      'ob.goalEdit': '改现有配置',
      'ob.goalCheck': '只看体检',
      'ob.dirQ': '检测到这些 mpv 配置目录，用哪个？',
      'ob.dirNote': '选一个作为默认；之后随时能在各页面改。',
      'ob.skip': '跳过，我自己来',
      'ob.reopen': '重新运行引导',
      'static.mode': '静态模式：此功能需要在本机运行后端',
      'static.banner': '当前是 GitHub Pages 静态演示：可以浏览选项库与文档；写配置 / 体检等功能请在本机运行（见 README）。',
      'static.docNote': '静态模式：以下为文档原文（完整排版请在本机运行后端打开本页）。',
      'static.docMissing': '静态模式下找不到这份文档。',
      'adv.clearAll': '🗑️ 清空全部选择',
      'adv.clearShaders': '🧹 只清 shader / 补帧脚本',
      'adv.clearNote': '只清本软件里的选择，不动你的配置文件',
      'adv.clearAllConfirm': '清空所有勾选？（不会动你的配置文件）',
      'adv.clearShadersToast': '已清空 shader 与补帧脚本',
      'adv.presetApplied': '✅ 已套用「{label}」',
      'adv.presetAppliedFull': '✅ 已套用「{label}」（{n} 项）—— 记得看右边预览再生成',
      'adv.presetMissing': '；本机缺少：{what}',
      'adv.comboApplied': '✅ 已套用「{label}」',
      'adv.comboMissing': '⚠ 本机缺少：{what}',
      'adv.comboLoadFailed': '组合加载失败：',
      'adv.myPresetH2': '💾 我自己的预设',
      'adv.myPresetNote': '上面那六套是内置的（代码里写死的）。这里存的是<b>你自己调好的一套</b> —— 参数、shader 链、补帧脚本、以及取消勾选的项一起存，放在 <code>presets/</code> 目录里。<b>刷新页面不会丢</b>，也能导出发给别人。',
      'adv.myPresetEmpty': '还没有存过预设。上面调好一套之后，在下面起个名字点「存下当前这一套」。',
      'adv.myPresetSave': '💾 存下当前这一套',
      'adv.myPresetExport': '⬇️ 导出成文件',
      'adv.myPresetImport': '⬆️ 从文件导入',
      'adv.myPresetCountN': '{n} 个选项',
      'adv.myPresetShadersN': ' · {n} 个 shader',
      'adv.myPresetMemc': ' · 含补帧脚本',
      'adv.myPresetBroken': '⚠ 有 {n} 个预设文件读不动（{files}）—— 没有删掉它们，你可以自己看看',
      'adv.myPresetNotFound': '找不到预设「{id}」，它可能刚被删掉了',
      'adv.exportTitle': '导出成文件',
      'adv.applyTitle': '点一下切换到这套方案',
      'adv.duplicateTitle': '复制成另一套方案',
      'adv.duplicatePrompt': '给复制出来的方案起个名字（原方案：{name}）',
      'adv.duplicateDefault': '{name} 副本',
      'adv.delTitle': '删掉这个预设',
      'adv.myPresetNeedName': '给这套预设起个名字吧',
      'adv.myPresetNothing': '一个选项都没勾，没什么可存的',
      'adv.myPresetOverwriteConfirm': '「{name}」已经存在了，覆盖它吗？',
      'adv.myPresetDelConfirm': '删掉预设「{id}」？\n\n只删这个文件，不动你的 mpv 配置。',
      'adv.exportFailed': '导出失败',
      'adv.importReadFailed': '❌ 读不了这个文件：{msg}',
      'adv.importFailed': '导入失败',
      'adv.importHint': '要留成自己的预设，就起个名字点「存下当前这一套」。',
      // shader 链
      'adv.shaderEmpty': '还没有选 shader，从下面挑一个加进来。',
      'adv.shaderNoFiles': '（本机没扫到 glsl 文件，先去「扫描与下载」）',
      'adv.shaderChainH2': '✨ 当前 shader 链（{n}）',
      'adv.shaderAdd': '➕ 加到链尾',
      'adv.shaderNote': '写入的是 <code>glsl-shaders</code>，顺序 = mpv 的处理顺序。常见顺序：修复/去噪 → 放大 → 色度还原 → 收尾锐化（Adaptive_sharpen 放最后）。',
      'adv.shaderLocalH2': '📦 本机已有（{n}）',
      'adv.shaderLocalNote': '这些是从目标目录里实际扫出来的文件，不是网上抄的清单。',
      'adv.none': '无',
      // 补帧脚本
      'adv.memcEmpty': '本机没扫到 .vpy 脚本',
      'adv.memcH2': '🎞️ 选一个 VS 脚本',
      'adv.memcNote': '同一时刻只能挂一个 vapoursynth 脚本：要么补帧、要么超分、要么降噪。想「补帧 + 超分」同时要，得选一个本身就包含多合一流程的脚本。',
      'adv.memcNone': '🚫 不挂脚本',
      'adv.memcCurrent': '当前：',
      'adv.memcNoneLabel': '（无）',
      'adv.memcHowH2': 'ℹ️ 怎么挑',
      'adv.memcHowNote': '<b>RIFE_NV / RIFE_DML</b>：AI 补帧，效果最好也最吃显卡；N 卡选 NV，其它卡选 DML。<br><b>MVT_LQ / MVT_MQ</b>：MVTools 运动补偿，通用、负载低。<br><b>SVP_*</b>：需要另外装 SVP 管理器。<br><b>SR_* / MIX_UAI_*</b>：超分/多合一脚本，别和 shader 超分链重复叠。',
      // 写入 / 输出
      'adv.outputWhereH2': '📤 写到哪',
      'adv.targetApply': '应用目录',
      'adv.outputHowH2': '📄 怎么写',
      'adv.srcLoad': '📂 读取',
      'adv.outputMergeNote': '合并模式保留原文件里的其它内容与注释，只改我们勾选的键；被取消勾选的键会被注释掉（不删除）。',
      'adv.undoH2': '↩️ 撤销',
      'adv.undoNote': '每次写入前都会生成 <code>xxx.bak-时间戳</code> 备份；完全体里的「版本 / 回滚」页面可以直接一键回滚。',
      // 扫描与下载
      'adv.scanH2': '🔍 扫描',
      'adv.scanNote': '扫描目标目录下的 <code>shaders/</code> 与 <code>vs/</code>，结果会进 shader / 补帧页面。',
      'adv.scanStart': '开始扫描',
      'adv.scanTarget': '目标：',
      'adv.scanNone': '（还没扫描）',
      'adv.scanNeedTarget': '先设置目标目录',
      'adv.scanning': '扫描中…',
      'adv.scanResultPc': 'portable_config: {pc}',
      'adv.scanResultGlsl': 'glsl ({n})：',
      'adv.scanResultVpy': 'vpy ({n})：',
      'adv.scanDone': '扫到 {g} 个 glsl、{v} 个 vpy',
      'adv.dlH2': '📦 下载',
      'adv.dlNote': '本软件不打包任何第三方二进制，链接全部指向官方发布页。',
      'adv.linkLazy': '📥 mpv-lazy 发布页',
      'adv.linkMpvNet': '📥 mpv.net 发布页',
      'adv.linkShaders': '📖 shader 搭配说明书',
      // 关于 / 致谢
      'adv.aboutH2': 'ℹ️ 这个软件是什么',
      'adv.aboutNote': '它不播放视频，只负责把 mpv 配置写对：勾选项 → 生成 mpv.conf，写前备份，随时可撤。所有选项说明来自 mpv 官方手册与社区整理。',
      'adv.aboutGuide': '📖 入门指南（配置放哪儿 / 怎么写 / 怎么救）',
      'adv.thanksH2': '🙏 致谢',
      'adv.thanksNote': '<b>mpv</b> 与官方手册 · <b>hooke007</b> 的 mpv-lazy / mpv_PlayKit / shader 搭配说明书 · <b>Anime4K</b>、<b>FSRCNNX</b>、<b>RAVU</b>、<b>RIFE</b>、<b>MVTools</b>、<b>SVP</b> 等算法作者 · <b>mpv_doc-CN</b> 中文手册翻译组',
      'adv.thanksFull': '🙏 完整致谢与许可',
      // 页面动作
      'adv.noConfigToLoad': '目录里没有可读取的配置文件',
      'adv.detectedTarget': '已用探测到的目录：{path}',
      'adv.noLazyFound': '没探测到 mpv-lazy，手动填吧',
      'adv.copiedClipboard': '已复制到剪贴板',
      'adv.handoffLabel': '刚才体检的那份配置',
      'adv.handoffConfirm': '把「{label}」的内容放进自定义层吗？\n\n放进自定义层 = 原样追加到生成结果末尾，本工具不解析、不改写它。\n选取消则什么都不做。',
      'adv.handoffDone': '已放进自定义层（原样保留，不会被工具改写）',

      // ---------- 快捷键页（keys.html，2026-10-14 做深一轮） ----------
      // 静态整句（HTML 里套 data-i18n）：内置键位卡的标题与说明被 <span>/<code>
      // 切断成三段，包 span 走键，不拿词条表拼半句
      'keys.refH2A': '📚 mpv 内置默认键位（',
      'keys.refH2B': ' 条，只读参考）',
      'keys.refNoteA': '这是从你自己的 mpv 里问出来的（',
      'keys.refNoteB': ' 属性），带真实命令。左边那份配置里如果绑了同一个键，这里会标出来 —— 注意 mpv-lazy 默认关了内置键位（',
      'keys.refNoteC': '），所以这些是「原版 mpv 的默认值」，仅供对照。',
      // 运行时拼串（JS 渲染时走 I18N.t；数字占位符见 RUNTIME_VARS）
      'keys.fileRead': 'mpv 读的是：',
      'keys.fileSource': '来源：',
      'keys.fileActive': '（mpv 正在用这个）',
      'keys.rowsN': '{n} 条',
      'keys.noInputFiles': '（目录里还没有 input 文件，保存时会新建 input.conf）',
      'keys.newFileName': 'input.conf（将新建）',
      'keys.encodingNew': 'UTF-8（新建）',
      'keys.noInputConf': '（没有 input-conf 设置）',
      'keys.countLine': '{binds} 条绑定 · 显示 {shown} 行',
      'keys.countDirty': ' · ⚠ 有未保存改动',
      'keys.promoteNote': '⚠ <b>你改的是播放器自带的键位表</b>（<code>{name}</code>）。升级 mpv-lazy 时它会被<b>覆盖回去</b>，你的改动就没了，而且不会有任何提示。<br>建议另存为 <code>{as}</code>：会生成一份属于你的键位表，并把 <code>mpv.conf</code> 的 <code>input-conf</code> 指过去（原自带文件一个字节都不动）。',
      'keys.promoteBtn': '💾 另存为我自己的键位表',
      'keys.promoteDirty': '有未保存的改动，先点「保存」再另存',
      'keys.promoteConfirm': '会做两件事：\n\n① 生成 {name} 的副本作为你自己的键位表\n② 把 mpv.conf 里的 input-conf 指到它（mpv.conf 会先备份）\n\nmpv-lazy 自带的原文件不会被改动。要继续吗？',
      'keys.switchDirtyConfirm': '这份文件有未保存的改动，切换会丢弃。继续？',
      'keys.headKey': '键位',
      'keys.headCmd': '命令',
      'keys.headComment': '分类 &gt; 说明',
      'keys.rowOnTitle': '取消勾选 = 注释掉这行',
      'keys.rowKeyPh': '（没绑键）',
      'keys.noKeyLabel': '（无键位）',
      'keys.rowCmdPh': '命令',
      'keys.rowCommentPh': '分类 > 说明',
      'keys.rowDelTitle': '删掉这一行',
      'keys.delConfirm': '删掉这一行？\n{key}  {cmd}',
      'keys.noFileToSave': '没有可保存的文件',
      'keys.refOverridden': '已被覆盖',
      'keys.refNoMatch': '没有匹配的。',

      // ---------- state.js 共用层（st.*，advanced / expert 页的选项卡片与预览卡） ----------
      // 2026-10-14 advanced 轮抽出。这些串由 state.js 在运行时写进 DOM，
      // 词条表按文本节点兜底盖不全（会被 <b>/<code> 切断），统一走键位表。
      // 与词条表重复的条目（'生成配置' 等）译文保持一致，别让两条路径显示两种英文。
      'st.primaryApply': '应用修改',
      'st.primaryGenerate': '生成配置',
      'st.previewMerge': '合并后的完整文件',
      'st.previewCreate': '将生成的配置',
      'st.modeHintBlocked': '✏️ 改现有配置：先点「📂 读取现有配置」，否则主按钮不可用（避免你以为在读文件、其实在凭空生成）。',
      'st.modeHintEdit': '✏️ 改现有配置：只改你动过的键，原文件其它内容与注释都保留。取消勾选 = 把原来那行<b>注释掉</b>。',
      'st.readFirstTitle': '先读取现有配置',
      'st.readOk': '✅ 已读取 {name}：{summary}',
      'st.readProfilesNote': '；另有 {n} 个 profile 没动，需要的话在右边单独载入',
      'st.loadEncoding': '编码 <b>{enc}</b> · 换行 {nl}',
      'st.loadChain': '跟随 include 读到 {n} 个文件：',
      'st.loadNoInclude': '没有 include 其它文件',
      'st.loadMissingInclude': '⚠ {n} 个 include 指向的文件不存在：',
      'st.profileItemsN': '（{n} 项）',
      'st.profileEmpty': 'profile「{name}」里没有可识别的选项',
      'st.profileLoadedCond': '已载入 profile「{name}」的 {n} 项 —— 它原本只在条件满足时生效，写进配置后就是全局生效了',
      'st.profileLoadedCall': '已载入 profile「{name}」的 {n} 项 —— 它原本只在被调用时生效，写进配置后就是全局生效了',
      'st.diffShowFull': '📄 看完整文件',
      'st.diffShowDiff': '🔀 逐行对比',
      'st.diffToggleN': '🔀 逐行对比（{n} 处）',
      'st.previewNoTarget': '（先选目标目录）',
      'st.previewFailed': '预览失败',
      'st.previewEmptyHint': '# 还没有勾选任何选项 —— 左边随便点一个，这里就实时变',
      'st.previewMergeTitle': '合并后的完整文件（{n} 处改动）',
      'st.pendingHint': '⚠ {n} 项勾选了但没填值，不会被写入',
      'st.encodingHint': '按原编码写回：{enc}',
      'st.scoreEmpty': '配置里还没有内容，先勾几个选项再看评分。',
      'st.applyNoTarget': '请先选目标配置目录',
      'undo.hint': '刚刚写入了配置。{n} 秒内可以一键撤回：',
      'undo.action': '↩️ 撤销这次写入',
      'undo.done': '已撤回这次写入（撤回前的版本也备份了）',
      'undo.fail': '撤回失败：{d}',
      'st.applyNeedRead': '「改现有配置」模式下要先点「📂 读取现有配置」',
      'st.applyMergeNeedRead': '合并模式需要先「读取现有配置」',
      'st.scoreOverall': '综合',
      'st.scoreQuality': '清晰度',
      'st.scoreSharp': '锐度',
      'st.scoreSmooth': '流畅度',
      'st.scoreColor': '色彩',
      'st.scoreLoad': 'GPU 负载',
      'st.scoreNote': '⚠ 评分为启发式估算，请以 mpv 的 stats（按 <code>i</code> 再按 <code>2</code>）实测为准',
      'st.issuesNone': '✅ 没有发现明显问题',
      'st.conflictError': '❌ 冲突',
      'st.conflictWarn': '⚠ 冲突',
      'st.conflictInfo': 'ℹ️ 提示',
      'st.conflictTitle': '点右边的 i 看说明；下方「评估与体检」里有完整原因和改法',
      'st.conflictFlagTitle': '与其它选项冲突，看下方体检',
      'st.typeBool': '开关',
      'st.typeEnum': '枚举',
      'st.typeInt': '整数',
      'st.typeFloat': '小数',
      'st.typeStr': '文本',
      'st.typeColor': '颜色',
      'st.typeList': '列表',
      'st.pickOne': '（选一个值）',
      'st.expandCandidates': '展开候选值',
      'st.suggestLabel': '建议值：',
      'st.moreOptions': '这个选项实际有 <b>{n}</b> 个可选值（上面只是常用建议）—— 输入框可以下拉看全部，也可以直接敲。',
      'st.freeHint': '也可以自己填：不限于上面这些值。',
      'st.defaultTitle': 'mpv 的默认值',
      'st.defaultBadge': '默认 {v}',
      'st.deprecated': '已弃用',
      'st.pendingRowHint': '⚠ 已勾选，但还没填值 —— 填了才会写进配置',
      'st.unsupportedByMpv': '⚠ 当前 mpv 不支持此参数（升级 mpv 后才能用）',
      'st.rangeLabel': '取值范围：',
      'st.infoTitle': '完整说明',
      'st.examples': '官方示例',
      'st.infoClose': '收起说明（双击 / 右键任意处也能关）',
      'st.comboNoMatch': '没有匹配的候选值 —— 直接敲你自己的值就行',
      'st.comboNoOptions': '没有候选值',
      'st.comboTooMany': '候选值太多，只显示前 {n} 个（继续输入可以缩小范围）',
      'st.subpvMeta': '预览（按当前设置实时渲染）',
      'st.subpvText': '这是字幕预览效果 Subtitle Preview 0123',
      'st.subpvNote': '样式来自 <code>sub-font</code> / <code>sub-font-size</code> / <code>sub-color</code> / <code>sub-border-*</code> / <code>sub-shadow-offset</code> / <code>sub-back-color</code> / <code>sub-pos</code>。实际观感还与片源分辨率、窗口大小、以及 ASS 字幕自带的样式有关 —— ASS 字幕默认<b>不</b>吃这些设置（见 <code>sub-ass-override</code>）。',
      'st.colorWarn': 'mpv 的 8 位颜色是 #AARRGGBB（透明度在**最前**两位），不是 #RRGGBBAA。你写的 {v} 会被当成「透明度 {pct}%」。若想表达「不透明」请写 #FF{six}，或直接用 6 位的 #{six}。',
      'st.colorBad': '看不懂这个颜色值：{v}',
      'st.pickValueToast': '给「{label}」选一个值才会写进配置',
      'st.errInt': '这里要填整数',
      'st.errFloat': '这里要填数字',
      'st.errColor': '颜色要写成 #RRGGBB 或 #AARRGGBB',
      'st.errEnum': '这个选项只能填固定取值：{shown}',
      'st.rowBad': '❌ {msg} —— 这样写 mpv 会报错，先改对再写',
      'st.noDesc': '（暂无说明）',
      'st.suggestValues': '建议取值',
      'st.filledToast': '已填入 {key} = {rec}',
      'st.shaderDup': '这个 shader 已经在链里了',
      'st.vpyLoadFailed': '读取失败',
      'st.fuseH2': '🔗 多脚本融合',
      'st.fuseH2Long': '🔗 多脚本融合（把「补帧 + 超分」合成一个 .vpy）',
      'st.fuseNoVpy': '目标目录里没有 <code>vs/</code> 脚本可选。',
      'st.fuseGenerated': '本工具生成',
      'st.fuseNote': 'mpv 同时只能挂一个 vapoursynth 脚本。勾几个脚本，这里按 <b>反交错 → 降噪 → 超分 → 补帧</b> 串成一个 <code>_mb_xxx.vpy</code>：每个脚本的用户选项与管线原样保留、各自独立，原脚本一个都不动。',
      'st.fuseNamePh': '文件名（留空就是 fused）',
      'st.fusePreview': '🔍 预览',
      'st.fuseWrite': '💾 写进 vs 目录',
      'st.fuseUse': '✅ 就用这个脚本',
      'st.fuseCopy': '📋 复制代码',
      'st.fuseNeedTwo': '至少勾两个脚本才需要融合',
      'st.fuseFailed': '融合失败',
      'st.fuseDoneToast': '✅ {detail}，可以用「就用这个脚本」挂上',
      'st.fusePreviewToast': '已生成预览，确认没问题再写进 vs 目录',
      'st.fuseAudioOnly': '这个脚本是音频处理，不能拼进视频链',
      'st.fuseAttached': '已把融合脚本挂上（记得点「应用修改」写进配置）',
      'st.copied': '已复制',
      'st.copyFailed': '复制失败，请手动选中',
      'st.noConfigFiles': '（目录里还没有配置文件）',
      'st.profileSet': '（profile 集合）',

      // ---------- 下载中心（downloads.html，2026-10-14 做深一轮） ----------
      // 静态整句：HTML 里套 data-i18n / data-i18n-html，译文要原样带上内联标签
      //（含 <a> 的 href）—— 词条表按文本节点精确匹配，拆开的半句各译各的会切坏。
      'dl.lazyNote': '本工具是以 <b>mpv-lazy</b> 为底座的。这台机器还没装的话，这里可以直接装 —— 从 <a href="https://github.com/hooke007/mpv_PlayKit" target="_blank" rel="noopener">官方 release</a> 取最新版，<b>不内置也不转发</b>任何文件。<br>流程：读取最新版本 → 下载到暂存目录 → 校验 → 解压 → 把 <code>portable_config</code> 放到目标目录。<b>每一步都会显示进度，可以随时关掉页面（半个包会留着，下次接着下）</b>。',
      'dl.checkOnly': '🔍 检查（不下载）',
      'dl.startInstall': '🚀 开始安装',
      'dl.singleFileNote': '这里只装<b>单文件</b>的东西：脚本进 <code>scripts\\</code>，字体进 <code>fonts\\</code>。全部从各项目的<b>官方地址</b>下载，本工具不内置、不转发任何第三方文件。<br>装过什么会记在本机清单里，列表上直接能看能卸。<b>只有点「下载」才会联网</b>，其余操作全程离线。',
      'dl.overwrite': '覆盖已存在的文件（会先备份）',
      'dl.faqWhere': '<b>装到哪儿</b>：<code>scripts\\</code> 与 <code>fonts\\</code> 就在你选的配置目录里。脚本放进去后 mpv 下次启动就会加载；字体还要在 <code>mpv.conf</code> 里写 <code>sub-font=字体名</code> 才会用上。',
      'dl.faqUnverified': '<b>「已装（未校验）」是什么意思</b>：上游没公开提供 sha256，我们无法验证文件完整性。但安装清单里记了<b>你装到的那份文件的哈希</b> —— 所以至少能判断"装完之后有没有被改过"。',
      'dl.faqUosc': '<b>为什么列表里没有 uosc</b>：它现在只以 <code>.zip</code> 发布（仓库里没有单文件），属于下一阶段（L2「压缩包里挑文件」）的活。这一阶段故意不放必然 404 的条目。',
      'dl.faqVapoursynth': '<b>VapourSynth 插件（滤镜）不在这里</b>：那些 <code>.dll</code> 必须安装到 mpv 配置目录<b>之外</b>，而且有版本与依赖要求，风险高一个量级，安排在 L3。',

      // 运行时拼串：JS 渲染时走 I18N.t()，切语言靠 i18n:change 重刷（见页面末尾）。
      // 数字一律走花括号占位（名字登记在 RUNTIME_VARS），不在语言表里写死。
      'dl.emptyKind': '这个分类下没有条目。',
      'dl.kindFont': '字幕字体',
      'dl.kindScript': 'mpv 脚本',
      'dl.itemsN': '{n} 项',
      // 单复数：字体分类常态就 1 项，英文态「1 items」太刺眼。i18n.js 没有复数机制，
      // 一个键一位，比引一套 plural 规则轻（渲染处按 n === 1 选键）。
      'dl.items1': '1 项',
      'dl.unverified': '未校验',
      'dl.unverifiedTitle': '上游没有提供 sha256，无法验证完整性',
      'dl.state.notInstalled': '未安装',
      'dl.state.installed': '已安装',
      'dl.state.modified': '已安装（文件被改过）',
      'dl.state.missing': '记录在，文件没了',
      'dl.state.untracked': '文件在，但不是这里装的',
      'dl.state.broken': '目标目录不可用',
      'dl.archiveBadge': '整包',
      'dl.archiveTitle': '这是一个压缩包，按白名单挑文件装进去',
      'dl.filesN': '{n} 个文件',
      'dl.filesChangedN': '{n} 个被改过',
      'dl.filesMissingN': '{n} 个不见了',
      'dl.destRoot': '配置目录根',
      'dl.installedAt': '装于 {when}',
      'dl.needs': '需要：{what}',
      'dl.download': '⬇️ 下载',
      'dl.redownload': '⬇️ 重新下载',
      'dl.uninstall': '🗑️ 卸载',
      'dl.homepage': '项目主页',
      'dl.setTargetFirst': '先设置目标目录（配置目录一般是 portable_config）。',
      'dl.reading': '读取中…',
      'dl.statCounts': '共 {total} 项，已安装 {installed} 项',
      'dl.confirmOverwrite': '覆盖 {path}？\n\n原文件会先备份成 .bak-时间戳。',
      'dl.alreadyThere': '这个文件已经在了。要换成清单里的版本，请先勾选「覆盖已存在的文件」',
      'dl.jobLost': '任务丢了',
      'dl.confirmRemove': '卸载 {path}？\n\n删之前会备份一份 .bak-时间戳。\n如果你自己改过这个文件，工具会拒绝删除并提示你。',
      'dl.confirmForceRemove': '确定要强制删除吗？',
      'dl.rowTag': '最新版本',
      'dl.noTag': '（没读到）',
      'dl.rowAsset': '要下的包',
      'dl.splitVolumes': '（分卷 {n} 个，会依次下载）',
      'dl.rowSha': 'sha256',
      'dl.noSha': '⚠ 这个 release 没给，装完只能报「未校验」',
      'dl.rowTarget': '装到',
      'dl.targetWillCreate': '（目录还不存在，会创建）',
      'dl.rowSpace': '空间',
      'dl.spaceUnknown': '拿不到剩余空间',
      'dl.spaceNeed': '需要约 {need}（按包大小 2 倍算）／可用 {free}',
      'dl.otherAssets': '这个 release 里还有别的包（点开看）',
      'dl.noVapoursynth': '⚠ 不含 VapourSynth（补帧/融合用不了）',
      'dl.hasVapoursynth': '✅ 含 VapourSynth',
      'dl.volumesN': '{n} 个分卷',
      'dl.missingVolumeN': '❌ 缺第 {n} 卷',
      'dl.alreadyInstalled': '⚠ 这个目录下已经有 portable_config 了 —— 一键安装<b>不会覆盖</b>它。想重装请自己先挪走或删掉。',
      'dl.planReading': '正在读取最新版本…（要联网）',
      'dl.planFailed': '读取失败',
      'dl.startFailed': '启动失败',
      'dl.preparing': '准备中…',
      'dl.jobLostDetail': '任务丢了：{detail}',
      'dl.configDir': '配置目录：',
      'dl.mirrorMethod': '下载线路：{mirror} · 解压方式：{method}',
      'dl.nextStep': '接下来去 <a href="index.html">入口页</a> 或基础模式，把目标目录设成那个 <code>portable_config</code> 就行。',
      'dl.installFailed': '安装失败',
      'dl.stagedHint': '半个包留在 <code>{path}</code>，下次装会接着下（断点续传），确认不要了可以自己删。',
      'dl.checking': '正在逐条校验下载地址…（要联网，可能要十几秒）',
      'dl.linksBad': '{total} 条地址，❌ {bad} 条失效',
      'dl.linksOk': '{total} 条地址，✅ 全部可用',

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

      'index.footer': '所有页面都接的是真实后端：勾选 → 生成 mpv.conf → 写入前自动备份。完全体里是 <b>{optsTotal} 项 mpv 全量选项库</b>（搜索 / 24 分组 / 分页），另有自定义层与版本回滚。下载与一键安装目前只在旧版界面（双击 <code>启动.bat</code>）。',

      // ---------- 完全体页：侧栏 / 全量库 / 分组 / 抽屉 ----------
      'nav.analyze': '配置体检',
      'nav.analyzeTitle': '不用改任何东西，出一份体检报告',
      'nav.keys': '快捷键',
      'nav.keysTitle': '改 mpv 实际在用的键位表',
      'nav.downloads': '下载中心',
      'nav.downloadsTitle': '脚本 / 字体 / 一键装 mpv-lazy',
      'nav.here': '你正在这一页',
      'nav.aria': '常驻入口',

      // ---------- 完全体各侧栏页 ----------
      'ex.customTitle': '🧩 自定义层',
      'ex.customNote': '这里写的内容会原样追加到配置末尾，不做校验。适合写 profile-*、[xxx] 小节，或数据库里暂时没有的键。',
      'ex.customSave': '💾 存进配置',
      'ex.customClear': '🗑️ 清空',
      'ex.customLive': '修改实时反映在右侧预览',
      'ex.singleTitle': '✍️ 单条写入',
      'ex.keyPh': '键，如 glsl-shader-reload',
      'ex.valPh': '值',
      'ex.addParam': '写入参数区',
      'ex.addNote': '这会把键值放进普通参数区（排好序、好读），和上面的自定义层不冲突。',
      'ex.backupTitle': '🕘 自动备份',
      'ex.backupNote': '每次写入前都会生成 <code>文件名.bak-时间戳</code>。点「回滚」会用备份覆盖当前文件，覆盖前还会把当前版本再备份一次。',
      'ex.refresh': '🔄 刷新列表',
      'ex.dir': '目录：',
      'ex.notSet': '未设置',
      'ex.loading': '读取中…',
      'ex.noBackups': '还没有备份（第一次写入时才会生成）。',
      'ex.originalFile': '原文件 {name} · {size} B',
      'ex.rollback': '↩️ 回滚',
      'ex.restoreConfirm': '用 {name} 覆盖 {target}？当前版本会再备份一次。',
      'ex.clickRefresh': '（点刷新读一次）',
      'ex.uoscMissing': '新建只会写 74 个键里带默认值的那部分，其余继续沿用 uosc 内置默认；文件里没有的键不会硬塞。',
      'ex.uoscMissingDetail': '目标目录里没有 script-opts/uosc.conf。',
      'ex.uoscMissingHint': '装过 uosc 的整合包才会有这个文件；点「新建一份默认 uosc.conf」可以由本工具造一份，也可以手动新建在这个位置：{path}',
      'ex.uoscCreate': '➕ 新建一份默认 uosc.conf',
      'ex.shaderTitle': '✨ glsl-shaders',
      'ex.empty': '（空）',
      'ex.noGlsl': '（本机没扫到 glsl）',
      'ex.addTail': '➕ 加到链尾',
      'ex.memcTitle': '🎞️ vf=vapoursynth（补帧 / 超分脚本）',
      'ex.noVpy': '（本机没扫到 vpy）',
      'ex.noMemc': '🚫 不挂',
      'ex.current': '当前：',
      'ex.none': '（无）',
      'ex.dlTitle': '📦 下载',
      'ex.dlNote': '本软件不打包任何第三方二进制，全部指向官方发布页。',
      'ex.mpvOfficial': 'mpv 官方',
      'ex.shaderGuide': 'shader 说明书',
      'ex.manual': 'mpv 手册',
      'ex.scanTitle': '🔍 扫描本机文件',
      'ex.scanBtn': '扫描 shaders / vs',
      'ex.notScanned': '（还没扫描）',
      'ex.sourceTitle': 'ℹ️ 数据来源',
      'ex.sourceNote': '<b>选项清单 / 默认值</b>：mpv 自带的 <code>--list-options</code>（本机 829 项）<br><b>中文说明</b>：mpv_doc-CN（社区翻译，GPL-3.0，已收录 726 条）<br><b>shader / vpy 列表</b>：从你自己的便携版目录实际扫描，不是固定清单<br><b>搭配建议</b>：hooke007 的《mpv shader 搭配说明书》',
      'ex.openGuide': '📖 入门指南',
      'ex.openShaderGuide': '✨ Shader 说明书',
      'ex.creditsTitle': '🙏 致谢',
      'ex.creditsNote': 'mpv 及其贡献者 · hooke007（mpv-lazy / mpv_PlayKit / shader 说明书）· Anime4K / FSRCNNX / RAVU / RIFE / MVTools / SVP 等算法作者 · mpv_doc-CN 翻译组 · 以及所有在论坛和 issue 里踩过坑的人。',
      'ex.fullCredits': '🙏 完整致谢与许可',
      'ex.roadmap': '🗺️ 产品说明（定位 / 四档模式 / 安全底线）',
      'section.all': '全部选项',
      'section.custom': '自定义选项',
      'section.customSub': '数据库里没有的键，直接写',
      'section.backup': '版本 / 回滚',
      'section.backupSub': '每次写入前的自动备份都在这里',
      'section.shader': 'Shader 链',
      'section.shaderSub': 'glsl-shaders 顺序',
      'section.uosc': 'uosc 设置',
      'section.uoscSub': '进度条 / 控制栏 / 顶栏的外观',
      'section.tools': '下载与安装',
      'section.toolsSub': '官方发布页与说明书',
      'section.about': '关于 / 致谢',
      'section.aboutSub': '数据来源与许可',
      'section.itemCount': '{n} 项',
      'section.has': '有',
      'db.all': '全部',
      'db.searchPh': '🔍 搜全部 {n} 个选项：键名、中文名、中文说明都行，例如 deband / 色带 / 字幕颜色',
      'db.clear': '清空',
      'db.loadMore': '加载更多',
      'db.leftN': '还剩 {n} 项',
      'db.noMatch': '没有匹配的选项。',
      'db.staticStat': '<b>{n}</b> 项 · 静态模式（只读）：写配置 / 建议值 / 候选值合并需本机运行后端',
      'db.stat': '选项库共 <b>{total}</b> 项（有中文说明 {zh} 项）· {scope}命中 <b>{hit}</b> 项，已显示 {shown} 项',
      'db.scopeSearch': '搜索「{q}」',
      'db.scopeGroup': '分组「{g}」',
      'db.scopeNone': '当前',
      'profile.bar': '这份文件里有 <b>{n}</b> 个 profile（只在条件满足时生效）：',
      'profile.load': '载入它的选项',
      'tag.note': '🏷️ 我的分组：拖每行左侧的 ⠿ 到分组上，归属会记住',
      'tag.common': '⭐ 常用',
      'tag.quality': '🎨 画质',
      'tag.performance': '⚡ 性能',
      'tag.subtitles': '💬 字幕',
      'tag.dragTitle': '拖到上面的「我的分组」',
      'drawer.explain': '说明',
      'drawer.closeHint': '点别处 / 再点一次 i / Esc / 右键 都能关',
      'drawer.fill': '填入建议值',
      'drawer.close': '关闭',
    },

    'en': {
      'lang.name': 'English',
      'lang.switch': 'Switch language',

      'status.targetEmpty': 'Not selected',
      'status.changes': '{changes} changes',
      'status.backendOn': 'Ready',
      'status.backendOff': 'Not responding',
      'status.backendUnknown': 'Checking…',
      'analyze.emptyTitle': 'No checkup yet',
      'analyze.emptyBody': 'Pick a config above, or drop mpv.conf here — the report will appear here.',
      'status.offline': 'The backend is not responding: the UI still works, but your config cannot be read',
      'status.retry': 'Retry',

      'api.connLost': 'Backend connection lost: ',
      'api.badResponse': 'The backend returned an unrecognisable response',
      'api.unknownError': 'Unknown error',
      'pick.targetPrompt': 'mpv config folder (usually portable_config):',
      'toast.copied': 'Copied: ',
      'toast.copyFail': 'Copy failed — select the text manually: ',
      'gs.hint': 'Type a keyword and press Enter.',
      'gs.searching': 'Searching…',
      'gs.empty': 'No matches. Key names and descriptions both work; keybindings and scripts appear only after a target folder has been chosen.',
      'gs.title': 'Site search',
      'gs.placeholder': 'Search options / uosc / keybindings / scripts, then press Enter',
      'gs.close': 'Close',
      'gs.clickCopy': 'Click to copy',
      'guide.enNotice': 'The interface is in English, but the bundled guide text is currently Chinese-only.',
      'guide.brand': 'Documentation',
      'guide.switchMode': 'Switch mode',
      'guide.loading': 'Loading…',
      'guide.readFailed': 'Failed to read',
      'doc.guide': 'Getting started',
      'doc.shaders': 'Shader pairing guide',
      'doc.thanks': 'Credits and license',
      'doc.roadmap': 'Product notes',
      'gs.tip': 'Site search (Ctrl+K): options / uosc / keybindings / scripts',
      'win.menu': 'Menu',
      'win.min': 'Minimise',
      'win.max': 'Maximise',
      'win.close': 'Close',

      'ctx.copyKey': 'Copy option name',
      'ctx.copyValue': 'Copy current value',
      'ctx.reset': 'Restore default (untick)',
      'ctx.info': 'Full description',

      'hk.title': 'Keyboard shortcuts',
      'hk.close': 'Close',
      'hk.primary': 'Run the primary action of this page (generate / save)',
      'hk.nav': 'Move between options',
      'hk.toggle': 'Tick / untick',
      'hk.info': 'Open the full description for this row',
      'hk.help': 'Open this panel',
      'hk.esc': 'Close the panel',
      'hk.statusHint': 'Shortcuts',
      'hk.statusHintTitle': 'See the available keyboard shortcuts',

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

      'hell.dangerNote': '⚠ No validation, no explanation. The only safety net is the <code>.bak-timestamp</code> file written automatically before saving (delete the backup yourself if you want it truly raw).',
      'hell.whoP': 'Some people need no wizard, no Chinese explanations, no conflict detection — what they want is a text box straight onto the target file and a window that does not nag. Shoving them into Full mode to dismiss confirmation dialogs all day is far more annoying.',
      'hell.positionP': 'So this page is: <b>the tier with every guardrail removed</b>.',
      'hell.banner': '🔥 <b>No guardrails here</b>: no syntax checks, no merging, no conflict warnings, no explanations.\n    If you break it and mpv will not open, that is expected — keep your own way back.',
      'hell.readOk': 'Read {size} B',
      'hell.sizeHint': '{lines} lines · {chars} chars',
      'hell.sizeHintTab': '{lines} lines · {chars} chars · contains tabs',

      'basic.modeHintCreate': '🆕 Create from scratch: generate a fresh config. Unticking a step only means <b>that step is not written</b> — your existing files are never touched.',
      'basic.modeHintEdit': '✏️ Edit existing config: click "Load config" below first. Merge writing only changes the keys you tick; everything else in the original file, comments included, is kept.',
      'basic.p1Sub': 'No mpv installed yet? One click installs a pre-configured mpv-lazy (that feature still lives in the legacy UI).',
      'basic.p2Note': 'This step is display-only for now and is not written into the config (presets do not yet distinguish resolution or refresh rate).',

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

      // ---------- Advanced mode (advanced.html) ----------
      'adv.secPreset': 'Quick presets',
      'adv.secPresetSub': 'Pick a ready-made set, then fine-tune item by item',
      'adv.secShader': 'Shader sharpening',
      'adv.secShaderSub': 'The order is the processing-chain order — later means closer to the finish',
      'adv.secMemc': 'Interpolation scripts',
      'adv.secMemcSub': 'Pick only one: interpolation and upscaling scripts cannot stack',
      'adv.secOutput': 'Write / output',
      'adv.secOutputSub': 'Where to write, how to write, how to undo',
      'adv.secTools': 'Scan & download',
      'adv.secToolsSub': 'See exactly which glsl / vpy files this machine has',
      'adv.secAbout': 'About / credits',
      'adv.secAboutSub': 'Data sources and licences',
      'adv.secGroupSub': 'Ticking means writing; unticked options never appear in the config at all',
      'adv.profileBarA': 'This file has',
      'adv.profileBarB': 'profiles (they only apply when their condition holds):',
      'adv.changesLabel': 'Changes',
      'adv.changesUnit': '· written to',
      'adv.drawerTitle': 'Notes',
      'adv.writeHintInclude': 'Generates <code>mpv-builder.conf</code> and adds one include line to the main config.',
      'adv.writeHintMerge': 'Merges the ticked keys into the existing <code>mpv.conf</code>; unticked keys get commented out.',
      'adv.previewModeInclude': 'Separate include file (delete the file to uninstall)',
      'adv.previewModeMerge': 'Merge into the existing mpv.conf',
      'adv.writeIncludeLabel': 'Separate include file (recommended)',
      'adv.writeMergeLabel': 'Merge into the existing mpv.conf',
      'adv.presetH2': '🌸 Content × tier',
      'adv.presetNote': 'The six presets are the same six as Basic mode. Click one to fill the parameters into the pages below, then keep tweaking.',
      'adv.comboH2': '⚡ One-click combos',
      'adv.comboNote': 'Each combo is a matched set of "parameters + shader chain + interpolation script", resolved against the files that actually exist on this machine.',
      'adv.comboLoading': '(resolving…)',
      'adv.comboLazy': 'Needs mpv-lazy bundled shaders',
      'adv.scanDirs': 'Scan directories (list-based, no full-disk scan)',
      'adv.scanDirPlaceholder': 'Add a directory, e.g. D:/shaders',
      'adv.scanDirAdd': 'Add directory',
      'adv.scanDirStandard': 'standard',
      'ob.title': 'First time? 10 seconds',
      'ob.goalQ': 'What do you want to do?',
      'ob.goalCreate': 'Start from scratch',
      'ob.goalEdit': 'Edit an existing config',
      'ob.goalCheck': 'Just run a checkup',
      'ob.dirQ': 'These mpv config directories were detected - which one?',
      'ob.dirNote': 'Pick one as the default; you can change it on any page later.',
      'ob.skip': 'Skip, I will handle it',
      'ob.reopen': 'Run the guide again',
      'static.mode': 'Static mode: this feature needs the local backend',
      'static.banner': 'This is the GitHub Pages static demo: browse the option database and docs; writing configs / checkups require running locally (see README).',
      'static.docNote': 'Static mode: raw document text below (full rendering needs the local backend).',
      'static.docMissing': 'Document not found in static mode.',
      'adv.clearAll': '🗑️ Clear all selections',
      'adv.clearShaders': '🧹 Clear shaders / interpolation scripts only',
      'adv.clearNote': 'Only clears the selections inside this tool — your config files are untouched',
      'adv.clearAllConfirm': 'Clear all ticks? (Your config files are not touched)',
      'adv.clearShadersToast': 'Shaders and interpolation scripts cleared',
      'adv.presetApplied': '✅ Applied "{label}"',
      'adv.presetAppliedFull': '✅ Applied "{label}" ({n} items) — check the preview on the right before generating',
      'adv.presetMissing': '; missing on this machine: {what}',
      'adv.comboApplied': '✅ Applied "{label}"',
      'adv.comboMissing': '⚠ Missing on this machine: {what}',
      'adv.comboLoadFailed': 'Combos failed to load: ',
      'adv.myPresetH2': '💾 My own presets',
      'adv.myPresetNote': 'The six sets above are built in (hard-coded). What is stored here is <b>a set you tuned yourself</b> — parameters, shader chain, interpolation script, and the unticked items, all saved together into the <code>presets/</code> folder. <b>Survives a page refresh</b>, and can be exported for others.',
      'adv.myPresetEmpty': 'No presets saved yet. Tune a set above, then give it a name below and click "Save this set".',
      'adv.myPresetSave': '💾 Save this set',
      'adv.myPresetExport': '⬇️ Export to file',
      'adv.myPresetImport': '⬆️ Import from file',
      'adv.myPresetCountN': '{n} options',
      'adv.myPresetShadersN': ' · {n} shaders',
      'adv.myPresetMemc': ' · with interpolation script',
      'adv.myPresetBroken': '⚠ {n} preset files could not be read ({files}) — they were not deleted, have a look yourself',
      'adv.myPresetNotFound': 'Preset "{id}" not found — it may have just been deleted',
      'adv.exportTitle': 'Export to file',
      'adv.applyTitle': 'Click to switch to this scheme',
      'adv.duplicateTitle': 'Duplicate as another scheme',
      'adv.duplicatePrompt': 'Name the duplicated scheme (original: {name})',
      'adv.duplicateDefault': '{name} copy',
      'adv.delTitle': 'Delete this preset',
      'adv.myPresetNeedName': 'Give this preset a name first',
      'adv.myPresetNothing': 'Not a single option is ticked — nothing to save',
      'adv.myPresetOverwriteConfirm': '"{name}" already exists. Overwrite it?',
      'adv.myPresetDelConfirm': 'Delete preset "{id}"?\n\nOnly this file is deleted — your mpv config is untouched.',
      'adv.exportFailed': 'Export failed',
      'adv.importReadFailed': '❌ Cannot read this file: {msg}',
      'adv.importFailed': 'Import failed',
      'adv.importHint': 'To keep it as your own preset, give it a name and click "Save this set".',
      'adv.shaderEmpty': 'No shader selected yet — pick one below to add it.',
      'adv.shaderNoFiles': '(no glsl files found on this machine — check "Scan & download" first)',
      'adv.shaderChainH2': '✨ Current shader chain ({n})',
      'adv.shaderAdd': '➕ Add to chain end',
      'adv.shaderNote': 'What gets written is <code>glsl-shaders</code>, and the order is mpv\'s processing order. A common order: fix/denoise → upscale → chroma restore → finishing sharpen (Adaptive_sharpen last).',
      'adv.shaderLocalH2': '📦 On this machine ({n})',
      'adv.shaderLocalNote': 'These are files actually scanned from the target folder, not a list copied off the web.',
      'adv.none': 'None',
      'adv.memcEmpty': 'No .vpy scripts found on this machine',
      'adv.memcH2': '🎞️ Pick one VS script',
      'adv.memcNote': 'Only one vapoursynth script can be attached at a time: either interpolation, or upscaling, or denoising. To want "interpolation + upscaling" together, pick a script that already contains an all-in-one pipeline.',
      'adv.memcNone': '🚫 No script',
      'adv.memcCurrent': 'Current: ',
      'adv.memcNoneLabel': '(none)',
      'adv.memcHowH2': 'ℹ️ How to pick',
      'adv.memcHowNote': '<b>RIFE_NV / RIFE_DML</b>: AI interpolation, best quality and heaviest on the GPU; NV for N-card, DML for everything else.<br><b>MVT_LQ / MVT_MQ</b>: MVTools motion compensation, universal and light.<br><b>SVP_*</b>: needs the SVP manager installed separately.<br><b>SR_* / MIX_UAI_*</b>: upscaling / all-in-one scripts — do not stack them on top of a shader upscaling chain.',
      'adv.outputWhereH2': '📤 Write where',
      'adv.targetApply': 'Apply folder',
      'adv.outputHowH2': '📄 How to write',
      'adv.srcLoad': '📂 Read',
      'adv.outputMergeNote': 'Merge mode keeps everything else in the original file, comments included, and only changes the keys you ticked; unticked keys get commented out (not deleted).',
      'adv.undoH2': '↩️ Undo',
      'adv.undoNote': 'Every write generates a <code>xxx.bak-timestamp</code> backup first; the "Version / rollback" page in Full mode can roll back in one click.',
      'adv.scanH2': '🔍 Scan',
      'adv.scanNote': 'Scans <code>shaders/</code> and <code>vs/</code> under the target folder; results feed the shader / interpolation pages.',
      'adv.scanStart': 'Start scan',
      'adv.scanTarget': 'Target: ',
      'adv.scanNone': '(not scanned yet)',
      'adv.scanNeedTarget': 'Set the target folder first',
      'adv.scanning': 'Scanning…',
      'adv.scanResultPc': 'portable_config: {pc}',
      'adv.scanResultGlsl': 'glsl ({n}):',
      'adv.scanResultVpy': 'vpy ({n}):',
      'adv.scanDone': 'Found {g} glsl and {v} vpy files',
      'adv.dlH2': '📦 Download',
      'adv.dlNote': 'This tool bundles no third-party binaries; every link points at an official release page.',
      'adv.linkLazy': '📥 mpv-lazy releases',
      'adv.linkMpvNet': '📥 mpv.net releases',
      'adv.linkShaders': '📖 Shader pairing notes',
      'adv.aboutH2': 'ℹ️ What this tool is',
      'adv.aboutNote': 'It does not play video — it only gets your mpv config right: tick options → generate mpv.conf, back up before writing, undo any time. All option descriptions come from the official mpv manual and community curation.',
      'adv.aboutGuide': '📖 Starter guide (where configs live / how to write / how to recover)',
      'adv.thanksH2': '🙏 Credits',
      'adv.thanksNote': '<b>mpv</b> and the official manual · <b>hooke007</b> for mpv-lazy / mpv_PlayKit / the shader pairing notes · algorithm authors behind <b>Anime4K</b>, <b>FSRCNNX</b>, <b>RAVU</b>, <b>RIFE</b>, <b>MVTools</b>, <b>SVP</b> · the <b>mpv_doc-CN</b> manual translation team',
      'adv.thanksFull': '🙏 Full credits and licence',
      'adv.noConfigToLoad': 'No readable config files in this folder',
      'adv.detectedTarget': 'Using the detected folder: {path}',
      'adv.noLazyFound': 'No mpv-lazy detected — fill it in manually',
      'adv.copiedClipboard': 'Copied to clipboard',
      'adv.handoffLabel': 'the config you just checked',
      'adv.handoffConfirm': 'Put the content of "{label}" into the custom layer?\n\nCustom layer = appended verbatim to the end of the generated output; this tool does not parse or rewrite it.\nCancel does nothing.',
      'adv.handoffDone': 'Moved into the custom layer (kept verbatim, never rewritten by the tool)',

      // ---------- Keybindings page (keys.html) ----------
      'keys.refH2A': '📚 mpv built-in default keybindings (',
      'keys.refH2B': ' entries, read-only reference)',
      'keys.refNoteA': 'This comes straight from your own mpv (',
      'keys.refNoteB': ' property), with the real commands. If the config on the left binds the same key, it is flagged here — note that mpv-lazy disables the built-in keybindings by default (',
      'keys.refNoteC': '), so these are "stock mpv defaults", for reference only.',
      'keys.fileRead': 'mpv reads: ',
      'keys.fileSource': 'Source: ',
      'keys.fileActive': '(mpv is using this one)',
      'keys.rowsN': '{n} rows',
      'keys.noInputFiles': '(no input files in this folder yet — saving will create input.conf)',
      'keys.newFileName': 'input.conf (will be created)',
      'keys.encodingNew': 'UTF-8 (new)',
      'keys.noInputConf': '(no input-conf setting)',
      'keys.countLine': '{binds} bindings · {shown} rows shown',
      'keys.countDirty': ' · ⚠ unsaved changes',
      'keys.promoteNote': '⚠ <b>You are editing the player\'s bundled keybinding file</b> (<code>{name}</code>). Upgrading mpv-lazy will <b>overwrite it</b> — your changes will be gone, with no warning.<br>Consider saving it as <code>{as}</code>: that creates a keybinding file of your own and points <code>input-conf</code> in <code>mpv.conf</code> at it (the bundled file is not touched by a single byte).',
      'keys.promoteBtn': '💾 Save as my own keybinding file',
      'keys.promoteDirty': 'You have unsaved changes — click "Save" first',
      'keys.promoteConfirm': 'This does two things:\n\n① Creates a copy of {name} as your own keybinding file\n② Points input-conf in mpv.conf at it (mpv.conf is backed up first)\n\nThe bundled mpv-lazy original is left untouched. Continue?',
      'keys.switchDirtyConfirm': 'This file has unsaved changes; switching will discard them. Continue?',
      'keys.headKey': 'Key',
      'keys.headCmd': 'Command',
      'keys.headComment': 'Category &gt; note',
      'keys.rowOnTitle': 'Untick = comment out this line',
      'keys.rowKeyPh': '(no key)',
      'keys.noKeyLabel': '(no key bound)',
      'keys.rowCmdPh': 'command',
      'keys.rowCommentPh': 'category > note',
      'keys.rowDelTitle': 'Delete this row',
      'keys.delConfirm': 'Delete this row?\n{key}  {cmd}',
      'keys.noFileToSave': 'No file to save',
      'keys.refOverridden': 'overridden',
      'keys.refNoMatch': 'No matches.',

      // ---------- state.js shared layer (advanced / expert option cards & preview) ----------
      'st.primaryApply': 'Apply changes',
      'st.primaryGenerate': 'Generate',
      'st.previewMerge': 'Merged full file',
      'st.previewCreate': 'Config to be generated',
      'st.modeHintBlocked': '✏️ Edit existing config: click "📂 Load config" first, otherwise the main button stays disabled (so you never think you are reading a file when you are actually generating from nothing).',
      'st.modeHintEdit': '✏️ Edit existing config: only the keys you touched change; everything else in the original file, comments included, is kept. Unticking = <b>commenting out</b> that original line.',
      'st.readFirstTitle': 'Read the existing config first',
      'st.readOk': '✅ Read {name}: {summary}',
      'st.readProfilesNote': '; {n} profiles left untouched — load them individually on the right if you need them',
      'st.loadEncoding': 'Encoding <b>{enc}</b> · newline {nl}',
      'st.loadChain': 'Followed include to read {n} files:',
      'st.loadNoInclude': 'No other files included',
      'st.loadMissingInclude': '⚠ {n} include targets do not exist:',
      'st.profileItemsN': '({n} items)',
      'st.profileEmpty': 'No recognisable options in profile "{name}"',
      'st.profileLoadedCond': 'Loaded {n} options from profile "{name}" — they only applied when the condition held; after writing they become global',
      'st.profileLoadedCall': 'Loaded {n} options from profile "{name}" — they only applied when called; after writing they become global',
      'st.diffShowFull': '📄 View full file',
      'st.diffShowDiff': '🔀 Line-by-line diff',
      'st.diffToggleN': '🔀 Line-by-line diff ({n} changes)',
      'st.previewNoTarget': '(pick a target folder first)',
      'st.previewFailed': 'Preview failed',
      'st.previewEmptyHint': '# Nothing ticked yet — click anything on the left and this updates live',
      'st.previewMergeTitle': 'Merged full file ({n} changes)',
      'st.pendingHint': '⚠ {n} items ticked but not filled in — they will not be written',
      'st.encodingHint': 'Written back in the original encoding: {enc}',
      'st.scoreEmpty': 'The config is still empty — tick a few options before scoring.',
      'st.applyNoTarget': 'Pick a target config folder first',
      'undo.hint': 'Config written. You can undo within {n}s:',
      'undo.action': '↩️ Undo this write',
      'undo.done': 'Undone — the version before undo was backed up too',
      'undo.fail': 'Undo failed: {d}',
      'st.applyNeedRead': 'In "edit existing config" mode, click "📂 Load config" first',
      'st.applyMergeNeedRead': 'Merge mode needs "Load config" first',
      'st.scoreOverall': 'Overall',
      'st.scoreQuality': 'Clarity',
      'st.scoreSharp': 'Sharpness',
      'st.scoreSmooth': 'Smoothness',
      'st.scoreColor': 'Colour',
      'st.scoreLoad': 'GPU load',
      'st.scoreNote': '⚠ Scores are heuristic estimates — measure for real with mpv stats (press <code>i</code> then <code>2</code>)',
      'st.issuesNone': '✅ No obvious problems found',
      'st.conflictError': '❌ Conflict',
      'st.conflictWarn': '⚠ Conflict',
      'st.conflictInfo': 'ℹ️ Note',
      'st.conflictTitle': 'Click the i on the right for details; "Assessment and checkup" below has the full reason and fix',
      'st.conflictFlagTitle': 'Conflicts with another option — see the checkup below',
      'st.typeBool': 'flag',
      'st.typeEnum': 'choice',
      'st.typeInt': 'int',
      'st.typeFloat': 'decimal',
      'st.typeStr': 'text',
      'st.typeColor': 'colour',
      'st.typeList': 'list',
      'st.pickOne': '(pick a value)',
      'st.expandCandidates': 'Expand candidate values',
      'st.suggestLabel': 'Suggested: ',
      'st.moreOptions': 'This option actually has <b>{n}</b> values (the ones above are common suggestions) — open the dropdown to see them all, or type your own.',
      'st.freeHint': 'You can type your own too: it is not limited to the values above.',
      'st.defaultTitle': 'mpv default value',
      'st.defaultBadge': 'default {v}',
      'st.deprecated': 'deprecated',
      'st.pendingRowHint': '⚠ Ticked but not filled in — it is written only once you fill it',
      'st.unsupportedByMpv': '⚠ Your current mpv does not support this option (upgrade mpv to use it)',
      'st.rangeLabel': 'Range: ',
      'st.infoTitle': 'Full description',
      'st.examples': 'Official examples',
      'st.infoClose': 'Collapse description (double-click / right-click anywhere also closes)',
      'st.comboNoMatch': 'No matching candidate — just type your own value',
      'st.comboNoOptions': 'No candidate values',
      'st.comboTooMany': 'Too many candidates — showing the first {n} (keep typing to narrow down)',
      'st.subpvMeta': 'Preview (rendered live from current settings)',
      'st.subpvText': 'Subtitle preview sample Subtitle Preview 0123',
      'st.subpvNote': 'Styling comes from <code>sub-font</code> / <code>sub-font-size</code> / <code>sub-color</code> / <code>sub-border-*</code> / <code>sub-shadow-offset</code> / <code>sub-back-color</code> / <code>sub-pos</code>. What you actually see also depends on the source resolution, the window size, and the ASS subtitle\'s own styling — ASS subtitles <b>ignore</b> these settings by default (see <code>sub-ass-override</code>).',
      'st.colorWarn': 'mpv 8-bit colours are #AARRGGBB (alpha in the **first** two digits), not #RRGGBBAA. Your {v} will be read as "{pct}% opacity". For fully opaque write #FF{six}, or just use the 6-digit #{six}.',
      'st.colorBad': 'Cannot parse this colour value: {v}',
      'st.pickValueToast': 'Pick a value for "{label}" before it is written',
      'st.errInt': 'An integer goes here',
      'st.errFloat': 'A number goes here',
      'st.errColor': 'Colours are written #RRGGBB or #AARRGGBB',
      'st.errEnum': 'This option only accepts fixed values: {shown}',
      'st.rowBad': '❌ {msg} — mpv will error on this, fix it before writing',
      'st.noDesc': '(no description yet)',
      'st.suggestValues': 'Suggested values',
      'st.filledToast': 'Filled in {key} = {rec}',
      'st.shaderDup': 'This shader is already in the chain',
      'st.vpyLoadFailed': 'Read failed',
      'st.fuseH2': '🔗 Multi-script fusion',
      'st.fuseH2Long': '🔗 Multi-script fusion (combine "interpolation + upscaling" into one .vpy)',
      'st.fuseNoVpy': 'No <code>vs/</code> scripts to choose from in the target folder.',
      'st.fuseGenerated': 'generated by this tool',
      'st.fuseNote': 'mpv can only run one vapoursynth script at a time. Tick a few scripts and they are chained here in the order <b>deinterlace → denoise → upscale → interpolate</b> into one <code>_mb_xxx.vpy</code>: each script keeps its own user options and pipeline untouched — not a single original script is modified.',
      'st.fuseNamePh': 'File name (leave empty for "fused")',
      'st.fusePreview': '🔍 Preview',
      'st.fuseWrite': '💾 Write into vs/',
      'st.fuseUse': '✅ Use this script',
      'st.fuseCopy': '📋 Copy code',
      'st.fuseNeedTwo': 'Tick at least two scripts before fusing',
      'st.fuseFailed': 'Fusion failed',
      'st.fuseDoneToast': '✅ {detail} — attach it with "Use this script"',
      'st.fusePreviewToast': 'Preview generated — check it before writing into vs/',
      'st.fuseAudioOnly': 'This script is audio processing and cannot join a video chain',
      'st.fuseAttached': 'Fusion script attached (remember to click "Apply changes" to write the config)',
      'st.copied': 'Copied',
      'st.copyFailed': 'Copy failed, please select manually',
      'st.noConfigFiles': '(no config files in this folder yet)',
      'st.profileSet': '(profile collection)',

      // ---------- Download centre (downloads.html) ----------
      'dl.lazyNote': 'This tool is built on <b>mpv-lazy</b>. If this machine does not have it yet, you can install it right here — the latest version comes from the <a href="https://github.com/hooke007/mpv_PlayKit" target="_blank" rel="noopener">official release</a>, and <b>nothing is bundled or re-hosted</b>.<br>The flow: read the latest version → download to a staging folder → verify → extract → drop <code>portable_config</code> into the target folder. <b>Progress is shown for every step, and you can close the page at any time (a partial package is kept and resumed next time)</b>.',
      'dl.checkOnly': '🔍 Check (no download)',
      'dl.startInstall': '🚀 Start install',
      'dl.singleFileNote': 'Only <b>single-file</b> things are installed here: scripts go to <code>scripts\\</code>, fonts to <code>fonts\\</code>. Everything is downloaded from each project\'s <b>official source</b> — this tool neither bundles nor re-hosts any third-party file.<br>Whatever you install is recorded in a local manifest, visible and uninstallable right from the list. <b>Only clicking "Download" goes online</b>; everything else works fully offline.',
      'dl.overwrite': 'Overwrite existing files (backed up first)',
      'dl.faqWhere': '<b>Where things go</b>: <code>scripts\\</code> and <code>fonts\\</code> live inside the config folder you picked. Scripts are loaded the next time mpv starts; fonts also need <code>sub-font=font name</code> written into <code>mpv.conf</code> before they take effect.',
      'dl.faqUnverified': '<b>What "installed (unverified)" means</b>: the upstream publishes no sha256, so file integrity cannot be verified. But the local manifest records <b>the hash of the copy you installed</b> — so at least you can tell whether it changed after installation.',
      'dl.faqUosc': '<b>Why uosc is not in the list</b>: it is only published as a <code>.zip</code> (no single file in the repo), which belongs to the next stage (L2, "pick files out of an archive"). This stage deliberately leaves out entries that would 404 for sure.',
      'dl.faqVapoursynth': '<b>VapourSynth plugins (filters) are not here</b>: those <code>.dll</code> files must be installed <b>outside</b> the mpv config folder, and they carry version and dependency requirements — a whole order of magnitude riskier, so they are scheduled for L3.',

      'dl.emptyKind': 'No items in this category.',
      'dl.kindFont': 'Subtitle fonts',
      'dl.kindScript': 'mpv scripts',
      'dl.itemsN': '{n} items',
      'dl.items1': '1 item',
      'dl.unverified': 'Unverified',
      'dl.unverifiedTitle': 'Upstream publishes no sha256, so integrity cannot be verified',
      'dl.state.notInstalled': 'Not installed',
      'dl.state.installed': 'Installed',
      'dl.state.modified': 'Installed (file modified)',
      'dl.state.missing': 'Listed, but the file is gone',
      'dl.state.untracked': 'Present, but not installed here',
      'dl.state.broken': 'Target folder unusable',
      'dl.archiveBadge': 'Whole package',
      'dl.archiveTitle': 'This is an archive; files are picked in by an allowlist',
      'dl.filesN': '{n} files',
      'dl.filesChangedN': '{n} modified',
      'dl.filesMissingN': '{n} missing',
      'dl.destRoot': 'config folder root',
      'dl.installedAt': 'Installed {when}',
      'dl.needs': 'Needs: {what}',
      'dl.download': '⬇️ Download',
      'dl.redownload': '⬇️ Download again',
      'dl.uninstall': '🗑️ Uninstall',
      'dl.homepage': 'Project page',
      'dl.setTargetFirst': 'Set the target folder first (the config folder is usually portable_config).',
      'dl.reading': 'Reading…',
      'dl.statCounts': '{total} items, {installed} installed',
      'dl.confirmOverwrite': 'Overwrite {path}?\n\nThe original file is backed up as .bak-timestamp first.',
      'dl.alreadyThere': 'This file is already there. To replace it with the manifest version, tick "Overwrite existing files" first.',
      'dl.jobLost': 'The job was lost',
      'dl.confirmRemove': 'Uninstall {path}?\n\nA .bak-timestamp backup is taken before deleting.\nIf you modified this file yourself, the tool refuses to delete it and tells you why.',
      'dl.confirmForceRemove': 'Force the deletion anyway?',
      'dl.rowTag': 'Latest version',
      'dl.noTag': '(not read)',
      'dl.rowAsset': 'Package to download',
      'dl.splitVolumes': '({n} volumes, downloaded in order)',
      'dl.rowSha': 'sha256',
      'dl.noSha': '⚠ This release publishes no sha256 — after installing it can only be reported as "unverified"',
      'dl.rowTarget': 'Install to',
      'dl.targetWillCreate': '(folder does not exist yet, it will be created)',
      'dl.rowSpace': 'Space',
      'dl.spaceUnknown': 'Cannot read free space',
      'dl.spaceNeed': 'Need about {need} (twice the package size) / {free} available',
      'dl.otherAssets': 'This release has other packages (click to expand)',
      'dl.noVapoursynth': '⚠ No VapourSynth (interpolation and fusion will not work)',
      'dl.hasVapoursynth': '✅ Includes VapourSynth',
      'dl.volumesN': '{n} volumes',
      'dl.missingVolumeN': '❌ missing volume {n}',
      'dl.alreadyInstalled': '⚠ This folder already has a portable_config — one-click install <b>will not overwrite</b> it. To reinstall, move or delete it yourself first.',
      'dl.planReading': 'Reading the latest version… (goes online)',
      'dl.planFailed': 'Failed to read',
      'dl.startFailed': 'Failed to start',
      'dl.preparing': 'Preparing…',
      'dl.jobLostDetail': 'Job lost: {detail}',
      'dl.configDir': 'Config folder:',
      'dl.mirrorMethod': 'Mirror: {mirror} · Extract: {method}',
      'dl.nextStep': 'Next, go to the <a href="index.html">entry page</a> or Basic mode and set the target folder to that <code>portable_config</code>.',
      'dl.installFailed': 'Install failed',
      'dl.stagedHint': 'A partial package is kept at <code>{path}</code>; the next install resumes from it (resumable download). Delete it yourself if you no longer want it.',
      'dl.checking': 'Verifying each download URL… (goes online, may take ten-odd seconds)',
      'dl.linksBad': '{total} URLs, ❌ {bad} dead',
      'dl.linksOk': '{total} URLs, ✅ all reachable',

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

      'index.footer': 'Every page talks to the real backend: tick → generate mpv.conf → auto-backup before writing. Full mode exposes the <b>{optsTotal}-option mpv library</b> (search / 24 groups / paging), plus a custom layer and version rollback. Downloads and one-click install are still only in the legacy UI (double-click <code>启动.bat</code>).',

      // ---------- Expert page: sidebar / library / groups / drawer ----------
      'nav.analyze': 'Checkup',
      'nav.analyzeTitle': 'Change nothing — just produce a health report',
      'nav.keys': 'Shortcuts',
      'nav.keysTitle': 'Edit the keymap mpv actually uses',
      'nav.downloads': 'Downloads',
      'nav.downloadsTitle': 'Scripts / fonts / one-click mpv-lazy install',
      'nav.here': 'You are here',
      'nav.aria': 'Persistent shortcuts',

      // ---------- Expert secondary pages ----------
      'ex.customTitle': '🧩 Custom layer',
      'ex.customNote': 'This text is appended verbatim to the end of the config, with no validation. Use it for profile-* or [xxx] sections, or for keys the database does not have yet.',
      'ex.customSave': '💾 Save to config',
      'ex.customClear': '🗑️ Clear',
      'ex.customLive': 'Edits show up in the preview on the right immediately',
      'ex.singleTitle': '✍️ Write a single option',
      'ex.keyPh': 'Key, e.g. glsl-shader-reload',
      'ex.valPh': 'Value',
      'ex.addParam': 'Write into the params section',
      'ex.addNote': 'This puts the key/value into the normal params block (sorted, readable) and does not conflict with the custom layer above.',
      'ex.backupTitle': '🕘 Automatic backups',
      'ex.backupNote': 'Before every write a <code>filename.bak-timestamp</code> file is created. “Roll back” overwrites the current file with the backup, and backs up the current version first.',
      'ex.refresh': '🔄 Refresh list',
      'ex.dir': 'Directory:',
      'ex.notSet': 'Not set',
      'ex.clickRefresh': '(click refresh to load)',
      'ex.loading': 'Loading…',
      'ex.noBackups': 'No backups yet (one is created on the first write).',
      'ex.originalFile': 'Original file {name} · {size} B',
      'ex.rollback': '↩️ Roll back',
      'ex.restoreConfirm': 'Overwrite {target} with {name}? The current version will be backed up first.',
      'ex.uoscMissing': 'Creating a file writes only the 74 known keys that have defaults; everything else keeps uosc’s built-in default. Keys not in the file are never forced in.',
      'ex.uoscMissingDetail': 'There is no script-opts/uosc.conf in the target directory.',
      'ex.uoscMissingHint': 'Only bundles that ship uosc contain this file. Click "Create a default uosc.conf" to have this tool generate one, or create it manually here: {path}',
      'ex.uoscCreate': '➕ Create a default uosc.conf',
      'ex.shaderTitle': '✨ glsl-shaders',
      'ex.empty': '(empty)',
      'ex.noGlsl': '(no glsl found on this machine)',
      'ex.addTail': '➕ Append to chain',
      'ex.memcTitle': '🎞️ vf=vapoursynth (interpolation / upscaling scripts)',
      'ex.noVpy': '(no vpy found on this machine)',
      'ex.noMemc': '🚫 None',
      'ex.current': 'Current:',
      'ex.none': '(none)',
      'ex.dlTitle': '📦 Downloads',
      'ex.dlNote': 'This app bundles no third-party binaries; every link goes to the official release page.',
      'ex.mpvOfficial': 'mpv official',
      'ex.shaderGuide': 'shader guide',
      'ex.manual': 'mpv manual',
      'ex.scanTitle': '🔍 Scan local files',
      'ex.scanBtn': 'Scan shaders / vs',
      'ex.notScanned': '(not scanned yet)',
      'ex.sourceTitle': 'ℹ️ Data sources',
      'ex.sourceNote': '<b>Option list / defaults</b>: mpv’s own <code>--list-options</code> (829 options on this machine)<br><b>Descriptions</b>: mpv_doc-CN (community translation, GPL-3.0, 726 entries)<br><b>shader / vpy lists</b>: scanned from your own portable directory, not a fixed list<br><b>Pairing advice</b>: hooke007’s mpv shader pairing guide',
      'ex.openGuide': '📖 Getting started',
      'ex.openShaderGuide': '✨ Shader guide',
      'ex.creditsTitle': '🙏 Credits',
      'ex.creditsNote': 'mpv and its contributors · hooke007 (mpv-lazy / mpv_PlayKit / shader guide) · the authors of Anime4K / FSRCNNX / RAVU / RIFE / MVTools / SVP and other algorithms · the mpv_doc-CN translators · and everyone who hit the pitfalls in forums and issues.',
      'ex.fullCredits': '🙏 Full credits and licenses',
      'ex.roadmap': '🗺️ Product notes (positioning / four modes / safety floor)',
      'section.all': 'All options',
      'section.custom': 'Custom options',
      'section.customSub': 'Keys the database does not have — write them directly',
      'section.backup': 'Versions / rollback',
      'section.backupSub': 'Every automatic backup made before a write',
      'section.shader': 'Shader chain',
      'section.shaderSub': 'glsl-shaders order',
      'section.uosc': 'uosc settings',
      'section.uoscSub': 'Progress bar / controls / top bar appearance',
      'section.tools': 'Download and install',
      'section.toolsSub': 'Official releases and manuals',
      'section.about': 'About / credits',
      'section.aboutSub': 'Data sources and licenses',
      'section.itemCount': '{n} options',
      'section.has': 'On',
      'db.all': 'All',
      'db.searchPh': '🔍 Search all {n} options by key, name or description — e.g. deband / banding / subtitle color',
      'db.clear': 'Clear',
      'db.loadMore': 'Load more',
      'db.leftN': '{n} left',
      'db.noMatch': 'No matching options.',
      'db.staticStat': '<b>{n}</b> options · static mode (read-only): writing configs, suggested values and value merging need the local backend',
      'db.stat': '<b>{total}</b> options in the library ({zh} with a description) · {scope} matched <b>{hit}</b>, showing {shown}',
      'db.scopeSearch': 'search “{q}”',
      'db.scopeGroup': 'group “{g}”',
      'db.scopeNone': 'current',
      'profile.bar': 'This file has <b>{n}</b> profiles (active only when their conditions match):',
      'profile.load': 'Load its options',
      'tag.note': '🏷️ My groups: drag the ⠿ handle on the left onto a group to remember it',
      'tag.common': '⭐ Common',
      'tag.quality': '🎨 Picture quality',
      'tag.performance': '⚡ Performance',
      'tag.subtitles': '💬 Subtitles',
      'tag.dragTitle': 'Drag onto “My groups” above',
      'drawer.explain': 'Details',
      'drawer.closeHint': 'Click elsewhere / press i again / Esc / right-click to close',
      'drawer.fill': 'Use suggested value',
      'drawer.close': 'Close',
    }
  };

  var current = (function () {
    try {
      var s = localStorage.getItem('mpvcb-lang');
      return (s === 'en' || s === 'zh-CN') ? s : DEFAULT_LANG;
    } catch (e) { return DEFAULT_LANG; }
  })();

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

  // ========== 词条表兜底 ==========
  // data-i18n 只能覆盖「写死在 HTML 里、且被标记过」的文字。两处它盖不到：
  //   1. 8 个内页里大量没标记的静态文案；
  //   2. state.js 运行时生成的界面文字（advanced / expert 的主体内容）……
  //      属性方案天生盖不到动态内容，因为元素在标记生效时还不存在。
  // 所以再加一层：按原文精确匹配替换文本节点，并用 MutationObserver 追新内容。
  //
  // 原文一律留档（_origText），切回中文时按原文还原 —— 否则译文覆盖了 DOM，
  // 中文就再也回不来了。

  var ENTRIES = [];
  var EXACT = {};
  var HAN = /[\u4e00-\u9fff]/;
  var _origText = new WeakMap();
  var _origAttr = new WeakMap();
  var _obs = null;
  var _timer = null;

  function loadDict() {
    var d = window.I18N_ZH2EN || {};
    EXACT = d;
    ENTRIES = Object.keys(d).map(function (k) { return [k, d[k]]; });
    // 长的先替换：否则先替掉「文档」，就再也吃不到「文档 · MPV Config Builder」了
    ENTRIES.sort(function (a, b) { return b[0].length - a[0].length; });
  }

  function zh2en(s) {
    if (!s || !HAN.test(s)) return s;
    // 只做整串精确匹配。早期版本会拿短词做子串替换，结果把
    // 「均衡器」变成「Balanced器」、「文件」变成「File」——宁可留中文，
    // 也不能把句子改坏。动态拼接串请改走 I18N.t(key)。
    if (Object.prototype.hasOwnProperty.call(EXACT, s)) return EXACT[s];
    var trimmed = s.trim();
    if (trimmed !== s && Object.prototype.hasOwnProperty.call(EXACT, trimmed)) {
      return s.replace(trimmed, EXACT[trimmed]);
    }
    // 只做整串精确匹配。任何子串替换都会改写选项说明（「选择 MPV 视频输出
    // 驱动」→「选择 MPV Video output驱动」这类混血句），宁可留中文等 key 补。
    return s;
  }

  /** 刷文本节点与 placeholder / title。current 为中文时按原文还原。 */
  function walkDict(root) {
    var scope = root || document;
    var tw = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, null);
    var n, changed = 0;
    while ((n = tw.nextNode())) {
      var p = n.parentNode;
      if (!p) continue;
      if (p.nodeName === 'SCRIPT' || p.nodeName === 'STYLE' || p.nodeName === 'TEXTAREA') continue;
      // 已经走 data-i18n 的节点别管，免得两套机制互相覆盖；
      // data-no-i18n 是「这不是文案，别翻」—— 文件名、键名、路径之类的标识符
      if (p.closest && p.closest('[data-i18n],[data-i18n-html],[data-no-i18n]')) continue;
      var orig = _origText.get(n);
      if (orig === undefined) { orig = n.nodeValue; _origText.set(n, orig); }
      var out = (current === 'en') ? zh2en(orig) : orig;
      if (out !== n.nodeValue) { n.nodeValue = out; changed++; }
    }
    ['placeholder', 'title'].forEach(function (a) {
      scope.querySelectorAll('[' + a + ']').forEach(function (el) {
        var v = el.getAttribute(a);
        if (!v) return;
        var m = _origAttr.get(el);
        if (!m) { m = {}; _origAttr.set(el, m); }
        if (m[a] === undefined) m[a] = v;
        var out = (current === 'en') ? zh2en(m[a]) : m[a];
        if (out !== v) el.setAttribute(a, out);
      });
    });
    return changed;
  }

  /** 追 JS 动态生成的文字：变了就重刷一遍（60ms 去抖，避免自己触发自己） */
  function observe() {
    if (_obs || typeof MutationObserver === 'undefined') return;
    _obs = new MutationObserver(function () {
      if (current !== 'en') return;         // 中文是原文，不用管
      clearTimeout(_timer);
      _timer = setTimeout(function () { walkDict(); }, 60);
    });
    _obs.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  /**
   * 把翻译刷进 DOM。
   *   data-i18n         → textContent（纯文本，安全）
   *   data-i18n-html    → innerHTML（译文里有 <code> / <b> 才用这个）
   *   data-i18n-title   → title 属性
   *   data-i18n-ph      → placeholder
   *   其余文本节点        → 走词条表兜底（见上）
   */
  function apply(root, keysOnly) {
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

    if (typeof window.I18N_ZH2EN === 'object' && ENTRIES.length === 0) loadDict();
    if (!keysOnly) walkDict(scope);   // 重渲染时只刷 data-i18n，别碰选项说明

    document.documentElement.lang = current;
  }

  function readStored() {
    try { return localStorage.getItem(STORE_KEY); } catch (e) { return null; }
  }

  /* 系统默认显示语言 → 本工具支持的语言（只有 zh-CN / en 两套）。
     Tauri/WebView2 下 navigator.languages 跟 Windows 显示语言；浏览器下跟浏览器
     UI 语言。按用户偏好顺序取第一个我们支持的：zh* → zh-CN，en* → en；
     一个都不支持但有值 → 英文兜底（英文当国际通用）；读不到 navigator → 中文，
     跟以前的固定默认一致。
     只在「用户没手动切过」时用；手动切换会写 localStorage，永远以它为准。 */
  function detectSystemLang() {
    var list = [];
    try {
      if (navigator.languages && navigator.languages.length) {
        list = Array.prototype.slice.call(navigator.languages);
      } else if (navigator.language) {
        list = [navigator.language];
      }
    } catch (e) { return DEFAULT_LANG; }
    for (var i = 0; i < list.length; i++) {
      var l = String(list[i] || '').toLowerCase();
      if (l === 'zh' || l.indexOf('zh-') === 0) return 'zh-CN';
      if (l === 'en' || l.indexOf('en-') === 0) return 'en';
    }
    return list.length ? 'en' : DEFAULT_LANG;
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
    else current = detectSystemLang();
    loadDict();
    apply();
    bindToggle();
    observe();
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
    detect: detectSystemLang,
    supported: SUPPORTED.slice(),
    vars: VARS
  };
})();

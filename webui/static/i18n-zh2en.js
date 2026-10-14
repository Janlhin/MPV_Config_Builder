/* i18n 词条表（中 → 英）
 * ============================================================================
 * 这是**纯数据**，机制在 i18n.js 里。分两个文件是为了都不超过 800 行（AGENTS.md §2.x）。
 *
 * 用法：页面里 i18n.js 和本文件都要加载，顺序是 i18n.js 在前。
 *   <script src="i18n.js"></script>
 *   <script src="i18n-zh2en.js"></script>
 *
 * ── 收录标准（重要，别乱加）──────────────────────────────────────────────
 * 只收**语义完整**的条目：按钮、标签、导航、短句、一整句话。
 *
 * **不收被标签截断的半句**。例如 HTML 里
 *     <p>从零创建：生成一份新配置。取消勾选只是<b>不写这一项</b>，不会去动你已有的文件</p>
 * 会被切成三个文本节点：「从零创建：生成一份新配置。取消勾选只是」「不写这一项」
 * 「不会去动你已有的文件」。把这三段各自译成英文拼起来，
 * 语法是对的、意思是不通的 —— 这正是「看着通顺但语义错了」的那类缺陷。
 * 这类条目要留到给整句套上 data-i18n 之后再收（T13 的后续批次）。
 *
 * 匹配规则：按原文长度从长到短依次替换，长的先吃掉，避免短条目把长条目截坏。
 */

window.I18N_ZH2EN = {
  // ---------- 页面标题与导航 ----------
  '文档 · MPV Config Builder': 'Docs · MPV Config Builder',
  '地狱模式 · MPV Config Builder': 'Hell mode · MPV Config Builder',
  '基础模式 · MPV Config Builder': 'Basic mode · MPV Config Builder',
  '快捷键 · MPV Config Builder': 'Keybindings · MPV Config Builder',
  '配置体检 · MPV Config Builder': 'Config checkup · MPV Config Builder',
  '下载中心 · MPV Config Builder': 'Download centre · MPV Config Builder',
  '完全体 · MPV Config Builder': 'Full mode · MPV Config Builder',
  '进阶模式 · MPV Config Builder': 'Advanced mode · MPV Config Builder',
  '文档': 'Docs',
  '切换模式': 'Switch mode',
  '地狱模式': 'Hell mode',
  '基础模式': 'Basic mode',
  '快捷键': 'Keybindings',
  '配置体检': 'Config checkup',
  '下载中心': 'Download centre',
  '完全体': 'Full mode',
  '进阶模式': 'Advanced mode',

  // ---------- 通用状态与按钮 ----------
  '正在读取': 'Reading…',
  '正在加载': 'Loading…',
  '正在计算': 'Computing…',
  '检测中': 'Detecting…',
  '检测到': 'Detected',
  '未选择': 'Not selected',
  '未设置': 'Not set',
  '重新读取': 'Re-read',
  '打开': 'Open',
  '关闭': 'Close',
  '保存': 'Save',
  '另存为': 'Save as',
  '复制': 'Copy',
  '写入': 'Write',
  '读取': 'Read',
  '生成': 'Generate',
  '更改': 'Change',
  '加一条': 'Add one',
  '刷新状态': 'Refresh status',
  '校验清单链接': 'Verify manifest links',
  '选择分类': 'Choose a category',
  '选择文件': 'Choose file',
  '选文件': 'Choose file',
  '全部': 'All',
  '上一步': 'Back',
  '下一步': 'Next',
  '开始安装': 'Start install',
  '自动探测': 'Auto-detect',
  '生成配置': 'Generate config',
  '逐行对比': 'Line-by-line diff',
  '复制全文': 'Copy all',
  '下载为文件': 'Download as a file',
  '直接覆盖写入': 'Overwrite directly',
  '填入建议值': 'Fill in suggested value',
  '去进阶模式改': 'Change it in Advanced mode',
  '装到：': 'Install to:',
  '装到': 'Install to',

  // ---------- 地狱模式 ----------
  '彩蛋 · 没有护栏': 'Easter egg · no guardrails',
  '这里没有护栏': 'No guardrails here',
  '不校验语法、不合并、不提示冲突、不做中文解释':
    'No syntax checking, no merging, no conflict warnings, no explanations',
  '写坏了 mpv 打不开属于正常现象，请自己留好退路':
    'If mpv will not start because of a bad write, that is expected — keep your own way back',
  '列出目录里的配置文件': 'List config files in this folder',
  '先列出目录': 'List the folder first',
  '读进来的是什么，保存下去就是什么 —— 中间没有任何加工':
    'What is read in is what gets written out — nothing is altered in between',
  '我确认知道我在做什么，出问题自己负责':
    'I know what I am doing; if it breaks, that is on me',
  '想彻底裸写，自己把备份删掉即可':
    'For completely raw writing, delete the backup yourself',
  '为什么会有这一页': 'Why does this page exist',
  '拿去完全体里检查': 'Check it in Full mode',
  '裸写': 'Raw write',
  '0 行': '0 lines',
  'bak-时间戳': 'bak-timestamp',
  // hell 页的 toast 在页面加载时（中文态）就渲染进 DOM 了；切语言时词典兜底会
  // 重扫它的文本节点 —— 没有这条的话，短条目「读取」→ Read 会命中「已读取」的
  // 中间，界面变成「已Read 4925 B」。长条目优先匹配，这条正好挡住那次误切。
  '已读取': 'Read',

  // textarea 的 placeholder：HTML 里写的是 `&#10;`，进 DOM 之后是**真正的换行符**，
  // 所以键里必须用 \n 转义 —— 写成字面换行会把这条在文件里断成两行。
  // `vo=` / `scale=` 那些是 mpv 的配置项标识符，**不译**（data-no-i18n 的同一道理）。
  '# 直接写 mpv.conf 的内容\nvo=gpu-next\nscale=ewa_lanczos4sharpest':
    '# Write your mpv.conf here\nvo=gpu-next\nscale=ewa_lanczos4sharpest',

  // ---------- 基础模式 ----------
  '你是从零开始，还是改现有配置':
    'Starting from scratch, or editing an existing config',
  '从零创建': 'Create from scratch',
  '改现有配置': 'Edit existing config',
  '读取现有配置': 'Read existing config',
  '先读一遍，才知道你原来设了什么':
    'It reads first, so it knows what you already had',
  '你的 mpv 配置目录在哪': 'Where is your mpv config folder',
  '下载并安装 mpv-lazy': 'Download and install mpv-lazy',
  '一键安装 mpv-lazy': 'One-click install mpv-lazy',
  '你的设备': 'Your device',
  '已经自动检测好了，不对可以改':
    'Detected automatically — change it if it is wrong',
  '分辨率': 'Resolution',
  '刷新率': 'Refresh rate',
  '显卡': 'GPU',
  '主要看什么': 'What you mainly watch',
  '这会影响 shader 与缩放算法的选择':
    'This affects which shaders and scalers are chosen',
  '动画': 'Animation',
  '番剧、动画电影': 'Anime series and animated films',
  '真人影视': 'Live action',
  '电影、剧集、纪录片': 'Films, series, documentaries',
  '更在意什么': 'What matters more',
  '决定预设档位': 'Decides the preset tier',
  '省电流畅': 'Power-saving and smooth',
  '核显 / 笔记本 / 老机器': 'Integrated GPU / laptop / older machine',
  '均衡': 'Balanced',
  '画质与性能折中': 'A trade-off between quality and performance',
  '最高画质': 'Highest quality',
  '独显，追求细节': 'Discrete GPU, chasing detail',
  '写入方式': 'How to write',
  '独立 include 文件': 'Separate include file',
  '推荐 · 想卸载删文件即可': 'Recommended · delete the file to uninstall',
  '直接合并进 mpv': 'Merge straight into mpv',
  '只有一个文件': 'Only one file',
  '将写入的内容': 'What will be written',
  '写前会自动备份原文件': 'The original file is backed up before writing',
  '写前自动备份': 'Auto-backup before writing',
  '目标': 'Target',
  '文件': 'File',

  // ---------- 快捷键 ----------
  '只看我改过的': 'Only what I changed',
  '只看未启用': 'Only disabled ones',
  '只看被覆盖的': 'Only overridden ones',
  'mpv 内置默认键位': 'mpv built-in default keybindings',
  '这是从你自己的 mpv 里问出来的': 'This comes straight from your own mpv',
  '属性': 'Property',
  '带真实命令。左边那份配置里如果绑了同一个键，这里会标出来':
    'With the real command. If the config on the left binds the same key, it is flagged here',
  '注意 mpv-lazy 默认关了内置键位':
    'Note: mpv-lazy disables the built-in keybindings by default',
  '仅供对照': 'For reference only',
  '点别处 / 再点一次 i / Esc / 右键 都能关':
    'Click elsewhere, press i again, Esc, or right-click — any of them closes it',

  // ---------- 配置体检 ----------
  '看哪一份配置': 'Which config to check',
  '选文件或直接拖进来都行。分析全在本地做，不联网':
    'Pick a file or drag one in. All analysis runs locally, no network',
  '目标目录里的配置文件': 'Config files in the target folder',
  '体检这份': 'Check this one',
  '评估与体检': 'Assessment and checkup',
  '等配置出来再算': 'Calculated once the config is out',
  '改动': 'Changes',

  // 下面四条是 2026-10-09「纵向做深」第一批：把 analyze 页打到切过去 0 汉字。
  //
  // ⚠ 第一条是**被标签截断的半句**，按上面的收录标准本该等整句套上 data-i18n 再收。
  // 这里破例，理由要写清：断点是连词「或者」，后半句「选择文件」已经是独立且完整的
  // 词条，两部分各自成句、拼起来语义不变（Drag mpv.conf here, or / Choose file）。
  // 不能用 data-i18n 覆盖这个 div —— 它内部还挂着 <input type=file>，
  // data-i18n 写 textContent、data-i18n-html 写 innerHTML，都会把那个 input 冲掉。
  '把 mpv.conf 拖到这里，或者': 'Drag mpv.conf here, or',
  '或者直接粘贴内容': 'Or paste the content directly',
  '# 把配置粘在这里': '# Paste your config here',
  '体检这段文本': 'Check this text',

  // ---------- 下载中心 ----------
  // 2026-10-14 做深一轮后，本页整句全部改走 data-i18n / I18N.t（见 i18n.js 的 dl.* 键），
  // 词条表只留三处：两个 h2 标题、input 的 placeholder（属性分支按原文精确匹配）。
  // 删掉的三条（'检查（不下载' / '每一步都会显示进度…' / '装过什么会记在本机清单里…'）
  // 是半句或整句被 data-i18n 接管后的死条目 —— 其中 '检查（不下载' 还少个右括号，
  // 会把按钮文案切成「🔍 Check (without downloading）」，正是收录标准要避免的半句匹配。
  'mpv 脚本与字幕字体': 'mpv scripts and subtitle fonts',
  '❓ 说明': '❓ Notes',
  '（点「检查」自动填默认位置）': '(click "Check" to fill in the default location)',

  // ---------- 完全体 / 进阶 ----------
  '全部选项': 'All options',
  '载入它的选项': 'Load its options',
  '独立文件': 'Separate file',
  '合并进 mpv': 'Merge into mpv',
  '快速预设': 'Quick presets',
  '选一套现成的，再逐项微调':
    'Pick a ready-made set, then fine-tune item by item',
  '独立 include 文件（想卸载删文件即可':
    'Separate include file (delete the file to uninstall)'
};

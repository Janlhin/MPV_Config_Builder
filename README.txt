MPV Config Builder 2.0
给普通人的 mpv 配置工具：装好就能用，改配置不用手写。
（非官方第三方工具，与 mpv / mpv-lazy 作者无隶属关系）

────────────────────────────────────────
运行
────────────────────────────────────────
  【新版界面 · HTML】双击  启动(新版界面).bat
      或：py -3 webui\server.py
      零依赖：Python 标准库起本地服务，用 Edge/Chrome 的 --app 模式开独立窗口
      界面文件在 webui\static\，改 style.css 就能换观感

  【旧版界面 · Tkinter】双击  启动.bat
      或：py -3 mpv_config_builder.py

  依赖：Python 3.8+（Windows 自带 py 启动器即可）。核心逻辑只用标准库，无第三方依赖。
  注意：必须保持 core\ 目录与程序在一起。

────────────────────────────────────────
四种模式（新版界面）+ 一个体检页
────────────────────────────────────────
  入口页 index.html 选模式，各页面共用同一套 core\ 逻辑，随时可来回切
  基础模式   4 个问题（配置目录 / 设备 / 看什么 / 更在意什么）→ 一键生成配置
  进阶模式   核心参数 + Shader 链（可排序）+ 补帧脚本（可融合）+ 6 套预设 + 9 套一键组合
  完全体     813 项 mpv 全量选项库（搜索 / 24 分组 / 分页）+ 自定义层 + 版本回滚
  地狱模式   直接编辑目标文件的文本框：不校验、不解释，写入前仍留 .bak 备份
  配置体检   analyze.html：拖入或选一份 mpv.conf → 出报告（不改任何东西）

  组合链接可以直接分享：advanced.html#combo=sharp_anime（9 套组合都有 id）

────────────────────────────────────────
功能
────────────────────────────────────────
【生成与修改】
- 6 套基础预设：动画·真人 × 省电流畅·均衡·最高画质（按你的机器自动挑选可用的 shader）
- 9 套一键组合：最锐利基础 / 动漫锐利链 / 真人锐利链 / 轻量超分 / 内置补帧 /
  RIFE 补帧 / MVT 补帧 / HDR·广色域 / 去色带；槽位按本机实际文件解析，
  缺哪个会明说「本机缺少：xxx」，不会偷偷换成别的东西
- 每项参数都有中文说明、可选值与建议；点 ⓘ 有侧边抽屉讲清楚
  （点别处 / 再点一次 i / Esc / 右键 都能关掉）
- 勾了但没填值 → 标黄挂起；填错值 → 红框拦住，**不合法的值不会写进配置**
- 两种写入方式：独立 include 文件（推荐，便于卸载）/ 直接合并进 mpv.conf
  - include：生成 mpv-builder.conf 并追加一行 include，卸载只需删文件
  - merge：保留原文件里的注释与其它选项，只改勾选的键，取消勾选的键会被注释掉
  - 右侧预览在 merge 模式下显示「合并后的完整文件」
- 读现有配置：跟随 include 链读全（标明每个键来自哪个文件），
  profile 小节单独列出、不混进全局值（要载入得手动选，会提示后果）
- 写前自动备份 *.bak-时间戳；完全体的「版本 / 回滚」页可一键回滚
- 编码安全：认 UTF-8 / GBK / Big5 与 BOM，**按原编码写回**，不会把你的 GBK 配置改成 UTF-8

【冲突检测】
- 17 条规则，全部注明 mpv 官方手册依据，逐条给「为什么」和「怎么改」
- 例：sigmoid-upscaling ↔ linear-upscaling 不兼容、interpolation 需要 display- 同步、
  icc-profile 会覆盖 target-*、vo=gpu 下用了 gpu-next 独占项、shader 链里两轮超分…
- 涉事选项在列表里直接打 ⚠ 标记，右侧「评估与体检」给出完整说明

【Shader 与补帧】
- Shader / VS 补帧列表按目标目录里真实存在的文件生成，勾选即用真实路径
- Shader 链可上下调序（顺序 = mpv 处理顺序）、可删除、可一键加到尾
- 多脚本融合（R-3）：勾几个 vs 脚本 → 按「反交错 → 降噪 → 超分 → 补帧」
  合成一个 _mb_xxx.vpy。每个脚本的用户选项与管线原样保留、各自独立，
  原脚本一个都不动；生成前先做语法检查，同名非本工具文件拒绝覆盖
- VS 补帧同一时间只启用一项，直接生成 vf=vapoursynth="~~/vs/xxx.vpy"
  （vf 里原有的 @label: 标签会保留）

【配置体检】
- 拖入 / 选文件 / 粘贴文本都行，全程本地分析不联网
- 报告内容：编码与换行、include 链（实际会读哪些文件）、profile 小节、
  工具认识的选项 / 标准但未收录 / 完全不认识 / 重复项、
  搭配冲突、六维评分、问题与建议
- 「完全不认识」现在只报真正不认识的键 —— 标准选项走全量选项库（813 项可写进配置）

【快捷键】
- 列出 mpv 实际在读的那份键位表（mpv-lazy 是 input_uosc.conf），逐条可编辑：
  改键、改命令、改「分类 > 说明」、停用某条、删除、新增
- 命令框带候选（86 条 mpv 命令，来自 mpv --input-cmdlist）
- 另附 mpv 的 209 条内置默认键位做对照（从你自己的 mpv 里问出来的，带真实命令），
  已经被你覆盖的键会标出来
- 保存前自动备份；**没动过的行逐字节原样写回**（连空格都不变）；
  同键绑多次、空命令这类问题会当场拦下
- 数据来源：tools\build_keybindings.py（mpv 升级后重跑一次即可）

【下载与安装】
- 一键安装 mpv-lazy：从官方 release 取最新版 → 下载（断点续传 / 镜像加速 / 进度）
  → sha256 校验 → 解压（zip 优先，7z 走 7z.exe 或系统 tar）→ 自动定位 portable_config
  默认装到 %LOCALAPPDATA%\mpv-lazy（免管理员）※ 目前只在旧版 Tkinter 界面里可用
- 下载器：内置 14 个常用 shader 直链，勾选后自动放进 shaders\ 对应子目录；
  覆盖前备份；下载后自检内容；带「校验链接」批量检查清单
- 资源 / 下载页：24 个外部链接（播放器、着色器库、VS 插件、官方文档）
  ⚠ 只有点「下载选中 / 下载并安装」时才会联网，其余功能全程离线

【其他】
- 窗口设置：geometry / autofit / 最大最小窗口限制 / 锁定比例 / HiDPI
- 更新检测：启动静默检查 mpv-lazy 新版本，另有手动「检查更新」
- 你自己的数据（都不会写进 mpv 配置目录）：
    %LOCALAPPDATA%\MPVConfigBuilder\settings.json   记住了目标目录 / 模式选择
    %LOCALAPPDATA%\MPVConfigBuilder\presets\        你自己存的预设（进阶模式）
    %LOCALAPPDATA%\MPVConfigBuilder\installed.json  下载中心装过什么
  ※ 这些放用户目录而不是程序目录，是为了**装到 Program Files 之后也能写**
    （那里通常只读）。升级 / 重装本工具不会动它们。

────────────────────────────────────────
目录结构
────────────────────────────────────────
  mpv_config_builder.py   旧界面（Tkinter，功能最全）
  webui\                  新界面
      server.py           只用标准库的本地服务 + JSON API（39 个接口）
                          加 --stdio 就不开端口，改用一行一条 JSON 的协议（给 Electron 用）
      api.py              与传输无关的分发层：dispatch(请求) → 响应（HTTP 与 stdio 共用）
      stdio.py            stdio 传输：读 stdin 的 JSONL、写 stdout 的 JSONL
                          **stdout 只走协议，日志一律 stderr**（规格见 specs\stdio-transport.md）
      static\             index / basic / advanced / expert / analyze / keys
                          / downloads / guide / hell（9 个页面）
                          + style.css + api.js + state.js
  core\                   核心逻辑，与界面无关（两个界面共用，24 个模块）
      schema.py           参数表 / shader·vpy 清单 / 原生选项 / 路径辅助
                          / 选项格式化（写盘唯一入口）
      options_db.py       全量选项库的读取与搜索（813 项可写进配置）
      builder.py          状态 → mpv.conf 文本
      loader.py           读 mpv.conf → 状态（含 include 链、profile、vf 标签）
      textio.py           编码探测与按原编码写回
      conflicts.py        冲突检测规则表（17 条）
      combos.py           9 套一键组合
      vpy.py              VPY 融合（把多个 vs 脚本合成一个）
      dlcenter.py         下载中心：mpv 脚本 / 字体的下载、安装清单、卸载
      notes.py            选项中文说明与格式提示（R-25 / R-28 共用）
      annotate.py         给已有配置补注释（纯函数，不碰磁盘）
      diff.py             行级差异（左右并排对比用）
      paths.py            路径解析（源码运行 / 打包运行都成立）
      report.py           配置体检报告
      keys.py             按键绑定（input.conf）的解析 / 编辑 / 写回
      mdrender.py         把仓库里的中文文档渲染进界面（guide.html 用）
      presets.py          基础模式 6 套预设
      writer.py           备份、include 写入、合并写入、取消勾选注释
      analyze.py          mpv.conf 解析与分析
      score.py            六维评分
      net.py              下载清单、镜像线路、HTTP
      hardware.py         分辨率 / 刷新率 / GPU 探测
      installer.py        mpv-lazy 一键安装
      update.py           版本检测
  data\
      mpv_options_zh.json 829 条原始选项 + 726 条中文说明（来自 mpv_doc-CN，GPL-3.0）
                          其中 16 条是命令行专用（mpv 标注 not in config files），
                          读取时会滤掉，所以界面里是 813 项
      mpv_keybindings.json 209 条内置默认按键（从你自己的 mpv 里导出）
      mpv_commands.json   86 条 mpv 命令（--input-cmdlist）
  tools\
      build_options_db.py 重新生成选项库（mpv 升级后跑一次）
      build_keybindings.py 重新生成按键库（同上）
      check_docs.py       检查文档里的数字与实测是否一致
      compare_conflicts.py 冲突规则「重构前/后」等价性对照（4699 组枚举，改规则时跑）
      gen_conflicts_golden.py 重新生成冲突检测的行为快照基准（改规则后才跑）
      check_ui.py         实机验证候选值下拉（要本机有 Edge/Chrome，另开服务）
      check_topnav.py     实机验证 9 个页面的顶栏常驻入口（同上，会自动起后端）
      check_stdio_ui.py   实机验证 9 个页面能跑在 stdio 通道上（同上；
                          会拦截 fetch 记账，任何漏到 HTTP 的 API 调用都算失败）
      check_pack.py       验证打包产物（要先打包；21 项，跑在真 exe 上）
      preflight.py        发布前自检（测试/编译/文档/必带文件/许可/下载链接/顶栏）
  packaging\
      backend.spec        PyInstaller 配方：把后端打成独立 exe（用户机器不需要 Python）
                          用法：py -m PyInstaller packaging\backend.spec
  tests\                  单元测试（648 项，含接口端到端与真实脚本测试）
  specs\                  先写规格再动手的 spec（每份都带验收记录）
  LICENSE                 许可：GPL-3.0 全文
  NOTICE.txt              第三方内容的来源与许可（分发安装包时要一并带上）
  _archive\               不再参与运行的历史文件（见其 README.md）
  *.md                    文档（见下）

────────────────────────────────────────
跑测试 / 发布前自检
────────────────────────────────────────
  py -3 -m unittest discover -s tests -t .
  py -3 tools\check_docs.py      # 文档数字对不对
  py -3 tools\preflight.py       # 发布前一次跑完（加 --offline 跳过联网检查）
  ⚠ tests\__init__.py 是 0 字节但**必须留着**，删了测试跑不起来

────────────────────────────────────────
文档
────────────────────────────────────────
  已完成清单.md              **只写做完并且验证过的东西**（核心模块 / 界面 / 数据 /
                             测试与实测结论）—— 想知道某功能到底有没有，看这份
  产品规划与路线图.md        **只写还没做的**（待做项 / 里程碑 / 待决策 / 未来方向：
                             PyQt6、英文版、许可）—— 想知道还剩什么，看这份
  问题清单与修复计划.md      发现过的问题（P0~P3，状态已刷新）+ F-1~F-18 修复记录
  入门指南.md                第一次改配置该看这个：mpv.conf 放哪儿 / 语法 5 条 /
                             改完怎么确认生效 / 改坏了三条退路 / 新手 8 个坑
  MPV_Shader搭配说明书.md    最锐利画面组合 / 最强大补帧排序（通俗版）
  致谢与许可.md              致谢、免责声明、合规说明
  制作与发布文档.md          打包、安装器、发布流程
  MPV_实机配置分析报告.md    几套实机配置的差异分析
  mpv1配置分析报告.md        单份配置的分析报告

  上面几份在界面里也能直接看：入口页 →「入门指南 / Shader 说明书 / 致谢与许可」，
  或打开 webui\static\guide.html（文档是在线渲染仓库里的 md，只有一个来源）

────────────────────────────────────────
致谢（完整版见 致谢与许可.md）
────────────────────────────────────────
  · mpv / mpv-player 团队 —— 播放器本体与官方手册
  · hooke007 —— mpv-lazy / mpv_PlayKit（本工具最重要的参考来源）
  · bloc97 (Anime4K)、igv (FSRCNNX / KrigBilateral / SSim)、
    bjin (mpv-prescalers / RAVU)、Artoriuz (ArtCNN)、
    the-database (AnimeJaNai)、iwalton3 (default-shader-pack)
  · VapourSynth 团队、dubhater (mvtools)、AmusementClub (vs-rife)、
    SVP Team、k7 (K7sfunc)
  · Anime 字幕论坛及所有分享 mpv 配置经验的朋友

────────────────────────────────────────
许可
────────────────────────────────────────
  本项目按 GNU GPL-3.0 分发 —— 全文见 LICENSE。
  为什么是 GPL-3.0：随包分发的中文选项说明来自 mpv_doc-CN（GPL-3.0），
  而 GPL-3.0 具传染性。
  第三方内容的来源与许可汇总在 NOTICE.txt（分发安装包时要一并带上）。

────────────────────────────────────────
免责声明
────────────────────────────────────────
  · 非官方第三方工具，与上述项目及其作者无隶属关系
  · 不包含、不重新分发任何第三方二进制或着色器文件；
    下载功能只指向各项目的官方发布地址
  · 第三方资源的版权与许可归原作者所有
  · 本工具按现状提供，不附带任何担保；写配置前会自动备份，但仍请自行保留重要副本

评分是启发式指标，不代表实际 FPS 或 Render Time；
最终应以 MPV stats、GPU Render Time、dropped frames 实测为准。

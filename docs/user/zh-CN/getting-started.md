# MPV 配置入门 · 从「文件放哪儿」到「改坏了怎么救」

写给第一次碰 mpv 配置的人。看完这一篇，你至少能做到三件事：
**知道文件该放哪儿**、**看懂一段配置在说什么**、**改坏了能退回去**。

> 本文里的路径规则、语法、`~~/` 含义，都出自 mpv 官方手册（中文版 mpv_doc-CN）原文，
> 不是经验之谈。凡是「手册这么说」的地方我尽量标出来。

---

## 一、mpv.conf 到底放哪儿？

mpv 只会从**一个**「设置目录」读配置，目录在哪，分三种情况：

| 情况 | 设置目录 | 说明 |
|---|---|---|
| **便携版**（推荐） | `mpv.exe` 旁边的 `portable_config\` | 手册原文：「如果 mpv.exe 旁边有一个名为 `portable_config` 的目录存在，所有的设置将只从这个目录加载」。watch-later、缓存也写在这里，整个文件夹拷走就能换机器 |
| **默认安装**（Windows） | `%APPDATA%\mpv\` | 一般是 `C:\users\你的用户名\AppData\Roaming\mpv\`，配置就是这里的 `mpv.conf` |
| **自己指定** | 任意目录 | 启动参数加 `--config-dir="D:\myconf"`，或用环境变量 `MPV_HOME` |

**怎么查自己属于哪种？** 在 cmd 里跑一句就知道默认路径长什么样：

```bat
echo %APPDATA%\mpv\mpv.conf
```

然后再看一眼 `mpv.exe` 旁边有没有 `portable_config` 文件夹 —— **有就是便携版，`%APPDATA%` 那份就不用管了**。

### mpv-lazy 是哪种？

mpv-lazy 是**便携版**。你所有要动的东西都在：

```
mpv-lazy\
├─ mpv.exe
└─ portable_config\          ← 这就是「设置目录」
   ├─ mpv.conf               ← 主配置，改这个
   ├─ input.conf             ← 快捷键
   ├─ profiles.conf          ← 条件配置（[小节] 形式，见第五节）
   ├─ script-opts.conf       ← 脚本参数
   ├─ scripts\               ← 放 .lua / .js 脚本
   ├─ shaders\               ← 放 .glsl / .hook 着色器
   ├─ vs\                    ← 放 .vpy 补帧/超分脚本
   ├─ fonts\                 ← 放字幕字体
   └─ watch_later\           ← 播放进度记忆（自动生成）
```

**记住一句话就够了**：`portable_config\` 就是这个 mpv 的「家」，配置、脚本、着色器、字体全在这里面。

---

## 二、`~~/` 是什么？为什么到处都能看到它

`~~/` 是 **「设置目录」的简写**。手册原文：`~~/` 会返回设置目录下**存在**的那个路径。

| 写法 | 指向 |
|---|---|
| `~~/shaders/FSRCNNX.glsl` | `portable_config\shaders\FSRCNNX.glsl` |
| `~~/vs/MEMC_RIFE_NV.vpy` | `portable_config\vs\MEMC_RIFE_NV.vpy` |
| `~~/fonts` | `portable_config\fonts` |
| `~~desktop/` | 你的桌面（截图常写 `~~desktop/`） |
| `~~exe_dir/` | `mpv.exe` 所在目录 |

**为什么要用它，而不是写 `C:\Program Files\mpv-lazy\...`？**
因为换个盘、换个用户名、把整个文件夹挪个地方，`~~/` 照样对，绝对路径就全废了。
所以抄别人配置时，看到 `~~/` 直接照抄，看到 `C:\Users\某某\...` 一定要改成自己的路径。

---

## 三、配置怎么写：5 条规则

**1. 一行一个选项，写成 `键=值`，不要写 `--`**

```ini
vo=gpu-next          ✅
--vo=gpu-next        ❌（`--` 是命令行用的，配置文件里不写）
```

**2. `#` 之后全是注释**（手册原文：「在 `#` 之后的所有内容都被认为是注释」）

```ini
# 整行注释
vo=gpu-next   # 行尾注释也可以
```

⚠️ **这条有个大坑**：因为 `#` 之后一律算注释，**颜色值必须加引号**，否则会被截断：

```ini
sub-color=#FFD766          ❌ 实际生效的是空值（# 后面被当注释了）
sub-color="#FFD766"        ✅
```

**3. 光写一个选项名 = 打开它**（手册：「如果该值被省略，则暗示 yes」）

```ini
hwdec          ← 等于 hwdec=yes
```

**4. 值里有特殊字符就加引号**

空格、`#`、`"`、`'`、`%`，以及前后的空格，都要用引号包住：

```ini
osd-playing-msg="File: ${filename}"
screenshot-directory="~~desktop/我的截图"
```

**5. 列表用分号 `;` 分隔，Windows 上千万别用冒号**

```ini
glsl-shaders="~~/shaders/a.glsl;~~/shaders/b.glsl"     ✅
glsl-shaders="C:/shaders/a.glsl"                        ✅（单个路径，引号包住）
glsl-shaders="C:/a.glsl:C:/b.glsl"                      ❌ 冒号会和盘符打架
```

---

## 四、改完怎么生效、怎么确认生效了

**配置只在 mpv 启动时读一次** —— 改完必须**重开 mpv**（不是重开视频，是退出再打开）。

想看「到底生效了没」：

1. 播放时按 `i`，再按 `2` → 打开 stats 面板，能看到当前的分辨率、帧率、丢帧、
   以及 **Render Time（渲染耗时）**。判断配置吃不吃得消，看这个，别靠猜。
2. 想看 mpv 到底读了哪些文件、有没有报错：启动参数加 `--log-file=%TEMP%\mpv.log`，
   然后打开这个日志搜 `mpv.conf`。

**优先级**（手册原文）：系统级 < 用户级/便携配置 < 命令行。
所以临时试一个参数，直接在命令行加就行，不用改文件：

```bat
mpv.exe --vo=gpu-next "D:\video.mkv"
```

---

## 五、`[小节]` 是条件配置，别当全局配置抄

`profiles.conf` 或 `mpv.conf` 里可能出现这种写法：

```ini
[ontop_playback]
profile-desc=播放时置顶
profile-cond=not pause and not p.idle_active
ontop=yes
```

`[名字]` 叫 **profile**，里面的选项**只在条件满足时生效**（上面这条就是「正在播放时窗口置顶」）。

⚠️ 新手最常见的误操作：**把小节里的选项复制到全局**，结果「本来只在某条件下生效」的东西变成了常驻。
本工具读取配置时会把 profile 单独列出来，不会混进全局值里 —— 想用哪个 profile，得手动选，而且会提醒你后果。

---

## 六、改坏了怎么救（三条退路，从轻到重）

| 办法 | 怎么做 | 适合 |
|---|---|---|
| **注释掉** | 在那一行前面加 `#`，重开 mpv | 只是某个选项有问题 |
| **用备份盖回去** | 找同目录下的 `mpv.conf.bak-20260913-171205` 这种文件，改名成 `mpv.conf` 覆盖 | 改乱了，想整体回退 |
| **删掉配置重来** | 把 `mpv.conf` 删掉（或改名成 `mpv.conf.old`），mpv 会用默认值启动 | 完全不知道哪里错了 |

**备份是谁生成的？** 本工具每次写入前都会自动生成一个 `文件名.bak-时间戳`，
完全体里的「版本 / 回滚」页面可以直接一键回滚（回滚前还会把当前版本再备份一次）。

**用本工具写的配置，卸载更简单**：默认走「独立 include 文件」方式 ——
它会生成一个 `mpv-builder.conf`，并在你的 `mpv.conf` 里加一行
`include = "~~/mpv-builder.conf"`。想全部撤销：**删掉 `mpv-builder.conf`，再把那一行 include 删掉**，你的原配置一个字都没被改过。

---

## 七、新手最容易踩的 8 个坑

1. **路径没加引号** —— 带空格或 `#` 的路径会被截断或报错。
2. **shader 列表用冒号分隔** —— Windows 下冒号是盘符，mpv 会读错。用 `;`。
3. **文件存成了 UTF-16 或带 BOM** —— 有些编辑器默认就这样，mpv 读到的键名会多出奇怪字符。
   存成 **UTF-8 无 BOM** 最保险（GBK 也能读，但混用容易乱）。
4. **抄了配置没抄文件** —— 配置里写了 `~~/shaders/xxx.glsl`，但你的 `shaders\` 里没有这个文件，
   轻则没效果，重则黑屏。本工具会明确告诉你「本机缺少：xxx」。
5. **同时挂两个 vpy 脚本** —— mpv 同一时刻只能有一个 `vf=vapoursynth=`。
   想要「补帧 + 超分」同时生效，只能用「多脚本融合」把两个脚本合成一个 `.vpy`。
6. **两轮超分叠一起** —— shader 链里同时有 FSRCNNX 和 Anime4K Upscale 之类的两个超分家族，
   负载翻倍、还容易出振铃。选一个家族就够。
7. **`interpolation=yes` 配了非 display 的同步模式** —— 手册明确说这时插值会被**静默禁用**，
   你看到的就是「开了但没效果」。要配 `video-sync=display-resample`。
8. **装到 `Program Files` 改不了配置** —— 那里需要管理员权限。要么用管理员启动，
   要么把 mpv 装到用户目录（本工具装 mpv-lazy 默认装到 `%LOCALAPPDATA%\mpv-lazy`，免管理员）。

---

## 八、从零开始，建议的顺序

1. **先别写配置**，用默认设置播一个你最熟悉的视频，按 `i` 再按 `2`，看一眼 Render Time 和丢帧。
2. **装一个便携版**（mpv-lazy 就挺好），把配置目录记下来。
3. **只改 3 个选项**试试水：

   ```ini
   vo=gpu-next             # 用新的 GPU 渲染器（默认的 gpu 也行）
   hwdec=auto-safe         # 开硬件解码，CPU 轻松很多
   scale=spline36          # 放大算法，比默认的 bilinear 好，性能要求不高
   ```

   改完重开 mpv，再按 `i`/`2` 对比 Render Time。
4. **确认没问题再往上加** —— 缩放算法 → 去色带 → shader → 补帧，一次只加一类。
5. **每加一步都留个备份**（或者干脆用本工具写，它自己会备份）。

---

## 九、这个工具能帮你省掉哪些事

| 你想干的事 | 用哪个页面 | 它替你做了什么 |
|---|---|---|
| 完全不想懂那些参数 | **基础模式** | 问 4 个问题，直接生成一套配置 |
| 想调但怕调坏 | **进阶模式** | 6 套预设 + 9 套一键组合；勾选即预览；值填错了当场红框拦住，**不会把错的写进去** |
| 想折腾到底 | **完全体** | 829 个 mpv 选项全在里面，带中文说明、类型、默认值、取值范围 |
| 只想看看现在这份配置有没有毛病 | **配置体检** | 拖一份 `mpv.conf` 进去：编码、include 链、profile、未知选项、重复项、搭配冲突，一次列清 |
| 想「补帧 + 超分」一起上 | **进阶模式 → 补帧脚本 → 多脚本融合** | 按「反交错 → 降噪 → 超分 → 补帧」合成一个 `.vpy`，原脚本不动，生成前先做语法检查 |
| 想自己裸写 | **地狱模式** | 一个文本框，不拦你；写入前仍留一份 `.bak` |

**这个工具不会做什么**（免得你误会）：

- 它**不播放视频**，只管把配置写对。
- 它默认**不改你的 `mpv.conf` 内容**，只是加一行 `include` 指向自己生成的文件（想卸载就删文件 + 删那行）。
- 它**不联网**（除了你自己去点下载链接），配置分析全在本地做。
- 它**不打包 mpv 或任何第三方文件**，下载链接都指向官方发布页。

---

## 附：三份最小可用配置

**核显笔记本（省电优先）**

```ini
vo=gpu-next
hwdec=auto-safe
video-sync=audio
scale=bilinear
cscale=bilinear
dscale=bilinear
```

**独显台式机（画质优先）**

```ini
vo=gpu-next
gpu-api=d3d11
hwdec=auto-safe
video-sync=display-resample
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=yes
deband-iterations=2
```

**加了 shader 与补帧（需要对应的文件真的存在）**

```ini
vo=gpu-next
hwdec=auto-safe
video-sync=display-resample
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
glsl-shaders="~~/shaders/FSRCNNX/FSRCNNX_x2_16_0_4_1.glsl;~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
vf=vapoursynth="~~/vs/MEMC_RIFE_NV.vpy"
```

> 最后一份别照抄 —— shader 文件名和 vpy 脚本名在每个版本里都不一样。
> 用「进阶模式 → 扫描与下载」看看你本机到底有哪些文件，再挑。

---

**相关文档**：`shader-guide.md`（画面怎么搭最锐）、`acknowledgments.md`（用到了谁的成果）。
**权威来源**：[mpv 官方手册](https://mpv.io/manual/master/) · [mpv_doc-CN 中文手册](https://github.com/hooke007/mpv_doc-CN) ·
[mpv-lazy / mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit)

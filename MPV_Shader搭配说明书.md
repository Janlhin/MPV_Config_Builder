# MPV 搭配说明书：最锐利画面组合 + 最强大补帧排序

> 参考：你给的 [hooke007 着色器页](https://hooke007.github.io/unofficial/mpv_shaders.html)（该页自述偏旧，已结合作者更新后的 [mpv_PlayKit Wiki](https://github.com/hooke007/mpv_PlayKit/wiki/4_GLSL)、[0_FAQ](https://github.com/hooke007/mpv_PlayKit/wiki/0_FAQ)、[3_K7sfunc](https://github.com/hooke007/mpv_PlayKit/wiki/3_K7sfunc)、[#313 超分+补帧顺序讨论](https://github.com/hooke007/mpv_PlayKit/discussions/313) 与 [mpv 官方手册](https://mpv.io/manual/master/) 整理）。
>
> 目标读者：**不想看代码也想会用的人**。所有配置都是"参考组合"，请用你实际显卡实测 `GPU Render Time` 和 `dropped frames`。

---

## 0. 先搞懂 3 件事（2 分钟版）

### ① 什么是"着色器 / Shader"？
就是让显卡在播放时对画面做"二次处理"的小程序。常见效果：
- 放大超分（把 720p 变得像 1080p/4K）
- 修复画面（去模糊、去噪、去振铃）
- 锐化描边（让线条、细节更清晰）

### ② 什么是"补帧 / MEMC"？
普通视频 24/30 帧，画面切换时会有卡顿感。补帧就是在两帧之间"凭空"画出中间帧，让 72/96/120Hz 的屏幕看起来更顺滑。
- **内置补帧**：mpv 自带，成本低，但只是"时间重采样"，不是真正的运动补偿。
- **外部 MEMC**：用 VapourSynth + MVTools / SVP / RIFE，才是真正"算出来的中间帧"，画质最好但最吃性能。

### ③ 为什么"排序"这么重要？
mpv 处理画面有固定流程：

```
视频源 → vf 滤镜链(超分/补帧) → mpv 缩放(scale/cscale/dscale) → 用户 shader(修复/锐化) → 输出
```

- 顺序不同，结果完全不同。
- 原则：**先修复/放大，再补帧；放大小瑕疵 → 瑕疵变大；最后才做锐化收尾**。

---

## 1. 最锐利的画面组合（直接抄）

### 1.1 只想要"锐"：先改这 6 个参数

```ini
vo=gpu-next
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=no            ; 最锐利就用 no；明显有色带再改 yes
```

| 参数 | 作用 | 怎么理解 |
|---|---|---|
| `vo=gpu-next` | 现代 GPU 渲染路径 | 让它能跑新 shader |
| `scale` | 亮度放大算法 | `ewa_lanczossharp` 是"锐利但不过头"的默认好手 |
| `cscale` | 色度放大算法 | 和 scale 一起选锐利款，减少彩边 |
| `dscale` | 缩小算法 | 播放 4K 压到 1080p 时用 `hermite`/`mitchell` 更干净 |
| `sigmoid-upscaling=yes` | 防高光过冲 | 默认开，锐化时不容易出现"白边" |
| `deband=no` | 去色带 | 去色带会轻微柔化画面，纯锐利就关掉 |

> 想再狠一点：`scale=ewa_lanczos4sharpest`，但必须配 `scale-antiring=0.6`，否则容易振铃（画面边缘出现一圈圈波纹）。

---

### 1.2 通用（非动画）锐利 shader 链

```ini
# mpv.conf
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=no

glsl-shaders="~~/shaders/CfL/KrigBilateral.glsl;\
~~/shaders/FSRCNNX/FSRCNNX_x2_16_0_4_1.glsl;\
~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
```

| 顺序 | Shader | 干什么 | 为什么放这里 |
|---|---|---|---|
| 1 | **KrigBilateral** | 高级色度还原（相当于强化版 `cscale`） | 先解决色度细节 |
| 2 | **FSRCNNX** | CNN 网络 2x 超分，画面锐利 | 放大后再锐化，省钱又干净 |
| 3 | **Adaptive_sharpen** | 最后一层自适应锐化 | 放在最后，只加强纹理不动线条边缘 |

> **RAVU 替代方案**（更轻更快）：
> ```ini
> glsl-shader="~~/shaders/RAISR/ravu_zoom_ar_r3.glsl"
> ```
> **SSim 系列**（只配 mpv 内置 scale/dscale，不要和上面混用）：
> ```ini
> glsl-shader="~~/shaders/SSim/SSimSuperRes_RT.glsl"
> glsl-shader="~~/shaders/SSim/SSimDownscaler_RT.glsl"
> ```

---

### 1.3 动画档：Anime4K v4 正确顺序（最容易抄错）

Anime4K 是一套"修复 + 放大"组合，**不能乱挂**。推荐大顺序：

```
Clamp → Restore → Upscale → (可选 AutoDownscalePre) → 第二次 Upscale → Adaptive_sharpen
```

```ini
glsl-shaders="~~/shaders/Anime4K/Anime4K_Clamp_Highlights.glsl;\
~~/shaders/Anime4K/Anime4K_Restore_CNN_M.glsl;\
~~/shaders/Anime4K/Anime4K_Upscale_CNN_x2_M.glsl;\
~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_S.glsl;\
~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
```

| 顺序 | 模块 | 一句话理解 |
|---|---|---|
| 1 | `Clamp_Highlights` | 先压住高光，防止后面过冲 |
| 2 | `Restore_CNN_M` | 修复线稿、去振铃 |
| 3 | `Upscale_CNN_x2_M` | 第一轮放大 |
| 3.5（可选） | `AutoDownscalePre_x2` | 只插在两个放大之间；不要单独放 |
| 4 | `Upscale_GAN_x2_S` | 第二轮放大（用 S/M 小号，因为放大后计算量约 4 倍） |
| 5 | `Adaptive_sharpen` | 最后收尾锐化 |

**重要规则：每个 Anime4K 文件只能挂一次；放大步骤优先用 S/M 版本；Clamp 放最前或最后都可以，但不要放中间乱插。**

---

## 2. 最强大的补帧排序（真正懂的人怎么排列）

### 2.1 先分清：你用的是哪一种"补帧"？

| 方案 | 成本 | 效果 | 适合谁 |
|---|---|---|---|
| mpv 内置 `interpolation=yes` | 低 | 平滑，但只是时间重采样，画面会"糊一点点" | 日常播放，谁都能用 |
| VapourSynth + **MVTools** | 中 | 运动补偿补帧，效果好 | 中端配置 |
| VapourSynth + **SVP** | 中高 | 商业级运动补偿 | 喜欢顺滑的人 |
| VapourSynth + **RIFE** | 很高 | AI 补帧，目前最强 | 高端显卡（NVIDIA 优先） |

### 2.2 内置补帧：最省事配置

```ini
video-sync=display-resample
interpolation=yes
tscale=oversample          ; 最锐
hr-seek-framedrop=no
```

**tscale 从"锐"到"糊"的官方顺序：**

```
oversample → linear → catmull_rom → mitchell → gaussian → bicubic
```

- `oversample`：**默认、最锐**，日常推荐。
- `catmull_rom`：更锐但容易振铃（出现波纹）。
- `mitchell`：最平滑，喜欢"丝滑感"用这个。

> ⚠️ `video-sync=display-resample` 和 G-Sync / FreeSync / VRR 会打架，如果开了防撕裂就二选一。

### 2.3 真正强大的 MEMC：完整链条顺序（重点）

最强排法不是"挂一个 shader"，而是一整条链：

```
① 视频源
② VS 滤镜：先降高度 → AI 超分 → 缩回显示器高度 → 补帧(MVT/SVP/RIFE)
③ mpv 缩放：scale/cscale/dscale
④ GPU shader：色度还原 → 放大/修复 → 最后锐化
⑤ 输出
```

> **核心原则：先超分、后补帧。**
> 理由：补帧会带来少量帧破损，如果放大放在补帧后面，破损会被放大。所以"超分 → 补帧 → 锐化"才是画质优先。

#### 示例：VapourSynth 合并脚本（超分 + 补帧）

```python
import k7sfunc as k7f
clip = video_in

# 超过 1080p 就不处理（省电）
ret = k7f.FMT_CTRL(clip, h_max=1080, h_ret=True)

# 先降到 720p，再 AI 超分回 1440p，最后补帧
clip = k7f.FMT_CTRL(clip, h_max=720, fmt_pix=1)
clip = k7f.UAI_NV_TRT(clip, model_pth="Zarxrax_DigitalFlim_SuperUltraCompact_x2_fp16_opset14.onnx",
                      fp16=True, st_eng=True)
clip = k7f.FMT_CTRL(clip, h_max=1440)            # 1440p 显示器
clip = k7f.MVT_MQ(clip, fps_in=container_fps)    # MVTools 补帧；也可换 RIFE_NV / RIFE_DML / SVP_PRO
clip.set_output()
```

对应 mpv.conf：

```ini
vf=vapoursynth="~~/vs/my_sr_memc.vpy"
video-sync=display-resample
interpolation=no          ; 外部已生成真实中间帧，不用内置补帧
hr-seek-framedrop=no
```

> 一次只开一个补帧方案。不要在 `interpolation=yes` 的同时又挂 RIFE，等于补两次帧，又糊又卡。

### 2.4 运行时一键切换（input.conf）

```ini
CTRL+1 change-list glsl-shaders set "~~/shaders/CfL/KrigBilateral.glsl;~~/shaders/FSRCNNX/FSRCNNX_x2_16_0_4_1.glsl;~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
CTRL+2 change-list glsl-shaders set "~~/shaders/Anime4K/Anime4K_Clamp_Highlights.glsl;~~/shaders/Anime4K/Anime4K_Restore_CNN_M.glsl;~~/shaders/Anime4K/Anime4K_Upscale_CNN_x2_M.glsl;~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_S.glsl"
CTRL+0 change-list glsl-shaders clr ""
!   vf toggle vapoursynth="~~/vs/MEMC_MVT_LQ.vpy"     ; mvtools 补帧
%   vf toggle vapoursynth="~~/vs/MEMC_RIFE_DML.vpy"   ; RIFE 补帧
```

---

## 3. 一张图：最省心排序表

| 目标 | 参数/Shaper 顺序 |
|---|---|
| 只看"最锐利" | `scale=ewa_lanczossharp` + `cscale=ewa_lanczossharp` + `dscale=hermite` + `sigmoid-upscaling=yes` + `deband=no` |
| 非动漫流媒体 | `KrigBilateral → FSRCNNX → Adaptive_sharpen` |
| 动漫 720p/1080p 升 2K/4K | `Anime4K Clamp → Restore → Upscale → AutoDownscalePre(可选) → Upscale → Adaptive_sharpen` |
| 只要内置补帧 | `video-sync=display-resample` + `interpolation=yes` + `tscale=oversample` |
| 最强外部补帧 | `VS: 降720 → AI超分 → 缩到显示器高度 → MVT/SVP/RIFE`，最后 GPU 层再锐化 |

---

## 4. 新手最容易踩的坑

1. **`glsl-shaders` 顺序不是随便排**：真正决定位置的，是每个 shader 内部的 `HOOK` 阶段（`LUMA → CHROMA → NATIVE → MAINPRESUB/MAIN → POSTKERNEL → SCALED → OUTPUT`）；`glsl-shaders` 只决定"同一阶段"的顺序。按 `Shift+i` → `2` 可以看到实际工作流程。
2. **Anime4K 每个文件只用一次**，不要一个 shader 挂两遍。
3. **TS 补帧一定要配 `video-sync=display-*`**，否则 `interpolation=yes` 静默失效。
4. **外部 MEMC 后不要再开内置 interpolation**，双重补帧会又糊又掉帧。
5. **锐化不要叠三层以上**。FSRCNNX 已经很锐，再来 Adaptive_sharpen 差不多够了，再叠容易"数码感"。
6. **补帧是性能大户**。RIFE 建议 NVIDIA RTX 2060 以上；MVTools 是性价比之选；内置补帧是保底方案。
7. **VRR/G-Sync 和 `display-resample` 冲突**，二选一。

---

## 5. 这套说明用在哪？

- 想在 [MPV Config Builder 2.0](mpv_config_builder.py) 里重现"最锐利组合"：打开程序的 **组合预设** 页，点击 **最锐利基础参数 / mpv-lazy 通用锐利 / mpv-lazy 动漫锐利 / mpv-lazy 最强动漫 / 内置补帧 / mpv-lazy RIFE 补帧** 一键套用。
- 程序会**自动锁定** `C:\Program Files\mpv-lazy\portable_config`，并读取该目录里真实存在的 `.glsl` / `.vpy`：
  * Shader / 锐化页只列出 mpv-lazy 里真有的 10 个着色器，勾选即用真实路径，不需要手动选文件
  * VS 补帧页只列出 mpv-lazy 里真有的 15 个 vpy，勾选后直接生成 `vf=vapoursynth="~~/vs/xxx.vpy"`，同一时间只允许启用一项
  * 启动时会读 mpv-lazy 当前的 `mpv.conf`，已经启用的项会自动勾上
- 保存方式：和以前一样用 **复制** 或 **另存为 mpv.conf**，程序不会自动改写 mpv-lazy 目录里的文件。
- 补帧进阶：装好 `vapoursynth` + `k7sfunc` 后，直接在 **VS 补帧** 页选一项（如 RIFE_NV）即可，配置行会自动生成。

> 提醒：所有评分/推荐都是启发式的。最终请用 mpv 的 `Shift+i` 看 `GPU Render Time` 和 `dropped frames`，以实际显卡为准。

---

## 6. 参考来源

- 用户给出的着色器页：<https://hooke007.github.io/unofficial/mpv_shaders.html>（偏旧，和下面 Wiki 配合看）
- hooke007/mpv_PlayKit Wiki 4_GLSL：<https://github.com/hooke007/mpv_PlayKit/wiki/4_GLSL>
- hooke007/mpv_PlayKit Wiki 0_FAQ：<https://github.com/hooke007/mpv_PlayKit/wiki/0_FAQ>
- hooke007/mpv_PlayKit Wiki 3_K7sfunc：<https://github.com/hooke007/mpv_PlayKit/wiki/3_K7sfunc>
- 超分 + 补帧顺序讨论 #313：<https://github.com/hooke007/mpv_PlayKit/discussions/313>
- RIFE 实时补帧讨论 #123：<https://github.com/hooke007/mpv_PlayKit/discussions/123>
- Anime4K 高级 GLSL 用法：<https://github.com/bloc97/Anime4K/blob/master/md/GLSL_Instructions_Advanced.md>
- mpv 官方手册：<https://mpv.io/manual/master/>
- 内置补帧入门：<https://salivity.github.io/mpv/article/how-do-i-enable-motion-interpolation-in-mpv>
- 自定义 GLSL 入门：<https://salivity.github.io/mpv/article/how-to-use-custom-glsl-shaders-in-mpv>

---

## 7. 致谢与免责

本文档与配套工具能写出来，主要靠这些人和项目（完整版见 `致谢与许可.md`）：

**项目与作者**
- **mpv / mpv-player 团队** —— 播放器本体与[官方手册](https://mpv.io/manual/master/)
- **hooke007** —— [mpv-lazy / mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit)：本文档里的着色器清单、渲染流程、脚本顺序、补帧方案，几乎都建立在这个项目之上

**着色器作者**
- bloc97（[Anime4K](https://github.com/bloc97/Anime4K)）
- igv（[FSRCNNX](https://github.com/igv/FSRCNNX)、KrigBilateral、SSim 系列）
- bjin（[mpv-prescalers](https://github.com/bjin/mpv-prescalers)：RAVU / NNEDI3）
- Artoriuz（[ArtCNN](https://github.com/Artoriuz/ArtCNN)）
- the-database（[AnimeJaNai](https://github.com/the-database/mpv-upscale-2x_animejanai)）
- iwalton3（[default-shader-pack](https://github.com/iwalton3/default-shader-pack)）

**补帧 / VapourSynth 生态**
- [VapourSynth](https://www.vapoursynth.com/) 团队、mvtools（dubhater）、vs-rife（AmusementClub）、
  [SVP](https://www.svp-team.com/)、[K7sfunc](https://github.com/hooke007/mpv_PlayKit/wiki/3_K7sfunc)（k7）

**社区**
- [Anime 字幕论坛](https://bbs.acgrip.com/) 以及所有分享 mpv 配置经验的朋友

> **免责**：本文档与配套工具均为非官方内容，与上述项目及其作者无隶属关系；
> 不包含、不重新分发任何第三方着色器或二进制文件，只提供官方来源链接与路径引用。
> 第三方资源的版权与许可归其原作者所有。

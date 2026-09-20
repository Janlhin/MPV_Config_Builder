# MPV 实机配置分析报告（只分析，未修改任何文件）

> 分析对象：
> 1. `C:\Users\Janlhin\Downloads\Archives\mpv-lazy`
> 2. `C:\Users\Janlhin\Downloads\Archives\mpv-Yaozhi`
> 3. `C:\Users\Janlhin\Downloads\Archives\mpv.net-DW v2024.01`
> 4. `C:\Program Files\mpv.net-DW v2.1.0`
>
> 说明：本报告仅对比现状和推荐组合，**没有改动任何 mpv.conf**。所有修改建议都是"建议"，实际用哪个组合请按你的显卡实测。

---

## 0. 推荐基线（所有配置通用）

```ini
# 渲染/解码
vo=gpu-next
gpu-api=d3d11              # Windows 推荐；也可保留现有 gpu-context
hwdec=auto-safe            # 或沿用 auto-copy / nvdec-copy

# 补帧（内置）
video-sync=display-resample
interpolation=yes          # 如果使用外部 MEMC，这里要改成 no
tscale=oversample          # 最锐；想更丝滑换 mitchell
hr-seek-framedrop=no

# 最锐利缩放
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=no                  # 出现明显色带再改 yes
```

**六维目标**：
- 锐度：`ewa_lanczossharp` + 后处理锐化（一层即可，不要叠三层）
- 流畅度：内置补帧 `oversample`；外部 MEMC 用 SVP/RIFE（最强）
- 色彩：`sigmoid-upscaling=yes` + `deband=no`（有色带再开 DeBand）

---

## 1. mpv-lazy（hooke007 懒人包）

**配置文件**：`mpv-lazy\portable_config\mpv.conf`

### 1.1 现状

| 项目 | 当前值 | 评价 |
|---|---|---|
| vo | `gpu-next` | ✅ 已是现代渲染路径 |
| hwdec | `auto-copy` | ✅ 保留即可 |
| video-sync | `display-resample` | ✅ |
| interpolation | `yes` | ✅ |
| tscale | 未设置（默认 oversample） | ✅ 等于推荐值 |
| hr-seek-framedrop | `no` | ✅ |
| scale | `bilinear` | ❌ 太模糊 |
| cscale | `bilinear` | ❌ 建议锐利款 |
| dscale | `bicubic` | ❌ 建议 `hermite` |
| sigmoid-upscaling | `no` | ❌ 建议 `yes` |
| correct-downscaling | `no` | ❌ 建议 `yes` |
| deband | 注释（默认关闭） | ⚠ 最锐利可关；有明显色带再开 |
| dither-depth | `no` | ⚠ 建议 `auto` 试效果 |
| Shader | 只有 `QCOM_SGEDS_ms_RT.glsl` | ⚠ 没有完整锐利/超分链 |

### 1.2 建议改动（最小集合）

```ini
# 把这几行改掉
scale=ewa_lanczossharp
cscale=ewa_lanczossharp        # 或保留 bilinear（该包没有 KrigBilateral 时）
dscale=hermite
sigmoid-upscaling=yes
correct-downscaling=yes
# deband=no                    # 默认即关，出现色带再取消注释
```

**通用锐利链**（该包已有文件）：

```ini
glsl-shaders="~~/shaders/FSRCNNX/FSRCNNX_x2_16_0_4_1.glsl;~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
```

**动漫链**（该包已有文件）：

```ini
glsl-shaders="~~/shaders/Anime4K/Anime4K_Restore_CNN_L.glsl;~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_M.glsl;~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
```

> ⚠ 该包 `shaders/` 下没有 KrigBilateral / RAVU，所以通用链以 FSRCNNX 为主，色度缩放直接靠 `cscale=ewa_lanczossharp`。

---

## 2. mpv-Yaozhi（杳知版）

**配置文件**：`mpv-Yaozhi\portable_config\mpv.conf`（很长，且用 profile 体系）

### 2.1 现状

| 项目 | 当前值 | 评价 |
|---|---|---|
| vo | `gpu-next` | ✅ |
| gpu-api | `d3d11` | ✅ |
| hwdec | `d3d11va` | ✅（硬解，性能好） |
| profile | `HQ` | ✅ 已含 `scale=ewa_lanczossharp`、`sigmoid=yes`、`deband=no` |
| scale（来自 HQ） | `ewa_lanczossharp` | ✅ |
| cscale（来自 HQ） | `bilinear` | ⚠ 可选锐利款或靠 KrigBilateral 覆盖 |
| dscale（来自 HQ） | `lanczos` | ⚠ 建议 `hermite` 或 `mitchell` |
| sigmoid-upscaling | `yes` | ✅ |
| correct-downscaling | `yes` | ✅ |
| linear-downscaling | `no` | ⚠ 若用 SSimDownscaler 需保持 no；否则可试 yes |
| 内置补帧 | 注释关闭 | ❌ 当前没有内置补帧 |
| VS 补帧脚本 | `yaozhi-rife.vpy`、`yaozhi-rife-nvidia-hq.vpy` 存在但未启用 | ⚠ 可启用 |
| Shader | 有大量 profile：`Anime4K`、`SSIM`、`FSRCNNX`、`ravu-zoom` 等 | 默认没启用 |

### 2.2 建议

**A. 想用内置补帧**（最简单）：

```ini
video-sync=display-resample
interpolation=yes
tscale=oversample
hr-seek-framedrop=no
```

或者直接启用它的内置配置组：

```ini
profile=Tscale
```

**B. 想用外部 RIFE 补帧**（最强，需要 VapourSynth + 显卡支持）：

```ini
vf=vapoursynth="~~/vs/yaozhi-rife-nvidia-hq.vpy"    # NVIDIA 显卡
# vf=vapoursynth="~~/vs/yaozhi-rife.vpy"            # 通用版
video-sync=display-resample
interpolation=no            # 外部已出真实中间帧，别双重补帧
hr-seek-framedrop=no
```

**C. 画面锐利链**（在它的 profile 体系里二选一，不要同时开）：

- 动画：`profile=Anime4K`（它已配好 `KrigBilateral → Restore_Soft → Clamp → SSimDownscaler`）
- 通用：`profile=ravu-zoom` 或 `profile=FSRCNNX`
- 低清动画：`profile=AnimeJaNai`

> 它的 `[Anime4K]` 组没有加 Adaptive_sharpen，但 KrigBilateral 已经足够锐；如果觉得不够，再加：
> ```ini
> glsl-shaders-append="~~/shaders/igv/adaptive-sharpen.glsl"
> ```

**D. 缩放微调**（HQ 组里改）：

```ini
dscale=hermite
# cscale=ewa_lanczossharp    # 或保持 bilinear，启用 KrigBilateral 后它会覆盖 cscale
```

---

## 3. mpv.net-DW v2024.01（Archive 版）

**配置文件**：`mpv.net-DW v2024.01\portable_config\mpv.conf`

### 3.1 现状

| 项目 | 当前值 | 评价 |
|---|---|---|
| vo | 未显式设置 | ⚠ 建议明确 `vo=gpu-next` |
| gpu-context | `d3d11` | ✅ |
| hwdec | `auto-copy` | ✅ |
| video-sync | `display-resample` | ✅ |
| interpolation | `yes` | ✅ |
| tscale | `oversample` | ✅ |
| hr-seek-framedrop | `no` | ✅ |
| scale/cscale/dscale | 未设置（走 mpv 默认） | ⚠ 建议显式配置 |
| shader | 全是注释 | ❌ 未启用锐利链 |
| 外部 MEMC | `vf=vapoursynth=~~/vs/MEMC_SVP_LQ.vpy` 被注释 | ⚠ 可选 |

### 3.2 建议

```ini
vo=gpu-next
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=no
```

**通用锐利链**（文件都在 `portable_config\shaders\` 下）：

```ini
glsl-shaders="~~/shaders/KrigBilateral.glsl;~~/shaders/FSRCNNX_x2_16_0_4_1.glsl;~~/shaders/adaptive_sharpen.glsl"
```

**动漫链**：

```ini
glsl-shaders="~~/shaders/Anime4K_Clamp_Highlights.glsl;~~/shaders/Anime4K_Restore_CNN_M.glsl;~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl;~~/shaders/Anime4K_Upscale_GAN_x2_S.glsl;~~/shaders/adaptive_sharpen.glsl"
```

> 它的 `portable_config\shaders\` 下已经有这些文件，路径直接可用，不用额外下载。

---

## 4. mpv.net-DW v2.1.0（已安装版）

**配置文件**：`C:\Program Files\mpv.net-DW v2.1.0\portable_config\mpv.conf`

### 4.1 现状

| 项目 | 当前值 | 评价 |
|---|---|---|
| vo | `gpu-next` | ✅ |
| gpu-context | `winvk` | ⚠ 无异常就保持；Windows 也可试 `d3d11` |
| hwdec | `nvdec-copy` | ✅（N 卡） |
| video-sync | `display-resample` | ✅ |
| interpolation | `yes` | ⚠ 与外部 VS 补帧可能冲突 |
| hr-seek-framedrop | `no` | ✅ |
| vf | `vapoursynth=~~/vs/SR_ESRGAN_SVP.vpy` | ✅ 已启用超分 + SVP 外部补帧 |
| glsl-shaders | `~~/shaders/Anime4K_Upscale_GAN_x2_M.glsl` | ⚠ 只有放大，没有完整链 |
| scale/cscale/dscale | 未设置 | ⚠ 建议配置 |

### 4.2 建议

**A. 先确认是否双重补帧**
`SR_ESRGAN_SVP.vpy` 如果已经输出目标帧率（SVP 补帧），那么：

```ini
interpolation=no            # 避免外部补帧 + 内置补帧双重处理
video-sync=display-resample # 仍然保留，让显示同步
```

如果测试觉得还是抖，再改回 `interpolation=yes`。

**B. 基础参数**

```ini
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=no
```

**C. 完整动漫链**（该版有 RT 版文件）：

```ini
glsl-shaders="~~/shaders/KrigBilateral.glsl;~~/shaders/Anime4K_Upscale_GAN_x2_M.glsl;~~/shaders/adaptive_sharpen_RT.glsl"
```

或者更完整的 Anime4K 顺序：

```ini
glsl-shaders="~~/shaders/Anime4K_Clamp_Highlights.glsl;~~/shaders/Anime4K_Restore_CNN_M.glsl;~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl;~~/shaders/Anime4K_Upscale_GAN_x2_S.glsl;~~/shaders/adaptive_sharpen_RT.glsl"
```

---

## 5. 四套配置优先级总结

| 目标 | 最优先改 | 其次 |
|---|---|---|
| mpv-lazy | scale/cscale/dscale + sigmoid | 加 FSRCNNX/Adaptive_sharpen 链 |
| mpv-Yaozhi | 启用 `profile=Tscale` 或 RIFE vpy | 按内容启用 `Anime4K`/`ravu-zoom` profile，调 dscale |
| mpv.net-DW 2024.01 | 显式 `vo=gpu-next` + 缩放参数 | 启用 KrigBilateral+FSRCNNX+adaptive_sharpen |
| mpv.net-DW v2.1.0 | 检查双重补帧（interpolation 改 no） | 补 KrigBilateral + adaptive_sharpen，基础缩放参数 |

---

## 6. 注意事项

1. **改之前先备份**：建议把 `mpv.conf` 复制成 `mpv.conf.bak`。
2. **Shader 不能全开**：锐化叠三层会出现"数码感"，超分和 Anime4K 二选一。
3. **外部 MEMC（SVP/RIFE）和内置 `interpolation=yes` 是互斥关系**：二选一，否则又糊又卡。
4. **`video-sync=display-resample` 与 G-Sync/FreeSync/VRR 冲突**：开了防撕裂就二选一。
5. **高分屏 / 4K60 视频**：FSRCNNX、Anime4K、RIFE 都可能吃不满 60fps，请用 `Shift+i` 看 `GPU Render Time` 和 `dropped frames` 实测。

# MPV Configuration Guide: Sharpest Picture Combination + Most Powerful Frame Interpolation Ranking

> Reference: The [hooke007 shaders page](https://hooke007.github.io/unofficial/mpv_shaders.html) you provided (this page is described as somewhat outdated and has been incorporated into the author's updated [mpv_PlayKit Wiki](https://github.com/hooke007/mpv_PlayKit/wiki/4_GLSL) and [0_FAQ](https://github.com/hooke007/mpv_PlayKit/wiki/0_FAQ), [3_K7sfunc](https://github.com/hooke007/mpv_PlayKit/wiki/3_K7sfunc), [#313 Discussion on Super-Resolution + Frame Interpolation Order](https://github.com/hooke007/mpv_PlayKit/discussions/313), and [mpv Official Manual](https://mpv.io/manual/master/)).

>
> Target audience: **People who want to use it without reading code**. All configurations are "reference combinations"; please test `GPU Render Time` and `dropped frames` with your actual graphics card.

---

## 0. First, Understand 3 Things (2-Minute Version)

### ① What is a "Shader"?
It's a small program that makes the graphics card perform "secondary processing" on the image during playback. Common effects include:
- Upscaling (making 720p look like 1080p/4K)
- Image restoration (deblurring, denoising, and removing ringing artifacts)
- Sharpening outlines (making lines and details clearer)

### ② What is "Frame Interpolation / MEMC"?
Standard videos run at 24/30 frames, which can cause a choppy feeling during scene transitions. Frame interpolation "invents" intermediate frames between two existing frames, making the display appear smoother on 72/96/120Hz screens.
- **Built-in Frame Interpolation**: Included with mpv, it is low-cost but merely performs "time resampling," not true motion compensation.

- **External MEMC**: Using VapourSynth + MVTools / SVP / RIFE is the only way to get truly "computed intermediate frames." It offers the best image quality but is the most performance-intensive.

### ③ Why is "sorting" so important?
mpv has a fixed process for handling video frames:

```
Video source → vf filter chain (super-resolution/frame interpolation) → mpv scaling (scale/cscale/dscale) → user shader (restoration/sharpening) → output
```

- A different order leads to a completely different result.
- Principle: **First repair/enlarge, then interpolate frames; enlarging minor flaws makes them bigger; only at the very end should you apply sharpening for the final touch.**

---

## 1. The Sharpest Image Combination (Copy Directly)

### 1.1 If You Only Want "Sharpness": First, Change These 6 Parameters

```ini
vo=gpu-next
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=no            ; For the sharpest result, use no; change to yes if noticeable banding occurs
```

| Parameter | Function | How to understand |
|---|---|---|
| `vo=gpu-next` | Modern GPU rendering path | Enables it to run new shaders |
| `scale` | Brightness Amplification Algorithm | `ewa_lanczossharp` is the default go-to for "sharp but not over the top" |
| `cscale` | Chroma Upscaling Algorithm | Select the sharp option along with scale to reduce color fringing |
| `dscale` | Scaling Algorithm | When downscaling 4K to 1080p, `hermite`/`mitchell` produce a cleaner result |
| `sigmoid-upscaling=yes` | Prevents highlight blowout | Enabled by default, which helps avoid "white fringing" when sharpening |
| `deband=no` | Remove banding | Removing banding will slightly soften the image; turn it off for pure sharpness |

> To be even more aggressive: `scale=ewa_lanczos4sharpest`, but it must be paired with `scale-antiring=0.6`, otherwise ringing artifacts (concentric ripples along the image edges) can easily occur.

---

### 1.2 General (non-animated) sharpness shader chain

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

| Order | Shader | What it does | Why it's placed here |
|---|---|---|---|
| 1 | **KrigBilateral** | Advanced chroma restoration (equivalent to an enhanced `cscale`) | Addresses chroma details first |
| 2 | **FSRCNNX** | CNN-based 2x super-resolution, sharpens the image | Sharpening after upscaling is efficient and clean |
| 3 | **Adaptive_sharpen** | Final adaptive sharpening layer | Placed last to enhance only textures without affecting line edges |

> **RAVU Alternative** (lighter and faster):
> ```ini
> glsl-shader="~~/shaders/RAISR/ravu_zoom_ar_r3.glsl"
> ```
> **SSim Series** (use only with mpv's built-in scale/dscale; do not mix with the above):
> ```ini
> glsl-shader="~~/shaders/SSim/SSimSuperRes_RT.glsl"
> glsl-shader="~~/shaders/SSim/SSimDownscaler_RT.glsl"
> ```

---

### 1.3 Animation Files: Correct Order for Anime4K v4 (Easiest to Get Wrong)

Anime4K is a "restoration + upscaling" combination that **must not be applied randomly**. The recommended overall order is:

```
Clamp → Restore → Upscale → (optional AutoDownscalePre) → Second Upscale → Adaptive_sharpen
```

```ini
glsl-shaders="~~/shaders/Anime4K/Anime4K_Clamp_Highlights.glsl;\
~~/shaders/Anime4K/Anime4K_Restore_CNN_M.glsl;\
~~/shaders/Anime4K/Anime4K_Upscale_CNN_x2_M.glsl;\
~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_S.glsl;\
~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
```

| Order | Module | One-sentence explanation |
|---|---|---|
| 1 | `Clamp_Highlights` | First, clamp the highlights to prevent overshooting later |
| 2 | `Restore_CNN_M` | Restore line art and remove ringing |
| 3 | `Upscale_CNN_x2_M` | First round of upscaling |
| 3.5 (optional) | `AutoDownscalePre_x2` | Insert only between the two upscaling steps; do not place it alone |
| 4 | `Upscale_GAN_x2_S` | Second round of upscaling (use the S/M smaller model, as the computational load becomes about 4 times greater after upscaling) |
| 5 | `Adaptive_sharpen` | Final sharpening touch-up |

**Important Rule: Each Anime4K file can only be applied once; for upscaling steps, prioritize the S/M version; Clamp can be placed at the very beginning or end, but do not insert it randomly in the middle.**

---

## 2. The Most Powerful Frame Interpolation Ordering (How Those Who Truly Know Arrange It)

### 2.1 First, Clarify: Which Type of "Frame Interpolation" Are You Using?

| Solution | Cost | Effect | Suitable for |
|---|---|---|---|
| mpv built-in `interpolation=yes` | Low | Smooth, but it's just time resampling, so the image will be "a little blurry" | Daily playback, works for anyone |
| VapourSynth + **MVTools** | Medium | Motion compensation frame interpolation, good results | Mid-range systems |
| VapourSynth + **SVP** | Medium-High | Commercial-grade motion compensation | People who like smoothness |
| VapourSynth + **RIFE** | Very High | AI frame interpolation, currently the best | High-end GPUs (NVIDIA preferred) |

### 2.2 Built-in Frame Interpolation: The Easiest Configuration

```ini
video-sync=display-resample
interpolation=yes
tscale=oversample          ; sharpest
hr-seek-framedrop=no
```

**tscale Official sequence from "sharp" to "blurred":**

```
oversample → linear → catmull_rom → mitchell → gaussian → bicubic
```

- `oversample`: **Default and sharpest**, recommended for daily use.
- `catmull_rom`: Sharper but prone to ringing (introduces ripples).
- `mitchell`: Smoothest; use this if you prefer a "silky" feel.

> ⚠️ `video-sync=display-resample` conflicts with G-Sync / FreeSync / VRR. If you have tearing prevention enabled, choose one or the other.

### 2.3 Truly Powerful MEMC: The Complete Chain Order (Key Point)

The optimal setup isn't just "slapping on a shader," but rather an entire chain:

```
① Video source
② VS filter: first reduce height → AI super-resolution → scale back to monitor height → frame interpolation (MVT/SVP/RIFE)
③ mpv scaling: scale/cscale/dscale
④ GPU shader: chroma restoration → upscaling/repair → final sharpening
⑤ Output
```

> **Core principle: Super-resolve first, then frame interpolate.**
> Reason: Frame interpolation introduces a small amount of frame damage. If upscaling is done after interpolation, this damage will be magnified. Therefore, "Super-resolve → Frame Interpolate → Sharpen" is the order that prioritizes image quality.

#### Example: VapourSynth combined script (Super-resolution + Frame Interpolation)

```python
import k7sfunc as k7f
clip = video_in

# Do not process if resolution exceeds 1080p (to save power)
ret = k7f.FMT_CTRL(clip, h_max=1080, h_ret=True)

# First downscale to 720p, then use AI to upscale back to 1440p, and finally perform frame interpolation
clip = k7f.FMT_CTRL(clip, h_max=720, fmt_pix=1)
clip = k7f.UAI_NV_TRT(clip, model_pth="Zarxrax_DigitalFlim_SuperUltraCompact_x2_fp16_opset14.onnx",
                      fp16=True, st_eng=True)
clip = k7f.FMT_CTRL(clip, h_max=1440)            # 1440p monitor
clip = k7f.MVT_MQ(clip, fps_in=container_fps)    # Frame interpolation with MVTools; can also be replaced with RIFE_NV / RIFE_DML / SVP_PRO
clip.set_output()
```

Corresponding mpv.conf:

```ini
vf=vapoursynth="~~/vs/my_sr_memc.vpy"
video-sync=display-resample
interpolation=no          ; External real intermediate frames have been generated, no need for built-in frame interpolation
hr-seek-framedrop=no
```

> Only enable one frame interpolation method at a time. Do not use RIFE while `interpolation=yes` is also enabled, as this performs interpolation twice, resulting in a blurry and laggy output.

### 2.4 Runtime One-Key Switching (input.conf)

```ini
CTRL+1 change-list glsl-shaders set "~~/shaders/CfL/KrigBilateral.glsl;~~/shaders/FSRCNNX/FSRCNNX_x2_16_0_4_1.glsl;~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
CTRL+2 change-list glsl-shaders set "~~/shaders/Anime4K/Anime4K_Clamp_Highlights.glsl;~~/shaders/Anime4K/Anime4K_Restore_CNN_M.glsl;~~/shaders/Anime4K/Anime4K_Upscale_CNN_x2_M.glsl;~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_S.glsl"
CTRL+0 change-list glsl-shaders clr ""
!   vf toggle vapoursynth="~~/vs/MEMC_MVT_LQ.vpy"     ; mvtools frame interpolation
%   vf toggle vapoursynth="~~/vs/MEMC_RIFE_DML.vpy"   ; RIFE frame interpolation
```

## 3. One Chart: The Most Effortless Sorting Table

| Target | Parameter/Shaper Sequence |
|---|---|
| Only "sharpest" | `scale=ewa_lanczossharp` + `cscale=ewa_lanczossharp` + `dscale=hermite` + `sigmoid-upscaling=yes` + `deband=no` |
| Non-anime streaming | `KrigBilateral → FSRCNNX → Adaptive_sharpen` |
| Anime 720p/1080p upscaled to 2K/4K | `Anime4K Clamp → Restore → Upscale → AutoDownscalePre(optional) → Upscale → Adaptive_sharpen` |
| Only built-in frame interpolation | `video-sync=display-resample` + `interpolation=yes` + `tscale=oversample` |
| Strongest external frame interpolation | `VS: Downscale to 720p → AI super-resolution → Scale to monitor height → MVT/SVP/RIFE`, then sharpen again at the GPU layer |

## 4. The Most Common Pitfalls for Beginners

1. **The order of `glsl-shaders` is not arbitrary**: What truly determines the position is the `HOOK` stage within each shader (`LUMA → CHROMA → NATIVE → MAINPRESUB/MAIN → POSTKERNEL → SCALED → OUTPUT`); `glsl-shaders` only determines the order "within the same stage". Press `Shift+i` → `2` to see the actual workflow.
2. **Anime4K should only be applied once per file**; do not attach the same shader twice.
3. **TS frame interpolation must be paired with `video-sync=display-*`**; otherwise, `interpolation=yes` will silently fail.
4. **Do not enable the built-in interpolation after using external MEMC**; double frame interpolation will result in blurriness and frame drops.

5. **Do not apply more than three layers of sharpening.** FSRCNNX is already very sharp; adding Adaptive_sharpen on top is generally sufficient. Applying more layers can easily result in a "digital" look.
6. **Frame interpolation is very performance-intensive.** RIFE is recommended for NVIDIA RTX 2060 or better; MVTools is a cost-effective choice; built-in frame interpolation is the fallback option.
7. **VRR/G-Sync conflicts with `display-resample`**, so choose one or the other.

## 5. Where is this documentation used?

- To reproduce the "sharpest combination" in MPV Config Builder: open the program's **Preset Combinations** page and click **Sharpest Base Parameters / mpv-lazy General Sharpening / mpv-lazy Anime Sharpening / mpv-lazy Strongest Anime / Built-in Frame Interpolation / mpv-lazy RIFE Frame Interpolation** to apply them with one click.
  (This text was originally written for the old Tkinter interface; that interface has been removed from the repository and archived in the `.git` history and outside the repo at
  `..\MPV_Config_Builder_legacy\`. The same page is also available in the new web interface.)
- The program will **automatically lock** `C:\Program Files\mpv-lazy\portable_config` and read the actual `.glsl` / `.vpy` files in that directory:

* Shader / The Sharpening page only lists the 10 shaders that actually exist in mpv-lazy. Check one to use it directly with the actual path, without manually selecting a file.
  * VS Frame Interpolation page only lists the 15 vpy scripts that actually exist in mpv-lazy. After checking one, it will directly generate `vf=vapoursynth="~~/vs/xxx.vpy"`. Only one can be enabled at a time.
  * On startup, it reads the current `mpv.conf` from mpv-lazy, and any already enabled options will be automatically checked.
- Saving: As before, use **Copy** or **Save As mpv.conf**. The program will not automatically overwrite the files in the mpv-lazy directory.
- Advanced Frame Interpolation: After installing `vapoursynth` + `k7sfunc`, simply select an option (e.g., RIFE_NV) on the **VS Frame Interpolation** page, and the configuration line will be generated automatically.

> Reminder: All ratings/recommendations are heuristic. Ultimately, please use `Shift+i` in mpv to check `GPU Render Time` and `dropped frames`, based on your actual graphics card.

---

## 6. References

- User-provided shader page: <https://hooke007.github.io/unofficial/mpv_shaders.html> (somewhat outdated; refer to it together with the Wiki below)
- hooke007/mpv_PlayKit Wiki 4_GLSL: <https://github.com/hooke007/mpv_PlayKit/wiki/4_GLSL>
- hooke007/mpv_PlayKit Wiki 0_FAQ: <https://github.com/hooke007/mpv_PlayKit/wiki/0_FAQ>
- hooke007/mpv_PlayKit Wiki 3_K7sfunc: <https://github.com/hooke007/mpv_PlayKit/wiki/3_K7sfunc>

- Super-resolution + Frame Interpolation Order Discussion #313: <https://github.com/hooke007/mpv_PlayKit/discussions/313>
- RIFE Real-time Frame Interpolation Discussion #123: <https://github.com/hooke007/mpv_PlayKit/discussions/123>
- Anime4K Advanced GLSL Usage: <https://github.com/bloc97/Anime4K/blob/master/md/GLSL_Instructions_Advanced.md>
- Official mpv Manual: <https://mpv.io/manual/master/>

- Introduction to built-in frame interpolation: <https://salivity.github.io/mpv/article/how-do-i-enable-motion-interpolation-in-mpv>
- Introduction to custom GLSL: <https://salivity.github.io/mpv/article/how-to-use-custom-glsl-shaders-in-mpv>

## 7. Acknowledgments and Disclaimer

This document and its accompanying tools were made possible mainly thanks to the following people and projects (see `Acknowledgments and License.md` for the full list):

**Projects and Authors**
- **mpv / mpv-player team** — the player itself and the [official manual](https://mpv.io/manual/master/)
- **hooke007** — [mpv-lazy / mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit): The shader list, rendering pipeline, script sequence, and frame interpolation solutions in this document are almost all built upon this project.

**Shader Authors**
- bloc97（[Anime4K](https://github.com/bloc97/Anime4K)）
- igv（[FSRCNNX](https://github.com/igv/FSRCNNX)、KrigBilateral、SSim series）
- bjin（[mpv-prescalers](https://github.com/bjin/mpv-prescalers)：RAVU / NNEDI3）
- Artoriuz（[ArtCNN](https://github.com/Artoriuz/ArtCNN)）
- the-database（[AnimeJaNai](https://github.com/the-database/mpv-upscale-2x_animejanai)）

- iwalton3（[default-shader-pack](https://github.com/iwalton3/default-shader-pack)）

**Frame Interpolation / VapourSynth Ecosystem**
- [VapourSynth](https://www.vapoursynth.com/) team, mvtools (dubhater), vs-rife (AmusementClub),
  [SVP](https://www.svp-team.com/), [K7sfunc](https://github.com/hooke007/mpv_PlayKit/wiki/3_K7sfunc) (k7)

**Community**
- [Anime Subtitle Forum](https://bbs.acgrip.com/) and all friends who share mpv configuration experiences

> **Disclaimer**: This document and its accompanying tools are unofficial content and are not affiliated with the aforementioned project or its authors;
> It does not include or redistribute any third-party shaders or binary files, only providing links and path references to official sources.
> The copyright and licenses for third-party resources belong to their respective original authors.

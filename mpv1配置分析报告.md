# mpv1.conf 配置分析报告

> 分析对象：`C:\Users\Janlhin\Desktop\mpv1.conf`
> 分析方式：MPV Config Builder 2.0 内置分析器 `analyze_config_text`
> 说明：**本次只做分析，没有修改任何文件。**

---

## 1. 基本概况

| 项目 | 结果 |
|---|---|
| 总行数 | 204 |
| 注释行 | 76 |
| 有效配置项 | 80 |
| 综合评分 | **82 / 100（高画质）** |
| GPU 负载等级 | **77 / 100（中等偏高）** |
| 文件性质 | 原始 mpv-lazy 配置（hooke007 预设） |

六维评分：

| 清晰度 | 锐度 | 流畅度 | 色彩/观感 | 稳定性 | GPU负载 |
|---|---|---|---|---|---|
| 100 | 78 | 70 | 50 | 90 | 77 |

> 提醒：评分为启发式，不代表实际 FPS。

---

## 2. 构建器能识别的关键项

| 参数 | 当前值 | 评价 |
|---|---|---|
| `vo` | `gpu-next` | ✅ 现代渲染路径 |
| `video-sync` | `display-resample` | ✅ |
| `interpolation` | `yes` | ✅ 已开启内置补帧 |
| `scale` | `bilinear` | ⚠ 偏软（lazy 默认，靠 QCOM shader 补锐度） |
| `cscale` | `bilinear` | ⚠ 同上 |
| `dscale` | `bicubic` | ⚠ 建议 `hermite` |
| `sigmoid-upscaling` | `no` | ⚠ 建议 `yes` |
| `correct-downscaling` | `no` | ⚠ 建议 `yes` |
| `hwdec` | `auto-copy` | ✅ 有效值（构建器预设列表里没收录，不代表错误） |
| `hr-seek-framedrop` | `no` | ✅ 补帧时正确 |
| `demuxer-max-bytes` | `1024MiB` | ✅ 有效值 |
| `volume` | `100  # 注意：...` | ⚠ 值后面跟了行内注释，分析器原样读取；mpv 会忽略注释，但构建器显示会带上注释 |
| `audio-file-auto` | `fuzzy` | ✅ |
| `sub-auto` | `fuzzy` | ✅ |
| `sub-font-size` | `44` | ✅ |

---

## 3. 发现的问题

### 3.1 真问题

1. **`interpolation=yes` 但没有设置 `tscale`**
   `#tscale = sphinx` 被注释掉了。内置补帧会用默认 `oversample`，但建议显式写一行：
   ```ini
   tscale = oversample      # 最锐
   # 或 tscale = mitchell   # 更平滑
   ```

2. **`scale/cscale = bilinear` 偏软**
   这是 mpv-lazy 的原生默认值（靠 `glsl-shaders-append=QCOM_SGEDS_ms_RT.glsl` 补锐度）。
   如果想让画面更锐，可改为：
   ```ini
   scale  = ewa_lanczossharp
   cscale = ewa_lanczossharp
   dscale = hermite
   sigmoid-upscaling = yes
   correct-downscaling = yes
   ```

3. **`dither-depth = no`**
   8bit/10bit 屏建议改 `auto`，能减少色带。

4. **`deband` 未启用**
   如果片源有明显色带，可以开 `deband=yes`；追求锐利则保持关闭。

### 3.2 不是问题的"误报"（分析器局限）

- **45 个"未识别选项"里绝大多数是标准 mpv 选项**，例如：
  `input-conf`、`include`、`use-filedir-conf`、`idle`、`keep-open`、`osd-*`、`sub-file-paths`、`sub-codepage`、`slang`、`screenshot-*`、`ytdl-raw-options-append` 等。
  它们完全有效，只是构建器的 `COMMON_OPTIONS` 收录不全，才被标成"未知"。**没有发现真正拼写错误。**
- **重复的 `include`（第 6、7 行）不是错误**：两条分别 include 了 `profiles.conf` 和 `script-opts.conf`，是两个不同文件。
- **`glsl-shaders-append` 被当成未知项**：它其实是 mpv 的合法列表追加选项，当前值 `QCOM/QCOM_SGEDS_ms_RT.glsl` 也是 mpv-lazy 里真实存在的文件。
- **`volume` 的值显示带行内注释**：分析器没有剥离 ` # ...`，实际 mpv 不受影响。

---

## 4. 结论

- 这份配置本身是**完整、正确、可用的 mpv-lazy 原始配置**，没有语法错误。
- 存在 1 个真实小问题：`interpolation=yes` 未显式设置 `tscale`。
- 4 个可优化点：`scale/cscale/dscale` 偏软、`sigmoid-upscaling=no`、`correct-downscaling=no`、`dither-depth=no`。
- 分析器对 mpv-lazy 这种"全量配置"会误报未收录选项，**不要按"未知 45 项"去改配置**。

---

## 5. 重要提醒（文件现状）

| 路径 | 内容 |
|---|---|
| `C:\Users\Janlhin\Desktop\mpv1.conf` | **原始 204 行 mpv-lazy 配置（本次分析对象）** |
| `C:\Program Files\mpv-lazy\portable_config\mpv.conf` | 已被构建器生成的 22 行配置覆盖（`vo/hwdec` + shader + `vf=vapoursynth="~~/vs/MEMC_RIFE_DML.vpy"`） |

也就是说：mpv-lazy 现在实际生效的是那份 22 行生成配置，桌面这份是原始备份。如果想把原始配置恢复回 mpv-lazy，把 `mpv1.conf` 复制成 `portable_config\mpv.conf` 即可（本次没有替你动它）。

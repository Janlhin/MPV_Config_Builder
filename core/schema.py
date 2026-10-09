"""纯数据与路径辅助：不依赖任何界面库。"""
import json
import os
import re
from pathlib import Path

from .paths import user_data_dir


APP_TITLE = "MPV Config Builder"
# 产品代数 —— **只给仓外归档的那个旧 Tkinter 界面用**，主界面不再显示它。
#
# 为什么还留着：那份旧界面（2026-10-09 移出仓库，归档在 ..\MPV_Config_Builder_legacy\）
# 有 4 处 import 并在标题里拼它 —— 它 import 的是**仓库里的** core.schema，
# 所以删了这个常数，那边会直接 ImportError。
# 为了一个显示用的常数去改一份"保留但不维护"的归档不值得，留着。
# 主界面（webui / electron）**不要用它** —— 见下面 FULL_TITLE 的说明。
# tests/test_version.py 有一条测试钉住"不许删"（归档这台机器上不在就跳过）。
APP_VERSION = "2.0"
# 软件版本号（打包 / Release / 更新检测用）。**主界面唯一的版本号来源。**
#
# 规则（2026-09-14 定）：
#     小更新（改文案、修 bug）  0.1.0 → 0.1.1 → 0.1.2
#     大更新（加功能）          0.1.x → 0.2.0 → 0.3.0
#     觉得能正式推荐给别人了     0.x   → 1.0.0
#
# ⚠ 改这里之后要跑一次 `py tools/build.py version`，
#   把版本刷进 electron/package.json（那边打包时要用）。
#   tests/test_version.py 有一条测试钉住两边相等，忘了会红。
VERSION = "0.1.0"
#: 打包工具（PyInstaller / setuptools）习惯认这个名字
__version__ = VERSION
#: 标题栏 / 关于页 / 生成的配置抬头统一用这个。
#
# 2026-09-14：**去掉了「2.0」**。原来这里拼的是 "MPV Config Builder 2.0"，
# 于是界面上同时出现两个版本号（顶栏 v0.1.0、标题 MPV Config Builder 2.0），
# 用户会以为装了两个东西。用户决定只留软件版本。
#
# ⚠ 生成配置的抬头因此从 `# MPV Config Builder 2.0` 变成了 `# MPV Config Builder`。
#   合并写入**不受影响** —— 它认的是 writer.MERGE_MARKER（「由 MPV Config Builder 写入」），
#   跟这条抬头无关。
FULL_TITLE = APP_TITLE
TITLE = FULL_TITLE                      # 旧名字，保留兼容

SETTINGS_PATH = user_data_dir() / "settings.json"


def load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# 资源导航：外部网站链接（只打开浏览器，不下载任何文件）
RESOURCE_LINKS = {
    "播放器本体": [
        ("mpv-lazy 仓库（hooke007 / mpv_PlayKit）", "https://github.com/hooke007/mpv_PlayKit"),
        ("mpv-lazy 下载页（Releases）", "https://github.com/hooke007/mpv_PlayKit/releases"),
        ("MPV_lazy 仓库", "https://github.com/hooke007/MPV_lazy"),
        ("mpv 官网", "https://mpv.io/"),
        ("mpv Windows 构建下载", "https://sourceforge.net/projects/mpv-player-windows/files/"),
        ("mpv.net 官方仓库", "https://github.com/mpvnet-player/mpv.net"),
        ("mpv.net 官网", "https://mpvnet.com/"),
    ],
    "着色器库（GLSL）": [
        ("hooke007 第三方着色器页", "https://hooke007.github.io/unofficial/mpv_shaders.html"),
        ("mpv_PlayKit Wiki · 4_GLSL（用户着色器）", "https://github.com/hooke007/mpv_PlayKit/wiki/4_GLSL"),
        ("Anime4K", "https://github.com/bloc97/Anime4K"),
        ("FSRCNNX", "https://github.com/igv/FSRCNNX"),
        ("mpv-prescalers（RAVU / NNEDI3）", "https://github.com/bjin/mpv-prescalers"),
        ("ArtCNN", "https://github.com/Artoriuz/ArtCNN"),
        ("AnimeJaNai（AI 超分）", "https://github.com/the-database/mpv-upscale-2x_animejanai"),
        ("default-shader-pack（着色器合集）", "https://github.com/iwalton3/default-shader-pack"),
    ],
    "VS 补帧 / 插件": [
        ("mpv_PlayKit Wiki · 3_K7sfunc（VS 脚本封装）", "https://github.com/hooke007/mpv_PlayKit/wiki/3_K7sfunc"),
        ("VapourSynth 官网", "https://www.vapoursynth.com/"),
        ("VapourSynth 下载", "https://github.com/vapoursynth/vapoursynth/releases"),
        ("mvtools（MVTools 补帧）", "https://github.com/dubhater/vapoursynth-mvtools"),
        ("vs-rife（RIFE 补帧）", "https://github.com/AmusementClub/vs-rife"),
        ("SVP（商业补帧）", "https://www.svp-team.com/"),
    ],
    "文档 / 参考": [
        ("mpv 官方手册", "https://mpv.io/manual/master/"),
        ("mpv_PlayKit Wiki · 0_FAQ", "https://github.com/hooke007/mpv_PlayKit/wiki/0_FAQ"),
        ("mpv_PlayKit 讨论区", "https://github.com/hooke007/mpv_PlayKit/discussions"),
    ],
}

# key: (Chinese name, description, options, scoring metadata)
PARAMS = {
    "视频输出": [
        ("vo", "视频输出", "选择 MPV 视频输出驱动。gpu-next 是现代 GPU 渲染路径。", ["gpu-next","gpu","null"], 2, 1),
        ("gpu-api", "GPU API", "选择图形 API。Windows 常用 d3d11；部分环境可使用 Vulkan。", ["d3d11","vulkan","opengl"], 1, 0),
        ("hwdec", "硬件解码", "让 GPU/专用视频解码器承担 H.264/HEVC/AV1 等解码工作。", ["auto-safe","auto","d3d11va","nvdec","no"], 2, -1),
        ("video-sync", "视频同步", "控制视频时钟与音频/显示器的同步方式。display-resample 常用于高刷新率显示。", ["display-resample","audio","display-resample-vdrop"], 2, 1),
    ],
    "缩放": [
        ("scale", "亮度缩放", "控制主图像/亮度平面的空间缩放算法。影响放大后的锐度、细节与 GPU 负载。", ["bilinear","bicubic","spline36","hermite","lanczos","jinc","ewa_lanczos","ewa_lanczossharp","ewa_lanczos4sharpest","sinc"], 5, 5),
        ("cscale", "色度缩放", "控制色度平面的缩放算法。高质量算法可以减少彩边和色度细节损失。", ["bilinear","bicubic","spline36","hermite","ewa_lanczos","ewa_lanczossharp","ewa_lanczos4sharpest"], 4, 4),
        ("dscale", "降采样", "输入分辨率高于目标分辨率时使用的缩小算法。", ["bilinear","mitchell","hermite","spline36","catmull_rom","oversample"], 3, 3),
        ("sigmoid-upscaling", "Sigmoid Upscaling", "缓解高质量锐利缩放在边缘产生的过冲观感。", ["yes","no"], 2, 1),
        ("deband", "Deband", "减少渐变区域的色带现象，代价是额外 GPU 运算。", ["yes","no"], 3, 2),
        ("linear-downscaling", "线性缩小", "缩小画面时使用线性滤波，默认开启。", ["yes","no"], 0, 0),
        ("correct-downscaling", "校正缩小", "缩小过程校正伽马/色彩，默认开启。", ["yes","no"], 0, 0),
    ],
    "补帧": [
        ("interpolation", "插值播放", "在原始帧之间计算中间画面，使 24/30 FPS 内容在高刷新率显示器上运动更连续。不是 AI 补帧。", ["yes","no"], 5, 4),
        ("tscale", "时间缩放算法", "插值模式下用于时间方向重采样的算法。不同算法在平滑度、拖影和负载之间取舍。", ["oversample","linear","box","triangle","catmull_rom","mitchell","gaussian","bicubic"], 4, 4),
        ("hr-seek-framedrop", "跳转丢帧", "补帧时建议 no，避免跳转/拖进度条后出现时间错位。", ["no","yes"], 0, 0),
    ],
    "字幕": [
        ("sub-auto", "自动字幕", "控制字幕文件自动加载方式。", ["fuzzy","exact","no"], 1, 0),
        ("sub-font-size", "字幕字号", "ASS 以外字幕的默认字号，可按观看距离调整。", ["32","36","40","44","48","52","56"], 0, 0),
        ("sub-ass-override", "ASS 覆盖", "决定是否覆盖 ASS/SSA 字幕原始样式。no 最忠实于原字幕设计。", ["no","yes","strip"], 1, 0),
    ],
    # 「字幕样式」这几项从原生层提上来了：它们是调字幕观感时最常动的，
    # 而且下面挂了个实时预览（见 webui/static/state.js 的 updateSubPreview）——
    # 预览要有东西可显示，这些得在进阶模式里就能改。
    "字幕样式": [
        ("sub-font", "字幕字体", "字幕用的字体名。装了字体还要在 mpv.conf 里写明字体名才会用上。"
                                "纯文本字幕直接生效；ASS 字幕默认不吃这项（见 sub-ass-override）。",
         ["sans-serif", "LXGW WenKai Lite", "Noto Sans CJK SC"], 0, 0),
        ("sub-color", "字幕颜色", "字幕文字颜色。写 6 位的 #RRGGBB（不透明），"
                                "或 8 位的 #AARRGGBB —— ⚠ 8 位时透明度在**最前**两位，"
                                "FF 不透明、00 全透明（跟 CSS 的习惯相反）。"
                                "嫌绕就直接用 6 位写法。",
         ["#FFFFFF", "#FFD766", "#FFE08A"], 0, 0),
        ("sub-border-size", "字幕描边粗细", "文字外圈描边的宽度，0 = 不描边。深色画面上的白字描一圈黑边会清楚很多。",
         ["0", "1", "2", "3"], 0, 0),
        ("sub-border-color", "描边颜色", "描边颜色，写法同 sub-color（8 位时透明度在最前）。常见是黑色。",
         ["#000000", "#101010"], 0, 0),
        ("sub-shadow-offset", "字幕阴影偏移", "阴影相对文字的偏移量。0 = 不要阴影（想要更干净的字幕就填 0）。",
         ["0", "1", "2", "3"], 0, 0),
        ("sub-shadow-color", "阴影颜色", "阴影颜色，写法同 sub-color。不想要阴影就把 sub-shadow-offset 设为 0。",
         ["#000000", "#101010"], 0, 0),
        ("sub-back-color", "字幕背景框", "字幕后面的底色块。想要半透明黑框写 #80000000"
                                       "（前两位 80 = 约 50% 不透明）；不想要背景框写 #00000000。",
         ["#00000000", "#80000000", "#FF000000"], 0, 0),
        ("sub-pos", "字幕垂直位置", "字幕距画面底部的百分比。100 = 最底部，90 会往上抬一点"
                                  "（有些片子底部有硬字幕或画面信息）。",
         ["90", "95", "100"], 0, 0),
        # 这里不放 sub-margin-x：它只影响左右边距，预览里看不出来，留在完全体
    ],
    "音频": [
        ("audio-exclusive", "独占模式", "音频设备独占输出。实际效果取决于操作系统、设备和 MPV 构建。", ["yes","no"], 1, 0),
        ("audio-file-auto", "自动加载音频", "控制外部音轨自动加载策略。", ["exact","fuzzy","no"], 1, 0),
        ("volume", "默认音量", "MPV 启动时的默认音量。", ["80","100","120"], 0, 0),
    ],
    "窗口": [
        ("geometry", "窗口开启位置", "控制 mpv 打开时的窗口位置或大小。50%:50% = 屏幕居中；+0+0 = 左上角；-0-0 = 右下角；也可自定义，例如 1280x720+100+100。", ["50%:50%","+0+0","-0-0","+100+100","-100-100","1280x720","1280x720+100+100"], 0, 0),
        ("autofit", "初始窗口大小", "打开时的初始窗口尺寸，可写像素或百分比。", ["no","1280x720","1600x900","1920x1080","100%x100%"], 0, 0),
        ("autofit-larger", "最大窗口限制", "窗口模式下允许的最大尺寸（像素或屏幕百分比），用来限制窗口不要开得太大。", ["100%x100%","90%x90%","85%x85%","80%x80%","1280x720","1600x900","1920x1080"], 1, 0),
        ("autofit-smaller", "最小窗口限制", "窗口模式下允许的最小尺寸（像素或屏幕百分比），避免窗口缩得太小。", ["30%x20%","40%x30%","50%x50%","640x360","800x450","960x540"], 0, 0),
        ("keepaspect-window", "锁定窗口比例", "窗口比例是否锁定为视频比例。no = 允许自由拉伸窗口。", ["yes","no"], 0, 0),
        ("hidpi-window-scale", "HiDPI 窗口缩放", "是否按系统 DPI 缩放窗口大小。4K 屏觉得窗口太大时可以设 no。", ["yes","no"], 0, 0),
    ],
    "性能 / 缓存": [
        ("cache", "文件缓存", "启用文件缓存，网络/慢速存储场景通常更有意义。", ["yes","no"], 1, 0),
        ("demuxer-max-bytes", "Demuxer 最大缓存", "限制 demuxer 缓冲数据量。不是越大越好，主要用于特定网络/大码率场景。", ["200MiB","500MiB","1GiB"], 1, 1),
    ],
}

# 这些参数的输入框允许手动输入自定义值（不限于下拉列表）
EDITABLE_PARAMS = {"geometry"}

SHADERS = {
    "KrigBilateral / CfL": ("高级色度还原（覆盖 cscale），配合超分/锐化使用，减少彩边。", 6, 3),
    "FSRCNNX x2_8": ("通用 CNN 2x 超分，8 通道，速度较快。", 7, 5),
    "FSRCNNX x2_16": ("通用 CNN 2x 超分，16 通道，更锐更慢（mpv-lazy 默认 Ctrl+3）。", 8, 6),
    "FSRCNNX LineArt_x2_8": ("针对动画线稿的 2x 超分版本。", 8, 6),
    "RAVU r2": ("RAVU 轻量快速超分档。", 6, 3),
    "RAVU r3 zoom-ar": ("RAVU 中间档，可配合 ar/zoom 一路放大到目标分辨率。", 7, 5),
    "RAVU r4": ("RAVU 高质量档。", 8, 6),
    "Adaptive_sharpen": ("最后一步自适应锐化（lite_RT 更省），推荐放链尾（mpv-lazy 默认 Ctrl+0）。", 5, 4),
    "AMD_CAS": ("AMD 对比度自适应锐化，轻量收尾。", 4, 3),
    "Anime4K Clamp_Highlights": ("压住高光防过冲，Anime4K 链第一或最后使用。", 2, 1),
    "Anime4K Restore_CNN_M": ("修复线稿、去振铃/修复压缩瑕疵。", 6, 5),
    "Anime4K Upscale_CNN_x2_M": ("Anime4K 第一轮卷积放大。", 8, 6),
    "Anime4K Upscale_GAN_x2_S": ("Anime4K 第二轮 GAN 放大，S 档省性能。", 9, 7),
    "Anime4K Denoise_CNN_M": ("Anime4K 去噪/平滑色带。", 4, 4),
    "Anime4K Deblur_DoG": ("Anime4K 去模糊/描边锐化。", 6, 4),
    "Anime4K AutoDownscalePre_x2": ("两轮放大之间插入的自适应预缩放，不要单独使用。", 3, 3),
    "SSimSuperRes_RT": ("配合 mpv 内置 scale 的超分增强，不要和外部超分混用。", 7, 5),
    "SSimDownscaler_RT": ("配合 mpv 内置 dscale 的缩小增强。", 5, 4),
    # ---- 以下为 mpv-lazy 实际自带的着色器（路径已按 C:\\Program Files\\mpv-lazy 对齐）----
    "Anime4K Restore_CNN_L": ("Anime4K 线稿修复 L 档，mpv-lazy 自带（Ctrl+5）。", 7, 6),
    "Anime4K Upscale_GAN_x2_M": ("Anime4K GAN 放大 M 档，mpv-lazy 自带（Ctrl+6）。", 9, 7),
    "QCOM SGEDS": ("QCOM 主缩放锐化 RT，mpv-lazy 默认追加（Ctrl+9）。", 6, 5),
    "Ani4Kv2 ArtCNN": ("Ani4Kv2 ArtCNN（LUMA 阶段），动画超分，负载高（Ctrl+1）。", 9, 9),
    "AniSD ArtCNN": ("AniSD ArtCNN，SD 动画专用超分，负载很高（Ctrl+2）。", 9, 10),
    "NNEDI3 nns64": ("NNEDI3 nns64 插值放大，通用型（Ctrl+4）。", 7, 6),
    "k7 Anime ESRGAN": ("k7 Anime ESRGAN 超分，动画向，负载高（Ctrl+7）。", 9, 9),
    "k7 Anime DT ESRGAN": ("k7 Anime DT ESRGAN，细节更强、负载更高（Ctrl+8）。", 9, 10),
}

# 各个 Shader 的预设路径（可点“选择文件”改成自己的实际路径）
SHADER_PATHS = {
    "KrigBilateral / CfL": "~~/shaders/CfL/KrigBilateral.glsl",
    "FSRCNNX x2_8": "~~/shaders/FSRCNNX/FSRCNNX_x2_8_0_4_1.glsl",
    "FSRCNNX x2_16": "~~/shaders/FSRCNNX/FSRCNNX_x2_16_0_4_1.glsl",
    "FSRCNNX LineArt_x2_8": "~~/shaders/FSRCNNX/FSRCNNX_LineArt_x2_8.glsl",
    "RAVU r2": "~~/shaders/RAISR/ravu-r2.glsl",
    "RAVU r3 zoom-ar": "~~/shaders/RAISR/ravu_zoom_ar_r3.glsl",
    "RAVU r4": "~~/shaders/RAISR/ravu-r4.glsl",
    "Adaptive_sharpen": "~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl",
    "AMD_CAS": "~~/shaders/AMD_CAS/AMD_CAS.glsl",
    "Anime4K Clamp_Highlights": "~~/shaders/Anime4K/Anime4K_Clamp_Highlights.glsl",
    "Anime4K Restore_CNN_M": "~~/shaders/Anime4K/Anime4K_Restore_CNN_M.glsl",
    "Anime4K Upscale_CNN_x2_M": "~~/shaders/Anime4K/Anime4K_Upscale_CNN_x2_M.glsl",
    "Anime4K Upscale_GAN_x2_S": "~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_S.glsl",
    "Anime4K Denoise_CNN_M": "~~/shaders/Anime4K/Anime4K_Denoise_CNN_M.glsl",
    "Anime4K Deblur_DoG": "~~/shaders/Anime4K/Anime4K_Deblur_DoG.glsl",
    "Anime4K AutoDownscalePre_x2": "~~/shaders/Anime4K/Anime4K_AutoDownscalePre_x2.glsl",
    "SSimSuperRes_RT": "~~/shaders/SSim/SSimSuperRes_RT.glsl",
    "SSimDownscaler_RT": "~~/shaders/SSim/SSimDownscaler_RT.glsl",
    # ---- mpv-lazy 实际路径 ----
    "Anime4K Restore_CNN_L": "~~/shaders/Anime4K/Anime4K_Restore_CNN_L.glsl",
    "Anime4K Upscale_GAN_x2_M": "~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_M.glsl",
    "QCOM SGEDS": "~~/shaders/QCOM/QCOM_SGEDS_ms_RT.glsl",
    "Ani4Kv2 ArtCNN": "~~/shaders/Ani/Ani4Kv2_ArtCNN_C4F32_i2_dx.glsl",
    "AniSD ArtCNN": "~~/shaders/Ani/AniSD_ArtCNN_C4F32_i4_dx.glsl",
    "NNEDI3 nns64": "~~/shaders/EDI/nnedi3_nns64_win8x4.glsl",
    "k7 Anime ESRGAN": "~~/shaders/ESRGAN/k7_modernAnime_FHD_x2.glsl",
    "k7 Anime DT ESRGAN": "~~/shaders/ESRGAN/k7_modernAnime_DT_FHD_x2.glsl",
}

# 外部 VapourSynth 补帧（MEMC）模板；需要自装 vapoursynth + k7sfunc 才有实际效果
MEMC_PRESETS = {
    "MVT_LQ": ("MVTools 低质量档，性价比高，中端显卡可试（mpv-lazy 默认 !）。", "~~/vs/MEMC_MVT_LQ.vpy"),
    "MVT_MQ": ("MVTools 中质量档，画质/性能均衡。", "~~/vs/MEMC_MVT_MQ.vpy"),
    "SVP_LQ": ("SVP 低档，商业级运动补偿。", "~~/vs/MEMC_SVP_LQ.vpy"),
    "SVP_HQ": ("SVP 高档，更顺滑。", "~~/vs/MEMC_SVP_HQ.vpy"),
    "SVP_PRO": ("SVP PRO 档。", "~~/vs/MEMC_SVP_PRO.vpy"),
    "DRBA_DML": ("DRBA DirectML 补帧（无 NVIDIA 也可用，mpv-lazy 默认 SHARP 键）。", "~~/vs/MEMC_DRBA_DML.vpy"),
    "DRBA_NV": ("DRBA NVIDIA 补帧（mpv-lazy 默认 %）。", "~~/vs/MEMC_DRBA_NV.vpy"),
    "RIFE_STD": ("RIFE 标准版。", "~~/vs/MEMC_RIFE_STD.vpy"),
    "RIFE_DML": ("RIFE DirectML（mpv-lazy 默认 @）。", "~~/vs/MEMC_RIFE_DML.vpy"),
    "RIFE_NV": ("RIFE NVIDIA，目前最强补帧之一（RTX 2060 以上推荐，mpv-lazy 默认 $）。", "~~/vs/MEMC_RIFE_NV.vpy"),
    # ---- mpv-lazy 实际自带的 VS 脚本 ----
    "MIX_UAI_DML": ("UAI AI 超分（DX12），对应快捷键 ^。", "~~/vs/MIX_UAI_DML.vpy"),
    "MIX_UAI_NV_TRT": ("UAI AI 超分（RTX TensorRT），对应快捷键 &。", "~~/vs/MIX_UAI_NV_TRT.vpy"),
    "MIX_UAI_MIGX": ("UAI AI 超分（MIGX）。", "~~/vs/MIX_UAI_MIGX.vpy"),
    "MIX_UVR_MAD": ("UVR 人声/伴奏分离。", "~~/vs/MIX_UVR_MAD.vpy"),
    "SR_ARTCNN_NV": ("ArtCNN 超分（RTX）。", "~~/vs/SR_ARTCNN_NV.vpy"),
    "NR_BM3D_NV": ("BM3D 降噪（RTX）。", "~~/vs/NR_BM3D_NV.vpy"),
    "NR_CCD_STD": ("CCD 降噪。", "~~/vs/NR_CCD_STD.vpy"),
    "ETC_DEINT_EX": ("反交错（用于隔行源）。", "~~/vs/ETC_DEINT_EX.vpy"),
}

# 最锐利基础参数（供快捷组合复用）
BASE_SHARP = {
    "vo": "gpu-next", "gpu-api": "d3d11", "hwdec": "auto-safe",
    "video-sync": "display-resample",
    "scale": "ewa_lanczossharp", "cscale": "ewa_lanczossharp",
    "dscale": "hermite", "sigmoid-upscaling": "yes", "deband": "no",
    "linear-downscaling": "yes", "correct-downscaling": "yes", "cache": "yes",
}

# ---------- 播放器目录扫描 ----------

SHADER_EXTS = {".glsl", ".hook", ".slang", ".spv"}
VS_EXTS = {".vpy"}

# mpv / mpv-lazy 配置目录的候选来源。顺序即优先级：
#   1. 用户上次选过的（settings.json，模型里记住的）
#   2. 程序/工具同目录的 portable_config
#   3. %APPDATA%\mpv（原版 mpv 的默认配置目录）
#   4. %LOCALAPPDATA%\mpv-lazy（一键安装的默认落点）
#   5. 几个常见的手工安装位置（Program Files 等）
# 注意：这里**不能出现某个具体用户的绝对路径** —— 装到 D:\mpv-lazy 的用户
# 也必须能被找到（以前只认写死的 4 条路径，等于只有作者自己的机器能用）。
COMMON_MPV_INSTALL_DIRS = [
    r"C:\Program Files\mpv-lazy",
    r"C:\Program Files (x86)\mpv-lazy",
    r"C:\Program Files\mpv",
    r"C:\Program Files (x86)\mpv",
    r"C:\mpv",
    r"D:\mpv-lazy",
    r"D:\mpv",
    r"E:\mpv-lazy",
    r"E:\mpv",
]


def _dedup_paths(paths):
    """去重（大小写不敏感，Windows 路径）并保持顺序。"""
    seen, out = set(), []
    for p in paths:
        if p is None:
            continue
        key = str(p).rstrip("\\/").lower()
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out


def candidate_dirs():
    """按优先级列出所有候选配置目录（存在的放前面，不存在的也返回供界面展示）。

    返回 [{"path": str, "source": 中文说明, "exists": bool}, ...]
    """
    import os
    home = Path.home()
    appdata = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
    localappdata = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")

    remembered = (load_settings() or {}).get("target")
    entries = []
    if remembered:
        entries.append((str(remembered), "上次使用的目录"))
    # 工具自己所在的目录（便携版常把 mpv 和工具放一起）
    entries.append((str(Path(__file__).resolve().parent.parent / "portable_config"),
                    "程序同目录"))
    entries.append((str(Path(appdata) / "mpv"), "%APPDATA%\\mpv"))
    entries.append((str(Path(localappdata) / "mpv-lazy" / "portable_config"),
                    "一键安装默认位置"))
    entries.append((str(Path(localappdata) / "mpv-lazy"), "一键安装默认位置"))
    for d in COMMON_MPV_INSTALL_DIRS:
        entries.append((d, "常见安装位置"))

    out, seen = [], set()
    for path, source in entries:
        key = str(path).rstrip("\\/").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        p = Path(path)
        out.append({"path": str(p), "source": source, "exists": p.is_dir()})
    return out


# 兼容旧接口：一串候选目录路径（存在的优先）
LAZY_CANDIDATE_DIRS = _dedup_paths(
    [e["path"] for e in candidate_dirs() if e["exists"]]
    + [e["path"] for e in candidate_dirs()]
)

# 列表排序优先级（数字越小越靠前）
SHADER_PRIORITY = {
    "FSRCNNX x2_16": 10,
    "Adaptive_sharpen": 20,
    "QCOM SGEDS": 30,
    "Anime4K Restore_CNN_L": 40,
    "Anime4K Upscale_GAN_x2_M": 50,
    "Ani4Kv2 ArtCNN": 60,
    "AniSD ArtCNN": 70,
    "NNEDI3 nns64": 80,
    "k7 Anime ESRGAN": 90,
    "k7 Anime DT ESRGAN": 100,
}

MEMC_PRIORITY = {
    "MVT_LQ": 10,
    "RIFE_NV": 20,
    "RIFE_DML": 30,
    "DRBA_NV": 40,
    "DRBA_DML": 50,
    "RIFE_STD": 60,
    "SVP_PRO": 70,
    "MIX_UAI_NV_TRT": 80,
    "MIX_UAI_DML": 90,
    "MIX_UAI_MIGX": 100,
    "SR_ARTCNN_NV": 110,
    "NR_BM3D_NV": 120,
    "NR_CCD_STD": 130,
    "ETC_DEINT_EX": 140,
}

# 分组顺序（让同一类目在列表里连在一起，不交叉重复出现）
SHADER_GROUP_ORDER = {
    "通用超分": 0,
    "动漫超分 / 修复": 1,
    "锐化": 2,
    "色度还原": 3,
    "其它": 4,
}

MEMC_GROUP_ORDER = {
    "补帧（MEMC）": 0,
    "超分": 1,
    "降噪": 2,
    "音频 / 其它": 3,
    "其它": 4,
}


def looks_like_config_dir(p):
    """这个目录像不像 mpv 的配置目录。"""
    p = Path(p)
    if not p.is_dir():
        return False
    if (p / "mpv.conf").is_file():
        return True
    for sub in ("shaders", "vs", "scripts", "script-opts", "fonts", "watch_later"):
        if (p / sub).is_dir():
            return True
    # 上游发的懒人包常多套一层目录
    return any((p / name).is_file() for name in ("mpv.exe", "mpv.com"))


def find_lazy_pc():
    """返回 mpv / mpv-lazy 的配置目录；找不到返回 None。

    候选顺序见 candidate_dirs()（上次使用 → 程序同目录 → %APPDATA%\\mpv →
    一键安装默认位置 → 常见安装位置）。`portable_config` 与裸目录都认。
    """
    for entry in candidate_dirs():
        p = Path(entry["path"])
        if looks_like_config_dir(p):
            return p
        # 传进来的可能是播放器根目录，配置在 portable_config 下
        nested = p / "portable_config"
        if looks_like_config_dir(nested):
            return nested
    return None


def scan_lazy(pc):
    """扫描 mpv-lazy 的 portable_config，返回 (shader 文件列表, vpy 文件列表)。"""
    shaders, vpy = [], []
    if pc is None:
        return shaders, vpy
    pc = Path(pc)
    shader_root = pc / "shaders"
    vs_root = pc / "vs"
    if shader_root.is_dir():
        for p in sorted(shader_root.rglob("*")):
            if p.is_file() and p.suffix.lower() in SHADER_EXTS:
                shaders.append(p)
    if vs_root.is_dir():
        for p in sorted(vs_root.rglob("*")):
            if p.is_file() and p.suffix.lower() in VS_EXTS:
                vpy.append(p)
    return shaders, vpy


def norm_mpv_path(p):
    """把 ~~/ 或绝对路径统一成小写相对路径，便于比较。"""
    s = str(p).strip().strip('"').strip("'").replace("\\", "/")
    if s.startswith("~~/"):
        s = s[3:]
    elif s.startswith("~~"):
        s = s[2:].lstrip("/")
    return s.lower()


def split_mpv_list(value):
    """拆分 mpv 列表值（支持 ; 和 :，但保护 Windows 盘符）。"""
    v = str(value).strip().strip('"').strip("'")
    if ";" in v:
        parts = v.split(";")
    elif ":" in v and not re.search(r"[A-Za-z]:[\\/]", v):
        parts = v.split(":")
    else:
        parts = [v]
    return [x.strip() for x in parts if x.strip()]


def extract_vapoursynth_path(value):
    """从 vf 值里取 vapoursynth= 后面的脚本路径。"""
    v = str(value).strip().strip('"').strip("'")
    idx = v.find("vapoursynth=")
    if idx >= 0:
        v = v[idx + len("vapoursynth="):]
    return v.strip().strip('"').strip("'")


def strip_inline_comment(s):
    """按 mpv 的规则去掉行尾注释。

    手册原文：「在 # 之后的所有内容都被认为是注释」，而且「只需要引用选项值以转义值的
    任意位置的 #」—— 也就是说 **没加引号的 # 一律当注释**，
    连 `sub-color=#FFD766` 这种颜色值都会被截断。这里照做。
    """
    quote = ""
    i = 0
    while i < len(s):
        ch = s[i]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return s[:i].strip()
        i += 1
    return s.strip()


def value_truncated_by_hash(raw):
    """这一行的**值**是不是被「没加引号的 #」截掉了。

    必须和"这一行有没有 #"区分开 —— 后者会把注释里出现 # 的正常行也算进去：

        sub-color=#FFD766              → 值被吃了，剩空串 → True（要警告）
        sub-color="#FFD766"  # 注释     → 值完好，只是尾部有注释 → False
        sub-color="#FFD766"  # #RRGGBB  → 同样是 False
        vo=gpu-next                    → 压根没 # → False

    判定办法：找第一个「引号外」的 `#`，看它前面有没有内容。

        `sub-color=#FFD766`            → # 前面没东西 → 值被吃了 → True
        `sub-color="#FFD766"  # 注释`   → # 前面有值（已闭合的引号）→ False
        `sub-color="#FFD766"  # #RRGGBB` → 同上 → False
        `sub-color=` / `sub-color=  # x` → 本来就是空值，没东西可丢 → False
        `vo=gpu-next`                  → 压根没 # → False

    已知的边缘取舍：`sub-color=  # 说明`（等号后直接跟注释）会返回 True。
    严格按 mpv 规则，这一行的值确实被 # 吃掉了，所以报出来不算错 ——
    只是它和"用户压根没填值"在结果上一样。这个取舍写在这里，
    免得下次有人看到又改回去。
    """
    s = str(raw).strip()
    # 空值行（`sub-color=` 或 `sub-color=  # 说明`）：没有值可以丢，不算截断。
    # 注意不能写成 `s.startswith("#")` —— `#FFD766` 也以 # 开头，但那是**值本身**。
    if not s or not s.lstrip("#").strip():
        return False
    quote = ""
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            # 第一个「引号外」的 # 出现在这里：
            #  · `#FFD766`            → i=0，前面什么都没有 → 值被吃了 → True
            #  · `"#FFD766"  # 注释`  → # 前面有已闭合的引号 → 值没丢 → False
            #  · `  # 说明`（空值）    → 前面只有空白，但整串只有注释 → 已在上面的守卫里返回
            return not s[:i].strip()
    return False


def value_had_unquoted_hash(raw):
    """这一行的值里是不是有「没加引号的 #」（会被 mpv 当注释截掉）。"""
    s = str(raw)
    quote = ""
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return True
    return False


def needs_quotes(value):
    """值里有没有必须加引号才能原样传给 mpv 的字符。"""
    v = str(value)
    if v != v.strip():
        return True                     # 前导/尾随空格
    if any(ch in v for ch in "#\"'%") and not (v.startswith('"') and v.endswith('"')):
        return True
    return False


# 值本身是「分号分隔的列表」的选项：整串要加引号
LIST_OPTION_KEYS = frozenset({
    "glsl-shaders", "glsl-shader", "glsl-shaders-append", "glsl-shader-append",
    "sub-file-paths", "audio-file-paths", "watch-later-options",
})


def format_option_value(key, value):
    """把值格式化成能安全写进 mpv.conf 的样子（该加引号就加）。

    **这是全项目唯一的选项格式化入口** —— builder（生成）与 writer（合并写回）
    都必须走这里。历史上 merge 路径用裸 f"{key} = {value}"，导致
    `sub-color = #FFD766` 被 mpv 当注释截成空值，而本工具自己的体检还会警告用户
    这个坑 —— 工具自己犯自己警告的错。
    """
    v = str(value).strip()
    if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        return v                        # 已经带引号，别套两层
    if key in LIST_OPTION_KEYS or needs_quotes(v):
        return f'"{v}"'
    return v


def format_option_line(key, value):
    """`key = value` 一行（值按 format_option_value 处理）。"""
    return f"{key} = {format_option_value(key, value)}"


def build_shader_catalog(pc):
    """按目标目录实际存在的文件生成 Shader 列表；pc 为 None 时退回通用模板列表。"""
    catalog = []
    used = set()
    for name, meta in SHADERS.items():
        path = SHADER_PATHS.get(name, "")
        if pc is not None:
            if not path:
                continue
            rel = norm_mpv_path(path)
            if not (Path(pc) / rel).is_file():
                continue
            used.add(rel)
        catalog.append({"name": name, "desc": meta[0], "q": meta[1], "load": meta[2], "path": path})
    if pc is not None:
        for p in scan_lazy(pc)[0]:
            rel = p.relative_to(Path(pc)).as_posix()
            if rel.lower() in used:
                continue
            catalog.append({
                "name": p.stem,
                "desc": f"自动发现（mpv-lazy 实际文件）：{rel}",
                "q": 4, "load": 4, "path": "~~/" + rel,
            })
    catalog.sort(key=lambda x: (SHADER_GROUP_ORDER.get(shader_group(x["name"]), 9),
                                SHADER_PRIORITY.get(x["name"], 500), x["name"]))
    return catalog


def build_memc_catalog(pc):
    """按目标目录实际存在的 vpy 生成补帧/滤镜列表；pc 为 None 时退回通用模板列表。"""
    catalog = []
    used = set()
    for name, (desc, path) in MEMC_PRESETS.items():
        if pc is not None:
            rel = norm_mpv_path(path)
            if not (Path(pc) / rel).is_file():
                continue
            used.add(rel)
        catalog.append({"name": name, "desc": desc, "path": path})
    if pc is not None:
        for p in scan_lazy(pc)[1]:
            rel = p.relative_to(Path(pc)).as_posix()
            if rel.lower() in used:
                continue
            catalog.append({"name": p.stem, "desc": f"自动发现（mpv-lazy 实际文件）：{rel}", "path": "~~/" + rel})
    catalog.sort(key=lambda x: (MEMC_GROUP_ORDER.get(memc_group(x["name"]), 9),
                                MEMC_PRIORITY.get(x["name"], 500), x["name"]))
    return catalog


def norm_id(name):
    """把名字归一化，便于跨写法匹配：去掉空格 / 下划线 / 连字符 / 点，全部小写。"""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def find_named(want, names):
    """在候选名字里找 want：先精确，再归一化相等，最后包含匹配。

    这一步是为了让「预设里写的漂亮名字」和「磁盘上真实文件名」能对上：
        Anime4K Restore_CNN_M  ↔  Anime4K_Restore_CNN_M.glsl
    """
    names = list(names)
    if want in names:
        return want
    nw = norm_id(want)
    if not nw:
        return None
    for n in names:
        if norm_id(n) == nw:
            return n
    for n in names:
        nn = norm_id(n)
        if nn and (nw in nn or nn in nw):
            return n
    return None


def shader_group(name):
    if name.startswith(("Anime4K", "Ani4Kv2", "AniSD", "k7 Anime")):
        return "动漫超分 / 修复"
    if name.startswith(("FSRCNNX", "RAVU", "NNEDI3")):
        return "通用超分"
    if name in ("Adaptive_sharpen", "AMD_CAS"):
        return "锐化"
    if name in ("KrigBilateral / CfL",):
        return "色度还原"
    return "其它"


def memc_group(name):
    if name.startswith("MEMC_") or name in ("MVT_LQ", "MVT_MQ", "SVP_LQ", "SVP_HQ", "SVP_PRO",
                                            "DRBA_DML", "DRBA_NV", "RIFE_STD", "RIFE_DML", "RIFE_NV"):
        return "补帧（MEMC）"
    if name.startswith(("SR_", "MIX_UAI")):
        return "超分"
    if name.startswith("NR_"):
        return "降噪"
    if name.startswith("MIX_UVR"):
        return "音频 / 其它"
    return "其它"

# 常见但构建器未提供界面的标准 mpv 配置项（用于分析时区分“未收录”和“疑似错误”）
COMMON_OPTIONS = {
    # 窗口 / 界面
    "profile", "load-scripts", "script-opts", "input-ipc-server", "keep-open",
    "force-window", "idle", "ontop", "fullscreen", "border", "geometry",
    "panscan", "snap-window", "terminal", "quiet", "msg-level",
    "osc", "osd-bar", "osd-on-seek", "osd-level", "osd-font", "osd-font-size",
    "screenshot-format", "screenshot-directory", "screenshot-template",
    "input-default-bindings", "input-ar-auto-align", "input-cursor",
    # 字幕 / 音频
    "alang", "slang", "aid", "sid", "vid", "sub-delay", "sub-pos",
    "sub-margin-x", "sub-margin-y", "sub-scale", "sub-font", "sub-text-font",
    "sub-text-size", "sub-text-color", "sub-text-border-size", "sub-text-shadow-offset",
    "sub-text-blur", "sub-use-margins", "sub-forced-only", "sub-codepage",
    "sub-fuzzy", "sub-filter-fuzziness", "sub-file-paths", "audio-file-paths",
    "audio-files", "external-file", "audio-delay", "audio-channels",
    "audio-format", "audio-exclusive", "audio-file-auto", "volume", "mute",
    "softvol", "volume-max",
    "ao", "audio-device", "audio-client-name", "audio-pitch-correction", "muted",
    # 显示 / 缩放 / 字幕渲染
    "keepaspect", "keepaspect-window", "video-output-levels", "aspect", "alpha",
    "display-fps", "fps", "framedrop", "video-latency-hacks", "vd-lavc-framedrop",
    "icc-profile", "icc-profile-auto", "icc-cache", "icc-intent", "icc-contrast",
    "blend-subtitles", "sub-ass-scale", "sub-scale-with-window", "sub-stretch-durations",
    # 缓存 / 渲染 API
    "demuxer-cache-wait", "demuxer-cache-secs", "cache-pause", "cache-pause-initial",
    "cache-pause-wait", "opengl-backend", "d3d11-adapter", "d3d11-feature-level",
    "d3d11-warp", "vulkan-async-compute",
    # 缓存 / 网络 / 播放
    "cache", "cache-dir", "cache-secs", "demuxer-max-bytes", "demuxer-readahead-secs",
    "network-timeout", "ytdl", "ytdl-format", "loop-file", "loop-playlist",
    "save-position-on-quit", "watch-later-options", "ab-loop-a", "ab-loop-b",
    # 渲染 / 着色器
    "vd-lavc-dr", "hwdec-codecs", "hwdec-preloaded", "vd-lavc-software-fallback",
    "scale-antiring", "cscale-antiring", "sigmoid-center", "sigmoid-slope",
    "target-peak", "hdr-compute-peak", "tone-mapping", "tone-mapping-mode",
    "gamut-mapping", "video-rotate", "video-unscaled", "video-aspect",
    "deinterlace", "interlace", "field-dominance", "af", "vf", "lavfi-complex",
    "shader", "glsl-shaders", "user-shaders", "glsl-shader-option",
    "glsl-shader-reload", "gpu-api", "gpu-debug", "gpu-dither", "gpu-hdr",
}

SHADER_OPTION_KEYS = {"shader", "glsl-shaders", "user-shaders", "glsl-shader-option", "glsl-shader-reload"}

def get_param_meta(key):
    for items in PARAMS.values():
        for item in items:
            if item[0] == key:
                return item
    return None




# ============================================================
# 原生 mpv 选项扩展（完全体）
# 结构：(key, 中文名, 类型, 建议值列表, 说明)
# 类型：bool / enum / int / float / str / color / list
# ============================================================

NATIVE_OPTIONS = {
    "画质细节": [
        ("dither-depth", "抖动色深", "enum", ["auto", "8", "10", "no"], "8bit 屏填 8，10bit 填 10；auto 不一定准。"),
        ("dither", "抖动算法", "enum", ["fruit", "ordered", "error-diffusion", "no"], "error-diffusion 效果最好也最耗性能。"),
        ("temporal-dither", "时域抖动", "bool", ["yes", "no"], "逐帧变化抖动图案，可能让 LCD 闪烁。"),
        ("temporal-dither-period", "时域抖动周期", "int", ["1", "2", "4"], "每隔多少帧换一次抖动图案。"),
        ("scale-antiring", "放大抗振铃", "float", ["0", "0.5", "0.6", "0.8", "1.0"], "越高越能压住振铃，但会引入其它伪影。"),
        ("cscale-antiring", "色度抗振铃", "float", ["0", "0.5", "0.6", "0.8", "1.0"], "色度平面抗振铃强度。"),
        ("dscale-antiring", "缩小抗振铃", "float", ["0", "0.5", "0.6", "0.8", "1.0"], "缩小算法抗振铃强度。"),
        ("scaler-resizes-only", "仅缩放时处理", "bool", ["yes", "no"], "no = 不缩放也用指定算法处理，可修正某些 shader 的半像素偏移。"),
        ("deband-iterations", "去色带次数", "int", ["1", "2", "3", "4"], "越高越强也越慢，>4 基本无效。"),
        ("deband-threshold", "去色带阈值", "int", ["32", "48", "64", "128"], "越高强度越大，细节损失也越多。"),
        ("deband-range", "去色带半径", "int", ["8", "16", "32", "64"], "半径越大越强、性能开销越高。"),
        ("deband-grain", "去色带噪点", "int", ["16", "32", "48", "64"], "加回一点噪点掩盖残留色带。"),
        ("interpolation-preserve", "保留插值结果", "bool", ["yes", "no"], "改渲染参数时是否保留上一帧插值，no 响应更快。"),
        ("video-sync-max-video-change", "同步最大变速", "float", ["1", "5", "10"], "display-resample 下允许的音视频变速上限（%）。"),
        ("tscale-clamp", "时域抗振铃", "float", ["0", "0.5", "1.0"], "1.0 完全去除负权重，减少时域振铃。"),
        ("tscale-antiring", "时域抗振铃强度", "float", ["0", "0.5", "1.0"], "插值时抑制振铃的强度。"),
    ],
    "色彩 / HDR": [
        ("icc-profile-auto", "自动 ICC", "bool", ["yes", "no"], "有校色文件的屏幕可以开；和 target-* 系列不要同时用。"),
        ("icc-profile", "指定 ICC 文件", "str", [], "手动指定 .icc/.icm 路径（留空表示不用）。"),
        ("icc-intent", "ICC 映射意图", "enum", ["0", "1", "2", "3"], "0 感知 / 1 相对色度 / 2 饱和 / 3 绝对色度。"),
        ("target-prim", "目标色域", "enum", ["auto", "bt.709", "srgb", "display-p3", "dci-p3", "adobe", "bt.2020"], "广色域屏填对应值可避免过饱和；Win11 开了 ACM 就别改。"),
        ("target-trc", "目标伽马", "enum", ["auto", "bt.1886", "gamma2.2", "srgb", "pq", "hlg"], "非 OLED 且非 HDR 建议 gamma2.2，避免画面偏暗。"),
        ("target-gamut", "限制输出色域", "enum", ["auto", "bt.709", "display-p3", "dci-p3", "adobe", "bt.2020"], "把输出色域限制在显示器能力范围内。"),
        ("target-peak", "屏幕峰值亮度", "str", ["auto", "203", "100", "600", "1000"], "HDR 屏填实测 nits；SDR 模式保持 203。"),
        ("target-contrast", "屏幕对比度", "str", ["auto", "inf", "1000", "100000"], "OLED 可填 inf 或 1000000。"),
        ("target-colorspace-hint", "输出色彩空间提示", "enum", ["auto", "yes", "no"], "HDR 直通相关；Win 下需手动切系统 HDR。"),
        ("tone-mapping", "色调映射算法", "enum", ["auto", "clip", "mobius", "reinhard", "hable", "bt.2390", "gamma", "spline", "bt.2446a"], "gpu-next 下常用 spline / bt.2446a / hable。"),
        ("hdr-compute-peak", "动态峰值检测", "enum", ["auto", "yes", "no"], "逐场景测峰值，画面更准但可能亮度跳动。"),
        ("gamut-mapping-mode", "色域映射模式", "enum", ["auto", "clip", "perceptual", "relative", "saturation", "absolute", "linear", "warn", "desaturate", "darken"], "常用 clip 或 perceptual。"),
        ("inverse-tone-mapping", "反向映射 SDR→HDR", "bool", ["yes", "no"], "仅 HDR 设备有效，谨慎使用。"),
        ("hdr-contrast-recovery", "HDR 对比度恢复", "float", ["0", "0.3", "0.5", "1.0"], "增强色调映射后的对比度，过高会过锐。"),
    ],
    "字幕明细": [
        ("slang", "优先字幕语言", "str", ["chs,sc,zh-cn,chi,zho,zh", "jpn,eng"], "逗号分隔的优先级列表。"),
        ("sub-file-paths", "字幕搜索目录", "list", ["sub;subs;subtitles"], "分号分隔；Windows 下用 ; 而不是 :。"),
        ("sub-codepage", "字幕编码", "str", ["auto", "utf-8", "gb18030", "big5"], "中文老字幕常见 gb18030。"),
        # sub-font / sub-color / sub-border-* / sub-shadow-offset / sub-back-color / sub-pos
        # 已提到核心层的「字幕样式」组（那里挂着实时预览）。别再往这里加回来 ——
        # tests/test_schema.py 有一条「核心层与原生层不许重叠」的测试守着。
        ("sub-use-margins", "字幕占黑边", "bool", ["yes", "no"], "no = 尽量把字幕压进画面内。"),
        ("sub-ass-force-margins", "ASS 强制黑边", "bool", ["yes", "no"], "可能破坏部分 ASS 的定位。"),
        ("sub-scale-with-window", "按窗口缩放字幕", "bool", ["yes", "no"], "仅影响纯文本字幕。"),
        ("subs-fallback", "字幕回退", "enum", ["yes", "default", "no"], "找不到匹配语言时的回退策略。"),
        ("blend-subtitles", "字幕参与渲染", "enum", ["no", "yes", "video"], "yes 后字幕会受 shader / 缩放影响。"),
        ("secondary-sub-ass-override", "次字幕样式覆盖", "bool", ["yes", "no"], "次字幕是否套用 sub-* 样式。"),
        ("sub-hdr-peak", "HDR 字幕亮度", "str", ["sdr", "100", "203"], "HDR 输出下字幕/OSD 的参考白。"),
        ("sub-margin-x", "字幕水平边距", "int", ["25", "35", "45"], "按缩放后的像素计。"),
    ],
    "音频明细": [
        ("audio-device", "音频设备", "str", ["auto", "wasapi"], "固定设备可填 wasapi/{GUID}。"),
        ("audio-channels", "声道布局", "enum", ["auto-safe", "auto", "stereo", "5.1", "7.1"], "系统无法确定布局时用 auto-safe。"),
        ("volume-max", "最大音量", "int", ["100", "130", "150"], "音量上限，130 约为 100 的两倍响度。"),
        ("audio-pitch-correction", "变速保持音调", "bool", ["yes", "no"], "变速播放时是否修正音调。"),
        ("replaygain", "重播增益", "enum", ["no", "track", "album"], "按文件元数据调整音量。"),
        ("gapless-audio", "无缝衔接", "enum", ["no", "weak", "yes"], "yes 可能降低音质，建议 weak。"),
        ("audio-delay", "音频延迟", "float", ["0", "0.04", "-0.04"], "音画不同步时微调（秒）。"),
        ("alang", "优先音轨语言", "str", ["jpn,eng", "chi,zho,zh"], "逗号分隔的优先级列表。"),
        ("audio-file-paths", "外挂音轨目录", "list", ["audio;audios;音轨"], "分号分隔。"),
        ("ao", "音频输出驱动", "str", ["wasapi", "sdl", "auto"], "Windows 首选 wasapi。"),
    ],
    "行为 / 界面": [
        ("keep-open", "播完保持窗口", "enum", ["no", "yes", "always"], "always = 播完暂停且不播下一个。"),
        ("idle", "空闲待机", "enum", ["no", "yes", "once"], "yes = 播完不退出，保留窗口。"),
        ("save-position-on-quit", "退出记住进度", "bool", ["yes", "no"], "下次打开同名文件继续播放。"),
        ("watch-later-options", "进度保存白名单", "list", ["start,vid,aid,sid"], "逗号分隔，限制哪些状态被保存。"),
        ("osc", "内置控制器", "bool", ["yes", "no"], "用第三方界面（uosc）时关掉。"),
        ("osd-bar", "OSD 进度条", "bool", ["yes", "no"], "是否显示底部进度条。"),
        ("osd-font-size", "OSD 字号", "float", ["24", "34", "40", "48"], "全局 OSD 文本大小。"),
        ("osd-duration", "OSD 停留时间", "int", ["1000", "2000", "3000"], "毫秒。"),
        ("osd-on-seek", "跳转提示", "enum", ["no", "bar", "msg", "msg-bar"], "拖动进度条时显示什么。"),
        ("osd-playing-msg", "开始播放提示", "str", ["${filename}"], "支持 mpv 属性展开。"),
        ("fullscreen", "启动全屏", "bool", ["yes", "no"], "打开即全屏。"),
        ("ontop", "窗口置顶", "bool", ["yes", "no"], "始终在最前。"),
        ("border", "窗口边框", "bool", ["yes", "no"], "no = 无边框窗口。"),
        ("title-bar", "标题栏", "bool", ["yes", "no"], "无边框时是否保留标题栏。"),
        ("input-default-bindings", "内置快捷键", "bool", ["yes", "no"], "no = 禁用 mpv 默认按键。"),
        ("input-conf", "快捷键文件", "str", ["~~/input.conf"], "指定 input.conf 路径。"),
        ("load-scripts", "加载脚本", "bool", ["yes", "no"], "是否自动加载 scripts 目录。"),
    ],
    "截图 / 其它": [
        ("screenshot-format", "截图格式", "enum", ["jpg", "png", "webp", "jxl", "avif"], "严谨对比用 png。"),
        ("screenshot-directory", "截图目录", "str", ["~~desktop/"], "留空 = 当前目录。"),
        ("screenshot-template", "截图命名", "str", ["%{media-title}-%P-%n"], "支持属性展开。"),
        ("screenshot-jpeg-quality", "JPEG 质量", "int", ["90", "95", "100"], "0-100。"),
        ("screenshot-png-compression", "PNG 压缩", "int", ["4", "6", "7", "9"], "越高越慢，7 为默认。"),
        ("screenshot-webp-lossless", "WebP 无损", "bool", ["yes", "no"], "yes = 无损但文件更大。"),
        ("screenshot-high-bit-depth", "高位深截图", "bool", ["yes", "no"], "尽量保留 10bit 信息。"),
        ("screenshot-tag-colorspace", "截图标记色彩空间", "bool", ["yes", "no"], "写入色彩空间元数据。"),
        ("screenshot-jxl-distance", "JXL 视觉距离", "int", ["0", "1"], "0 为质量无损。"),
        ("ytdl-format", "网络视频格式", "str", ["bestvideo+bestaudio/best"], "yt-dlp 的 -f 参数。"),
        ("cache-secs", "缓存秒数", "int", ["10", "30", "60"], "网络流缓存时长。"),
        ("demuxer-readahead-secs", "预读秒数", "int", ["10", "30", "60"], "本地/网络预读时长。"),
        ("demuxer-max-back-bytes", "后退缓存", "str", ["50MiB", "512MiB"], "允许回退的缓冲量。"),
        ("network-timeout", "网络超时", "int", ["10", "30", "60"], "秒。"),
    ],
}

# key -> (类型, 建议值)
NATIVE_TYPES = {}
for _group, _items in NATIVE_OPTIONS.items():
    for _k, _label, _typ, _values, _desc in _items:
        NATIVE_TYPES[_k] = (_typ, _values)

# 需要手动输入的类别（下拉框改成可编辑）
NATIVE_EDITABLE_TYPES = {"int", "float", "str", "color", "list"}

_COLOR_RE = re.compile(r"^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")


def native_items():
    """展开成 (分类, key, 中文名, 说明, 建议值, 类型) 的列表，便于搜索与建页。"""
    out = []
    for group, items in NATIVE_OPTIONS.items():
        for key, label, typ, values, desc in items:
            out.append((group, key, label, desc, values, typ))
    return out


# ============================================================
# 全量选项数据库（R-19）：829 个 mpv 选项 + 中文说明
# 数据在 data/mpv_options_zh.json，由 tools/build_options_db.py 从
# `mpv --list-options` 与 mpv_doc-CN 生成。
# ============================================================

# 数据库类型 → 界面控件类型
DB_TYPE_MAP = {
    "flag": "bool",
    "integer": "int", "integer64": "int", "int": "int",
    "float": "float", "double": "float",
    "choice": "enum", "choices": "enum",
    "color": "color",
    "string list": "list", "object settings list": "list", "key/value list": "list",
}


def db_option_type(entry):
    """数据库里的类型名 → 界面用的类型（bool/enum/int/float/color/list/str）。"""
    raw = str((entry or {}).get("type", "")).strip().lower()
    if raw in DB_TYPE_MAP:
        return DB_TYPE_MAP[raw]
    for prefix, mapped in DB_TYPE_MAP.items():
        if raw.startswith(prefix):
            return mapped
    if raw.startswith("string"):
        return "str"
    return "str"


# ---------------------------------------------------------------- 值域

def _curated_values(key, values):
    """精选层写的那串值 —— 语义是**建议/举例**，不是全集。"""
    return [str(v) for v in (values or []) if str(v).strip()]


def real_values(key, typ, curated=()):
    """这个选项**真正允许**的取值表（拿不到就返回空 = 不做限制）。

    优先级：精选层（自己写的，本来就不全）→ 全量库的真实取值表。
    之所以要这一层：精选层里 `scale` 只写了 10 个值，而 mpv 实际有 39 个 ——
    界面上把它当全集渲染成下拉框，等于把用户锁在一个残缺的列表里。
    """
    if typ not in ("enum", "bool"):
        return []
    if typ == "bool":
        return ["yes", "no"]
    entry = _db_entry(key) or {}
    choices = [str(c) for c in (entry.get("choices") or []) if str(c).strip()]
    if choices:
        return choices
    return _curated_values(key, curated)


def is_free_form(key, typ, curated=()):
    """这个选项能不能随便填（不限于建议值）。

    **判据以全量库为准**，不是以精选层的"看起来像下拉"为准：
      · 库里是 `Choice`（或 `Flag`）→ 不能乱填，mpv 会拒绝不认识的值
      · 库里是 `Window geometry` / `Window size` / `String` / `ByteSize` / `Float`…
        → 能随便填，精选层列的那几个只是**例子**
      · 库里查不到 → 用传入的 typ 兜底；再拿不准就允许（不瞎判）

    修之前这里是"建议值里有 yes/no 就当 bool、否则当 enum"，
    结果把 `geometry`（库类型是 Window geometry）、`sub-font`（String）、
    `volume`（Float）这些**本来就该自由填**的项全锁成了下拉框。
    """
    entry = _db_entry(key) or {}
    raw = str(entry.get("type") or "").strip().lower()
    if raw in ("choice", "choices", "flag"):
        return False                       # 真正的枚举：只能从取值表里挑
    if raw:
        return True                        # 库里给了类型且不是枚举 → 自由填
    # 库里没有：退回传入的类型判断
    if typ not in ("enum", "bool"):
        return True
    return not real_values(key, typ, curated)


def value_info(key, typ, curated=()):
    """给界面用的值域信息：建议值 / 候选值 / 能不能自由填。"""
    sug = _curated_values(key, curated)
    entry = _db_entry(key) or {}
    raw = str(entry.get("type") or "").strip().lower()
    real = [str(c) for c in (entry.get("choices") or []) if str(c).strip()]
    if typ == "bool":
        real = ["yes", "no"]
    open_ = is_free_form(key, typ, curated)
    merged = []
    for v in sug + real:
        if v not in merged:
            merged.append(v)
    return {
        "suggest": sug,          # 精选层建议（界面展开区显示）
        "options": merged,       # 候选里的全部（真实取值 + 建议）
        "open": open_,
    }


def db_ui_item(entry):
    """把数据库条目转成界面直接能渲染的结构。"""
    key = entry.get("key", "")
    label, desc = key, (entry.get("zh_desc") or "").strip()
    for group, items in NATIVE_OPTIONS.items():      # 精选层给过中文名与建议值，优先用
        for k, lb, _typ, _vals, ds in items:
            if k == key:
                label, desc = lb, ds or desc
                break
    typ = db_option_type(entry)
    values = list(entry.get("choices") or [])
    if typ == "bool":
        values = ["yes", "no"]
    info = value_info(key, typ, values)
    return {
        "group": entry.get("group") or "其它",
        "key": key,
        "label": label,
        "desc": desc,
        "values": values,
        "type": typ,
        "kind": "db",
        "default": entry.get("default", ""),
        "range": entry.get("range", ""),
        "deprecated": bool(entry.get("deprecated")),
        "suggest": info["suggest"],
        "options": info["options"],
        "open": info["open"],
    }


def db_known_keys():
    """数据库里所有选项名（界面可能还没有对应控件，但 mpv 认识）。"""
    try:
        from .options_db import load_db
        return set((load_db().get("options") or {}).keys())
    except Exception:
        return set()


def _db_entry(key):
    """从全量数据库里取一条（取不到返回 None）。"""
    try:
        from .options_db import load_db
        return (load_db().get("options") or {}).get(key)
    except Exception:
        return None


def validate_native_value(key, value):
    """校验选项值，返回 (是否合法, 提示)。查不到类型的一律视为合法。

    先查精选层（NATIVE_TYPES，带建议值），查不到再查全量数据库（R-19）——
    数据库里有 mpv 真实的类型与取值范围，比手写的建议值靠谱。
    """
    spec = NATIVE_TYPES.get(key)
    db = _db_entry(key)
    if spec is None and db is None:
        return True, ""
    if spec is None:
        typ = db_option_type(db)
        curated_values = []
        values = list(db.get("choices") or [])
    else:
        typ, curated_values = spec
        values = list(curated_values)
        # 数据库里有 mpv 的真实取值表时以它为准：
        # 精选层的列表只是「推荐值」，不是全集（例如 tone-mapping 还有 st2094-40）
        if db and typ in ("enum", "bool") and db.get("choices"):
            values = list(db["choices"])
    if typ == "bool" and not values:
        values = ["yes", "no"]
    rng = str((db or {}).get("range") or "")
    raw_sig = str((db or {}).get("raw_sig") or "")
    v = str(value).strip().strip('"')
    if not v:
        return False, "值为空"
    if typ in ("enum", "bool"):
        if v in values or v in curated_values:
            return True, ""
        # 有些选项是「命名取值 + 整数」混着用（--dither-depth=<no|auto|8|10>）
        if "integer" in raw_sig.lower() and re.fullmatch(r"-?\d+", v):
            return True, ""
        shown = values or curated_values
        if not shown:
            return True, ""          # 数据库和精选层都没有取值表，不瞎判
        return False, (f"应为：{'/'.join(shown[:12])}" + ("…" if len(shown) > 12 else ""))
    if typ == "int":
        if not re.fullmatch(r"-?\d+", v):
            return False, "应为整数"
        return _check_range(v, rng)
    if typ == "float":
        if not re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", v):
            return False, "应为数字"
        return _check_range(v, rng)
    if typ == "color":
        return (True, "") if _COLOR_RE.match(v) else (False, "颜色格式应为 #RRGGBB 或 #AARRGGBB")
    return True, ""


_RANGE_RE = re.compile(r"^\s*(-?[\d.]+(?:e[-+]?\d+)?)\s+to\s+(-?[\d.]+(?:e[-+]?\d+)?|any)\s*$",
                       re.IGNORECASE)


def _check_range(value, rng):
    """数据库里的 `0 to 16` 这类范围，能解析就顺手校验一下。"""
    m = _RANGE_RE.match(rng or "")
    if not m:
        return True, ""
    try:
        lo = float(m.group(1))
        v = float(value)
    except ValueError:
        return True, ""
    if v < lo:
        return False, f"不能小于 {m.group(1)}"
    hi_raw = m.group(2)
    if hi_raw.lower() != "any":
        try:
            if v > float(hi_raw):
                return False, f"不能大于 {hi_raw}"
        except ValueError:
            pass
    return True, ""

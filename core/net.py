"""下载器：内置清单、镜像线路与 HTTP 访问（只用标准库）。"""
import urllib.error
import urllib.request

from .schema import APP_TITLE  # noqa: F401  （保持包内引用一致）


# ---------- 下载器：内置清单与加速线路 ----------
# 说明：清单里的 URL 指向上游官方仓库；发布前请用「校验链接」跑一遍确认没有 404。

SHADER_DOWNLOADS = [
    # Anime4K v4（bloc97/Anime4K）
    {"name": "Anime4K Clamp_Highlights", "dest": "shaders/Anime4K/Anime4K_Clamp_Highlights.glsl",
     "url": "https://raw.githubusercontent.com/bloc97/Anime4K/master/glsl/Restore/Anime4K_Clamp_Highlights.glsl",
     "note": "压高光防过冲"},
    {"name": "Anime4K Restore_CNN_M", "dest": "shaders/Anime4K/Anime4K_Restore_CNN_M.glsl",
     "url": "https://raw.githubusercontent.com/bloc97/Anime4K/master/glsl/Restore/Anime4K_Restore_CNN_M.glsl",
     "note": "线稿修复 M 档"},
    {"name": "Anime4K Restore_CNN_Soft_M", "dest": "shaders/Anime4K/Anime4K_Restore_CNN_Soft_M.glsl",
     "url": "https://raw.githubusercontent.com/bloc97/Anime4K/master/glsl/Restore/Anime4K_Restore_CNN_Soft_M.glsl",
     "note": "柔化修复，振铃更少"},
    {"name": "Anime4K Upscale_CNN_x2_M", "dest": "shaders/Anime4K/Anime4K_Upscale_CNN_x2_M.glsl",
     "url": "https://raw.githubusercontent.com/bloc97/Anime4K/master/glsl/Upscale/Anime4K_Upscale_CNN_x2_M.glsl",
     "note": "卷积放大 M 档"},
    {"name": "Anime4K Upscale_GAN_x2_S", "dest": "shaders/Anime4K/Anime4K_Upscale_GAN_x2_S.glsl",
     "url": "https://raw.githubusercontent.com/bloc97/Anime4K/master/glsl/Upscale/Anime4K_Upscale_GAN_x2_S.glsl",
     "note": "GAN 放大 S 档"},
    {"name": "Anime4K Upscale_GAN_x2_M", "dest": "shaders/Anime4K/Anime4K_Upscale_GAN_x2_M.glsl",
     "url": "https://raw.githubusercontent.com/bloc97/Anime4K/master/glsl/Upscale/Anime4K_Upscale_GAN_x2_M.glsl",
     "note": "GAN 放大 M 档"},
    {"name": "Anime4K AutoDownscalePre_x2", "dest": "shaders/Anime4K/Anime4K_AutoDownscalePre_x2.glsl",
     "url": "https://raw.githubusercontent.com/bloc97/Anime4K/master/glsl/Upscale/Anime4K_AutoDownscalePre_x2.glsl",
     "note": "两轮放大之间的预缩放"},
    {"name": "Anime4K Deblur_DoG", "dest": "shaders/Anime4K/Anime4K_Deblur_DoG.glsl",
     "url": "https://raw.githubusercontent.com/bloc97/Anime4K/master/glsl/Deblur/Anime4K_Deblur_DoG.glsl",
     "note": "去模糊锐化"},
    # FSRCNNX（igv/FSRCNNX）
    {"name": "FSRCNNX x2_8", "dest": "shaders/FSRCNNX/FSRCNNX_x2_8-0-4-1.glsl",
     "url": "https://raw.githubusercontent.com/igv/FSRCNNX/master/FSRCNNX_x2_8-0-4-1.glsl",
     "note": "通用超分，轻量"},
    {"name": "FSRCNNX x2_16", "dest": "shaders/FSRCNNX/FSRCNNX_x2_16-0-4-1.glsl",
     "url": "https://raw.githubusercontent.com/igv/FSRCNNX/master/FSRCNNX_x2_16-0-4-1.glsl",
     "note": "通用超分，更锐更慢"},
    {"name": "FSRCNNX x1_16 distort", "dest": "shaders/FSRCNNX/FSRCNNX_x1_16-0-4-1_distort.glsl",
     "url": "https://raw.githubusercontent.com/igv/FSRCNNX/master/FSRCNNX_x1_16-0-4-1_distort.glsl",
     "note": "去伪影变体，适合低清源"},
    # RAVU（bjin/mpv-prescalers）
    {"name": "RAVU zoom-ar r3", "dest": "shaders/RAVU/ravu-zoom-ar-r3.glsl",
     "url": "https://raw.githubusercontent.com/bjin/mpv-prescalers/master/ravu/ravu-zoom-ar-r3.glsl",
     "note": "一路放大到目标分辨率"},
    {"name": "RAVU zoom-ar r4", "dest": "shaders/RAVU/ravu-zoom-ar-r4.glsl",
     "url": "https://raw.githubusercontent.com/bjin/mpv-prescalers/master/ravu/ravu-zoom-ar-r4.glsl",
     "note": "RAVU 高质量档"},
    {"name": "RAVU lite-ar r3", "dest": "shaders/RAVU/ravu-lite-ar-r3.glsl",
     "url": "https://raw.githubusercontent.com/bjin/mpv-prescalers/master/ravu/ravu-lite-ar-r3.glsl",
     "note": "RAVU 轻量档，最锐"},
]

MIRROR_PREFIXES = {
    "ghproxy.net": "https://ghproxy.net/",
    "gh-proxy.com": "https://gh-proxy.com/",
    "ghfast.top": "https://ghfast.top/",
}
MIRROR_OPTIONS = ["自动（直连 → 镜像）", "直连 GitHub"] + list(MIRROR_PREFIXES.keys())


def build_url_candidates(url, mode):
    """按加速模式给出尝试顺序：直连 / 镜像。"""
    if mode.startswith("自动"):
        return [""] + list(MIRROR_PREFIXES.values())
    if mode == "直连 GitHub":
        return [""]
    prefix = MIRROR_PREFIXES.get(mode, "")
    return [prefix, ""] if prefix else [""]


def _http_request(url, method="GET", timeout=25):
    req = urllib.request.Request(url, method=method,
                                 headers={"User-Agent": "MPVConfigBuilder/0.1"})
    return urllib.request.urlopen(req, timeout=timeout)


def http_fetch(url, timeout=25):
    with _http_request(url, "GET", timeout) as resp:
        return resp.read()


def http_head(url, timeout=15):
    with _http_request(url, "HEAD", timeout) as resp:
        return resp.status, resp.headers.get("Content-Length")


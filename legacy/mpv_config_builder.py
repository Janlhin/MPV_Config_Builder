import json
import os
import queue
import re
import shutil
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ---- 让 `core` 找得到（这个文件住在 legacy/，而 core/ 在仓库根）----
#
# 2026-09-14 把旧界面从仓库根挪进了 `legacy/`。挪完它 import 不到 `core` 了 ——
# 以前能跑只是因为启动器 `cd` 到了仓库根，靠"当前工作目录"碰巧在 sys.path 上。
# 这种依赖是隐式的，换个启动方式就断，所以这里把它写明。
#
# 三种运行形态都认：
#   · 源码：legacy/mpv_config_builder.py → 退一级就是仓库根
#   · 打包：数据在 sys._MEIPASS（PyInstaller 解包目录）
#   · 被别处以包的形式导入：仓库根已经在 sys.path 上，插了也无害
if not getattr(sys, "frozen", False):
    _ROOT = Path(__file__).resolve().parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

from core.paths import doc_path, is_frozen, writable_root      # noqa: E402
from core.schema import (
    APP_TITLE,
    APP_VERSION,
    VERSION,
    FULL_TITLE,
    SETTINGS_PATH,
    load_settings,
    save_settings,
    RESOURCE_LINKS,
    PARAMS,
    EDITABLE_PARAMS,
    SHADERS,
    SHADER_PATHS,
    MEMC_PRESETS,
    BASE_SHARP,
    SHADER_EXTS,
    VS_EXTS,
    LAZY_CANDIDATE_DIRS,
    SHADER_PRIORITY,
    MEMC_PRIORITY,
    SHADER_GROUP_ORDER,
    MEMC_GROUP_ORDER,
    find_lazy_pc,
    scan_lazy,
    norm_mpv_path,
    split_mpv_list,
    extract_vapoursynth_path,
    strip_inline_comment,
    build_shader_catalog,
    build_memc_catalog,
    shader_group,
    memc_group,
    COMMON_OPTIONS,
    SHADER_OPTION_KEYS,
    get_param_meta,
    NATIVE_OPTIONS,
    NATIVE_TYPES,
    NATIVE_EDITABLE_TYPES,
    native_items,
    validate_native_value,
)
from core.net import (
    SHADER_DOWNLOADS,
    MIRROR_PREFIXES,
    MIRROR_OPTIONS,
    build_url_candidates,
    _http_request,
    http_fetch,
    http_head,
)
from core.score import score_active
from core.analyze import analyze_config_text
from core.presets import (
    BASIC_PRESETS,
    CONTENT_CHOICES,
    PREFER_CHOICES,
    WRITE_MODE_INCLUDE,
    WRITE_MODE_MERGE,
    get_basic_preset,
    resolve_shader_slots,
)
from core.hardware import detect_all
from core.writer import (
    INCLUDE_FILENAME,
    build_include_text,
    write_include,
    ensure_include_line,
    merge_into_file,
    apply_params_to_lines,
    read_text,
)
from core.installer import (
    default_install_dir,
    fetch_latest_release,
    pick_asset,
    recommend_asset,
    download_file,
    verify_sha256,
    verify_size,
    extract_archive,
    find_portable_config,
)
from core.update import check_tool_update, check_lazy_update

def enable_dpi_awareness():
    """让界面跟上系统缩放（M6 / P2-3）。

    不做这件事的话，在 125% / 150% 缩放的屏幕上，Windows 会把这窗口当"不认识 DPI
    的老程序"，整个界面先按 100% 渲染再被拉伸 —— 结果就是发糊、字发虚。
    网页版天然没这问题（浏览器自己处理），Tkinter 这份必须显式声明。

    失败一律忽略：这只是观感优化，不该因为它让程序起不来。
    """
    try:
        import ctypes
        # 优先 per-monitor v2（Win10 1703+，多屏不同缩放时最准）
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
            return "per-monitor-v2"
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PROCESS_PER_MONITOR_DPI_AWARE
            return "per-monitor"
        except Exception:
            pass
        ctypes.windll.user32.SetProcessDPIAware()            # 老系统兜底
        return "system"
    except Exception:
        return ""


def tk_scaling():
    """按系统 DPI 给出 tk 的缩放系数（拿不到就返回 1.0）。"""
    try:
        import ctypes
        hdc = ctypes.windll.user32.GetDC(0)
        try:
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        finally:
            ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, min(3.0, dpi / 96.0)) if dpi else 1.0
    except Exception:
        return 1.0


class App(tk.Tk):
    def __init__(self):
        # DPI 声明必须在建窗口**之前**做，否则已经按 96dpi 布局完了
        self.dpi_mode = enable_dpi_awareness()
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        # 按系统缩放放大字体与控件，4K/125% 屏上不再糊成一团
        try:
            scale = tk_scaling()
            if scale > 1.0:
                self.tk.call("tk", "scaling", scale * 1.3333)
        except Exception:
            pass
        self.geometry("1280x820")
        self.minsize(1050, 680)
        self.vars = {}
        self.checks = {}
        self.desc = {}
        self.option_lists = {}
        self.custom_unknown = ""
        self.shader_order = []
        self.lazy_pc = find_lazy_pc()
        self.shader_catalog = build_shader_catalog(self.lazy_pc)
        self.memc_catalog = build_memc_catalog(self.lazy_pc)
        # 模式状态
        self.mode = tk.StringVar(value="create")
        self.source_path = None
        self.source_lines = []
        self.source_bom = False
        self.source_newline = "\n"
        self.baseline_params = {}
        self.baseline_shader_paths = []
        self.baseline_memc_path = None
        self.change_count = 0
        self.last_preview_text = ""
        # 扫描状态
        self.scan_dir = tk.StringVar(value=str(self.lazy_pc) if self.lazy_pc else "")
        self.scan_found = []
        self.scan_missing = []
        # 简易 / 高级模式
        settings = load_settings()
        self.advanced = tk.BooleanVar(value=bool(settings.get("advanced", False)))
        self.advanced_tabs = []          # [(widget, tab_text)] 只在高级模式显示
        self.advanced_param_keys = set() # 属于"高级"的参数 key（用于提示）
        # 下载器状态
        self.dl_target = tk.StringVar(value=str(self.lazy_pc) if self.lazy_pc else "")
        self.dl_mirror = tk.StringVar(value=settings.get("mirror", MIRROR_OPTIONS[0]))
        self.dl_overwrite = tk.BooleanVar(value=False)
        self.dl_checks = {}
        self.dl_status = {}
        self.dl_queue = queue.Queue()
        self.dl_running = False
        self.dl_notified = bool(settings.get("dl_notified", False))
        # 一键安装状态
        self.install_queue = queue.Queue()
        self.install_running = False
        # 更新检测
        self.update_queue = queue.Queue()
        self.update_running = False
        self.build()
        self.apply_advanced_mode()
        self.load_lazy_config()
        self.update_all()
        if self.lazy_pc:
            self.status.config(text=f"已读取 mpv-lazy 现有配置：自动勾选 {self.lazy_loaded_count} 项")
        self.start_update_check()

    def build(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text=f"{APP_TITLE} {APP_VERSION}",
                  font=("Segoe UI", 17, "bold")).pack(side="left")
        ttk.Label(top, text=f"v{VERSION}", foreground="#6b7488").pack(side="left", padx=(8, 0))
        target_text = f"目标：{self.lazy_pc}" if self.lazy_pc else "目标：未找到 mpv-lazy（通用模板模式）"
        ttk.Label(top, text=target_text, foreground="#1a7f37" if self.lazy_pc else "#c0392b").pack(side="left", padx=(12,0))
        for text, cmd in [
            ("打开", self.load_conf), ("保存", self.save_conf),
            ("复制", self.copy_conf), ("清空", self.clear_all),
            ("上传分析", self.analysis_upload), ("粘贴分析", self.analysis_paste),
            ("说明书", self.open_guide), ("高质量预设", self.high_quality)
        ]:
            ttk.Button(top, text=text, command=cmd).pack(side="right", padx=3)

        # 模式选择行
        mode_row = ttk.Frame(self, padding=(10, 0, 10, 4))
        mode_row.pack(fill="x")
        ttk.Label(mode_row, text="模式：", font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Radiobutton(mode_row, text="完全创造模式", variable=self.mode, value="create",
                        command=self.on_mode_change).pack(side="left")
        ttk.Radiobutton(mode_row, text="上传修改模式", variable=self.mode, value="modify",
                        command=self.on_mode_change).pack(side="left", padx=(8, 0))
        ttk.Button(mode_row, text="上传配置...", command=self.upload_for_modify).pack(side="left", padx=(14, 4))
        ttk.Button(mode_row, text="应用修改", command=self.apply_modify).pack(side="left", padx=4)
        ttk.Button(mode_row, text="另存为", command=self.save_as).pack(side="left", padx=4)
        ttk.Checkbutton(mode_row, text="高级模式", variable=self.advanced,
                        command=self.on_advanced_change).pack(side="left", padx=(14, 0))
        self.mode_label = ttk.Label(mode_row, text="完全创造模式：从零生成新配置", foreground="#555555")
        self.mode_label.pack(side="left", padx=(10, 0))

        # Overall evaluation
        score = ttk.LabelFrame(self, text="总体评估", padding=10)
        score.pack(fill="x", padx=10, pady=(0,8))
        self.overall = ttk.Label(score, text="", font=("Segoe UI", 13, "bold"))
        self.overall.grid(row=0, column=0, sticky="w")
        self.bars = {}
        for i, name in enumerate(["清晰度","锐度","流畅度","色彩/观感","稳定性","GPU负载"]):
            ttk.Label(score, text=name).grid(row=1, column=i*2, padx=(5,2), sticky="w")
            pb = ttk.Progressbar(score, length=105, maximum=100)
            pb.grid(row=1, column=i*2+1, padx=(0,8), sticky="ew")
            self.bars[name] = pb

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=(0,10))

        left = ttk.Frame(paned)
        mid = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(mid, weight=1)
        paned.add(right, weight=2)

        self.nb = ttk.Notebook(left)
        self.nb.pack(fill="both", expand=True)
        self.build_basic_tab()
        for cat, items in PARAMS.items():
            frame = ttk.Frame(self.nb, padding=9)
            self.nb.add(frame, text=cat)
            for key, label, description, options, q, load in items:
                self.add_param(frame, key, label, description, options)

        # ---- 原生选项（完全体，仅高级模式显示）----
        for group, items in NATIVE_OPTIONS.items():
            frame = ttk.Frame(self.nb, padding=9)
            self.nb.add(frame, text=group)
            self.advanced_tabs.append((frame, group))
            inner = self.make_scrollable(frame)
            for key, label, typ, values, desc in items:
                self.add_param(inner, key, label, desc, values,
                               editable=typ in NATIVE_EDITABLE_TYPES)
                self.advanced_param_keys.add(key)

        # ---- 搜索页（仅高级模式显示）----
        search_frame = ttk.Frame(self.nb, padding=9)
        self.nb.add(search_frame, text="搜索")
        self.advanced_tabs.append((search_frame, "搜索"))
        ttk.Label(search_frame, text="输入关键词搜索全部选项（键名 / 中文名）",
                  font=("Segoe UI", 10, "bold"), wraplength=330).pack(anchor="w", pady=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(fill="x", pady=2)
        search_entry.bind("<KeyRelease>", lambda e: self.refresh_search())
        self.search_hint = ttk.Label(search_frame, text="", foreground="#666666")
        self.search_hint.pack(anchor="w")
        search_holder = ttk.Frame(search_frame)
        search_holder.pack(fill="both", expand=True, pady=4)
        self.search_inner = self.make_scrollable(search_holder, "search_canvas")
        ttk.Label(self.search_inner, text="（输入后显示匹配项）",
                  foreground="#888888").pack(anchor="w")

        self.shader_frame = ttk.Frame(self.nb, padding=9)
        self.nb.add(self.shader_frame, text="Shader / 锐化")
        self.shader_inner = self.make_scrollable(self.shader_frame, "shader_canvas")
        current_group = None
        for item in self.shader_catalog:
            g = shader_group(item["name"])
            if g != current_group:
                current_group = g
                ttk.Label(self.shader_inner, text="— " + g + " —",
                          font=("Segoe UI", 9, "bold"), foreground="#1f4e79").pack(anchor="w", pady=(6,0))
            self.add_shader(self.shader_inner, item["name"], item["desc"], path=item["path"])

        combo_frame = ttk.Frame(self.nb, padding=9)
        self.nb.add(combo_frame, text="组合预设")
        ttk.Label(combo_frame, text="一键套用组合（会先清空当前配置）",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0,6))
        if self.lazy_pc:
            preset_buttons = [
                ("最锐利基础参数", self.preset_sharp_base),
                ("mpv-lazy 通用锐利", self.preset_lazy_general),
                ("mpv-lazy 动漫锐利", self.preset_lazy_anime),
                ("mpv-lazy 最强动漫", self.preset_lazy_anime_max),
                ("内置补帧", self.preset_internal_memc),
                ("mpv-lazy RIFE 补帧", self.preset_lazy_rife),
                ("清空 Shader", self.clear_shaders),
            ]
            preset_hint = "提示：所有 Shader 路径都来自 mpv-lazy 实际存在的文件，勾选即可，无需手动选文件。"
        else:
            preset_buttons = [
                ("最锐利基础参数", self.preset_sharp_base),
                ("通用锐利链", self.preset_general_sharp),
                ("动漫极致链", self.preset_anime_sharp),
                ("内置补帧", self.preset_internal_memc),
                ("外部MEMC(RIFE模板)", self.preset_external_memc),
                ("清空 Shader", self.clear_shaders),
            ]
            preset_hint = "提示：未找到 mpv-lazy，当前为通用模板模式，Shader 路径可能需要手动选择。"
        for text, cmd in preset_buttons:
            ttk.Button(combo_frame, text=text, command=cmd).pack(fill="x", pady=2)
        ttk.Label(combo_frame, text=preset_hint, wraplength=330, foreground="#555555").pack(anchor="w", pady=(8,0))

        self.memc_frame = ttk.Frame(self.nb, padding=9)
        self.nb.add(self.memc_frame, text="VS 补帧")
        self.memc_inner = self.make_scrollable(self.memc_frame, "memc_canvas")
        ttk.Label(self.memc_inner, text="选择一项即生成 vf=vapoursynth 配置；同一时间只会启用一项。",
                  font=("Segoe UI", 11, "bold"), wraplength=330).pack(anchor="w", pady=(0,6))
        current_group = None
        for item in self.memc_catalog:
            g = memc_group(item["name"])
            if g != current_group:
                current_group = g
                ttk.Label(self.memc_inner, text="— " + g + " —",
                          font=("Segoe UI", 9, "bold"), foreground="#1f4e79").pack(anchor="w", pady=(6,0))
            self.add_memc(self.memc_inner, item["name"], item["desc"], item["path"])

        # 资源 / 下载
        res_frame = ttk.Frame(self.nb, padding=9)
        self.nb.add(res_frame, text="资源 / 下载")
        res_inner = self.make_scrollable(res_frame, "res_canvas")
        ttk.Label(res_inner, text="以下都是外部网站，程序不会自动下载任何文件",
                  font=("Segoe UI", 10, "bold"), foreground="#c0392b",
                  wraplength=330).pack(anchor="w", pady=(0, 6))
        for group, links in RESOURCE_LINKS.items():
            ttk.Label(res_inner, text="— " + group + " —",
                      font=("Segoe UI", 9, "bold"), foreground="#1f4e79").pack(anchor="w", pady=(8, 2))
            for label, url in links:
                ttk.Button(res_inner, text=label,
                           command=lambda u=url: self.open_url(u)).pack(fill="x", pady=1)
        ttk.Button(res_inner, text="打开本地搭配说明书", command=self.open_guide).pack(fill="x", pady=(12, 2))
        ttk.Button(res_inner, text="检查更新", command=lambda: self.start_update_check(manual=True)).pack(fill="x", pady=2)
        ttk.Label(res_inner, text="提示：装好播放器和着色器后，回到「扫描 glsl/vpy」页扫描本机文件。",
                  foreground="#555555", wraplength=330).pack(anchor="w", pady=(6, 0))

        # 下载器
        dl_frame = ttk.Frame(self.nb, padding=9)
        self.nb.add(dl_frame, text="下载器")
        ttk.Label(dl_frame, text="把常用 shader 直接下载到播放器目录（只有点「下载选中」时才联网）",
                  font=("Segoe UI", 11, "bold"), wraplength=330).pack(anchor="w", pady=(0, 4))

        row = ttk.Frame(dl_frame)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="目标：").pack(side="left")
        ttk.Entry(row, textvariable=self.dl_target).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row, text="浏览", width=5, command=self.dl_browse).pack(side="right")

        row2 = ttk.Frame(dl_frame)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="加速：").pack(side="left")
        cb = ttk.Combobox(row2, textvariable=self.dl_mirror, values=MIRROR_OPTIONS,
                          state="readonly", width=16)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: save_settings({"mirror": self.dl_mirror.get()}))
        ttk.Checkbutton(row2, text="覆盖已存在(先备份)", variable=self.dl_overwrite).pack(side="left", padx=6)

        dl_holder = ttk.Frame(dl_frame)
        dl_holder.pack(fill="both", expand=True, pady=4)
        dl_inner = self.make_scrollable(dl_holder, "dl_canvas")
        for item in SHADER_DOWNLOADS:
            r = ttk.Frame(dl_inner)
            r.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=False)
            self.dl_checks[item["name"]] = var
            ttk.Checkbutton(r, text=item["name"], variable=var).pack(side="left", anchor="w")
            sv = tk.StringVar(value="")
            self.dl_status[item["name"]] = sv
            ttk.Label(r, textvariable=sv, foreground="#666666",
                      font=("Consolas", 8), wraplength=150).pack(side="right", padx=2)

        dl_btns = ttk.Frame(dl_frame)
        dl_btns.pack(fill="x", pady=2)
        ttk.Button(dl_btns, text="全选", command=lambda: self.dl_select(True)).pack(side="left", padx=2)
        ttk.Button(dl_btns, text="全不选", command=lambda: self.dl_select(False)).pack(side="left", padx=2)
        ttk.Button(dl_btns, text="下载选中", command=self.dl_start).pack(side="left", padx=2)
        ttk.Button(dl_btns, text="校验链接", command=self.dl_check_links).pack(side="left", padx=2)
        ttk.Button(dl_btns, text="打开目录", command=self.dl_open_target).pack(side="left", padx=2)

        self.dl_progress = ttk.Progressbar(dl_frame, maximum=100)
        self.dl_progress.pack(fill="x", pady=2)
        self.dl_hint = ttk.Label(dl_frame, text="提示：下载前会弹出一次联网说明；内容自检失败会删除文件并报错。",
                                 foreground="#555555", wraplength=330)
        self.dl_hint.pack(anchor="w", pady=(2, 0))

        # 扫描 glsl / vpy
        scan_frame = ttk.Frame(self.nb, padding=9)
        self.nb.add(scan_frame, text="扫描 glsl/vpy")
        self.advanced_tabs.append((scan_frame, "扫描 glsl/vpy"))
        ttk.Label(scan_frame, text="扫描 shaders 和 vs 目录，列出全部 .glsl / .vpy，并说明哪些没进列表",
                  font=("Segoe UI", 11, "bold"), wraplength=330).pack(anchor="w", pady=(0,4))
        scan_row = ttk.Frame(scan_frame)
        scan_row.pack(fill="x", pady=2)
        ttk.Entry(scan_row, textvariable=self.scan_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(scan_row, text="浏览", width=5, command=self.browse_scan_dir).pack(side="right", padx=2)
        scan_btns = ttk.Frame(scan_frame)
        scan_btns.pack(fill="x", pady=4)
        ttk.Button(scan_btns, text="扫描两者", command=self.scan_dirs).pack(side="left", padx=2)
        ttk.Button(scan_btns, text="导入选中并勾选", command=lambda: self.import_scan_items(True)).pack(side="left", padx=2)
        ttk.Button(scan_btns, text="导入全部(不勾选)", command=lambda: self.import_scan_items(False)).pack(side="left", padx=2)
        scan_btns2 = ttk.Frame(scan_frame)
        scan_btns2.pack(fill="x", pady=2)
        ttk.Button(scan_btns2, text="复制路径", command=self.copy_scan_path).pack(side="left", padx=2)
        ttk.Button(scan_btns2, text="导出清单", command=self.export_scan_list).pack(side="left", padx=2)
        tree_holder = ttk.Frame(scan_frame)
        tree_holder.pack(fill="both", expand=True, pady=4)
        self.scan_tree = ttk.Treeview(tree_holder, columns=("state", "kind", "path"), show="headings", height=14)
        self.scan_tree.heading("state", text="状态")
        self.scan_tree.heading("kind", text="类型")
        self.scan_tree.heading("path", text="路径")
        self.scan_tree.column("state", width=90, anchor="center")
        self.scan_tree.column("kind", width=45, anchor="center")
        self.scan_tree.column("path", width=220)
        sb2 = ttk.Scrollbar(tree_holder, orient="vertical", command=self.scan_tree.yview)
        self.scan_tree.configure(yscrollcommand=sb2.set)
        self.scan_tree.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.scan_tree.bind("<Double-1>", lambda e: self.copy_scan_path())
        self.scan_status = ttk.Label(scan_frame, text="点『扫描两者』开始", foreground="#555555", wraplength=330)
        self.scan_status.pack(anchor="w", pady=(4,0))
        ttk.Label(scan_frame, text="流程：扫描 → 选中行 →『导入选中并勾选』(立即写入预览)；"
                                   "『已在列表』只代表列表里有它，是否写入看勾选。",
                  foreground="#1f4e79", wraplength=330).pack(anchor="w", pady=(4,0))

        # Explanation panel
        ttk.Label(mid, text="参数说明", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.explain_title = ttk.Label(mid, text="点击左侧参数查看详细说明", font=("Segoe UI", 12, "bold"))
        self.explain_title.pack(anchor="w", pady=(8,4))
        self.explain = tk.Text(mid, wrap="word", height=20, font=("Segoe UI", 10), state="disabled")
        self.explain.pack(fill="both", expand=True)
        self.explain.tag_configure("heading", font=("Segoe UI", 11, "bold"))
        self.explain.tag_configure("warn", font=("Segoe UI", 10, "bold"))

        # Preview
        self.preview_label = ttk.Label(right, text="实时生成的 mpv.conf", font=("Segoe UI", 11, "bold"))
        self.preview_label.pack(anchor="w")
        self.text = tk.Text(right, wrap="none", font=("Consolas", 10), undo=True)
        self.text.pack(fill="both", expand=True, pady=(6,0))
        self.text.bind("<KeyRelease>", lambda e: self.update_score_only())

        bottom = ttk.Frame(self, padding=(10,0,10,8))
        bottom.pack(fill="x")
        self.status = ttk.Label(bottom, text="就绪")
        self.status.pack(side="left")
        self.recommend = ttk.Label(bottom, text="")
        self.recommend.pack(side="right")

    # ---------- 基础模式（向导） ----------

    def build_basic_tab(self):
        frame = ttk.Frame(self.nb, padding=9)
        self.nb.add(frame, text="基础模式")
        self.basic_frame = frame
        inner = self.make_scrollable(frame, "basic_canvas")

        ttk.Label(inner, text="① 你的 mpv 配置在哪？",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
        row = ttk.Frame(inner)
        row.pack(fill="x", pady=2)
        self.basic_dir = tk.StringVar(value=str(self.lazy_pc) if self.lazy_pc else "")
        ttk.Entry(row, textvariable=self.basic_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="浏览", width=5, command=self.basic_browse).pack(side="right", padx=2)
        row1b = ttk.Frame(inner)
        row1b.pack(fill="x", pady=2)
        ttk.Button(row1b, text="自动探测", command=self.basic_detect_dir).pack(side="left")
        self.basic_dir_hint = ttk.Label(row1b, text="", foreground="#666666", wraplength=200)
        self.basic_dir_hint.pack(side="left", padx=6)

        row1c = ttk.Frame(inner)
        row1c.pack(fill="x", pady=2)
        ttk.Button(row1c, text="下载并安装 mpv-lazy", command=self.install_lazy).pack(side="left")
        self.install_progress = ttk.Progressbar(row1c, length=110, maximum=100)
        self.install_progress.pack(side="left", padx=6)
        self.install_hint = ttk.Label(inner, text="没装 mpv-lazy？点上面的按钮自动下载安装（会联网，约数百 MB）",
                                      foreground="#666666", wraplength=310)
        self.install_hint.pack(anchor="w", pady=(0, 4))

        ttk.Label(inner, text="② 你的设备？（自动检测，可手改）",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        dev = ttk.Frame(inner)
        dev.pack(fill="x", pady=2)
        ttk.Label(dev, text="分辨率").pack(side="left")
        self.basic_res = tk.StringVar(value="")
        ttk.Entry(dev, textvariable=self.basic_res, width=11).pack(side="left", padx=(2, 8))
        ttk.Label(dev, text="刷新率").pack(side="left")
        self.basic_hz = tk.StringVar(value="")
        ttk.Entry(dev, textvariable=self.basic_hz, width=5).pack(side="left", padx=(2, 8))
        ttk.Button(dev, text="重新检测", command=self.basic_detect_hw).pack(side="left")
        dev2 = ttk.Frame(inner)
        dev2.pack(fill="x", pady=2)
        ttk.Label(dev2, text="显卡").pack(side="left")
        self.basic_gpu = tk.StringVar(value="")
        ttk.Entry(dev2, textvariable=self.basic_gpu).pack(side="left", fill="x", expand=True, padx=2)

        ttk.Label(inner, text="③ 主要看什么？",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        self.basic_content = tk.StringVar(value=CONTENT_CHOICES[0])
        rowc = ttk.Frame(inner)
        rowc.pack(fill="x")
        for c in CONTENT_CHOICES:
            ttk.Radiobutton(rowc, text=c, variable=self.basic_content, value=c,
                            command=self.basic_refresh_preview).pack(side="left", padx=(0, 10))

        ttk.Label(inner, text="④ 更在意什么？",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        self.basic_prefer = tk.StringVar(value=PREFER_CHOICES[1])
        for p in PREFER_CHOICES:
            ttk.Radiobutton(inner, text=p, variable=self.basic_prefer, value=p,
                            command=self.basic_refresh_preview).pack(anchor="w")

        ttk.Label(inner, text="写入方式",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        self.basic_write = tk.StringVar(value=WRITE_MODE_INCLUDE)
        ttk.Radiobutton(inner, text="独立 include 文件（推荐，便于卸载）",
                        variable=self.basic_write, value=WRITE_MODE_INCLUDE,
                        command=self.basic_refresh_preview).pack(anchor="w")
        ttk.Radiobutton(inner, text="直接合并进 mpv.conf（保留原内容）",
                        variable=self.basic_write, value=WRITE_MODE_MERGE,
                        command=self.basic_refresh_preview).pack(anchor="w")

        ttk.Button(inner, text="生成配置", command=self.basic_generate).pack(fill="x", pady=(12, 4))
        self.basic_result = ttk.Label(inner, text="", foreground="#1a7f37", wraplength=310)
        self.basic_result.pack(anchor="w", pady=(2, 6))

        ttk.Label(inner, text="将写入的内容预览",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        self.basic_preview = tk.Text(inner, height=12, wrap="none", font=("Consolas", 9))
        self.basic_preview.pack(fill="both", expand=True)

        self.basic_detect_hw()
        self.basic_detect_dir(silent=True)
        self.basic_refresh_preview()

    def basic_browse(self):
        d = filedialog.askdirectory(initialdir=self.basic_dir.get() or os.path.expanduser("~"))
        if d:
            self.basic_dir.set(d)
            self.basic_refresh_preview()

    def basic_detect_dir(self, silent=False):
        """探测常见的 mpv 配置目录。"""
        candidates = []
        if self.lazy_pc:
            candidates.append(Path(self.lazy_pc))
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "mpv")
        candidates.append(Path(__file__).resolve().parent / "portable_config")
        for c in candidates:
            if c.is_dir():
                self.basic_dir.set(str(c))
                self.basic_dir_hint.config(text=f"已找到：{c.name}")
                self.basic_refresh_preview()
                return
        if not silent:
            self.basic_dir_hint.config(text="没找到，请手动选择配置目录")

    def basic_detect_hw(self):
        info = detect_all()
        if info.get("resolution"):
            self.basic_res.set(info["resolution"])
        if info.get("refresh"):
            self.basic_hz.set(info["refresh"])
        if info.get("gpu"):
            self.basic_gpu.set(info["gpu"])

    # ---------- 一键安装 mpv-lazy ----------

    def install_lazy(self):
        if self.install_running:
            messagebox.showinfo(APP_TITLE, "正在安装中，请稍候…")
            return
        target = default_install_dir()
        if not messagebox.askyesno(
                APP_TITLE,
                f"将从 GitHub 官方仓库下载最新版 mpv-lazy，解压到：\n\n{target}\n\n"
                f"（只下载官方 release，不重新打包分发）\n\n"
                f"选「是」用这个目录；选「否」自己挑一个目录。"):
            d = filedialog.askdirectory(initialdir=str(target.parent))
            if not d:
                return
            target = Path(d) / "mpv-lazy"
        self.install_running = True
        self.install_progress["value"] = 0
        self.install_hint.config(text="准备中…")
        threading.Thread(target=self._install_worker,
                         args=(target, self.dl_mirror.get()), daemon=True).start()
        self.after(150, self._install_poll)

    def _install_worker(self, target, mirror_mode):
        q = self.install_queue
        try:
            q.put(("hint", "正在获取最新版本信息…"))
            rel = fetch_latest_release()
            # ⚠ 用 recommend_asset 而不是 pick_asset。
            # pick_asset 是"同类里选最大的"，会挑中 `-noVS` 精简包
            # （名字里的 noVS = **没有 VapourSynth**），装完补帧用不了。
            # 详见 core/installer.py 里 recommend_asset 上面那段注释。
            asset, why, _usable, notes = recommend_asset(rel["assets"])
            if asset is None:
                raise RuntimeError(why or "最新 release 里没有可用的 zip/7z 包")
            q.put(("hint", f"最新版 {rel['tag']}：{asset['name']}"
                           f"（{asset['size'] // 1048576} MB）— {why}"))
            for n in notes:
                q.put(("hint", f"ℹ️ {n}"))
            target.mkdir(parents=True, exist_ok=True)
            # 分卷要逐卷下（老界面这边只做第一卷一键下，其余卷提示手动补齐）
            dest = Path(target) / asset["name"]
            if asset.get("split") and len(asset.get("names") or []) > 1:
                q.put(("hint", f"⚠ 这个包有 {len(asset['names'])} 卷，"
                               "这个老界面只下第一卷；建议改用网页版的「下载中心」"
                               "（会自动依次下完）"))

            last = {"pct": -1}

            def cb(done, total):
                if total:
                    pct = int(done * 100 / total)
                    if pct != last["pct"]:
                        last["pct"] = pct
                        q.put(("pct", pct, ""))
                        q.put(("hint", f"下载中 {done // 1048576} / {total // 1048576} MB"))

            ok, err = False, None
            for prefix in build_url_candidates(asset["url"], mirror_mode):
                try:
                    download_file(prefix + asset["url"] if prefix else asset["url"],
                                  dest, progress_cb=cb)
                    ok = True
                    break
                except Exception as e:
                    err = e
            if not ok:
                raise err or RuntimeError("下载失败")

            if asset.get("digest"):
                good, actual = verify_sha256(dest, asset["digest"])
                if not good:
                    raise RuntimeError(f"校验失败：期望 {asset['digest'][:12]}…，实际 {actual[:12]}…")
            elif asset.get("size"):
                # 没有 digest 时退化校验：至少比一下文件大小（以前是直接放行）
                good, actual = verify_size(dest, asset["size"])
                if not good:
                    raise RuntimeError(
                        f"下载不完整：期望 {asset['size']} 字节，实际 {actual} 字节")
                q.put(("hint", "上游没提供 sha256，已按文件大小校验"))

            q.put(("hint", "正在解压…"))
            method = extract_archive(dest, target,
                                     progress_cb=lambda i, n: q.put(("pct", int(i * 100 / max(n, 1)), "")))
            pc = find_portable_config(target)
            try:
                st = load_settings()
                st["lazy_tag"] = rel.get("tag", "")
                st["lazy_dir"] = str(target)
                save_settings(st)
            except Exception:
                pass
            q.put(("done", str(pc) if pc else "", f"解压方式：{method}"))
        except Exception as e:
            q.put(("error", str(e), ""))

    def _install_poll(self):
        try:
            while True:
                kind, a, b = self.install_queue.get_nowait()
                if kind == "hint":
                    self.install_hint.config(text=a)
                elif kind == "pct":
                    self.install_progress["value"] = a
                elif kind == "done":
                    self.install_running = False
                    self.install_progress["value"] = 100
                    if a:
                        self.basic_dir.set(a)
                        self.basic_refresh_preview()
                        self.install_hint.config(text=f"安装完成，配置目录：{a}")
                    else:
                        self.install_hint.config(text="解压完成，但没找到 portable_config，请手动选择目录")
                    messagebox.showinfo(APP_TITLE, f"mpv-lazy 安装完成\n\n{b}\n配置目录：{a or '未识别'}")
                    return
                elif kind == "error":
                    self.install_running = False
                    self.install_progress["value"] = 0
                    self.install_hint.config(text="安装失败：" + a)
                    messagebox.showerror(APP_TITLE, "安装失败：\n" + a)
                    return
        except queue.Empty:
            pass
        if self.install_running:
            self.after(200, self._install_poll)

    # ---------- 更新检测 ----------

    def start_update_check(self, manual=False):
        if self.update_running:
            if manual:
                messagebox.showinfo(APP_TITLE, "正在检查更新，请稍候…")
            return
        self.update_running = True
        if manual:
            self.status.config(text="正在检查更新…")
        known = load_settings().get("lazy_tag", "")
        threading.Thread(target=self._update_worker, args=(known, manual), daemon=True).start()
        self.after(300, self._update_poll)

    def _update_worker(self, known_tag, manual):
        lazy_tag = None
        tool = None
        try:
            lazy_tag = check_lazy_update(known_tag)
        except Exception:
            lazy_tag = None
        try:
            tool = check_tool_update()
        except Exception:
            tool = None
        self.update_queue.put(("done", lazy_tag, tool, manual))

    def _update_poll(self):
        try:
            kind, lazy_tag, tool, manual = self.update_queue.get_nowait()
        except queue.Empty:
            if self.update_running:
                self.after(400, self._update_poll)
            return
        self.update_running = False
        msgs = []
        if lazy_tag:
            msgs.append(f"mpv-lazy 有新版本 {lazy_tag}")
        if tool:
            msgs.append(f"本工具有新版本 {tool['version']}")
        if msgs:
            self.status.config(text="⚠ " + "；".join(msgs))
            st = load_settings()
            if lazy_tag and st.get("last_notified_tag") != lazy_tag:
                st["last_notified_tag"] = lazy_tag
                save_settings(st)
                messagebox.showinfo(
                    APP_TITLE,
                    f"发现 mpv-lazy 新版本：{lazy_tag}\n\n"
                    f"可以到「基础模式」页点『下载并安装 mpv-lazy』更新。")
            if tool:
                messagebox.showinfo(
                    APP_TITLE,
                    f"本工具有新版本 {tool['version']}\n\n{tool.get('notes', '')}\n{tool.get('url', '')}")
        elif manual:
            known = load_settings().get("lazy_tag", "")
            if known:
                messagebox.showinfo(APP_TITLE, f"已是最新版本（本地记录：{known}）。")
            else:
                messagebox.showinfo(
                    APP_TITLE,
                    "没有可比较的版本记录。\n\n"
                    "用本工具安装过 mpv-lazy 之后才会记录版本号，之后再来检查才有意义。\n"
                    "（本工具的自身更新源尚未配置，配置后也会一起检查。）")

    def basic_collect(self):
        """按当前选择算出要写入的键值与 shader 列表。"""
        preset = get_basic_preset(self.basic_content.get(), self.basic_prefer.get())
        params = dict(preset["params"])
        catalog_names = [x["name"] for x in self.shader_catalog]
        picked, missing = resolve_shader_slots(preset["shaders"], catalog_names)
        paths = []
        for name in picked:
            key = "shader:" + name
            if key in self.vars and self.vars[key].get().strip():
                paths.append(self.vars[key].get().strip())
        if paths:
            params["glsl-shaders"] = '"' + ";".join(paths) + '"'
        return params, picked, missing, preset["note"]

    def basic_refresh_preview(self):
        if not hasattr(self, "basic_preview"):
            return
        try:
            params, picked, missing, note = self.basic_collect()
        except Exception as e:
            params, picked, missing, note = {}, [], [], f"（预览失败：{e}）"
        target = Path(self.basic_dir.get().strip() or ".")
        if self.basic_write.get() == WRITE_MODE_INCLUDE:
            body = build_include_text(params, note)
            text = f"# 将写入 {target / INCLUDE_FILENAME}\n" \
                   f"# 并在 {target / 'mpv.conf'} 末尾追加一行 include\n\n" + body
        else:
            main = target / "mpv.conf"
            lines = read_text(main).splitlines()
            _, changes = apply_params_to_lines(lines, params)
            text = f"# 将合并进 {main}\n# 共 {len(changes)} 处改动\n\n" + "\n".join(changes)
        if picked:
            text += "\n# 选用的 shader：" + " → ".join(picked) + "\n"
        if missing:
            text += "# 本机缺少、已跳过：" + "、".join(missing) + "\n"
        self.basic_preview.config(state="normal")
        self.basic_preview.delete("1.0", "end")
        self.basic_preview.insert("1.0", text)
        self.basic_preview.config(state="disabled")

    def basic_generate(self):
        target = Path(self.basic_dir.get().strip())
        if not target.is_dir():
            messagebox.showerror(APP_TITLE, "配置目录不存在：\n" + str(target))
            return
        params, picked, missing, note = self.basic_collect()
        if self.basic_write.get() == WRITE_MODE_INCLUDE:
            prompt = (f"将在下列位置写入配置：\n\n"
                      f"  {target / INCLUDE_FILENAME}\n"
                      f"  并在 {target / 'mpv.conf'} 追加一行 include\n\n"
                      f"（原文件会自动备份）是否继续？")
        else:
            prompt = (f"将把 {len(params)} 项设置合并进：\n\n  {target / 'mpv.conf'}\n\n"
                      f"原有内容保留，同名项会被覆盖，原文件自动备份。是否继续？")
        if not messagebox.askyesno(APP_TITLE, prompt):
            return
        try:
            if self.basic_write.get() == WRITE_MODE_INCLUDE:
                path, backup = write_include(target, build_include_text(params, note))
                changed, main_backup, msg = ensure_include_line(target / "mpv.conf")
                detail = f"已写入 {path.name}"
                if changed:
                    detail += "，并已在 mpv.conf 追加 include 行"
                else:
                    detail += f"，{msg}"
                if backup or main_backup:
                    detail += "（已备份原文件）"
            else:
                changes, backup = merge_into_file(target / "mpv.conf", params)
                detail = f"已合并 {len(changes)} 处改动到 mpv.conf"
                if backup:
                    detail += "（已备份）"
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"写入失败：{e}\n\n如果目录在 Program Files 下，请用管理员身份运行。")
            return
        if missing:
            detail += f"；本机缺少 shader：{'、'.join(missing)}（已跳过）"
        self.basic_result.config(text=detail)
        self.status.config(text=detail)
        messagebox.showinfo(APP_TITLE, detail)

    def make_scrollable(self, parent, store=None):
        """把内容放进带纵向滚动条的容器，便于容纳扫描出的大量 shader。"""
        canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        if store:
            setattr(self, store, canvas)
        return inner

    def add_param(self, parent, key, label, description, options, editable=None):
        """创建一行「勾选 + 值」。同一个 key 复用已有的 Tk 变量，
        这样搜索页再渲染一份也不会和原页面失联。"""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        if key not in self.checks:
            self.checks[key] = tk.BooleanVar(value=False)
            self.vars[key] = tk.StringVar(value=options[0] if options else "")
        self.desc[key] = description
        self.option_lists[key] = options
        en = self.checks[key]
        var = self.vars[key]
        if editable is None:
            editable = key in EDITABLE_PARAMS
        cb = ttk.Checkbutton(row, text=label, variable=en, command=lambda k=key:self.select_param(k))
        cb.pack(side="left", fill="x", expand=True)
        combo = ttk.Combobox(row, textvariable=var, values=options,
                             state="normal" if editable else "readonly", width=21)
        combo.pack(side="right")
        combo.bind("<<ComboboxSelected>>", lambda e,k=key:self.select_param(k))
        if editable:
            combo.bind("<Return>", lambda e,k=key:self.select_param(k))
            combo.bind("<FocusOut>", lambda e,k=key:self.select_param(k))
        return row

    def add_shader(self, parent, name, description, path=None):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        key = "shader:" + name
        en = tk.BooleanVar(value=False)
        self.checks[key] = en
        self.desc[key] = description
        self.vars[key] = tk.StringVar(value=path if path is not None else SHADER_PATHS.get(name, ""))
        if key not in self.shader_order:
            self.shader_order.append(key)
        ttk.Checkbutton(row, text=name, variable=en, command=lambda k=key:self.select_param(k)).pack(side="left", fill="x", expand=True)
        ttk.Label(row, textvariable=self.vars[key], font=("Consolas", 8), foreground="#666666", wraplength=240).pack(side="right", padx=4)
        ttk.Button(row, text="选择/修改", command=lambda k=key:self.browse_shader(k)).pack(side="right")

    def add_memc(self, parent, name, description, path):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        key = "memc:" + name
        en = tk.BooleanVar(value=False)
        self.checks[key] = en
        self.desc[key] = description
        self.vars[key] = tk.StringVar(value=path)
        ttk.Checkbutton(row, text=name, variable=en, command=lambda k=key:self.toggle_memc(k)).pack(side="left", fill="x", expand=True)
        ttk.Label(row, textvariable=self.vars[key], font=("Consolas", 8), foreground="#666666", wraplength=240).pack(side="right", padx=4)

    def toggle_memc(self, key):
        """同一时间只允许启用一个 VapourSynth 滤镜。"""
        if self.checks[key].get():
            for k in self.checks:
                if k.startswith("memc:") and k != key:
                    self.checks[k].set(False)
        self.select_param(key)

    def select_param(self, key):
        title = key.replace("shader:","").replace("memc:","")
        self.explain.config(state="normal")
        self.explain.delete("1.0","end")
        self.explain.insert("end", title + "\n", "heading")
        self.explain.insert("end", self.desc.get(key,"") + "\n\n")
        if key.startswith("shader:"):
            name = key[7:]
            meta = SHADERS.get(name)
            if meta:
                q, load = meta[1], meta[2]
            else:
                q, load = 4, 4
            self.explain.insert("end", f"画质提升：{'★'*min(5,(q+1)//2)}\n")
            self.explain.insert("end", f"GPU负载：{'★'*min(5,(load+1)//2)}\n")
            self.explain.insert("end", f"预设路径：{self.vars[key].get()}\n")
            self.explain.insert("end", "\n注意：Shader 链的顺序、输入分辨率以及具体 Shader 版本都会改变实际效果。")
        elif key.startswith("memc:"):
            self.explain.insert("end", f"脚本路径：{self.vars[key].get()}\n")
            self.explain.insert("end", "勾选后会直接生成 vf=vapoursynth=\"...\" 配置行；同一时间只会启用一项。\n")
            self.explain.insert("end", "外部 MEMC 已生成真实中间帧时，不要再开内置 interpolation=yes。\n")
            self.explain.insert("end", "推荐：中端 MVT_LQ，NVIDIA 高端 RIFE_NV。\n")
        else:
            opts = self.option_lists[key]
            self.explain.insert("end", "可选值：\n")
            for x in opts:
                self.explain.insert("end", f"  • {x}\n")
            self.explain.insert("end", "\n建议：先根据目标画质选择，再观察 GPU Render Time 与 dropped frames，而不是只看理论评分。")
        self.explain.config(state="disabled")
        self.update_all()

    def browse_shader(self, key):
        paths = filedialog.askopenfilenames(filetypes=[("Shader","*.glsl *.hook *.slang *.spv"),("All","*.*")])
        if paths:
            self.vars[key].set(";".join(paths))
            self.checks[key].set(True)
            self.select_param(key)

    def refresh_search(self):
        """在核心参数 + 原生选项里搜索，结果直接渲染成可操作的控件行。"""
        if not hasattr(self, "search_inner"):
            return
        for child in self.search_inner.winfo_children():
            child.destroy()
        q = self.search_var.get().strip().lower()
        if not q:
            ttk.Label(self.search_inner, text="（输入后显示匹配项）",
                      foreground="#888888").pack(anchor="w")
            self.search_hint.config(text="")
            return
        matches = []
        for cat, items in PARAMS.items():
            for key, label, description, options, qq, load in items:
                if q in key.lower() or q in label.lower() or q in cat.lower():
                    matches.append((key, label, description, options, None))
        for group, key, label, desc, values, typ in native_items():
            if q in key.lower() or q in label.lower() or q in group.lower() or q in desc.lower():
                matches.append((key, label, desc, values, typ in NATIVE_EDITABLE_TYPES))
        if not matches:
            ttk.Label(self.search_inner, text="没有匹配项", foreground="#888888").pack(anchor="w")
            self.search_hint.config(text="0 项匹配")
            return
        for key, label, description, options, editable in matches[:30]:
            ttk.Label(self.search_inner, text=key, foreground="#888888",
                      font=("Consolas", 8)).pack(anchor="w")
            self.add_param(self.search_inner, key, label, description, options, editable=editable)
        tail = "（只显示前 30 条）" if len(matches) > 30 else ""
        self.search_hint.config(text=f"{len(matches)} 项匹配{tail}")

    def generate(self):
        lines = [f"# {APP_TITLE} {APP_VERSION}", "# Generated configuration", ""]
        sections = {}
        for cat, items in PARAMS.items():
            vals=[]
            for key, label, desc, opts, q, load in items:
                if self.checks[key].get() and self.vars[key].get().strip():
                    vals.append(f"{key}={self.vars[key].get().strip()}")
            if vals:
                sections[cat]=vals
        for cat, vals in sections.items():
            lines += [f"# {cat}"] + vals + [""]
        # 原生扩展项
        native_vals = []
        for group, key, label, desc, values, typ in native_items():
            if self.checks.get(key) and self.checks[key].get() and self.vars[key].get().strip():
                native_vals.append(f"{key}={self.vars[key].get().strip()}")
        if native_vals:
            lines += ["# 原生扩展"] + native_vals + [""]
        shaders=[]
        ordered = [k for k in self.shader_order if k in self.checks]
        for key in self.checks:
            if key.startswith("shader:") and key not in ordered:
                ordered.append(key)
        for key in ordered:
            if self.checks[key].get() and self.vars[key].get().strip():
                shaders.append(self.vars[key].get().strip())
        if shaders:
            lines += ["# Shader / 锐化", f'glsl-shaders="{";".join(shaders)}"', ""]
        memc_list=[]
        for key in self.checks:
            if key.startswith("memc:") and self.checks[key].get() and self.vars[key].get().strip():
                memc_list.append(self.vars[key].get().strip())
        if memc_list:
            lines += ["# VS 补帧 / VapourSynth", f'vf=vapoursynth="{memc_list[0]}"', ""]
        if getattr(self, "custom_unknown", "").strip():
            lines += ["# 导入配置中未收录的选项", self.custom_unknown, ""]
        return "\n".join(lines)

    def update_all(self):
        if self.mode.get() == "modify" and self.source_lines:
            conf, changes = self.build_merged_text()
            self.change_count = len(changes)
            self.last_preview_text = conf
            self.preview_label.config(text=f"修改预览（原文件 + {self.change_count} 处改动）")
            base = f"上传修改模式：{Path(self.source_path).name}　改动 {self.change_count} 处"
        else:
            conf = self.generate()
            self.change_count = 0
            self.last_preview_text = conf
            self.preview_label.config(text="实时生成的 mpv.conf")
            base = "完全创造模式：从零生成新配置"
        self.mode_label.config(text=base + self.advanced_hint())
        self.text.delete("1.0","end")
        self.text.insert("1.0",conf)
        self.update_score_only()

    def advanced_hint(self):
        """简易模式下提示"有高级选项被隐藏但会写入"。"""
        if self.advanced.get():
            return "　｜　高级模式"
        hidden = [k for k in self.advanced_param_keys if self.checks.get(k) and self.checks[k].get()]
        if hidden:
            return f"　｜　简易模式　⚠ 已启用 {len(hidden)} 个高级选项（会写入配置）"
        return "　｜　简易模式"

    def on_advanced_change(self):
        self.apply_advanced_mode()
        save_settings({"advanced": bool(self.advanced.get())})
        self.update_all()
        self.status.config(text="已切换到高级模式：显示全部页面" if self.advanced.get()
                           else "已切换到简易模式：只显示常用页面（已勾选的高级选项仍会写入）")

    def apply_advanced_mode(self):
        """按简易/高级模式显示或隐藏高级标签页。"""
        if not hasattr(self, "nb"):
            return
        advanced = self.advanced.get()
        for widget, text in self.advanced_tabs:
            wid = str(widget)
            if wid in self.nb.tabs():
                if advanced:
                    self.nb.tab(widget, state="normal")
                else:
                    if self.nb.select() == wid:
                        try:
                            self.nb.select(0)
                        except tk.TclError:
                            pass
                    self.nb.tab(widget, state="hidden")
            elif advanced:
                self.nb.add(widget, text=text)

    def update_score_only(self):
        active=[k for k,v in self.checks.items() if v.get()]
        scores=score_active(active)
        quality=scores["quality"]; sharp=scores["sharp"]; smooth=scores["smooth"]
        color=scores["color"]; stability=scores["stability"]; load=scores["load"]
        overall=round((quality*0.28+sharp*0.22+smooth*0.18+color*0.12+stability*0.20))
        grade="极限画质" if overall>=92 else "高画质" if overall>=82 else "均衡" if overall>=70 else "轻量"
        self.overall.config(text=f"综合 {overall}/100   |   {grade}   |   GPU负载等级 {load}/100")
        for n,val in {"清晰度":quality,"锐度":sharp,"流畅度":smooth,"色彩/观感":color,"稳定性":stability,"GPU负载":load}.items():
            self.bars[n]["value"]=val
        if load>=85:
            msg="⚠ 高负载：建议实际监控 render time / dropped frames"
        elif load>=65:
            msg="● 中高负载：适合中高端 GPU"
        else:
            msg="● 轻中负载：日常播放较稳"
        self.recommend.config(text=msg)
        missing = [k for k in self.checks
                   if k.startswith(("shader:", "memc:")) and self.checks[k].get()
                   and not self.vars[k].get().strip()]
        invalid = []
        for k, var in self.checks.items():
            if var.get() and not k.startswith(("shader:", "memc:")):
                ok, msg = validate_native_value(k, self.vars[k].get())
                if not ok:
                    invalid.append(f"{k}（{msg}）")
        warn = []
        if missing:
            warn.append(f"{len(missing)} 个已勾选的 shader/vpy 没有路径，已跳过")
        if invalid:
            warn.append(f"{len(invalid)} 个值不合法：" + "、".join(invalid[:3]))
        if warn:
            self.status.config(text=f"已启用 {len(active)} 项参数  ⚠ " + "；".join(warn))
        else:
            self.status.config(text=f"已启用 {len(active)} 项参数")

    def high_quality(self):
        preset={"vo":"gpu-next","gpu-api":"d3d11","hwdec":"auto-safe","video-sync":"display-resample",
                "scale":"ewa_lanczossharp","cscale":"ewa_lanczossharp","dscale":"mitchell",
                "sigmoid-upscaling":"yes","deband":"yes","interpolation":"yes","tscale":"mitchell",
                "sub-auto":"fuzzy","sub-ass-override":"no","cache":"yes"}
        for k,v in preset.items():
            if k in self.vars:
                self.checks[k].set(True); self.vars[k].set(v)
        self.update_all()

    # ---------- 快捷组合预设 ----------

    def set_base(self, params):
        """先清空当前配置，再写入一组基础参数。"""
        self.clear_all(silent=True)
        for k, v in params.items():
            if k in self.vars:
                self.checks[k].set(True)
                self.vars[k].set(v)

    def set_shader_combo(self, names):
        """清空所有 glsl Shader，再按顺序勾选 combo 中的 shader。"""
        for key in self.checks:
            if key.startswith("shader:"):
                self.checks[key].set(False)
        order = []
        for name in names:
            key = "shader:" + name
            if key in self.checks:
                self.checks[key].set(True)
                if SHADER_PATHS.get(name):
                    self.vars[key].set(SHADER_PATHS[name])
                order.append(key)
        for key in self.shader_order:
            if key not in order and key in self.checks:
                order.append(key)
        for key in self.checks:
            if key.startswith("shader:") and key not in order:
                order.append(key)
        self.shader_order = order

    def clear_shaders(self):
        for key in self.checks:
            if key.startswith("shader:") or key.startswith("memc:"):
                self.checks[key].set(False)
        self.update_all()
        self.status.config(text="已清空 Shader / MEMC 选择")

    def preset_sharp_base(self):
        self.set_base(BASE_SHARP)
        self.update_all()
        self.status.config(text="已套用：最锐利基础参数")

    def preset_general_sharp(self):
        self.set_base(BASE_SHARP)
        self.set_shader_combo(["KrigBilateral / CfL", "FSRCNNX x2_16", "Adaptive_sharpen"])
        self.update_all()
        self.status.config(text="已套用：通用锐利链（KrigBilateral → FSRCNNX x2_16 → Adaptive_sharpen）")

    def preset_anime_sharp(self):
        self.set_base(BASE_SHARP)
        self.set_shader_combo([
            "Anime4K Clamp_Highlights", "Anime4K Restore_CNN_M",
            "Anime4K Upscale_CNN_x2_M", "Anime4K Upscale_GAN_x2_S",
            "Adaptive_sharpen",
        ])
        self.update_all()
        self.status.config(text="已套用：动漫极致链（Clamp → Restore → Upscale → Upscale → Adaptive_sharpen）")

    def preset_internal_memc(self):
        self.set_base({})
        params = {"video-sync": "display-resample", "interpolation": "yes",
                  "tscale": "oversample", "hr-seek-framedrop": "no"}
        for k, v in params.items():
            if k in self.vars:
                self.checks[k].set(True)
                self.vars[k].set(v)
        self.update_all()
        self.status.config(text="已套用：内置补帧（display-resample + interpolation + tscale=oversample）")

    def preset_external_memc(self):
        self.set_base({})
        params = {"video-sync": "display-resample", "interpolation": "no",
                  "hr-seek-framedrop": "no"}
        for k, v in params.items():
            if k in self.vars:
                self.checks[k].set(True)
                self.vars[k].set(v)
        key = "memc:RIFE_NV"
        if key in self.checks:
            self.checks[key].set(True)
            self.vars[key].set(MEMC_PRESETS["RIFE_NV"][1])
        self.update_all()
        self.status.config(text="已套用：外部 MEMC 模板（RIFE_NV，生成注释行，需自装 VS + k7sfunc）")

    # ---------- mpv-lazy 实机预设 ----------

    def _apply_lazy_base(self):
        self.set_base(BASE_SHARP)
        for k, v in {"hwdec": "auto-copy", "interpolation": "yes",
                     "tscale": "oversample", "hr-seek-framedrop": "no"}.items():
            if k in self.vars:
                self.checks[k].set(True)
                self.vars[k].set(v)

    def preset_lazy_general(self):
        self._apply_lazy_base()
        self.set_shader_combo(["FSRCNNX x2_16", "Adaptive_sharpen"])
        self.update_all()
        self.status.config(text="已套用：mpv-lazy 通用锐利（FSRCNNX x2_16 → Adaptive_sharpen）")

    def preset_lazy_anime(self):
        self._apply_lazy_base()
        self.set_shader_combo(["Anime4K Restore_CNN_L", "Anime4K Upscale_GAN_x2_M", "Adaptive_sharpen"])
        self.update_all()
        self.status.config(text="已套用：mpv-lazy 动漫锐利（Restore_CNN_L → Upscale_GAN_x2_M → Adaptive_sharpen）")

    def preset_lazy_anime_max(self):
        self._apply_lazy_base()
        self.set_shader_combo(["Ani4Kv2 ArtCNN", "Anime4K Restore_CNN_L",
                               "Anime4K Upscale_GAN_x2_M", "QCOM SGEDS", "Adaptive_sharpen"])
        self.update_all()
        self.status.config(text="已套用：mpv-lazy 最强动漫（Ani4Kv2 → Restore → Upscale_GAN → QCOM → Adaptive）")

    def preset_lazy_rife(self):
        self.set_base({})
        for k, v in {"video-sync": "display-resample", "interpolation": "no",
                     "hr-seek-framedrop": "no", "hwdec": "auto-copy"}.items():
            if k in self.vars:
                self.checks[k].set(True)
                self.vars[k].set(v)
        key = "memc:RIFE_NV"
        if key in self.checks:
            self.checks[key].set(True)
            self.vars[key].set(MEMC_PRESETS["RIFE_NV"][1])
        self.update_all()
        self.status.config(text="已套用：mpv-lazy RIFE_NV 补帧模板（取消注释 vf 行，配合 ~~/vs/MEMC_RIFE_NV.vpy）")

    def open_guide(self):
        # 打包后 md 在解包目录（sys._MEIPASS），不能用 __file__ 推
        p = doc_path("MPV_Shader搭配说明书.md")
        if p.exists():
            os.startfile(str(p))
            self.status.config(text="已打开搭配说明书")
        else:
            hint = ('\n\n打包时要把 md 一起带上：--add-data "*.md;."'
                    if is_frozen() else "")
            messagebox.showinfo(APP_TITLE, "未找到说明书文件：\n" + str(p) + hint)

    def open_url(self, url):
        """用系统默认浏览器打开链接（不下载任何文件）。"""
        try:
            ok = webbrowser.open(url)
        except Exception:
            ok = False
        if ok:
            self.status.config(text="已在浏览器打开：" + url)
        else:
            self.clipboard_clear(); self.clipboard_append(url)
            messagebox.showinfo(APP_TITLE, "没能自动打开浏览器，链接已复制到剪贴板：\n\n" + url)

    # ---------- 下载器 ----------

    def dl_browse(self):
        d = filedialog.askdirectory(initialdir=self.dl_target.get() or "C:\\")
        if d:
            self.dl_target.set(d)

    def dl_select(self, state):
        for var in self.dl_checks.values():
            var.set(bool(state))

    def dl_open_target(self):
        t = Path(self.dl_target.get().strip())
        if t.is_dir():
            os.startfile(str(t))
        else:
            messagebox.showerror(APP_TITLE, "目标目录不存在：\n" + str(t))

    def dl_start(self):
        if self.dl_running:
            messagebox.showinfo(APP_TITLE, "正在执行中，请稍候…")
            return
        target = Path(self.dl_target.get().strip())
        if not target.is_dir():
            messagebox.showerror(APP_TITLE, "目标目录不存在：\n" + str(target))
            return
        items = [it for it in SHADER_DOWNLOADS if self.dl_checks[it["name"]].get()]
        if not items:
            messagebox.showinfo(APP_TITLE, "还没有勾选任何项目。")
            return
        if not self.dl_notified:
            ok = messagebox.askyesno(
                APP_TITLE,
                "下载会联网访问以下域名：\n"
                "  · raw.githubusercontent.com\n"
                "  · 你选择的加速线路（如 ghproxy.net）\n\n"
                "除下载功能外，本工具全程离线、不上传任何数据。是否继续？")
            if not ok:
                return
            self.dl_notified = True
            save_settings({"dl_notified": True, "mirror": self.dl_mirror.get()})
        self.dl_running = True
        self.dl_progress["value"] = 0
        self.dl_progress["maximum"] = len(items)
        for it in items:
            self.dl_status[it["name"]].set("排队中")
        threading.Thread(target=self._dl_worker,
                         args=(items, target, self.dl_mirror.get(), self.dl_overwrite.get()),
                         daemon=True).start()
        self.after(120, self._dl_poll)

    def _dl_worker(self, items, target, mirror_mode, overwrite):
        for it in items:
            name = it["name"]
            dest = Path(target) / it["dest"]
            self.dl_queue.put(("status", name, "下载中…"))
            try:
                if dest.exists() and not overwrite:
                    self.dl_queue.put(("status", name, "已存在，跳过"))
                    self.dl_queue.put(("tick", name, None))
                    continue
                data = None
                last_err = None
                used = ""
                for prefix in build_url_candidates(it["url"], mirror_mode):
                    try:
                        data = http_fetch(prefix + it["url"] if prefix else it["url"])
                        used = "直连" if not prefix else prefix.strip("/").replace("https://", "")
                        break
                    except Exception as e:
                        last_err = e
                if data is None:
                    raise last_err or RuntimeError("下载失败")
                if b"//!" not in data[:4096]:
                    raise RuntimeError("内容不像 mpv shader（缺少 //! 标记）")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and overwrite:
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    shutil.copy2(dest, dest.with_name(dest.name + f".bak-{stamp}"))
                dest.write_bytes(data)
                self.dl_queue.put(("status", name, f"完成 {len(data)//1024} KB（{used}）"))
            except Exception as e:
                self.dl_queue.put(("status", name, f"失败：{e}"))
            self.dl_queue.put(("tick", name, None))
        self.dl_queue.put(("done", None, None))

    def dl_check_links(self):
        if self.dl_running:
            messagebox.showinfo(APP_TITLE, "正在执行中，请稍候…")
            return
        self.dl_running = True
        self.dl_progress["value"] = 0
        self.dl_progress["maximum"] = len(SHADER_DOWNLOADS)
        for it in SHADER_DOWNLOADS:
            self.dl_status[it["name"]].set("检查中…")
        threading.Thread(target=self._dl_check_worker, args=(self.dl_mirror.get(),),
                         daemon=True).start()
        self.after(120, self._dl_poll)

    def _dl_check_worker(self, mirror_mode):
        for it in SHADER_DOWNLOADS:
            name = it["name"]
            result = "失败"
            for prefix in build_url_candidates(it["url"], mirror_mode):
                try:
                    status, length = http_head(prefix + it["url"] if prefix else it["url"])
                    kb = f"{int(length)//1024} KB" if length and str(length).isdigit() else "?"
                    result = f"OK {status} / {kb}" + ("（镜像）" if prefix else "（直连）")
                    break
                except urllib.error.HTTPError as e:
                    result = f"HTTP {e.code}"
                except Exception as e:
                    result = f"失败：{type(e).__name__}"
            self.dl_queue.put(("status", name, result))
            self.dl_queue.put(("tick", name, None))
        self.dl_queue.put(("done", None, None))

    def _dl_poll(self):
        try:
            while True:
                kind, name, text = self.dl_queue.get_nowait()
                if kind == "status":
                    if name in self.dl_status:
                        self.dl_status[name].set(text)
                elif kind == "tick":
                    try:
                        self.dl_progress["value"] = float(self.dl_progress["value"]) + 1
                    except (TypeError, ValueError):
                        self.dl_progress["value"] = 1
                elif kind == "done":
                    self.dl_running = False
                    self.status.config(text="任务结束")
                    self.dl_hint.config(text="任务结束。下载完成后可到「扫描 glsl/vpy」页重新扫描本机文件。")
                    return
        except queue.Empty:
            pass
        if self.dl_running:
            self.after(150, self._dl_poll)

    # ---------- 扫描 glsl / vpy ----------

    def browse_scan_dir(self):
        d = filedialog.askdirectory(initialdir=self.scan_dir.get() or "C:\\")
        if d:
            self.scan_dir.set(d)
            self.scan_dirs()

    def scan_dirs(self):
        root = Path(self.scan_dir.get().strip())
        if not root.is_dir():
            messagebox.showerror(APP_TITLE, "目录不存在：\n" + str(root))
            return
        if root.name.lower() == "portable_config":
            pc = root
        elif root.name.lower() in ("shaders", "vs"):
            # 直接选了 shaders / vs 子目录时，回到 portable_config 层级，才能同时看到两类文件
            pc = root.parent
        elif (root / "portable_config").is_dir():
            pc = root / "portable_config"
        else:
            pc = root
        shaders, vpy = scan_lazy(pc)
        if not shaders and not vpy:
            # 兜底：目录层级不对时，直接递归扫描 .glsl / .vpy
            for p in sorted(root.rglob("*")):
                if not p.is_file():
                    continue
                if p.suffix.lower() in SHADER_EXTS:
                    shaders.append(p)
                elif p.suffix.lower() in VS_EXTS:
                    vpy.append(p)
        same_target = self.lazy_pc is not None and Path(pc).resolve() == Path(self.lazy_pc).resolve()
        used_paths = set()
        for k, var in self.vars.items():
            if (k.startswith("shader:") or k.startswith("memc:")) and var.get().strip():
                used_paths.add(norm_mpv_path(var.get().strip()))
        self.scan_found = []
        for p in shaders + vpy:
            kind = "GLSL" if p.suffix.lower() in SHADER_EXTS else "VPY"
            try:
                rel = p.relative_to(pc).as_posix()
            except ValueError:
                rel = p.name
            # 只有扫描的目录就是当前目标目录时才用 ~~/，否则用绝对路径，避免 mpv 找不到文件
            mpv = ("~~/" + rel) if same_target else str(p).replace("\\", "/")
            if kind == "GLSL":
                key = self.match_shader_key(mpv)
                name = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            else:
                key = self.match_memc_key(mpv)
                name = p.stem
            in_list = norm_mpv_path(mpv) in used_paths or (bool(key) and key in self.checks)
            self.scan_found.append({
                "kind": kind, "abs": str(p), "mpv": mpv, "name": name,
                "rel": rel, "in_list": in_list, "pc": str(pc),
            })
        self.scan_missing = []
        for name, path in SHADER_PATHS.items():
            if path and not (pc / norm_mpv_path(path)).is_file():
                self.scan_missing.append({"kind": "GLSL", "name": name, "mpv": path, "rel": norm_mpv_path(path)})
        for name, (desc, path) in MEMC_PRESETS.items():
            if path and not (pc / norm_mpv_path(path)).is_file():
                self.scan_missing.append({"kind": "VPY", "name": name, "mpv": path, "rel": norm_mpv_path(path)})
        self.populate_scan_tree()
        path_note = "路径写成 ~~/（当前目标目录）" if same_target else "路径写成绝对路径（该目录不是当前目标目录）"
        self.scan_status.config(
            text=(f"目录：{pc}\n"
                  f"实际存在 {len(shaders)} 个 glsl / {len(vpy)} 个 vpy，其中已进列表 "
                  f"{sum(1 for x in self.scan_found if x['in_list'])} 个\n"
                  f"构建器已知但该目录缺失 {len(self.scan_missing)} 个（所以列表里看不到它们）\n"
                  f"{path_note}"))
        self.status.config(text=f"扫描完成：{len(shaders)} glsl / {len(vpy)} vpy")

    def populate_scan_tree(self):
        self.scan_tree.delete(*self.scan_tree.get_children())
        for i, it in enumerate(self.scan_found):
            state = "已在列表" if it["in_list"] else "可导入"
            self.scan_tree.insert("", "end", iid="f%d" % i, values=(state, it["kind"], it["mpv"]))
        for i, it in enumerate(self.scan_missing):
            self.scan_tree.insert("", "end", iid="m%d" % i, values=("缺失", it["kind"], it["mpv"]))

    def copy_scan_path(self):
        sel = self.scan_tree.selection()
        if not sel:
            return
        iid = sel[0]
        item = self.scan_found[int(iid[1:])] if iid.startswith("f") else self.scan_missing[int(iid[1:])]
        self.clipboard_clear(); self.clipboard_append(item["mpv"])
        self.status.config(text="已复制路径：" + item["mpv"])

    def import_scan_items(self, only_selected=True):
        if not self.scan_found:
            self.scan_dirs()
        if not self.scan_found:
            return
        if only_selected:
            items = []
            for iid in self.scan_tree.selection():
                if iid.startswith("f"):
                    items.append(self.scan_found[int(iid[1:])])
            if not items:
                self.status.config(text="没有选中任何行：先在列表里点一行（可 Ctrl/Shift 多选），再点『导入选中』")
                return
        else:
            items = [x for x in self.scan_found if not x["in_list"]]
        used_paths = set()
        for k, var in self.vars.items():
            if (k.startswith("shader:") or k.startswith("memc:")) and var.get().strip():
                used_paths.add(norm_mpv_path(var.get().strip()))
        added_keys = []
        for it in items:
            if norm_mpv_path(it["mpv"]) in used_paths:
                continue
            if it["kind"] == "GLSL":
                key = "shader:" + it["name"]
                if key in self.checks:
                    continue
                self.add_shader(self.shader_inner, it["name"], f"扫描导入：{it['rel']}", path=it["mpv"])
            else:
                key = "memc:" + it["name"]
                if key in self.checks:
                    continue
                self.add_memc(self.memc_inner, it["name"], f"扫描导入：{it['rel']}", it["mpv"])
            added_keys.append(key)
            used_paths.add(norm_mpv_path(it["mpv"]))

        # 「导入选中」= 导入并直接勾选，立刻写进右侧预览
        if only_selected:
            memc_done = False
            for key in added_keys:
                if key.startswith("memc:"):
                    if memc_done:
                        continue
                    memc_done = True
                self.checks[key].set(True)

        self.update_all()
        self.scan_dirs()
        if not added_keys:
            self.status.config(text="没有新文件需要导入（扫描到的都已经在列表里）。要写入请到 Shader / VS 补帧 页勾选已有条目")
            return
        has_shader = any(k.startswith("shader:") for k in added_keys)
        has_memc = any(k.startswith("memc:") for k in added_keys)
        if has_shader:
            self.nb.select(self.shader_frame)
            if hasattr(self, "shader_canvas"):
                self.shader_canvas.update_idletasks()
                self.shader_canvas.yview_moveto(1.0)
        elif has_memc:
            self.nb.select(self.memc_frame)
            if hasattr(self, "memc_canvas"):
                self.memc_canvas.update_idletasks()
                self.memc_canvas.yview_moveto(1.0)
        if only_selected:
            self.status.config(text=f"已导入并勾选 {len(added_keys)} 个（新条目在页面最下方）→ 右侧预览已更新，保存/应用修改即可写入")
        else:
            self.status.config(text=f"已导入 {len(added_keys)} 个（新条目在页面最下方，未勾选）→ 勾选后才会写进配置")

    def export_scan_list(self):
        if not self.scan_found:
            self.scan_dirs()
        if not self.scan_found:
            return
        p = filedialog.asksaveasfilename(defaultextension=".md", initialfile="glsl_vpy_清单.md",
                                         filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
        if not p:
            return
        lines = ["# glsl / vpy 扫描清单", "", f"目录：{self.scan_dir.get()}", "",
                 f"## 实际存在（{len(self.scan_found)}）"]
        for it in self.scan_found:
            lines.append(f"- [{it['kind']}] `{it['mpv']}`" + ("（已在列表）" if it["in_list"] else ""))
        lines += ["", f"## 构建器已知但缺失（{len(self.scan_missing)}）"]
        for it in self.scan_missing:
            lines.append(f"- [{it['kind']}] `{it['mpv']}`（缺失）")
        Path(p).write_text("\n".join(lines), encoding="utf-8")
        self.status.config(text="清单已导出：" + p)

    def copy_conf(self):
        self.clipboard_clear(); self.clipboard_append(self.text.get("1.0","end"))
        self.status.config(text="配置已复制")

    def copy_text(self, text):
        self.clipboard_clear(); self.clipboard_append(text)
        self.status.config(text="分析报告已复制")

    def save_conf(self):
        """创造模式=另存为；修改模式=写回原文件（自动备份）。"""
        if self.mode.get() == "modify" and self.source_path:
            self.apply_modify()
        else:
            self.save_as()

    def save_as(self):
        p=filedialog.asksaveasfilename(defaultextension=".conf",initialfile="mpv.conf",
            filetypes=[("MPV config","*.conf"),("All files","*.*")])
        if p:
            text = self.last_preview_text or self.text.get("1.0","end")
            Path(p).write_text(text, encoding="utf-8")
            self.status.config(text="配置已保存：" + p)

    # ---------- 上传修改模式 ----------

    def on_mode_change(self):
        if self.mode.get() == "modify" and not self.source_path:
            self.upload_for_modify()
            if not self.source_path:
                self.mode.set("create")
        self.update_all()

    def upload_for_modify(self):
        if self.lazy_pc:
            init_dir = str(self.lazy_pc)
            init_file = "mpv.conf"
        else:
            init_dir = None
            init_file = ""
        p = filedialog.askopenfilename(title="上传要修改的 mpv.conf",
                                       initialdir=init_dir, initialfile=init_file,
                                       filetypes=[("MPV config","*.conf"),("All files","*.*")])
        if not p:
            return
        try:
            raw = Path(p).read_bytes()
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"读取失败：{e}")
            return
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig", errors="replace")
        # 上传前先记住已经勾选的 shader / vpy，上传后保留它们（否则会被文件内容清空）
        keep = {}
        for k, var in self.vars.items():
            if k.startswith("shader:") or k.startswith("memc:"):
                if self.checks[k].get() and var.get().strip():
                    keep[k] = var.get()
        self.source_path = p
        self.source_bom = bom
        self.source_newline = "\r\n" if "\r\n" in text else "\n"
        self.source_lines = text.splitlines()
        self.load_config_text(text)
        kept = 0
        for k, v in keep.items():
            if k in self.checks:
                self.vars[k].set(v)
                self.checks[k].set(True)
                kept += 1
        self.mode.set("modify")
        self.update_all()
        note = f"，保留了你上传前勾选的 {kept} 个 shader/vpy" if kept else ""
        self.status.config(text=f"已进入上传修改模式：{Path(p).name}{note}（参数以文件为准，改动会实时显示在预览）")

    def load_config_text(self, text):
        """把配置文本读进界面，并记录基线（用于计算改动）。"""
        self.clear_all(silent=True)
        self.baseline_params = {}
        self.baseline_shader_paths = []
        self.baseline_memc_path = None
        shader_keys = ("glsl-shaders", "glsl-shader", "glsl-shaders-append", "glsl-shader-append")
        for raw in text.splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = strip_inline_comment(v.strip())
            if k in self.checks:
                self.checks[k].set(True)
                self.vars[k].set(v)
                self.baseline_params[k] = v
            elif k in shader_keys:
                for path in split_mpv_list(v):
                    self.baseline_shader_paths.append(path)
                    key = self.match_shader_key(path)
                    if key and key in self.checks:
                        self.checks[key].set(True)
                        # 关键：保留原文件里的原始路径，避免"没改任何东西"也被判成改动
                        self.vars[key].set(path)
                    else:
                        self.add_dynamic_shader(path)
            elif k in ("vf", "vf-append"):
                path = extract_vapoursynth_path(v)
                if path:
                    self.baseline_memc_path = path
                    key = self.match_memc_key(path)
                    if key and key in self.checks:
                        self.checks[key].set(True)
                        self.vars[key].set(path)
                    else:
                        self.add_dynamic_memc(path)

    def add_dynamic_shader(self, path):
        """上传的配置里有、但库中没有的 shader 路径：动态加一条，保证可见可勾选。"""
        raw = str(path).strip().strip('"').strip("'")
        stem = Path(raw.replace("\\", "/")).stem or "shader"
        key = "shader:" + stem
        n = 1
        while key in self.checks and self.vars[key].get().strip() != raw:
            n += 1
            key = f"shader:{stem}#{n}"
        if key not in self.checks:
            self.add_shader(self.shader_inner, key[len("shader:"):], f"来自上传配置：{raw}", path=raw)
        self.checks[key].set(True)
        return key

    def add_dynamic_memc(self, path):
        """上传的配置里有、但库中没有的 vpy 路径：动态加一条。"""
        raw = str(path).strip().strip('"').strip("'")
        stem = Path(raw.replace("\\", "/")).stem or "memc"
        key = "memc:" + stem
        n = 1
        while key in self.checks and self.vars[key].get().strip() != raw:
            n += 1
            key = f"memc:{stem}#{n}"
        if key not in self.checks:
            self.add_memc(self.memc_inner, key[len("memc:"):], f"来自上传配置：{raw}", raw)
        self.checks[key].set(True)
        return key

    def build_merged_text(self):
        """在原文件基础上只应用改动，返回 (合并后的文本, 改动说明列表)。"""
        lines = list(self.source_lines)
        changes = []
        key_re = re.compile(r"^(\s*)(#?)\s*([A-Za-z0-9_.\-]+)\s*=\s*(.*)$")

        def find(key, active=True):
            for i, ln in enumerate(lines):
                m = key_re.match(ln)
                if m and m.group(3) == key and (bool(m.group(2)) != active):
                    return i, m
            return None, None

        appended = []

        # ---- 普通参数（核心 + 原生扩展）----
        param_keys = []
        for items in PARAMS.values():
            for key, label, desc, opts, q, load in items:
                param_keys.append(key)
        for group, key, label, desc, values, typ in native_items():
            param_keys.append(key)
        for key in param_keys:
            cur_on = self.checks[key].get()
            cur_val = self.vars[key].get().strip()
            base = self.baseline_params.get(key)
            if cur_on and cur_val:
                if base == cur_val:
                    continue
                idx, m = find(key, True)
                if idx is None:
                    idx, m = find(key, False)
                if idx is not None:
                    old = m.group(4).strip()
                    lines[idx] = m.group(1) + f"{key} = {cur_val}"
                    changes.append(f"{key}: {old} -> {cur_val}")
                else:
                    appended.append(f"{key} = {cur_val}")
                    changes.append(f"{key}: 新增 {cur_val}")
            elif base is not None:
                idx, m = find(key, True)
                if idx is not None:
                    lines[idx] = m.group(1) + "#" + lines[idx].lstrip()
                    changes.append(f"{key}: 已注释（取消启用）")

        # ---- Shader 列表 ----
        cur_paths = []
        for key in self.shader_order:
            if key.startswith("shader:") and self.checks[key].get() and self.vars[key].get().strip():
                cur_paths.append(self.vars[key].get().strip())
        entry_paths = set()
        for k, var in self.vars.items():
            if k.startswith("shader:") and var.get().strip():
                entry_paths.add(norm_mpv_path(var.get().strip()))
        unmatched = [p for p in self.baseline_shader_paths
                     if self.match_shader_key(p) is None and norm_mpv_path(p) not in entry_paths]
        new_paths = cur_paths + unmatched
        if sorted(norm_mpv_path(p) for p in new_paths if str(p).strip()) != \
           sorted(norm_mpv_path(p) for p in self.baseline_shader_paths if str(p).strip()):
            idx_set, m_set = find("glsl-shaders", True)
            idx_app, m_app = find("glsl-shaders-append", True)
            if idx_app is not None:
                lines[idx_app] = m_app.group(1) + "#" + lines[idx_app].lstrip()
                changes.append("glsl-shaders-append: 已注释（改用 glsl-shaders）")
            if new_paths:
                new_val = '"' + ";".join(new_paths) + '"'
                if idx_set is not None:
                    lines[idx_set] = m_set.group(1) + f"glsl-shaders = {new_val}"
                    changes.append("glsl-shaders: 已更新")
                else:
                    if idx_app is not None:
                        lines.insert(idx_app + 1, m_app.group(1) + f"glsl-shaders = {new_val}")
                    else:
                        appended.append(f"glsl-shaders = {new_val}")
                    changes.append("glsl-shaders: 新增")
            elif idx_set is not None:
                lines[idx_set] = m_set.group(1) + "#" + lines[idx_set].lstrip()
                changes.append("glsl-shaders: 已注释（未选择 shader）")

        # ---- VS 补帧 vf ----
        cur_memc = None
        for key in self.checks:
            if key.startswith("memc:") and self.checks[key].get() and self.vars[key].get().strip():
                cur_memc = self.vars[key].get().strip()
                break
        if norm_mpv_path(cur_memc or "") != norm_mpv_path(self.baseline_memc_path or ""):
            idx_vf, m_vf = find("vf", True)
            if idx_vf is not None:
                parts = [x.strip() for x in m_vf.group(4).strip().strip('"').split(",") if x.strip()]
                parts = [x for x in parts if "vapoursynth=" not in x]
                if cur_memc:
                    parts.append(f'vapoursynth="{cur_memc}"')
                if parts:
                    lines[idx_vf] = m_vf.group(1) + "vf = " + ",".join(parts)
                    changes.append(f"vf: 已更新为 {','.join(parts)}")
                else:
                    lines[idx_vf] = m_vf.group(1) + "#" + lines[idx_vf].lstrip()
                    changes.append("vf: 已注释（未选择补帧）")
            elif cur_memc:
                appended.append(f'vf = vapoursynth="{cur_memc}"')
                changes.append(f'vf: 新增 vapoursynth="{cur_memc}"')

        if appended:
            lines += ["", " ####################", " # 由 MPV Config Builder 写入 #", " ####################", ""]
            for ln in appended:
                lines.append(" " + ln)
            lines.append("")

        return self.source_newline.join(lines) + self.source_newline, changes

    def apply_modify(self):
        if not self.source_path:
            messagebox.showinfo(APP_TITLE, "还没有上传配置文件。\n请先点『上传配置...』选择要修改的 mpv.conf。")
            return
        text, changes = self.build_merged_text()
        if not changes:
            self.status.config(text="没有检测到改动，未写入文件")
            messagebox.showinfo(APP_TITLE,
                                "没有检测到改动，所以没有写文件。\n\n"
                                "只有下面这些操作才算改动：\n"
                                "· 勾选/取消勾选参数，或改了参数的值\n"
                                "· 勾选/取消勾选 shader 或 vpy（在扫描页导入后还要在列表里勾上）\n\n"
                                "如果你勾选的内容和原文件里已有的完全一样，就不会产生改动。")
            return
        src = Path(self.source_path)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = src.with_name(src.name + f".bak-{stamp}")
        try:
            shutil.copy2(src, backup)
            src.write_bytes(text.encode("utf-8-sig" if self.source_bom else "utf-8"))
        except OSError as e:
            messagebox.showerror(APP_TITLE,
                                 f"写入失败：{e}\n\n"
                                 "如果文件在 Program Files 下，请用管理员身份运行本程序，\n"
                                 "或改用『另存为』保存到其它位置。")
            return
        self.source_lines = text.splitlines()
        self.load_config_text(text)
        self.update_all()
        self.status.config(text=f"已写回 {src.name}，共 {len(changes)} 处改动（备份 {backup.name}）")
        detail = "\n".join(changes[:12]) + ("\n……" if len(changes) > 12 else "")
        messagebox.showinfo(APP_TITLE, f"已应用 {len(changes)} 处修改：\n\n{detail}\n\n原文件备份：{backup.name}")

    def load_conf(self):
        if self.mode.get() == "modify":
            self.upload_for_modify()
            return
        p=filedialog.askopenfilename(filetypes=[("MPV config","*.conf"),("All files","*.*")])
        if p:
            self.load_conf_path(p)

    def load_conf_path(self, p):
        self.clear_all(silent=True)
        unknown=[]
        for raw in Path(p).read_text(encoding="utf-8-sig",errors="replace").splitlines():
            s=raw.strip()
            if not s or s.startswith("#") or "=" not in s: continue
            k,v=s.split("=",1); k=k.strip(); v=v.strip()
            if k in self.vars:
                self.checks[k].set(True); self.vars[k].set(v)
            else: unknown.append(s)
        self.custom_unknown="\n".join(unknown)
        self.update_all()

    def clear_all(self,silent=False):
        for v in self.checks.values():v.set(False)
        for k, v in self.vars.items():
            # shader / vpy 的"值"是文件路径，属于条目本身，清空勾选时不能丢，
            # 否则之后勾选会因为路径为空而被静默跳过（表现为"勾了没反应"）
            if k.startswith("shader:") or k.startswith("memc:"):
                continue
            v.set("")
        self.custom_unknown=""
        if not silent:self.update_all()

    # ---------- 读取 mpv-lazy 现有配置 ----------

    def match_shader_key(self, path):
        raw = str(path).strip().strip('"').strip("'")
        if not raw:
            return None
        target_rel = norm_mpv_path(raw)
        target_name = Path(raw.replace("\\", "/")).name.lower()
        for item in self.shader_catalog:
            rel = norm_mpv_path(item["path"])
            if rel and (rel == target_rel or Path(rel).name.lower() == target_name):
                return "shader:" + item["name"]
        return None

    def match_memc_key(self, path):
        raw = str(path).strip().strip('"').strip("'")
        if not raw:
            return None
        target_rel = norm_mpv_path(raw)
        target_name = Path(raw.replace("\\", "/")).name.lower()
        for item in self.memc_catalog:
            rel = norm_mpv_path(item["path"])
            if rel and (rel == target_rel or Path(rel).name.lower() == target_name):
                return "memc:" + item["name"]
        return None

    def load_lazy_config(self):
        """读取 mpv-lazy 现有 mpv.conf，把已启用的项自动勾上。"""
        self.lazy_loaded_count = 0
        if not self.lazy_pc:
            return
        conf = Path(self.lazy_pc) / "mpv.conf"
        if not conf.is_file():
            return
        text = conf.read_text(encoding="utf-8-sig", errors="replace")
        for raw in text.splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = strip_inline_comment(v.strip())
            if k in self.checks:
                self.checks[k].set(True)
                self.vars[k].set(v)
                self.lazy_loaded_count += 1
            elif k in ("glsl-shaders", "glsl-shader", "glsl-shaders-append", "glsl-shader-append"):
                for p in split_mpv_list(v):
                    key = self.match_shader_key(p)
                    if key:
                        self.checks[key].set(True)
                        self.lazy_loaded_count += 1
            elif k in ("vf", "vf-append"):
                p = extract_vapoursynth_path(v)
                if p:
                    key = self.match_memc_key(p)
                    if key:
                        self.checks[key].set(True)
                        self.lazy_loaded_count += 1

    # ---------- 配置上传 / 粘贴分析 ----------

    def analysis_upload(self):
        p=filedialog.askopenfilename(filetypes=[("MPV 配置","*.conf *.ini *.txt"),("所有文件","*.*")])
        if not p: return
        try:
            text=Path(p).read_text(encoding="utf-8-sig",errors="replace")
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"读取文件失败：{e}")
            return
        self.open_analysis_window(text, p)

    def analysis_paste(self):
        try:
            text=self.clipboard_get()
        except tk.TclError:
            messagebox.showinfo(APP_TITLE, "剪贴板中没有文本内容。")
            return
        if not text.strip():
            messagebox.showinfo(APP_TITLE, "剪贴板中没有文本内容。")
            return
        self.open_analysis_window(text, "剪贴板")

    def open_analysis_window(self, text, source=""):
        report=analyze_config_text(text)
        report["source"]=source or "内存文本"

        win=tk.Toplevel(self)
        win.title("配置上传分析")
        win.geometry("780x660")
        win.minsize(640, 520)
        win.transient(self)

        top=ttk.Frame(win, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="配置分析报告", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(top, text=f"来源：{report['source']}", foreground="#555555").pack(anchor="w")
        ttk.Label(top, text=f"行数：{report['line_count']}  |  注释：{report['comment_count']}  |  有效配置项：{report['option_count']}",
                  foreground="#555555").pack(anchor="w")

        summary=ttk.LabelFrame(win, text="总体评估", padding=8)
        summary.pack(fill="x", padx=10, pady=(0,8))
        grade_color="#1a7f37" if report["overall"]>=82 else "#b45f06" if report["overall"]>=70 else "#c0392b"
        ttk.Label(summary, text=f"综合 {report['overall']}/100  |  {report['grade']}  |  GPU负载等级 {report['load']}/100",
                  font=("Segoe UI", 12, "bold"), foreground=grade_color).grid(row=0, column=0, columnspan=12, sticky="w")
        for i, (name, skey) in enumerate([("清晰度","quality"),("锐度","sharp"),("流畅度","smooth"),("色彩/观感","color"),("稳定性","stability"),("GPU负载","load")]):
            ttk.Label(summary, text=name).grid(row=1, column=i*2, padx=(5,2), sticky="w")
            pb=ttk.Progressbar(summary, length=95, maximum=100)
            pb.grid(row=1, column=i*2+1, padx=(0,8), sticky="ew")
            pb["value"]=report["scores"][skey]

        body=ttk.Frame(win, padding=(10,0,10,8))
        body.pack(fill="both", expand=True)
        txt=tk.Text(body, wrap="none", font=("Consolas", 10))
        sb=ttk.Scrollbar(body, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        txt.tag_configure("h", font=("Segoe UI", 12, "bold"), foreground="#1f4e79")
        txt.tag_configure("ok", foreground="#1a7f37")
        txt.tag_configure("warn", foreground="#b45f06")
        txt.tag_configure("bad", foreground="#c0392b", font=("Segoe UI", 10, "bold"))
        txt.tag_configure("info", foreground="#555555")

        parts=self.analysis_report_parts(report)
        plain_lines=[]
        for tag, line in parts:
            if tag:
                txt.insert("end", line+"\n", tag)
            else:
                txt.insert("end", line+"\n")
            plain_lines.append(line)
        txt.config(state="disabled")

        btns=ttk.Frame(win, padding=10)
        btns.pack(fill="x")
        plain_report="\n".join(plain_lines)
        ttk.Button(btns, text="复制报告", command=lambda: self.copy_text(plain_report)).pack(side="left", padx=3)
        src=report.get("source","")
        if src and Path(src).is_file():
            ttk.Button(btns, text="导入到构建器", command=lambda f=src: self.import_analyzed_file(f)).pack(side="left", padx=3)
        ttk.Button(btns, text="关闭", command=win.destroy).pack(side="right", padx=3)

    def import_analyzed_file(self, path):
        self.load_conf_path(path)
        name=Path(path).name
        self.status.config(text=f"已导入分析配置：{name}")
        messagebox.showinfo(APP_TITLE, f"已导入到构建器：{name}\n\n未收录/未知选项会保留在 custom_unknown 中，实时预览仅生成构建器支持的参数。")

    def analysis_report_parts(self, report):
        parts=[]
        parts.append(("h", "配置分析报告"))
        parts.append(("info", f"来源：{report.get('source','')}"))
        parts.append(("info", f"行数：{report['line_count']}  |  注释：{report['comment_count']}  |  有效配置项：{report['option_count']}"))
        parts.append(("", ""))
        parts.append(("h", "总体评估"))
        grade_tag = "ok" if report["overall"]>=82 else "warn" if report["overall"]>=70 else "bad"
        parts.append((grade_tag, f"综合 {report['overall']}/100  |  {report['grade']}  |  GPU负载等级 {report['load']}/100"))
        for name, skey in [("清晰度","quality"),("锐度","sharp"),("流畅度","smooth"),("色彩/观感","color"),("稳定性","stability"),("GPU负载","load")]:
            parts.append(("info", f"  {name}：{report['scores'][skey]}/100"))
        parts.append(("", ""))

        parts.append(("h", f"已识别参数（{len(report['known'])}）"))
        if report["known"]:
            for item in report["known"]:
                tag = "ok" if item["ok"] else "warn"
                parts.append((tag, f"  ✔ {item['name']} = {item['value']}   [{item['note']}]"))
        else:
            parts.append(("info", "  未识别到构建器支持的具体参数。"))
        parts.append(("", ""))

        parts.append(("h", f"Shader 配置（{len(report['shaders'])}）"))
        if report["shaders"]:
            for s in report["shaders"]:
                parts.append(("info", f"  第{s['line']}行  {s['key']} = {s['value']}"))
        else:
            parts.append(("info", "  未检测到 Shader 相关配置。"))
        parts.append(("", ""))

        parts.append(("h", f"工具未收录的标准选项（{len(report['unlisted'])}）"))
        if report["unlisted"]:
            for k, v in report["unlisted"]:
                parts.append(("info", f"  {k} = {v}"))
        else:
            parts.append(("info", "  无。"))
        parts.append(("", ""))

        parts.append(("h", f"疑似未知选项（{len(report['unknown'])}）"))
        if report["unknown"]:
            for k, v, no in report["unknown"]:
                parts.append(("bad", f"  第{no}行  {k} = {v}"))
        else:
            parts.append(("info", "  无。"))
        parts.append(("", ""))

        parts.append(("h", f"重复配置项（{len(report['duplicates'])}）"))
        if report["duplicates"]:
            for k, first, second in report["duplicates"]:
                parts.append(("warn", f"  {k}：第{first}行 与 第{second}行 重复"))
        else:
            parts.append(("info", "  无。"))
        parts.append(("", ""))

        parts.append(("h", f"发现的问题（{len(report['issues'])}）"))
        if report["issues"]:
            for issue in report["issues"]:
                parts.append(("bad", f"  ⚠ {issue}"))
        else:
            parts.append(("ok", "  没有发现明显问题。"))
        parts.append(("", ""))

        parts.append(("h", f"建议（{len(report['suggestions'])}）"))
        for s in report["suggestions"]:
            parts.append(("info", f"  • {s}"))

        return parts


if __name__=="__main__":
    App().mainloop()

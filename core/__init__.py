"""MPV Config Builder 核心逻辑（与界面无关）。

模块划分：
    schema    参数表、shader/vpy 清单、原生选项、路径与扫描辅助
    net       下载清单、镜像线路、HTTP 访问
    score     六维启发式评分
    analyze   mpv.conf 解析与分析
    presets   基础模式 6 套预设
    hardware  分辨率 / 刷新率 / GPU 探测
    writer    备份、include 写入、合并写入
    installer mpv-lazy 一键安装（查版本/下载/校验/解压）
    update    工具与 mpv-lazy 的版本检测
"""

from .schema import *     # noqa: F401,F403
from .net import *        # noqa: F401,F403
from .score import *      # noqa: F401,F403
from .analyze import *    # noqa: F401,F403
from .presets import *    # noqa: F401,F403
from .hardware import *   # noqa: F401,F403
from .writer import *     # noqa: F401,F403
from .installer import *  # noqa: F401,F403
from .update import *     # noqa: F401,F403

# 这几个没有 __all__，通配导入时容易漏，显式再导一次
from .schema import (     # noqa: F401
    candidate_dirs, find_lazy_pc, looks_like_config_dir,
    format_option_line, format_option_value, needs_quotes, LIST_OPTION_KEYS,
    LAZY_CANDIDATE_DIRS, COMMON_MPV_INSTALL_DIRS,
    load_settings, save_settings, SETTINGS_PATH,
)

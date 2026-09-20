"""六维启发式评分。"""
from .schema import PARAMS, SHADERS, get_param_meta


def score_active(active):
    """根据启用的配置项计算六维启发式得分。"""
    quality = 55
    sharp = 50
    smooth = 45
    color = 50
    stability = 90
    load = 20
    for k in active:
        if k.startswith("shader:"):
            meta = SHADERS.get(k[7:])
            if meta:
                q, l = meta[1], meta[2]
            else:
                q, l = 4, 4
            quality += q
            sharp += q + 1
            load += l * 2
        elif k.startswith("memc:"):
            # 外部 MEMC 模板：提高流畅度评分，同时视为高负载
            smooth += 20
            load += 12
        else:
            meta = get_param_meta(k)
            if meta:
                _, _, _, opts, q, l = meta
                quality += q * 2
                sharp += q
                load += l * 3
                if k == "interpolation":
                    smooth += 25
                if k == "tscale":
                    smooth += 10
                if k == "deband":
                    color += 10
    return {
        "quality": min(100, quality),
        "sharp": min(100, sharp),
        "smooth": min(100, smooth),
        "color": min(100, color),
        "stability": min(100, stability),
        "load": min(100, load),
    }


# 总分权重：**只在这里定义一次**。
# 以前 analyze.py 与 webui/server.py 各写了一遍一模一样的 0.28/0.22/0.18/0.12/0.20，
# 改权重必然漏改一处，两处结果就会不一致。
OVERALL_WEIGHTS = {
    "quality": 0.28,
    "sharp": 0.22,
    "smooth": 0.18,
    "color": 0.12,
    "stability": 0.20,
}


def overall_score(scores):
    """六维 → 一个总分（0–100 整数）。"""
    return round(sum(scores.get(k, 0) * w for k, w in OVERALL_WEIGHTS.items()))


def grade_of(overall):
    """总分 → 中文档位。"""
    if overall >= 92:
        return "极限画质"
    if overall >= 82:
        return "高画质"
    if overall >= 70:
        return "均衡"
    return "轻量"


__all__ = ["score_active", "overall_score", "grade_of", "OVERALL_WEIGHTS"]



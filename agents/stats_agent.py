"""
統計検定エージェント

任意の閾値ではなく、統計的根拠に基づいてパフォーマンスを判定する。

【使用手法】
- 低パフォーマンス判定: 第25パーセンタイル（IQR法）
- グループ差の検定: Mann-Whitney U検定（視聴数は正規分布しないため非パラメトリック）
- 効果量: rank-biserial相関（-1〜1、|r|>0.3で実用的な差あり）
- 最小サンプル数: 5本（それ未満は判定せず中央値比較にフォールバック）
"""

import numpy as np
from scipy import stats as scipy_stats


MIN_SAMPLE = 5  # 統計検定に必要な最小サンプル数


def describe(values):
    """分布の基本統計量を返す"""
    if not values:
        return {}
    arr = np.array(values, dtype=float)
    return {
        "n": len(arr),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def low_performer_threshold(channel_views, percentile=25):
    """
    チャンネルの過去動画から低パフォーマンス閾値を算出。
    サンプル不足時は中央値の50%にフォールバック。
    """
    if len(channel_views) < MIN_SAMPLE:
        median = float(np.median(channel_views)) if channel_views else 0
        return median * 0.5, "fallback_median"

    threshold = float(np.percentile(channel_views, percentile))
    return threshold, f"p{percentile}"


def is_significantly_better(group_a, group_b, alpha=0.05):
    """
    group_b が group_a より統計的に有意に高いか（片側検定）。
    Returns: (significant: bool, p_value: float, effect_r: float)
    """
    if len(group_a) < MIN_SAMPLE or len(group_b) < MIN_SAMPLE:
        return False, 1.0, 0.0

    stat, p = scipy_stats.mannwhitneyu(group_b, group_a, alternative="greater")

    # rank-biserial相関（効果量）
    n1, n2 = len(group_a), len(group_b)
    r = 1 - (2 * stat) / (n1 * n2)

    return p < alpha, float(p), float(r)


def lift(before, after):
    """
    施策前後の視聴数リストから平均リフト率を計算。
    Returns: float (1.0 = 変化なし, 1.2 = +20%)
    """
    if not before or not after:
        return 1.0
    b = np.mean(before)
    a = np.mean(after)
    return float(a / b) if b > 0 else 1.0


def sample_size_ok(n, min_n=MIN_SAMPLE):
    """統計的判定に十分なサンプルがあるか"""
    return n >= min_n


def format_stats(desc):
    """describe()の結果を読みやすい文字列に"""
    if not desc:
        return "データなし"
    return (
        f"中央値:{desc['median']:.0f} / "
        f"P25:{desc['p25']:.0f} / "
        f"P75:{desc['p75']:.0f} / "
        f"n={desc['n']}"
    )

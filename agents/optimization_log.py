"""
最適化ログ管理エージェント

施策実施前後の数値を記録し、効果測定を自動化する。
data/optimization_log.json に永続化。

【ライフサイクル】
  1. optimize_agent が動画を最適化する際に record_optimization() を呼ぶ
  2. 7〜14日後の optimize_agent 実行時に update_post_views() で事後数値を記録
  3. weekly_report_agent が get_lift_stats() で効果サマリーを表示
"""

import json
import os
from datetime import datetime, timedelta, timezone

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "optimization_log.json")


def _load():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        return json.load(f)


def _save(log):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def record_optimization(video_id, channel, views_before, actions, ctr_before=None):
    """
    最適化実施を記録する。

    Args:
        video_id: YouTube動画ID
        channel: チャンネル名 (jazz / cafe / sleep)
        views_before: 最適化前の視聴数
        actions: 実施したアクション ["tags", "description", "title"]
        ctr_before: 最適化前のCTR（Analytics API利用可能な場合）
    """
    log = _load()

    # 重複チェック（同じ動画を2回記録しない）
    for entry in log:
        if entry["video_id"] == video_id:
            return

    log.append({
        "video_id": video_id,
        "channel": channel,
        "optimized_at": datetime.now(timezone.utc).isoformat(),
        "views_before": views_before,
        "ctr_before": ctr_before,
        "actions": actions,
        "views_7d_after": None,
        "ctr_7d_after": None,
        "measured_at": None,
    })
    _save(log)
    print(f"  [log] Recorded optimization: {video_id} ({channel}, {views_before}v)")


def update_post_metrics(youtube, video_ids_on_channel=None):
    """
    記録から7〜21日経過した動画の事後視聴数を取得して更新する。
    optimize_agent の実行時に呼び出す。
    """
    log = _load()
    now = datetime.now(timezone.utc)
    updated = 0

    for entry in log:
        if entry["views_7d_after"] is not None:
            continue  # 計測済み

        optimized_at = datetime.fromisoformat(entry["optimized_at"])
        age_days = (now - optimized_at).days

        if age_days < 7:
            continue  # まだ7日経っていない
        if age_days > 30:
            # 30日経っても未計測なら中止
            entry["views_7d_after"] = -1
            entry["measured_at"] = now.isoformat()
            continue

        try:
            resp = youtube.videos().list(
                part="statistics", id=entry["video_id"]
            ).execute()
            items = resp.get("items", [])
            if items:
                views_after = int(items[0]["statistics"].get("viewCount", 0))
                entry["views_7d_after"] = views_after
                entry["measured_at"] = now.isoformat()
                lift = views_after / entry["views_before"] if entry["views_before"] > 0 else 1
                print(f"  [log] {entry['video_id']}: {entry['views_before']}→{views_after}v (×{lift:.1f})")
                updated += 1
        except Exception as e:
            print(f"  [log] Failed to fetch {entry['video_id']}: {e}")

    if updated:
        _save(log)
    return updated


def get_lift_stats(min_samples=5):
    """
    最適化効果の統計サマリーを返す。

    Returns:
        dict: {
            "n_measured": 計測済み件数,
            "avg_lift": 平均リフト率 (1.2 = +20%),
            "median_lift": 中央値リフト,
            "by_action": {action: avg_lift},
            "significant": bool (p<0.05),
            "p_value": float,
        }
    """
    import numpy as np

    log = _load()
    measured = [e for e in log if e["views_7d_after"] and e["views_7d_after"] > 0]

    if len(measured) < min_samples:
        return {"n_measured": len(measured), "avg_lift": None, "note": f"計測済み{len(measured)}件（最低{min_samples}件必要）"}

    lifts = []
    for e in measured:
        if e["views_before"] > 0:
            lifts.append(e["views_7d_after"] / e["views_before"])

    if not lifts:
        return {"n_measured": 0, "avg_lift": None}

    # Mann-Whitney U: 最適化後 vs 最適化前（1.0との比較）
    from scipy import stats as scipy_stats
    stat, p = scipy_stats.wilcoxon([l - 1.0 for l in lifts], alternative="greater")

    # アクション別効果
    action_lifts = {}
    for e in measured:
        if e["views_before"] <= 0:
            continue
        lift_val = e["views_7d_after"] / e["views_before"]
        for action in e.get("actions", []):
            action_lifts.setdefault(action, []).append(lift_val)

    return {
        "n_measured": len(lifts),
        "avg_lift": float(np.mean(lifts)),
        "median_lift": float(np.median(lifts)),
        "by_action": {a: float(np.mean(v)) for a, v in action_lifts.items()},
        "significant": bool(p < 0.05),
        "p_value": float(p),
    }


def get_pending_measurement():
    """7日以上経過して未計測の件数"""
    log = _load()
    now = datetime.now(timezone.utc)
    pending = []
    for e in log:
        if e["views_7d_after"] is not None:
            continue
        optimized_at = datetime.fromisoformat(e["optimized_at"])
        if (now - optimized_at).days >= 7:
            pending.append(e)
    return pending

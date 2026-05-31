"""
投稿タイミング最適化エージェント

アップロード動画の曜日・時間帯と7日後視聴数を記録し、
最適な投稿スケジュールを統計的に推定する。

【データフロー】
  1. 各 main.py がアップロード後に record_upload() を呼ぶ
  2. 次回実行時に update_timing_metrics() で 7d 視聴数を取得
  3. update_schedule.py (週1) が analyze_best_timing() でスケジュールを最適化
  4. weekly_report_agent が get_timing_summary() でレポートに組み込む

【データスキーマ: data/upload_timing.json】
  {
    "jazz": [
      {
        "video_id": "abc123",
        "published_at": "2025-05-21T09:00:00+00:00",
        "day_of_week": 2,      // 0=月 〜 6=日 (Python weekday)
        "hour_utc": 9,
        "views_7d": 1500,      // null = 未計測
        "measured_at": "2025-05-28T09:00:00+00:00"
      }
    ],
    "cafe": [...],
    "sleep": [...],
    "chill": [...]
  }
"""

import json
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

TIMING_PATH = Path(__file__).parent.parent / "data" / "upload_timing.json"

# 最低サンプル数（これ未満なら推奨なし）
MIN_SAMPLES_PER_DAY = 3
# 推奨変更の閾値: 現在スケジュールより X% 以上改善する場合のみ提案
IMPROVEMENT_THRESHOLD = 0.15  # 15%

# Python weekday (0=Mon) → 日本語曜日名
DAY_NAMES_JA = ["月", "火", "水", "木", "金", "土", "日"]
DAY_NAMES_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Python weekday → cron weekday (0=Sun, 1=Mon, ..., 6=Sat)
# Python: Mon=0, ..., Sun=6
# Cron:   Sun=0, Mon=1, ..., Sat=6
def _py_to_cron_day(py_day: int) -> int:
    return (py_day + 1) % 7


def _cron_to_py_day(cron_day: int) -> int:
    return (cron_day - 1) % 7


# ── データ永続化 ──────────────────────────────────────────────────────────────

def _load() -> dict:
    TIMING_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not TIMING_PATH.exists():
        return {}
    with open(TIMING_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    TIMING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TIMING_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── データ記録 ────────────────────────────────────────────────────────────────

def record_upload(
    channel: str,
    video_id: str,
    published_at: datetime | None = None,
) -> None:
    """
    アップロード直後に呼び出す。投稿曜日・時間帯を記録する。

    Args:
        channel: "jazz" | "cafe" | "sleep" | "chill"
        video_id: YouTube 動画 ID
        published_at: 投稿日時 (None の場合は現在時刻)
    """
    data = _load()
    channel_list = data.setdefault(channel, [])

    # 重複チェック
    if any(e["video_id"] == video_id for e in channel_list):
        return

    now = published_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    entry = {
        "video_id": video_id,
        "published_at": now.isoformat(),
        "day_of_week": now.weekday(),        # 0=月 〜 6=日
        "hour_utc": now.hour,
        "views_7d": None,
        "measured_at": None,
    }
    channel_list.append(entry)
    _save(data)
    print(f"  [timing] 記録: {video_id} ({channel}) — {DAY_NAMES_JA[now.weekday()]}曜 {now.hour:02d}:00 UTC")


# ── 視聴数計測 ────────────────────────────────────────────────────────────────

def update_timing_metrics(youtube, channel: str) -> int:
    """
    7〜30日前にアップロードした動画の視聴数を取得して更新する。
    各 main.py の冒頭（アップロード前）に呼び出す。

    Returns:
        更新件数
    """
    data = _load()
    channel_list = data.get(channel, [])
    now = datetime.now(timezone.utc)
    updated = 0

    targets = []
    for entry in channel_list:
        if entry["views_7d"] is not None:
            continue  # 計測済み
        pub = datetime.fromisoformat(entry["published_at"])
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        age_days = (now - pub).days
        if age_days < 7:
            continue  # まだ7日経っていない
        if age_days > 30:
            entry["views_7d"] = -1  # 期限切れ
            entry["measured_at"] = now.isoformat()
            continue
        targets.append(entry)

    if not targets:
        if updated:
            _save(data)
        return updated

    # バッチで視聴数を取得
    ids = ",".join(e["video_id"] for e in targets)
    try:
        resp = youtube.videos().list(part="statistics", id=ids).execute()
        stats_map = {item["id"]: item["statistics"] for item in resp.get("items", [])}
    except Exception as e:
        print(f"  [timing] 視聴数取得失敗: {e}")
        return 0

    for entry in targets:
        s = stats_map.get(entry["video_id"], {})
        views = int(s.get("viewCount", 0))
        entry["views_7d"] = views
        entry["measured_at"] = now.isoformat()
        updated += 1
        print(f"  [timing] 計測: {entry['video_id']} → {views:,} views (7d)")

    if updated:
        _save(data)

    return updated


# ── 分析 ──────────────────────────────────────────────────────────────────────

def analyze_best_timing(channel: str) -> dict:
    """
    チャンネルの投稿タイミングデータを分析し、曜日別の平均視聴数を返す。

    Returns:
        {
            "channel": str,
            "total_samples": int,
            "day_stats": {
                0: {"mean": 1200.0, "median": 1100.0, "n": 5, "day_ja": "月"},
                ...
            },
            "best_day": int | None,       # Python weekday (0=Mon), None=データ不足
            "best_day_ja": str | None,
            "current_days": list[int],    # 現在のスケジュールに含まれる曜日
            "recommendation": str,        # 人間向け説明文
            "confident": bool,            # 十分なサンプル数か
        }
    """
    data = _load()
    entries = [
        e for e in data.get(channel, [])
        if e.get("views_7d") and e["views_7d"] > 0
    ]

    # 曜日ごとにグループ化
    day_groups: dict[int, list[int]] = {}
    for e in entries:
        d = e["day_of_week"]
        day_groups.setdefault(d, []).append(e["views_7d"])

    day_stats = {}
    for day, views in day_groups.items():
        day_stats[day] = {
            "mean": statistics.mean(views),
            "median": statistics.median(views),
            "n": len(views),
            "day_ja": DAY_NAMES_JA[day],
            "day_en": DAY_NAMES_EN[day],
        }

    # 十分なサンプルがある曜日のみ対象
    qualified = {d: s for d, s in day_stats.items() if s["n"] >= MIN_SAMPLES_PER_DAY}

    result = {
        "channel": channel,
        "total_samples": len(entries),
        "day_stats": day_stats,
        "best_day": None,
        "best_day_ja": None,
        "current_days": [],
        "recommendation": f"データ蓄積中（計測済み {len(entries)} 件 / 各曜日 {MIN_SAMPLES_PER_DAY} 件以上必要）",
        "confident": False,
    }

    if not qualified:
        return result

    best_day = max(qualified, key=lambda d: qualified[d]["mean"])
    best_mean = qualified[best_day]["mean"]

    result["best_day"] = best_day
    result["best_day_ja"] = DAY_NAMES_JA[best_day]
    result["confident"] = True

    # 最良曜日の改善率
    all_means = [s["mean"] for s in qualified.values()]
    overall_mean = statistics.mean(all_means)
    if overall_mean > 0:
        improvement = (best_mean - overall_mean) / overall_mean * 100
        result["recommendation"] = (
            f"{DAY_NAMES_JA[best_day]}曜日投稿が平均 +{improvement:.0f}% 多く再生"
            f"（{best_mean:,.0f} views / {qualified[best_day]['n']} サンプル）"
        )
    else:
        result["recommendation"] = f"{DAY_NAMES_JA[best_day]}曜日が最も再生数が多い"

    return result


def recommend_new_days(
    channel: str,
    current_cron_days: list[int],  # cron 形式 (0=Sun, 1=Mon, ...)
    n_days: int | None = None,
) -> list[int] | None:
    """
    現在のスケジュールより改善が期待できる場合、新しい投稿曜日リストを返す。
    改善が不十分 or データ不足の場合は None を返す。

    Args:
        current_cron_days: 現在のcron曜日リスト (cron形式: 0=Sun)
        n_days: 何曜日分投稿するか (None = current_cron_days の len と同じ)

    Returns:
        新しい cron 曜日リスト (cron形式) or None
    """
    analysis = analyze_best_timing(channel)
    if not analysis["confident"]:
        return None

    day_stats = analysis["day_stats"]
    qualified = {d: s for d, s in day_stats.items() if s["n"] >= MIN_SAMPLES_PER_DAY}
    if not qualified:
        return None

    target_n = n_days or len(current_cron_days)

    # 平均視聴数の多い順に target_n 日を選ぶ
    sorted_days = sorted(qualified, key=lambda d: qualified[d]["mean"], reverse=True)
    best_py_days = sorted_days[:target_n]

    # cron 形式に変換
    best_cron_days = sorted([_py_to_cron_day(d) for d in best_py_days])

    # 現在のスケジュールと比較
    current_py_days = [_cron_to_py_day(d) for d in current_cron_days]
    current_mean = statistics.mean([
        qualified[d]["mean"] for d in current_py_days if d in qualified
    ]) if any(d in qualified for d in current_py_days) else 0

    new_mean = statistics.mean([
        qualified[d]["mean"] for d in best_py_days
    ])

    if current_mean > 0:
        improvement = (new_mean - current_mean) / current_mean
        if improvement < IMPROVEMENT_THRESHOLD:
            return None  # 改善幅が閾値未満

    # 変更がなければ None
    if sorted(best_cron_days) == sorted(current_cron_days):
        return None

    return best_cron_days


# ── レポート用サマリー ─────────────────────────────────────────────────────────

def get_timing_summary() -> dict[str, dict]:
    """
    全チャンネルのタイミング分析サマリーを返す。weekly_report_agent から呼ぶ。

    Returns:
        { "jazz": {analysis dict}, "cafe": {...}, ... }
    """
    channels = ["jazz", "cafe", "sleep", "chill"]
    return {ch: analyze_best_timing(ch) for ch in channels}

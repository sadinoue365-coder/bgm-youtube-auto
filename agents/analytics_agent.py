"""
YouTube Analytics API エージェント

YouTube Data API では取得できない以下の指標を取得する:
  - CTR (impressionClickThroughRate)  — サムネイルのクリック率
  - 平均視聴時間 (averageViewDuration) — 秒単位
  - 平均視聴率 (averageViewPercentage) — 動画の何%視聴されたか
  - 登録者転換数 (subscribersGained)  — この動画経由の登録者数
  - 視聴時間 (estimatedMinutesWatched)

【スコープ要件】
  https://www.googleapis.com/auth/yt-analytics.readonly
  → get_token.py で再認証が必要（既存トークンには含まれていない）

【フォールバック】
  スコープがない場合は None を返し、呼び出し元は Data API のviewCountで代替する。
"""

from datetime import datetime, timedelta, timezone


def get_video_analytics(yt_analytics, channel_id, video_id, days=28):
    """
    指定動画の Analytics 指標を取得する。

    Returns:
        dict or None: {
            "ctr": float,                    # 0.0〜1.0
            "avg_view_duration_sec": float,  # 秒
            "avg_view_percentage": float,    # 0〜100%
            "subscribers_gained": int,
            "watch_minutes": int,
            "views": int,
        }
    """
    try:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

        resp = yt_analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start,
            endDate=end,
            metrics=(
                "views,estimatedMinutesWatched,averageViewDuration,"
                "averageViewPercentage,subscribersGained,"
                "impressionClickThroughRate"
            ),
            filters=f"video=={video_id}",
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            return None

        row = rows[0]
        headers = [h["name"] for h in resp.get("columnHeaders", [])]
        data = dict(zip(headers, row))

        return {
            "views": int(data.get("views", 0)),
            "watch_minutes": int(data.get("estimatedMinutesWatched", 0)),
            "avg_view_duration_sec": float(data.get("averageViewDuration", 0)),
            "avg_view_percentage": float(data.get("averageViewPercentage", 0)),
            "subscribers_gained": int(data.get("subscribersGained", 0)),
            "ctr": float(data.get("impressionClickThroughRate", 0)),
        }

    except Exception as e:
        # スコープ不足や quota エラーは無視してフォールバック
        if "insufficientPermissions" in str(e) or "forbidden" in str(e).lower():
            return None
        print(f"  Analytics API error ({video_id}): {e}")
        return None


def get_channel_analytics(yt_analytics, channel_id, days=7):
    """
    チャンネル全体の直近 N 日間 Analytics を取得する。

    Returns:
        dict or None: {
            "views": int,
            "watch_minutes": int,
            "subscribers_gained": int,
            "avg_ctr": float,
            "avg_view_percentage": float,
        }
    """
    try:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

        resp = yt_analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start,
            endDate=end,
            metrics=(
                "views,estimatedMinutesWatched,subscribersGained,"
                "impressionClickThroughRate,averageViewPercentage"
            ),
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            return None

        row = rows[0]
        headers = [h["name"] for h in resp.get("columnHeaders", [])]
        data = dict(zip(headers, row))

        return {
            "views": int(data.get("views", 0)),
            "watch_minutes": int(data.get("estimatedMinutesWatched", 0)),
            "subscribers_gained": int(data.get("subscribersGained", 0)),
            "avg_ctr": float(data.get("impressionClickThroughRate", 0)),
            "avg_view_percentage": float(data.get("averageViewPercentage", 0)),
        }

    except Exception as e:
        if "insufficientPermissions" in str(e) or "forbidden" in str(e).lower():
            return None
        print(f"  Channel Analytics API error: {e}")
        return None


def build_analytics_client(creds):
    """YouTube Analytics API クライアントを構築"""
    from googleapiclient.discovery import build
    try:
        return build("youtubeAnalytics", "v2", credentials=creds)
    except Exception:
        return None

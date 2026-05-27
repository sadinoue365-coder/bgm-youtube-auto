"""
トレンドキーワード注入エージェント

アップロード前にYouTube検索で上位動画のタイトル・タグを取得し、
自チャンネルの動画に注入する追加タグリストを返す。

APIコスト: search.list = 100 units / 呼び出し
"""

import re
from googleapiclient.discovery import build


def _extract_keywords(text):
    """タイトルから意味のある単語を抽出"""
    stop_words = {
        "for", "and", "the", "a", "an", "in", "on", "at", "to", "of",
        "with", "by", "&", "-", "|", "•", "hours", "hour", "min",
        "minutes", "vol", "mix", "bgm", "music", "1", "2", "3",
    }
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if len(w) > 3 and w not in stop_words]


def get_trending_tags(youtube, query, max_results=10):
    """
    指定クエリで上位動画を検索し、トレンドキーワードを返す。

    Args:
        youtube: YouTube API クライアント
        query: 検索クエリ (例: "jazz bgm", "coffee shop music")
        max_results: 取得する動画数

    Returns:
        list[str]: 追加推奨タグ（最大10個）
    """
    try:
        resp = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            order="viewCount",
            maxResults=max_results,
            relevanceLanguage="en",
        ).execute()

        keyword_counts = {}
        for item in resp.get("items", []):
            title = item["snippet"]["title"]
            words = _extract_keywords(title)
            for w in words:
                keyword_counts[w] = keyword_counts.get(w, 0) + 1

        # 2本以上のトップ動画に出現したキーワードを採用
        trending = [k for k, v in sorted(keyword_counts.items(), key=lambda x: -x[1]) if v >= 2]
        print(f"  Trending keywords ({query}): {trending[:10]}")
        return trending[:10]

    except Exception as e:
        print(f"  Trending fetch failed ({query}): {e}")
        return []


def get_top_performing_styles(youtube, style_list, days=30):
    """
    自チャンネルの直近動画から各スタイルの平均視聴数を計算し、
    重み付きリストを返す（パフォーマンスフィードバックループ）。

    Args:
        youtube: YouTube API クライアント
        style_list: 候補スタイルのリスト
        days: 分析対象の日数

    Returns:
        dict: {style: weight} — 視聴数が多いスタイルほど高い重み
    """
    from datetime import datetime, timedelta, timezone

    try:
        ch = youtube.channels().list(part="contentDetails", mine=True).execute()
        playlist_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        since = datetime.now(timezone.utc) - timedelta(days=days)
        resp = youtube.playlistItems().list(
            part="snippet", playlistId=playlist_id, maxResults=50
        ).execute()

        video_ids = []
        titles = []
        for item in resp.get("items", []):
            pub_str = item["snippet"]["publishedAt"]
            from datetime import datetime, timezone
            pub_dt = datetime.strptime(pub_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if pub_dt >= since:
                video_ids.append(item["snippet"]["resourceId"]["videoId"])
                titles.append(item["snippet"]["title"])

        if not video_ids:
            return {s: 1 for s in style_list}

        stats_resp = youtube.videos().list(
            part="statistics", id=",".join(video_ids)
        ).execute()
        stats_map = {s["id"]: int(s["statistics"].get("viewCount", 0))
                     for s in stats_resp.get("items", [])}

        # 各スタイルと動画タイトルをマッチング
        style_views = {s: [] for s in style_list}
        for vid_id, title in zip(video_ids, titles):
            views = stats_map.get(vid_id, 0)
            title_lower = title.lower()
            for style in style_list:
                if style.lower() in title_lower:
                    style_views[style].append(views)

        # 重み計算: 実績ありは平均視聴数、実績なしは全体平均
        all_views = list(stats_map.values())
        global_avg = sum(all_views) / len(all_views) if all_views else 1

        weights = {}
        for style in style_list:
            if style_views[style]:
                avg = sum(style_views[style]) / len(style_views[style])
                weights[style] = max(1, int(avg / global_avg * 3))
            else:
                weights[style] = 1  # 実績なしは最低重み

        top = sorted(weights.items(), key=lambda x: -x[1])[:3]
        print(f"  Top styles: {[(s, w) for s, w in top]}")
        return weights

    except Exception as e:
        print(f"  Style analysis failed: {e}")
        return {s: 1 for s in style_list}

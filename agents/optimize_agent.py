"""
直近2週間の動画のパフォーマンスを確認し、
低パフォーマンスの動画のタグ・説明文を更新する
"""
import json
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import config

EXTRA_TAGS = [
    "lofi", "chill beats", "study beats", "focus music", "work from home",
    "concentration music", "relaxing music", "instrumental", "ambient",
    "electronic", "beats", "house music", "techno", "deep focus",
]


def get_credentials():
    client_info = json.loads(config.CLIENT_SECRET_JSON)
    creds = Credentials(
        token=None,
        refresh_token=config.REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_info["installed"]["client_id"],
        client_secret=client_info["installed"]["client_secret"],
        scopes=[
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/yt-analytics.readonly",
        ],
    )
    creds.refresh(Request())
    return creds


def get_recent_videos(youtube, days=14):
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    response = youtube.search().list(
        part="id,snippet",
        forMine=True,
        type="video",
        publishedAfter=since,
        maxResults=20,
        order="date",
    ).execute()
    return response.get("items", [])


def get_video_stats(youtube, video_id):
    response = youtube.videos().list(
        part="statistics,snippet",
        id=video_id,
    ).execute()
    items = response.get("items", [])
    return items[0] if items else None


def update_video_tags(youtube, video_id, snippet):
    current_tags = snippet.get("tags", [])
    new_tags = list(set(current_tags + EXTRA_TAGS))[:30]
    snippet["tags"] = new_tags

    youtube.videos().update(
        part="snippet",
        body={"id": video_id, "snippet": snippet},
    ).execute()
    print(f"  Updated tags for video: {video_id}")


def run():
    print("=== Optimize Agent ===\n")
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    videos = get_recent_videos(youtube, days=14)
    if not videos:
        print("最近の動画が見つかりませんでした")
        return

    view_counts = []
    for item in videos:
        video_id = item["id"]["videoId"]
        data = get_video_stats(youtube, video_id)
        if data:
            views = int(data["statistics"].get("viewCount", 0))
            view_counts.append(views)
            print(f"  {data['snippet']['title'][:50]} → {views} views")

    if not view_counts:
        return

    avg_views = sum(view_counts) / len(view_counts)
    print(f"\n  平均視聴数: {avg_views:.0f}")

    # 平均の50%以下の動画はタグを追加して最適化
    for item in videos:
        video_id = item["id"]["videoId"]
        data = get_video_stats(youtube, video_id)
        if not data:
            continue
        views = int(data["statistics"].get("viewCount", 0))
        if views < avg_views * 0.5:
            print(f"  低パフォーマンス検出 ({views} views) → タグ更新")
            update_video_tags(youtube, video_id, data["snippet"])

    print("\n✅ Optimize complete")


if __name__ == "__main__":
    run()

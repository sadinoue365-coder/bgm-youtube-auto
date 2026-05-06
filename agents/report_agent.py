"""
月次パフォーマンスレポートを生成してGitHub Issueに投稿する
"""
import json
import os
import subprocess
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import config


def get_credentials():
    client_info = json.loads(config.CLIENT_SECRET_JSON)
    creds = Credentials(
        token=None,
        refresh_token=config.REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_info["installed"]["client_id"],
        client_secret=client_info["installed"]["client_secret"],
        scopes=[
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/yt-analytics.readonly",
        ],
    )
    creds.refresh(Request())
    return creds


def get_channel_id(youtube):
    response = youtube.channels().list(part="id", mine=True).execute()
    return response["items"][0]["id"]


def get_monthly_analytics(yt_analytics, channel_id):
    today = datetime.utcnow()
    start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    response = yt_analytics.reports().query(
        ids=f"channel=={channel_id}",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched,subscribersGained,likes",
        dimensions="day",
        sort="day",
    ).execute()
    return response, start, end


def get_top_videos(youtube, channel_id):
    response = youtube.search().list(
        part="id,snippet",
        channelId=channel_id,
        type="video",
        order="viewCount",
        maxResults=3,
    ).execute()
    items = response.get("items", [])
    result = []
    for item in items:
        vid_id = item["id"]["videoId"]
        stats = youtube.videos().list(part="statistics", id=vid_id).execute()
        views = stats["items"][0]["statistics"].get("viewCount", "0") if stats["items"] else "0"
        result.append((item["snippet"]["title"][:60], int(views)))
    return result


def build_report(analytics_data, start, end, top_videos):
    rows = analytics_data.get("rows", [])
    total_views = sum(r[1] for r in rows)
    total_watch_min = sum(r[2] for r in rows)
    total_subs = sum(r[3] for r in rows)
    total_likes = sum(r[4] for r in rows)
    watch_hours = total_watch_min // 60

    month = datetime.utcnow().strftime("%Y年%m月")

    top_videos_text = ""
    for i, (title, views) in enumerate(top_videos, 1):
        top_videos_text += f"{i}. {title} — {views:,} views\n"

    report = f"""## 📊 {month} パフォーマンスレポート

**集計期間:** {start} 〜 {end}

### サマリー

| 指標 | 数値 |
|---|---|
| 総視聴数 | {total_views:,} views |
| 総視聴時間 | {watch_hours:,} 時間 |
| 新規登録者 | +{total_subs:,} 人 |
| いいね数 | {total_likes:,} |

### 今月のトップ動画

{top_videos_text}
---
*自動生成レポート by BGM YouTube Auto System*
"""
    return report, month


def run():
    print("=== Report Agent ===\n")
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    yt_analytics = build("youtubeAnalytics", "v2", credentials=creds)

    channel_id = get_channel_id(youtube)
    analytics_data, start, end = get_monthly_analytics(yt_analytics, channel_id)
    top_videos = get_top_videos(youtube, channel_id)

    report, month = build_report(analytics_data, start, end, top_videos)
    print(report)

    # GitHub Issueとして投稿
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if gh_token and repo:
        subprocess.run([
            "gh", "issue", "create",
            "--title", f"月次レポート {month}",
            "--body", report,
        ], env={**os.environ, "GH_TOKEN": gh_token}, check=True)
        print("✅ GitHub Issueに投稿しました")
    else:
        print("⚠️  GITHUB_TOKEN未設定のためIssue投稿をスキップ")

    print("\n✅ Report complete")


if __name__ == "__main__":
    run()

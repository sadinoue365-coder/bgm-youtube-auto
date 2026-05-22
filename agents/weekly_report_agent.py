"""
週次パフォーマンスレポート — 全4チャンネル

毎週月曜日に直近7日間の各チャンネル成績をまとめ、メール本文を生成する。
GitHub Actionsの dawidd6/action-send-mail でメール送信。

出力: 標準出力にメール本文 + 環境変数 GITHUB_OUTPUT にも書き出し
"""

import json
import os
import statistics
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


CHANNEL_CONFIGS = {
    "Chill": {
        "client_secret_env": "CHILL_CLIENT_SECRET_JSON",
        "refresh_token_env": "CHILL_REFRESH_TOKEN",
        "emoji": "🎵",
    },
    "Jazz": {
        "client_secret_env": "JAZZ_CLIENT_SECRET_JSON",
        "refresh_token_env": "JAZZ_REFRESH_TOKEN",
        "emoji": "🎷",
    },
    "Cafe": {
        "client_secret_env": "CAFE_CLIENT_SECRET_JSON",
        "refresh_token_env": "CAFE_REFRESH_TOKEN",
        "emoji": "☕",
    },
    "Sleep": {
        "client_secret_env": "SLEEP_CLIENT_SECRET_JSON",
        "refresh_token_env": "SLEEP_REFRESH_TOKEN",
        "emoji": "🌙",
    },
}


def get_credentials(client_secret_json, refresh_token):
    client_info = json.loads(client_secret_json)
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_info["installed"]["client_id"],
        client_secret=client_info["installed"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
    )
    creds.refresh(Request())
    return creds


def get_channel_stats(youtube, days=14):
    """直近14日の動画を取得し、今週・先週の視聴数を返す"""
    ch = youtube.channels().list(part="contentDetails,snippet,statistics", mine=True).execute()
    ch_item = ch["items"][0]
    playlist_id = ch_item["contentDetails"]["relatedPlaylists"]["uploads"]
    ch_name = ch_item["snippet"]["title"]
    total_subs = int(ch_item["statistics"].get("subscriberCount", 0))

    resp = youtube.playlistItems().list(
        part="snippet", playlistId=playlist_id, maxResults=50
    ).execute()

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    videos = []
    for item in resp.get("items", []):
        pub_str = item["snippet"]["publishedAt"]
        pub_dt = datetime.strptime(pub_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if pub_dt >= since:
            videos.append({
                "id": item["snippet"]["resourceId"]["videoId"],
                "title": item["snippet"]["title"],
                "published_at": pub_dt,
            })

    if not videos:
        return ch_name, total_subs, [], []

    # 統計取得
    ids = ",".join(v["id"] for v in videos)
    stats_resp = youtube.videos().list(part="statistics", id=ids).execute()
    stats_map = {s["id"]: s["statistics"] for s in stats_resp.get("items", [])}

    this_week = []
    last_week = []
    week_ago = now - timedelta(days=7)

    for v in videos:
        s = stats_map.get(v["id"], {})
        views = int(s.get("viewCount", 0))
        age_days = (now - v["published_at"]).days
        entry = {
            "title": v["title"],
            "views": views,
            "age_days": age_days,
            "published_at": v["published_at"],
        }
        if v["published_at"] >= week_ago:
            this_week.append(entry)
        else:
            last_week.append(entry)

    return ch_name, total_subs, this_week, last_week


def format_channel_section(name, emoji, ch_name, total_subs, this_week, last_week):
    lines = []
    lines.append(f"{emoji} {name} ({ch_name})")
    lines.append(f"   登録者数: {total_subs:,}")

    # 今週
    this_views = sum(v["views"] for v in this_week)
    lines.append(f"   今週の投稿: {len(this_week)}本 / 合計 {this_views:,} views")
    if this_week:
        top = sorted(this_week, key=lambda x: x["views"], reverse=True)[0]
        lines.append(f"   今週トップ: {top['title'][:50]} ({top['views']:,} views)")

    # 先週比
    last_views = sum(v["views"] for v in last_week)
    if last_week and last_views > 0:
        ratio = this_views / last_views * 100
        arrow = "↑" if ratio >= 100 else "↓"
        lines.append(f"   先週比: {arrow} {ratio:.0f}% (先週 {last_views:,} views)")

    # 低パフォーマンス警告
    all_views = [v["views"] for v in this_week + last_week]
    if len(all_views) >= 3:
        median = statistics.median(all_views)
        low = [v for v in this_week if v["views"] < median * 0.5 and v["age_days"] >= 7]
        if low:
            lines.append(f"   ⚠️  低パフォーマンス動画: {len(low)}本 (中央値{median:.0f}の50%未満)")

    return "\n".join(lines)


def run():
    now = datetime.now(timezone.utc)
    week_str = now.strftime("%Y/%m/%d")
    start_str = (now - timedelta(days=7)).strftime("%m/%d")
    end_str = now.strftime("%m/%d")

    subject = f"【週次レポート】BGM YouTube 4チャンネル ({start_str}〜{end_str})"

    sections = []
    total_this_views = 0
    total_last_views = 0
    total_subs_all = 0

    for name, cfg in CHANNEL_CONFIGS.items():
        client_secret = os.environ.get(cfg["client_secret_env"])
        refresh_token = os.environ.get(cfg["refresh_token_env"])
        if not client_secret or not refresh_token:
            sections.append(f"{cfg['emoji']} {name}: 認証情報なし")
            continue
        try:
            creds = get_credentials(client_secret, refresh_token)
            youtube = build("youtube", "v3", credentials=creds)
            ch_name, subs, this_week, last_week = get_channel_stats(youtube)
            total_this_views += sum(v["views"] for v in this_week)
            total_last_views += sum(v["views"] for v in last_week)
            total_subs_all += subs
            sections.append(format_channel_section(name, cfg["emoji"], ch_name, subs, this_week, last_week))
        except Exception as e:
            sections.append(f"{cfg['emoji']} {name}: エラー — {e}")

    ratio_text = ""
    if total_last_views > 0:
        ratio = total_this_views / total_last_views * 100
        arrow = "↑" if ratio >= 100 else "↓"
        ratio_text = f" ({arrow} 先週比 {ratio:.0f}%)"

    body = f"""BGM YouTube 週次レポート
集計期間: {start_str} 〜 {end_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【全チャンネル合計】
今週の視聴数: {total_this_views:,} views{ratio_text}
総登録者数:   {total_subs_all:,}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【チャンネル別内訳】

{chr(10).join(sections)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
※ 低パフォーマンス動画はoptimize_agentが自動で
  タグ・タイトル・説明文を改善します（投稿7日後）

Generated by BGM YouTube Auto System
"""

    print(f"SUBJECT: {subject}")
    print("=" * 60)
    print(body)

    # GitHub Actions output
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"subject={subject}\n")
            # body はマルチライン対応
            f.write(f"body<<EOF\n{body}\nEOF\n")

    return subject, body


if __name__ == "__main__":
    run()

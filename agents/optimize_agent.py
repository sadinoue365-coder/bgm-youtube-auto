"""
全チャンネル最適化エージェント

直近2週間の動画を分析し、低パフォーマンス動画を自動改善する。

【閾値】動画年齢で補正した自チャンネル中央値ベース
  - 0〜7日:  中央値の30%以下 → 深刻
  - 8〜14日: 中央値の50%以下 → 深刻 / 50〜70%以下 → 軽微

【アクション】
  - 軽微: タグ追加 + 説明文にキーワード追加
  - 深刻: 上記 + タイトル末尾にキーワード追加
"""

import json
import os
import statistics
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ─── チャンネル別設定 ─────────────────────────────────────────────
CHANNEL_CONFIGS = {
    "chill": {
        "client_secret_env": "CHILL_CLIENT_SECRET_JSON",
        "refresh_token_env": "CHILL_REFRESH_TOKEN",
        "extra_tags": [
            "chill music", "lofi", "study music", "relaxing music",
            "ambient music", "focus music", "work music", "background music",
            "chill beats", "study beats", "concentration music",
        ],
        "title_suffix": "Relaxing BGM | Study Music",
        "desc_footer": "\n\n🎵 #ChillMusic #LoFi #StudyMusic #RelaxingMusic #AmbientMusic #FocusMusic",
    },
    "jazz": {
        "client_secret_env": "JAZZ_CLIENT_SECRET_JSON",
        "refresh_token_env": "JAZZ_REFRESH_TOKEN",
        "extra_tags": [
            "jazz music", "smooth jazz", "jazz bar", "night jazz",
            "jazz bgm", "lounge music", "noir jazz", "jazz for studying",
            "late night jazz", "relaxing jazz",
        ],
        "title_suffix": "Jazz BGM | Night Music",
        "desc_footer": "\n\n🎷 #JazzMusic #SmoothJazz #JazzBar #NightJazz #LoungeMusic #NightVibes",
    },
    "cafe": {
        "client_secret_env": "CAFE_CLIENT_SECRET_JSON",
        "refresh_token_env": "CAFE_REFRESH_TOKEN",
        "extra_tags": [
            "cafe music", "coffee shop music", "bossa nova", "study cafe",
            "work cafe", "cafe bgm", "coffee music", "acoustic background",
            "relaxing cafe", "morning music",
        ],
        "title_suffix": "Cafe Music | Study BGM",
        "desc_footer": "\n\n☕ #CafeMusic #CoffeeShop #BossaNova #StudyCafe #MorningMusic",
    },
    "sleep": {
        "client_secret_env": "SLEEP_CLIENT_SECRET_JSON",
        "refresh_token_env": "SLEEP_REFRESH_TOKEN",
        "extra_tags": [
            "sleep music", "black screen sleep music", "deep sleep",
            "insomnia relief", "sleep aid", "delta waves", "sleep sounds",
            "relaxing sleep music", "8 hours sleep", "healing sleep music",
        ],
        "title_suffix": "Sleep Aid | Insomnia Relief",
        "desc_footer": "\n\n🌙 #SleepMusic #BlackScreen #DeepSleep #InsomniaRelief #SleepAid #DeltaWaves",
    },
}


# ─── 認証 ────────────────────────────────────────────────────────
def get_credentials(client_secret_json, refresh_token):
    client_info = json.loads(client_secret_json)
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_info["installed"]["client_id"],
        client_secret=client_info["installed"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    creds.refresh(Request())
    return creds


# ─── 直近14日の動画取得 ──────────────────────────────────────────
def get_recent_videos(youtube, days=14):
    ch = youtube.channels().list(part="contentDetails", mine=True).execute()
    playlist_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    resp = youtube.playlistItems().list(
        part="snippet", playlistId=playlist_id, maxResults=30
    ).execute()

    since = datetime.now(timezone.utc) - timedelta(days=days)
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
    return videos


# ─── 動画の詳細（統計+snippet）取得 ─────────────────────────────
def get_video_detail(youtube, video_id):
    resp = youtube.videos().list(part="statistics,snippet", id=video_id).execute()
    items = resp.get("items", [])
    return items[0] if items else None


# ─── タイトル更新（末尾にキーワード追加） ────────────────────────
def update_title(youtube, video_id, snippet, suffix):
    current = snippet["title"]
    if suffix.split("|")[0].strip() in current:
        return False
    new_title = f"{current} | {suffix}"[:100]
    snippet["title"] = new_title
    youtube.videos().update(
        part="snippet",
        body={"id": video_id, "snippet": snippet},
    ).execute()
    print(f"    タイトル更新: ...| {suffix}")
    return True


# ─── 説明文更新（末尾にキーワード追加） ──────────────────────────
def update_description(youtube, video_id, snippet, footer):
    current_desc = snippet.get("description", "")
    if footer.strip() in current_desc:
        return False
    snippet["description"] = current_desc + footer
    youtube.videos().update(
        part="snippet",
        body={"id": video_id, "snippet": snippet},
    ).execute()
    print(f"    説明文更新: フッター追加")
    return True


# ─── タグ更新 ───────────────────────────────────────────────────
def update_tags(youtube, video_id, snippet, extra_tags):
    current = snippet.get("tags", [])
    new_tags = list(dict.fromkeys(current + extra_tags))[:30]
    if set(new_tags) == set(current):
        return False
    snippet["tags"] = new_tags
    youtube.videos().update(
        part="snippet",
        body={"id": video_id, "snippet": snippet},
    ).execute()
    print(f"    タグ更新: {len(new_tags)}個")
    return True


# ─── チャンネル単位の最適化 ──────────────────────────────────────
def optimize_channel(channel_key, cfg):
    client_secret = os.environ.get(cfg["client_secret_env"])
    refresh_token = os.environ.get(cfg["refresh_token_env"])

    if not client_secret or not refresh_token:
        print(f"  [{channel_key}] 認証情報なし → スキップ")
        return

    print(f"\n{'='*50}")
    print(f"  チャンネル: {channel_key.upper()}")
    print(f"{'='*50}")

    try:
        creds = get_credentials(client_secret, refresh_token)
        youtube = build("youtube", "v3", credentials=creds)
        videos = get_recent_videos(youtube, days=14)

        if not videos:
            print("  直近14日の動画なし → スキップ")
            return

        # 視聴数取得
        video_data = []
        for v in videos:
            detail = get_video_detail(youtube, v["id"])
            if detail:
                views = int(detail["statistics"].get("viewCount", 0))
                age_days = (datetime.now(timezone.utc) - v["published_at"]).days
                video_data.append({
                    "id": v["id"],
                    "views": views,
                    "age_days": age_days,
                    "snippet": detail["snippet"],
                })
                print(f"  {v['title'][:55]} | {views}views / {age_days}日")

        if not video_data:
            return

        # 中央値計算
        median_views = statistics.median([v["views"] for v in video_data])
        print(f"\n  中央値: {median_views:.0f} views")

        # 各動画を評価・最適化
        optimized = 0
        for v in video_data:
            if v["age_days"] <= 7:
                severe_threshold = 0.30
                mild_threshold   = None
            else:
                severe_threshold = 0.50
                mild_threshold   = 0.70

            ratio = v["views"] / median_views if median_views > 0 else 1.0
            snippet = v["snippet"]

            if ratio <= severe_threshold:
                print(f"\n  ⚠️  深刻 ({v['views']}views / 中央値比{ratio:.0%}) → {snippet['title'][:50]}")
                update_tags(youtube, v["id"], snippet, cfg["extra_tags"])
                update_description(youtube, v["id"], snippet, cfg["desc_footer"])
                update_title(youtube, v["id"], snippet, cfg["title_suffix"])
                optimized += 1

            elif mild_threshold and ratio <= mild_threshold:
                print(f"\n  📉 軽微 ({v['views']}views / 中央値比{ratio:.0%}) → {snippet['title'][:50]}")
                update_tags(youtube, v["id"], snippet, cfg["extra_tags"])
                update_description(youtube, v["id"], snippet, cfg["desc_footer"])
                optimized += 1

        print(f"\n  ✅ {optimized}/{len(video_data)} 本を最適化")

    except Exception as e:
        print(f"  [{channel_key}] エラー: {e}")


# ─── メイン ──────────────────────────────────────────────────────
def run():
    print("=== Weekly Optimize Agent ===\n")
    print("対象: Chill / Jazz / Cafe / Sleep\n")

    for key, cfg in CHANNEL_CONFIGS.items():
        optimize_channel(key, cfg)

    print("\n✅ 全チャンネル最適化完了")


if __name__ == "__main__":
    run()

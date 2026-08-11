import datetime
import io
import json
import random
import ssl
import time

import jazz_config as config
from agents.duration_agent import get_random_duration, format_duration
from agents.wolf_image_agent import generate_wolf_image
from agents.jazz_video_agent import create_jazz_video
from agents.loop_agent import loop_audio
from agents.thumbnail_agent import create_thumbnail
from agents.cleanup_agent import cleanup
from agents.playlist_agent import add_to_playlist
from agents.trending_agent import get_trending_tags, get_top_performing_styles
from agents.timing_agent import record_upload, update_timing_metrics

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

MOODS = [
    "Midnight", "Smoky", "Rainy Night", "Late Night", "Dark",
    "3AM", "Moonlit", "Foggy", "Velvet", "Stormy",
    "Whiskey", "Candlelit", "Neon", "Shadowy", "Lonely",
    "Brooding", "Melancholic", "Silky", "Dim", "Haunting",
]

STYLES = [
    "Noir Jazz", "Hardboiled Jazz", "Slow Jazz", "Cool Jazz", "Dark Jazz",
    "Jazz Lounge", "Bebop", "Smooth Jazz", "Blues Jazz", "Swing Jazz",
    "Late Night Jazz", "Jazz Bar", "Midnight Jazz", "Jazz Ballad", "Neo Soul Jazz",
]

SETTINGS = [
    "for Late Night Work", "for Deep Focus", "for Reading & Whiskey",
    "for Rainy Evenings", "for Creative Writing", "for Insomniacs",
    "for the Lonely Hours", "for Slow Mornings", "for the Last Train Home",
    "for Dimly Lit Rooms", "for Thinking Too Much", "for Night Owls",
]

# タイトル先頭に置く検索需要の高いフレーズ（YouTube検索で実際に打たれる言葉）
SEARCH_HOOKS = [
    "Relaxing Jazz for Sleep",
    "Late Night Jazz for Work & Study",
    "Rainy Night Jazz",
    "Jazz for Deep Sleep & Stress Relief",
    "Study Jazz Music",
    "Smooth Jazz for Relaxing",
    "Night Jazz Bar Ambience",
    "Jazz Piano for Work & Focus",
    "Calm Jazz for Reading",
    "Sleep Jazz Music",
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
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    creds.refresh(Request())
    return creds


def download_random_mp3s(creds, num=10, dest_dir="work"):
    import os
    service = build("drive", "v3", credentials=creds)
    results = service.files().list(
        q=f"'{config.GDRIVE_FOLDER_ID}' in parents and mimeType='audio/mpeg' and trashed=false",
        fields="files(id, name)",
        pageSize=200,
    ).execute()

    files = results.get("files", [])
    if not files:
        raise Exception("Google DriveにMP3ファイルが見つかりません")

    selected = random.sample(files, min(num, len(files)))
    os.makedirs(dest_dir, exist_ok=True)
    downloaded = []
    for f in selected:
        path = os.path.join(dest_dir, f["name"])
        request = service.files().get_media(fileId=f["id"])
        with io.FileIO(path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        downloaded.append(path)
        print(f"  Downloaded: {f['name']}")
    return downloaded


def upload_video(creds, video_path, thumbnail_path, title, description, tags,
                 publish_at_utc=None):
    service = build("youtube", "v3", credentials=creds)
    status = {
        "privacyStatus": "public",
        "selfDeclaredMadeForKids": False,
        "madeForKids": False,
    }
    if publish_at_utc is not None:
        # 予約公開: 非公開でアップし、指定時刻にYouTubeが自動公開する
        from agents.publish_agent import to_rfc3339
        status["privacyStatus"] = "private"
        status["publishAt"] = to_rfc3339(publish_at_utc)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "10",
        },
        "status": status,
    }
    media = MediaFileUpload(
        video_path, mimetype="video/mp4", resumable=True, chunksize=50 * 1024 * 1024
    )
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retry = 0
    max_retries = 5
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  Uploading... {int(status.progress() * 100)}%")
            retry = 0  # チャンク成功時はカウントリセット
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                retry += 1
                if retry > max_retries:
                    raise
                wait = min(2 ** retry, 64)
                print(f"  HTTP {e.resp.status} エラー、{wait}秒後にリトライ ({retry}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
        except (ssl.SSLEOFError, ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError) as e:
            retry += 1
            if retry > max_retries:
                raise
            wait = min(2 ** retry, 64)
            print(f"  ネットワークエラー ({type(e).__name__})、{wait}秒後にリトライ ({retry}/{max_retries})...")
            time.sleep(wait)

    video_id = response["id"]
    print(f"  Uploaded: https://www.youtube.com/watch?v={video_id}")

    retry = 0
    while True:
        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
            break
        except (ssl.SSLEOFError, ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError) as e:
            retry += 1
            if retry > max_retries:
                raise
            wait = min(2 ** retry, 64)
            print(f"  サムネイル設定エラー ({type(e).__name__})、{wait}秒後にリトライ ({retry}/{max_retries})...")
            time.sleep(wait)

    return video_id


def generate_metadata(scene, target_hours):
    mood = random.choice(MOODS)
    style = random.choice(STYLES)
    setting = random.choice(SETTINGS)
    hook = random.choice(SEARCH_HOOKS)
    now = datetime.datetime.now()
    dur = format_duration(target_hours)

    # 検索需要ワードを先頭に、キャラ性(mood/style)を後半に
    title = f"{hook} 🎷 {mood} {style} {setting} | {dur}"

    # 冒頭2行は検索インデックス用のキーワード文（詩的表現はその後）
    description = f"""Relaxing jazz music for sleeping, studying, working and stress relief. {dur} of {style.lower()} with a smoky midnight bar atmosphere — perfect background music for deep focus, reading, or falling asleep.

🐺 Step into the smoky world of Red Wolf's noir jazz.

Perfect for:
✅ Late night work sessions
✅ Deep focus & concentration
✅ Relaxing with whiskey
✅ Rainy evening vibes
✅ Creative writing & reading

🎵 AI-generated original music — no copyright
🎨 AI-generated artwork
📅 {now.strftime('%B %Y')}

⚠️ This content contains AI-generated music and visuals

#{style.replace(' ', '')} #NightJazz #NightMusic #BGM #JazzMusic
#LateNightVibes #NoirJazz #RelaxingJazz #SmokyJazz #WorkMusic

─────────────────────────────
🎵 More relaxing music on our channels:
  ☕ Coffee Shop BGM → Coffee Shop Music Studio
  🌊 Chill & Study  → Chill Relax BGM
  🌙 Sleep Music    → Drift Into Sleep Music
─────────────────────────────
"""

    tags = [
        "jazz", "relaxing jazz", "jazz for sleep", "study jazz", "jazz for work",
        "late night jazz", "rainy night jazz", "jazz bar ambience", "smooth jazz",
        "sleep music", "study music", "focus music", "background music",
        "noir jazz", style, "BGM", f"{format_duration(target_hours).lower()} mix",
    ]

    return title, description, tags


def main():
    print("=== Jazz Wolf BGM Auto System ===\n")

    print("[1/6] Authenticating...")
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    print("\n[Timing] Measuring past upload performance...")
    update_timing_metrics(youtube, "jazz")

    print("\n[Trend] Analyzing trending keywords & top styles...")
    trending_tags = get_trending_tags(youtube, "jazz bgm late night")
    style_weights = get_top_performing_styles(youtube, STYLES)
    weighted_styles = [s for s in STYLES for _ in range(style_weights.get(s, 1))]
    scene = random.choice(weighted_styles)

    print("\n[2/6] Downloading MP3s from Google Drive...")
    mp3_paths = download_random_mp3s(creds, num=config.NUM_SONGS, dest_dir=config.WORK_DIR)

    target_hours = get_random_duration()
    print(f"  Today's duration: {format_duration(target_hours)}")

    print("\n[3/6] Creating looped audio...")
    audio_path = loop_audio(mp3_paths, target_hours=target_hours,
                            output_path=f"{config.WORK_DIR}/looped.mp3")

    print("\n[4/6] Fetching wolf image from Google Drive...")
    image_path, _, img_source = generate_wolf_image(
        creds,
        config.IMAGE_FOLDER_ID,
        output_path=f"{config.WORK_DIR}/wolf_bg.jpg",
    )
    # ソフト障害監視: AI生成もDrive取得も失敗し真っ暗なPIL背景になった場合は即通知
    if img_source == "pil":
        from agents.alert_agent import send_alert
        send_alert(
            "Jazz画像が真っ暗なフォールバックになりました",
            "Jazzの動画生成で、HF(AI生成)とDrive取得の両方が失敗し、\n"
            "PILの黒背景にフォールバックしました。サムネ・背景が真っ暗になります。\n\n"
            "考えられる原因:\n"
            "  1. HF_API_TOKEN の無料枠超過/失効、またはHF側の一時障害\n"
            "  2. JAZZ_IMAGE_FOLDER_ID のフォルダに狼画像が無い"
            "（スクリーンショットのみは除外されます）\n\n"
            "対処: Driveフォルダに狼のjpg/png画像を入れる / HFトークンを確認してください。",
        )

    print("\n[5/6] Creating video...")
    video_path = create_jazz_video(image_path, audio_path,
                                   output_path=f"{config.WORK_DIR}/output.mp4")

    title, description, tags = generate_metadata(scene, target_hours)
    tags = list(dict.fromkeys(tags + trending_tags))[:30]  # トレンドタグを追加（最大30）

    print("\n[6/6] Creating thumbnail & uploading...")
    thumbnail_path = create_thumbnail(
        title[:50],
        output_path=f"{config.WORK_DIR}/thumbnail.jpg",
        background_path=image_path,
        channel_name=config.CHANNEL_NAME,
        target_hours=target_hours,
        accent_color=(220, 180, 60),  # Jazz: ゴールド
        style="minimal",
    )
    from agents.publish_agent import next_publish_time_utc, JST
    publish_at = next_publish_time_utc(config.PUBLISH_HOUR_JST)
    print(f"  予約公開: {publish_at.astimezone(JST).strftime('%m/%d %H:%M JST')}")
    video_id = upload_video(creds, video_path, thumbnail_path, title, description, tags,
                            publish_at_utc=publish_at)

    print("\nAdding to playlist...")
    add_to_playlist(youtube, video_id, config.PLAYLIST_ID)

    record_upload("jazz", video_id, published_at=publish_at)

    print("\nCleaning up...")
    cleanup(config.WORK_DIR)

    print(f"\n✅ Done! https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        cleanup(config.WORK_DIR)
        print(f"\n❌ Fatal error: {e}")
        raise

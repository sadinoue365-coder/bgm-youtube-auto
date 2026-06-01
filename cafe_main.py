import datetime
import io
import json
import random
import ssl
import time

import cafe_config as config
from agents.duration_agent import get_random_duration, format_duration
from agents.image_agent import fetch_pexels_image
from agents.static_video_agent import create_static_video
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
    "Relaxing", "Peaceful", "Cozy", "Warm", "Soothing",
    "Mellow", "Tranquil", "Gentle", "Soft", "Serene",
]

STYLES = [
    "Coffee Shop Music", "Cafe Music", "Bossa Nova Cafe",
    "Jazz Piano Cafe", "Acoustic Cafe", "Lo-fi Cafe",
    "Cafe Jazz", "Coffee Jazz", "Cafe Bossa Nova",
    "Acoustic Coffee Shop",
]

SETTINGS = [
    "for Work & Focus", "for Study Sessions", "for Deep Focus",
    "for Relaxation", "for Reading", "for Rainy Days",
    "for Morning Coffee", "for Creative Writing", "for Slow Mornings",
    "for Cozy Evenings",
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


def upload_video(creds, video_path, thumbnail_path, title, description, tags):
    service = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "10",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "madeForKids": False,
        },
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
            retry = 0
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

    service.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
    ).execute()
    return video_id


def generate_metadata(scene_keyword, target_hours):
    mood = random.choice(MOODS)
    style = random.choice(STYLES)
    setting = random.choice(SETTINGS)
    now = datetime.datetime.now()
    dur = format_duration(target_hours)

    title = f"Coffee Shop Music | {mood} {style} {setting} | {dur} BGM"

    description = f"""☕ {dur} {mood} {style} {setting}

Step into your perfect coffee shop atmosphere.

Perfect for:
✅ Work from home & deep focus
✅ Study sessions
✅ Morning coffee ritual
✅ Relaxing & unwinding
✅ Rainy day vibes
✅ Creative writing & reading

🎵 AI-generated original music — no copyright
🎨 Beautiful cafe imagery
📅 {now.strftime('%B %Y')}

⚠️ This content contains AI-generated music

#CoffeeShopMusic #CafeMusic #BGM #StudyMusic #WorkMusic
#RelaxingMusic #BossaNova #JazzPiano #LofiJazz #CoffeeMusicJazz

─────────────────────────────
🎵 More relaxing music on our channels:
  🎷 Night Jazz BGM → Red Wolf's Lounge
  🌊 Chill & Study  → Chill Relax BGM
  🌙 Sleep Music    → Drift Into Sleep Music
─────────────────────────────
"""

    tags = [
        "coffee shop music", "cafe music", "bossa nova", "jazz piano",
        "lo-fi jazz", "study music", "work music", "relaxing music",
        "background music", "BGM", "cafe BGM", "instrumental music",
        "coffee music", "acoustic guitar", f"{dur.lower()} mix",
        "no copyright music", "AI music", scene_keyword,
    ]

    return title, description, tags


def main():
    print("=== Coffee Shop Music Studio Auto System ===\n")

    print("[1/6] Authenticating...")
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    print("\n[Timing] Measuring past upload performance...")
    update_timing_metrics(youtube, "cafe")

    print("\n[Trend] Analyzing trending keywords & top styles...")
    trending_tags = get_trending_tags(youtube, "coffee shop music morning")
    style_weights = get_top_performing_styles(youtube, STYLES)
    weighted_styles = [s for s in STYLES for _ in range(style_weights.get(s, 1))]
    scene_keyword = random.choice(weighted_styles)

    target_hours = get_random_duration()
    print(f"  Today's duration: {format_duration(target_hours)}")

    print("\n[2/6] Downloading MP3s from Google Drive...")
    mp3_paths = download_random_mp3s(creds, num=config.NUM_SONGS, dest_dir=config.WORK_DIR)

    print("\n[3/6] Creating looped audio...")
    audio_path = loop_audio(mp3_paths, target_hours=target_hours,
                            output_path=f"{config.WORK_DIR}/looped.mp3")

    print("\n[4/6] Fetching background image from Pexels...")
    image_path, _ = fetch_pexels_image(
        config.PEXELS_API_KEY, config.PEXELS_QUERIES,
        output_path=f"{config.WORK_DIR}/background.jpg"
    )

    print("\n[5/6] Creating video...")
    video_path = create_static_video(image_path, audio_path,
                                     output_path=f"{config.WORK_DIR}/output.mp4")

    title, description, tags = generate_metadata(scene_keyword, target_hours)
    tags = list(dict.fromkeys(tags + trending_tags))[:30]  # トレンドタグを追加

    print("\n[6/6] Creating thumbnail & uploading...")
    thumbnail_path = create_thumbnail(
        title,
        output_path=f"{config.WORK_DIR}/thumbnail.jpg",
        background_path=image_path,
        channel_name=config.CHANNEL_NAME,
        target_hours=target_hours,
        accent_color=(210, 160, 90),  # Cafe: ウォームブラウン
        style="minimal",
    )
    video_id = upload_video(creds, video_path, thumbnail_path, title, description, tags)

    if config.PLAYLIST_ID:
        print("\nAdding to playlist...")
        add_to_playlist(youtube, video_id, config.PLAYLIST_ID)

    record_upload("cafe", video_id)

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

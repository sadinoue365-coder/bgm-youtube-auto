import datetime
import json
import random
import ssl
import time

import chill_config as config
from agents.duration_agent import get_random_duration, format_duration
from agents.timing_agent import record_upload, update_timing_metrics
from agents.image_agent import fetch_pexels_image
from agents.static_video_agent import create_static_video
from agents.loop_agent import loop_audio
from agents.thumbnail_agent import create_thumbnail
from agents.cleanup_agent import cleanup
from agents.playlist_agent import add_to_playlist

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import io
from googleapiclient.http import MediaIoBaseDownload

MOODS = ["Relaxing", "Peaceful", "Calming", "Soothing", "Tranquil"]
SCENES = ["Beach Sunset", "Ocean Waves", "Forest Morning", "Mountain Lake", "Tropical Paradise"]


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


def download_random_mp3s(creds, num=5, dest_dir="work"):
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
    import os
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
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=50 * 1024 * 1024)
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


def generate_metadata(scene_keyword, target_hours):
    mood = random.choice(MOODS)
    now = datetime.datetime.now()
    dur = format_duration(target_hours)
    title = f"{mood} Chill Music | {scene_keyword.title()} | {dur} Relaxing BGM"
    description = f"""🌊 {dur} {mood} Chill Music for Relaxation & Focus

Perfect for:
✅ Work from home
✅ Study sessions
✅ Meditation & yoga
✅ Sleep & relaxation
✅ Stress relief

🎵 AI-generated original music — no copyright
📅 {now.strftime('%B %Y')}

#ChillMusic #RelaxingMusic #BGM #StudyMusic #WorkMusic #Meditation #Lofi #AmbientMusic

─────────────────────────────
🎵 More relaxing music on our channels:
  🎷 Night Jazz BGM → Red Wolf's Lounge
  ☕ Coffee Shop BGM → Coffee Shop Music Studio
  🌙 Sleep Music    → Drift Into Sleep Music
─────────────────────────────
"""
    tags = [
        "chill music", "relaxing music", "BGM", "study music", "work music",
        "meditation music", "ambient music", "sleep music", "stress relief",
        "lofi", "chillout", scene_keyword, f"{dur.lower()} mix",
        "no copyright music", "AI music",
    ]
    return title, description, tags


def main():
    print("=== Chill BGM YouTube Auto System ===\n")

    print("[1/5] Authenticating...")
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    print("\n[Timing] Measuring past upload performance...")
    update_timing_metrics(youtube, "chill")

    target_hours = get_random_duration()
    print(f"  Today's duration: {format_duration(target_hours)}")

    print("\n[2/5] Downloading MP3s from Google Drive...")
    mp3_paths = download_random_mp3s(creds, num=config.NUM_SONGS, dest_dir=config.WORK_DIR)

    print("\n[3/5] Creating looped audio...")
    audio_path = loop_audio(mp3_paths, target_hours=target_hours,
                            output_path=f"{config.WORK_DIR}/looped.mp3")

    print("\n[4/5] Fetching background image from Pexels...")
    image_path, scene_keyword = fetch_pexels_image(
        config.PEXELS_API_KEY, config.PEXELS_QUERIES,
        output_path=f"{config.WORK_DIR}/background.jpg"
    )

    print("\n[5/5] Creating video...")
    video_path = create_static_video(image_path, audio_path,
                                     output_path=f"{config.WORK_DIR}/output.mp4")

    title, description, tags = generate_metadata(scene_keyword, target_hours)

    print("\n[6/6] Creating thumbnail & uploading...")
    thumbnail_path = create_thumbnail(
        title[:50],
        output_path=f"{config.WORK_DIR}/thumbnail.jpg",
        background_path=image_path,
        channel_name=config.CHANNEL_NAME,
        target_hours=target_hours,
        accent_color=(0, 220, 180),  # Chill: ティール
        style="minimal",
    )
    from agents.publish_agent import next_publish_time_utc, JST
    publish_at = next_publish_time_utc(config.PUBLISH_HOUR_JST)
    print(f"  予約公開: {publish_at.astimezone(JST).strftime('%m/%d %H:%M JST')}")
    video_id = upload_video(creds, video_path, thumbnail_path, title, description, tags,
                            publish_at_utc=publish_at)

    print("\nAdding to playlist...")
    add_to_playlist(youtube, video_id, config.PLAYLIST_ID)

    record_upload("chill", video_id, published_at=publish_at)

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

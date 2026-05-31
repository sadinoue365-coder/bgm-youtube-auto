"""
Drift Into Sleep Music — YouTube自動アップロードスクリプト
完全真っ黒画面・波形なし・睡眠特化
"""

import datetime
import io
import json
import os
import random
import subprocess
import sys

import sleep_config as config
from agents.duration_agent import get_random_duration, format_duration
from agents.timing_agent import record_upload, update_timing_metrics
from agents.loop_agent import loop_audio
from agents.thumbnail_agent import create_thumbnail
from agents.cleanup_agent import cleanup

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from PIL import Image, ImageDraw


SLEEP_STYLES = [
    "Delta Waves", "Soft Drones", "Gentle Rain",
    "Tibetan Bowls", "Ocean Drift", "Cosmic Drift",
    "Forest Night", "Deep Ambient", "Theta Waves",
    "White Noise", "Healing Tones", "Midnight Rain",
]

MOODS = [
    "Deep Sleep", "Gentle Sleep", "Peaceful Sleep",
    "Calm Sleep", "Soft Sleep", "Restful Sleep",
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


def download_random_mp3s(creds, num=8, dest_dir="work"):
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


def create_black_image(output_path):
    """完全真っ黒の1920x1080画像を生成"""
    img = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    img.save(output_path, "JPEG", quality=95)
    return output_path


def create_black_thumbnail_bg(output_path):
    """サムネイル用：ほぼ黒に極微かなグラデーション"""
    w, h = 1280, 720
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for i in range(h):
        v = int(12 * (1 - i / h))  # 上部に極わずかな輝き
        draw.line([(0, i), (w, i)], fill=(v, v, v + 3))
    img.save(output_path, "JPEG", quality=95)
    return output_path


def create_black_video(audio_path, output_path):
    """完全真っ黒・波形なし・音声のみの動画を生成"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=24",  # 24fps (YouTube推奨最低値)
        "-i", audio_path,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ], check=True)
    print(f"  Black screen video created: {output_path}")
    return output_path


def generate_metadata(style, target_hours):
    mood = random.choice(MOODS)
    dur = format_duration(target_hours)
    now = datetime.datetime.now()

    title = f"Black Screen Sleep Music | {style} | {dur}"

    description = f"""🌙 {dur} Black Screen Sleep Music — No light. Just sound.

Screen stays completely BLACK the entire time.
Safe to leave on all night without any light disturbing your sleep.

✨ {style}

Perfect for:
🌙 Falling asleep faster
🌙 Staying asleep all night
🌙 No blue light, no distractions
🌙 Insomnia relief
🌙 Deep meditation before sleep
🌙 Anxiety & stress relief

🎵 AI-generated original music — no copyright issues
📅 {now.strftime('%B %Y')}

─────────────────────────────
💤 Subscribe for daily sleep music
🔔 Turn on notifications — new video every day
─────────────────────────────

#SleepMusic #BlackScreen #DeepSleep #SleepAid #InsomniaCure
#AmbientMusic #DeltaWaves #Meditation #Relaxing #NoCopyrightMusic
#{style.replace(' ', '').replace('Hz', 'Hz')}

─────────────────────────────
🎵 More relaxing music on our channels:
  🎷 Night Jazz BGM → Red Wolf's Lounge
  ☕ Coffee Shop BGM → Coffee Shop Music Studio
  🌊 Chill & Study  → Chill Relax BGM
─────────────────────────────
"""

    tags = [
        "sleep music", "black screen sleep music", "deep sleep",
        "sleep aid", "insomnia", "ambient sleep music",
        "delta waves", "meditation", "relaxing music",
        "no light sleep", "8 hours sleep music",
        "no copyright music", "AI music",
        style.lower(), f"{dur.lower()} sleep music",
        "black screen", "sleep sounds",
    ]

    return title, description, tags


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
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Uploading... {int(status.progress() * 100)}%")
    video_id = response["id"]
    print(f"  Uploaded: https://www.youtube.com/watch?v={video_id}")
    service.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
    ).execute()
    return video_id


def add_to_playlist(creds, video_id, playlist_id):
    service = build("youtube", "v3", credentials=creds)
    service.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            }
        },
    ).execute()
    print(f"  Added to playlist: {playlist_id}")


def main():
    print("=== Drift Into Sleep Music ===\n")

    print("[1/5] Authenticating...")
    creds = get_credentials()
    youtube_client = build("youtube", "v3", credentials=creds)

    print("\n[Timing] Measuring past upload performance...")
    update_timing_metrics(youtube_client, "sleep")

    # 睡眠向け：長め時間を重み付きでランダム選択
    # 8〜12時間を30分刻みでランダム選択
    durations = [8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0]
    target_hours = random.choice(durations)
    style = random.choice(SLEEP_STYLES)
    print(f"  Duration: {format_duration(target_hours)} / Style: {style}")

    print("\n[2/5] Downloading MP3s from Google Drive...")
    mp3_paths = download_random_mp3s(creds, num=config.NUM_SONGS, dest_dir=config.WORK_DIR)

    print("\n[3/5] Creating looped audio...")
    audio_path = loop_audio(
        mp3_paths, target_hours=target_hours,
        output_path=f"{config.WORK_DIR}/looped.mp3"
    )

    print("\n[4/5] Creating black screen video...")
    video_path = create_black_video(
        audio_path,
        output_path=f"{config.WORK_DIR}/output.mp4",
    )

    print("\n[5/5] Creating thumbnail & uploading...")
    thumb_bg = f"{config.WORK_DIR}/thumb_bg.jpg"
    create_black_thumbnail_bg(thumb_bg)

    title, description, tags = generate_metadata(style, target_hours)
    print(f"  Title: {title}")

    thumbnail_path = create_thumbnail(
        title,
        output_path=f"{config.WORK_DIR}/thumbnail.jpg",
        channel_name=config.CHANNEL_NAME,
        target_hours=target_hours,
        style="sleep",
    )

    video_id = upload_video(creds, video_path, thumbnail_path, title, description, tags)

    print("\nAdding to playlist...")
    add_to_playlist(creds, video_id, config.PLAYLIST_ID)

    record_upload("sleep", video_id)

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

import datetime
import io
import json
import random

import jazz_config as config
from agents.wolf_image_agent import generate_wolf_image
from agents.jazz_video_agent import create_jazz_video
from agents.loop_agent import loop_audio
from agents.thumbnail_agent import create_thumbnail
from agents.cleanup_agent import cleanup
from agents.playlist_agent import add_to_playlist

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
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


def generate_metadata(scene):
    mood = random.choice(MOODS)
    style = random.choice(STYLES)
    setting = random.choice(SETTINGS)
    now = datetime.datetime.now()

    title = f"Jazz BGM | {mood} {style} {setting} | {config.TARGET_HOURS}H"

    description = f"""🐺 {config.TARGET_HOURS}-Hour {mood} {style} for Late Nights & Deep Focus

Step into the smoky world of noir jazz.

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
"""

    tags = [
        "jazz", "noir jazz", style, "BGM", "late night music",
        "work music", "focus music", "relaxing jazz", "smooth jazz",
        "AI music", "no copyright music", f"{config.TARGET_HOURS} hour mix",
        "night music", "dark jazz", "cool jazz",
    ]

    return title, description, tags


def main():
    print("=== Jazz Wolf BGM Auto System ===\n")

    print("[1/6] Authenticating...")
    creds = get_credentials()

    print("\n[2/6] Downloading MP3s from Google Drive...")
    mp3_paths = download_random_mp3s(creds, num=config.NUM_SONGS, dest_dir=config.WORK_DIR)

    print("\n[3/6] Creating looped audio...")
    audio_path = loop_audio(mp3_paths, target_hours=config.TARGET_HOURS,
                            output_path=f"{config.WORK_DIR}/looped.mp3")

    print("\n[4/6] Fetching wolf image from Google Drive...")
    image_path, scene = generate_wolf_image(
        creds,
        config.IMAGE_FOLDER_ID,
        output_path=f"{config.WORK_DIR}/wolf_bg.jpg",
    )

    print("\n[5/6] Creating video...")
    video_path = create_jazz_video(image_path, audio_path,
                                   output_path=f"{config.WORK_DIR}/output.mp4")

    title, description, tags = generate_metadata(scene)

    print("\n[6/6] Creating thumbnail & uploading...")
    thumbnail_path = create_thumbnail(
        title[:50],
        output_path=f"{config.WORK_DIR}/thumbnail.jpg",
        background_path=image_path,
        channel_name=config.CHANNEL_NAME,
        target_hours=config.TARGET_HOURS,
        accent_color=(220, 180, 60),  # Jazz: ゴールド
    )
    video_id = upload_video(creds, video_path, thumbnail_path, title, description, tags)

    print("\nAdding to playlist...")
    youtube = build("youtube", "v3", credentials=creds)
    add_to_playlist(youtube, video_id, config.PLAYLIST_ID)

    print("\nCleaning up...")
    cleanup(config.WORK_DIR)

    print(f"\n✅ Done! https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()

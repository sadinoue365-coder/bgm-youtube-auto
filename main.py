import datetime
import random

import config
from agents.drive_agent import download_random_mp3s
from agents.loop_agent import loop_audio
from agents.video_agent import create_waveform_video
from agents.thumbnail_agent import create_thumbnail
from agents.upload_agent import upload_video
from agents.cleanup_agent import cleanup
from agents.playlist_agent import add_to_playlist
from googleapiclient.discovery import build

GENRES = ["Deep House", "Tech House", "Melodic Techno", "Ambient House", "Progressive House"]
MOODS = ["Dark", "Uplifting", "Groovy", "Chill", "Intense"]


def generate_metadata():
    genre = random.choice(GENRES)
    mood = random.choice(MOODS)
    now = datetime.datetime.now()

    title = f"{mood} {genre} Mix {now.strftime('%Y.%m')} | {config.TARGET_HOURS}H Non-Stop BGM"

    description = f"""🎧 {config.TARGET_HOURS}-Hour {mood} {genre} Mix for Work, Study & Focus

Perfect background music for:
✅ Deep work & coding
✅ Study sessions
✅ Late night vibes
✅ Gym & workout

🎵 All tracks are AI-generated original music
📅 {now.strftime('%B %Y')}

#{genre.replace(' ', '')} #{mood}Vibes #BGM #WorkMusic #StudyMusic #ElectronicMusic #NoCopyrightMusic
"""

    tags = [
        genre, mood, "BGM", "background music", "work music", "study music",
        "electronic music", "AI music", "no copyright music", "club music",
        f"{config.TARGET_HOURS} hour mix", "non stop mix", "deep focus",
    ]

    return title, description, tags


def main():
    print("=== BGM YouTube Auto System ===\n")

    print("[1/5] Downloading MP3s from Google Drive...")
    mp3_paths = download_random_mp3s(num=config.NUM_SONGS, dest_dir=config.WORK_DIR)

    print("\n[2/5] Creating looped audio...")
    audio_path = loop_audio(mp3_paths, target_hours=config.TARGET_HOURS,
                            output_path=f"{config.WORK_DIR}/looped.mp3")

    print("\n[3/5] Rendering waveform video...")
    video_path = create_waveform_video(audio_path,
                                       output_path=f"{config.WORK_DIR}/output.mp4")

    title, description, tags = generate_metadata()

    print("\n[4/5] Creating thumbnail...")
    short_title = title[:50]
    thumbnail_path = create_thumbnail(short_title,
                                      output_path=f"{config.WORK_DIR}/thumbnail.jpg")

    print("\n[5/5] Uploading to YouTube...")
    video_id = upload_video(video_path, thumbnail_path, title, description, tags)

    print("\nAdding to playlist...")
    from agents.drive_agent import get_credentials
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    add_to_playlist(youtube, video_id, config.PLAYLIST_ID)

    print("\nCleaning up...")
    cleanup(config.WORK_DIR)

    print(f"\n✅ Done! https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()

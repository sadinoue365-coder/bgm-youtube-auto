"""
Jazz Shorts 自動生成・投稿スクリプト

狼アート + 楽曲の60秒切り抜きで縦型Short動画を作成し、アップロードする。
Shortsは登録者ゼロでも表示される新規リーチの入口。本編への誘導を狙う。

縦1080x1920・60秒・#Shorts タグでYouTubeが自動的にShorts判定する。
"""

import datetime
import random
import ssl
import subprocess
import time

import jazz_config as config
from agents.cleanup_agent import cleanup
from agents.wolf_image_agent import generate_wolf_image

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# jazz_main の認証・DL関数を再利用
from jazz_main import get_credentials, download_random_mp3s

SHORT_SECONDS = 60

# Shorts用フック（コメントを誘発する短い問いかけ）
SHORT_HOOKS = [
    "POV: it's 3AM and the city is finally quiet 🌃",
    "Rainy night + jazz = instant calm 🌧️",
    "Your late-night work companion 🐺",
    "This is what midnight sounds like 🎷",
    "Jazz bar ambience, anywhere you are 🥃",
    "For the night owls still awake 🌙",
]


def create_short_video(image_path, audio_path, output_path="work/short.mp4"):
    """狼画像+音源60秒で縦型(1080x1920)のShort動画を生成する。"""
    # 画像を縦画面いっぱいにcrop、音声はフェードイン/アウト付き60秒
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1"
    )
    af = f"atrim=0:{SHORT_SECONDS},afade=t=in:d=2,afade=t=out:st={SHORT_SECONDS-3}:d=3"
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-vf", vf, "-af", af,
        "-t", str(SHORT_SECONDS),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-r", "30",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Short生成失敗: {result.stderr.decode()[-300:]}")
    print(f"  Short video created: {output_path}")
    return output_path


def generate_short_metadata():
    hook = random.choice(SHORT_HOOKS)
    title = f"{hook} #Shorts"
    description = f"""{hook}

🎷 Full-length jazz mixes (1-3 hours) on our channel — perfect for sleep, study & late-night work.
🐺 New uploads daily at 18:00 JST. Subscribe for the full experience.

#Shorts #jazz #relaxingmusic #lofi #jazzbar #nightjazz #studymusic #sleepmusic
"""
    tags = [
        "jazz", "shorts", "relaxing music", "jazz shorts", "night jazz",
        "study music", "sleep music", "jazz bar", "lofi jazz", "BGM",
    ]
    return title, description, tags


def upload_short(creds, video_path, title, description, tags):
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
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True,
                            chunksize=50 * 1024 * 1024)
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
                print(f"  HTTP {e.resp.status}、{wait}秒後リトライ ({retry}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
        except (ssl.SSLEOFError, ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError) as e:
            retry += 1
            if retry > max_retries:
                raise
            wait = min(2 ** retry, 64)
            print(f"  ネットワークエラー ({type(e).__name__})、{wait}秒後リトライ ({retry}/{max_retries})...")
            time.sleep(wait)

    video_id = response["id"]
    print(f"  Uploaded Short: https://www.youtube.com/shorts/{video_id}")
    return video_id


def main():
    print("=== Jazz Shorts Auto System ===\n")

    print("[1/4] Authenticating...")
    creds = get_credentials()

    print("\n[2/4] Downloading 1 MP3 from Google Drive...")
    mp3_paths = download_random_mp3s(creds, num=1, dest_dir=config.WORK_DIR)
    audio_path = mp3_paths[0]

    print("\n[3/4] Fetching wolf image...")
    image_path, _, img_source = generate_wolf_image(
        creds,
        config.IMAGE_FOLDER_ID,
        output_path=f"{config.WORK_DIR}/wolf_short.jpg",
    )
    if img_source == "pil":
        # 黒背景しか無い場合はShortを出す価値が薄いので中止（本編と違い毎日ではないため）
        print("  画像ソースが黒背景のみ → 今回のShort投稿はスキップ")
        cleanup(config.WORK_DIR)
        return

    print("\n[4/4] Creating & uploading Short...")
    video_path = create_short_video(
        image_path, audio_path, output_path=f"{config.WORK_DIR}/short.mp4"
    )
    title, description, tags = generate_short_metadata()
    upload_short(creds, video_path, title, description, tags)

    print("\nCleaning up...")
    cleanup(config.WORK_DIR)
    print("\n✅ Short done!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        cleanup(config.WORK_DIR)
        print(f"\n❌ Fatal error: {e}")
        raise

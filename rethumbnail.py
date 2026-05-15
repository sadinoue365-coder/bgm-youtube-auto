"""
既存動画のサムネイルを新デザインで一括更新するスクリプト

動画フレーム（テキストなし）を背景として取得し、クリーンなサムネイルを生成します。

使い方:
  # Chillチャンネル
  python3 rethumbnail.py chill ~/Downloads/client_secret_158927624501-xxx.json

  # Jazzチャンネル
  python3 rethumbnail.py jazz ~/Downloads/client_secret_594268582890-xxx.json
"""

import os
import re
import sys
import time
import urllib.request
import ssl

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import chill_config
import jazz_config
from agents.thumbnail_agent import create_thumbnail

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_credentials(client_secret_path):
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True)
    return creds


def get_all_videos(youtube):
    """チャンネルの全動画を取得"""
    ch = youtube.channels().list(part="contentDetails", mine=True).execute()
    uploads_playlist = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    videos = []
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=next_page,
        ).execute()
        for item in resp["items"]:
            videos.append({
                "id": item["snippet"]["resourceId"]["videoId"],
                "title": item["snippet"]["title"],
            })
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return videos


def fetch_pexels_background(scene_keyword, output_path, pexels_api_key):
    """Pexelsからシーンキーワードで背景画像を取得（Chill用）"""
    from agents.image_agent import fetch_pexels_image
    try:
        image_path, _ = fetch_pexels_image(
            pexels_api_key, [scene_keyword],
            output_path=output_path,
        )
        print(f"    Pexels画像取得: '{scene_keyword}'")
        return image_path
    except Exception as e:
        print(f"    Pexels取得失敗: {e}")
        return None


def get_channel_icon_url(youtube):
    """チャンネルアイコンURLを取得（kontextのbase imageとして使用）"""
    try:
        resp = youtube.channels().list(part="snippet", mine=True).execute()
        if resp["items"]:
            thumbnails = resp["items"][0]["snippet"]["thumbnails"]
            for size in ["high", "medium", "default"]:
                if size in thumbnails:
                    return thumbnails[size]["url"]
    except Exception as e:
        print(f"    アイコンURL取得失敗: {e}")
    return None


def generate_kontext_wolf_image(prompt, base_image_url, output_path):
    """Pollinations.ai kontextでチャンネルアイコンを参照して狼画像を生成"""
    import urllib.parse
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    encoded_prompt = urllib.parse.quote(prompt)
    encoded_image = urllib.parse.quote(base_image_url)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?model=kontext&image={encoded_image}&width=1920&height=1080&nologo=true"
    )

    for attempt in range(3):
        try:
            if attempt > 0:
                wait = 15 * attempt
                print(f"    {wait}秒待機してリトライ...")
                time.sleep(wait)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
                data = r.read()
            with open(output_path, "wb") as f:
                f.write(data)
            print(f"    kontext狼画像生成: '{prompt[:40]}'")
            return output_path
        except Exception as e:
            print(f"    kontext生成失敗 (attempt {attempt+1}): {e}")
    return None


def generate_pollinations_image(prompt, output_path):
    """Pollinations.aiで画像を生成（APIキー不要）、429時はリトライ"""
    import urllib.parse
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1080&model=flux&nologo=true"

    for attempt in range(3):
        try:
            if attempt > 0:
                wait = 15 * attempt
                print(f"    {wait}秒待機してリトライ...")
                time.sleep(wait)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
                data = r.read()
            with open(output_path, "wb") as f:
                f.write(data)
            print(f"    AI画像生成: '{prompt[:40]}'")
            return output_path
        except Exception as e:
            print(f"    AI画像生成失敗 (attempt {attempt+1}): {e}")
            if attempt == 2:
                return None
    return None


def create_gradient_background(path, channel):
    """
    チャンネルカラーのグラデーション背景を生成。
    自動フレームが取得できない場合のフォールバック。
    """
    from PIL import Image, ImageDraw
    w, h = 1280, 720
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)

    if channel == "jazz":
        top, bottom = (25, 5, 5), (8, 0, 0)      # 深紅〜漆黒
    else:  # chill
        top, bottom = (5, 20, 35), (0, 35, 55)   # 深海ブルー

    for i in range(h):
        r = int(top[0] + (bottom[0] - top[0]) * i / h)
        g = int(top[1] + (bottom[1] - top[1]) * i / h)
        b = int(top[2] + (bottom[2] - top[2]) * i / h)
        draw.line([(0, i), (w, i)], fill=(r, g, b))

    img.save(path, "JPEG", quality=92)
    print(f"    グラデーション背景を使用")
    return path


def parse_hours_from_title(title):
    """
    タイトルから動画の長さを抽出
    "3 Hours", "1 Hour", "30 Min", "90 Min", "2.5 Hours" → float(hours)
    """
    m = re.search(r'(\d+\.?\d*)\s*(Hours?|Min)', title, re.IGNORECASE)
    if not m:
        return 3.0  # デフォルト
    val = float(m.group(1))
    unit = m.group(2).lower()
    if 'min' in unit:
        return round(val / 60, 1)
    return val


def upload_thumbnail(youtube, video_id, thumbnail_path):
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
    ).execute()


def process_channel(channel, client_secret_path, pexels_api_key=None):
    os.makedirs("work", exist_ok=True)

    if channel == "chill":
        cfg = chill_config
        accent_color = (0, 220, 180)
        style = "minimal"
        print("=== Chill チャンネルのサムネイルを更新 ===\n")
    elif channel == "jazz":
        cfg = jazz_config
        accent_color = (220, 180, 60)
        style = "minimal"
        print("=== Jazz チャンネルのサムネイルを更新 ===\n")
    else:
        print("使い方: python3 rethumbnail.py [chill|jazz] <client_secret.jsonのパス> [pexels_api_key]")
        sys.exit(1)

    creds = get_credentials(client_secret_path)
    youtube = build("youtube", "v3", credentials=creds)

    print("動画一覧を取得中...")
    videos = get_all_videos(youtube)
    print(f"  {len(videos)} 本の動画が見つかりました\n")

    # Jazz用: チャンネルアイコンURLを取得（kontext参照用）
    channel_icon_url = None
    if channel == "jazz":
        channel_icon_url = get_channel_icon_url(youtube)
        if channel_icon_url:
            print(f"  チャンネルアイコン取得: {channel_icon_url[:60]}...")
        else:
            print("  チャンネルアイコン取得失敗 → 通常生成にフォールバック")

    success = 0
    for i, video in enumerate(videos):
        print(f"[{i+1}/{len(videos)}] {video['title'][:60]}")

        try:
            bg_path = "work/bg_image.jpg"

            if channel == "chill" and pexels_api_key:
                # タイトルからシーンキーワードを抽出してPexelsから取得
                parts = [p.strip() for p in video["title"].split("|")]
                scene = parts[1] if len(parts) >= 2 else parts[0]
                bg = fetch_pexels_background(scene, bg_path, pexels_api_key)
            elif channel == "chill":
                # Pexelsキーなし → Pollinations.aiで自然風景を生成
                parts = [p.strip() for p in video["title"].split("|")]
                scene = parts[1] if len(parts) >= 2 else "peaceful nature"
                prompt = f"peaceful {scene} landscape photography cinematic 4k"
                bg = generate_pollinations_image(prompt, bg_path)
            elif channel == "jazz":
                # Google DriveからJazz用の狼画像をランダムに取得
                if pexels_api_key:  # jazz用にはfolder_idをpexels_api_keyとして流用
                    bg = fetch_drive_wolf_image(creds, pexels_api_key, bg_path)
                else:
                    parts = [p.strip() for p in video["title"].split("|")]
                    mood = parts[1] if len(parts) >= 2 else parts[0]
                    mood_str = " ".join(mood.split()[:3]).lower()
                    prompt = (
                        f"anthropomorphic wolf detective fedora hat smoking "
                        f"{mood_str} noir jazz bar dark red crimson atmospheric "
                        f"anime illustration style cinematic moody"
                    )
                    bg = generate_pollinations_image(prompt, bg_path)
            else:
                bg = None

            if bg is None:
                bg = create_gradient_background(bg_path, channel)
            frame_path = bg

            # タイトルから長さを解析
            target_hours = parse_hours_from_title(video["title"])
            print(f"    長さ: {target_hours}h")

            # 新デザインでサムネイル生成
            thumb_path = "work/new_thumb.jpg"
            create_thumbnail(
                video["title"],
                output_path=thumb_path,
                background_path=frame_path,
                channel_name=cfg.CHANNEL_NAME,
                target_hours=target_hours,
                accent_color=accent_color,
                style=style,
            )

            # アップロード
            upload_thumbnail(youtube, video["id"], thumb_path)
            print(f"    ✅ 更新完了")
            success += 1

        except Exception as e:
            print(f"    ❌ エラー: {e}")

        # API制限対策（Pollinations.ai レート制限回避のため少し長めに待機）
        time.sleep(8)

    print(f"\n✅ 完了！ {success}/{len(videos)} 本のサムネイルを更新しました")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python3 rethumbnail.py [chill|jazz] <client_secret.json> [pexels_key_or_drive_folder_id]")
        print()
        print("例:")
        print("  python3 rethumbnail.py chill ~/Downloads/client_secret_158927624501-xxx.json YOUR_PEXELS_KEY")
        print("  python3 rethumbnail.py jazz  ~/Desktop/client_secret_594268582890-xxx.json DRIVE_FOLDER_ID")
        sys.exit(1)
    extra_key = sys.argv[3] if len(sys.argv) >= 4 else None
    process_channel(sys.argv[1].lower(), sys.argv[2], extra_key)

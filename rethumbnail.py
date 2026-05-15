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


def download_video_frame(video_id, path):
    """
    YouTubeの自動生成フレームをダウンロード（1.jpg / 2.jpg / 3.jpg のみ試みる）。
    0.jpg / maxresdefault.jpg はカスタムサムネイルが返ることがあるため使わない。
    取得できなければ None を返す。
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for frame_num in ["1", "2", "3"]:
        try:
            url = f"https://img.youtube.com/vi/{video_id}/{frame_num}.jpg"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                data = r.read()

            # 小さすぎる（プレースホルダー画像）は除外
            if len(data) < 5000:
                continue

            with open(path, "wb") as f:
                f.write(data)
            print(f"    フレーム取得: {frame_num}.jpg ({len(data)//1024}KB)")
            return path

        except Exception:
            continue

    return None  # 取得できなかった場合


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


def process_channel(channel, client_secret_path):
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
        print("使い方: python3 rethumbnail.py [chill|jazz] <client_secret.jsonのパス>")
        sys.exit(1)

    creds = get_credentials(client_secret_path)
    youtube = build("youtube", "v3", credentials=creds)

    print("動画一覧を取得中...")
    videos = get_all_videos(youtube)
    print(f"  {len(videos)} 本の動画が見つかりました\n")

    success = 0
    for i, video in enumerate(videos):
        print(f"[{i+1}/{len(videos)}] {video['title'][:60]}")

        try:
            # 動画フレームを試みる（取得できなければグラデーション背景を使用）
            frame_path = "work/video_frame.jpg"
            bg = download_video_frame(video["id"], frame_path)
            if bg is None:
                bg = create_gradient_background(frame_path, channel)
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

        # API制限対策
        time.sleep(1)

    print(f"\n✅ 完了！ {success}/{len(videos)} 本のサムネイルを更新しました")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python3 rethumbnail.py [chill|jazz] <client_secret.jsonのパス>")
        print()
        print("例:")
        print("  python3 rethumbnail.py chill ~/Downloads/client_secret_158927624501-xxx.json")
        print("  python3 rethumbnail.py jazz  ~/Desktop/client_secret_594268582890-xxx.json")
        sys.exit(1)
    process_channel(sys.argv[1].lower(), sys.argv[2])

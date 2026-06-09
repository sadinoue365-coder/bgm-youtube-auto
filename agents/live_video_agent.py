"""
YouTube Live 24/7 動画連結配信エージェント（固定順ループ）

Google Drive 内の動画ファイルを固定順で連結し、無限ループで
YouTube RTMP へ配信する。

【処理フロー】
  1. Drive から動画を全件ダウンロード（名前順＝固定順）
  2. 全動画を同一規格(1920x1080/30fps/H.264/AAC)に正規化（キャッシュ）
  3. concat プレイリストを生成
  4. FFmpeg concat + stream_loop -1 で無限ループ配信
  5. FFmpeg 終了時は自動再起動（launchd KeepAlive と二重で保護）

【前提】
  YouTube Studio で「永続ストリームキー」を有効化し、
  setup/.live.env に下記を設定すること:
    {CHANNEL}_LIVE_STREAM_KEY       … YouTubeストリームキー
    {CHANNEL}_LIVE_VIDEO_FOLDER_ID  … 動画が入ったDriveフォルダID
    {CHANNEL}_CLIENT_SECRET_JSON    … OAuth(既存と共通)
    {CHANNEL}_REFRESH_TOKEN         … OAuth(既存と共通)
"""

import io
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ── 定数 ────────────────────────────────────────────────────────────────────
RTMP_BASE = "rtmp://a.rtmp.youtube.com/live2"
CACHE_ROOT = Path("work/live_video")
LOG_DIR = Path("logs")

# 出力規格（全動画をこの規格に正規化）
TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
VIDEO_BITRATE = "4500k"
AUDIO_BITRATE = "128k"

# Drive キャッシュを再取得する間隔（新規動画の取り込み）
CACHE_REFRESH_DAYS = 1

VIDEO_MIME_PREFIXES = ("video/",)


# ── 認証 ─────────────────────────────────────────────────────────────────────
def _get_credentials(client_secret_json: str, refresh_token: str) -> Credentials:
    info = json.loads(client_secret_json)
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=info["installed"]["client_id"],
        client_secret=info["installed"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    creds.refresh(Request())
    return creds


# ── Drive からダウンロード ────────────────────────────────────────────────────
def download_videos(creds, folder_id: str, dest_dir: Path) -> list[Path]:
    """Drive フォルダ内の動画を名前順（固定順）で全件DLする。既存はスキップ。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    service = build("drive", "v3", credentials=creds)

    files = []
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType contains 'video/'",
            fields="nextPageToken, files(id, name, mimeType)",
            orderBy="name_natural",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    if not files:
        print(f"  [live-video] Drive に動画が見つかりません (folder={folder_id})")
        return []

    # 名前順で固定化
    files.sort(key=lambda f: f["name"])
    downloaded = []
    for f in files:
        local = dest_dir / f["name"]
        if local.exists() and local.stat().st_size > 0:
            downloaded.append(local)
            continue
        try:
            req = service.files().get_media(fileId=f["id"])
            with io.FileIO(local, "wb") as fh:
                dl = MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _, done = dl.next_chunk()
            print(f"  [live-video] DL: {f['name']}")
            downloaded.append(local)
        except Exception as e:
            print(f"  [live-video] DL失敗 {f['name']}: {e}")

    return downloaded


# ── 正規化 ───────────────────────────────────────────────────────────────────
def normalize_video(src: Path, dst: Path) -> bool:
    """1本の動画を同一規格(1920x1080/30fps/H.264/AAC)へ変換する。"""
    if dst.exists() and dst.stat().st_size > 0:
        return True  # キャッシュ済み

    vf = (
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
        f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={TARGET_FPS}"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        # 連結時に無音区間で映像が止まらないよう、音声無しでも無音を生成
        "-shortest",
        str(dst),
    ]
    print(f"  [live-video] 正規化中: {src.name}")
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"  [live-video] 正規化失敗 {src.name}: {result.stderr.decode()[-300:]}")
        if dst.exists():
            dst.unlink()
        return False
    return True


def normalize_all(video_paths: list[Path], norm_dir: Path) -> list[Path]:
    """全動画を正規化し、成功したファイル（固定順維持）を返す。"""
    norm_dir.mkdir(parents=True, exist_ok=True)
    normalized = []
    for src in video_paths:
        dst = norm_dir / f"{src.stem}_norm.mp4"
        if normalize_video(src, dst):
            normalized.append(dst)
    return normalized


# ── concat プレイリスト ───────────────────────────────────────────────────────
def write_concat_playlist(normalized: list[Path], out_path: Path) -> None:
    lines = [f"file '{p.resolve()}'" for p in normalized]
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ── 配信 ─────────────────────────────────────────────────────────────────────
def stream_forever(channel: str, stream_key: str, playlist_path: Path) -> None:
    """FFmpeg で concat を無限ループ配信。終了時は自動再起動。"""
    rtmp_url = f"{RTMP_BASE}/{stream_key}"
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"live_video_{channel}.log"
    buf = str(int(VIDEO_BITRATE.rstrip("k")) * 2) + "k"

    retry_wait = 5
    while True:
        cmd = [
            "ffmpeg", "-hide_banner",
            "-re", "-stream_loop", "-1",
            "-f", "concat", "-safe", "0", "-i", str(playlist_path.resolve()),
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", VIDEO_BITRATE, "-maxrate", VIDEO_BITRATE, "-bufsize", buf,
            "-pix_fmt", "yuv420p", "-g", str(TARGET_FPS * 2),
            "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "44100",
            "-f", "flv", rtmp_url,
        ]
        start = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[live-video:{channel}] 配信開始 {start}")
        with open(log_path, "a") as fp:
            fp.write(f"\n=== START {start} ===\n")
            result = subprocess.run(cmd, stderr=fp)

        end = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[live-video:{channel}] FFmpeg終了 code={result.returncode} @ {end} → {retry_wait}秒後再起動")
        time.sleep(retry_wait)
        retry_wait = 5 if result.returncode == 0 else min(retry_wait * 2, 60)


# ── エントリポイント ───────────────────────────────────────────────────────────
def run(channel: str) -> None:
    ch = channel.upper()
    stream_key = os.environ.get(f"{ch}_LIVE_STREAM_KEY")
    folder_id = os.environ.get(f"{ch}_LIVE_VIDEO_FOLDER_ID")
    client_secret = os.environ.get(f"{ch}_CLIENT_SECRET_JSON")
    refresh_token = os.environ.get(f"{ch}_REFRESH_TOKEN")

    missing = [k for k, v in {
        f"{ch}_LIVE_STREAM_KEY": stream_key,
        f"{ch}_LIVE_VIDEO_FOLDER_ID": folder_id,
        f"{ch}_CLIENT_SECRET_JSON": client_secret,
        f"{ch}_REFRESH_TOKEN": refresh_token,
    }.items() if not v]
    if missing:
        raise EnvironmentError(f"環境変数が不足しています: {missing}（setup/.live.env を確認）")

    print(f"[live-video:{channel}] === 起動 ===")
    cache = CACHE_ROOT / channel
    raw_dir = cache / "raw"
    norm_dir = cache / "normalized"
    playlist_path = cache / "playlist.txt"

    creds = _get_credentials(client_secret, refresh_token)

    # 1) DL → 2) 正規化 → 3) プレイリスト
    raw = download_videos(creds, folder_id, raw_dir)
    if not raw:
        raise RuntimeError("配信できる動画がありません（Driveフォルダを確認）")
    normalized = normalize_all(raw, norm_dir)
    if not normalized:
        raise RuntimeError("正規化に成功した動画が0本です")
    write_concat_playlist(normalized, playlist_path)
    print(f"[live-video:{channel}] {len(normalized)}本を連結して配信開始します")

    # 4) 無限ループ配信
    stream_forever(channel, stream_key, playlist_path)

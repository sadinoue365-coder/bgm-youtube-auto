"""
YouTube Live 24/7配信エージェント

各チャンネルのBGM音源をGoogle Driveからキャッシュし、
FFmpegでYouTube RTMPへループ配信する。

配信方式:
  Sleep → 黒背景 + 音源ループ
  Jazz  → 静止画(サムネイル) + 音源ループ
  Cafe  → 静止画(サムネイル) + 音源ループ

前提:
  YouTube Studio で「永続ストリーム」を有効にし、
  各チャンネルのストリームキーを setup/.live.env に設定すること。
  ストリームキーは YouTube Studio → ライブ配信 → ストリーム で確認できる。
"""

import json
import os
import random
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ── 定数 ────────────────────────────────────────────────────────────────────
RTMP_BASE = "rtmp://a.rtmp.youtube.com/live2"
CACHE_DIR = Path("work/live_cache")
ASSETS_DIR = Path("assets")
LOG_DIR = Path("logs")

CACHE_MAX_AGE_DAYS = 7
MAX_AUDIO_FILES = 30

CHANNEL_CONFIGS: dict[str, dict] = {
    "jazz": {
        "stream_key_env": "JAZZ_LIVE_STREAM_KEY",
        "client_secret_env": "JAZZ_CLIENT_SECRET_JSON",
        "refresh_token_env": "JAZZ_REFRESH_TOKEN",
        "gdrive_folder_env": "JAZZ_GDRIVE_FOLDER_ID",
        "image_folder_env": "JAZZ_IMAGE_FOLDER_ID",  # 画像ローテーション用
        "video_type": "image",
        "thumbnail": "live_thumbnail_jazz.jpg",
        "video_bitrate": "2000k",
        "rotate_hours": 6,  # 6時間ごとに画像+曲順を入れ替え(数秒の瞬断あり)
    },
    "cafe": {
        "stream_key_env": "CAFE_LIVE_STREAM_KEY",
        "client_secret_env": "CAFE_CLIENT_SECRET_JSON",
        "refresh_token_env": "CAFE_REFRESH_TOKEN",
        "gdrive_folder_env": "CAFE_GDRIVE_FOLDER_ID",
        "image_folder_env": "CAFE_IMAGE_FOLDER_ID",
        "video_type": "image",
        "thumbnail": "live_thumbnail_cafe.jpg",
        # 3本目はCPU節約のため720p/低ビットレート
        "scale": "1280:720",
        "video_bitrate": "1500k",
        "rotate_hours": 6,
    },
    "sleep": {
        "stream_key_env": "SLEEP_LIVE_STREAM_KEY",
        "client_secret_env": "SLEEP_CLIENT_SECRET_JSON",
        "refresh_token_env": "SLEEP_REFRESH_TOKEN",
        "gdrive_folder_env": "SLEEP_GDRIVE_FOLDER_ID",
        "video_type": "black",
        # 黒画面は解像度/fpsを落としても視聴体験が変わらないためCPU優先
        "black_size": "1280x720",
        "black_fps": 10,
        "video_bitrate": "600k",
        "preset": "ultrafast",
    },
}


# ── 認証 ─────────────────────────────────────────────────────────────────────
def _get_credentials(client_secret_json: str, refresh_token: str) -> Credentials:
    client_info = json.loads(client_secret_json)
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_info["installed"]["client_id"],
        client_secret=client_info["installed"]["client_secret"],
        scopes=[
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    creds.refresh(Request())
    return creds


# ── 音源キャッシュ ────────────────────────────────────────────────────────────
def refresh_audio_cache(channel: str, cfg: dict) -> list[Path]:
    """Google Drive から音源をダウンロードしてローカルにキャッシュする。"""
    client_secret = os.environ.get(cfg["client_secret_env"])
    refresh_token = os.environ.get(cfg["refresh_token_env"])
    folder_id = os.environ.get(cfg["gdrive_folder_env"])

    if not all([client_secret, refresh_token, folder_id]):
        print(f"  [live:{channel}] 認証情報が不足しています（.live.env を確認してください）")
        return []

    cache_dir = CACHE_DIR / channel
    cache_dir.mkdir(parents=True, exist_ok=True)

    creds = _get_credentials(client_secret, refresh_token)
    drive = build("drive", "v3", credentials=creds)

    # Drive からオーディオファイル一覧を取得
    query = (
        f"'{folder_id}' in parents and trashed=false "
        f"and (mimeType contains 'audio' or name contains '.mp3' or name contains '.m4a')"
    )
    results = drive.files().list(
        q=query, fields="files(id,name)", pageSize=100
    ).execute()
    files = results.get("files", [])

    if not files:
        print(f"  [live:{channel}] Drive に音源ファイルが見つかりません")
        return []

    # ランダムに MAX_AUDIO_FILES 件選択してダウンロード
    selected = random.sample(files, min(len(files), MAX_AUDIO_FILES))
    downloaded: list[Path] = []

    for f in selected:
        local_path = cache_dir / f["name"]
        if not local_path.exists():
            try:
                data = drive.files().get_media(fileId=f["id"]).execute()
                local_path.write_bytes(data)
                print(f"  [live:{channel}] DL: {f['name']}")
            except Exception as e:
                print(f"  [live:{channel}] DL失敗: {f['name']} — {e}")
                continue
        downloaded.append(local_path)

    return downloaded


def load_audio_cache(channel: str, cfg: dict) -> list[Path]:
    """
    キャッシュ状態を確認し、必要なら更新してから音源ファイルリストを返す。
    7日以上古い or ファイルが1件もなければ Drive から再取得する。
    """
    cache_dir = CACHE_DIR / channel
    state_path = cache_dir / "cache_state.json"

    needs_refresh = True
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            last_updated_str = state.get("last_updated", "2000-01-01T00:00:00+00:00")
            last_updated = datetime.fromisoformat(last_updated_str)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - last_updated).days
            needs_refresh = age_days >= CACHE_MAX_AGE_DAYS
        except Exception:
            needs_refresh = True

    if needs_refresh:
        print(f"[live:{channel}] 音源キャッシュを更新中...")
        audio_files = refresh_audio_cache(channel, cfg)
        if audio_files:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "files": [str(f) for f in audio_files],
            }, indent=2, ensure_ascii=False))
            return audio_files
        print(f"[live:{channel}] 更新失敗。既存キャッシュにフォールバック...")

    # 既存キャッシュから読み込む
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            files = [Path(p) for p in state.get("files", []) if Path(p).exists()]
            if files:
                return files
        except Exception:
            pass

    # state.json がなければディレクトリを直接スキャン
    if cache_dir.exists():
        files = list(cache_dir.glob("*.mp3")) + list(cache_dir.glob("*.m4a"))
        if files:
            return files

    return []


# ── FFmpeg 配信 ───────────────────────────────────────────────────────────────
def _make_concat_playlist(audio_files: list[Path], out_path: Path) -> None:
    """FFmpeg concat demuxer 用プレイリストファイルを作成する。"""
    lines = [f"file '{f.resolve()}'" for f in audio_files]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _rotate_live_image(channel: str, cfg: dict) -> None:
    """
    Drive の画像フォルダからランダムに1枚DLしてライブ背景を差し替える。
    失敗しても既存の画像で続行する（配信は止めない）。
    """
    image_folder_env = cfg.get("image_folder_env")
    if not image_folder_env:
        return
    folder_id = os.environ.get(image_folder_env)
    client_secret = os.environ.get(cfg["client_secret_env"])
    refresh_token = os.environ.get(cfg["refresh_token_env"])
    if not all([folder_id, client_secret, refresh_token]):
        return

    try:
        from googleapiclient.http import MediaIoBaseDownload
        import io

        creds = _get_credentials(client_secret, refresh_token)
        drive = build("drive", "v3", credentials=creds)
        r = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType contains 'image/'",
            fields="files(id,name)",
            pageSize=200,
        ).execute()
        files = r.get("files", [])
        if not files:
            return
        chosen = random.choice(files)
        thumbnail_name = cfg.get("thumbnail", f"live_thumbnail_{channel}.jpg")
        out_path = ASSETS_DIR / thumbnail_name
        ASSETS_DIR.mkdir(exist_ok=True)
        req = drive.files().get_media(fileId=chosen["id"])
        with io.FileIO(out_path, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
        print(f"[live:{channel}] 背景画像を更新: {chosen['name']}")
    except Exception as e:
        print(f"[live:{channel}] 画像更新失敗（既存画像で続行）: {e}")


def _build_video_args(cfg: dict, channel: str) -> list[str]:
    """
    映像ソースの FFmpeg 入力引数を返す。
    戻り値の入力は入力インデックス 1 として使うことを想定。
    """
    if cfg["video_type"] == "black":
        # 黒背景 (Sleep チャンネル向け)
        size = cfg.get("black_size", "1920x1080")
        fps = cfg.get("black_fps", 30)
        return ["-f", "lavfi", "-i", f"color=c=black:s={size}:r={fps}"]

    # 静止画 (Jazz / Cafe)
    thumbnail_name = cfg.get("thumbnail", f"live_thumbnail_{channel}.jpg")
    thumbnail_path = ASSETS_DIR / thumbnail_name
    if thumbnail_path.exists():
        return ["-loop", "1", "-i", str(thumbnail_path.resolve())]

    # フォールバック: 黒背景
    print(f"[live:{channel}] {thumbnail_path} が見つかりません → 黒背景で代替します")
    return ["-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=30"]


def stream_forever(channel: str, cfg: dict, audio_files: list[Path]) -> None:
    """
    FFmpeg を起動して YouTube RTMP へ永続配信する。
    FFmpeg が終了するたびに自動再起動する（無限ループ）。
    """
    stream_key = os.environ.get(cfg["stream_key_env"])
    if not stream_key:
        raise EnvironmentError(
            f"ストリームキーが設定されていません: {cfg['stream_key_env']}\n"
            "setup/.live.env にストリームキーを記載してください。"
        )

    rtmp_url = f"{RTMP_BASE}/{stream_key}"
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"live_{channel}.log"
    playlist_path = CACHE_DIR / channel / "playlist.txt"
    (CACHE_DIR / channel).mkdir(parents=True, exist_ok=True)

    retry_wait = 5  # 初回リトライ待機秒数
    last_cache_refresh = datetime.now(timezone.utc)

    while True:
        # 7日ごとにキャッシュを更新して新曲に入れ替える
        if (datetime.now(timezone.utc) - last_cache_refresh).days >= CACHE_MAX_AGE_DAYS:
            print(f"[live:{channel}] 定期キャッシュ更新...")
            new_files = load_audio_cache(channel, cfg)
            if new_files:
                audio_files = new_files
            last_cache_refresh = datetime.now(timezone.utc)

        # ローテーション: 背景画像をランダム更新 + 曲順シャッフル
        rotate_hours = cfg.get("rotate_hours")
        _rotate_live_image(channel, cfg)
        shuffled = list(audio_files)
        random.shuffle(shuffled)
        _make_concat_playlist(shuffled, playlist_path)

        video_args = _build_video_args(cfg, channel)
        bitrate = cfg.get("video_bitrate", "2000k")
        buf_size = str(int(bitrate.rstrip("k")) * 2) + "k"

        # 映像フィルタ: 縮小(3本目対策) + ゲストブック(チャット壁)描画
        vf_parts = []
        if cfg.get("scale"):
            w, h = cfg["scale"].split(":")
            # アスペクト比が違う画像でも歪まないよう拡大→中央クロップ
            vf_parts.append(
                f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
            )
        wall_path = CACHE_DIR / channel / "chat_wall.txt"
        font_path = ASSETS_DIR / "fonts" / "Oswald-Variable.ttf"
        if cfg["video_type"] == "image" and wall_path.exists() and font_path.exists():
            # reload=1: 壁ファイル更新が配信を止めずに画面へ反映される
            vf_parts.append(
                "drawtext="
                f"textfile={wall_path.resolve()}:reload=1"
                f":fontfile={font_path.resolve()}"
                ":fontsize=26:fontcolor=white@0.92"
                ":x=42:y=h-th-42:line_spacing=12"
                ":box=1:boxcolor=black@0.45:boxborderw=16"
            )

        cmd = [
            "ffmpeg", "-hide_banner",
            # 音声入力 (input 0): concat プレイリストを無限ループ
            "-re", "-stream_loop", "-1",
            "-f", "concat", "-safe", "0", "-i", str(playlist_path.resolve()),
            # 映像入力 (input 1): 黒背景または静止画
            *video_args,
            # マッピング
            "-map", "1:v", "-map", "0:a",
        ]
        if vf_parts:
            cmd += ["-vf", ",".join(vf_parts)]
        cmd += [
            # 映像エンコード
            "-c:v", "libx264", "-preset", cfg.get("preset", "veryfast"),
            "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", buf_size,
            "-g", "60", "-keyint_min", "60",
            # 音声エンコード
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        ]
        if rotate_hours:
            # 指定時間で正常終了させ、次のループで画像+曲順を入れ替える
            cmd += ["-t", str(int(rotate_hours * 3600))]
        cmd += ["-f", "flv", rtmp_url]

        start_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        rotate_note = f" / {rotate_hours}hごとに入替" if rotate_hours else ""
        print(f"[live:{channel}] 配信開始 {start_time}  ({len(shuffled)} 曲{rotate_note})")

        with open(log_path, "a") as log_fp:
            log_fp.write(f"\n=== START {start_time} ===\n")
            result = subprocess.run(cmd, stderr=log_fp)

        end_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(
            f"[live:{channel}] FFmpeg 終了 code={result.returncode} @ {end_time}. "
            f"{retry_wait}秒後に再起動..."
        )

        time.sleep(retry_wait)
        # 成功終了 (code=0) は待機を延ばさない。エラーは指数バックオフ
        if result.returncode != 0:
            retry_wait = min(retry_wait * 2, 60)
        else:
            retry_wait = 5


# ── エントリポイント ───────────────────────────────────────────────────────────
def run(channel: str) -> None:
    cfg = CHANNEL_CONFIGS.get(channel)
    if cfg is None:
        raise ValueError(
            f"不明なチャンネル: '{channel}'\n"
            f"指定可能: {list(CHANNEL_CONFIGS.keys())}"
        )

    print(f"[live:{channel}] === 起動 ===")

    audio_files = load_audio_cache(channel, cfg)
    if not audio_files:
        raise RuntimeError(
            f"[live:{channel}] 音源ファイルが1件もありません。"
            "Drive への接続・フォルダIDを確認してください。"
        )

    print(f"[live:{channel}] 音源 {len(audio_files)} 件 準備完了")
    stream_forever(channel, cfg, audio_files)

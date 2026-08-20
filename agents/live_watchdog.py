"""
ライブ配信ウォッチドッグ（ゾンビ配信検知・自動復旧）

【検知する障害】
  ネットワーク瞬断後、ffmpegは再接続してデータを送り続けているのに
  YouTube側はライブを「終了」扱いにしており、映像が誰にも届かない状態。
  (2026-08-15 Sleepチャンネルで実際に発生)

【動作】
  10分ごとに各チャンネルをチェック:
    - ffmpegが5分以上稼働している
    - かつ YouTube API 上に live 状態のブロードキャストが無い
  → その チャンネルの launchd ジョブを kickstart (ffmpeg再接続で新ライブ生成)

使い方:
  python live_watchdog_main.py
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CHECK_INTERVAL = 600      # チェック間隔(秒)
MIN_FFMPEG_AGE = 300      # ffmpegがこれ以上稼働していて初めて判定対象(起動直後を除外)
CHANNELS = ["jazz", "cafe", "sleep"]


def _get_youtube(channel: str):
    CH = channel.upper()
    cs = os.environ.get(f"{CH}_CLIENT_SECRET_JSON")
    rt = os.environ.get(f"{CH}_REFRESH_TOKEN")
    if not cs or not rt:
        return None
    info = json.loads(cs)
    creds = Credentials(
        token=None,
        refresh_token=rt,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=info["installed"]["client_id"],
        client_secret=info["installed"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def _ffmpeg_age_seconds(channel: str) -> int | None:
    """このチャンネル向けffmpegの稼働秒数を返す。無ければNone。"""
    try:
        out = subprocess.run(
            ["pgrep", "-f", f"live_cache/{channel}/playlist"],
            capture_output=True, text=True,
        ).stdout.strip()
        if not out:
            return None
        pid = out.splitlines()[0]
        etime = subprocess.run(
            ["ps", "-o", "etime=", "-p", pid],
            capture_output=True, text=True,
        ).stdout.strip()
        # etime形式: [[dd-]hh:]mm:ss
        parts = etime.replace("-", ":").split(":")
        parts = [int(p) for p in parts]
        while len(parts) < 4:
            parts.insert(0, 0)
        d, h, m, s = parts
        return d * 86400 + h * 3600 + m * 60 + s
    except Exception:
        return None


def _is_live_on_youtube(channel: str) -> bool | None:
    """YouTube上にlive状態のブロードキャストがあるか。判定不能はNone。"""
    try:
        yt = _get_youtube(channel)
        if yt is None:
            return None
        resp = yt.liveBroadcasts().list(
            part="status", mine=True, maxResults=5
        ).execute()
        return any(
            it.get("status", {}).get("lifeCycleStatus") == "live"
            for it in resp.get("items", [])
        )
    except Exception as e:
        print(f"[watchdog:{channel}] API確認失敗: {str(e)[:100]}")
        return None


def _kickstart(channel: str) -> None:
    uid = os.getuid()
    label = f"com.bgm-youtube.{channel}-live"
    subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{uid}/{label}"],
        capture_output=True,
    )


def run() -> None:
    print(f"[watchdog] === 起動 (間隔{CHECK_INTERVAL}秒) ===")
    while True:
        for ch in CHANNELS:
            age = _ffmpeg_age_seconds(ch)
            if age is None or age < MIN_FFMPEG_AGE:
                continue  # 配信していない or 起動直後(判定保留)

            live = _is_live_on_youtube(ch)
            if live is False:
                ts = datetime.now(timezone.utc).strftime("%m/%d %H:%M UTC")
                print(f"[watchdog:{ch}] ゾンビ配信検知 (ffmpeg稼働{age//60}分/YouTube側live無し) → 再起動 {ts}")
                _kickstart(ch)
            elif live is True:
                pass  # 正常
            # None(判定不能)は何もしない — 誤検知でライブを切らない

        time.sleep(CHECK_INTERVAL)

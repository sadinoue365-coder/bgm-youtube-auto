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
  → 新しいブロードキャストをAPIで作成し、受信中ストリームにbindして復活
    (enableAutoStop=False で作成するため、以後は瞬断でライブが終了しなくなる)
    (2026-08-15の実障害で kickstart では復旧しないことを確認済み —
     ストリーム受信はactiveでも受け皿が自動生成されないため)

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

# ゾンビ復旧時に作成するブロードキャストのタイトル・説明
BROADCAST_META = {
    "jazz": {
        "title": "Jazz Radio 24/7 🐺 Relaxing Noir Jazz for Sleep, Study & Late Night Work",
        "description": "24/7 live jazz radio — relaxing jazz music for sleeping, studying, "
                       "working and stress relief. Smoky midnight bar ambience with smooth noir jazz.\n\n"
                       "🎵 AI-generated original music — no copyright issues",
    },
    "cafe": {
        "title": "Coffee Shop Music 24/7 ☕ Relaxing Jazz & Bossa Nova for Morning, Work & Study",
        "description": "24/7 coffee shop music — relaxing cafe jazz and bossa nova for morning "
                       "coffee, work, study and good mood.\n\n"
                       "🎵 AI-generated original music — no copyright issues",
    },
    "sleep": {
        "title": "Black Screen Sleep Music 24/7 🌙 Deep Sleep, Relaxation & Insomnia Relief",
        "description": "24/7 black screen sleep music — relaxing sleep sounds for deep sleep, "
                       "insomnia relief and stress relief.\n\n"
                       "🌙 No visuals. No distractions. Just sleep.\n\n"
                       "🎵 AI-generated original music — no copyright issues",
    },
}


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


def _create_and_bind_broadcast(channel: str) -> str | None:
    """
    受信中ストリームに新しいブロードキャストを作成・bindして復活させる。
    enableAutoStop=False のため、以後は瞬断でライブが勝手に終了しない。
    成功したら新しい video ID を返す。
    """
    try:
        yt = _get_youtube(channel)
        if yt is None:
            return None

        # 受信中(active)ストリームのIDを取得
        streams = yt.liveStreams().list(
            part="id,status", mine=True, maxResults=5
        ).execute()
        stream_id = None
        for it in streams.get("items", []):
            if it.get("status", {}).get("streamStatus") == "active":
                stream_id = it["id"]
                break
        if not stream_id:
            print(f"[watchdog:{channel}] activeなストリームが無いため復旧見送り(ffmpeg側の問題の可能性)")
            return None

        meta = BROADCAST_META.get(channel, {})
        body = {
            "snippet": {
                "title": meta.get("title", f"{channel} 24/7 live"),
                "description": meta.get("description", ""),
                "scheduledStartTime": datetime.now(timezone.utc).isoformat(),
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": False,
                "enableDvr": True,
                "latencyPreference": "normal",
            },
        }
        bc = yt.liveBroadcasts().insert(
            part="snippet,status,contentDetails", body=body
        ).execute()
        bc_id = bc["id"]
        yt.liveBroadcasts().bind(id=bc_id, part="id,status", streamId=stream_id).execute()
        return bc_id
    except Exception as e:
        print(f"[watchdog:{channel}] ブロードキャスト作成失敗: {str(e)[:150]}")
        return None


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
                print(f"[watchdog:{ch}] ゾンビ配信検知 (ffmpeg稼働{age//60}分/YouTube側live無し) {ts}")
                bc_id = _create_and_bind_broadcast(ch)
                if bc_id:
                    print(f"[watchdog:{ch}] ✅ 復旧: https://www.youtube.com/watch?v={bc_id}")
                    try:
                        from agents.alert_agent import send_alert
                        send_alert(
                            f"{ch}ライブをゾンビ状態から自動復旧しました",
                            f"YouTube側でライブが終了扱いになっていたため、\n"
                            f"新しいブロードキャストを自動作成して復旧しました。\n\n"
                            f"新URL: https://www.youtube.com/watch?v={bc_id}\n"
                            f"(概要欄の再生リスト等のリンクは新URLに引き継がれません)",
                        )
                    except Exception:
                        pass
            elif live is True:
                pass  # 正常
            # None(判定不能)は何もしない — 誤検知でライブを切らない

        time.sleep(CHECK_INTERVAL)

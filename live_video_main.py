"""
YouTube Live 24/7 動画連結配信 起動スクリプト

使い方:
  python live_video_main.py jazz

事前準備:
  1. YouTube Studio → ライブ配信 → ストリーム で永続ストリームキーを有効化
  2. setup/.live.env に下記を設定:
       JAZZ_LIVE_STREAM_KEY=...
       JAZZ_LIVE_VIDEO_FOLDER_ID=...   ← 連結したい動画のDriveフォルダID
       JAZZ_CLIENT_SECRET_JSON=...      （既存と共通）
       JAZZ_REFRESH_TOKEN=...           （既存と共通）
"""

import os
import sys
from pathlib import Path

# setup/.live.env を自動ロード
_env_file = Path(__file__).parent / "setup" / ".live.env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            if _k.strip() not in os.environ:
                os.environ[_k.strip()] = _v.strip().strip("'\"")

from agents.live_video_agent import run  # noqa: E402


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python live_video_main.py [channel]")
        sys.exit(1)
    channel = sys.argv[1].lower()
    try:
        run(channel)
    except KeyboardInterrupt:
        print(f"\n[live-video:{channel}] 停止しました")
    except Exception as e:
        print(f"[live-video:{channel}] エラー: {e}", file=sys.stderr)
        sys.exit(1)

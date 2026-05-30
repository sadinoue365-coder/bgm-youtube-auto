"""
YouTube Live 24/7配信 起動スクリプト

使い方:
  python live_main.py jazz
  python live_main.py cafe
  python live_main.py sleep

事前準備:
  1. YouTube Studio → ライブ配信 → ストリーム で「永続ストリーム」を有効化
  2. 各チャンネルのストリームキーをコピー
  3. setup/.live.env にストリームキーと認証情報を記載
  4. source setup/.live.env を実行（または launchd 経由で起動）
"""

import os
import sys
from pathlib import Path

# setup/.live.env を自動ロード（存在する場合）
_env_file = Path(__file__).parent / "setup" / ".live.env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            # すでに環境変数に設定されていれば上書きしない
            if _key.strip() not in os.environ:
                os.environ[_key.strip()] = _val.strip().strip("'\"")

from agents.live_agent import run  # noqa: E402


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python live_main.py [jazz|cafe|sleep]")
        sys.exit(1)

    channel = sys.argv[1].lower()
    try:
        run(channel)
    except KeyboardInterrupt:
        print(f"\n[live:{channel}] 停止しました")
    except Exception as e:
        print(f"[live:{channel}] エラー: {e}", file=sys.stderr)
        sys.exit(1)

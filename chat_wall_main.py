"""
ライブチャット「ゲストブック」起動スクリプト

使い方:
  python chat_wall_main.py jazz
"""

import os
import sys
from pathlib import Path

_env_file = Path(__file__).parent / "setup" / ".live.env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            if _k.strip() not in os.environ:
                os.environ[_k.strip()] = _v.strip().strip("'\"")

from agents.chat_wall_agent import run  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python chat_wall_main.py [jazz|cafe|sleep]")
        sys.exit(1)
    channel = sys.argv[1].lower()
    try:
        run(channel)
    except KeyboardInterrupt:
        print(f"\n[chat-wall:{channel}] 停止しました")

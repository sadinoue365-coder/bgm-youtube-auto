"""ライブ配信ウォッチドッグ起動スクリプト"""
import os
from pathlib import Path

_env_file = Path(__file__).parent / "setup" / ".live.env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            if _k.strip() not in os.environ:
                os.environ[_k.strip()] = _v.strip().strip("'\"")

from agents.live_watchdog import run  # noqa: E402

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n[watchdog] 停止しました")

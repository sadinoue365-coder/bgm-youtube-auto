"""
ライブチャット「ゲストブック」エージェント

24/7ライブのチャットを定期取得し、直近メッセージを
配信画面に焼き込むためのテキストファイルを更新し続ける。
(live_agent が ffmpeg drawtext reload=1 でこのファイルを毎フレーム参照)

過疎ライブでも過去の訪問者の痕跡が画面に残るため、
新規視聴者の書き込みハードルを下げる（社会的証明）。

使い方:
  python chat_wall_main.py jazz
"""

import json
import os
import re
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CACHE_DIR = Path("work/live_cache")
MAX_MESSAGES = 5          # 画面に表示する件数
MAX_LEN = 46              # 1メッセージの最大文字数
MAX_AUTHOR = 14           # 表示する名前の最大文字数
POLL_SECONDS = 60         # チャット取得間隔
CHAT_ID_RETRY_SECONDS = 300  # ライブが見つからない時の再試行間隔

CTA_LINE = ">> Say hi in chat - your message joins the wall"

# 表示しないメッセージ（URL・スパム対策の最低限フィルタ）
_BLOCK_PATTERNS = [
    re.compile(r"https?://", re.I),
    re.compile(r"\b(sub4sub|subscribe to me|check my channel)\b", re.I),
]

# ── ウェルカムボット設定 ───────────────────────────────────────────────────────
# 初コメントの人へチャンネル名義で自動挨拶する（承認済みチャンネルのみ）
WELCOME_ENABLED = {"jazz"}

WELCOME_TEMPLATES = {
    "jazz": [
        "Welcome to the lounge, {name} - the wolf tips his hat 🎩",
        "{name} just walked into the bar. What are you drinking tonight? 🥃",
        "Good to see a new face, {name}. Grab a seat by the window 🌧️",
        "The wolf nods at {name}. Make yourself at home 🐺",
    ],
    "sleep": [
        "Rest well, {name} 🌙",
        "Welcome, {name}. Lights off, volume low - sweet dreams 🌙",
    ],
    "cafe": [
        "Welcome in, {name}! Coffee's fresh ☕",
        "Morning, {name} - grab your favorite seat ☕",
    ],
}


def _get_credentials(channel: str) -> Credentials:
    CH = channel.upper()
    info = json.loads(os.environ[f"{CH}_CLIENT_SECRET_JSON"])
    creds = Credentials(
        token=None,
        refresh_token=os.environ[f"{CH}_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=info["installed"]["client_id"],
        client_secret=info["installed"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    creds.refresh(Request())
    return creds


def _sanitize(text: str, max_len: int) -> str:
    """drawtext で安全に表示できるASCII文字だけ残す。"""
    text = "".join(c for c in text if 0x20 <= ord(c) <= 0x7E)
    text = text.replace("%", "pct").replace("\\", "").replace("'", "").replace('"', "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _is_blocked(text: str) -> bool:
    return any(p.search(text) for p in _BLOCK_PATTERNS)


def _find_active_chat_id(youtube) -> str | None:
    """稼働中ライブの liveChatId を取得する。"""
    try:
        resp = youtube.liveBroadcasts().list(
            part="snippet,status", mine=True, maxResults=10
        ).execute()
        for item in resp.get("items", []):
            if item.get("status", {}).get("lifeCycleStatus") == "live":
                chat_id = item["snippet"].get("liveChatId")
                if chat_id:
                    return chat_id
    except Exception as e:
        print(f"[chat-wall] broadcast取得失敗: {e}")
    return None


def _append_chat_log(log_path: Path, entry: dict) -> None:
    """全チャットをJSONL形式で永続保存（後から遡れる自前ログ）。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_known_authors(path: Path) -> set[str]:
    if path.exists():
        try:
            return set(json.loads(path.read_text()))
        except Exception:
            pass
    return set()


def _save_known_authors(path: Path, authors: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(authors)))


def _post_welcome(youtube, chat_id: str, channel: str, display_name: str) -> None:
    """初コメントの人へチャンネル名義でウェルカム返信を投稿する。"""
    import random as _random
    templates = WELCOME_TEMPLATES.get(channel)
    if not templates:
        return
    text = _random.choice(templates).format(name=display_name)[:190]
    try:
        youtube.liveChatMessages().insert(
            part="snippet",
            body={
                "snippet": {
                    "liveChatId": chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {"messageText": text},
                }
            },
        ).execute()
        print(f"[chat-wall:{channel}] ウェルカム送信: {text}")
    except Exception as e:
        print(f"[chat-wall:{channel}] ウェルカム送信失敗: {str(e)[:120]}")


def _write_wall(wall_path: Path, messages: list[tuple[str, str]]) -> None:
    """アトミックに壁ファイルを更新（ffmpegが読みかけの中途半端な状態を見ないように）。"""
    lines = ["=== GUEST BOOK ==="]
    for author, text in messages[-MAX_MESSAGES:]:
        lines.append(f"{author}: {text}")
    if not messages:
        lines.append("(no messages yet - be the first!)")
    lines.append(CTA_LINE)
    tmp = wall_path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="ascii", errors="ignore")
    tmp.replace(wall_path)


def run(channel: str) -> None:
    print(f"[chat-wall:{channel}] === 起動 ===")
    wall_path = CACHE_DIR / channel / "chat_wall.txt"
    wall_path.parent.mkdir(parents=True, exist_ok=True)

    messages: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    _write_wall(wall_path, messages)  # 初期表示(CTAのみ)

    # 永続データ: 全チャットログ + 既知ユーザー(ウェルカム済み)
    data_dir = Path("data")
    chat_log_path = data_dir / f"chat_log_{channel}.jsonl"
    known_path = data_dir / f"chat_known_{channel}.json"
    known_authors = _load_known_authors(known_path)
    from datetime import datetime, timezone

    creds = _get_credentials(channel)
    youtube = build("youtube", "v3", credentials=creds)

    chat_id = None
    page_token = None

    while True:
        try:
            if chat_id is None:
                chat_id = _find_active_chat_id(youtube)
                if chat_id is None:
                    print(f"[chat-wall:{channel}] 稼働中ライブなし。{CHAT_ID_RETRY_SECONDS}秒後に再確認")
                    time.sleep(CHAT_ID_RETRY_SECONDS)
                    continue
                print(f"[chat-wall:{channel}] チャット接続: {chat_id[:24]}...")
                page_token = None

            kwargs = dict(liveChatId=chat_id, part="snippet,authorDetails", maxResults=200)
            if page_token:
                kwargs["pageToken"] = page_token
            resp = youtube.liveChatMessages().list(**kwargs).execute()
            page_token = resp.get("nextPageToken")

            new_count = 0
            for item in resp.get("items", []):
                mid = item["id"]
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                snippet = item.get("snippet", {})
                if snippet.get("type") != "textMessageEvent":
                    continue
                raw = snippet.get("displayMessage", "")
                author_info = item.get("authorDetails", {})
                author = _sanitize(author_info.get("displayName", "guest"), MAX_AUTHOR)
                author_id = author_info.get("channelId", "")
                is_owner = author_info.get("isChatOwner", False)

                # 全チャットを永続ログに保存（遡り分析用）
                _append_chat_log(chat_log_path, {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "author": author_info.get("displayName", ""),
                    "author_id": author_id,
                    "text": raw,
                    "is_owner": is_owner,
                })

                text = _sanitize(raw, MAX_LEN)
                if not text or _is_blocked(raw):
                    continue
                messages.append((author, text))
                new_count += 1

                # 初コメントの人へウェルカム返信（自分自身は除く）
                if (
                    channel in WELCOME_ENABLED
                    and author_id
                    and author_id not in known_authors
                    and not is_owner
                ):
                    _post_welcome(youtube, chat_id, channel, author or "friend")
                if author_id and author_id not in known_authors:
                    known_authors.add(author_id)
                    _save_known_authors(known_path, known_authors)

            if new_count:
                messages = messages[-50:]  # メモリ節約
                _write_wall(wall_path, messages)
                print(f"[chat-wall:{channel}] {new_count}件追加 (計{len(messages)}件)")

            # seen_ids の肥大防止
            if len(seen_ids) > 5000:
                seen_ids = set(list(seen_ids)[-2000:])

            time.sleep(POLL_SECONDS)

        except Exception as e:
            msg = str(e)
            if "liveChatEnded" in msg or "notFound" in msg or "forbidden" in msg.lower():
                print(f"[chat-wall:{channel}] チャット終了/変更を検知 → 再取得します")
                chat_id = None
                page_token = None
                time.sleep(30)
            else:
                print(f"[chat-wall:{channel}] エラー: {msg[:150]} → 60秒後リトライ")
                time.sleep(60)

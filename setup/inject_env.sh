#!/bin/bash
# ============================================================
# setup/.live.env の値を launchd plist に自動注入するスクリプト
# ============================================================
# 使い方:
#   bash setup/inject_env.sh
#
# .live.env の KEY=VALUE を読み込み、対応する plist の
# PLACEHOLDER_REPLACE_ME を実際の値に置換します。
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.live.env"
PLIST_DIR="$SCRIPT_DIR/launchd"

if [ ! -f "$ENV_FILE" ]; then
  echo "エラー: $ENV_FILE が見つかりません"
  echo "  cp setup/.live.env.example setup/.live.env して値を記載してください"
  exit 1
fi

# 各チャンネルの plist に対応する環境変数を注入する
inject_plist() {
  local CHANNEL=$1
  shift
  local PLIST="$PLIST_DIR/com.bgm-youtube.${CHANNEL}-live.plist"

  if [ ! -f "$PLIST" ]; then
    echo "スキップ: $PLIST が見つかりません"
    return
  fi

  # 一時ファイルに作業コピー
  local TMP=$(mktemp)
  cp "$PLIST" "$TMP"

  # 各環境変数キーについて置換
  for KEY in "$@"; do
    VALUE=$(grep "^${KEY}=" "$ENV_FILE" | head -1 | cut -d= -f2-)
    if [ -z "$VALUE" ]; then
      echo "  ⚠ ${KEY} が .live.env に見つかりません"
      continue
    fi

    # XML 特殊文字をエスケープ (& < > " ')
    ESC_VALUE=$(printf '%s' "$VALUE" | sed \
      -e 's/&/\&amp;/g' \
      -e 's/</\&lt;/g' \
      -e 's/>/\&gt;/g')

    # plist 内の <key>KEY</key>\n<string>PLACEHOLDER... を置換
    # Python を使って安全に置換
    python3 - "$TMP" "$KEY" "$VALUE" <<'PYEOF'
import sys, re

plist_path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
content = open(plist_path).read()

# <key>KEY</key> の直後の <string>...</string> を置換
pattern = r'(<key>' + re.escape(key) + r'</key>\s*<string>)[^<]*(</string>)'
replacement = r'\g<1>' + value.replace('\\', '\\\\') + r'\g<2>'
new_content = re.sub(pattern, replacement, content)

open(plist_path, 'w').write(new_content)
PYEOF
  done

  # 変更を元のファイルに反映
  cp "$TMP" "$PLIST"
  rm -f "$TMP"
  echo "  ✓ $CHANNEL plist 更新完了"
}

echo "plist に環境変数を注入中..."

inject_plist jazz \
  JAZZ_LIVE_STREAM_KEY \
  JAZZ_CLIENT_SECRET_JSON \
  JAZZ_REFRESH_TOKEN \
  JAZZ_GDRIVE_FOLDER_ID

inject_plist cafe \
  CAFE_LIVE_STREAM_KEY \
  CAFE_CLIENT_SECRET_JSON \
  CAFE_REFRESH_TOKEN \
  CAFE_GDRIVE_FOLDER_ID

inject_plist sleep \
  SLEEP_LIVE_STREAM_KEY \
  SLEEP_CLIENT_SECRET_JSON \
  SLEEP_REFRESH_TOKEN \
  SLEEP_GDRIVE_FOLDER_ID

echo ""
echo "完了！次のコマンドで launchd にインストールしてください:"
echo "  bash setup/install_live.sh all"

#!/bin/bash
# ============================================================
# YouTube Live 24/7配信 launchd インストールスクリプト
# ============================================================
# 使い方:
#   bash setup/install_live.sh [jazz|cafe|sleep|all]
#
# 前提条件:
#   1. setup/.live.env を作成して認証情報を記載済みであること
#   2. plist の EnvironmentVariables を .live.env の値で更新済みであること
#      → setup/inject_env.sh を使うと自動で埋め込めます
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="$SCRIPT_DIR/launchd"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

# .live.env のチェック
if [ ! -f "$SCRIPT_DIR/.live.env" ]; then
  echo -e "${RED}エラー:${NC} setup/.live.env が見つかりません。"
  echo "  cp setup/.live.env.example setup/.live.env"
  echo "  → .live.env に認証情報・ストリームキーを記載してください。"
  exit 1
fi

# logs ディレクトリ作成
mkdir -p "$PROJECT_DIR/logs"

install_channel() {
  local CHANNEL=$1
  local PLIST_NAME="com.bgm-youtube.${CHANNEL}-live.plist"
  local SRC="$PLIST_DIR/$PLIST_NAME"
  local DEST="$LAUNCH_AGENTS/$PLIST_NAME"

  if [ ! -f "$SRC" ]; then
    echo -e "${YELLOW}スキップ:${NC} $SRC が見つかりません"
    return
  fi

  # すでに登録済みならアンロード
  if launchctl list | grep -q "com.bgm-youtube.${CHANNEL}-live" 2>/dev/null; then
    launchctl unload "$DEST" 2>/dev/null || true
    echo "  既存エージェントをアンロードしました: $CHANNEL"
  fi

  # plist をコピー
  cp "$SRC" "$DEST"

  # ロード
  launchctl load "$DEST"
  echo -e "  ${GREEN}✓${NC} $CHANNEL: launchd エージェント登録完了"
}

TARGET="${1:-all}"

if [ "$TARGET" = "all" ]; then
  install_channel jazz
  install_channel cafe
  install_channel sleep
else
  install_channel "$TARGET"
fi

echo ""
echo -e "${GREEN}インストール完了！${NC}"
echo ""
echo "確認コマンド:"
echo "  launchctl list | grep bgm-youtube"
echo ""
echo "停止コマンド:"
echo "  launchctl unload ~/Library/LaunchAgents/com.bgm-youtube.jazz-live.plist"
echo ""
echo "ログ確認:"
echo "  tail -f $PROJECT_DIR/logs/launchd_jazz_live.log"

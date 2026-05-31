"""
投稿スケジュール自動最適化スクリプト

各チャンネルの upload_timing.json を分析し、
パフォーマンスが向上する投稿曜日が見つかれば .github/workflows/*.yml を更新する。

使い方:
  python update_schedule.py           # ドライラン (変更なし、推奨内容を表示)
  python update_schedule.py --apply   # 実際に workflow YAML を書き換え

GitHub Actions から自動実行する場合:
  .github/workflows/optimize_schedule.yml を参照
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from agents.timing_agent import (
    DAY_NAMES_JA,
    _cron_to_py_day,
    analyze_best_timing,
    recommend_new_days,
    update_timing_metrics,
)


# ── チャンネル設定 ────────────────────────────────────────────────────────────

CHANNEL_CONFIGS = {
    "jazz": {
        "workflow": ".github/workflows/jazz_upload.yml",
        "client_secret_env": "JAZZ_CLIENT_SECRET_JSON",
        "refresh_token_env": "JAZZ_REFRESH_TOKEN",
        "optimize": False,  # 毎日投稿のため曜日最適化対象外
    },
    "cafe": {
        "workflow": ".github/workflows/cafe_upload.yml",
        "client_secret_env": "CAFE_CLIENT_SECRET_JSON",
        "refresh_token_env": "CAFE_REFRESH_TOKEN",
        "optimize": True,
    },
    "sleep": {
        "workflow": ".github/workflows/sleep_upload.yml",
        "client_secret_env": "SLEEP_CLIENT_SECRET_JSON",
        "refresh_token_env": "SLEEP_REFRESH_TOKEN",
        "optimize": True,
    },
    "chill": {
        "workflow": ".github/workflows/chill_upload.yml",
        "client_secret_env": "CHILL_CLIENT_SECRET_JSON",
        "refresh_token_env": "CHILL_REFRESH_TOKEN",
        "optimize": True,
    },
}


# ── ユーティリティ ────────────────────────────────────────────────────────────

def _get_credentials(client_secret_json: str, refresh_token: str) -> Credentials:
    client_info = json.loads(client_secret_json)
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_info["installed"]["client_id"],
        client_secret=client_info["installed"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    creds.refresh(Request())
    return creds


def _parse_cron_days(cron: str) -> list[int]:
    """
    'cron: 0 9 * * 2,6' のような文字列から曜日リストを抽出する。
    'cron: 0 9 * * *'  のような毎日の場合は [0,1,2,3,4,5,6] を返す。
    """
    # cron 式の5フィールドを取得
    match = re.search(r"cron:\s*['\"]?([^'\"]+)['\"]?", cron)
    if not match:
        return []
    fields = match.group(1).strip().split()
    if len(fields) < 5:
        return []
    day_field = fields[4]
    if day_field == "*":
        return list(range(7))
    return [int(d) for d in day_field.split(",")]


def _build_cron(current_cron_line: str, new_days: list[int]) -> str:
    """既存 cron 行の曜日フィールドだけを new_days に置き換えた行を返す。"""
    day_str = ",".join(str(d) for d in sorted(new_days))
    # cron 式内の day-of-week フィールド (5番目) を置き換える
    def replace_days(m):
        fields = m.group(1).split()
        fields[4] = day_str
        new_expr = " ".join(fields)
        quote = m.group(0)[len("cron: ")]  # ' or "
        if quote in ("'", '"'):
            return f"cron: {quote}{new_expr}{quote}"
        return f"cron: {new_expr}"
    return re.sub(r"cron: ['\"]?[^'\"]+['\"]?", replace_days, current_cron_line)


def _update_workflow_cron(
    workflow_path: Path,
    new_days: list[int],
    dry_run: bool = True,
) -> tuple[bool, str, str]:
    """
    workflow YAML の cron 式の曜日を更新する。

    Returns:
        (changed: bool, old_cron: str, new_cron: str)
    """
    content = workflow_path.read_text(encoding="utf-8")

    # cron 行を抽出
    cron_match = re.search(r"- cron: ['\"]([^'\"]+)['\"]", content)
    if not cron_match:
        return False, "", ""

    old_expr = cron_match.group(1)
    fields = old_expr.strip().split()
    if len(fields) < 5:
        return False, old_expr, ""

    day_str = ",".join(str(d) for d in sorted(new_days))
    if fields[4] == day_str:
        return False, old_expr, old_expr  # 変更なし

    fields[4] = day_str
    new_expr = " ".join(fields)

    if not dry_run:
        new_content = content.replace(
            f"- cron: '{old_expr}'",
            f"- cron: '{new_expr}'",
        )
        workflow_path.write_text(new_content, encoding="utf-8")

    return True, old_expr, new_expr


# ── メイン処理 ────────────────────────────────────────────────────────────────

def run(apply: bool = False) -> None:
    print(f"{'=' * 60}")
    print(f"  投稿スケジュール最適化  {'[DRY RUN]' if not apply else '[APPLY]'}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 60}\n")

    any_updated = False

    for channel, cfg in CHANNEL_CONFIGS.items():
        print(f"── {channel.upper()} ──")
        workflow_path = Path(cfg["workflow"])

        # 視聴数データを更新
        client_secret = os.environ.get(cfg["client_secret_env"])
        refresh_token = os.environ.get(cfg["refresh_token_env"])
        if client_secret and refresh_token:
            try:
                creds = _get_credentials(client_secret, refresh_token)
                youtube = build("youtube", "v3", credentials=creds)
                n = update_timing_metrics(youtube, channel)
                if n:
                    print(f"  視聴数を {n} 件更新しました")
            except Exception as e:
                print(f"  視聴数取得エラー: {e}")

        # 分析
        analysis = analyze_best_timing(channel)
        print(f"  計測済みサンプル: {analysis['total_samples']} 件")

        if not cfg["optimize"]:
            print(f"  ※ 毎日投稿のため曜日最適化対象外\n")
            continue

        if not workflow_path.exists():
            print(f"  ワークフローが見つかりません: {workflow_path}\n")
            continue

        # 現在のスケジュールを取得
        content = workflow_path.read_text(encoding="utf-8")
        current_days = _parse_cron_days(content)
        if not current_days:
            print(f"  cron 式を解析できませんでした\n")
            continue

        current_days_ja = "・".join(DAY_NAMES_JA[_cron_to_py_day(d)] for d in sorted(current_days))
        print(f"  現在のスケジュール: {current_days_ja}曜日")

        # 推奨
        new_days = recommend_new_days(channel, current_days, n_days=len(current_days))

        if new_days is None:
            if analysis["confident"]:
                print(f"  分析結果: {analysis['recommendation']}")
                print(f"  → 現状のスケジュールが最適（改善幅 <15%、変更なし）")
            else:
                print(f"  → {analysis['recommendation']}")
            print()
            continue

        new_days_ja = "・".join(
            DAY_NAMES_JA[_cron_to_py_day(d)] for d in sorted(new_days)
        )
        print(f"  推奨スケジュール: {new_days_ja}曜日")
        print(f"  分析: {analysis['recommendation']}")

        # 更新
        changed, old_expr, new_expr = _update_workflow_cron(
            workflow_path, new_days, dry_run=not apply
        )
        if changed:
            status = "✅ 適用" if apply else "🔍 変更予定（--apply で適用）"
            print(f"  cron: '{old_expr}' → '{new_expr}'  {status}")
            if apply:
                any_updated = True
        print()

    print("=" * 60)
    if apply and any_updated:
        print("✅ ワークフローを更新しました。git commit/push してください。")
    elif not apply:
        print("ドライランが完了しました。変更を適用するには --apply を付けて実行してください。")
    else:
        print("スケジュールの変更はありません。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="投稿スケジュール自動最適化")
    parser.add_argument(
        "--apply", action="store_true", help="実際に workflow YAML を書き換える"
    )
    args = parser.parse_args()
    run(apply=args.apply)

"""
障害アラートエージェント

自動運用中に「ジョブは成功扱いだが品質が劣化している」ソフト障害を
検知した際、即座にメール通知する。

例: Jazzの画像がAI生成もDrive取得も失敗し、真っ暗なPIL背景に
    フォールバックした場合（ジョブはexit 0で終わるため通常の
    GitHub Actions失敗通知では検知できない）。

必要な環境変数（weekly_report と共通のGmail App Password）:
  REPORT_GMAIL_ADDRESS       … 送信元Gmailアドレス
  REPORT_GMAIL_APP_PASSWORD  … Gmailアプリパスワード
  REPORT_TO_EMAIL            … 通知先アドレス

これらが未設定の場合は標準出力に警告を出すだけで静かに終了する
（アラート未設定でも本処理は止めない）。
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate


def send_alert(subject: str, body: str) -> bool:
    """
    アラートメールを送信する。成功すれば True。
    SMTP情報が無ければ False（警告のみ）。
    """
    gmail = os.environ.get("REPORT_GMAIL_ADDRESS")
    app_pw = os.environ.get("REPORT_GMAIL_APP_PASSWORD")
    to_addr = os.environ.get("REPORT_TO_EMAIL")

    full_subject = f"⚠️ [BGM監視] {subject}"

    if not all([gmail, app_pw, to_addr]):
        print(f"  [alert] SMTP未設定のためメール送信スキップ: {full_subject}")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = full_subject
    msg["From"] = f"BGM Monitor <{gmail}>"
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(gmail, app_pw)
            server.sendmail(gmail, [to_addr], msg.as_string())
        print(f"  [alert] アラートメール送信: {full_subject}")
        return True
    except Exception as e:
        print(f"  [alert] メール送信失敗: {e}")
        return False

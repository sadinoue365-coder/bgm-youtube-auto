"""
このスクリプトをローカルで1回だけ実行してリフレッシュトークンを取得する
取得したトークンをGitHub Secretsの GOOGLE_REFRESH_TOKEN に登録する
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main():
    if len(sys.argv) < 2:
        print("使い方: python setup/get_token.py client_secret.jsonのパス")
        sys.exit(1)

    client_secret_file = sys.argv[1]

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n" + "=" * 60)
    print("✅ 認証成功！以下をGitHub Secretsに登録してください")
    print("=" * 60)
    print(f"\nSecret名: GOOGLE_REFRESH_TOKEN")
    print(f"値: {creds.refresh_token}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

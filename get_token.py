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
        print("使い方: python3 get_token.py <client_secret.jsonのパス>")
        print()
        print("例:")
        print("  python3 get_token.py ~/Downloads/client_secret_158927624501-xxx.json")
        sys.exit(1)

    client_secret_path = sys.argv[1]

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True)

    print("\n✅ 認証成功！")
    print("\n--- REFRESH TOKEN (GitHubに登録) ---")
    print(creds.refresh_token)
    print("-------------------------------------\n")

    with open(client_secret_path) as f:
        client_info = json.load(f)
    print("--- CLIENT SECRET JSON (GitHubに登録) ---")
    print(json.dumps(client_info))
    print("-----------------------------------------\n")

if __name__ == "__main__":
    main()

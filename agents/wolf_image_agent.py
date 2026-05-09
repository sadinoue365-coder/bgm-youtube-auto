import io
import os
import random
import time
import urllib.parse
import urllib.request

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# Jazz wolf用シーンバリエーション
SCENES = [
    "sitting at a dark mahogany bar counter with a whiskey glass",
    "playing a saxophone on a dimly lit stage",
    "leaning against a brick wall in a rainy alleyway",
    "shuffling playing cards at a poker table",
    "looking out a rain-streaked window at city lights",
    "standing in a doorway with backlight silhouette",
    "reading a newspaper under a lamp",
    "surrounded by jazz band musicians",
    "walking down a foggy street at night",
    "sitting alone in a jazz club booth",
    "adjusting his fedora in a mirror reflection",
    "smoking a cigarette under a street lamp",
]

BASE_PROMPT = (
    "Anthropomorphic wolf character, hardboiled noir detective style, "
    "wearing a black fedora hat and dark trench coat, "
    "strong masculine features, anime illustration style, "
    "deep crimson red and black color palette, "
    "1940s noir jazz atmosphere, dramatic moody lighting, "
    "high contrast, cinematic composition, flat 2D illustration, "
    "no text, "
)


def _get_random_image_id(creds, folder_id):
    """Drive フォルダから画像ファイルをランダムに1件選んでIDを返す"""
    service = build("drive", "v3", credentials=creds)
    results = service.files().list(
        q=(
            f"'{folder_id}' in parents and trashed=false "
            "and (mimeType='image/jpeg' or mimeType='image/png')"
        ),
        fields="files(id, name)",
        pageSize=100,
    ).execute()
    files = results.get("files", [])
    if not files:
        raise Exception("Google Drive の画像フォルダに画像が見つかりません")
    chosen = random.choice(files)
    print(f"  Base image selected: {chosen['name']}")
    return chosen["id"], chosen["name"]


def _pollinations_img2img(file_id, scene, output_path, retries=3):
    """
    Pollinations.ai の image= パラメータを使って img2img 生成。
    Drive の公開URLを参照画像として渡す。
    フォルダは「リンクを知っている全員が閲覧可」に設定が必要。
    """
    # Google Drive 公開ダウンロードURL
    base_image_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    encoded_image_url = urllib.parse.quote(base_image_url, safe="")

    full_prompt = BASE_PROMPT + scene
    encoded_prompt = urllib.parse.quote(full_prompt)
    seed = random.randint(1, 99999)

    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=1920&height=1080&seed={seed}&model=flux&nologo=true"
        f"&image={encoded_image_url}&strength=0.65"
    )

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BGM-Bot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=180) as response:
                with open(output_path, "wb") as f:
                    f.write(response.read())
            return True
        except Exception as e:
            print(f"  Pollinations attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(10)
    return False


def _download_from_drive(creds, file_id, output_path):
    """フォールバック：参照画像をそのままDriveからダウンロードして使う"""
    service = build("drive", "v3", credentials=creds)
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(output_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    print("  Fallback: using original Drive image directly")


def generate_wolf_image(creds, folder_id, output_path="work/wolf_bg.jpg"):
    """
    Drive の画像フォルダからランダムに1枚選び、
    Pollinations.ai img2img で新しいシーンの画像を生成する。
    生成に失敗した場合はDrive画像をそのまま使用。
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    file_id, file_name = _get_random_image_id(creds, folder_id)
    scene = random.choice(SCENES)
    print(f"  Scene: {scene}")

    success = _pollinations_img2img(file_id, scene, output_path)

    if not success:
        print("  img2img failed. Using original Drive image as fallback.")
        _download_from_drive(creds, file_id, output_path)
        scene = os.path.splitext(file_name)[0]

    return output_path, scene

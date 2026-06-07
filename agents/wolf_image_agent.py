import io
import math
import os
import random
import ssl
import time
import urllib.parse
import urllib.request

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

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
    "pouring whiskey at a dimly lit bar",
    "gazing at rain-soaked city streets from a fire escape",
    "playing piano in an empty jazz club at 3am",
    "lighting a cigarette in a shadowy doorway",
    "silhouette against a neon-lit window",
    "sitting across a chess board in a smoky lounge",
    "walking under a streetlamp in heavy rain",
    "leaning on a jukebox in a late-night diner",
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


def _generate_flux_image(scene, output_path, retries=4):
    """Pollinations.ai Flux モデルでシーン別狼画像を生成"""
    full_prompt = BASE_PROMPT + scene
    encoded_prompt = urllib.parse.quote(full_prompt)
    seed = random.randint(1, 999999)

    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=1920&height=1080&seed={seed}&model=flux&nologo=true"
    )

    # GitHub Actions環境ではデフォルトSSLを優先、失敗時はCERT_NONE
    ssl_contexts = [None, _SSL_CTX]

    for attempt in range(retries):
        try:
            if attempt > 0:
                wait = 20 * attempt
                print(f"  {wait}秒待機してリトライ...")
                time.sleep(wait)
            ctx = ssl_contexts[min(attempt, len(ssl_contexts) - 1)]
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BGM-Bot/1.0)"},
            )
            kwargs = {"timeout": 180}
            if ctx:
                kwargs["context"] = ctx
            with urllib.request.urlopen(req, **kwargs) as response:
                content_type = response.headers.get("Content-Type", "")
                data = response.read()

            # 画像かどうか検証（最低30KB、Content-Typeが画像）
            if len(data) < 30000:
                print(f"  Flux attempt {attempt+1}: レスポンスが小さすぎる ({len(data)} bytes) → リトライ")
                continue
            if "image" not in content_type and not data[:4] in (b'\xff\xd8\xff\xe0', b'\x89PNG'):
                print(f"  Flux attempt {attempt+1}: 画像ではないレスポンス → リトライ")
                continue

            with open(output_path, "wb") as f:
                f.write(data)
            print(f"  Flux生成成功: '{scene[:50]}' ({len(data)//1024}KB)")
            return True
        except Exception as e:
            print(f"  Flux attempt {attempt+1} failed: {e}")
    return False


def _download_from_drive(creds, folder_id, output_path) -> bool:
    """フォールバック：DriveフォルダからランダムにDL。成功すれば True を返す。"""
    try:
        service = build("drive", "v3", credentials=creds)
        # mimeType contains 'image/' で全画像形式を受け入れる
        # (jpeg/png だけでなく heic / webp / gif 等も拾う)
        results = service.files().list(
            q=(
                f"'{folder_id}' in parents and trashed=false "
                "and mimeType contains 'image/'"
            ),
            fields="files(id, name, mimeType)",
            pageSize=100,
        ).execute()
        all_files = results.get("files", [])

        # mimeType内訳をログ出力（どの形式が入っているか可視化）
        mime_summary = {}
        for f in all_files:
            mt = f.get("mimeType", "?")
            mime_summary[mt] = mime_summary.get(mt, 0) + 1

        # パイプライン(FFmpeg/PIL)が確実に扱える形式のみ採用
        SAFE_MIMES = {"image/jpeg", "image/png", "image/webp"}
        files = [
            f for f in all_files
            if f.get("mimeType") in SAFE_MIMES
            and "スクリーンショット" not in f["name"]
            and "screenshot" not in f["name"].lower()
        ]
        print(f"  Drive: 全{len(all_files)}件  採用可能{len(files)}件  内訳={mime_summary}")
        if not files and all_files:
            print("  ⚠ 画像は存在するが対応形式(jpeg/png/webp)が0件。HEIC等は要変換")
        if not files:
            print("  Drive: 使用可能な画像なし → PILフォールバックへ")
            return False

        chosen = random.choice(files)
        print(f"  Fallback: Drive画像を使用 ({chosen['name']})")
        request = service.files().get_media(fileId=chosen["id"])
        with io.FileIO(output_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return True
    except Exception as e:
        print(f"  Drive取得失敗: {e} → PILフォールバックへ")
        return False


def _generate_pil_background(output_path) -> None:
    """最終フォールバック：PILでノワール調の暗背景を生成する。"""
    from PIL import Image, ImageDraw, ImageFilter

    W, H = 1920, 1080
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # 深い紺〜黒のグラデーション（縦方向）
    for y in range(H):
        t = y / H
        r = int(8 + t * 12)
        g = int(5 + t * 8)
        b = int(18 + t * 22)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # 中央に薄いビネット（周辺を暗く）
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    cx, cy = W // 2, H // 2
    for i in range(min(cx, cy), 0, -1):
        alpha = int(180 * (1 - i / min(cx, cy)) ** 2)
        vd.ellipse([cx - i, cy - i, cx + i, cy + i], fill=alpha)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=80))
    img_rgba = img.convert("RGBA")
    img_rgba.paste((0, 0, 0, 255), mask=vignette)
    img = img_rgba.convert("RGB")

    img.save(output_path, "JPEG", quality=90)
    print("  PIL暗背景を生成しました（最終フォールバック）")


def generate_wolf_image(creds, folder_id, output_path="work/wolf_bg.jpg"):
    """
    狼画像を3段階フォールバックで取得する。
      1st: Pollinations.ai Flux でAI生成（4回リトライ）
      2nd: Drive フォルダからランダムDL
      3rd: PIL でノワール調暗背景を生成（絶対に失敗しない）
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    scene = random.choice(SCENES)
    print(f"  Scene: {scene}")

    # 1st: Flux
    if _generate_flux_image(scene, output_path):
        return output_path, scene

    # 2nd: Drive
    print("  Flux生成失敗。Driveフォールバックを試みます...")
    if _download_from_drive(creds, folder_id, output_path):
        return output_path, "jazz noir wolf"

    # 3rd: PIL（絶対フォールバック）
    print("  Drive取得も失敗。PIL生成にフォールバックします...")
    _generate_pil_background(output_path)
    return output_path, "jazz noir wolf"

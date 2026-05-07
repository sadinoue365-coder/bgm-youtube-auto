import math
import os

from PIL import Image, ImageDraw, ImageFont, ImageEnhance

import config


def create_thumbnail(title, output_path="work/thumbnail.jpg", background_path=None):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    w, h = 1280, 720

    # 背景画像があればそれを使う、なければ黒背景
    if background_path and os.path.exists(background_path):
        img = Image.open(background_path).convert("RGB")
        img = img.resize((w, h), Image.LANCZOS)
        img = ImageEnhance.Brightness(img).enhance(0.5)
    else:
        img = Image.new("RGB", (w, h), color=(8, 8, 16))

    draw = ImageDraw.Draw(img)

    # 下部に半透明グラデーション風の暗いオーバーレイ
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for i in range(h // 2, h):
        alpha = int(180 * (i - h // 2) / (h // 2))
        overlay_draw.line([(0, i), (w, i)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # フォント
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    font_large = None
    font_small = None
    for fp in font_paths:
        if os.path.exists(fp):
            font_large = ImageFont.truetype(fp, 52)
            font_small = ImageFont.truetype(fp, 28)
            break
    if font_large is None:
        font_large = ImageFont.load_default()
        font_small = font_large

    # タイトル
    bbox = draw.textbbox((0, 0), title, font=font_large)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, int(h * 0.62)), title, font=font_large, fill=(255, 255, 255))

    # サブタイトル
    sub = f"{config.CHANNEL_NAME}  •  {config.TARGET_HOURS}H Non-Stop Mix"
    bbox2 = draw.textbbox((0, 0), sub, font=font_small)
    sw = bbox2[2] - bbox2[0]
    draw.text(((w - sw) // 2, int(h * 0.80)), sub, font=font_small, fill=(200, 200, 200))

    img.save(output_path, "JPEG", quality=90)
    print(f"  Thumbnail created: {output_path}")
    return output_path

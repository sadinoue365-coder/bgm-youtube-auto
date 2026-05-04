import math
import os

from PIL import Image, ImageDraw, ImageFont

import config


def create_thumbnail(title, output_path="work/thumbnail.jpg"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    w, h = 1280, 720
    img = Image.new("RGB", (w, h), color=(8, 8, 16))
    draw = ImageDraw.Draw(img)

    # 波形風デザイン
    for i in range(0, w, 3):
        bar_h = int(h * 0.35 * abs(math.sin(i * 0.015) * math.cos(i * 0.007)))
        ratio = i / w
        r = int(0 * (1 - ratio) + 255 * ratio)
        g = int(255 * (1 - ratio) + 0 * ratio)
        b = int(170 * (1 - ratio) + 187 * ratio)
        cy = h // 2
        draw.line([(i, cy - bar_h), (i, cy + bar_h)], fill=(r, g, b), width=2)

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
    draw.text(((w - tw) // 2, int(h * 0.58)), title, font=font_large, fill=(255, 255, 255))

    # サブタイトル
    sub = f"{config.CHANNEL_NAME}  •  {config.TARGET_HOURS}H Non-Stop Mix"
    bbox2 = draw.textbbox((0, 0), sub, font=font_small)
    sw = bbox2[2] - bbox2[0]
    draw.text(((w - sw) // 2, int(h * 0.76)), sub, font=font_small, fill=(160, 160, 160))

    img.save(output_path, "JPEG", quality=90)
    print(f"  Thumbnail created: {output_path}")
    return output_path

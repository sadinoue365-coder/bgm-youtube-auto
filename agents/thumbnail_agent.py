import os

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter


def _draw_text_with_outline(draw, pos, text, font, fill, outline_color, outline_width=3):
    """テキストを縁取りつきで描画する"""
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=fill)


def create_thumbnail(title, output_path="work/thumbnail.jpg", background_path=None,
                     channel_name="BGM Channel", target_hours=3, accent_color=(255, 255, 255)):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    w, h = 1280, 720

    # 背景画像
    if background_path and os.path.exists(background_path):
        img = Image.open(background_path).convert("RGB")
        img = img.resize((w, h), Image.LANCZOS)
        # 明度を上げる（暗くしすぎない）
        img = ImageEnhance.Brightness(img).enhance(0.7)
        # 彩度を少し上げてビビッドに
        img = ImageEnhance.Color(img).enhance(1.3)
    else:
        img = Image.new("RGB", (w, h), color=(8, 8, 24))

    # 左右にグラデーションのビネット（中央を明るく保つ）
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vignette)
    for i in range(60):
        alpha = int(160 * (i / 60) ** 2)
        vd.rectangle([i, i, w - i, h - i], outline=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), vignette).convert("RGB")

    # 下部グラデーションオーバーレイ（テキスト読みやすくする）
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(h // 3 * 2, h):
        alpha = int(200 * (i - h // 3 * 2) / (h // 3))
        od.line([(0, i), (w, i)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    # フォント（サイズを大きく）
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    font_title = None
    font_sub = None
    font_badge = None
    for fp in font_paths:
        if os.path.exists(fp):
            font_title = ImageFont.truetype(fp, 80)
            font_sub = ImageFont.truetype(fp, 34)
            font_badge = ImageFont.truetype(fp, 30)
            break
    if font_title is None:
        font_title = ImageFont.load_default()
        font_sub = font_title
        font_badge = font_title

    # 時間バッジ（左上）
    badge_text = f"{target_hours}H BGM"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    bw = badge_bbox[2] - badge_bbox[0] + 32
    bh = badge_bbox[3] - badge_bbox[1] + 16
    draw.rounded_rectangle([30, 30, 30 + bw, 30 + bh], radius=8, fill=accent_color)
    draw.text((30 + 16, 30 + 8), badge_text, font=font_badge, fill=(0, 0, 0))

    # メインタイトル（中央下寄り、2行対応）
    words = title.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font_title)
        if bbox[2] - bbox[0] > w - 80 and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    # 最大2行
    lines = lines[:2]
    line_height = 90
    total_text_h = len(lines) * line_height
    start_y = int(h * 0.52) - total_text_h // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_title)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        y = start_y + i * line_height
        _draw_text_with_outline(draw, (x, y), line, font_title,
                                fill=(255, 255, 255), outline_color=(0, 0, 0), outline_width=4)

    # サブタイトル
    sub = f"{channel_name}  •  Relaxing Music"
    bbox2 = draw.textbbox((0, 0), sub, font=font_sub)
    sw = bbox2[2] - bbox2[0]
    _draw_text_with_outline(draw, ((w - sw) // 2, int(h * 0.83)), sub, font_sub,
                            fill=accent_color, outline_color=(0, 0, 0), outline_width=3)

    img.save(output_path, "JPEG", quality=92)
    print(f"  Thumbnail created: {output_path}")
    return output_path

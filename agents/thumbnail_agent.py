import os
import re

from PIL import Image, ImageDraw, ImageFont, ImageEnhance


def _load_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def _load_anton(size):
    """Anton フォント（sleep用 極太ディスプレイ体）"""
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [
        os.path.join(_base, "assets/fonts/Anton-Regular.ttf"),
        "/usr/share/fonts/truetype/Anton-Regular.ttf",
    ]
    for fp in paths:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return _load_font(size)  # フォールバック


def _load_oswald(size):
    """Oswald フォント（sleep用 サブテキスト）"""
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [
        os.path.join(_base, "assets/fonts/Oswald-Variable.ttf"),
        "/usr/share/fonts/truetype/Oswald-Variable.ttf",
    ]
    for fp in paths:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return _load_font(size)


def _draw_text_centered(draw, y, text, font, fill, shadow=True):
    """テキストを水平中央揃えで描画（シャドウつき）"""
    w = 1280
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (w - tw) // 2
    if shadow:
        # ソフトシャドウ（黒を薄く複数回）
        for ox, oy in [(2, 2), (3, 3), (4, 4)]:
            draw.text((x + ox, y + oy), text, font=font, fill=(0, 0, 0, 120))
    draw.text((x, y), text, font=font, fill=fill)


def create_thumbnail(title, output_path="work/thumbnail.jpg", background_path=None,
                     channel_name="BGM Channel", target_hours=3, accent_color=(255, 255, 255),
                     style="standard"):
    """
    style="standard" : バッジ・サブタイトルあり
    style="minimal"  : テキスト最小限・画像主役（Cafe/Chill/Jazz用）
    style="sleep"    : 純黒背景・極太白テキスト（Drift Into Sleep用）
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    w, h = 1280, 720

    if style == "sleep":
        # 純黒背景（画像不要）
        img = Image.new("RGB", (w, h), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        _render_sleep(draw, title, target_hours, channel_name)
    else:
        # 背景画像
        if background_path and os.path.exists(background_path):
            img = Image.open(background_path).convert("RGB")
            img = img.resize((w, h), Image.LANCZOS)
            if style == "minimal":
                img = ImageEnhance.Brightness(img).enhance(0.75)
                img = ImageEnhance.Color(img).enhance(1.2)
            else:
                img = ImageEnhance.Brightness(img).enhance(0.7)
                img = ImageEnhance.Color(img).enhance(1.3)
        else:
            img = Image.new("RGB", (w, h), color=(8, 8, 24))

        # ビネット
        vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        vd = ImageDraw.Draw(vignette)
        strength = 100 if style == "minimal" else 160
        for i in range(60):
            alpha = int(strength * (i / 60) ** 2)
            vd.rectangle([i, i, w - i, h - i], outline=(0, 0, 0, alpha))
        img = Image.alpha_composite(img.convert("RGBA"), vignette).convert("RGB")

        # 下部グラデーション
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        grad_start = h // 2 if style == "minimal" else h // 3 * 2
        max_alpha = 160 if style == "minimal" else 200
        for i in range(grad_start, h):
            alpha = int(max_alpha * (i - grad_start) / (h - grad_start))
            od.line([(0, i), (w, i)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        draw = ImageDraw.Draw(img, "RGBA")

        if style == "minimal":
            _render_minimal(draw, title, target_hours, accent_color)
        else:
            _render_standard(draw, title, target_hours, accent_color, channel_name)

    img.save(output_path, "JPEG", quality=95)
    print(f"  Thumbnail created: {output_path}")
    return output_path


def _extract_core_text(title):
    """
    タイトルからサムネイル用コアテキストを抽出。
    - "Jazz BGM | 3AM Jazz Bar for Reading & Whiskey | 3H" → "3AM Jazz Bar"
    - "Calming Chill Music | Ocean Waves | 3H Relaxing BGM" → "Ocean Waves"
    - "Coffee Shop Music | Serene Cafe Bossa Nova | 3 Hours BGM" → "Serene Cafe Bossa Nova"
    - "Velvet Midnight Jazz for Creative Writing | 3H BGM" → "Velvet Midnight Jazz"
    """
    parts = [p.strip() for p in title.split("|")]

    # 2番目のセグメントを候補に
    if len(parts) >= 2:
        candidate = parts[1]
        # 時間表記・BGMだけのセグメントは除外
        if re.match(r'^\d+\.?\d*\s*(H\b|Hours?|Min|BGM)', candidate, re.IGNORECASE):
            candidate = parts[0]
    else:
        candidate = parts[0]

    # 最大3単語に制限
    words = candidate.split()
    if len(words) > 3:
        candidate = " ".join(words[:3])

    return candidate


def _render_minimal(draw, title, target_hours, accent_color):
    """
    ミニマルデザイン（全チャンネル共通）：
    - コアワード（大・中央）
    - 時間表記（小）をその下
    """
    main_text = _extract_core_text(title)

    font_main = _load_font(88)
    font_hours = _load_font(36)

    # メインテキストが幅に収まるか確認、収まらなければ2行に
    bbox = draw.textbbox((0, 0), main_text, font=font_main)
    if bbox[2] - bbox[0] > 1180:
        words = main_text.split()
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = [main_text]

    line_h = 100
    total_h = len(lines) * line_h
    start_y = int(720 * 0.58) - total_h // 2

    for i, line in enumerate(lines):
        _draw_text_centered(draw, start_y + i * line_h, line, font_main,
                            fill=(255, 255, 255), shadow=True)

    # 時間表記（細く・小さく）
    if target_hours == 0.5:
        hour_text = "30 Min"
    elif target_hours == 1.0:
        hour_text = "1 Hour"
    elif target_hours == 1.5:
        hour_text = "90 Min"
    elif target_hours % 1 == 0:
        hour_text = f"{int(target_hours)} Hours"
    else:
        hour_text = f"{target_hours} Hours"
    _draw_text_centered(draw, int(720 * 0.82), hour_text, font_hours,
                        fill=(*accent_color, 210), shadow=False)


def _render_sleep(draw, title, target_hours, channel_name):
    """
    Sleep デザイン（Drift Into Sleep Music用）:
    - 純黒背景
    - チャンネル名（上部・小・グレー）
    - キーワード（中央・極太・白・Anton フォント）
    - BLACK SCREEN X HOURS（下部・白）
    """
    w, h = 1280, 720

    font_channel = _load_oswald(28)
    font_main    = _load_anton(148)
    font_sub     = _load_anton(56)

    # ── チャンネル名（上部中央）──────────────────────────────────
    ch_text = channel_name.upper()
    _draw_text_centered(draw, 48, ch_text, font_channel,
                        fill=(160, 160, 160), shadow=False)

    # ── メインキーワード（中央）──────────────────────────────────
    # ⬛ などの絵文字・パイプ区切りを除去してキーワードを取得
    keyword = _extract_core_text(title).upper()

    # 幅チェック → 長い場合は2行
    bbox = draw.textbbox((0, 0), keyword, font=font_main)
    if bbox[2] - bbox[0] > 1160:
        words = keyword.split()
        mid = max(1, len(words) // 2)
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = [keyword]

    line_h = 158
    total_h = len(lines) * line_h
    start_y = h // 2 - total_h // 2 - 20

    for i, line in enumerate(lines):
        _draw_text_centered(draw, start_y + i * line_h, line, font_main,
                            fill=(255, 255, 255), shadow=False)

    # ── 下部テキスト（BLACK SCREEN X HOURS）────────────────────
    if target_hours == 1.0:
        dur_text = "1 HOUR"
    elif target_hours % 1 == 0:
        dur_text = f"{int(target_hours)} HOURS"
    else:
        dur_text = f"{target_hours} HOURS"

    bottom_text = f"BLACK SCREEN  •  {dur_text}"
    _draw_text_centered(draw, h - 110, bottom_text, font_sub,
                        fill=(210, 210, 210), shadow=False)


def _render_standard(draw, title, target_hours, accent_color, channel_name):
    """
    スタンダードデザイン：バッジ・タイトル・サブタイトルあり（Chill/Jazz用）
    """
    font_title = _load_font(80)
    font_sub = _load_font(34)
    font_badge = _load_font(30)

    # 時間バッジ（左上）
    badge_text = f"{target_hours}H BGM"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    bw = badge_bbox[2] - badge_bbox[0] + 32
    bh = badge_bbox[3] - badge_bbox[1] + 16
    draw.rounded_rectangle([30, 30, 30 + bw, 30 + bh], radius=8, fill=accent_color)
    draw.text((30 + 16, 30 + 8), badge_text, font=font_badge, fill=(0, 0, 0))

    # タイトル（2行まで）
    words = title.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font_title)
        if bbox[2] - bbox[0] > 1200 and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    lines = lines[:2]

    line_height = 90
    total_text_h = len(lines) * line_height
    start_y = int(720 * 0.52) - total_text_h // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_title)
        tw = bbox[2] - bbox[0]
        x = (1280 - tw) // 2
        y = start_y + i * line_height
        # 縁取り
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, font=font_title, fill=(0, 0, 0))
        draw.text((x, y), line, font=font_title, fill=(255, 255, 255))

    # サブタイトル
    sub = f"{channel_name}  •  Relaxing Music"
    bbox2 = draw.textbbox((0, 0), sub, font=font_sub)
    sw = bbox2[2] - bbox2[0]
    sx = (1280 - sw) // 2
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if dx != 0 or dy != 0:
                draw.text((sx + dx, int(720 * 0.83) + dy), sub, font=font_sub, fill=(0, 0, 0))
    draw.text((sx, int(720 * 0.83)), sub, font=font_sub, fill=accent_color)

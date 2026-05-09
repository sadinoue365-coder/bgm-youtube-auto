import os
import random
import urllib.request
import urllib.parse
import json
import time


def generate_wolf_image(api_key, base_prompt, scenes, output_path="work/wolf_bg.jpg"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    scene = random.choice(scenes)
    full_prompt = base_prompt + scene

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-preview-image-generation:generateContent"

    payload = json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{url}?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())

    # 画像データを取得
    import base64
    parts = data["candidates"][0]["content"]["parts"]
    for part in parts:
        if "inlineData" in part:
            img_data = base64.b64decode(part["inlineData"]["data"])
            with open(output_path, "wb") as f:
                f.write(img_data)
            print(f"  Wolf image generated: {scene} → {output_path}")
            return output_path, scene

    raise Exception("画像生成に失敗しました")

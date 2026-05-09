import os
import random
import urllib.request
import urllib.parse


def generate_wolf_image(api_key, base_prompt, scenes, output_path="work/wolf_bg.jpg"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    scene = random.choice(scenes)
    full_prompt = base_prompt + scene
    seed = random.randint(1, 99999)

    encoded_prompt = urllib.parse.quote(full_prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=1920&height=1080&seed={seed}&model=flux&nologo=true"
    )

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; BGM-Bot/1.0)"},
    )

    with urllib.request.urlopen(req, timeout=120) as response:
        with open(output_path, "wb") as f:
            f.write(response.read())

    print(f"  Wolf image generated: {scene} → {output_path}")
    return output_path, scene

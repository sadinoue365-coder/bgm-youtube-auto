import os
import random
import urllib.request

import urllib.parse


def fetch_pexels_image(api_key, queries, output_path="work/background.jpg"):
    query = random.choice(queries)
    encoded_query = urllib.parse.quote(query)
    url = f"https://api.pexels.com/v1/search?query={encoded_query}&per_page=20&orientation=landscape"

    req = urllib.request.Request(url, headers={"Authorization": api_key})
    with urllib.request.urlopen(req) as response:
        import json
        data = json.loads(response.read())

    photos = data.get("photos", [])
    if not photos:
        raise Exception(f"Pexelsで画像が見つかりませんでした: {query}")

    photo = random.choice(photos)
    image_url = photo["src"]["landscape"]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    urllib.request.urlretrieve(image_url, output_path)

    print(f"  Image fetched: '{query}' → {output_path}")
    return output_path, query

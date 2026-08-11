import os

GDRIVE_FOLDER_ID = os.environ.get("JAZZ_GDRIVE_FOLDER_ID", "")
IMAGE_FOLDER_ID = os.environ.get("JAZZ_IMAGE_FOLDER_ID", "")
REFRESH_TOKEN = os.environ.get("JAZZ_REFRESH_TOKEN", "")
CLIENT_SECRET_JSON = os.environ.get("JAZZ_CLIENT_SECRET_JSON", "")

CHANNEL_NAME = "Red Wolf's Lounge"
PUBLISH_HOUR_JST = 18  # 毎日18:00 JSTに定時公開
NUM_SONGS = 10
TARGET_HOURS = 3

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30

WORK_DIR = "work"
PLAYLIST_ID = "PLyUduwWDOrpyAAaC-X8cBNdGDa670aDLx"

WOLF_SCENES = [
    "sitting at a dark mahogany bar counter with a whiskey glass",
    "playing a saxophone on a dimly lit stage",
    "leaning against a brick wall in a rainy alleyway",
    "shuffling playing cards at a poker table",
    "looking out a rain-streaked window at city lights",
    "smoking a cigarette in a leather armchair",
    "adjusting his fedora in a mirror reflection",
    "standing in a doorway with backlight silhouette",
    "reading a newspaper under a lamp",
    "surrounded by jazz band musicians",
    "walking down a foggy street at night",
    "sitting alone in a jazz club booth",
]

WOLF_BASE_PROMPT = (
    "Anthropomorphic wolf character, hardboiled noir detective style, "
    "wearing a black fedora hat and dark trench coat, "
    "strong masculine features, anime illustration style, "
    "deep crimson red and black color palette, "
    "1940s noir jazz atmosphere, dramatic moody lighting, "
    "high contrast, cinematic composition, flat 2D illustration, "
    "no text, "
)

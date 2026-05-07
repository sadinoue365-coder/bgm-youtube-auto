import os

GDRIVE_FOLDER_ID = os.environ.get("CHILL_GDRIVE_FOLDER_ID", "")
REFRESH_TOKEN = os.environ.get("CHILL_REFRESH_TOKEN", "")
CLIENT_SECRET_JSON = os.environ.get("CHILL_CLIENT_SECRET_JSON", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

CHANNEL_NAME = "Chill Relax BGM"
NUM_SONGS = 10
TARGET_HOURS = 3

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30

WORK_DIR = "work"

PEXELS_QUERIES = [
    "beach sunset",
    "ocean waves",
    "tropical paradise",
    "mountain lake",
    "forest morning",
    "calm sea",
    "golden hour beach",
    "peaceful nature",
    "sunset sky",
    "misty forest",
]

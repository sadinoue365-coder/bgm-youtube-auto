import os

GDRIVE_FOLDER_ID = os.environ.get("SLEEP_GDRIVE_FOLDER_ID", "")
REFRESH_TOKEN = os.environ.get("SLEEP_REFRESH_TOKEN", "")
CLIENT_SECRET_JSON = os.environ.get("SLEEP_CLIENT_SECRET_JSON", "")

CHANNEL_NAME = "Drift Into Sleep Music"
NUM_SONGS = 20  # 130曲からランダムに20曲選んでループ
WORK_DIR = "work"

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30

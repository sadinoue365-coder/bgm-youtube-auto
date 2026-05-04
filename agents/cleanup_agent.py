import glob
import os


def cleanup(work_dir="work"):
    for pattern in ["*.mp3", "*.mp4", "*.jpg", "*.txt"]:
        for f in glob.glob(os.path.join(work_dir, pattern)):
            os.remove(f)
            print(f"  Deleted: {f}")

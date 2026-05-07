import os
import subprocess


def create_static_video(image_path, audio_path, output_path="work/output.mp4"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        output_path
    ], check=True)

    print(f"  Static video created: {output_path}")
    return output_path

import os
import subprocess

import config


def create_waveform_video(audio_path, output_path="work/output.mp4"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    w = config.VIDEO_WIDTH
    h = config.VIDEO_HEIGHT
    fps = config.VIDEO_FPS
    half_h = h // 2

    filter_complex = (
        f"color=c=0x080810:s={w}x{h}:r={fps}[bg];"
        f"[0:a]showwaves=s={w}x{half_h}:mode=cline:rate={fps}"
        f":colors=0x00FFAA|0xFF00BB[waves];"
        f"[bg][waves]overlay=(W-w)/2:(H-h)/2[v]"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ], check=True)

    print(f"  Video created: {output_path}")
    return output_path

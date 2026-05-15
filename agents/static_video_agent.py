import os
import subprocess


def create_static_video(image_path, audio_path, output_path="work/output.mp4"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    filter_complex = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
        "eq=brightness=-0.1:contrast=1.05:saturation=1.1[bg];"
        "[1:a]showwaves=s=380x55:mode=cline:rate=30:colors=0xFFFFFF[waves];"
        "[bg][waves]overlay=W-w-30:H-h-30[v]"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ], check=True)

    print(f"  Video with waveform created: {output_path}")
    return output_path

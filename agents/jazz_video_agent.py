import os
import subprocess


def create_jazz_video(image_path, audio_path, output_path="work/output.mp4"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    filter_complex = (
        # 背景画像を1920x1080にリサイズ・暗く
        "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
        "colorlevels=rimin=0:gimin=0:bimin=0:rimax=0.85:gimax=0.85:bimax=0.85[bg];"

        # フィルムグレイン（古い映像風ノイズ）
        "[bg]noise=alls=12:allf=t+u[grain];"

        # ビネット（周辺を暗く）
        "[grain]vignette=PI/5[vignette];"

        # 右下に小さい白い波形
        "[1:a]showwaves=s=380x55:mode=cline:rate=30:colors=0xFFFFFF[waves];"

        # 波形を右下に配置
        "[vignette][waves]overlay=W-w-30:H-h-30[v]"
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

    print(f"  Jazz video created: {output_path}")
    return output_path

import os
import subprocess


def loop_audio(mp3_paths, target_hours=3, output_path="work/looped.mp3"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    concat_path = "work/concat.mp3"
    filelist_path = "work/filelist.txt"

    with open(filelist_path, "w") as f:
        for path in mp3_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", filelist_path, "-c", "copy", concat_path
    ], check=True, capture_output=True)

    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", concat_path
    ], capture_output=True, text=True, check=True)
    single_duration = float(result.stdout.strip())

    target_seconds = target_hours * 3600
    loop_count = int(target_seconds / single_duration) + 2

    subprocess.run([
        "ffmpeg", "-y",
        "-stream_loop", str(loop_count),
        "-i", concat_path,
        "-t", str(target_seconds),
        "-c", "copy", output_path
    ], check=True, capture_output=True)

    os.remove(concat_path)
    os.remove(filelist_path)

    print(f"  Audio looped: {target_hours}h → {output_path}")
    return output_path

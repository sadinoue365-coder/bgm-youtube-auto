"""
動きのある長尺動画エージェント（ループコピー方式）

静止画から「呼吸ズーム」の短いループ動画(既定24秒)を1回だけ高品質で
レンダリングし、それを再エンコードなしで連結(-c copy)して長尺化する。

【なぜこの方式か】
  3時間全編に動きを付けると従来はエンコード時間が数倍になり、
  GitHub Actions の6時間タイムアウト事故(2026-10-16)の再発リスクがあった。
  ループのコピー連結なら「動き付き」なのに全編エンコードより速い。

【ループが繋がる理由】
  ズーム量をサイン波 z = base + amp*sin(2π·frame/total) で変化させるため、
  最終フレームと先頭フレームが同じ画になり、境目が見えない。

※従来の showwaves(音声波形表示) はこの方式では廃止
  (波形は3時間ぶん固有のため、ループに焼き込めない)。
"""

import math
import os
import subprocess

FPS = 30
LOOP_SECONDS = 24  # サイン1周期 = ループ長


def _probe_duration_seconds(path: str) -> float:
    """ffprobeで音声の長さ(秒)を取得する。"""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def _build_style_filter(style: str) -> str:
    """ループに焼き込むスタイル別の色調・質感フィルタを返す。"""
    if style == "jazz":
        # ノワール: 暗め・フィルムグレイン・ビネット
        # (グレインはビットレートを跳ね上げるため控えめに。上限は下のmaxrateで制御)
        return (
            "colorlevels=rimin=0:gimin=0:bimin=0:rimax=0.85:gimax=0.85:bimax=0.85,"
            "noise=alls=7:allf=t+u,"
            "vignette=PI/5"
        )
    # warm (cafe/chill): 少し暗く・コントラスト/彩度アップ
    return "eq=brightness=-0.1:contrast=1.05:saturation=1.1"


def _render_motion_loop(image_path: str, loop_path: str, style: str) -> None:
    """静止画から呼吸ズームのループ動画(LOOP_SECONDS秒)を高品質レンダリング。"""
    total_frames = FPS * LOOP_SECONDS
    # 2倍に拡大してからzoompanすることでズーム時の画質劣化を防ぐ
    vf = (
        "scale=3840:2160:force_original_aspect_ratio=decrease,"
        "pad=3840:2160:(ow-iw)/2:(oh-ih)/2,"
        f"zoompan=z='1.04+0.04*sin(2*PI*on/{total_frames})'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s=1920x1080:fps={FPS},"
        f"{_build_style_filter(style)},"
        "format=yuv420p"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-t", "1", "-i", image_path,
            "-vf", vf,
            "-frames:v", str(total_frames),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            # ファイルサイズ上限(3hで約3GB以内)。超過するとアップロードが延びて
            # 6hタイムアウト(2026-10-16再発)の原因になるため必須
            "-maxrate", "2300k", "-bufsize", "4600k",
            loop_path,
        ],
        check=True,
    )


def create_motion_video(image_path, audio_path, output_path="work/output.mp4",
                        style="jazz"):
    """
    静止画+音声 → ゆっくり呼吸ズームする長尺動画を生成する。

    Args:
        style: "jazz" (ノワール調) / "warm" (cafe/chill向け暖色調)
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    work_dir = os.path.dirname(output_path)
    loop_path = os.path.join(work_dir, "motion_loop.mp4")
    concat_path = os.path.join(work_dir, "motion_concat.txt")

    # 1) 24秒の動きループを1回だけレンダリング(1〜2分)
    print(f"  [motion] 呼吸ズームループを生成中 ({LOOP_SECONDS}s/{style})...")
    _render_motion_loop(image_path, loop_path, style)

    # 2) 音声の長さに合わせた回数だけコピー連結(再エンコードなし)
    duration = _probe_duration_seconds(audio_path)
    repeats = math.ceil(duration / LOOP_SECONDS) + 1
    with open(concat_path, "w") as f:
        abs_loop = os.path.abspath(loop_path)
        f.write("\n".join([f"file '{abs_loop}'"] * repeats))
    print(f"  [motion] {repeats}回連結 (音声{duration/3600:.1f}h, 映像は再エンコードなし)")

    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", concat_path,
            "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ],
        check=True,
    )

    for p in (loop_path, concat_path):
        try:
            os.remove(p)
        except OSError:
            pass

    print(f"  Motion video created: {output_path}")
    return output_path

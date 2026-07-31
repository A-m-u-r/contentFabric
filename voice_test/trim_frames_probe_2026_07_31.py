"""Сколько кадров реально отдаёт наш trim при разной записи конца.

    /opt/venv/bin/python /app/voice_test/trim_frames_probe_2026_07_31.py <clip.mp4>
"""
import subprocess
import sys

NORM = ("scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1")


def frames(clip, end_expr):
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", clip,
         "-vf", f"trim=start=0:end={end_expr},setpts=PTS-STARTPTS,{NORM}",
         "-f", "null", "-"],
        capture_output=True, text=True)
    count = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", clip,
         "-vf", f"trim=start=0:end={end_expr},setpts=PTS-STARTPTS,{NORM}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-s", "16x16", "-"],
        capture_output=True).stdout
    return len(count) // (16 * 16), out.stderr.strip()


def main(clip):
    for end in ("1.867", "1.866", "1.850", "1.885", "1.900", "2.133", "2.116"):
        n, err = frames(clip, end)
        print(f"  end={end}: {n} кадров = {n / 30:.4f}с {err}")


if __name__ == "__main__":
    main(sys.argv[1])

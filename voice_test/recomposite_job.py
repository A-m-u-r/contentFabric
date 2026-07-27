"""Re-assemble a finished job from its cached clips, plus a lip-offset A/B set.

Free: only ffmpeg runs — no fal.ai, no TTS. Used to check assembly changes
against a real job and to pick the residual lip offset by ear.

    python voice_test/recomposite_job.py output/saas_<id> [offset_ms ...]

Offsets are "lips later by N ms" (i.e. the voice arrives N ms earlier).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, "/app")

from saasshorts import (  # noqa: E402
    _is_broll_shot,
    _mp3_encoder_delay,
    _pick_background_music,
    composite_storyboard_video,
)


def slug_of(job_dir):
    for name in sorted(os.listdir(job_dir)):
        if name.endswith("_storyboard_final.mp4"):
            return name[: -len("_storyboard_final.mp4")]
    raise SystemExit(f"no finished video in {job_dir}")


def clips_of(job_dir, slug, shots):
    clips = []
    for index, shot in enumerate(shots, start=1):
        broll = _is_broll_shot(shot)
        name = f"{slug}_avatar_broll_{index:02d}.mp4" if broll else f"{slug}_avatar_{index:02d}.mp4"
        path = os.path.join(job_dir, name)
        if not os.path.exists(path):
            raise SystemExit(f"missing cached clip {name}")
        slice_audio = os.path.join(job_dir, f"{slug}_slice_{index:02d}.mp3")
        clips.append({
            "path": path,
            "duration": float(shot["end"]) - float(shot["start"]),
            "shot": shot,
            "speech_offset": 0.0 if broll else _mp3_encoder_delay(slice_audio),
        })
    return clips


def shift_lips(source, output, offset_ms):
    """Hold the first frame for offset_ms so the mouth lands that much later."""
    if offset_ms == 0:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", source, "-c", "copy", output],
                       check=True)
        return output
    seconds = abs(offset_ms) / 1000.0
    if offset_ms > 0:
        vf = f"tpad=start_mode=clone:start_duration={seconds:.3f},setpts=PTS-STARTPTS"
    else:
        vf = f"trim=start={seconds:.3f},setpts=PTS-STARTPTS"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", source,
        "-filter_complex", f"[0:v]{vf}[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "copy",
        "-shortest", output,
    ], check=True)
    return output


def main():
    job_dir = sys.argv[1].rstrip("/")
    offsets = [int(x) for x in sys.argv[2:]]
    slug = slug_of(job_dir)
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    shots = meta["shots"]
    clips = clips_of(job_dir, slug, shots)
    for clip in clips:
        print(f"  {os.path.basename(clip['path'])}: slot {clip['duration']:.3f}s "
              f"head {clip['speech_offset'] * 1000:.0f}ms")
    audio = os.path.join(job_dir, f"{slug}_voice_clean.mp3")
    if not os.path.exists(audio):
        audio = os.path.join(job_dir, f"{slug}_voice.mp3")
    subs = os.path.join(job_dir, f"{slug}_subs.ass")
    fixed = os.path.join(job_dir, f"{slug}_storyboard_final_fixed.mp4")
    print(f"re-assembling {os.path.basename(fixed)} ...")
    composite_storyboard_video(
        clips, audio, subs, fixed, music_path=_pick_background_music(slug),
    )
    if not offsets:
        return
    out_dir = os.path.join("voice_test", "sync_check_2026_07_25")
    os.makedirs(out_dir, exist_ok=True)
    for offset in offsets:
        if offset > 0:
            name = f"lips_later_{offset:03d}ms.mp4"
        elif offset < 0:
            name = f"lips_earlier_{abs(offset):03d}ms.mp4"
        else:
            name = "baseline_000ms.mp4"
        target = os.path.join(out_dir, name)
        shift_lips(fixed, target, offset)
        print(f"  {name}")


if __name__ == "__main__":
    main()

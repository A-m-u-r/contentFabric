"""Rebuild every old gallery video with the new audio/subtitle pipeline. Zero paid calls.

- Storyboard job (e468baa0, clips cached): full re-composite with the new caption
  style (no top plates, outline+shadow, pop-in) + loudnorm + ducked music bed.
- Old June UGC jobs (subs burned into the picture, b-roll timeline not stored):
  audio-only v2 — video stream copied, audio normalized with music bed.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, "/app")

from saasshorts import (
    _SUB_POP_TAG,
    _final_audio_filter_parts,
    _get_media_duration,
    _pick_background_music,
    _strip_pictographs,
    composite_storyboard_video,
)

OUT = "/app/output"


def restyle_ass(src_path: str, dst_path: str) -> None:
    """Old ASS -> new caption preset: keep word timings, drop top plates."""
    with open(src_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    header = """[Script Info]
Title: Storyboard Reels Caption Preset
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,Montserrat ExtraBold,60,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,3,2,2,96,96,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for line in lines:
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        style = parts[3]
        if style in ("Hook", "Overlay"):
            continue  # top plates removed by user decision
        text = _strip_pictographs(parts[9])
        text = text.replace("\\bord8", "").replace("{\\rSubtitle}", "{\\c&HFFFFFF&}")
        if not text:
            continue
        parts[0] = "Dialogue: 0"
        parts[3] = "Subtitle"
        parts[9] = _SUB_POP_TAG + text
        events.append(",".join(parts))
    with open(dst_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    print(f"  restyled subs: {os.path.basename(dst_path)} ({len(events)} captions)")


def rebuild_storyboard(job: str, slug: str) -> None:
    print(f"== storyboard rebuild: {os.path.basename(job)}")
    dst_ass = os.path.join(job, f"{slug}_subs_v2.ass")
    restyle_ass(os.path.join(job, f"{slug}_subs.ass"), dst_ass)
    order = [
        ("avatar_01", "slice_01"), ("avatar_broll_02", "slice_02"),
        ("avatar_03", "slice_03"), ("avatar_broll_04", "slice_04"),
        ("avatar_05", "slice_05"),
    ]
    clips = []
    for clip_name, slice_name in order:
        path = os.path.join(job, f"{slug}_{clip_name}.mp4")
        assert os.path.exists(path), path
        dur = _get_media_duration(os.path.join(job, f"{slug}_{slice_name}.mp3"))
        clips.append({"path": path, "duration": dur})
    voice = os.path.join(job, f"{slug}_voice_clean.mp3")
    if not os.path.exists(voice):
        voice = os.path.join(job, f"{slug}_voice.mp3")
    final = os.path.join(job, f"{slug}_storyboard_final_v2.mp4")
    composite_storyboard_video(clips, voice, dst_ass, final,
                               music_path=_pick_background_music(slug))
    print(f"  done: {os.path.basename(final)} {os.path.getsize(final)} bytes")


def rebuild_ugc_audio_only(job: str) -> None:
    """Subs are burned in and the b-roll timeline is gone: upgrade audio only."""
    name = os.path.basename(job.rstrip("/"))
    src = os.path.join(job, "__final.mp4")
    if not os.path.exists(src):
        print(f"== skip {name}: no __final.mp4")
        return
    print(f"== ugc audio-only rebuild: {name}")
    music = _pick_background_music(name)
    dst = os.path.join(job, "__final_v2.mp4")
    audio_parts = _final_audio_filter_parts("0", "1" if music else None, 0.16)
    cmd = [
        "ffmpeg", "-y", "-i", src,
        *(["-stream_loop", "-1", "-i", music] if music else []),
        "-filter_complex", ";".join(audio_parts),
        "-map", "0:v", "-c:v", "copy",
        "-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
        "-shortest", dst,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"  done: __final_v2.mp4 {os.path.getsize(dst)} bytes")


rebuild_storyboard(
    os.path.join(OUT, "saas_e468baa0-3354-4d33-99f6-2763c7b21945"),
    "not_your_fault_after_30",
)
for d in sorted(os.listdir(OUT)):
    job = os.path.join(OUT, d)
    if d.startswith("saas_") and d != "saas_e468baa0-3354-4d33-99f6-2763c7b21945" and os.path.isdir(job):
        rebuild_ugc_audio_only(job)
print("ALL DONE")

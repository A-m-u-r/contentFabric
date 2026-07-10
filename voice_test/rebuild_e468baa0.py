"""Rebuild the real run's final video from cached clips — zero paid calls.

Applies the new pipeline to existing footage: bundled Montserrat font,
pictograph cleanup in subtitles, loudnorm -14 LUFS, ducked music bed.
Writes *_final_v2.mp4 next to the original for A/B comparison.
"""
import os
import sys

sys.path.insert(0, "/app")

from saasshorts import (
    _get_media_duration,
    _pick_background_music,
    _strip_pictographs,
    composite_storyboard_video,
)

JOB = "/app/output/saas_e468baa0-3354-4d33-99f6-2763c7b21945"
SLUG = "not_your_fault_after_30"

# 1. Patch the subtitle file: bundled font + no tofu glyphs.
src_ass = os.path.join(JOB, f"{SLUG}_subs.ass")
dst_ass = os.path.join(JOB, f"{SLUG}_subs_v2.ass")
with open(src_ass, encoding="utf-8") as f:
    content = f.read().replace("Arial Black", "Montserrat ExtraBold")
out_lines = []
for line in content.splitlines():
    if line.startswith("Dialogue:"):
        parts = line.split(",", 9)
        parts[9] = _strip_pictographs(parts[9])
        line = ",".join(parts)
    out_lines.append(line)
with open(dst_ass, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines) + "\n")
print("patched subs:", dst_ass)

# 2. Clips in timeline order; slot duration = matching voiceover slice length.
order = [
    ("avatar_01", "slice_01"),
    ("avatar_broll_02", "slice_02"),
    ("avatar_03", "slice_03"),
    ("avatar_broll_04", "slice_04"),
    ("avatar_05", "slice_05"),
]
clips = []
for clip_name, slice_name in order:
    path = os.path.join(JOB, f"{SLUG}_{clip_name}.mp4")
    assert os.path.exists(path), path
    dur = _get_media_duration(os.path.join(JOB, f"{SLUG}_{slice_name}.mp3"))
    clips.append({"path": path, "duration": dur})
    print(f"  {clip_name}: slot {dur:.2f}s")

voice = os.path.join(JOB, f"{SLUG}_voice_clean.mp3")
if not os.path.exists(voice):
    voice = os.path.join(JOB, f"{SLUG}_voice.mp3")
music = _pick_background_music(SLUG)
print("voice:", os.path.basename(voice), "| music:", music and os.path.basename(music))

final = os.path.join(JOB, f"{SLUG}_storyboard_final_v2.mp4")
composite_storyboard_video(clips, voice, dst_ass, final, music_path=music)
print("done:", final, os.path.getsize(final), "bytes")

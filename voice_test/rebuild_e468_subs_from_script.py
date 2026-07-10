"""Regenerate e468baa0 subtitles from the REAL script text and re-composite v2.

gallery_metadata.json stores full_narration — so the old video CAN get exact
script-aligned captions: Whisper supplies timings, the script supplies words.
Zero paid calls (local whisper + ffmpeg).
"""
import json
import os
import sys

sys.path.insert(0, "/app")

from saasshorts import (
    _align_asr_words_to_script,
    _get_media_duration,
    _pick_background_music,
    composite_storyboard_video,
    generate_storyboard_ass_subtitles,
    transcribe_audio_for_subs,
)

JOB = "/app/output/saas_e468baa0-3354-4d33-99f6-2763c7b21945"
SLUG = "not_your_fault_after_30"

with open(os.path.join(JOB, "gallery_metadata.json"), encoding="utf-8") as f:
    meta = json.load(f)
full_narration = meta["full_narration"]
shots = meta.get("shots") or []

voice = os.path.join(JOB, f"{SLUG}_voice_clean.mp3")
if not os.path.exists(voice):
    voice = os.path.join(JOB, f"{SLUG}_voice.mp3")

words = transcribe_audio_for_subs(voice, language="ru")
aligned = _align_asr_words_to_script(words, full_narration)

dst_ass = os.path.join(JOB, f"{SLUG}_subs_v2.ass")
generate_storyboard_ass_subtitles(voice, shots, dst_ass, max_words=2, words=aligned)

order = [
    ("avatar_01", "slice_01"), ("avatar_broll_02", "slice_02"),
    ("avatar_03", "slice_03"), ("avatar_broll_04", "slice_04"),
    ("avatar_05", "slice_05"),
]
clips = []
for clip_name, slice_name in order:
    path = os.path.join(JOB, f"{SLUG}_{clip_name}.mp4")
    dur = _get_media_duration(os.path.join(JOB, f"{SLUG}_{slice_name}.mp3"))
    clips.append({"path": path, "duration": dur})

final = os.path.join(JOB, f"{SLUG}_storyboard_final_v2.mp4")
composite_storyboard_video(clips, voice, dst_ass, final,
                           music_path=_pick_background_music(SLUG))
print("done:", final, os.path.getsize(final), "bytes")

with open(dst_ass, encoding="utf-8") as f:
    ass = f.read()
print("СЛАБОЕ in subs:", "СЛАБОЕ" in ass)
print("СЛАБАЯ in subs:", "СЛАБАЯ" in ass)

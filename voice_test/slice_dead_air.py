"""How much silence each shot's voiceover slice opens with, on a real job.

Dead air at the head of a slice is what makes a cut read as "picture ahead of
the voice": the avatar clip starts moving its mouth before the phrase begins.
Free — local whisper only, no paid calls.

    python voice_test/slice_dead_air.py output/saas_<id>
"""
import json
import os
import sys

sys.path.insert(0, "/app")

import saasshorts as s  # noqa: E402


def main(job_dir):
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    slug = None
    for name in sorted(os.listdir(job_dir)):
        if name.endswith("_voice_clean.mp3"):
            slug = name[: -len("_voice_clean.mp3")]
    audio = os.path.join(job_dir, f"{slug}_voice_clean.mp3")
    shots = [dict(shot) for shot in meta["shots"]]
    # Same text the pipeline voices: shot speech joined, not the script's
    # full_narration field (that one can still carry a CTA the TTS never got).
    narration = " ".join(shot.get("speech", "") for shot in shots if shot.get("speech")).strip()
    words = s._align_asr_words_to_script(
        s.transcribe_audio_for_subs(audio, language=meta.get("language") or "ru"),
        narration, log=lambda *a: None,
    )
    slices, _ = s._align_shots_to_voiceover(shots, words, s._get_media_duration(audio))
    print(f"{'кадр':>5} {'старт':>8} {'тишина в начале':>16}")
    for index, sl in enumerate(slices, start=1):
        start = sl["start"]
        nxt = next((w for w in words if float(w["start"]) >= start - 0.001), None)
        dead = (float(nxt["start"]) - start) * 1000 if nxt else 0.0
        print(f"{index:>5} {start:>7.3f}s {dead:>13.0f} ms")


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"))

"""Dead air at the head of every slice: the boundary rule we shipped with vs now.

    python voice_test/dead_air_before_after.py output/saas_<id>
"""
import json
import os
import sys

sys.path.insert(0, "/app")

import saasshorts as s  # noqa: E402


def midpoint(prev_end, next_start):
    """The rule the old job was cut with: halfway through the pause."""
    return (prev_end + next_start) / 2


def dead_air(slices, words):
    out = []
    for sl in slices:
        nxt = next((w for w in words if float(w["start"]) >= sl["start"] - 0.001), None)
        out.append((sl["start"], (float(nxt["start"]) - sl["start"]) * 1000 if nxt else 0.0))
    return out


def main(job_dir):
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    slug = None
    for name in sorted(os.listdir(job_dir)):
        if name.endswith("_voice_clean.mp3"):
            slug = name[: -len("_voice_clean.mp3")]
    audio = os.path.join(job_dir, f"{slug}_voice_clean.mp3")
    shots = [dict(shot) for shot in meta["shots"]]
    narration = " ".join(shot.get("speech", "") for shot in shots if shot.get("speech")).strip()
    words = s._align_asr_words_to_script(
        s.transcribe_audio_for_subs(audio, language=meta.get("language") or "ru"),
        narration, log=lambda *a: None,
    )
    duration = s._get_media_duration(audio)

    now = dead_air(s._align_shots_to_voiceover(shots, words, duration)[0], words)
    real = s._phrase_boundary
    s._phrase_boundary = midpoint
    try:
        before = dead_air(s._align_shots_to_voiceover([dict(x) for x in shots], words, duration)[0], words)
    finally:
        s._phrase_boundary = real

    print(f"{'кадр':>5} {'было (середина паузы)':>24} {'стало (за 80 мс до слова)':>27}")
    for i, ((s0, d0), (s1, d1)) in enumerate(zip(before, now), start=1):
        print(f"{i:>5} {s0:>10.3f}s {d0:>8.0f} ms {s1:>14.3f}s {d1:>10.0f} ms")
    spread = max(d for _, d in before) - min(d for _, d in before)
    print(f"\nразброс тишины по кадрам: было {spread:.0f} мс, стало "
          f"{max(d for _, d in now) - min(d for _, d in now):.0f} мс")
    print(f"задержка mp3-энкодера в этом файле: {s._mp3_encoder_delay(audio)*1000:.1f} мс")


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"))

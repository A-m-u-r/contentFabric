"""End-to-end check of the incremental voiceover against the real TTS.

Reproduces the situation this was built for: render a reel with the tail cut
off, then restore the deleted shots and render again. What has to hold is that
the kept shots' audio comes back byte for byte — that is what keeps their paid
avatar clips valid — while only the restored shots are read again.

Costs a few ElevenLabs cents. Touches no fal.ai model.
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saasshorts import build_incremental_voiceover, read_voice_manifest  # noqa: E402
from tts_seam_test import load_shots, resolve_key  # noqa: E402

SLUG = "check"


def digest(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", default="output/saas_feddb8e4-f627-4f1d-a626-cc59562c2275")
    parser.add_argument("--out-dir", default="output/voice_pieces_check")
    parser.add_argument("--keep", type=int, default=2, help="shots left before the first render")
    args = parser.parse_args()

    title, speeches, voice_id = load_shots(args.job_dir)
    shots = [{"shot_number": i + 1, "speech": text, "visual_type": "talking"}
             for i, text in enumerate(speeches)]
    print(f"Script: {title} — {len(shots)} shots, voice {voice_id}")
    os.makedirs(args.out_dir, exist_ok=True)

    settings = {
        "provider": "elevenlabs",
        "fal_key": "",
        "elevenlabs_key": resolve_key(),
        "voice_id": voice_id,
        "minimax_voice_id": "Russian_AmbitiousWoman",
        "language": "ru",
        "actor_gender": "female",
    }

    print(f"\n=== Render 1: only shots 1-{args.keep} kept")
    first = build_incremental_voiceover(shots[:args.keep], args.out_dir, SLUG, **settings)
    kept = {n: digest(os.path.join(args.out_dir, f"{SLUG}_speech_{n:02d}.wav"))
            for n in range(1, args.keep + 1)}
    first_bounds = read_voice_manifest(args.out_dir, SLUG)

    print(f"\n=== Render 2: deleted shots restored")
    second = build_incremental_voiceover(shots, args.out_dir, SLUG, **settings)
    second_bounds = read_voice_manifest(args.out_dir, SLUG)

    print("\n--- what actually happened")
    print(f"re-voiced shots: {second['changed_shots']} (expected {list(range(args.keep + 1, len(shots) + 1))})")
    for number, before in kept.items():
        now = digest(os.path.join(args.out_dir, f"{SLUG}_speech_{number:02d}.wav"))
        moved = (first_bounds[str(number)]["start"] != second_bounds[str(number)]["start"]
                 or first_bounds[str(number)]["end"] != second_bounds[str(number)]["end"])
        print(f"  shot {number}: audio {'IDENTICAL' if now == before else 'CHANGED'}, "
              f"bounds {'moved' if moved else 'unchanged'} "
              f"({second_bounds[str(number)]['start']:.3f}-{second_bounds[str(number)]['end']:.3f}s)")
    joins = [i for i in range(1, len(shots))
             if second_bounds[str(i + 1)].get("take_seq") != second_bounds[str(i)].get("take_seq")]
    print(f"  joins in the track: {joins or 'none'} "
          f"(at {[round(second_bounds[str(i + 1)]['start'], 2) for i in joins]}s)")
    print(f"  master: {second['path']}, first render kept at {first['path']}")
    with open(os.path.join(args.out_dir, "check.json"), "w", encoding="utf-8") as f:
        json.dump({"first": first_bounds, "second": second_bounds,
                   "changed": second["changed_shots"]}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

"""Every avatar clip on disk, scored for lip sync, against what was requested.

Natural experiment: the jobs on disk differ in slice length, tier, prompt and
reference frame. If sync tracks one of those, the table shows it.

    /opt/venv/bin/python /app/voice_test/lip_corpus_2026_07_31.py /app/output
"""
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import (  # noqa: E402
    FPS, SR, _audio, _envelope, _fill_gaps, _frames, mouth_openness,
)

FOREHEAD, CHIN = 10, 152


def dur(path, stream=None):
    cmd = ["ffprobe", "-v", "error"]
    cmd += (["-select_streams", stream, "-show_entries", "stream=duration"] if stream
            else ["-show_entries", "format=duration"])
    cmd += ["-of", "default=nw=1:nk=1", path]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()
    try:
        return float(out[0])
    except (IndexError, ValueError):
        return 0.0


def head_silence(path, floor_frac=0.08):
    pcm = _audio(path)
    if not len(pcm):
        return 0.0
    hop = SR // 100
    env = np.array([np.sqrt(np.mean(pcm[i * hop:(i + 1) * hop] ** 2) + 1e-12)
                    for i in range(len(pcm) // hop)])
    thr = env.max() * floor_frac
    voiced = np.where(env > thr)[0]
    return float(voiced[0]) / 100.0 if len(voiced) else 0.0


def face_height(frames):
    import mediapipe as mp
    mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1,
                                           refine_landmarks=True, min_detection_confidence=0.5)
    result = mesh.process(frames[0])
    mesh.close()
    if not result.multi_face_landmarks:
        return 0.0
    pts = result.multi_face_landmarks[0].landmark
    return abs(pts[FOREHEAD].y - pts[CHIN].y)


def score(path):
    frames = _frames(path)
    pcm = _audio(path)
    env = _envelope(pcm, len(frames))
    mouth = _fill_gaps(mouth_openness(frames[: len(env)]))
    if mouth is None:
        return None
    mouth = mouth[: len(env)]
    voiced = np.where(env > env.min() + 0.10 * (env.max() - env.min()))[0]
    lo, hi = (int(voiced[0]), int(voiced[-1]) + 1) if len(voiced) else (0, len(env))
    a = env[lo:hi]
    if len(a) < FPS:
        lo, hi, a = 0, len(env), env
    a = (a - a.mean()) / (a.std() + 1e-12)
    best = (0, -2.0)
    # ±600 ms: a short take can miss by more than the ±400 ms a longer one ever
    # does, and a narrow search reports that as "no correlation at all".
    for lag in range(-18, 19):
        s = lo + lag
        if s < 0 or s + len(a) > len(mouth):
            continue
        b = mouth[s:s + len(a)]
        b = (b - b.mean()) / (b.std() + 1e-12)
        r = float(np.corrcoef(a, b)[0, 1])
        if r > best[1]:
            best = (lag, r)
    return {
        "lag_ms": best[0] * 1000.0 / FPS,
        "r": best[1],
        "amp": float(np.percentile(mouth, 95) - np.percentile(mouth, 5)),
        "face": face_height(frames),
        "frames": len(env),
    }


def tier_of(clip):
    meta = clip.replace(".mp4", "_base_fal.json")
    if not os.path.exists(meta):
        return "?", 0
    try:
        data = json.load(open(meta, encoding="utf-8"))
    except Exception:
        return "?", 0
    return data.get("tier", "?"), len((data.get("payload") or {}).get("prompt", ""))


def main(root):
    rows = []
    for clip in sorted(glob.glob(os.path.join(root, "saas_*", "*_avatar_[0-9][0-9].mp4"))):
        job = os.path.basename(os.path.dirname(clip))[5:13]
        index = int(re.search(r"_(\d\d)\.mp4$", clip).group(1))
        slug = os.path.basename(clip).rsplit("_avatar_", 1)[0]
        slice_mp3 = os.path.join(os.path.dirname(clip), f"{slug}_slice_{index:02d}.mp3")
        if not os.path.exists(slice_mp3):
            continue
        s = score(clip)
        if not s:
            continue
        tier, prompt_len = tier_of(clip)
        rows.append({
            "job": job, "n": index, "audio": dur(slice_mp3), "video": dur(clip),
            "lead": head_silence(slice_mp3), "tier": tier, "prompt": prompt_len, **s,
        })
        r = rows[-1]
        print(f"{r['job']} #{r['n']:02d} audio {r['audio']:5.2f}s video {r['video']:5.2f}s "
              f"lead {r['lead']:.2f}s {r['tier']:8s} prompt {r['prompt']:3d} "
              f"| lag {r['lag_ms']:+5.0f} ms r {r['r']:+.2f} amp {r['amp']:.3f} "
              f"face {r['face']:.3f}", flush=True)

    if not rows:
        return
    print("\n--- grouped by slice length ---")
    for lo, hi in ((0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 99)):
        band = [r for r in rows if lo <= r["audio"] < hi]
        if band:
            print(f"{lo:.0f}-{hi:.0f}s  n={len(band):2d}  "
                  f"mean r {np.mean([r['r'] for r in band]):+.2f}  "
                  f"median |lag| {np.median([abs(r['lag_ms']) for r in band]):3.0f} ms  "
                  f"mean amp {np.mean([r['amp'] for r in band]):.3f}")
    print("\n--- grouped by tier ---")
    for tier in sorted({r["tier"] for r in rows}):
        band = [r for r in rows if r["tier"] == tier]
        print(f"{tier:9s} n={len(band):2d}  mean r {np.mean([r['r'] for r in band]):+.2f}  "
              f"mean audio {np.mean([r['audio'] for r in band]):.2f}s  "
              f"mean amp {np.mean([r['amp'] for r in band]):.3f}")
    print("\n--- grouped by lead-in silence ---")
    for lo, hi in ((0, 0.05), (0.05, 0.15), (0.15, 9)):
        band = [r for r in rows if lo <= r["lead"] < hi]
        if band:
            print(f"lead {lo:.2f}-{hi:.2f}s n={len(band):2d}  "
                  f"mean r {np.mean([r['r'] for r in band]):+.2f}  "
                  f"mean audio {np.mean([r['audio'] for r in band]):.2f}s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/app/output")

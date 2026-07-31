"""Is the head of an avatar take worse than the rest of it?

Every clip on disk, scored over its first second and over everything after it.
If the model needs a run-up before the mouth locks onto the audio, short takes
are mostly run-up — and that is a slicing decision, not a model limitation.

    /opt/venv/bin/python /app/voice_test/lip_headtail_2026_07_31.py /app/output
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import (  # noqa: E402
    FPS, _audio, _envelope, _fill_gaps, _frames, mouth_openness,
)

HEAD_SECONDS = 1.0


def band(env, mouth, lo, hi, max_lag=12):
    a = env[lo:hi]
    if len(a) < int(0.6 * FPS):
        return None, None
    a = (a - a.mean()) / (a.std() + 1e-12)
    best = (None, -2.0)
    for lag in range(-max_lag, max_lag + 1):
        s = lo + lag
        if s < 0 or s + len(a) > len(mouth):
            continue
        b = mouth[s:s + len(a)]
        b = (b - b.mean()) / (b.std() + 1e-12)
        r = float(np.corrcoef(a, b)[0, 1])
        if r > best[1]:
            best = (lag, r)
    if best[0] is None:
        return None, None
    return best[0] * 1000.0 / FPS, best[1]


def run(paths):
    heads, tails = [], []
    for path in paths:
        frames = _frames(path)
        pcm = _audio(path)
        env = _envelope(pcm, len(frames))
        mouth = _fill_gaps(mouth_openness(frames[: len(env)]))
        if mouth is None:
            continue
        mouth = mouth[: len(env)]
        cut = int(HEAD_SECONDS * FPS)
        h_lag, h_r = band(env, mouth, 0, cut)
        t_lag, t_r = band(env, mouth, cut, len(env))
        name = f"{os.path.basename(os.path.dirname(path))[5:13]}/{os.path.basename(path)[-6:-4]}"
        head_txt = f"{h_lag:+4.0f} ms r {h_r:+.2f}" if h_r is not None else "   (too short)"
        tail_txt = f"{t_lag:+4.0f} ms r {t_r:+.2f}" if t_r is not None else "   (too short)"
        print(f"{name}  len {len(env) / FPS:4.2f}s | head 0-1s: {head_txt} | rest: {tail_txt}",
              flush=True)
        if h_r is not None:
            heads.append(h_r)
        if t_r is not None:
            tails.append(t_r)
    if heads:
        print(f"\nfirst second: n={len(heads)} mean r {np.mean(heads):+.2f} "
              f"median {np.median(heads):+.2f}")
    if tails:
        print(f"after 1 s   : n={len(tails)} mean r {np.mean(tails):+.2f} "
              f"median {np.median(tails):+.2f}")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "/app/output"
    clips = sorted(glob.glob(os.path.join(root, "saas_*", "*_avatar_[0-9][0-9].mp4")))
    clips.append("/app/voice_test/kling_manual_2026_07_26/hand_with_prompt.mp4")
    run(clips)

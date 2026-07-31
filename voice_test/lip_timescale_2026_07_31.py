"""Does the avatar model stretch a short take over its clip floor?

Kling never returns a clip shorter than ~2.13 s. When the slice we send is
shorter than that, the extra picture has to come from somewhere: either the
model holds still after the audio ends (fine) or it spreads the speech over the
whole clip (fatal — the mouth then runs slow and no fixed offset can fix it).

Searches the mouth curve against the audio envelope over time scale AND offset:
scale 1.0 = the model kept our timing, scale audio/video = it stretched.

    /opt/venv/bin/python /app/voice_test/lip_timescale_2026_07_31.py clip.mp4 ...
"""
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import (  # noqa: E402
    FPS, _audio, _envelope, _fill_gaps, _frames, mouth_openness,
)


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


def corr(env, mouth, scale, shift_s):
    """Mouth at time t compared with the envelope at scale*t + shift."""
    t = np.arange(len(mouth)) / FPS
    src = scale * t + shift_s
    keep = (src >= 0) & (src <= (len(env) - 1) / FPS)
    if keep.sum() < FPS:
        return -2.0
    sampled = np.interp(src[keep], np.arange(len(env)) / FPS, env)
    m = mouth[keep]
    if sampled.std() < 1e-9 or m.std() < 1e-9:
        return -2.0
    return float(np.corrcoef(sampled, m)[0, 1])


def run(path):
    frames = _frames(path)
    pcm = _audio(path)
    env = _envelope(pcm, len(frames))
    mouth = _fill_gaps(mouth_openness(frames[: len(env)]))
    name = path.split("/")[-1]
    if mouth is None:
        print(f"{name}: no face")
        return
    mouth = mouth[: len(env)]
    v, a = dur(path, "v:0") or dur(path), dur(path, "a:0")
    best = (None, None, -2.0)
    for scale in np.arange(0.70, 1.41, 0.01):
        for shift in np.arange(-0.5, 0.51, 1 / FPS):
            r = corr(env, mouth, float(scale), float(shift))
            if r > best[2]:
                best = (float(scale), float(shift), r)
    flat = max((corr(env, mouth, 1.0, float(s)), s) for s in np.arange(-0.5, 0.51, 1 / FPS))
    print(f"{name}: video {v:.3f}s audio {a:.3f}s (audio/video {a / v:.3f})")
    print(f"   no stretch      : r {flat[0]:+.2f} at {flat[1] * 1000:+4.0f} ms")
    print(f"   best over scales: r {best[2]:+.2f} at scale {best[0]:.2f}, "
          f"{best[1] * 1000:+4.0f} ms")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        run(path)
        print()

"""Control for the lip-vs-sound metric: does it survive short windows?

The reel's takes are 1.7-2.6 s, the hand-made control clip is 4.4 s. Before
reading anything into a weak correlation on a short take, measure the known-good
clip over windows of the same length.

    /opt/venv/bin/python /app/voice_test/lip_window_control_2026_07_31.py clip.mp4 ...
"""
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import (  # noqa: E402
    FPS, _audio, _envelope, _fill_gaps, _frames, mouth_openness,
)


def corr_at_lag(env, mouth, lo, hi, lag):
    a = env[lo:hi]
    s = lo + lag
    if s < 0 or s + len(a) > len(mouth) or len(a) < FPS:
        return None
    b = mouth[s:s + len(a)]
    a = (a - a.mean()) / (a.std() + 1e-12)
    b = (b - b.mean()) / (b.std() + 1e-12)
    return float(np.corrcoef(a, b)[0, 1])


def best(env, mouth, lo, hi, max_lag=12):
    table = [(lag, corr_at_lag(env, mouth, lo, hi, lag)) for lag in range(-max_lag, max_lag + 1)]
    table = [(lag, r) for lag, r in table if r is not None]
    if not table:
        return None, None
    lag, r = max(table, key=lambda t: t[1])
    return lag * 1000.0 / FPS, r


def run(path, window_s=1.75):
    frames = _frames(path)
    pcm = _audio(path)
    env = _envelope(pcm, len(frames))
    mouth = _fill_gaps(mouth_openness(frames[: len(env)]))
    if mouth is None:
        print(f"{path}: no face")
        return
    mouth = mouth[: len(env)]
    name = path.split("/")[-1]
    lag, r = best(env, mouth, 0, len(env))
    print(f"{name}: whole clip {len(env)} frames -> {lag:+.0f} ms r={r:+.2f}")
    win = int(window_s * FPS)
    step = win // 2
    for lo in range(0, max(1, len(env) - win + 1), step):
        hi = lo + win
        lag, r = best(env, mouth, lo, hi)
        if lag is None:
            continue
        print(f"    window {lo / FPS:4.1f}-{hi / FPS:4.1f}s -> {lag:+4.0f} ms r={r:+.2f}")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        run(path)
        print()

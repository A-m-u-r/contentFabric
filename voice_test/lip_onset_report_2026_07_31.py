"""How fast does the mouth pick up the sound at the head of an avatar take?

Per clip: where the sound starts, where the mouth starts moving, how long the
sound runs past the picture, and the correlation lag over the speaking region
only (the silent tail Kling pads to its clip floor is excluded — it drags a
whole-clip correlation around by hundreds of ms).

    /opt/venv/bin/python /app/voice_test/lip_onset_report_2026_07_31.py clip.mp4 ...
"""
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import (  # noqa: E402
    FPS, SR, _audio, _envelope, _fill_gaps, _frames, mouth_openness,
)


def dur(path, stream=None):
    cmd = ["ffprobe", "-v", "error"]
    if stream:
        cmd += ["-select_streams", stream, "-show_entries", "stream=duration"]
    else:
        cmd += ["-show_entries", "format=duration"]
    cmd += ["-of", "default=nw=1:nk=1", path]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()
    try:
        return float(out[0])
    except (IndexError, ValueError):
        return 0.0


def onset(curve, floor, span, frac):
    thr = floor + frac * span
    for i in range(len(curve) - 1):
        if curve[i] > thr and curve[i + 1] > thr:
            return i
    return None


def lag_over(env, mouth, lo, hi, max_lag_frames=12):
    """Correlation lag (mouth - sound) using frames [lo, hi) only."""
    a, b = env[lo:hi], mouth[lo:hi]
    if len(a) < FPS:
        return None, 0.0
    a = (a - a.mean()) / (a.std() + 1e-12)
    best = (None, -2.0)
    for lag in range(-max_lag_frames, max_lag_frames + 1):
        s = lo + lag
        if s < 0 or s + len(a) > len(mouth):
            continue
        m = mouth[s:s + len(a)]
        m = (m - m.mean()) / (m.std() + 1e-12)
        r = float(np.corrcoef(a, m)[0, 1])
        if r > best[1]:
            best = (lag, r)
    if best[0] is None:
        return None, 0.0
    return best[0] * 1000.0 / FPS, best[1]


def report(path, audio_from=None):
    frames = _frames(path)
    pcm = _audio(audio_from or path)
    env = _envelope(pcm, len(frames))
    frames = frames[: len(env)]
    mouth = _fill_gaps(mouth_openness(frames))
    name = path.split("/")[-1]
    if mouth is None:
        print(f"{name}: no face")
        return
    mouth = mouth[: len(env)]

    v_dur, a_dur = dur(path, "v:0") or dur(path), dur(audio_from or path, "a:0")
    e_span = env.max() - env.min()
    m_floor = float(np.percentile(mouth, 5))
    m_span = float(np.percentile(mouth, 95)) - m_floor

    s_on = onset(env, env.min(), e_span, 0.10)
    m_on = onset(mouth, m_floor, m_span, 0.30)
    speech = np.where(env > env.min() + 0.10 * e_span)[0]
    lo, hi = (int(speech[0]), int(speech[-1]) + 1) if len(speech) else (0, len(env))
    lag, r = lag_over(env, mouth, lo, hi)

    print(f"{name}")
    print(f"   video {v_dur:.3f}s | audio {a_dur:.3f}s | frames {len(frames)}")
    print(f"   sound starts {(s_on or 0) * 1000 // FPS:4.0f} ms | "
          f"mouth starts {(m_on if m_on is not None else -1) * 1000 // FPS:4.0f} ms | "
          f"mouth open at frame 0: {mouth[0]:.3f} (floor {m_floor:.3f}, peak {mouth.max():.3f})")
    if s_on is not None and m_on is not None:
        print(f"   mouth pick-up after sound: {(m_on - s_on) * 1000 // FPS:+4.0f} ms")
    if lag is not None:
        print(f"   lag over speech region   : {lag:+4.0f} ms (r={r:+.2f}, "
              f"frames {lo}-{hi} of {len(env)})")


if __name__ == "__main__":
    for spec in sys.argv[1:]:
        if "|" in spec:
            video, audio = spec.split("|")
            report(video, audio)
        else:
            report(spec)
        print()

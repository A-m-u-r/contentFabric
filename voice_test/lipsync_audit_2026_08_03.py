"""Насколько рот попадает в звук — с таблицей корреляции, а не одним числом.

`lip_open_probe` печатает один сдвиг. Когда сдвига нет вовсе (рот живёт своей
жизнью), максимум корреляции уезжает на край окна и число читается как «−500 мс»,
хотя мерить там уже нечего. Здесь видно и силу связи, и её форму: r на нуле, r в
максимуме, где этот максимум и сколько рот вообще шевелится.

    python voice_test/lipsync_audit_2026_08_03.py clip.mp4 [clip.mp4@start:dur ...]
"""
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")

from lip_open_probe import (  # noqa: E402
    FPS, _audio, _envelope, _fill_gaps, _frames, mouth_openness,
)

MAX_LAG = 9  # ±300 мс: дальше уезжать нечему, там уже другой слог


def _z(x):
    x = np.asarray(x, dtype=np.float64)
    return (x - x.mean()) / (x.std() + 1e-12)


def table(sound, mouth, max_lag=MAX_LAG):
    """r(lag) для сдвига рта относительно звука, в кадрах."""
    sound, mouth = _z(sound), _z(mouth)
    n = min(len(sound), len(mouth))
    sound, mouth = sound[:n], mouth[:n]
    out = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a, b = sound[: n - lag], mouth[lag:]
        else:
            a, b = sound[-lag:], mouth[: n + lag]
        if len(a) < FPS:
            continue
        out.append((lag, float(np.corrcoef(a, b)[0, 1])))
    return out


def audit(spec, audio_from=None):
    path, start, duration = spec, None, None
    if "@" in spec:
        path, rng = spec.split("@")
        start, duration = (float(v) for v in rng.split(":"))
    frames = _frames(path, start, duration)
    pcm = _audio(audio_from or path, start, duration)
    env = _envelope(pcm, len(frames))
    frames = frames[: len(env)]
    raw = mouth_openness(frames)
    mouth = _fill_gaps(raw)
    label = spec.split("/")[-1]
    if mouth is None:
        print(f"{label}: лицо не найдено")
        return
    rows = table(env, mouth)
    lags = np.array([r[0] for r in rows])
    corrs = np.array([r[1] for r in rows])
    top = int(np.argmax(corrs))
    zero = float(corrs[lags == 0][0])
    span = float(np.percentile(mouth, 95) - np.percentile(mouth, 5))
    print(f"{label}: {len(frames)} кадров, лицо на {int((~np.isnan(raw)).sum())}")
    print(f"    r на нуле {zero:+.2f} | максимум {corrs[top]:+.2f} "
          f"на {lags[top] * 1000 // FPS:+.0f} мс | ход рта {span:.3f}")
    print("    r(мс): " + "  ".join(
        f"{int(l * 1000 // FPS):+d}:{c:+.2f}" for l, c in zip(lags, corrs)
    ))


if __name__ == "__main__":
    args, audio_from = [], None
    for arg in sys.argv[1:]:
        if arg.startswith("--audio="):
            audio_from = arg.split("=", 1)[1]
        else:
            args.append(arg)
    for spec in args:
        audit(spec, audio_from)

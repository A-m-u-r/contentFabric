"""Side-by-side lip report for avatar clips: when the mouth opens vs when sound starts.

    python voice_test/clip_lip_report.py a.mp4 b.mp4 ...
"""
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")

from lip_open_probe import (  # noqa: E402
    FPS, SR, _audio, _envelope, _fill_gaps, _frames, best_lag, mouth_openness,
)


def sound_onset(env):
    thr = max(env.max() * 0.08, np.median(env) * 0.5)
    return int(np.argmax(env > thr))


def report(path):
    frames = _frames(path)
    pcm = _audio(path)
    env = _envelope(pcm, len(frames))
    frames = frames[: len(env)]
    raw = mouth_openness(frames)
    mouth = _fill_gaps(raw)
    name = path.split("/")[-1]
    if mouth is None:
        print(f"{name}: лицо не найдено")
        return
    onset = sound_onset(env)
    span = np.percentile(mouth, 95) - mouth.min()
    thr = mouth.min() + 0.25 * span
    first_open = next((i for i in range(len(mouth) - 1)
                       if mouth[i] > thr and mouth[i + 1] > thr), 0)
    lag, r, _ = best_lag(env, mouth)
    print(f"{name}")
    print(f"   звук с {onset * 1000 // FPS:4.0f} мс | рот открыт с {first_open * 1000 // FPS:4.0f} мс "
          f"| раскрытие на 0-м кадре {mouth[0]:.3f} (максимум {mouth.max():.3f})")
    print(f"   до звука рот в среднем {mouth[:max(1, onset)].mean():.3f}, "
          f"на речи {mouth[onset:].mean():.3f}")
    print(f"   общий сдвиг губ к звуку: {lag:+.0f} мс (r={r:+.2f})")
    print(f"   первые 12 кадров: {np.round(mouth[:12], 3).tolist()}")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        report(path)

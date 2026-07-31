"""Где в готовом ролике звук проваливается в ничто.

Не «пауза», а именно провал: шумовой пол держится, держится — и исчезает.
В наушниках это слышно как обрыв связи. Скрипт ищет такие участки и печатает,
насколько глубоко и надолго проваливается уровень и что стоит по краям.

    /opt/venv/bin/python /app/voice_test/dropout_report_2026_07_31.py <reel.mp4> [...]
"""
import subprocess
import sys

import numpy as np

SR = 48000
HOP = 0.005


def pcm(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1",
         "-ar", str(SR), "-f", "f32le", "-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def rms_db(samples):
    hop = int(SR * HOP)
    n = len(samples) // hop
    block = samples[: n * hop].reshape(n, hop)
    return 20 * np.log10(np.sqrt((block ** 2).mean(axis=1)) + 1e-12)


def runs_below(level, threshold):
    quiet = level < threshold
    edges = np.diff(quiet.astype(np.int8))
    starts = list(np.where(edges == 1)[0] + 1)
    ends = list(np.where(edges == -1)[0] + 1)
    if quiet.size and quiet[0]:
        starts.insert(0, 0)
    if quiet.size and quiet[-1]:
        ends.append(len(quiet))
    return list(zip(starts, ends))


def main(paths):
    for path in paths:
        level = rms_db(pcm(path))
        floor = np.percentile(level, 20)
        speech = np.percentile(level, 95)
        print(f"\n{path}")
        print(f"  длина {len(level) * HOP:.2f}с, речь {speech:+.1f} dB, "
              f"шумовой пол {floor:+.1f} dB")
        deep = floor - 12
        total = 0.0
        for start, end in runs_below(level, deep):
            length = (end - start) * HOP
            if length < 0.015:
                continue
            total += length
            before = level[max(0, start - 6):start]
            after = level[end:end + 6]
            print(f"  {start * HOP:6.2f}с  провал {length * 1000:5.0f} мс  "
                  f"дно {level[start:end].min():+7.1f} dB   "
                  f"до {before.max() if before.size else float('nan'):+6.1f} dB / "
                  f"после {after.max() if after.size else float('nan'):+6.1f} dB")
        print(f"  всего провалов ниже {deep:+.1f} dB: {total * 1000:.0f} мс")


if __name__ == "__main__":
    main(sys.argv[1:])

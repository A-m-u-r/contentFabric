"""Is the voice in the finished reel where the master track says it is?

Everything upstream is timed against the master voiceover: slice bounds, shot
slots, subtitles. If the encoded final track sits a few dozen ms off the master,
every mouth in the reel is off by exactly that much and no per-clip fix helps.

    /opt/venv/bin/python /app/voice_test/final_audio_shift_2026_07_31.py <job_dir>
"""
import glob
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import SR, _audio  # noqa: E402


def lag_ms(reference, probe, max_lag=1.0):
    a, b = _audio(reference), _audio(probe)
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    size = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
    limit = int(max_lag * SR)
    window = np.concatenate([corr[-limit:], corr[: limit + 1]])
    lags = np.arange(-limit, limit + 1)
    i = int(np.argmax(window))
    norm = np.sqrt((a ** 2).sum() * (b ** 2).sum()) + 1e-12
    return lags[i] * 1000.0 / SR, float(window[i] / norm)


def dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True).stdout.strip()
    return float(out or 0.0)


def main(job_dir):
    master = glob.glob(os.path.join(job_dir, "*_voice.mp3"))[0]
    final = glob.glob(os.path.join(job_dir, "*_final*.mp4"))
    final = [f for f in final if "_v2" not in f][0]
    lag, r = lag_ms(master, final)
    print(f"master {os.path.basename(master)} {dur(master):.3f}s")
    print(f"final  {os.path.basename(final)} {dur(final):.3f}s")
    print(f"voice in the final track vs the master: {lag:+.1f} ms (r={r:+.2f})")


if __name__ == "__main__":
    for job in sys.argv[1:]:
        main(job)
        print()

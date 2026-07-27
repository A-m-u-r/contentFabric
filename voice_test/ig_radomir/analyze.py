"""Measure the reel's subtitle cadence and what fills its pauses."""
import subprocess
import sys

import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"
FPS, SR = 30, 44100


def pcm(path):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR),
           "-f", "s16le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0


def sub_band(path):
    """Grayscale strip where the one-word subtitle lives."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf",
           f"fps={FPS},crop=720:110:0:880,scale=180:28,format=gray",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    n = len(raw) // (180 * 28)
    return np.frombuffer(raw[: n * 180 * 28], dtype=np.uint8).reshape(n, 28, 180).astype(np.float64)


a = pcm(PATH)
hop = int(SR * 0.05)
rms = np.array([np.sqrt(np.mean(a[i:i + hop] ** 2)) for i in range(0, len(a) - hop, hop)])
db = 20 * np.log10(np.maximum(rms, 1e-9))
print(f"audio: {len(a)/SR:.2f}s, 50ms windows: {len(db)}")
print(f"  loudest window {db.max():+.1f} dB, quietest {db.min():+.1f} dB")
for thr in (-40, -35, -30, -25):
    print(f"  windows below {thr} dB: {(db < thr).sum()} ({(db < thr).mean()*100:.1f}%)")

quiet = np.argsort(db)[:6]
print("  quietest windows at:", ", ".join(f"{i*0.05:.2f}s ({db[i]:+.1f})" for i in sorted(quiet)))

# what lives in the quietest window: tonal (music) or broadband (room)?
i = int(quiet[0]) * hop
seg = a[i:i + int(SR * 0.25)]
if len(seg) > 1024:
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freq = np.fft.rfftfreq(len(seg), 1 / SR)
    band = lambda lo, hi: 20 * np.log10(max(np.mean(spec[(freq >= lo) & (freq < hi)]), 1e-9))
    print("  quiet-window spectrum:",
          ", ".join(f"{lo}-{hi}Hz {band(lo,hi):+.0f}dB" for lo, hi in
                    [(20, 120), (120, 400), (400, 2000), (2000, 6000), (6000, 16000)]))
    peak = freq[np.argmax(spec)]
    print(f"  strongest tone in quiet window: {peak:.0f} Hz")

f = sub_band(PATH)
diff = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
thr = max(diff.mean() * 1.6, 1.2)
changes = [i for i in range(1, len(diff) - 1)
           if diff[i] > thr and diff[i] >= diff[i - 1] and diff[i] > diff[i + 1]]
gaps = np.diff(changes) / FPS
print(f"\nsubtitle strip: {len(f)} frames, change threshold {thr:.2f}")
print(f"  word changes detected: {len(changes)}")
if len(gaps):
    print(f"  gap between words: median {np.median(gaps)*1000:.0f} ms, "
          f"p10 {np.percentile(gaps,10)*1000:.0f} ms, p90 {np.percentile(gaps,90)*1000:.0f} ms")
    print(f"  implied tempo: {len(changes)/(len(f)/FPS)*60:.0f} words/min")

ink = (f > 200).sum(axis=(1, 2))
print(f"  frames with bright text pixels: {(ink > 3).mean()*100:.0f}% of the clip")

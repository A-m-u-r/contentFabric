"""Do his cuts land on phrase boundaries, or mid-word?"""
import subprocess

import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"
FPS, SR = 30, 16000
CUTS = [2.2, 4.433, 7.2, 11.9, 20.067, 26.467, 31.167, 34.133,
        38.467, 44.6, 50.133, 55.333, 61.533, 68.7, 70.0]


def gray(vf, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", PATH, "-vf", vf, "-f", "rawvideo", "-"],
                         check=True, capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float64)


strip = gray(f"fps={FPS},crop=720:110:0:880,scale=240:36,format=gray", 240, 36)
d = np.abs(np.diff(strip, axis=0)).mean(axis=(1, 2))
thr = np.median(d) + 3 * np.median(np.abs(d - np.median(d))) + 0.5
peaks = [i for i in range(1, len(d) - 1) if d[i] > thr and d[i] >= d[i - 1] and d[i] > d[i + 1]]
swaps, last = [], -99
for p in peaks:
    if p - last > 4:
        swaps.append(p / FPS)
    last = p
swaps = np.array(swaps)

pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", PATH, "-vn", "-ac", "1", "-ar", str(SR),
                      "-f", "s16le", "-"], check=True, capture_output=True).stdout
a = np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768.0
hop = SR // 100                                   # 10 ms
rms = np.array([np.sqrt(np.mean(a[i:i + hop] ** 2)) for i in range(0, len(a) - hop, hop)])
db = 20 * np.log10(np.maximum(rms, 1e-9))
loud = db > (db.max() - 26)                       # speech present

print("cut  -> nearest word swap | audio level at the cut | in speech?")
near, in_speech = [], 0
for c in CUTS:
    k = int(c * 100)
    dist = float(np.min(np.abs(swaps - c))) if len(swaps) else float("nan")
    lvl = db[min(k, len(db) - 1)]
    spoken = bool(loud[min(k, len(loud) - 1)])
    in_speech += spoken
    near.append(dist)
    print(f"{c:6.2f}s -> {dist*1000:5.0f} ms      | {lvl:+6.1f} dB          | {'yes' if spoken else 'no'}")
print(f"\nmedian cut-to-word distance: {np.median(near)*1000:.0f} ms")
print(f"cuts landing while he is speaking: {in_speech}/{len(CUTS)}")

# how long is the longest true pause anywhere in the track?
quiet_runs, run = [], 0
for v in loud:
    if not v:
        run += 1
    else:
        if run:
            quiet_runs.append(run / 100)
        run = 0
quiet_runs.sort(reverse=True)
print(f"longest pauses in the voiceover (s): {[round(x,2) for x in quiet_runs[:6]]}")
print(f"pauses >0.4s: {sum(1 for x in quiet_runs if x > 0.4)}, total quiet {sum(quiet_runs):.1f}s of {len(loud)/100:.1f}s")

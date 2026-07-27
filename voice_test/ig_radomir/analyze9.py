"""Hard cut or a short dissolve? Look at the frame-diff profile around each cut."""
import subprocess

import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"
FPS = 30
CUTS = [2.2, 4.433, 7.2, 11.9, 20.067, 26.467, 31.167, 34.133,
        38.467, 44.6, 50.133, 55.333, 61.533, 68.7, 70.0]
W, H = 90, 160

raw = subprocess.run(["ffmpeg", "-v", "error", "-i", PATH, "-vf",
                      f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                     check=True, capture_output=True).stdout
n = len(raw) // (W * H)
f = np.frombuffer(raw[: n * W * H], dtype=np.uint8).reshape(n, H, W).astype(np.float32)
d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
print(f"{n} frames, baseline frame-to-frame |diff|: median {np.median(d):.2f}")
print("\ncut      diff profile around the cut (frames -3..+3)         spread")
for c in CUTS:
    k = int(round(c * FPS))
    win = d[max(0, k - 4):k + 3]
    peak = win.max()
    big = int((win > peak * 0.35).sum())
    print(f"{c:6.2f}s  " + " ".join(f"{v:5.1f}" for v in win) +
          f"   peak {peak:5.1f}, frames>35% of peak: {big}")

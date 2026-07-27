"""Word cadence (clustered) and whether each shot carries a slow push-in."""
import subprocess

import cv2
import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"
FPS = 30


def gray(vf, w, h):
    cmd = ["ffmpeg", "-v", "error", "-i", PATH, "-vf", vf, "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float64)


# --- word changes, clustering peaks that belong to one swap ---
strip = gray(f"fps={FPS},crop=720:110:0:880,scale=240:36,format=gray", 240, 36)
d = np.abs(np.diff(strip, axis=0)).mean(axis=(1, 2))
thr = np.median(d) + 3 * np.median(np.abs(d - np.median(d))) + 0.5
peaks = [i for i in range(1, len(d) - 1) if d[i] > thr and d[i] >= d[i - 1] and d[i] > d[i + 1]]
events, last = [], -99
for p in peaks:
    if p - last > 4:          # >133 ms apart = a new swap
        events.append(p)
    last = p
gaps = np.diff(events) / FPS
print(f"subtitle swaps: {len(events)} over {len(strip)/FPS:.1f}s -> "
      f"{len(events)/(len(strip)/FPS)*60:.0f} words/min")
print(f"  word on screen: median {np.median(gaps)*1000:.0f} ms, "
      f"p10 {np.percentile(gaps,10)*1000:.0f}, p90 {np.percentile(gaps,90)*1000:.0f}")

# --- push-in test: best matching scale between the start and the end of a shot ---
def frame(t):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", PATH, "-frames:v", "1",
           "-vf", "format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw[: 720 * 1280], dtype=np.uint8).reshape(1280, 720).astype(np.float32)


def best_scale(t0, t1, region=(0, 0, 720, 420)):
    x, y, w, h = region
    a = frame(t0)[y:y + h, x:x + w]
    b = frame(t1)
    out = []
    for s in np.arange(0.90, 1.101, 0.01):
        big = cv2.resize(b, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        cy, cx = big.shape[0] / 2, big.shape[1] / 2
        oy = int(cy - 1280 / 2 * 1 + y * 1)
        ox = int(cx - 720 / 2 + x)
        crop = big[oy:oy + h, ox:ox + w]
        if crop.shape != a.shape:
            continue
        out.append((float(np.abs(a - crop).mean()), round(float(s), 2)))
    out.sort()
    return out[:3]


for label, (t0, t1) in {
    "shot 11.9-20.1 (A, 8.2s)": (12.2, 19.7),
    "shot 20.1-26.5 (B, 6.4s)": (20.4, 26.1),
    "shot 61.5-68.7 (B, 7.2s)": (61.8, 68.4),
    "shot 44.6-50.1 (A, 5.5s)": (44.9, 49.8),
}.items():
    print(f"{label}: best scale (end vs start) -> " +
          ", ".join(f"x{s} (err {e:.2f})" for e, s in best_scale(t0, t1)))

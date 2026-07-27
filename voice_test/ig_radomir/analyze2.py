"""Count subtitle words properly and look for generation drift across shots."""
import subprocess

import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"
FPS = 30
CUTS = [0.0, 2.2, 4.433, 7.2, 11.9, 20.067, 26.467, 31.167, 34.133,
        38.467, 44.6, 50.133, 55.333, 61.533, 68.7, 70.0, 72.333]
ANGLE = "ABABABABABABABAA"  # read off the frame montage


def gray(vf, w, h, path=PATH, extra=()):
    cmd = ["ffmpeg", "-v", "error", *extra, "-i", path, "-vf", vf, "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float64)


# --- subtitle words: a word is a run of frames with bright text present ---
strip = gray(f"fps={FPS},crop=720:110:0:880,scale=240:36,format=gray", 240, 36)
ink = (strip > 205).sum(axis=(1, 2))
present = ink > 6
runs, start = [], None
for i, p in enumerate(present):
    if p and start is None:
        start = i
    elif not p and start is not None:
        runs.append((start, i))
        start = None
if start is not None:
    runs.append((start, len(present)))
runs = [(a, b) for a, b in runs if b - a >= 2]
hold = np.array([(b - a) / FPS for a, b in runs])
gap = np.array([(runs[i + 1][0] - runs[i][1]) / FPS for i in range(len(runs) - 1)])
print(f"subtitle runs (= words on screen): {len(runs)}")
print(f"  on-screen hold: median {np.median(hold)*1000:.0f} ms, "
      f"p10 {np.percentile(hold,10)*1000:.0f}, p90 {np.percentile(hold,90)*1000:.0f}")
print(f"  blank between words: median {np.median(gap)*1000:.0f} ms, p90 {np.percentile(gap,90)*1000:.0f}")
print(f"  words/min: {len(runs)/(len(strip)/FPS)*60:.0f}")
print(f"  text on screen {present.mean()*100:.0f}% of the time")
print(f"  words visible at once: max ink {ink.max()} px, median when present {np.median(ink[present]):.0f} px")

# --- drift: same-angle background across shots vs inside one shot ---
top = gray(f"fps=2,crop=720:260:0:0,scale=180:65,format=gray", 180, 65)
def at(t):
    return top[min(int(t * 2), len(top) - 1)]

a_shots = [(CUTS[i], CUTS[i + 1]) for i in range(len(ANGLE)) if ANGLE[i] == "A"]
b_shots = [(CUTS[i], CUTS[i + 1]) for i in range(len(ANGLE)) if ANGLE[i] == "B"]
inside = [np.abs(at(s + 0.5) - at(min(e - 0.5, s + 1.5))).mean() for s, e in a_shots if e - s > 2.2]
print(f"\nbackground strip, inside one A shot (0.5s->1.5s): mean |diff| {np.mean(inside):.2f}")
print("across A shots:")
for i in range(len(a_shots) - 1):
    s1, s2 = a_shots[i], a_shots[i + 1]
    d = np.abs(at(s1[0] + 0.5) - at(s2[0] + 0.5)).mean()
    print(f"  A@{s1[0]:5.1f}s vs A@{s2[0]:5.1f}s: {d:5.2f}")
first_last = np.abs(at(a_shots[0][0] + 0.5) - at(a_shots[-1][0] + 0.5)).mean()
print(f"  first A vs last A ({a_shots[0][0]:.1f}s -> {a_shots[-1][0]:.1f}s): {first_last:.2f}")
print(f"\nshot lengths: " + " ".join(f"{CUTS[i+1]-CUTS[i]:.1f}" for i in range(len(ANGLE))))
print(f"A time {sum(e-s for s,e in a_shots):.1f}s in {len(a_shots)} shots, "
      f"B time {sum(e-s for s,e in b_shots):.1f}s in {len(b_shots)} shots")

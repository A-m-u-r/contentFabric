"""Do same-angle shots resume a pose, or reset to the reference still?"""
import subprocess

import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"
CUTS = [0.0, 2.2, 4.433, 7.2, 11.9, 20.067, 26.467, 31.167, 34.133,
        38.467, 44.6, 50.133, 55.333, 61.533, 68.7, 70.0, 72.333]
ANGLE = "ABABABABABABABAA"


def frame(t):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", PATH, "-frames:v", "1",
           "-vf", "format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw[: 720 * 1280], dtype=np.uint8).reshape(1280, 720).astype(np.float32)


HANDS = (slice(820, 1140), slice(0, 720))    # arms / desk
FACE = (slice(150, 620), slice(140, 620))

def diff(a, b, roi):
    return float(np.abs(a[roi] - b[roi]).mean())


shots = [(CUTS[i], CUTS[i + 1], ANGLE[i]) for i in range(len(ANGLE))]
cache = {}
def f(t):
    if t not in cache:
        cache[t] = frame(t)
    return cache[t]

for tag in ("A", "B"):
    sel = [s for s in shots if s[2] == tag and s[1] - s[0] > 2.0]
    sel = [s for s in sel if s[0] not in (0.0, 70.0)]     # skip the wide opener and the CTA card
    print(f"--- angle {tag}: {len(sel)} shots ---")
    inside = [diff(f(s + 0.10), f(s + 1.10), HANDS) for s, e, _ in sel]
    print(f"  arms move inside one shot (0.1s -> 1.1s): mean {np.mean(inside):.2f}")
    firsts = [diff(f(sel[i][0] + 0.10), f(sel[j][0] + 0.10), HANDS)
              for i in range(len(sel)) for j in range(i + 1, len(sel))]
    print(f"  arms across different shots, both at 0.1s: mean {np.mean(firsts):.2f} "
          f"(min {min(firsts):.2f}, max {max(firsts):.2f})")
    faces = [diff(f(sel[i][0] + 0.10), f(sel[j][0] + 0.10), FACE)
             for i in range(len(sel)) for j in range(i + 1, len(sel))]
    print(f"  face across different shots, both at 0.1s: mean {np.mean(faces):.2f}")

# is shot 1 a wider framing than the other A shots?
print("\nopener vs the standard A framing (whole frame |diff|):")
print(f"  0.3s vs 4.9s: {diff(f(0.3), f(4.9), (slice(0,1280), slice(0,720))):.2f}")
print(f"  4.9s vs 12.4s: {diff(f(4.9), f(12.4), (slice(0,1280), slice(0,720))):.2f}")

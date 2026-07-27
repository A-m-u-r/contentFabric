"""Where do the zooms live: inside a shot, or as a step at each cut?"""
import subprocess

import cv2
import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"
CUTS = [0.0, 2.2, 4.433, 7.2, 11.9, 20.067, 26.467, 31.167, 34.133,
        38.467, 44.6, 50.133, 55.333, 61.533, 68.7, 70.0, 72.333]
ANGLE = "ABABABABABABABAA"
orb = cv2.ORB_create(8000)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def frame(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", PATH,
                          "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw[: 720 * 1280], dtype=np.uint8).reshape(1280, 720).copy()


def sim(a, b, mask_person=True):
    mask = np.full(a.shape, 255, np.uint8)
    if mask_person:
        mask[260:1280, 40:680] = 0
    k1, d1 = orb.detectAndCompute(a, mask)
    k2, d2 = orb.detectAndCompute(b, mask)
    if d1 is None or d2 is None or len(k1) < 12 or len(k2) < 12:
        return None
    m = sorted(bf.match(d1, d2), key=lambda x: x.distance)[:600]
    if len(m) < 12:
        return None
    p1 = np.float32([k1[x.queryIdx].pt for x in m]).reshape(-1, 1, 2)
    p2 = np.float32([k2[x.trainIdx].pt for x in m]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=1.0,
                                         maxIters=8000, confidence=0.999)
    if M is None or inl is None or inl.sum() < 12:
        return None
    return float(np.hypot(M[0, 0], M[1, 0])), float(M[0, 2]), float(M[1, 2]), int(inl.sum())


shots = [(CUTS[i], CUTS[i + 1], ANGLE[i]) for i in range(len(ANGLE))]
print("=== inside each shot (first vs last frame) ===")
for s, e, ang in shots:
    if e - s < 1.6:
        continue
    r = sim(frame(s + 0.15), frame(e - 0.15))
    if r:
        print(f"{ang} {s:5.1f}-{e:5.1f}s  x{r[0]:.4f}  pan({r[1]:+.0f},{r[2]:+.0f})  inl {r[3]}")
    else:
        print(f"{ang} {s:5.1f}-{e:5.1f}s  (no fit)")

print("\n=== step at the cut: each shot vs the previous shot of the same angle ===")
for ang in "AB":
    sel = [(s, e) for s, e, a in shots if a == ang and e - s > 1.6]
    print(f"-- angle {ang} --")
    cum = 1.0
    for i in range(len(sel) - 1):
        a = frame(sel[i][0] + 0.4)
        b = frame(sel[i + 1][0] + 0.4)
        r = sim(a, b)
        if not r:
            print(f"  {sel[i][0]:5.1f} -> {sel[i+1][0]:5.1f}: no fit")
            continue
        cum *= r[0]
        print(f"  {sel[i][0]:5.1f} -> {sel[i+1][0]:5.1f}s: x{r[0]:.4f} "
              f"pan({r[1]:+.0f},{r[2]:+.0f}) inl {r[3]}   cumulative x{cum:.4f}")

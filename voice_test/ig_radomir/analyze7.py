"""Measure the real scale change inside each shot from background features."""
import subprocess

import cv2
import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"
CUTS = [0.0, 2.2, 4.433, 7.2, 11.9, 20.067, 26.467, 31.167, 34.133,
        38.467, 44.6, 50.133, 55.333, 61.533, 68.7, 70.0, 72.333]
ANGLE = "ABABABABABABABAA"


def frame(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", PATH,
                          "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw[: 720 * 1280], dtype=np.uint8).reshape(1280, 720).copy()


orb = cv2.ORB_create(4000)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def scale_between(a, b):
    """Similarity transform from background keypoints (person masked out)."""
    mask = np.full(a.shape, 255, np.uint8)
    mask[300:1280, 60:660] = 0          # drop the speaker, keep walls/shelves/desk edges
    k1, d1 = orb.detectAndCompute(a, mask)
    k2, d2 = orb.detectAndCompute(b, mask)
    if d1 is None or d2 is None:
        return None
    m = sorted(bf.match(d1, d2), key=lambda x: x.distance)[:400]
    if len(m) < 12:
        return None
    p1 = np.float32([k1[x.queryIdx].pt for x in m]).reshape(-1, 1, 2)
    p2 = np.float32([k2[x.trainIdx].pt for x in m]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=1.5)
    if M is None:
        return None
    s = float(np.sqrt(M[0, 0] ** 2 + M[1, 0] ** 2))
    return s, float(M[0, 2]), float(M[1, 2]), int(inl.sum()), len(m)


print("shot                 scale(end/start)  per second   pan px      inliers")
for i in range(len(ANGLE)):
    s0, s1 = CUTS[i], CUTS[i + 1]
    if s1 - s0 < 1.6:
        continue
    a, b = frame(s0 + 0.25), frame(s1 - 0.25)
    r = scale_between(a, b)
    dur = (s1 - 0.25) - (s0 + 0.25)
    if not r:
        print(f"{ANGLE[i]} {s0:5.1f}-{s1:5.1f}s      no match")
        continue
    s, tx, ty, inl, tot = r
    print(f"{ANGLE[i]} {s0:5.1f}-{s1:5.1f}s      x{s:.4f}        {(s-1)/dur*100:+.2f}%/s   "
          f"({tx:+.0f},{ty:+.0f})   {inl}/{tot}")

print("\nsanity: two frames 1/30s apart inside one shot")
a, b = frame(13.0), frame(13.033)
r = scale_between(a, b)
print(f"  x{r[0]:.4f}, inliers {r[3]}/{r[4]}")
print("sanity: same-angle frames from different shots (should be ~1.0 if the plate is fixed)")
for t0, t1 in [(12.4, 45.0), (21.0, 31.6)]:
    r = scale_between(frame(t0), frame(t1))
    print(f"  {t0}s vs {t1}s: x{r[0]:.4f}, pan ({r[1]:+.0f},{r[2]:+.0f}), inliers {r[3]}/{r[4]}")

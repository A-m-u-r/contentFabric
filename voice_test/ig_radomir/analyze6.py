"""Is the close angle a digital zoom of the wide one, or a separate setup?"""
import subprocess

import cv2
import numpy as np

PATH = "/app/voice_test/ig_radomir/reel_213k.mp4"


def frame(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", PATH,
                          "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw[: 720 * 1280], dtype=np.uint8).reshape(1280, 720).astype(np.float32)


wide, close = frame(12.4), frame(21.0)
best = []
for s in np.arange(1.05, 2.61, 0.05):
    big = cv2.resize(wide, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    if big.shape[0] < 1280 or big.shape[1] < 720:
        continue
    # slide the 720x1280 window over the upscaled wide frame, coarse grid
    step = 60
    for oy in range(0, big.shape[0] - 1280 + 1, step):
        for ox in range(0, big.shape[1] - 720 + 1, step):
            crop = big[oy:oy + 1280, ox:ox + 720]
            best.append((float(np.abs(crop - close).mean()), round(float(s), 2), ox, oy))
best.sort()
print("best zoom-and-crop match of the WIDE frame onto the CLOSE frame:")
for e, s, ox, oy in best[:5]:
    print(f"  scale x{s} offset ({ox},{oy}) -> mean |diff| {e:.1f}")
b1, b2 = frame(21.0), frame(31.6)
print(f"\nreference: two CLOSE frames from different shots differ by {np.abs(b1-b2).mean():.1f}")
w1, w2 = frame(12.4), frame(45.0)
print(f"reference: two WIDE frames from different shots differ by  {np.abs(w1-w2).mean():.1f}")

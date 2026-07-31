"""Does the edit put each paid clip exactly where its audio is?

Same picture, two places: the clip file and the finished reel. Mouth openness is
crop- and zoom-invariant, so correlating the two curves finds any shift the
assembly introduced, independent of how well the model lip-synced.

Slot bounds come from the shots the job archived, not from the length of the
slice mp3 — an mp3 is ~30 ms longer than the window it was cut from, and using
it as the slot walks the cursor forward a frame per shot.

    /opt/venv/bin/python /app/voice_test/assembly_shift_2026_07_31.py <job_dir>
"""
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import FPS, _fill_gaps, _frames, mouth_openness  # noqa: E402

HEAD = 1105 / 44100.0  # what the composite skips on a lip-synced clip


def dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True).stdout.strip()
    return float(out or 0.0)


def curve(path, start=None, length=None):
    return _fill_gaps(mouth_openness(_frames(path, start, length)))


def align(a, b, max_lag=12):
    """Sub-frame lag of b relative to a, in ms, by parabolic peak fit."""
    n = min(len(a), len(b))
    table = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x, y = a[: n - lag], b[lag:n]
        else:
            x, y = a[-lag:n], b[: n + lag]
        if len(x) < 10:
            continue
        x = (x - x.mean()) / (x.std() + 1e-12)
        y = (y - y.mean()) / (y.std() + 1e-12)
        table.append((lag, float(np.corrcoef(x, y)[0, 1])))
    lags = np.array([t[0] for t in table], dtype=float)
    corrs = np.array([t[1] for t in table])
    i = int(np.argmax(corrs))
    lag = lags[i]
    if 0 < i < len(corrs) - 1:
        y0, y1, y2 = corrs[i - 1], corrs[i], corrs[i + 1]
        denom = y0 - 2 * y1 + y2
        if denom:
            lag += -0.5 * (y2 - y0) / denom
    return lag * 1000.0 / FPS, corrs[i]


def bounds(job_dir):
    meta = os.path.join(job_dir, "gallery_metadata.json")
    data = json.load(open(meta, encoding="utf-8"))
    shots = data.get("shots") or data.get("storyboard_shots") or []
    return {int(s["shot_number"]): (float(s["start"]), float(s["end"]))
            for s in shots if s.get("start") is not None}


def main(job_dir):
    clips = sorted(glob.glob(os.path.join(job_dir, "*_avatar_[0-9][0-9].mp4")))
    slug = os.path.basename(clips[0]).rsplit("_avatar_", 1)[0]
    final = os.path.join(job_dir, f"{slug}_storyboard_final.mp4")
    slots = bounds(job_dir)

    print(f"master  {dur(os.path.join(job_dir, f'{slug}_voice.mp3')):.3f}s   "
          f"final {dur(final):.3f}s   last shot ends {max(e for _, e in slots.values()):.3f}s\n")
    for path in clips:
        index = int(re.search(r"_(\d\d)\.mp4$", path).group(1))
        if index not in slots:
            continue
        start, end = slots[index]
        window = end - start
        a = curve(path, HEAD, window)
        b = curve(final, start, window)
        if a is None or b is None:
            print(f"[{index:02d}] no face")
            continue
        lag, r = align(a, b)
        print(f"[{index:02d}] slot {start:6.3f}-{end:6.3f} ({window:.3f}s)  "
              f"clip file {dur(path):.3f}s  ->  picture in the reel is "
              f"{lag:+6.1f} ms off (r={r:+.3f})")


if __name__ == "__main__":
    main(sys.argv[1])

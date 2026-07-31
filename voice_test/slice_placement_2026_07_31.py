"""Is the audio a take was lip-synced against the audio that plays over it?

Each slice is located inside the master track by correlation and the position is
compared with the slot the shot was given. A slice that does not sit where its
clip plays means the picture was synced to words the viewer never hears there.

    /opt/venv/bin/python /app/voice_test/slice_placement_2026_07_31.py <job_dir> ...
"""
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import SR, _audio  # noqa: E402

LAME_HEAD = 1105 / 44100.0


def locate(master_pcm, piece_pcm):
    """Where the piece sits inside the master, in seconds, plus its match quality."""
    n = len(master_pcm)
    size = 1 << int(np.ceil(np.log2(n + len(piece_pcm))))
    corr = np.fft.irfft(np.fft.rfft(master_pcm, size) * np.conj(np.fft.rfft(piece_pcm, size)), size)
    corr = corr[:n]
    i = int(np.argmax(corr))
    energy = np.sqrt((piece_pcm ** 2).sum() * (master_pcm[i:i + len(piece_pcm)] ** 2).sum()) + 1e-12
    return i / SR, float(corr[i] / energy)


def main(job_dir):
    master_path = glob.glob(os.path.join(job_dir, "*_voice.mp3"))[0]
    slug = os.path.basename(master_path)[: -len("_voice.mp3")]
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    shots = meta.get("shots") or meta.get("storyboard_shots") or []
    slots = {int(s["shot_number"]): (float(s["start"]), float(s["end"]))
             for s in shots if s.get("start") is not None}
    master = _audio(master_path)
    print(f"{os.path.basename(job_dir)}  master {len(master) / SR:.3f}s")
    for path in sorted(glob.glob(os.path.join(job_dir, f"{slug}_slice_[0-9][0-9].mp3"))):
        index = int(re.search(r"_(\d\d)\.mp3$", path).group(1))
        piece = _audio(path)
        # ffmpeg drops the LAME head when decoding, so the piece starts clean.
        found, r = locate(master, piece)
        start, end = slots.get(index, (float("nan"), float("nan")))
        print(f"  slice {index:02d}: sits at {found:6.3f}s, shot slot starts {start:6.3f}s "
              f"-> {(found - start) * 1000:+6.0f} ms (match r={r:+.2f}, len {len(piece) / SR:.3f}s "
              f"vs slot {end - start:.3f}s)")


if __name__ == "__main__":
    for job in sys.argv[1:]:
        main(job)
        print()

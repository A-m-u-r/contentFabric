"""Каждая плашка против начала фразы в конкретном файле.

    /opt/venv/bin/python /app/voice_test/caption_check_2026_07_31.py <subs.ass> <media>
"""
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from verify_glued_reel_2026_07_31 import captions, onsets  # noqa: E402
from lip_open_probe import _audio  # noqa: E402


def main(ass, media):
    starts = onsets(_audio(media))
    print(f"{media.split('/')[-1]}: {len(starts)} начал фраз")
    for c_start, word in captions(ass):
        near = starts[np.argmin(np.abs(starts - c_start))]
        delta = (c_start - near) * 1000
        mark = f"{delta:+5.0f} мс" if abs(delta) <= 400 else "внутри фразы"
        print(f"  {c_start:6.2f}  {word:<20} {mark}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

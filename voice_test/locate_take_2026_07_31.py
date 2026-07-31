"""Where does a take's own audio actually sit inside an assembled reel?

    /opt/venv/bin/python /app/voice_test/locate_take_2026_07_31.py <reel.mp4> <take.mp4> ...
"""
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import SR, _audio  # noqa: E402


def locate(haystack, needle):
    n = len(haystack)
    size = 1 << int(np.ceil(np.log2(n + len(needle))))
    corr = np.fft.irfft(np.fft.rfft(haystack, size) * np.conj(np.fft.rfft(needle, size)), size)[:n]
    i = int(np.argmax(corr))
    energy = np.sqrt((needle ** 2).sum() * (haystack[i:i + len(needle)] ** 2).sum()) + 1e-12
    return i / SR, float(corr[i] / energy)


def main(reel, takes):
    haystack = _audio(reel)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", reel],
                         capture_output=True, text=True).stdout.strip()
    print(f"reel {reel.split('/')[-1]} {float(dur):.3f}s "
          f"(decoded audio {len(haystack) / SR:.3f}s)")
    for take in takes:
        needle = _audio(take)
        # The padded tail is silence and only blurs the peak.
        voiced = np.where(np.abs(needle) > np.abs(needle).max() * 0.02)[0]
        if len(voiced):
            needle = needle[voiced[0]:voiced[-1]]
            head = voiced[0] / SR
        else:
            head = 0.0
        at, r = locate(haystack, needle)
        print(f"  {take.split('/')[-1]}: speech starts at {at:.3f}s in the reel "
              f"(take's own head {head:.3f}s -> take starts {at - head:.3f}s), r={r:+.2f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])

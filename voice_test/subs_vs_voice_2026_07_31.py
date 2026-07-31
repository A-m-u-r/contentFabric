"""Do the burned-in captions land on the words the viewer hears?

Word-by-word captions are read, not glanced at: if they run ahead of the voice
the whole reel feels out of sync even when the mouth is right. Each caption's
start is compared with the nearest real speech onset in the master track.

Also prints the shot slots against the caption timeline, so a slot that cuts a
sentence in half is visible.

    /opt/venv/bin/python /app/voice_test/subs_vs_voice_2026_07_31.py <job_dir>
"""
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import SR, _audio  # noqa: E402

STEP = 0.01  # 10 ms envelope


def captions(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        start, end, text = parts[1], parts[2], parts[9]
        def secs(t):
            h, m, s = t.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        word = re.sub(r"\{[^}]*\}", "", text).strip()
        out.append((secs(start), secs(end), word))
    return out


def onsets(pcm, floor_frac=0.06, gap=0.12):
    hop = int(SR * STEP)
    env = np.array([np.sqrt(np.mean(pcm[i * hop:(i + 1) * hop] ** 2) + 1e-12)
                    for i in range(len(pcm) // hop)])
    thr = env.max() * floor_frac
    loud = env > thr
    found = []
    quiet_for = int(gap / STEP)
    run = quiet_for
    for i, is_loud in enumerate(loud):
        if is_loud:
            if run >= quiet_for:
                found.append(i * STEP)
            run = 0
        else:
            run += 1
    return np.array(found), env, thr


def main(job_dir):
    ass = glob.glob(os.path.join(job_dir, "*_subs.ass"))[0]
    master = glob.glob(os.path.join(job_dir, "*_voice.mp3"))[0]
    caps = captions(ass)
    pcm = _audio(master)
    starts, env, thr = onsets(pcm)

    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    shots = meta.get("shots") or []
    print("shot slots:")
    for s in shots:
        print(f"  {int(s['shot_number']):02d} {s.get('visual_type', ''):8s} "
              f"{float(s['start']):6.2f}-{float(s['end']):6.2f}  {(s.get('speech') or '')[:60]}")

    print(f"\n{len(caps)} captions, {len(starts)} speech onsets in the master\n")
    diffs = []
    for c_start, c_end, word in caps:
        near = starts[np.argmin(np.abs(starts - c_start))] if len(starts) else float("nan")
        d = (c_start - near) * 1000
        # Only pair a caption with an onset it can plausibly belong to.
        if abs(d) <= 400:
            diffs.append(d)
            print(f"  {c_start:6.2f}-{c_end:6.2f}  {word:<18} nearest onset {near:6.2f} "
                  f"-> caption {d:+5.0f} ms")
        else:
            print(f"  {c_start:6.2f}-{c_end:6.2f}  {word:<18} (no onset within 400 ms — "
                  f"mid-phrase word)")
    if diffs:
        print(f"\ncaption vs speech onset: median {np.median(diffs):+.0f} ms, "
              f"mean {np.mean(diffs):+.0f} ms, n={len(diffs)}")
        print("positive = caption appears after the sound, negative = before it")


if __name__ == "__main__":
    main(sys.argv[1])

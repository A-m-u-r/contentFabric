"""Check a reel assembled from takes-as-delivered.

Three things have to hold:
  * every self-voiced take plays in the reel exactly as it came back (picture
    and its own sound, no relative shift);
  * b-roll still carries the right window of the master voiceover;
  * the captions, re-stamped onto the new timeline, still land on the words.

    /opt/venv/bin/python /app/voice_test/verify_glued_reel_2026_07_31.py <job_dir> <reel.mp4>
"""
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/voice_test")
import saasshorts  # noqa: E402
from lip_open_probe import FPS, SR, _audio, _fill_gaps, _frames, mouth_openness  # noqa: E402


def cut_audio(path, start, duration):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path, "-t", f"{duration:.3f}",
         "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def lag_ms(a, b, max_lag=0.6):
    n = min(len(a), len(b))
    if n < SR // 4:
        return None, 0.0
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    size = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
    limit = int(max_lag * SR)
    window = np.concatenate([corr[-limit:], corr[: limit + 1]])
    i = int(np.argmax(window))
    norm = np.sqrt((a ** 2).sum() * (b ** 2).sum()) + 1e-12
    return (np.arange(-limit, limit + 1)[i]) * 1000.0 / SR, float(window[i] / norm)


def mouth_lag(clip, reel, reel_start, duration, head=0.0):
    a = _fill_gaps(mouth_openness(_frames(clip, head, duration)))
    b = _fill_gaps(mouth_openness(_frames(reel, reel_start, duration)))
    if a is None or b is None:
        return None, 0.0
    n = min(len(a), len(b))
    best = (None, -2.0)
    for lag in range(-10, 11):
        if lag >= 0:
            x, y = a[: n - lag], b[lag:n]
        else:
            x, y = a[-lag:n], b[: n + lag]
        if len(x) < 10:
            continue
        x = (x - x.mean()) / (x.std() + 1e-12)
        y = (y - y.mean()) / (y.std() + 1e-12)
        r = float(np.corrcoef(x, y)[0, 1])
        if r > best[1]:
            best = (lag, r)
    return best[0] * 1000.0 / FPS, best[1]


def captions(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        def secs(t):
            h, m, rest = t.split(":")
            return int(h) * 3600 + int(m) * 60 + float(rest)
        out.append((secs(parts[1]), re.sub(r"\{[^}]*\}", "", parts[9]).strip()))
    return out


def onsets(pcm, floor_frac=0.06, gap=0.12):
    hop = int(SR * 0.01)
    env = np.array([np.sqrt(np.mean(pcm[i * hop:(i + 1) * hop] ** 2) + 1e-12)
                    for i in range(len(pcm) // hop)])
    thr = env.max() * floor_frac
    found, quiet = [], int(gap / 0.01)
    run = quiet
    for i, loud in enumerate(env > thr):
        if loud:
            if run >= quiet:
                found.append(i * 0.01)
            run = 0
        else:
            run += 1
    return np.array(found)


def main(job_dir, reel):
    master = glob.glob(os.path.join(job_dir, "*_voice.mp3"))[0]
    slug = os.path.basename(master)[: -len("_voice.mp3")]
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    shots = sorted(meta["shots"], key=lambda s: int(s["shot_number"]))

    clips = []
    for shot in shots:
        n = int(shot["shot_number"])
        talking = os.path.join(job_dir, f"{slug}_avatar_{n:02d}.mp4")
        broll = os.path.join(job_dir, f"{slug}_avatar_broll_{n:02d}.mp4")
        path = talking if os.path.exists(talking) else broll
        if not os.path.exists(path):
            continue
        slice_audio = os.path.join(job_dir, f"{slug}_slice_{n:02d}.mp3")
        clips.append({
            "path": path, "duration": float(shot["end"]) - float(shot["start"]),
            "shot": shot, "audio_slice": slice_audio if path == talking else "",
            "speech_offset": (saasshorts._mp3_encoder_delay(slice_audio)
                              if path == talking else 0.0),
        })
    layout = saasshorts._reel_layout(clips)

    for segment in layout:
        start, duration = segment["reel_start"], segment["duration"]
        reel_pcm = cut_audio(reel, start, duration)
        if segment["self_voiced"]:
            head = segment["head"]
            own = cut_audio(segment["clip"]["path"], head, duration)
            a_lag, a_r = lag_ms(own, reel_pcm)
            m_lag, m_r = mouth_lag(segment["clip"]["path"], reel, start, duration, head)
            print(f"[{segment['index'] + 1:02d}] как прислали: звук {a_lag:+.0f} мс "
                  f"(r={a_r:+.2f}), картинка {m_lag:+.0f} мс (r={m_r:+.3f})")
        else:
            window = cut_audio(master, segment["reel_start"], duration)
            a_lag, a_r = lag_ms(window, reel_pcm)
            print(f"[{segment['index'] + 1:02d}] перебивка   : звук {a_lag:+.0f} мс (r={a_r:+.2f})")

    ass = os.path.join(job_dir, f"{slug}_subs.ass")
    if os.path.exists(ass):
        starts = onsets(_audio(reel))
        diffs = []
        for c_start, word in captions(ass):
            if not len(starts):
                break
            near = starts[np.argmin(np.abs(starts - c_start))]
            if abs(c_start - near) <= 0.4:
                diffs.append((c_start - near) * 1000)
        if diffs:
            print(f"\nсубтитры против речи в ролике: медиана {np.median(diffs):+.0f} мс, "
                  f"максимум {max(abs(d) for d in diffs):.0f} мс, n={len(diffs)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

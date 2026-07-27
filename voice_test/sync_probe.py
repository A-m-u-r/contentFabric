"""Measure A/V offsets inside a finished storyboard job (no paid calls).

For each avatar shot: how far the Kling clip's embedded audio sits from the
voiceover slice it was generated from. The clip's lips follow that embedded
audio, so this offset is exactly how far the lips land from the master
voiceover in the final edit.

Sign convention everywhere: positive = the second signal happens LATER.
"""
import json
import os
import subprocess
import sys

import numpy as np

SR = 16000


def decode(path, start=None, duration=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def envelope(x, win=160):  # 10 ms frames
    e = np.abs(x)
    kernel = np.ones(win) / win
    return np.convolve(e, kernel, mode="same")


def find_shift(ref, sig, max_lag=1.0):
    """Return d (seconds) such that sig(t) ~= ref(t - d): d > 0 => sig is later."""
    a, b = envelope(ref), envelope(sig)
    a = a - a.mean()
    b = b - b.mean()
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    cc = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    lag_limit = int(max_lag * SR)
    lags = np.concatenate([np.arange(0, lag_limit + 1), np.arange(n - lag_limit, n)])
    vals = cc[lags]
    best = lags[int(np.argmax(vals))]
    if best > n // 2:
        best -= n
    peak = float(np.max(vals))
    # crude confidence: peak vs the spread of all candidate lags
    conf = peak / (np.std(vals) + 1e-9)
    return best / SR, conf


def _self_test():
    rng = np.random.default_rng(0)
    base = rng.standard_normal(SR * 2) * np.repeat(rng.random(200), SR * 2 // 200)
    shift = int(0.037 * SR)
    delayed = np.concatenate([np.zeros(shift), base])[: len(base)]
    d, _ = find_shift(base, delayed)
    assert abs(d - 0.037) < 0.005, d
    d, _ = find_shift(delayed, base)
    assert abs(d + 0.037) < 0.005, d


def media_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def freeze_report(path):
    proc = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path, "-vf", "freezedetect=n=-55dB:d=0.15",
         "-map", "0:v", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace",
    )
    return [line.strip() for line in proc.stderr.splitlines() if "freezedetect" in line]


def main(job_dir):
    _self_test()
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    shots = meta.get("shots") or []
    slug = None
    for name in sorted(os.listdir(job_dir)):
        if name.endswith("_voice_clean.mp3"):
            slug = name[: -len("_voice_clean.mp3")]
    master = os.path.join(job_dir, f"{slug}_voice_clean.mp3")
    if not os.path.exists(master):
        master = os.path.join(job_dir, f"{slug}_voice.mp3")
    master_pcm = decode(master)
    print(f"master: {os.path.basename(master)}  {len(master_pcm)/SR:.3f}s")

    final = os.path.join(job_dir, f"{slug}_storyboard_final.mp4")
    print(f"\n== final vs master voiceover ==")
    fin = decode(final)
    d, conf = find_shift(master_pcm, fin, max_lag=2.0)
    print(f"final audio vs master: {d*1000:+.0f} ms (conf {conf:.1f}), "
          f"final {len(fin)/SR:.3f}s vs master {len(master_pcm)/SR:.3f}s")
    # drift check: correlate each shot's window of the final against the master
    for shot in shots:
        s, e = float(shot["start"]), float(shot["end"])
        if e - s < 0.6:
            continue
        seg = fin[int(s * SR): int(e * SR)]
        lead = min(0.5, s)
        ref = master_pcm[int((s - lead) * SR): int((e + 0.5) * SR)]
        d, conf = find_shift(ref, seg, max_lag=lead + 0.5)
        # ref starts `lead` before the window, so a perfect match reports -lead
        rel = d + lead
        print(f"  window {s:5.2f}-{e:5.2f}s: {rel*1000:+.0f} ms (conf {conf:.1f})")

    print("\n== per-shot clip vs its voiceover slice ==")
    for index, shot in enumerate(shots, start=1):
        broll = (shot.get("visual_type") or "").lower() == "broll"
        clip = os.path.join(
            job_dir,
            f"{slug}_avatar_broll_{index:02d}.mp4" if broll else f"{slug}_avatar_{index:02d}.mp4",
        )
        sl = os.path.join(job_dir, f"{slug}_slice_{index:02d}.mp3")
        if not os.path.exists(clip):
            print(f"shot {index}: clip missing ({os.path.basename(clip)})")
            continue
        slot = float(shot["end"]) - float(shot["start"])
        vdur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=duration", "-of", "csv=p=0", clip], check=True,
            capture_output=True, text=True).stdout.strip())
        slice_pcm = decode(sl)
        master_slice = decode(master, float(shot["start"]), slot)
        d_slice, c_slice = find_shift(master_slice, slice_pcm, max_lag=0.5)
        line = (f"shot {index} ({'broll' if broll else 'talking'}): slot {slot:.3f}s  "
                f"video {vdur:.3f}s  slice {len(slice_pcm)/SR:.3f}s  "
                f"slice-vs-master {d_slice*1000:+.0f}ms (conf {c_slice:.1f})")
        try:
            clip_pcm = decode(clip)
        except subprocess.CalledProcessError:
            clip_pcm = np.array([])
        if clip_pcm.size:
            d_clip, c_clip = find_shift(slice_pcm, clip_pcm, max_lag=0.6)
            line += (f"\n    clip audio vs slice: {d_clip*1000:+.0f} ms (conf {c_clip:.1f})"
                     f"  [+ = lips late in final, - = lips early]"
                     f"  clip audio {len(clip_pcm)/SR:.3f}s")
        else:
            line += "\n    clip has no audio track"
        print(line)
        for row in freeze_report(clip):
            print(f"    {row}")


if __name__ == "__main__":
    main(sys.argv[1])

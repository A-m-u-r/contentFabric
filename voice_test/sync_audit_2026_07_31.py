"""Where does lip sync die: in the model, in the request, or in the assembly?

For one finished job it reports, per talking clip:
  * how the clip's own returned audio sits against the slice we sent (sample lag)
  * how the mouth sits against the clip's own audio (the model's own sync)
  * where the clip lands in the final edit and how the mouth sits against the
    final master track there (our assembly's sync)

Run inside the backend container:
    /opt/venv/bin/python /app/voice_test/sync_audit_2026_07_31.py <job_dir>
"""
import glob
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import (  # noqa: E402
    FPS, SR, _audio, _envelope, _fill_gaps, _frames, best_lag, mouth_openness,
)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out or 0.0)


def stream_info(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,r_frame_rate,duration,nb_frames,sample_rate",
         "-of", "default=nw=1", path],
        capture_output=True, text=True, check=True,
    ).stdout
    return out


def audio_lag(reference, probe, max_lag=1.0):
    """Lag of `probe` relative to `reference`, in ms, by full-sample correlation."""
    a = _audio(reference)
    b = _audio(probe)
    n = min(len(a), len(b))
    if n < SR // 2:
        return None, 0.0
    a = a[:n] - a[:n].mean()
    b = b[:n] - b[:n].mean()
    size = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
    limit = int(max_lag * SR)
    window = np.concatenate([corr[-limit:], corr[:limit + 1]])
    lags = np.arange(-limit, limit + 1)
    i = int(np.argmax(window))
    norm = np.sqrt((a ** 2).sum() * (b ** 2).sum()) + 1e-12
    return lags[i] * 1000.0 / SR, float(window[i] / norm)


def lip_lag(video, audio_from=None, start=None, dur=None):
    frames = _frames(video, start, dur)
    pcm = _audio(audio_from or video, start, dur)
    env = _envelope(pcm, len(frames))
    frames = frames[: len(env)]
    raw = mouth_openness(frames)
    tracked = int((~np.isnan(raw)).sum())
    mouth = _fill_gaps(raw)
    if mouth is None:
        return None, 0.0, tracked, len(frames)
    lag, r, _ = best_lag(env, mouth)
    return lag, r, tracked, len(frames)


def main(job_dir):
    clips = sorted(glob.glob(os.path.join(job_dir, "*_avatar_[0-9][0-9].mp4")))
    brolls = sorted(glob.glob(os.path.join(job_dir, "*_avatar_broll_[0-9][0-9].mp4")))
    slug = os.path.basename(clips[0]).rsplit("_avatar_", 1)[0]
    master = os.path.join(job_dir, f"{slug}_voice.mp3")
    final = os.path.join(job_dir, f"{slug}_storyboard_final.mp4")

    ordered = sorted(
        clips + brolls,
        key=lambda p: int(re.search(r"_(\d\d)\.mp4$", p).group(1)),
    )

    print(f"job      : {os.path.basename(job_dir)}")
    print(f"master   : {duration(master):.3f} s")
    if os.path.exists(final):
        print(f"final    : {duration(final):.3f} s")
    print()
    print(stream_info(ordered[0]))

    cursor = 0.0
    for path in ordered:
        index = int(re.search(r"_(\d\d)\.mp4$", path).group(1))
        broll = "_broll_" in path
        slice_mp3 = os.path.join(job_dir, f"{slug}_slice_{index:02d}.mp3")
        slot = duration(slice_mp3)
        clip_len = duration(path)
        kind = "b-roll " if broll else "talking"
        print(f"[{index:02d}] {kind}  slot {cursor:6.3f}-{cursor + slot:6.3f} "
              f"({slot:.3f}s)  clip file {clip_len:.3f}s")

        if not broll:
            lag_audio, r_audio = audio_lag(slice_mp3, path)
            if lag_audio is not None:
                print(f"      returned audio vs slice we sent: {lag_audio:+.0f} ms (r={r_audio:+.2f})")
            lag, r, tracked, frames = lip_lag(path)
            if lag is None:
                print("      mouth: no face tracked in the clip")
            else:
                print(f"      mouth vs its own audio         : {lag:+.0f} ms "
                      f"(r={r:+.2f}, face on {tracked}/{frames})")
            if os.path.exists(final):
                lag, r, tracked, frames = lip_lag(final, start=cursor, dur=slot)
                if lag is None:
                    print("      mouth in final edit: no face tracked")
                else:
                    print(f"      mouth vs FINAL master track    : {lag:+.0f} ms "
                          f"(r={r:+.2f}, face on {tracked}/{frames})")
        cursor += slot
    print(f"\nsum of slots: {cursor:.3f} s")


if __name__ == "__main__":
    main(sys.argv[1])

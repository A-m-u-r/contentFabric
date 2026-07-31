"""Что происходит ровно на стыке: рвётся ли фраза и прыгает ли фон.

Для каждой склейки берём полсекунды ролика поперёк неё и сравниваем с тем же
местом мастер-озвучки. Если между кусками что-то вставлено или потеряно, сдвиг
уедет, а совпадение просядет. Заодно печатаем уровень по обе стороны стыка —
ступенька шума слышна не как пауза, а как пропавшая связь.

    /opt/venv/bin/python /app/voice_test/seam_floor_2026_07_31.py <job_dir> <reel.mp4>
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app")
import saasshorts  # noqa: E402

SR = 48000
HOP = 0.005


def pcm(path, start=None, duration=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def level(samples):
    hop = int(SR * HOP)
    n = len(samples) // hop
    block = samples[: n * hop].reshape(n, hop)
    return 20 * np.log10(np.sqrt((block ** 2).mean(axis=1)) + 1e-12)


def lag_ms(a, b, max_lag=0.2):
    n = min(len(a), len(b))
    if n < SR // 20:
        return None, 0.0
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    size = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
    limit = int(max_lag * SR)
    window = np.concatenate([corr[-limit:], corr[: limit + 1]])
    i = int(np.argmax(window))
    norm = np.sqrt((a ** 2).sum() * (b ** 2).sum()) + 1e-12
    return np.arange(-limit, limit + 1)[i] * 1000.0 / SR, float(window[i] / norm)


def build_layout(job_dir):
    master = glob.glob(os.path.join(job_dir, "*_voice.mp3"))[0]
    slug = os.path.basename(master)[: -len("_voice.mp3")]
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    clips = []
    for shot in sorted(meta["shots"], key=lambda s: int(s["shot_number"])):
        n = int(shot["shot_number"])
        talking = os.path.join(job_dir, f"{slug}_avatar_{n:02d}.mp4")
        broll = os.path.join(job_dir, f"{slug}_avatar_broll_{n:02d}.mp4")
        path = talking if os.path.exists(talking) else broll
        if not os.path.exists(path):
            continue
        slice_audio = os.path.join(job_dir, f"{slug}_slice_{n:02d}.mp3")
        clips.append({
            "path": path,
            "duration": float(shot["end"]) - float(shot["start"]),
            "shot": shot,
            "audio_slice": slice_audio if path == talking else "",
            "speech_offset": (saasshorts._mp3_encoder_delay(slice_audio)
                              if path == talking else 0.0),
        })
    return master, saasshorts._reel_layout(clips)


def main(job_dir, reel):
    master, layout = build_layout(job_dir)
    track = level(pcm(reel))
    print(os.path.basename(reel))
    for segment in layout[:-1]:
        seam = segment["reel_start"] + segment["duration"]
        span = 0.25
        lag, r = lag_ms(pcm(master, seam - span, span * 2),
                        pcm(reel, seam - span, span * 2))
        before = track[int((seam - 0.06) / HOP):int((seam - 0.01) / HOP)]
        after = track[int((seam + 0.01) / HOP):int((seam + 0.06) / HOP)]
        step = float(np.median(after)) - float(np.median(before))
        kind = "дубль -> мастер" if segment["self_voiced"] else "мастер -> дубль"
        print(f"  {seam:6.2f}с {kind}: фраза {lag:+.0f} мс (r={r:+.2f}), "
              f"уровень {np.median(before):+.1f} -> {np.median(after):+.1f} dB "
              f"({step:+.1f} dB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

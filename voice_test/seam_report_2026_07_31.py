"""Что происходит на стыке дубля и перебивки.

Для каждого говорящего дубля: сколько своего звука он несёт, где в нём кончается
речь, сколько тишины дописывается до конца картинки, и насколько его шумовой пол
отличается от мастер-дорожки — стык слышно именно как смену фона, а не как паузу.

    /opt/venv/bin/python /app/voice_test/seam_report_2026_07_31.py <job_dir>
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")
from lip_open_probe import SR, _audio  # noqa: E402


def dur(path, stream=None):
    cmd = ["ffprobe", "-v", "error"]
    cmd += (["-select_streams", stream, "-show_entries", "stream=duration"] if stream
            else ["-show_entries", "format=duration"])
    cmd += ["-of", "default=nw=1:nk=1", path]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()
    try:
        return float(out[0])
    except (IndexError, ValueError):
        return 0.0


def envelope(pcm, step=0.01):
    hop = int(SR * step)
    return np.array([np.sqrt(np.mean(pcm[i * hop:(i + 1) * hop] ** 2) + 1e-12)
                     for i in range(len(pcm) // hop)])


def db(x):
    return 20 * np.log10(max(float(x), 1e-9))


def main(job_dir):
    master_path = glob.glob(os.path.join(job_dir, "*_voice.mp3"))[0]
    slug = os.path.basename(master_path)[: -len("_voice.mp3")]
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    shots = sorted(meta["shots"], key=lambda s: int(s["shot_number"]))
    master = _audio(master_path)
    m_env = envelope(master)
    m_floor = np.percentile(m_env, 5)
    print(f"мастер: пик {db(m_env.max()):+.1f} dB, шумовой пол {db(m_floor):+.1f} dB")

    for shot in shots:
        n = int(shot["shot_number"])
        clip = os.path.join(job_dir, f"{slug}_avatar_{n:02d}.mp4")
        if not os.path.exists(clip):
            continue
        pcm = _audio(clip)
        env = envelope(pcm)
        video, audio = dur(clip, "v:0") or dur(clip), len(pcm) / SR
        thr = env.max() * 0.06
        voiced = np.where(env > thr)[0]
        speech_end = (voiced[-1] + 1) * 0.01 if len(voiced) else audio
        floor = np.percentile(env, 5)
        print(f"  кадр {n:02d}: картинка {video:.3f}с, свой звук {audio:.3f}с, "
              f"речь кончается на {speech_end:.3f}с")
        print(f"          тишина в своём звуке {audio - speech_end:.3f}с + дописываем "
              f"{video - audio:.3f}с = пауза {video - speech_end:.3f}с")
        print(f"          пик {db(env.max()):+.1f} dB, шумовой пол {db(floor):+.1f} dB "
              f"(мастер {db(m_floor):+.1f} dB)")


if __name__ == "__main__":
    main(sys.argv[1])

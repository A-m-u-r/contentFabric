"""Что модель сделала со звуком, который мы ей дали, и насколько крупно лицо.

Два вопроса про говорящий дубль, на которые в отчётах пайплайна ответа нет:

1. Звук в возвращённом mp4 — тот же и на том же месте, что мы отправляли?
   Если модель отдала дорожку со сдвигом относительно картинки, которую по ней
   же и рисовала, губы уедут ровно на этот сдвиг, и никакой монтаж это не
   исправит. Меряется взаимной корреляцией волн, с точностью до сэмпла.

2. Насколько крупно лицо в кадре — доля высоты кадра между лбом и подбородком.
   Это то, чем липсинку вообще есть где происходить.

    python voice_test/take_vs_sent_2026_08_03.py clip.mp4 sent.mp3 [clip.mp4 sent.mp3 ...]
"""
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")

from lip_open_probe import _frames  # noqa: E402

SR = 16000
FOREHEAD, CHIN = 10, 152


def pcm(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1",
         "-ar", str(SR), "-f", "f32le", "-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def wave_lag(a, b, max_ms=400):
    """Сдвиг b относительно a в мс, по максимуму взаимной корреляции."""
    from scipy.signal import correlate
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    a = a - a.mean()
    b = b - b.mean()
    corr = correlate(b, a, mode="full")
    lags = np.arange(-n + 1, n)
    window = np.abs(lags) <= int(SR * max_ms / 1000)
    corr, lags = corr[window], lags[window]
    peak = int(np.argmax(np.abs(corr)))
    norm = corr[peak] / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)
    return lags[peak] * 1000.0 / SR, float(norm)


def face_share(path):
    """Медианная доля высоты кадра, которую занимает лицо."""
    import mediapipe as mp

    mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    shares = []
    for frame in _frames(path)[::5]:
        result = mesh.process(frame)
        if not result.multi_face_landmarks:
            continue
        pts = result.multi_face_landmarks[0].landmark
        shares.append(abs(pts[FOREHEAD].y - pts[CHIN].y))
    mesh.close()
    return float(np.median(shares)) if shares else float("nan")


def report(clip, sent):
    theirs, ours = pcm(clip), pcm(sent)
    lag, r = wave_lag(ours, theirs)
    print(f"{clip.split('/')[-1]} против {sent.split('/')[-1]}")
    print(f"    звук дубля против отправленного: {lag:+.1f} мс (r={r:+.2f}), "
          f"длины {len(theirs) / SR:.3f} и {len(ours) / SR:.3f} с")
    print(f"    лицо занимает {face_share(clip) * 100:.1f}% высоты кадра")


if __name__ == "__main__":
    args = sys.argv[1:]
    for clip, sent in zip(args[::2], args[1::2]):
        report(clip, sent)

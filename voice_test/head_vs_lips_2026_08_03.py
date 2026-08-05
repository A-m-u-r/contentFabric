"""Сколько в кадре головы и сколько рта — и не одно ли мешает другому.

Раскрытие рта, нормированное на высоту лица, ломается, когда голова ходит:
поворот и наклон меняют обе величины сразу. Поэтому здесь две нормировки —
на высоту лица и на ширину рта (её поворот меняет иначе) — и рядом честная
мера движения самой головы, чтобы было видно, что выросло, а что упало.

    python voice_test/head_vs_lips_2026_08_03.py clip.mp4 [clip.mp4 ...]
"""
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")

from lip_open_probe import FPS, SR, _audio, _envelope, _frames  # noqa: E402

UPPER_INNER_LIP, LOWER_INNER_LIP = 13, 14
MOUTH_LEFT, MOUTH_RIGHT = 61, 291
FOREHEAD, CHIN = 10, 152
NOSE = 1


def track(path):
    import mediapipe as mp

    mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    by_height, by_width, nose_x, nose_y, yaw = [], [], [], [], []
    frames = _frames(path)
    for frame in frames:
        result = mesh.process(frame)
        if not result.multi_face_landmarks:
            for series in (by_height, by_width, nose_x, nose_y, yaw):
                series.append(np.nan)
            continue
        p = result.multi_face_landmarks[0].landmark
        gap = abs(p[UPPER_INNER_LIP].y - p[LOWER_INNER_LIP].y)
        height = abs(p[FOREHEAD].y - p[CHIN].y) or 1e-6
        width = abs(p[MOUTH_LEFT].x - p[MOUTH_RIGHT].x) or 1e-6
        by_height.append(gap / height)
        by_width.append(gap / width)
        nose_x.append(p[NOSE].x / width)
        nose_y.append(p[NOSE].y / height)
        # Поворот: насколько нос сместился от середины линии рта.
        yaw.append((p[NOSE].x - (p[MOUTH_LEFT].x + p[MOUTH_RIGHT].x) / 2) / width)
    mesh.close()
    return (len(frames), *[np.array(s, dtype=float) for s in
                           (by_height, by_width, nose_x, nose_y, yaw)])


def fill(x):
    idx = np.arange(len(x))
    good = ~np.isnan(x)
    return np.interp(idx, idx[good], x[good]) if good.sum() >= 5 else None


def r_at(sound, mouth, lag=0):
    a, b = np.asarray(sound), np.asarray(mouth)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    if lag > 0:
        a, b = a[: n - lag], b[lag:]
    elif lag < 0:
        a, b = a[-lag:], b[: n + lag]
    return float(np.corrcoef(a, b)[0, 1])


def report(path):
    n, by_height, by_width, nose_x, nose_y, yaw = track(path)
    env = _envelope(_audio(path), n)
    m_h, m_w = fill(by_height)[: len(env)], fill(by_width)[: len(env)]
    label = path.split("/")[-1]
    best_h = max(range(-6, 7), key=lambda l: r_at(env, m_h, l))
    best_w = max(range(-6, 7), key=lambda l: r_at(env, m_w, l))
    print(f"{label}: {n} кадров")
    print(f"    рот/лицо   r@0 {r_at(env, m_h):+.2f} | лучший {r_at(env, m_h, best_h):+.2f} "
          f"на {best_h * 1000 // FPS:+.0f} мс")
    print(f"    рот/ширина r@0 {r_at(env, m_w):+.2f} | лучший {r_at(env, m_w, best_w):+.2f} "
          f"на {best_w * 1000 // FPS:+.0f} мс")
    print(f"    ход головы: нос x {np.nanstd(nose_x) * 100:.2f}, y {np.nanstd(nose_y) * 100:.2f}, "
          f"поворот {np.nanstd(yaw) * 100:.2f} (в % ширины рта / высоты лица)")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        report(path)

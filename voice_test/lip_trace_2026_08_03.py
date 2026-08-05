"""Покадровая таблица «звук против рта» и контактный лист самих губ.

Корреляция на клипе в две секунды — величина шумная, и по одному числу нельзя
сказать, рот не попал или мерялка не справилась. Здесь то же самое видно
глазами: на каждый кадр печатается уровень звука и раскрытие рта, а рядом
складывается полоска из вырезанных ртов — по ней сразу читается, закрывается ли
рот на паузе и открывается ли на гласной.

    python voice_test/lip_trace_2026_08_03.py clip.mp4 out_strip.png [первый_кадр] [сколько]
"""
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")

from lip_open_probe import FPS, _audio, _envelope, _frames  # noqa: E402

UPPER_INNER_LIP, LOWER_INNER_LIP = 13, 14
MOUTH_LEFT, MOUTH_RIGHT = 61, 291
FOREHEAD, CHIN = 10, 152


def trace(path, out_png, first=0, count=40):
    import cv2
    import mediapipe as mp

    frames = _frames(path)
    env = _envelope(_audio(path), len(frames))
    mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    height, width = frames.shape[1:3]
    crops, rows = [], []
    for i, frame in enumerate(frames):
        result = mesh.process(frame)
        if not result.multi_face_landmarks:
            rows.append((i, float("nan")))
            continue
        p = result.multi_face_landmarks[0].landmark
        gap = abs(p[UPPER_INNER_LIP].y - p[LOWER_INNER_LIP].y)
        face = abs(p[FOREHEAD].y - p[CHIN].y) or 1e-6
        rows.append((i, gap / face))
        if first <= i < first + count:
            cx = (p[MOUTH_LEFT].x + p[MOUTH_RIGHT].x) / 2 * width
            cy = (p[UPPER_INNER_LIP].y + p[LOWER_INNER_LIP].y) / 2 * height
            half_w = max(18, abs(p[MOUTH_LEFT].x - p[MOUTH_RIGHT].x) * width)
            half_h = half_w
            x0, y0 = int(max(0, cx - half_w)), int(max(0, cy - half_h))
            x1, y1 = int(min(width, cx + half_w)), int(min(height, cy + half_h))
            crop = cv2.resize(frame[y0:y1, x0:x1], (96, 96))
            crops.append(crop)
    mesh.close()

    peak = max((e for e in env if not np.isnan(e)), default=1.0)
    print(f"{path.split('/')[-1]}: {len(frames)} кадров, звук на {len(env)}")
    print(" кадр   мс   звук                 рот")
    for i, openness in rows[: len(env)]:
        bar = "#" * int(round(env[i] / peak * 20))
        mouth = "" if np.isnan(openness) else "=" * int(round(openness * 200))
        print(f" {i:4d} {i * 1000 // FPS:5d}  {bar:<20} {mouth}")

    if crops:
        per_row = 10
        pad = (-len(crops)) % per_row
        crops += [np.zeros_like(crops[0])] * pad
        grid = np.vstack([np.hstack(crops[r:r + per_row])
                          for r in range(0, len(crops), per_row)])
        cv2.imwrite(out_png, cv2.cvtColor(grid, cv2.COLOR_RGB2BGR))
        print(f"полоска губ: {out_png} (кадры {first}..{first + count - 1}, по {per_row} в ряд)")


if __name__ == "__main__":
    args = sys.argv[1:]
    trace(args[0], args[1],
          int(args[2]) if len(args) > 2 else 0,
          int(args[3]) if len(args) > 3 else 40)

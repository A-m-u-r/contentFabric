"""Насколько крупно лицо в кадре — по самой картинке, а не по названию файла.

Меряем высоту лица как долю высоты кадра. Крупный план — это ~0.45 и выше,
средний — ~0.2, поясной и шире — меньше 0.15. Позволяет проверить, что вышло
после правки, а не что мы просили словами.

    /opt/venv/bin/python /app/voice_test/framing_check_2026_08_02.py <img.png> [...]
"""
import os
import sys

import cv2
import mediapipe as mp
import numpy as np


def face_share(path):
    image = cv2.imread(path)
    if image is None:
        return None, None
    h, w = image.shape[:2]
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1,
                                         refine_landmarks=True) as mesh:
        found = mesh.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    if not found.multi_face_landmarks:
        return None, (w, h)
    ys = np.array([p.y for p in found.multi_face_landmarks[0].landmark])
    return float(ys.max() - ys.min()), (w, h)


def plan(share):
    if share is None:
        return "лица не видно"
    if share >= 0.45:
        return "крупный"
    if share >= 0.28:
        return "средний крупный"
    if share >= 0.16:
        return "средний"
    return "поясной и шире"


def main(paths):
    for path in paths:
        share, size = face_share(path)
        name = os.path.basename(path)
        if share is None:
            print(f"  {name:44s} {size}  {plan(share)}")
            continue
        print(f"  {name:44s} {size[0]}x{size[1]}  лицо {share * 100:4.1f}% кадра  "
              f"-> {plan(share)}")


if __name__ == "__main__":
    main(sys.argv[1:])

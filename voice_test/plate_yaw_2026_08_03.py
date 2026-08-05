"""Насколько плита действительно снята «сбоку»: поворот головы и место в кадре.

Ракурс просят словами, а получают картинкой, и «кажется, тот же анфас» — не
аргумент. Здесь два числа на плиту:

* `поворот` — асимметрия лица: расстояние от кончика носа до левого контура
  минус до правого, делённое на их сумму. Анфас даёт около нуля, поворот на
  сорок градусов — заметную величину со знаком. Мера безразмерная, так что
  плиты разной крупности сравниваются между собой.
* `центр` — где лицо стоит по горизонтали, долей ширины кадра. Промпт камеры
  `side` просит человека справа кадра, то есть заметно больше 0.50.

    python voice_test/plate_yaw_2026_08_03.py plate.png [plate.png ...]
"""
import sys

NOSE_TIP, LEFT_EDGE, RIGHT_EDGE = 1, 234, 454


def measure(path):
    import cv2
    import mediapipe as mp

    image = cv2.imread(path)
    if image is None:
        return None
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True, max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.4,
    ) as mesh:
        result = mesh.process(rgb)
    if not result.multi_face_landmarks:
        return None
    p = result.multi_face_landmarks[0].landmark
    left = abs(p[NOSE_TIP].x - p[LEFT_EDGE].x)
    right = abs(p[RIGHT_EDGE].x - p[NOSE_TIP].x)
    span = left + right
    return {
        "yaw": (left - right) / span if span else 0.0,
        "centre": p[NOSE_TIP].x,
        "face": abs(p[10].y - p[152].y),
    }


if __name__ == "__main__":
    for path in sys.argv[1:]:
        got = measure(path)
        name = path.replace("\\", "/").split("/")
        label = f"{name[-2]}/{name[-1]}" if len(name) > 1 else path
        if not got:
            print(f"{label:<62} лицо не найдено")
            continue
        print(f"{label:<62} поворот {got['yaw']:+.3f} | "
              f"центр {got['centre']:.2f} | лицо {got['face']:.3f}")

"""Сводка по пачке дублей: артикулирует рот или держит одну гримасу.

Три числа на клип, все три читаются без корреляций:

* `ход` — средняя перемена раскрытия от кадра к кадру. Артикуляция это перемена;
  застывшая улыбка даёт ноль, как бы широко рот при этом ни был открыт.
* `тихо` и `громко` — среднее раскрытие на самых тихих и самых громких кадрах.
  У попадающего в звук рта второе заметно больше первого; если они равны или
  перевёрнуты, рот живёт отдельно от речи.
* `r@0` — корреляция раскрытия с огибающей, для сравнения с прежними замерами.

    python voice_test/lip_population_2026_08_03.py clip.mp4 [clip.mp4 ...]
"""
import sys

import numpy as np

sys.path.insert(0, "/app/voice_test")

from lip_open_probe import (  # noqa: E402
    _audio, _envelope, _fill_gaps, _frames, mouth_openness,
)


def summarise(path):
    frames = _frames(path)
    env = _envelope(_audio(path), len(frames))
    mouth = _fill_gaps(mouth_openness(frames[: len(env)]))
    if mouth is None:
        print(f"{path.split('/')[-1]}: лицо не найдено")
        return
    n = min(len(env), len(mouth))
    env, mouth = env[:n], mouth[:n]
    order = np.argsort(env)
    third = max(1, n // 3)
    quiet, loud = mouth[order[:third]].mean(), mouth[order[-third:]].mean()
    move = float(np.abs(np.diff(mouth)).mean())
    r = float(np.corrcoef(env, mouth)[0, 1])
    print(f"{path.split('/')[-1]:<28} кадров {n:3d} | ход {move * 1000:5.1f} | "
          f"тихо {quiet:.3f} громко {loud:.3f} (разница {loud - quiet:+.3f}) | r@0 {r:+.2f}")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        summarise(path)

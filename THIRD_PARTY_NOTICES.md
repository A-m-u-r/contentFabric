# Уведомления о сторонних компонентах

Закрытый доступ к репозиторию «Контентфабрики» не меняет лицензии унаследованного кода и зависимостей. Ограничения в [LICENSE](LICENSE) относятся только к собственным материалам проекта в пределах прав их владельцев.

## OpenShorts

Проект использует унаследованный код [OpenShorts](https://github.com/mutonby/openshorts). Ниже сохранён полный текст исходного уведомления MIT. Предоставленные им права на соответствующий код сохраняются.

```text
MIT License

Copyright (c) 2024 OpenShorts

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Ultralytics и YOLO

В `requirements.txt` используется `ultralytics==8.4.46`; обработка длинного видео обращается к YOLO, а backend-образ загружает модель `yolov8n.pt`.

Эта версия распространяется по [AGPL-3.0](https://github.com/ultralytics/ultralytics/blob/v8.4.46/LICENSE). Производитель также предлагает [Enterprise License](https://www.ultralytics.com/license) для использования в закрытых продуктах. Режим использования этого компонента и необходимость отдельной лицензии должны быть определены до соответствующего распространения или коммерческого развёртывания. Наличие приватного репозитория само по себе этот вопрос не решает.

## Remotion

Зафиксированная версия Remotion — `4.0.447`. Она использует [собственную лицензию](https://github.com/remotion-dev/remotion/blob/v4.0.447/LICENSE.md), а не MIT. Условия бесплатного использования и необходимость Company License определяются [условиями версии 4](https://www.remotion.pro/terms-4-0), в том числе размером и типом организации.

## Остальные зависимости

Библиотеки, модели, шрифты и внешние сервисы сохраняют собственные лицензии и условия использования. Их тексты поставляются в соответствующих дистрибутивах. Собственные условия проекта не заменяют эти документы.

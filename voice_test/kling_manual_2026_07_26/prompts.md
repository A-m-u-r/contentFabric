# Промпты для Kling Avatar: что можно, чего нельзя

Три вещи задают клип: **референсный кадр** (сцена, одежда, свет, крупность),
**аудио** (речь и её темп) и **промпт**. У промпта остаётся одна работа —
держать тело. Всё остальное он только портит.

## Что говорят сами схемы моделей (fal OpenAPI, проверено 2026-07-26)

| Модель | Обязательные поля | prompt | negative_prompt |
|---|---|---|---|
| `kling-video/ai-avatar/v2/standard` и `/pro` (наша) | `image_url`, `audio_url` | опционально, **дефолт `"."`** | **поля нет** |
| `kling-video/v3/standard/image-to-video` (наш b-roll) | `start_image_url` | есть | есть, дефолт `blur, distort, and low quality` |
| `longcat-single-avatar/image-audio-to-video` | `image_url`, `audio_url` | дефолт: `A person is talking naturally with natural expressions and movements.` | есть, туда вендор кладёт `subtitles`, `worst quality`, `three legs` и т.п. |
| `heygen/avatar4/image-to-video` | `image_url` | текст реплики | нет, зато есть `talking_style: stable \| expressive` — «stable for minimal movement» |

Отсюда три вывода:

1. У аватарного эндпойнта Kling **нет negative_prompt** — значит запрещать
   что-либо словами там негде, и всё, что мы напишем, модель считает заказом.
   У Kling V3 поле есть, и мы им уже пользуемся (`blur, distort, low quality,
   deformed face, extra fingers, wrong text, watermark`) — вот туда такие слова
   и складывают.
2. Дефолт вендора для аватара — точка. То есть модель рассчитана работать
   вообще без промпта; всё, что мы дописываем, — на свой страх.
3. Ориентир длины: у Longcat вендорский дефолт — одно предложение простым
   языком. Не абзац на десять строк.

## Правила

1. **Никаких отрицаний.** У модели нет negative prompt. «no text», «no
   watermark», «never duplicate» она читает как перечисление того, что надо
   нарисовать. Наш старый промпт содержал слова text/captions/subtitles/logos —
   и получил нечитаемый текст внизу кадра.
2. **Пиши состояние, которое нужно, а не то, которого не нужно.** Не «руки не
   двигаются», а «руки спокойно лежат». Не «без лишних движений», а «двигается
   только лицо».
3. **Не описывай сцену.** Она уже в референсном кадре. Дублирование сцены в
   промпте тянет модель перерисовывать композицию и ломает совпадение кадров
   между шотами.
4. **Коротко.** Три-четыре предложения. Чем длиннее промпт, тем больше у модели
   поводов «поставить постановку».
5. **Не пиши про губы и тайминг.** «Mouth movement must follow the audio
   exactly» ничего не улучшило: замер показал одинаковый сдвиг губ с промптом и
   без (+146 и +145 мс). Липсинк задаётся аудио, а не текстом.

Проверка словаря зашита в код: `_avatar_prompt_issues()` ловит
text/caption/subtitle/logo/watermark/sign/label/screen/number/symbol и прочее,
тест падает, если такое слово появится в промпте.

## Что тестировать руками

Одинаковые вход: `reference_shot05.png` + `A_as_we_send_shot05.mp3`.
Смотреть два признака: **перекладывание ног/рук** и **кракозябры**.

### P1 — минимум

```
The person from the reference image speaks straight to the camera and stays seated in the same pose, hands resting calmly, legs still. Only the face moves: natural blinking and small head movements.
```

### P2 — то, что сейчас в коде

```
The person stays seated in the same pose, hands resting calmly, legs still, speaking straight to the camera with a calm friendly expression. Only the face moves: the lips follow the audio, natural blinking, small head movements, one locked-off take.
```

### P3 — жёстче, если P2 всё ещё ёрзает

```
The person from the reference image holds one steady seated pose for the whole shot: hands stay where they are, legs stay where they are, torso and shoulders stay in place. Only the face moves: the lips follow the audio, natural blinking, tiny head movements, a calm friendly expression. Outfit, hair, background, crop and camera stay exactly as in the reference image, one locked-off take.
```

Если на всех трёх кракозябр нет — берём самый жёсткий, который не выглядит
«замороженным». Если кракозябры вернулись даже на P1 — значит дело не в
словаре, а в самом факте промпта, и тогда правильный ответ: не слать промпт
совсем и лечить ёрзание референсным кадром (поза с руками на коленях, кадр
поплотнее — по грудь, чтобы ног в кадре просто не было).

# Ручная проверка Kling Avatar — наш это косяк или модели

Всё взято из джоба `saas_b13f0229-9f09-4bf5-a8d8-890226a92863`, кадр 5
(«Нужна другая стратегия, бережная… без насилия над собой»).

## Что мы отправляли на самом деле

- эндпойнт: `fal-ai/kling-video/ai-avatar/v2/standard`
- вход: только `image_url`, `audio_url` и `prompt` — больше ничего
- картинка: `reference_shot05.png` (она же уходила в запрос)
- звук: `A_as_we_send_shot05.mp3`
- промпт (в нём, между прочим, уже сказано держать рот закрытым в тишине):

```
Vertical 9:16 realistic UGC ad, same actor, natural 35-year-old Slavic woman,
sitting comfortably on a soft sofa, casual outfit, friendly and encouraging
expression, beautiful window light, no text, no burned-in text, no watermark.
no readable on-screen text, any device screens turned away or out of focus.
Keep body movement minimal and controlled. Use only subtle head movement,
natural blinking, and small micro-expressions. Maintain eye contact with the
camera. Mouth movement must follow the provided audio exactly. When the audio
is silent or ends, keep lips closed and hold a calm neutral expression. Show
exactly one single person, centered and fully inside the frame. Never duplicate
the subject, never show a twin, clone, mirror copy or a second face, and keep
the edges of the frame free of any extra person. Keep the outfit, skin and
background exactly as in the reference image: never add text, letters, numbers,
logos, prints or tattoos to clothing, skin or background.
```

## Файлы

| Файл | Что это | Длина | Тишина в начале |
|---|---|---|---|
| `A_as_we_send_shot05.mp3` | ровно то, что ушло в Kling | 4.389 с | 310 мс + 25 мс задержки mp3-энкодера |
| `B_shot05_same_but_wav.wav` | тот же звук, но PCM | 4.347 с | 310 мс, задержки энкодера нет |
| `C_shot05_speech_only.wav` | та же фраза без немого начала | 4.047 с | нет |
| `D_control_shot01.mp3` | кадр 1, он и так начинается с речи | 3.500 с | нет (контроль) |
| `reference_shot05.png` | референсный кадр из запроса | — | — |

## Что смотреть

1. **A** — должен воспроизвести нашу картину: рот на первом кадре уже открыт и
   закрывается к ~270 мс, пока в звуке тишина. Если у тебя выйдет так же —
   это поведение модели, а не сборки.
2. **B против A** — отвечает на вопрос про 25 мс задержки mp3. Если B заметно
   ровнее, значит Kling не срезает служебную голову mp3 и надо слать PCM.
3. **C** — главный тест. Если на звуке без немого начала губы попадают точно,
   подтверждается то, что я уже поправил в коде: резать надо не по середине
   паузы, а перед самой фразой.
4. **D** — контроль. Этот кадр и раньше начинался с речи; если он синхронен,
   а A нет — дело именно в тишине на старте.

Замер, который получился у меня по лицевым точкам (mediapipe, лицо найдено на
100% кадров): в клипе кадра 5 звук молчит первые 330 мс, а раскрытие губ на
нулевом кадре 0.06 и плавно уходит в 0.003 к 270 мс. В кадре 3 (тишина 200 мс)
рот открывается ровно на 200 мс — там модель тишину отработала правильно.

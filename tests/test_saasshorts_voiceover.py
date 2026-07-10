import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import httpx

from saasshorts import (
    _align_shots_to_voiceover,
    _avatar_reference_variant,
    _avatar_scene_prompt,
    _broll_slice_shot,
    _elevenlabs_voice_for,
    _is_broll_shot,
    _pick_caption_highlight_word,
    _purge_voiceover_derived_assets,
    _salvage_json_array,
    _strip_audio_tags,
    generate_voiceover,
)


def _fake_http_client(responses):
    """Context-manager mock for httpx.Client whose .post() replays `responses`."""
    client = MagicMock()
    client.post.side_effect = responses
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    return cm, client


def _response(status_code=200, content=b"mp3-bytes", text="error"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = text
    return resp


class StripAudioTagsTests(unittest.TestCase):
    def test_removes_tags_and_collapses_whitespace(self):
        self.assertEqual(
            _strip_audio_tags("[sighs] Привет — мир [excited] и точка."),
            "Привет — мир и точка.",
        )

    def test_keeps_text_without_tags_intact(self):
        text = "Стоп-стоп-стоп. Это не работает… вообще."
        self.assertEqual(_strip_audio_tags(text), text)


class GenerateVoiceoverV3Tests(unittest.TestCase):
    def test_defaults_to_v3_creative_with_tags_preserved(self):
        cm, client = _fake_http_client([_response(200)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "voice.mp3")
            with patch("saasshorts.httpx.Client", return_value=cm):
                generate_voiceover("[sighs] Так, слушай.", "key", out, voice_id="v1")
            self.assertTrue(os.path.getsize(out) > 0)

        self.assertEqual(client.post.call_count, 1)
        body = client.post.call_args.kwargs["json"]
        self.assertEqual(body["model_id"], "eleven_v3")
        self.assertEqual(body["voice_settings"], {"stability": 0.0})
        self.assertIn("[sighs]", body["text"])

    def test_falls_back_to_multilingual_v2_with_stripped_tags(self):
        cm, client = _fake_http_client([_response(403), _response(200)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "voice.mp3")
            with patch("saasshorts.httpx.Client", return_value=cm):
                generate_voiceover("[sighs] Так, слушай.", "key", out, voice_id="v1")

        self.assertEqual(client.post.call_count, 2)
        body = client.post.call_args_list[1].kwargs["json"]
        self.assertEqual(body["model_id"], "eleven_multilingual_v2")
        self.assertEqual(body["voice_settings"]["stability"], 0.5)
        self.assertNotIn("[sighs]", body["text"])
        self.assertIn("Так, слушай.", body["text"])

    def test_raises_when_both_models_fail(self):
        # 500 повторяется 3 раза (transient), 403 — нет
        cm, client = _fake_http_client([_response(403), _response(500), _response(500), _response(500)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "voice.mp3")
            with patch("saasshorts.httpx.Client", return_value=cm), \
                 patch("saasshorts.time.sleep"):
                with self.assertRaises(Exception):
                    generate_voiceover("Привет", "key", out)
        self.assertEqual(client.post.call_count, 4)

    def test_retries_network_errors_before_provider_fallback(self):
        # Два сетевых сбоя, затем успех — MiniMax-фолбэк не должен понадобиться
        cm, client = _fake_http_client([
            httpx.ConnectTimeout("timed out"),
            httpx.ConnectTimeout("timed out"),
            _response(200),
        ])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "voice.mp3")
            with patch("saasshorts.httpx.Client", return_value=cm), \
                 patch("saasshorts.time.sleep"):
                generate_voiceover("Привет", "key", out)
            self.assertTrue(os.path.getsize(out) > 0)
        self.assertEqual(client.post.call_count, 3)
        # Все три вызова — та же модель v3, никакого даунгрейда
        for call in client.post.call_args_list:
            self.assertEqual(call.kwargs["json"]["model_id"], "eleven_v3")


class SlicedAvatarShotVarietyTests(unittest.TestCase):
    def test_scene_prompt_built_from_shot_fields(self):
        shot = {
            "scene": "Kitchen counter, morning light",
            "actor_action": "leans in, gestures with cup",
            "camera": "medium close-up",
            "emotion": "warm",
        }
        prompt = _avatar_scene_prompt(shot)
        self.assertIn("Kitchen counter", prompt)
        self.assertIn("gestures with cup", prompt)
        self.assertIn("medium close-up", prompt)
        self.assertIn("warm mood", prompt)

    def test_scene_prompt_empty_for_bare_shot(self):
        self.assertEqual(_avatar_scene_prompt({"speech": "только текст"}), "")

    def test_first_shot_keeps_original_reference(self):
        result = _avatar_reference_variant("/img/actor.png", "/img/ref_01.png", 1)
        self.assertEqual(result, "/img/actor.png")

    def test_later_shots_get_cropped_variant(self):
        recorded = {}

        def fake_run(cmd, check, capture_output):
            recorded["cmd"] = cmd
            with open(cmd[-1], "wb") as f:
                f.write(b"png")

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            src = os.path.join(tmp, "actor.png")
            with open(src, "wb") as f:
                f.write(b"src")
            out = os.path.join(tmp, "ref_02.png")
            with patch("saasshorts.subprocess.run", side_effect=fake_run):
                result = _avatar_reference_variant(src, out, 2)
            self.assertEqual(result, out)
        self.assertIn("crop=", " ".join(recorded["cmd"]))


class SalvageJsonArrayTests(unittest.TestCase):
    def test_recovers_complete_objects_before_truncation(self):
        text = (
            '[{"title": "One", "shots": [{"speech": "a"}]}, '
            '{"title": "Two", "shots": [{"speech": "b"}]}, '
            '{"title": "Three", "shots": [{"speech": "unterminated'
        )
        result = _salvage_json_array(text)
        self.assertEqual([s["title"] for s in result], ["One", "Two"])

    def test_ignores_braces_inside_strings(self):
        text = '[{"title": "Uses { and } inside a string"}, {"title": "Second"'
        result = _salvage_json_array(text)
        self.assertEqual([s["title"] for s in result], ["Uses { and } inside a string"])

    def test_returns_empty_list_when_nothing_closed(self):
        self.assertEqual(_salvage_json_array('[{"title": "unterminated'), [])

    def test_full_valid_array_recovers_everything(self):
        text = '[{"a": 1}, {"b": 2}]'
        self.assertEqual(_salvage_json_array(text), [{"a": 1}, {"b": 2}])

    def test_generate_scripts_recovers_from_truncated_gemini_response(self):
        import json as _json

        from saasshorts import generate_scripts

        def _shot(text):
            return {
                "shot_number": 1, "start": 0, "end": 4, "role": "hook",
                "scene": "s", "camera": "c", "actor_action": "a", "speech": text,
                "emotion": "excited", "overlay_text": "o", "visual_type": "talking",
                "transition": "cut", "generation_prompt": "g",
            }

        first = {"title": "One", "shots": [_shot("Text one")], "full_narration": "Text one"}
        second = {"title": "Two", "shots": [_shot("Text two")], "full_narration": "Text two"}
        # Mirrors the real failure: Gemini's output cap cuts the 3rd script mid-string.
        truncated = (
            "[" + _json.dumps(first) + ", " + _json.dumps(second)
            + ', {"title": "Three", "shots": [{"speech": "unterminated'
        )

        mock_response = MagicMock()
        mock_response.text = truncated
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client):
            scripts = generate_scripts(
                analysis={"product_name": "Test"},
                gemini_key="key",
                num_scripts=3,
                script_format="storyboard_v3",
                language="ru",
            )

        self.assertEqual([s["title"] for s in scripts], ["One", "Two"])
        self.assertTrue(all(s["format"] == "storyboard_v3" for s in scripts))


class GenerateContentPlanTests(unittest.TestCase):
    def _plan_from_response(self, response_text, **kwargs):
        from saasshorts import generate_content_plan

        mock_response = MagicMock()
        mock_response.text = response_text
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client):
            return generate_content_plan(
                {"name": "Моя Форма 30+", "description": "Система похудения", "topic": ""},
                "key",
                **kwargs,
            )

    def test_normalizes_and_sorts_items_by_day(self):
        import json as _json

        raw = _json.dumps([
            {"day": 8, "title": "Мифы о диетах", "topic": "Разбор мифа", "hook": "Стоп.",
             "goal": "Доверие", "format_hint": "UGC", "cta": "Подпишись"},
            {"day": 1, "title": "Почему срывы", "topic": "Срывы вечером", "hook": "Так, слушай.",
             "goal": "прогрев", "format_hint": "storyboard_v3", "cta": "Напиши НЕДЕЛЯ"},
        ])
        items = self._plan_from_response(raw, num_items=2)

        self.assertEqual([item["day"] for item in items], [1, 8])
        self.assertEqual(items[1]["goal"], "доверие")
        self.assertEqual(items[1]["format_hint"], "ugc")

    def test_recovers_items_from_truncated_response(self):
        raw = (
            '[{"day": 1, "title": "A", "topic": "t", "hook": "h", "goal": "прогрев", '
            '"format_hint": "ugc", "cta": "c"}, {"day": 5, "title": "B", "topic": "обрыв'
        )
        items = self._plan_from_response(raw, num_items=2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A")


class BrollSliceShotTests(unittest.TestCase):
    def test_is_broll_accepts_spelling_variants(self):
        for value in ("broll", "B-Roll", "b_roll", "  BROLL "):
            self.assertTrue(_is_broll_shot({"visual_type": value}), value)
        for value in ("talking", "", None):
            self.assertFalse(_is_broll_shot({"visual_type": value}), repr(value))

    def test_ceils_duration_and_appends_no_lip_clause(self):
        shot = {
            "visual_type": "broll",
            "start": 3.2,
            "end": 7.4,
            "generation_prompt": "vertical 9:16 realistic UGC ad, kitchen, no burned-in text",
        }
        v3_shot = _broll_slice_shot(shot, 4.2)

        self.assertEqual(v3_shot["start"], 0)
        self.assertEqual(v3_shot["end"], 5)
        self.assertTrue(v3_shot["generation_prompt"].startswith(shot["generation_prompt"]))
        self.assertIn("no lip movement", v3_shot["generation_prompt"])
        # Оригинальный кадр не мутируется — им ещё пользуются субтитры
        self.assertEqual(shot["start"], 3.2)
        self.assertNotIn("no lip movement", shot["generation_prompt"])

    def test_builds_prompt_from_scene_when_missing(self):
        shot = {"visual_type": "broll", "scene": "hands pour coffee", "speech": "текст"}
        v3_shot = _broll_slice_shot(shot, 3.0)
        self.assertIn("hands pour coffee", v3_shot["generation_prompt"])
        self.assertIn("no lip movement", v3_shot["generation_prompt"])


class CaptionHighlightTests(unittest.TestCase):
    def test_prefers_script_keywords(self):
        word = _pick_caption_highlight_word("ХВАТИТ ЖДАТЬ ЧУДА", keywords=["чуда"])
        self.assertEqual(word, "ЧУДА")

    def test_falls_back_to_longest_heavy_word(self):
        word = _pick_caption_highlight_word("каждый понедельник заново")
        self.assertEqual(word, "ПОНЕДЕЛЬНИК")


class PurgeDerivedAssetsTests(unittest.TestCase):
    def test_removes_slices_and_avatar_clips_keeps_rest(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            stale = [
                "story_slice_01.mp3",
                "story_avatar_01.mp4",
                "story_avatar_01.mp4.fal_url.txt",
                "story_voice_clean.mp3",
            ]
            kept = ["story_voice.mp3", "story_actor.png", "story_shot_01.mp4"]
            for name in stale + kept:
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(b"x")

            _purge_voiceover_derived_assets(tmp, "story")

            remaining = set(os.listdir(tmp))
            self.assertEqual(remaining, set(kept))


class DefaultVoiceTests(unittest.TestCase):
    def test_russian_defaults_to_native_voice(self):
        self.assertEqual(_elevenlabs_voice_for("ru"), "D5RRIJYa9pFwxiSpbGbR")

    def test_explicit_voice_wins(self):
        self.assertEqual(_elevenlabs_voice_for("ru", "custom"), "custom")

    def test_unknown_language_falls_back_to_rachel(self):
        self.assertEqual(_elevenlabs_voice_for("de"), "21m00Tcm4TlvDq8ikWAM")

    def test_english_fallback_voice_remapped_for_russian(self):
        # Регрессия: фронтенд после перезагрузки слал свой английский дефолт
        # (Rachel) для русского текста — бэкенд должен вернуть русский дефолт.
        self.assertEqual(_elevenlabs_voice_for("ru", "21m00Tcm4TlvDq8ikWAM"), "D5RRIJYa9pFwxiSpbGbR")

    def test_english_fallback_voice_kept_for_english(self):
        self.assertEqual(_elevenlabs_voice_for("en", "21m00Tcm4TlvDq8ikWAM"), "21m00Tcm4TlvDq8ikWAM")


class AlignWithAudioTagsTests(unittest.TestCase):
    def _words(self):
        # Два предложения по 3 слова с явной паузой между ними
        return [
            {"word": "раз", "start": 0.0, "end": 0.4},
            {"word": "два", "start": 0.5, "end": 0.9},
            {"word": "три", "start": 1.0, "end": 1.4},
            {"word": "четыре", "start": 2.4, "end": 2.8},
            {"word": "пять", "start": 2.9, "end": 3.3},
            {"word": "шесть", "start": 3.4, "end": 3.8},
        ]

    def test_trailing_tag_does_not_break_last_word_match(self):
        shots = [
            {"shot_number": 1, "speech": "Раз два три [sighs]"},
            {"shot_number": 2, "speech": "Четыре пять шесть"},
        ]
        slices, skipped = _align_shots_to_voiceover(shots, self._words(), 4.0)
        self.assertEqual(skipped, [])
        self.assertEqual(len(slices), 2)
        # Граница в паузе между "три" (1.4) и "четыре" (2.4)
        self.assertAlmostEqual(slices[0]["end"], 1.9, delta=0.05)

    def test_tag_only_words_do_not_skew_weights(self):
        shots = [
            {"shot_number": 1, "speech": "[excited] [whispers] Раз два три"},
            {"shot_number": 2, "speech": "Четыре пять шесть"},
        ]
        slices, _ = _align_shots_to_voiceover(shots, self._words(), 4.0)
        # Без учёта тегов веса равные (3 и 3) — граница остаётся в паузе
        self.assertAlmostEqual(slices[0]["end"], 1.9, delta=0.05)


if __name__ == "__main__":
    unittest.main()

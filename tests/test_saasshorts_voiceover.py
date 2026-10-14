import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import httpx

from saasshorts import (
    _align_shots_to_voiceover,
    _avatar_reference_variant,
    _broll_slice_shot,
    _elevenlabs_voice_for,
    _estimate_speech_duration,
    _finalize_generated_script,
    _hook_opening,
    _is_broll_shot,
    _pick_caption_highlight_word,
    _purge_voiceover_derived_assets,
    _request_gemini_script_batch,
    _salvage_json_array,
    _script_spoken_text,
    _strip_audio_tags,
    _validate_script_batch_hooks,
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


class SanitizeElevenV3AudioTagsTests(unittest.TestCase):
    def test_normalizes_known_aliases_and_removes_unknown_tags(self):
        module = __import__("saasshorts")
        sanitizer = getattr(module, "_sanitize_eleven_v3_audio_tags", None)

        self.assertIsNotNone(sanitizer)
        self.assertEqual(
            sanitizer("[confident] Привет. [whispering] Это секрет. [music]"),
            "Привет. [whispers] Это секрет.",
        )


class GenerateVoiceoverV3Tests(unittest.TestCase):
    def test_sanitizes_v3_tags_before_sending_text(self):
        cm, client = _fake_http_client([_response(200)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "voice.mp3")
            with patch("saasshorts.httpx.Client", return_value=cm):
                generate_voiceover(
                    "[confident] Привет. [whispering] Это секрет. [music]",
                    "key",
                    out,
                    voice_id="v1",
                )

        body = client.post.call_args.kwargs["json"]
        self.assertEqual(body["text"], "Привет. [whispers] Это секрет.")

    def test_defaults_to_v3_natural_with_supported_tags_preserved(self):
        cm, client = _fake_http_client([_response(200)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "voice.mp3")
            with patch("saasshorts.httpx.Client", return_value=cm):
                generate_voiceover("[sighs] Так, слушай.", "key", out, voice_id="v1")
            self.assertTrue(os.path.getsize(out) > 0)

        self.assertEqual(client.post.call_count, 1)
        body = client.post.call_args.kwargs["json"]
        self.assertEqual(body["model_id"], "eleven_v3")
        self.assertEqual(body["voice_settings"], {"stability": 0.5})
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


class GenerateVoiceoverV4Tests(unittest.TestCase):
    def test_v4_uses_requested_model_and_preserves_russian_tags(self):
        cm, client = _fake_http_client([_response(200)])
        text = "[curious] Привет. [whispers] Это секрет. [exhales]"
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "voice.mp3")
            with patch("saasshorts.httpx.Client", return_value=cm):
                model = generate_voiceover(text, "key", out, voice_id="v1", model_id="eleven_v4")
            with open(out, "rb") as audio:
                self.assertEqual(audio.read(), b"mp3-bytes")
        self.assertEqual(model, "eleven_v4")
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(client.post.call_args.args[0], "https://api.elevenlabs.io/v1/text-to-speech/v1")
        self.assertEqual(client.post.call_args.kwargs["json"]["text"], text)
        self.assertEqual(client.post.call_args.kwargs["json"]["model_id"], "eleven_v4")
        self.assertEqual(client.post.call_args.kwargs["json"]["voice_settings"], {
            "stability": 0.5, "similarity_boost": 0.75,
        })

    def test_v4_custom_settings_reach_provider(self):
        cm, client = _fake_http_client([_response(200)])
        with tempfile.TemporaryDirectory() as tmp:
            with patch("saasshorts.httpx.Client", return_value=cm):
                generate_voiceover(
                    "Привет", "key", os.path.join(tmp, "voice.mp3"),
                    voice_id="v1", model_id="eleven_v4",
                    stability=0.35, similarity=0.9,
                )
        self.assertEqual(client.post.call_args.kwargs["json"]["voice_settings"], {
            "stability": 0.35, "similarity_boost": 0.9,
        })

    def test_v4_transient_failure_is_not_retried_to_avoid_duplicate_charges(self):
        cm, client = _fake_http_client([_response(503), _response(200)])
        with tempfile.TemporaryDirectory() as tmp:
            with patch("saasshorts.httpx.Client", return_value=cm):
                with self.assertRaisesRegex(Exception, "503"):
                    generate_voiceover("Привет", "key", os.path.join(tmp, "voice.mp3"), model_id="eleven_v4")
        self.assertEqual(client.post.call_count, 1)

    def test_v4_error_does_not_automatically_charge_for_v2(self):
        cm, client = _fake_http_client([_response(403)])
        with tempfile.TemporaryDirectory() as tmp:
            with patch("saasshorts.httpx.Client", return_value=cm):
                with self.assertRaisesRegex(Exception, "403"):
                    generate_voiceover("Привет", "key", os.path.join(tmp, "voice.mp3"), model_id="eleven_v4")
        self.assertEqual(client.post.call_count, 1)

    def test_selected_model_reaches_elevenlabs_provider(self):
        import saasshorts
        with patch("saasshorts.generate_voiceover", return_value="eleven_v4") as generate:
            result = saasshorts.generate_voiceover_with_fallback(
                "Привет", "unused.mp3", provider="elevenlabs", fal_key="",
                elevenlabs_key="key", elevenlabs_model="eleven_v4", log=lambda _: None,
            )
        self.assertEqual(generate.call_args.kwargs["model_id"], "eleven_v4")
        self.assertEqual(result["model"], "eleven_v4")

    def test_v4_settings_reach_elevenlabs_provider(self):
        import saasshorts
        with patch("saasshorts.generate_voiceover", return_value="eleven_v4") as generate:
            saasshorts.generate_voiceover_with_fallback(
                "Привет", "unused.mp3", provider="elevenlabs", fal_key="",
                elevenlabs_key="key", elevenlabs_model="eleven_v4",
                elevenlabs_stability=0.35, elevenlabs_similarity=0.9,
            )
        self.assertEqual(generate.call_args.kwargs["stability"], 0.35)
        self.assertEqual(generate.call_args.kwargs["similarity"], 0.9)

    def test_v4_auto_without_key_does_not_use_minimax(self):
        import saasshorts
        with patch("saasshorts.generate_voiceover_minimax") as minimax:
            with self.assertRaisesRegex(Exception, "ElevenLabs API key"):
                saasshorts.generate_voiceover_with_fallback(
                    "Привет", "unused.mp3", provider="auto", fal_key="key",
                    elevenlabs_key=None, elevenlabs_model="eleven_v4", log=lambda _: None,
                )
        minimax.assert_not_called()

    def test_api_request_accepts_v4_and_defaults_to_calm_v4(self):
        from app import SaaSGenerateRequest
        script = {"title": "Тест", "narration": "Привет"}
        self.assertEqual(SaaSGenerateRequest(script=script).elevenlabs_model, "eleven_v4")
        self.assertEqual(SaaSGenerateRequest(script=script).elevenlabs_stability, 0.65)
        self.assertEqual(SaaSGenerateRequest(script=script, elevenlabs_model="eleven_v4").elevenlabs_model, "eleven_v4")
        with self.assertRaises(ValueError):
            SaaSGenerateRequest(script=script, elevenlabs_model="eleven_v5")

    def test_api_rejects_out_of_range_v4_settings(self):
        from app import SaaSGenerateRequest
        script = {"title": "Тест", "narration": "Привет"}
        with self.assertRaises(ValueError):
            SaaSGenerateRequest(script=script, elevenlabs_stability=1.1)
        with self.assertRaises(ValueError):
            SaaSGenerateRequest(script=script, elevenlabs_similarity=-0.1)

    def test_signature_keeps_legacy_v3_cache_but_separates_v4(self):
        import saasshorts
        arguments = ("[curious] Привет", "elevenlabs", "voice1", "minimax1", "ru", "female")
        old = saasshorts._tts_signature(*arguments)
        self.assertEqual(old, saasshorts._tts_signature(*arguments, elevenlabs_model="eleven_v3"))
        self.assertNotEqual(old, saasshorts._tts_signature(*arguments, elevenlabs_model="eleven_v4"))

    def test_v4_settings_invalidate_only_v4_audio_cache(self):
        import saasshorts
        args = ("Привет", "elevenlabs", "anna", "minimax", "ru", "female")
        baseline = saasshorts._tts_signature(*args, elevenlabs_model="eleven_v4")
        changed = saasshorts._tts_signature(
            *args, elevenlabs_model="eleven_v4",
            elevenlabs_stability=0.35, elevenlabs_similarity=0.9,
        )
        self.assertNotEqual(baseline, changed)
        self.assertEqual(
            saasshorts._tts_signature(*args, elevenlabs_model="eleven_v3"),
            saasshorts._tts_signature(*args, elevenlabs_model="eleven_v3",
                                       elevenlabs_stability=0.35, elevenlabs_similarity=0.9),
        )


class SlicedAvatarShotVarietyTests(unittest.TestCase):
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
        # Положительный промпт — только то, что снимаем. Запрет говорящего рта
        # живёт в negative_prompt: в положительном слово «mouth» само приводило
        # в кадр говорящего человека.
        self.assertEqual(v3_shot["generation_prompt"], shot["generation_prompt"])
        self.assertNotIn("mouth", v3_shot["generation_prompt"])
        self.assertIn("moving lips", v3_shot["_negative_prompt"])
        # Оригинальный кадр не мутируется — им ещё пользуются субтитры
        self.assertEqual(shot["start"], 3.2)
        self.assertNotIn("_negative_prompt", shot)

    def test_builds_prompt_from_scene_when_missing(self):
        shot = {"visual_type": "broll", "scene": "hands pour coffee", "speech": "текст"}
        v3_shot = _broll_slice_shot(shot, 3.0)
        self.assertIn("hands pour coffee", v3_shot["generation_prompt"])
        self.assertNotIn("voiceover", v3_shot["generation_prompt"])
        self.assertIn("talking", v3_shot["_negative_prompt"])


class CaptionHighlightTests(unittest.TestCase):
    def test_prefers_script_keywords(self):
        word = _pick_caption_highlight_word("ХВАТИТ ЖДАТЬ ЧУДА", keywords=["чуда"])
        self.assertEqual(word, "ЧУДА")

    def test_falls_back_to_longest_heavy_word(self):
        word = _pick_caption_highlight_word("каждый понедельник заново")
        self.assertEqual(word, "ПОНЕДЕЛЬНИК")


class ScriptDurationAndHookTests(unittest.TestCase):
    def test_finalize_sanitizes_audio_tags_in_storyboard_shots(self):
        script = {
            "shots": [
                {"speech": "[confident] Первая фраза."},
                {"speech": "[whispering] Вторая фраза. [music]"},
            ],
        }

        _finalize_generated_script(script)

        self.assertEqual(script["shots"][0]["speech"], "Первая фраза.")
        self.assertEqual(script["shots"][1]["speech"], "[whispers] Вторая фраза.")
        self.assertEqual(
            script["full_narration"],
            "Первая фраза. [whispers] Вторая фраза.",
        )

    def test_estimate_ignores_audio_tag_words_and_counts_tag_pause_time(self):
        text = "[sighs] one two three four five six seven eight nine ten eleven ... [whispers]"
        self.assertEqual(_estimate_speech_duration(text), 7)

    def test_storyboard_narration_overwrites_stale_llm_duration(self):
        script = {
            "duration_seconds": 88,
            "full_narration": "stale narration",
            "shots": [
                {"speech": "one two three four five six seven eight nine ten eleven"},
                {"speech": "twelve thirteen"},
            ],
        }

        _finalize_generated_script(script)

        self.assertEqual(script["full_narration"], "one two three four five six seven eight nine ten eleven twelve thirteen")
        self.assertEqual(script["duration_seconds"], 6)
        self.assertEqual(script["duration_source"], "narration_estimate")

    def test_segment_narration_overwrites_stale_llm_duration(self):
        script = {
            "duration_seconds": 18,
            "full_narration": "stale narration",
            "segments": [{"narration": "one two three four five six seven eight nine ten eleven twelve thirteen"}],
        }

        _finalize_generated_script(script)

        self.assertEqual(script["full_narration"], "one two three four five six seven eight nine ten eleven twelve thirteen")
        self.assertEqual(script["duration_seconds"], 6)
        self.assertEqual(script["duration_source"], "narration_estimate")

    def test_script_spoken_text_prefers_storyboard_then_legacy_segments(self):
        self.assertEqual(
            _script_spoken_text({"shots": [{"speech": "First"}, {"speech": "Second"}], "full_narration": "stale"}),
            "First Second",
        )
        self.assertEqual(
            _script_spoken_text({"segments": [{"narration": "First"}, {"narration": "Second"}], "full_narration": "stale"}),
            "First Second",
        )

    def test_duplicate_openings_request_one_retry_and_return_diverse_batch(self):
        responses = iter([
            MagicMock(text='[{"hook_type":"pain_question","segments":[{"narration":"Exact pain question now"}]},{"hook_type":"data_point","segments":[{"narration":"Exact pain question later"}]}]'),
            MagicMock(text='[{"hook_type":"mistake_prohibition","segments":[{"narration":"Specific mistake costs money"}]},{"hook_type":"data_point","segments":[{"narration":"Three data points prove it"}]}]'),
        ])
        calls = 0

        def ask():
            nonlocal calls
            calls += 1
            return next(responses)

        scripts = _request_gemini_script_batch(
            ask,
            num_scripts=2,
            require_shots=False,
            label="script",
            batch_validator=_validate_script_batch_hooks,
        )

        self.assertEqual(calls, 2)
        self.assertEqual(_hook_opening(scripts[0]), "specific mistake costs")

    def test_diverse_openings_accept_first_batch_without_retry(self):
        response = MagicMock(text='[{"hook_type":"mistake_prohibition","segments":[{"narration":"Specific mistake costs money"}]},{"hook_type":"data_point","segments":[{"narration":"Three data points prove it"}]}]')
        ask = MagicMock(return_value=response)

        scripts = _request_gemini_script_batch(
            ask,
            num_scripts=2,
            require_shots=False,
            label="script",
            batch_validator=_validate_script_batch_hooks,
        )

        self.assertEqual(ask.call_count, 1)
        self.assertEqual(len(scripts), 2)

    def test_canned_preamble_requests_one_retry(self):
        responses = iter([
            MagicMock(text='[{"segments":[{"narration":"Stop stop stop, this costs you money"}]}]'),
            MagicMock(text='[{"segments":[{"narration":"Specific mistake costs money"}]}]'),
        ])
        ask = MagicMock(side_effect=lambda: next(responses))

        scripts = _request_gemini_script_batch(
            ask,
            num_scripts=1,
            require_shots=False,
            label="script",
            batch_validator=_validate_script_batch_hooks,
        )

        self.assertEqual(ask.call_count, 2)
        self.assertEqual(_hook_opening(scripts[0]), "specific mistake costs")

    def test_supplied_hook_must_be_the_first_script_opening(self):
        scripts = [
            {"hook_type": "result_first", "segments": [{"narration": "[sighs] First claim is specific"}]},
            {"hook_type": "data_point", "segments": [{"narration": "Three data points prove it"}]},
        ]

        self.assertEqual(_validate_script_batch_hooks(scripts, supplied_hook="First claim"), [])
        scripts[0]["segments"][0]["narration"] = "A different opening entirely"
        self.assertTrue(_validate_script_batch_hooks(scripts, supplied_hook="First claim"))

    def test_duplicate_hook_type_requests_one_retry(self):
        responses = iter([
            MagicMock(text='[{"hook_type":"result_first","segments":[{"narration":"Revenue doubled after this"}]},{"hook_type":"result_first","segments":[{"narration":"Invoices clear faster now"}]}]'),
            MagicMock(text='[{"hook_type":"result_first","segments":[{"narration":"Revenue doubled after this"}]},{"hook_type":"mistake_prohibition","segments":[{"narration":"Stop approving invoices manually"}]}]'),
        ])
        ask = MagicMock(side_effect=lambda: next(responses))

        scripts = _request_gemini_script_batch(
            ask,
            num_scripts=2,
            require_shots=False,
            label="script",
            batch_validator=_validate_script_batch_hooks,
        )

        self.assertEqual(ask.call_count, 2)
        self.assertEqual([script["hook_type"] for script in scripts], ["result_first", "mistake_prohibition"])

    def test_distinct_supported_hook_types_accept_first_batch(self):
        ask = MagicMock(return_value=MagicMock(text='[{"hook_type":"result_first","segments":[{"narration":"Revenue doubled after this"}]},{"hook_type":"data_point","segments":[{"narration":"Three numbers expose the leak"}]}]'))

        scripts = _request_gemini_script_batch(
            ask,
            num_scripts=2,
            require_shots=False,
            label="script",
            batch_validator=_validate_script_batch_hooks,
        )

        self.assertEqual(ask.call_count, 1)
        self.assertEqual(len(scripts), 2)

    def test_extended_hook_taxonomy_accepts_lists_secrets_and_identity(self):
        scripts = [
            {"hook_type": "list_specific", "segments": [{"narration": "Three dinner rules simplify evenings"}]},
            {"hook_type": "secret_reveal", "segments": [{"narration": "The hidden reset starts at lunch"}]},
            {"hook_type": "identity_callout", "segments": [{"narration": "Busy mothers need a smaller fallback"}]},
        ]

        self.assertEqual(_validate_script_batch_hooks(scripts), [])

    def test_substantive_stop_prohibition_is_not_canned_filler(self):
        scripts = [{"segments": [{"narration": "Stop approving invoices manually"}]}]
        self.assertEqual(_validate_script_batch_hooks(scripts), [])

    def test_filler_phrases_and_hyphenated_stop_repetition_are_rejected(self):
        for narration in (
            "Watch until the end to learn why",
            "Досмотри до конца, это важно",
            "Стоп-стоп-стоп, ты теряешь деньги",
        ):
            with self.subTest(narration=narration):
                issues = _validate_script_batch_hooks([{"segments": [{"narration": narration}]}])
                self.assertTrue(issues)


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
        # Граница в паузе между "три" (1.4) и "четыре" (2.4), у самого начала
        # второй фразы — чтобы кадр 2 открывался речью, а не тишиной.
        self.assertAlmostEqual(slices[0]["end"], 2.32, delta=0.05)

    def test_tag_only_words_do_not_skew_weights(self):
        shots = [
            {"shot_number": 1, "speech": "[excited] [whispers] Раз два три"},
            {"shot_number": 2, "speech": "Четыре пять шесть"},
        ]
        slices, _ = _align_shots_to_voiceover(shots, self._words(), 4.0)
        # Без учёта тегов веса равные (3 и 3) — граница остаётся в паузе
        self.assertAlmostEqual(slices[0]["end"], 2.32, delta=0.05)


if __name__ == "__main__":
    unittest.main()

import json
import os
import tempfile
import unittest
import asyncio
from unittest.mock import MagicMock, patch

import saasshorts
from saasshorts import (
    build_custom_script,
    build_kling_v3_storyboard_request,
    generate_full_video,
    generate_storyboard_ass_subtitles,
    generate_storyboard_video,
    kling_v3_cost_per_second,
    storyboard_video_cost_per_second,
    normalize_storyboard_shots,
    split_storyboard_shots,
)


def _charge(kwargs, output_path):
    """Фейк рисовальщика тратит деньги так же, как настоящий: считает обращения.

    Смета превью берётся из числа платных запросов к модели, а не из числа
    удачных кадров — пустой кадр fal тарифицирует наравне с картинкой. Уже
    нарисованный кадр настоящий `_flux_reference_frame` отдаёт из кэша, не
    обращаясь к модели, поэтому второй ракурс на пяти кадрах денег не стоит.
    """
    billing = kwargs.get("billing")
    if billing is not None and not os.path.exists(output_path):
        billing["calls"] = billing.get("calls", 0) + 1


class SaaSGeminiJsonRecoveryTests(unittest.TestCase):
    def test_repair_recovers_missing_comma_between_values(self):
        # The exact failure users hit: "Expecting ',' delimiter" — a dropped
        # comma between two objects (and two fields) on adjacent lines.
        bad_array = '[\n  {"a": 1, "n": "x"}\n  {"b": 2}\n]'
        with self.assertRaises(json.JSONDecodeError):
            json.loads(bad_array)
        self.assertEqual(
            json.loads(saasshorts._repair_gemini_json(bad_array)),
            [{"a": 1, "n": "x"}, {"b": 2}],
        )
        bad_fields = '{\n  "a": "x"\n  "b": "y"\n}'
        self.assertEqual(
            json.loads(saasshorts._repair_gemini_json(bad_fields)),
            {"a": "x", "b": "y"},
        )

    def test_repair_strips_trailing_comma(self):
        self.assertEqual(json.loads(saasshorts._repair_gemini_json('[{"a":1},]')), [{"a": 1}])

    def test_salvage_keeps_clean_objects_and_skips_broken_ones(self):
        # Truncated tail: keep every object that closed cleanly.
        truncated = '[{"a":1},{"b":2},{"c": "unterminated'
        self.assertEqual(saasshorts._salvage_json_array(truncated), [{"a": 1}, {"b": 2}])
        # One irreparable object in the middle must not drop its neighbours.
        mixed = '[{"a":1}\n{"b":2 "c":3}\n{"d":4}]'
        self.assertEqual(saasshorts._salvage_json_array(mixed), [{"a": 1}, {"d": 4}])


def _storyboard_shot(number, speech):
    return {
        "shot_number": number, "start": 0, "end": 3, "role": "hook",
        "scene": f"Сцена {number}", "camera": "Крупный план", "actor_action": "смотрит в камеру",
        "transition": "cut", "speech": speech, "emotion": "excited", "overlay_text": "o",
        "visual_type": "talking", "generation_prompt": "vertical 9:16 realistic",
    }


def _storyboard_answer(title, shot_count):
    script = {
        "title": title, "format": "storyboard_v3", "duration_seconds": 18,
        "shots": [_storyboard_shot(i, f"Реплика {i}") for i in range(1, shot_count + 1)],
        "actor_description": "a woman in her 30s", "hashtags": ["#reels"],
    }
    return json.dumps([script], ensure_ascii=False)


class SaaSBrollSpeechAlignmentTests(unittest.TestCase):
    def _scripts_with_broll(self):
        return [{
            "title": "Metabolism",
            "actor_description": "a woman in her 30s",
            "shots": [
                {
                    "shot_number": 1, "visual_type": "talking", "role": "hook",
                    "scene": "Living room", "camera": "close-up", "actor_action": "speaks",
                    "speech": "You are not failing because your body changed.",
                    "overlay_text": "Not your fault", "start": 0, "end": 3,
                    "generation_prompt": "woman talking to camera",
                },
                {
                    "shot_number": 2, "visual_type": "broll", "role": "explanation",
                    "scene": "Stylish dining table", "camera": "macro top-down", "actor_action": "hands slice avocado",
                    "speech": "Our metabolism naturally slows by a few percent every ten years.",
                    "overlay_text": "Metabolism changes", "start": 3, "end": 6,
                    "generation_prompt": "vertical 9:16, hands slicing avocado on a wooden board",
                },
                {
                    "shot_number": 3, "visual_type": "talking", "role": "solution",
                    "scene": "Window", "camera": "medium", "actor_action": "explains calmly",
                    "speech": "That is why the old rules stop working for you.",
                    "overlay_text": "New rules", "start": 6, "end": 9,
                    "generation_prompt": "woman explaining by window",
                },
            ],
        }]

    def _refine(self, scripts, reply, language=None):
        from types import SimpleNamespace

        class FakeClient:
            def __init__(self, api_key=None):
                pass

        with patch("google.genai.Client", FakeClient), \
             patch("saasshorts._generate_gemini_content", return_value=SimpleNamespace(
                 text=json.dumps(reply)
             )) as generate:
            kwargs = {"language": language} if language is not None else {}
            result = saasshorts.refine_storyboard_broll_alignment(scripts, "key", **kwargs)
        return result, generate

    def test_replaces_unrelated_avocado_with_speech_grounded_visual(self):
        scripts = self._scripts_with_broll()
        original_speech = scripts[0]["shots"][1]["speech"]
        result, _ = self._refine(scripts, [{
            "script_index": 0, "shot_number": 2, "decision": "replace",
            "scene": "One person walks the same route in three calm life stages, shown from behind.",
            "camera": "Side tracking medium shot, gentle match cuts.",
            "actor_action": "A faceless person keeps walking as the pace subtly slows.",
            "generation_prompt": "vertical 9:16 realistic UGC b-roll, faceless woman seen from behind walking the same path across life stages, pace subtly slows, side tracking shot, natural light, no readable text, no watermark",
            "reason": "The walking pace is a direct visual analogy for gradual metabolic change.",
        }])

        shot = result[0]["shots"][1]
        self.assertEqual(shot["speech"], original_speech)
        self.assertNotIn("avocado", shot["generation_prompt"].lower())
        self.assertIn("pace subtly slows", shot["generation_prompt"])
        self.assertEqual(shot["_prompt_source_scene"], shot["scene"])
        self.assertEqual(shot["action"], shot["actor_action"])

    def test_review_request_contains_current_and_neighboring_speech(self):
        scripts = self._scripts_with_broll()
        _, generate = self._refine(scripts, [{"script_index": 0, "shot_number": 2, "decision": "keep"}])

        request = generate.call_args.kwargs["contents"][0]
        self.assertIn(scripts[0]["shots"][0]["speech"], request)
        self.assertIn(scripts[0]["shots"][1]["speech"], request)
        self.assertIn(scripts[0]["shots"][2]["speech"], request)

    def test_keep_decision_preserves_the_editable_shot(self):
        scripts = self._scripts_with_broll()
        before = dict(scripts[0]["shots"][1])

        result, _ = self._refine(scripts, [{"script_index": 0, "shot_number": 2, "decision": "keep"}])

        self.assertEqual(result[0]["shots"][1], before)

    def test_malformed_or_failed_refinement_keeps_scripts(self):
        scripts = self._scripts_with_broll()
        before = json.loads(json.dumps(scripts))

        class FakeClient:
            def __init__(self, api_key=None):
                pass

        with patch("google.genai.Client", FakeClient), \
             patch("saasshorts._generate_gemini_content", side_effect=RuntimeError("temporary failure")):
            result = saasshorts.refine_storyboard_broll_alignment(scripts, "key")

        self.assertEqual(result, before)

    def test_malformed_refinement_json_keeps_scripts(self):
        scripts = self._scripts_with_broll()
        before = json.loads(json.dumps(scripts))

        class FakeClient:
            def __init__(self, api_key=None):
                pass

        with patch("google.genai.Client", FakeClient), \
             patch("saasshorts._generate_gemini_content", return_value=MagicMock(text="not json")):
            result = saasshorts.refine_storyboard_broll_alignment(scripts, "key")

        self.assertEqual(result, before)

    def test_invalid_field_types_are_ignored_while_a_valid_sibling_is_applied(self):
        scripts = self._scripts_with_broll()
        scripts[0]["shots"].append({
            "shot_number": 4, "visual_type": "broll", "role": "proof",
            "scene": "Generic scale", "camera": "close-up", "actor_action": "needle moves",
            "speech": "The change is gradual, not a sudden collapse.",
            "overlay_text": "Gradual change", "start": 9, "end": 12,
            "generation_prompt": "a generic bathroom scale",
        })
        invalid_before = dict(scripts[0]["shots"][1])

        result, _ = self._refine(scripts, [
            {
                "script_index": 0, "shot_number": 2, "decision": "replace",
                "scene": {"unexpected": "object"},
                "camera": ["unexpected", "array"],
                "actor_action": 42,
                "generation_prompt": ["not", "a", "string"],
            },
            {
                "script_index": 0, "shot_number": 4, "decision": "replace",
                "scene": "The same pendulum loses speed almost imperceptibly.",
                "camera": "Locked medium close-up.",
                "actor_action": "The pendulum continues moving at a subtly slower pace.",
                "generation_prompt": "vertical 9:16 realistic UGC b-roll, one pendulum gradually slowing, locked medium close-up, natural light, no readable text, no watermark",
            },
        ])

        self.assertEqual(result[0]["shots"][1], invalid_before)
        self.assertIn("pendulum gradually slowing", result[0]["shots"][3]["generation_prompt"])
        self.assertEqual(
            result[0]["shots"][3]["action"],
            "The pendulum continues moving at a subtly slower pace.",
        )

    def test_null_or_missing_optional_fields_preserve_existing_shot_values(self):
        scripts = self._scripts_with_broll()
        original_camera = scripts[0]["shots"][1]["camera"]
        original_action = scripts[0]["shots"][1]["actor_action"]
        scripts[0]["shots"][1]["action"] = original_action

        result, _ = self._refine(scripts, [{
            "script_index": 0, "shot_number": 2, "decision": "replace",
            "scene": "A faceless walker keeps the same route as their pace gradually slows.",
            "camera": None,
            "generation_prompt": "vertical 9:16 realistic UGC b-roll, faceless walker seen from behind gradually slowing on the same path, natural light, no readable text, no watermark",
        }])

        shot = result[0]["shots"][1]
        self.assertEqual(
            shot["scene"],
            "A faceless walker keeps the same route as their pace gradually slows.",
        )
        self.assertIn("faceless walker seen from behind", shot["generation_prompt"])
        self.assertEqual(shot["camera"], original_camera)
        self.assertEqual(shot["actor_action"], original_action)
        self.assertEqual(shot["action"], original_action)

    def test_russian_ui_fields_are_requested_while_generation_prompt_stays_english(self):
        scripts = self._scripts_with_broll()
        result, generate = self._refine(scripts, [{
            "script_index": 0, "shot_number": 2, "decision": "replace",
            "scene": "Один человек идёт по одной дорожке в разные периоды жизни.",
            "camera": "Средний план сбоку, плавное сопровождение.",
            "actor_action": "Человек со спины продолжает идти, постепенно замедляя шаг.",
            "generation_prompt": "vertical 9:16 realistic UGC b-roll, faceless person seen from behind gradually slowing their walking pace, side tracking shot, natural light, no readable text, no watermark",
        }], language="ru")

        request = generate.call_args.kwargs["contents"][0]
        self.assertIn("Target UI language: Russian", request)
        shot = result[0]["shots"][1]
        self.assertEqual(shot["scene"], "Один человек идёт по одной дорожке в разные периоды жизни.")
        self.assertEqual(shot["camera"], "Средний план сбоку, плавное сопровождение.")
        self.assertEqual(
            shot["actor_action"],
            "Человек со спины продолжает идти, постепенно замедляя шаг.",
        )
        self.assertIn("faceless person seen from behind", shot["generation_prompt"])

    def test_multiple_broll_candidates_share_one_model_request(self):
        scripts = self._scripts_with_broll()
        second_script = self._scripts_with_broll()[0]
        second_script["shots"][1]["speech"] = "Stress can also change the rhythm of appetite."
        scripts.append(second_script)

        _, generate = self._refine(scripts, [
            {"script_index": 0, "shot_number": 2, "decision": "keep"},
            {"script_index": 1, "shot_number": 2, "decision": "keep"},
        ])

        self.assertEqual(generate.call_count, 1)
        request = generate.call_args.kwargs["contents"][0]
        self.assertIn("Our metabolism naturally slows by a few percent every ten years.", request)
        self.assertIn("Stress can also change the rhythm of appetite.", request)

    def test_no_broll_or_key_makes_zero_model_calls(self):
        scripts = self._scripts_with_broll()
        scripts[0]["shots"][1]["visual_type"] = "talking"
        no_key_scripts = self._scripts_with_broll()
        with patch("google.genai.Client") as client, \
             patch("saasshorts._generate_gemini_content") as generate:
            self.assertIs(saasshorts.refine_storyboard_broll_alignment(scripts, "key"), scripts)
            self.assertIs(saasshorts.refine_storyboard_broll_alignment(no_key_scripts, ""), no_key_scripts)
        client.assert_not_called()
        generate.assert_not_called()

    def test_generate_scripts_invokes_one_batched_refinement_for_broll(self):
        answer = json.dumps([{
            "title": "B-roll", "hook_type": "result_first", "shots": [
                {**_storyboard_shot(1, "Start with the useful result."), "visual_type": "talking"},
                {**_storyboard_shot(2, "This claim needs an insert shot."), "visual_type": "broll"},
            ],
        }])
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(text=answer)
        with patch("google.genai.Client", return_value=client), \
             patch("saasshorts.refine_storyboard_broll_alignment", side_effect=lambda scripts, *_args, **_kwargs: scripts) as refine, \
             patch("builtins.print"):
            saasshorts.generate_scripts(
                analysis={"product_name": "Test"}, gemini_key="key", num_scripts=1,
                script_format="storyboard_v3", language="ru",
            )
        refine.assert_called_once()
        self.assertEqual(refine.call_args.kwargs["language"], "ru")

    def test_storyboard_prompt_no_longer_bans_all_people_from_broll(self):
        source = saasshorts.generate_scripts.__code__.co_consts
        prompt_source = "\n".join(value for value in source if isinstance(value, str))
        self.assertNotIn("strictly NO faces and NO people", prompt_source)


def _cut_off_storyboard_answer(complete_shots=3):
    """Gemini's answer as it arrives when it runs out of output budget.

    It stops right where the next value should start — the "Expecting value"
    parse error users hit, with no closing bracket anywhere in the answer.
    """
    shots = ",\n      ".join(
        json.dumps(_storyboard_shot(i, f"Реплика {i}"), ensure_ascii=False)
        for i in range(1, complete_shots + 1)
    )
    return (
        '[\n  {\n    "title": "Ты срываешься вечером не из-за слабости",\n'
        '    "format": "storyboard_v3",\n    "shots": [\n      '
        + shots
        + ',\n      {\n        "shot_number": %d,\n        "camera": ' % (complete_shots + 1)
    )


class SaaSTruncatedGeminiAnswerTests(unittest.TestCase):
    """Ответ Gemini обрывается на полуслове — сценарий не должен падать целиком."""

    def _generate(self, answers):
        responses = []
        for answer in answers:
            if isinstance(answer, Exception):
                responses.append(answer)
                continue
            response = MagicMock()
            response.text = answer
            responses.append(response)
        client = MagicMock()
        client.models.generate_content.side_effect = responses
        with patch("google.genai.Client", return_value=client):
            scripts = saasshorts.generate_scripts(
                analysis={"product_name": "Моя Форма"},
                gemini_key="key",
                num_scripts=1,
                script_format="storyboard_v3",
                language="ru",
            )
        return scripts, client.models.generate_content.call_count

    def test_cut_off_answer_keeps_the_shots_that_arrived(self):
        cut_off = _cut_off_storyboard_answer(complete_shots=3)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(cut_off)

        scripts, note = saasshorts._parse_gemini_script_array(cut_off)

        self.assertEqual(note, saasshorts._JSON_TRUNCATED)
        self.assertEqual(len(scripts), 1)
        self.assertEqual([shot["shot_number"] for shot in scripts[0]["shots"]], [1, 2, 3])

    def test_asks_gemini_once_more_when_the_answer_was_cut_off(self):
        # Пересъёмка платная: лучше переспросить, чем молча отдать огрызок сценария.
        scripts, calls = self._generate(
            [_cut_off_storyboard_answer(complete_shots=2), _storyboard_answer("Полный", 6)]
        )

        self.assertEqual(calls, 2)
        self.assertEqual([s["title"] for s in scripts], ["Полный"])
        self.assertEqual(len(scripts[0]["shots"]), 6)

    def test_keeps_the_recovered_shots_when_the_retry_comes_back_worse(self):
        scripts, calls = self._generate([_cut_off_storyboard_answer(complete_shots=3), ""])

        self.assertEqual(calls, 2)
        self.assertEqual(len(scripts[0]["shots"]), 3)

    def test_a_failing_retry_does_not_throw_away_the_recovered_shots(self):
        scripts, calls = self._generate(
            [_cut_off_storyboard_answer(complete_shots=3), RuntimeError("400 INVALID_ARGUMENT")]
        )

        self.assertEqual(calls, 2)
        self.assertEqual(len(scripts[0]["shots"]), 3)

    def test_a_clean_answer_is_not_paid_for_twice(self):
        scripts, calls = self._generate([_storyboard_answer("Чистый", 5)])

        self.assertEqual(calls, 1)
        self.assertEqual(len(scripts[0]["shots"]), 5)

    def test_scripts_without_shots_are_not_offered_as_storyboards(self):
        empty = json.dumps([{"title": "Без кадров", "shots": []}], ensure_ascii=False)
        scripts, calls = self._generate([empty, _storyboard_answer("Со кадрами", 4)])

        self.assertEqual(calls, 2)
        self.assertEqual([s["title"] for s in scripts], ["Со кадрами"])

    def test_two_broken_answers_fail_with_a_message_a_person_can_act_on(self):
        # Раньше пользователю в лицо прилетали 500 символов сырого JSON.
        with self.assertRaises(Exception) as raised:
            self._generate(['[{"title": "Обрыв', '[{"title": "Обрыв'])

        self.assertNotIn("{", str(raised.exception))
        self.assertIn("try generating again", str(raised.exception))

    def test_failure_message_points_at_the_break_not_at_the_head(self):
        # Обрыв случается на 6000-м символе — первые 500 символов о нём молчат.
        note = saasshorts._describe_gemini_json_failure(_cut_off_storyboard_answer(complete_shots=1))

        self.assertIn("ANSWER ENDS HERE", note)
        self.assertIn('"camera"', note)


class SaaSFillShotDetailsTests(unittest.TestCase):
    """Восстановленный кадр несёт только реплику — сцену/камеру дозаполняет ИИ."""

    SCRIPT = {"title": "Диеты после 30", "actor_description": "a woman in her 30s"}

    def _fill(self, shots, reply):
        from types import SimpleNamespace

        class FakeClient:
            def __init__(self, api_key=None):
                pass

        with patch("google.genai.Client", FakeClient), \
             patch("saasshorts._generate_gemini_content",
                   return_value=SimpleNamespace(text=json.dumps(reply, ensure_ascii=False))):
            return saasshorts.fill_storyboard_shot_details(self.SCRIPT, shots, "key")

    def test_missing_fields_are_filled_and_prompt_built(self):
        shots = [{"shot_number": 3, "speech": "Кортизол растет, метаболизм падает."}]
        out = self._fill(shots, [{
            "shot_number": 3,
            "scene": "Светлая кухня, героиня у окна.",
            "camera": "Средний план, лёгкое приближение.",
            "actor_action": "Смотрит в камеру и объясняет.",
            "role": "explanation",
            "emotion": "confident",
            "transition": "cut",
            "visual_type": "talking",
            "generation_prompt": "a woman explains to camera in a bright kitchen",
        }])
        self.assertEqual(out[0]["scene"], "Светлая кухня, героиня у окна.")
        self.assertEqual(out[0]["camera"], "Средний план, лёгкое приближение.")
        self.assertEqual(out[0]["visual_type"], "talking")
        # Действие дублируется в legacy-поле, которое читает генерация.
        self.assertEqual(out[0]["action"], out[0]["actor_action"])
        # Промпт проходит через общий билдер — формат на месте, запреты нет:
        # они уходят в negative_prompt запроса.
        self.assertIn("vertical 9:16", out[0]["generation_prompt"])
        self.assertNotIn("no burned-in text", out[0]["generation_prompt"])
        self.assertEqual(out[0]["_prompt_source_scene"], out[0]["scene"])

    def test_existing_values_are_not_overwritten(self):
        shots = [{
            "shot_number": 1,
            "speech": "Так, стоп.",
            "scene": "Моя сцена",
            "camera": "Моя камера",
        }]
        out = self._fill(shots, [{
            "shot_number": 1, "scene": "ИИ сцена", "camera": "ИИ камера",
            "actor_action": "действие", "generation_prompt": "prompt",
        }])
        self.assertEqual(out[0]["scene"], "Моя сцена")
        self.assertEqual(out[0]["camera"], "Моя камера")
        self.assertEqual(out[0]["actor_action"], "действие")

    def test_hand_pinned_prompt_is_left_alone(self):
        shots = [{"shot_number": 1, "speech": "Реплика", "prompt_manual": True,
                  "generation_prompt": "my own prompt"}]
        out = self._fill(shots, [{"shot_number": 1, "scene": "сцена",
                                  "generation_prompt": "ai prompt"}])
        self.assertEqual(out[0]["generation_prompt"], "my own prompt")

    def test_without_a_key_shots_come_back_untouched(self):
        shots = [{"shot_number": 1, "speech": "Реплика"}]
        self.assertIs(saasshorts.fill_storyboard_shot_details({}, shots, ""), shots)


class SaaSExistingShotFrameTests(unittest.TestCase):
    """Кадр, за который уже заплатили, не должен генериться заново."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.job = os.path.join(self.root, "saas_old")
        os.makedirs(self.job)
        self.frame = os.path.join(self.job, "frame_01.png")
        from PIL import Image
        import numpy as np
        rng = np.random.default_rng(7)
        Image.fromarray(rng.integers(0, 256, (64, 36, 3), dtype="uint8"), "RGB").save(self.frame)

    def tearDown(self):
        self.tmp.cleanup()

    def test_frame_found_via_stored_path(self):
        found = saasshorts._existing_shot_frame({"image_path": self.frame}, self.root)
        self.assertEqual(found, self.frame)

    def test_frame_found_via_videos_url_of_an_earlier_job(self):
        shot = {"local_url": "/videos/saas_old/frame_01.png"}
        self.assertEqual(saasshorts._existing_shot_frame(shot, self.root), self.frame)

    def test_missing_or_blank_frame_is_not_reused(self):
        self.assertEqual(saasshorts._existing_shot_frame({"image_path": "/nope.png"}, self.root), "")
        blank = os.path.join(self.job, "blank.png")
        from PIL import Image
        import numpy as np
        Image.fromarray(np.zeros((64, 36, 3), dtype="uint8"), "RGB").save(blank)
        self.assertEqual(saasshorts._existing_shot_frame({"image_path": blank}, self.root), "")

    def test_shot_without_any_frame_reference(self):
        self.assertEqual(saasshorts._existing_shot_frame({"speech": "привет"}, self.root), "")


class SaaSAdoptJobArtifactsTests(unittest.TestCase):
    """Пересъёмка готового ролика не должна оплачивать снятые кадры заново."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = os.path.join(self.tmp.name, "saas_old")
        self.target = os.path.join(self.tmp.name, "saas_new")
        os.makedirs(self.source)
        for name, body in (
            ("moya_forma_avatar_01.mp4", "clip"),
            ("moya_forma_avatar_01.mp4.meta.json", '{"payload": {"prompt": "p"}}'),
            ("moya_forma_actor_scene_01.png", "frame"),
            ("moya_forma_voice.mp3", "voice"),
            ("moya_forma_storyboard_final.mp4", "final cut"),
            ("moya_forma_final_v2.mp4", "lip-synced version"),
            ("gallery_metadata.json", "{}"),
        ):
            with open(os.path.join(self.source, name), "w", encoding="utf-8") as f:
                f.write(body)

    def tearDown(self):
        self.tmp.cleanup()

    def test_paid_artifacts_are_carried_over_without_the_finished_cut(self):
        copied = saasshorts.adopt_job_artifacts(self.source, self.target, log=lambda *_: None)
        adopted = set(os.listdir(self.target))
        self.assertEqual(copied, 4)
        self.assertIn("moya_forma_avatar_01.mp4", adopted)
        self.assertIn("moya_forma_avatar_01.mp4.meta.json", adopted)
        self.assertIn("moya_forma_actor_scene_01.png", adopted)
        self.assertIn("moya_forma_voice.mp3", adopted)
        # Прошлый ролик остаётся в своём джобе: иначе новая версия затрёт старую.
        # Это касается и пересобранных липсинком версий (_final_v2.mp4).
        self.assertNotIn("moya_forma_storyboard_final.mp4", adopted)
        self.assertNotIn("moya_forma_final_v2.mp4", adopted)
        self.assertNotIn("gallery_metadata.json", adopted)

    def test_adopt_log_names_voice_artifacts_as_voice_not_frames(self):
        logs = []

        saasshorts.adopt_job_artifacts(
            self.source,
            self.target,
            source_label="прослушанной озвучки",
            log=logs.append,
        )

        self.assertTrue(any(line.startswith("[озвучка]") for line in logs))
        self.assertFalse(any(line.startswith("[кадры]") for line in logs))
        self.assertFalse(any("изменённые кадры" in line for line in logs))

    def test_renamed_title_keeps_the_cache_hitting(self):
        with open(
            os.path.join(self.source, "moya_forma_voice_manifest.json"),
            "w",
            encoding="utf-8",
        ) as manifest_file:
            json.dump({
                "shots": [{
                    "shot_number": 1,
                    "signature": "same-voice",
                    "piece": "moya_forma_speech_01.wav",
                }],
            }, manifest_file)
        with open(os.path.join(self.source, "moya_forma_speech_01.wav"), "wb") as piece:
            piece.write(b"voice piece")

        saasshorts.adopt_job_artifacts(
            self.source, self.target,
            source_slug="moya_forma", target_slug="novaya_forma",
            log=lambda *_: None,
        )
        adopted = set(os.listdir(self.target))
        # Кэш ищет файлы по новому слагу — иначе всё снимается заново за деньги.
        self.assertIn("novaya_forma_avatar_01.mp4", adopted)
        self.assertIn("novaya_forma_avatar_01.mp4.meta.json", adopted)
        self.assertIn("novaya_forma_voice.mp3", adopted)
        self.assertNotIn("moya_forma_avatar_01.mp4", adopted)
        with open(
            os.path.join(self.target, "novaya_forma_voice_manifest.json"),
            encoding="utf-8",
        ) as manifest_file:
            manifest = json.load(manifest_file)
        self.assertEqual(
            manifest["shots"][0]["piece"],
            "novaya_forma_speech_01.wav",
        )

    def test_existing_file_in_the_new_job_is_never_overwritten(self):
        os.makedirs(self.target)
        keep = os.path.join(self.target, "moya_forma_avatar_01.mp4")
        with open(keep, "w", encoding="utf-8") as f:
            f.write("newer clip")
        saasshorts.adopt_job_artifacts(self.source, self.target, log=lambda *_: None)
        with open(keep, encoding="utf-8") as f:
            self.assertEqual(f.read(), "newer clip")

    def test_missing_source_job_is_not_an_error(self):
        self.assertEqual(
            saasshorts.adopt_job_artifacts(os.path.join(self.tmp.name, "gone"), self.target),
            0,
        )


class SaaSForgetShotArtifactsTests(unittest.TestCase):
    """«Переснять» должно пробивать кэш: иначе кадр вернётся тот же самый."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.job = self.tmp.name
        for name in (
            "slug_avatar_01.mp4",
            "slug_avatar_01.mp4.meta.json",
            "slug_avatar_01_base.mp4",
            "slug_avatar_01_base_fal.json",
            "slug_actor_scene_01.png",
            "slug_slice_01.mp3",
            "slug_avatar_02.mp4",
            "slug_actor_scene_02.png",
        ):
            with open(os.path.join(self.job, name), "w", encoding="utf-8") as f:
                f.write("x")
        self.shots = [
            {
                "shot_number": 1,
                "clip_url": "/videos/saas_old/slug_avatar_01.mp4",
                "preview_frame_url": "/videos/saas_old/slug_thumb_01.jpg",
                "image_path": "/app/output/saas_old/slug_actor_scene_01.png",
                "_render_files": ["slug_avatar_01.mp4", "slug_actor_scene_01.png", "slug_slice_01.mp3"],
            },
            {
                "shot_number": 2,
                "clip_url": "/videos/saas_old/slug_avatar_02.mp4",
                "_render_files": ["slug_avatar_02.mp4", "slug_actor_scene_02.png"],
            },
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_marked_shot_loses_its_clip_frame_and_sidecars(self):
        saasshorts.forget_shot_artifacts(self.job, self.shots, [1], log=lambda *_: None)
        left = set(os.listdir(self.job))
        for gone in (
            "slug_avatar_01.mp4",
            "slug_avatar_01.mp4.meta.json",
            "slug_avatar_01_base.mp4",
            "slug_avatar_01_base_fal.json",
            "slug_actor_scene_01.png",
            "slug_slice_01.mp3",
        ):
            self.assertNotIn(gone, left)
        # Соседний кадр не трогаем — он оплачен и не менялся.
        self.assertIn("slug_avatar_02.mp4", left)
        self.assertIn("slug_actor_scene_02.png", left)

    def test_urls_of_the_previous_job_are_cleared(self):
        saasshorts.forget_shot_artifacts(self.job, self.shots, [1], log=lambda *_: None)
        # Иначе кадр «нашёлся бы» по копии, оставшейся в каталоге прошлого джоба.
        for key in ("clip_url", "preview_frame_url", "image_path", "_render_files"):
            self.assertNotIn(key, self.shots[0])
        self.assertEqual(self.shots[1]["clip_url"], "/videos/saas_old/slug_avatar_02.mp4")

    def test_empty_selection_changes_nothing(self):
        before = set(os.listdir(self.job))
        self.assertEqual(saasshorts.forget_shot_artifacts(self.job, self.shots, [], log=lambda *_: None), [])
        self.assertEqual(set(os.listdir(self.job)), before)
        self.assertIn("clip_url", self.shots[0])


class SaaSShotRenderFilesTests(unittest.TestCase):
    """Кадр должен помнить, из каких файлов он снят, — иначе нечего пересдавать."""

    def test_split_shot_records_every_clip_frame_and_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            clips = []
            for index in (1, 2):
                path = os.path.join(tmp, f"slug_avatar_{index:02d}.mp4")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("clip")
                clips.append({
                    "path": path,
                    "shot": {"shot_number": 1},
                    "reference_image": os.path.join(tmp, f"slug_actor_scene_{index:02d}.png"),
                    "audio_slice": os.path.join(tmp, f"slug_slice_{index:02d}.mp3"),
                })
            shots = [{"shot_number": 1}]
            with patch.object(saasshorts.subprocess, "run"):
                saasshorts._attach_shot_previews(shots, clips, tmp, "slug", log=lambda *_: None)

        self.assertEqual(shots[0]["clip_url"], "/videos/" + os.path.basename(tmp) + "/slug_avatar_01.mp4")
        self.assertEqual(shots[0]["_render_files"], [
            "slug_avatar_01.mp4", "slug_actor_scene_01.png", "slug_slice_01.mp3",
            "slug_avatar_02.mp4", "slug_actor_scene_02.png", "slug_slice_02.mp3",
        ])


class SaaSBlankFrameGuardTests(unittest.TestCase):
    """A blank/black Flux frame must be rejected, not shown as a valid shot."""

    def _write_png(self, path, arr):
        from PIL import Image
        import numpy as np

        Image.fromarray(np.asarray(arr, dtype="uint8"), "RGB").save(path)

    def test_solid_black_frame_is_blank(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "black.png")
            self._write_png(path, np.zeros((128, 72, 3)))
            self.assertTrue(saasshorts._looks_blank(path))

    def test_flat_color_frame_is_blank(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "flat.png")
            self._write_png(path, np.full((128, 72, 3), 130))  # uniform mid-gray
            self.assertTrue(saasshorts._looks_blank(path))

    def test_detailed_frame_is_not_blank(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "noise.png")
            rng = np.random.default_rng(0)
            self._write_png(path, rng.integers(0, 256, size=(128, 72, 3)))
            self.assertFalse(saasshorts._looks_blank(path))

    def test_dim_but_real_frame_is_not_rejected(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dim.png")
            # Dark scene that still has real detail (variance) — must survive.
            rng = np.random.default_rng(1)
            self._write_png(path, rng.integers(0, 60, size=(128, 72, 3)))
            self.assertFalse(saasshorts._looks_blank(path))

    def test_missing_file_does_not_crash_and_is_not_blank(self):
        self.assertFalse(saasshorts._looks_blank("/nonexistent/frame.png"))

    def test_oversized_actor_photo_is_shrunk_before_it_goes_to_flux(self):
        """Фото-условие ужимается: на 4802×3584 Kontext возвращал чёрный кадр."""
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "actor.png")
            rng = np.random.default_rng(2)
            self._write_png(path, rng.integers(0, 256, size=(600, 800, 3)))  # h=600, w=800

            with patch.object(saasshorts, "_FLUX_CONDITION_MAX_PX", 256):
                shrunk = saasshorts._flux_condition_photo(path)

            from PIL import Image

            self.assertNotEqual(shrunk, path)
            with Image.open(shrunk) as im:
                self.assertLessEqual(max(im.size), 256)

    def test_small_actor_photo_goes_to_flux_untouched(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "actor.png")
            rng = np.random.default_rng(3)
            self._write_png(path, rng.integers(0, 256, size=(128, 72, 3)))

            self.assertEqual(saasshorts._flux_condition_photo(path), path)

    def _fake_httpx_client(self, out, bodies):
        """httpx.Client, кладущий в out очередную картинку из bodies."""
        def fake_get(url, *a, **kw):
            self._write_png(out, next(bodies))
            with open(out, "rb") as f:
                return MagicMock(content=f.read(), raise_for_status=lambda: None)

        client = MagicMock()
        client.__enter__ = lambda self_: self_
        client.__exit__ = lambda *a: False
        client.get = fake_get
        return client

    def test_one_click_buys_at_most_one_paid_frame(self):
        """Чёрный кадр тарифицируется как обычный — платим за него один раз.

        Автоматический перебор моделей внутри одного прогона превращал неудачу в
        счёт по числу кандидатов. Зовём ровно одного редактора — выбранного.
        """
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "plate.png")
            photo = os.path.join(tmp, "actor.png")
            rng = np.random.default_rng(6)
            self._write_png(photo, rng.integers(0, 256, size=(128, 72, 3)))
            bodies = iter([np.zeros((128, 72, 3))] * 4)
            models = []
            billing = {}

            def fake_run(model_id, args, key, timeout=600):
                models.append(model_id)
                return {"images": [{"url": "u"}], "has_nsfw_concepts": [True]}

            with patch.object(saasshorts, "_fal_run", side_effect=fake_run),                  patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"),                  patch.object(saasshorts.httpx, "Client",
                              return_value=self._fake_httpx_client(out, bodies)):
                made = saasshorts._flux_reference_frame(
                    "prompt", "key", out, log=lambda *_: None, actor_photo_path=photo,
                    billing=billing,
                )

            self.assertEqual(made, "")
            self.assertEqual(models, ["fal-ai/flux-pro/kontext"])
            self.assertEqual(billing["calls"], 1)

    def test_second_click_never_repeats_a_refused_model_on_its_own(self):
        """Молчаливой подмены модели нет: второй клик просто бесплатно отказывает.

        Раньше пайплайн сам брал следующего кандидата, и человек узнавал о
        подмене по счёту. Теперь та же модель второй раз не покупается (модерация
        детерминированна), а другую выбирает пользователь.
        """
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "plate.png")
            photo = os.path.join(tmp, "actor.png")
            rng = np.random.default_rng(7)
            self._write_png(photo, rng.integers(0, 256, size=(128, 72, 3)))
            models = []
            billing = {}

            def fake_run(model_id, args, key, timeout=600):
                models.append(model_id)
                return {"images": [{"url": "u"}], "has_nsfw_concepts": [True]}

            def click():
                bodies = iter([np.zeros((128, 72, 3))] * 2)
                with patch.object(saasshorts, "_fal_run", side_effect=fake_run),                      patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"),                      patch.object(saasshorts.httpx, "Client",
                                  return_value=self._fake_httpx_client(out, bodies)):
                    return saasshorts._flux_reference_frame(
                        "prompt", "key", out, log=lambda *_: None, actor_photo_path=photo,
                        billing=billing,
                    )

            for _ in range(3):
                self.assertEqual(click(), "")

            # Один платный запрос на все три клика, и ни одного к чужой модели.
            self.assertEqual(models, [saasshorts.DEFAULT_AVATAR_EDIT_MODEL])
            self.assertEqual(billing["calls"], 1)
            # Каждый отказ доезжает до интерфейса, даже бесплатный.
            self.assertEqual([b["reason"] for b in billing["blocked"]],
                             ["moderation", "known", "known"])

    def test_chosen_editor_is_the_one_that_gets_called(self):
        """Выбор пользователя — это и есть модель запроса, без «умных» правок."""
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "plate.png")
            photo = os.path.join(tmp, "actor.png")
            rng = np.random.default_rng(8)
            self._write_png(photo, rng.integers(0, 256, size=(128, 72, 3)))
            calls = []

            def fake_run(model_id, args, key, timeout=600):
                calls.append((model_id, args))
                return {"images": [{"url": "u"}]}

            bodies = iter([rng.integers(0, 256, size=(128, 72, 3))])
            with patch.object(saasshorts, "_fal_run", side_effect=fake_run), \
                 patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"), \
                 patch.object(saasshorts.httpx, "Client",
                              return_value=self._fake_httpx_client(out, bodies)):
                made = saasshorts._flux_reference_frame(
                    "prompt", "key", out, log=lambda *_: None, actor_photo_path=photo,
                    edit_model="fal-ai/nano-banana/edit",
                )

            self.assertEqual(made, out)
            model, args = calls[0]
            self.assertEqual(model, "fal-ai/nano-banana/edit")
            # Поле под картинку у каждого эндпоинта своё — иначе 422 вместо кадра.
            self.assertEqual(args["image_urls"], ["http://photo"])

    def test_plate_adopted_from_the_preview_job_is_not_bought_again(self):
        """Одобренный ракурс переезжает в рендер и не покупается второй раз.

        Кадр кэшируется по промпту, но внутри папки своего джоба. Пока рендер не
        забирал файлы предпросмотра, он платил заново за ровно ту картинку,
        которую пользователь уже посмотрел и утвердил, — и получал другой сэмпл
        вместо одобренного.
        """
        import numpy as np

        with tempfile.TemporaryDirectory() as root:
            preview = os.path.join(root, "saas_preview")
            render = os.path.join(root, "saas_render")
            os.makedirs(preview)
            os.makedirs(render)
            photo = os.path.join(root, "actor.png")
            rng = np.random.default_rng(11)
            self._write_png(photo, rng.integers(0, 256, size=(128, 72, 3)))
            plate = os.path.join(preview, "job_actor_set_medium.png")
            bodies = iter([rng.integers(0, 256, size=(128, 72, 3))])
            staged = {"scene_override": "kitchen counter at golden hour",
                      "framing": "Medium shot from the chest up"}

            with patch.object(saasshorts, "_fal_run", return_value={"images": [{"url": "u"}]}), \
                 patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"), \
                 patch.object(saasshorts.httpx, "Client",
                              return_value=self._fake_httpx_client(plate, bodies)):
                drawn = saasshorts._avatar_reference_image(
                    {}, photo, "key", plate, log=lambda *_: None, **staged,
                )
            self.assertEqual(drawn, plate)

            saasshorts.adopt_job_artifacts(preview, render, log=lambda *_: None)

            # Рендер зовёт ту же камеру тем же промптом — и упирается в кэш,
            # переехавший вместе с картинкой.
            adopted = os.path.join(render, "job_actor_set_medium.png")
            with patch.object(saasshorts, "_fal_run",
                              side_effect=AssertionError("одобренный ракурс перерисовывать нельзя")):
                reused = saasshorts._avatar_reference_image(
                    {}, photo, "key", adopted, log=lambda *_: None, **staged,
                )
            self.assertEqual(reused, adopted)

    def test_blocked_report_carries_the_verdict_and_what_is_left(self):
        """Отчёт наверх: дословный ответ fal и модели, которых ещё не пробовали.

        Модалка строится из него, поэтому без ответа модели («что за нагота?») и
        без списка альтернатив она не имеет смысла.
        """
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "plate.png")
            photo = os.path.join(tmp, "actor.png")
            rng = np.random.default_rng(9)
            self._write_png(photo, rng.integers(0, 256, size=(128, 72, 3)))
            billing = {}
            bodies = iter([np.zeros((128, 72, 3))] * 2)

            with patch.object(saasshorts, "_fal_run",
                              return_value={"images": [{"url": "u"}], "has_nsfw_concepts": [True]}), \
                 patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"), \
                 patch.object(saasshorts.httpx, "Client",
                              return_value=self._fake_httpx_client(out, bodies)):
                saasshorts._flux_reference_frame(
                    "prompt", "key", out, log=lambda *_: None, actor_photo_path=photo,
                    billing=billing,
                )

            report = billing["blocked"][0]
            self.assertEqual(report["model"], saasshorts.DEFAULT_AVATAR_EDIT_MODEL)
            self.assertEqual(report["flags"], {"has_nsfw_concepts": [True]})
            # Пустой кадр оплачен — умолчать об этом нельзя.
            self.assertTrue(report["charged"])
            left = [alt["id"] for alt in report["alternatives"]]
            self.assertNotIn(saasshorts.DEFAULT_AVATAR_EDIT_MODEL, left)
            self.assertIn("fal-ai/qwen-image-edit", left)

    def test_refused_endpoint_is_reported_as_unavailable_not_moderation(self):
        """404/422 — это переехавший эндпоинт, а не «модерация зарубила фото».

        Путать их нельзя: за отказ эндпоинта fal денег не берёт, и советовать
        из-за него менять фотографию — вредный совет.
        """
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "plate.png")
            photo = os.path.join(tmp, "actor.png")
            rng = np.random.default_rng(10)
            self._write_png(photo, rng.integers(0, 256, size=(128, 72, 3)))
            billing = {}

            with patch.object(saasshorts, "_fal_run",
                              side_effect=RuntimeError("404 model not found")), \
                 patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"), \
                 patch.object(saasshorts.httpx, "Client",
                              return_value=self._fake_httpx_client(out, iter([]))):
                made = saasshorts._flux_reference_frame(
                    "prompt", "key", out, log=lambda *_: None, actor_photo_path=photo,
                    billing=billing,
                )

            self.assertEqual(made, "")
            self.assertEqual(billing["blocked"][0]["reason"], "unavailable")
            self.assertFalse(billing["blocked"][0]["charged"])
            self.assertEqual(billing["calls"], 0)

    def test_editor_catalogue_ends_on_a_model_without_a_moderator(self):
        """Последним стоит редактор с открытыми весами — его никто не зарубит.

        Все, кто выше, — закрытые API со своей модерацией: они и возвращают
        чёрные квадраты. Замыкать каталог должен тот, у кого чужого модератора
        нет, — это последнее, что можно предложить вместо смены фото.
        """
        catalogue = saasshorts.AVATAR_EDIT_MODELS
        self.assertEqual(catalogue[-1]["id"], "fal-ai/qwen-image-edit")
        self.assertEqual(catalogue[0]["id"], saasshorts.DEFAULT_AVATAR_EDIT_MODEL)
        names = [m["id"] for m in catalogue]
        # Дубль в каталоге — это два пункта меню, ведущих на одну модерацию.
        self.assertEqual(len(names), len(set(names)))
        for model in catalogue:
            self.assertIn(model["field"], ("image_url", "image_urls"), model["id"])
            # Витрина: без названия и пояснения выбирать не из чего.
            self.assertTrue(model["title"] and model["vendor"] and model["note"])

    def test_unknown_editor_id_falls_back_to_the_default(self):
        """Фронт мог отстать от каталога — незнакомый id не должен уезжать в fal."""
        self.assertEqual(saasshorts._avatar_edit_model("")["id"],
                         saasshorts.DEFAULT_AVATAR_EDIT_MODEL)
        self.assertEqual(saasshorts._avatar_edit_model("fal-ai/nope")["id"],
                         saasshorts.DEFAULT_AVATAR_EDIT_MODEL)
        self.assertEqual(saasshorts._avatar_edit_model("fal-ai/qwen-image-edit")["id"],
                         "fal-ai/qwen-image-edit")

    def test_blank_frame_logs_what_the_model_answered(self):
        """Причина чёрного кадра должна попасть в лог, а не остаться догадкой."""
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "plate.png")
            photo = os.path.join(tmp, "actor.png")
            rng = np.random.default_rng(7)
            self._write_png(photo, rng.integers(0, 256, size=(128, 72, 3)))
            bodies = iter([np.zeros((128, 72, 3))] * 4)
            lines = []

            with patch.object(saasshorts, "_fal_run",
                              return_value={"images": [{"url": "u"}], "has_nsfw_concepts": [True]}), \
                 patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"), \
                 patch.object(saasshorts.httpx, "Client",
                              return_value=self._fake_httpx_client(out, bodies)):
                made = saasshorts._flux_reference_frame(
                    "prompt", "key", out, log=lines.append, actor_photo_path=photo,
                )

            self.assertEqual(made, "")
            self.assertTrue(any("has_nsfw_concepts" in line for line in lines), lines)

    def test_horizontal_actor_photo_stops_the_job_before_paid_video(self):
        """Раскладка ракурсов не должна уезжать в Kling — это оплаченный брак."""
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            wide = os.path.join(tmp, "sheet.png")
            tall = os.path.join(tmp, "portrait.png")
            rng = np.random.default_rng(5)
            self._write_png(wide, rng.integers(0, 256, size=(384, 512, 3)))  # h<w
            self._write_png(tall, rng.integers(0, 256, size=(512, 384, 3)))  # h>w

            with self.assertRaises(RuntimeError) as caught:
                saasshorts._refuse_unusable_start_frame(wide)
            self.assertIn("Сгенерить недостающие", str(caught.exception))

            saasshorts._refuse_unusable_start_frame(tall)  # вертикальное — пропускаем
            saasshorts._refuse_unusable_start_frame("/nonexistent.png")  # нечитаемое — не мешаем


class SaaSStoryboardTests(unittest.TestCase):
    def test_target_duration_normalizes_supported_presets_and_falls_back_to_twenty(self):
        for value in (15, 20, 30, 45):
            self.assertEqual(saasshorts.normalize_target_duration(value), value)
        self.assertEqual(saasshorts.normalize_target_duration("45"), 45)
        self.assertEqual(saasshorts.normalize_target_duration(29), 20)
        self.assertEqual(saasshorts.normalize_target_duration(None), 20)

    def test_storyboard_duration_prompt_uses_selected_target_only(self):
        answer = _storyboard_answer("Thirty", 12)
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(text=answer)

        with patch("google.genai.Client", return_value=client), \
             patch(
                 "saasshorts.refine_storyboard_broll_alignment",
                 side_effect=lambda scripts, *_args, **_kwargs: scripts,
             ):
            scripts = saasshorts.generate_scripts(
                analysis={"product_name": "Test"},
                gemini_key="key",
                num_scripts=1,
                script_format="storyboard_v3",
                target_duration_seconds=30,
            )

        prompt = client.models.generate_content.call_args.kwargs["contents"][0]
        self.assertIn("28-32 seconds", prompt)
        self.assertIn("59-63 spoken words", prompt)
        self.assertIn("8-10 visual beats", prompt)
        self.assertIn('Make 1-2 middle shots "broll"', prompt)
        self.assertNotIn("30-40 percent", prompt)
        self.assertNotIn("18-22 seconds total", prompt)
        self.assertEqual(scripts[0]["target_duration_seconds"], 30)

    def test_storyboard_prompt_does_not_expose_experimental_pacing_profile(self):
        answer = _storyboard_answer("Previous rhythm", 6)
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(text=answer)

        with patch("google.genai.Client", return_value=client), \
             patch(
                 "saasshorts.refine_storyboard_broll_alignment",
                 side_effect=lambda scripts, *_args, **_kwargs: scripts,
             ):
            saasshorts.generate_scripts(
                analysis={"product_name": "Test"},
                gemini_key="key",
                num_scripts=1,
                script_format="storyboard_v3",
                target_duration_seconds=20,
            )

        prompt = client.models.generate_content.call_args.kwargs["contents"][0]
        self.assertIn("5-7 visual beats", prompt)
        self.assertIn("about 3 seconds (5 at the absolute limit)", prompt)
        self.assertNotIn("STORYBOARD PACING PROFILE", prompt)
        self.assertNotIn("storyboard_pacing", prompt)

    def test_target_duration_metadata_applies_to_every_script_in_batch(self):
        scripts_answer = []
        for index, hook_type in enumerate(("result_first", "data_point"), start=1):
            script = json.loads(_storyboard_answer(f"Script {index}", 6))[0]
            script["hook_type"] = hook_type
            script["shots"][0]["speech"] = f"Unique opening {index} proves the point."
            scripts_answer.append(script)
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(
            text=json.dumps(scripts_answer),
        )

        with patch("google.genai.Client", return_value=client), \
             patch(
                 "saasshorts.refine_storyboard_broll_alignment",
                 side_effect=lambda scripts, *_args, **_kwargs: scripts,
             ):
            scripts = saasshorts.generate_scripts(
                analysis={"product_name": "Test"},
                gemini_key="key",
                num_scripts=2,
                script_format="storyboard_v3",
                target_duration_seconds=15,
            )

        self.assertEqual(len(scripts), 2)
        self.assertEqual(
            [script["target_duration_seconds"] for script in scripts],
            [15, 15],
        )

    def test_ugc_duration_prompt_scales_five_segments_to_selected_target(self):
        answer = json.dumps([{
            "title": "Long explainer",
            "hook_type": "result_first",
            "segments": [
                {
                    "type": "hook",
                    "start": 0,
                    "end": 9,
                    "narration": "A useful opening.",
                    "visual": "actor_talking",
                    "broll_prompt": None,
                },
                {
                    "type": "problem",
                    "start": 9,
                    "end": 18,
                    "narration": "The concrete problem.",
                    "visual": "broll",
                    "broll_prompt": "A relevant object demonstrates the problem.",
                },
                {
                    "type": "solution",
                    "start": 18,
                    "end": 27,
                    "narration": "The practical solution.",
                    "visual": "actor_talking",
                    "broll_prompt": None,
                },
                {
                    "type": "demo",
                    "start": 27,
                    "end": 36,
                    "narration": "The result in use.",
                    "visual": "broll",
                    "broll_prompt": "A relevant object demonstrates the result.",
                },
                {
                    "type": "cta",
                    "start": 36,
                    "end": 45,
                    "narration": "One direct call to action.",
                    "visual": "actor_talking",
                    "broll_prompt": None,
                },
            ],
        }])
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(text=answer)

        with patch("google.genai.Client", return_value=client):
            scripts = saasshorts.generate_scripts(
                analysis={"product_name": "Test"},
                gemini_key="key",
                num_scripts=1,
                script_format="ugc",
                target_duration_seconds=45,
            )

        prompt = client.models.generate_content.call_args.kwargs["contents"][0]
        self.assertIn("43-47 seconds", prompt)
        self.assertIn("92-96 spoken words", prompt)
        self.assertIn("five segments", prompt.casefold())
        self.assertIn('"end": 45', prompt)
        self.assertNotIn("18-22 seconds total", prompt)
        self.assertEqual(scripts[0]["target_duration_seconds"], 45)

    def test_custom_scripts_do_not_store_experimental_pacing_profile(self):
        script = build_custom_script(
            "Первая короткая фраза. Вторая короткая фраза.",
            {"product_name": "Test"},
            language="ru",
            script_format="storyboard_v3",
        )

        self.assertNotIn("storyboard_pacing", script)

    def test_power_text_model_resolves_to_gemini_31_pro_with_flash_fallback(self):
        resolver = getattr(saasshorts, "resolve_gemini_text_model", None)
        chain_builder = getattr(saasshorts, "gemini_text_model_chain", None)

        self.assertIsNotNone(resolver)
        self.assertIsNotNone(chain_builder)
        with patch.object(saasshorts, "GEMINI_MODEL", "gemini-3-flash-preview"), \
             patch.object(saasshorts, "GEMINI_FALLBACK_MODELS", ["gemini-2.5-flash"]):
            self.assertEqual(resolver("pro"), "gemini-3.1-pro-preview")
            self.assertEqual(resolver("quality"), "gemini-3.1-pro-preview")
            self.assertEqual(
                chain_builder("pro")[:3],
                ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash"],
            )

    def test_default_free_text_model_is_gemini_35_flash(self):
        self.assertEqual(saasshorts.DEFAULT_FREE_GEMINI_MODEL, "gemini-3.5-flash")
        with patch.object(saasshorts, "GEMINI_MODEL", saasshorts.DEFAULT_FREE_GEMINI_MODEL):
            self.assertEqual(saasshorts.resolve_gemini_text_model("fast"), "gemini-3.5-flash")
            self.assertEqual(saasshorts.gemini_text_model_chain("fast")[0], "gemini-3.5-flash")

    def test_free_grounding_model_uses_model_with_free_search_grounding(self):
        self.assertEqual(saasshorts.DEFAULT_FREE_GEMINI_GROUNDING_MODEL, "gemini-2.5-flash")
        with patch.object(saasshorts, "GEMINI_FREE_GROUNDING_MODEL", "gemini-2.5-flash"):
            self.assertEqual(saasshorts.resolve_gemini_grounding_model("fast"), "gemini-2.5-flash")
            self.assertEqual(saasshorts.gemini_grounding_model_chain("fast"), ["gemini-2.5-flash"])

    def test_normalizes_storyboard_action_transition_and_prompt_contract(self):
        shots = normalize_storyboard_shots({
            "shots": [
                {
                    "shot_number": 1,
                    "start": 0,
                    "end": 3,
                    "role": "hook",
                    "scene": "Close-up face near a window",
                    "camera": "tight close-up, steady handheld",
                    "action": "looks into camera with raised eyebrows",
                    "speech": "Ты делаешь всё правильно?",
                    "overlay_text": "Вес встал?",
                    "transition": "cut",
                }
            ]
        })

        shot = shots[0]

        self.assertEqual(shot["role"], "hook")
        self.assertEqual(shot["actor_action"], "looks into camera with raised eyebrows")
        self.assertEqual(shot["camera"], "tight close-up, steady handheld")
        self.assertEqual(shot["transition"], "cut")
        self.assertEqual(shot["overlay_text"], "Вес встал?")
        self.assertIn("vertical 9:16", shot["generation_prompt"])
        self.assertIn("Close-up face near a window", shot["generation_prompt"])
        self.assertIn("looks into camera with raised eyebrows", shot["generation_prompt"])
        self.assertNotIn("no burned-in text", shot["generation_prompt"])

    def test_custom_storyboard_parses_russian_frame_template(self):
        custom_script = """
## РОЛИК №1 — «Почему вес встал после 30»

### КАДР 1 — 0:00–0:03 — ХУК
Что делает: Смотрит в камеру, рот слегка открыт, брови чуть подняты

Текст на экране: «Вес встал и не двигается?»

Она говорит:
> «Ты делаешь всё правильно — а весы стоят на месте?»

### КАДР 2 — 0:03–0:07 — ПРОБЛЕМА
Что делает: Сидит на диване, наклонилась вперёд, ладони открыты

Текст на экране: «После 30 тело работает по другим правилам»

Она говорит:
> «Это не потому что ты слабая. После 30 тело меняется.»

| 1 → 2 | 0:03 | Резкая склейка |
"""

        script = build_custom_script(
            custom_script,
            {"product_name": "Моя Форма 30+", "description": "wellness guide"},
            language="ru",
            actor_gender="female",
            topic="Почему вес встал после 30",
            script_format="storyboard_v3",
        )

        self.assertEqual(script["format"], "storyboard_v3")
        self.assertEqual(len(script["shots"]), 2)
        self.assertEqual(script["shots"][0]["role"], "hook")
        self.assertIn("Смотрит в камеру", script["shots"][0]["actor_action"])
        self.assertEqual(script["shots"][0]["overlay_text"], "Вес встал и не двигается?")
        self.assertIn("Ты делаешь всё правильно", script["shots"][0]["speech"])
        self.assertEqual(script["shots"][0]["transition"], "cut")
        self.assertEqual(script["shots"][1]["role"], "problem")
        self.assertIn("После 30 тело меняется", script["full_narration"])


class SaaSAnalyzePacingContractTests(unittest.TestCase):
    def test_analyze_request_defaults_target_duration_to_twenty(self):
        import app

        self.assertEqual(
            app.SaaSAnalyzeRequest(description="Test").target_duration_seconds,
            20,
        )

    def test_analyze_request_normalizes_unsupported_target_duration(self):
        import app

        for value in (None, 29, "not-a-preset"):
            request = app.SaaSAnalyzeRequest(
                description="Test",
                target_duration_seconds=value,
            )
            self.assertEqual(request.target_duration_seconds, 20)

    def test_analyze_request_passes_target_duration_to_ai_generation(self):
        import app

        request = app.SaaSAnalyzeRequest(
            description="Test product",
            script_format="storyboard_v3",
            target_duration_seconds=45,
        )
        with patch("app.resolve_effective_api_key", return_value="key"), \
             patch("app.generate_scripts", return_value=[]) as generate:
            asyncio.run(app.saasshorts_analyze(
                request,
                x_gemini_key="key",
                authorization=None,
            ))

        self.assertEqual(
            generate.call_args.kwargs["target_duration_seconds"],
            45,
        )

    def test_custom_script_is_not_fitted_to_target_duration(self):
        import app

        narration = "Первая фраза. Вторая фраза остаётся без изменений."
        request = app.SaaSAnalyzeRequest(
            description="Test product",
            script_mode="custom",
            script_format="ugc",
            custom_script=narration,
            target_duration_seconds=15,
            language="ru",
        )
        with patch("app.resolve_effective_api_key", return_value=""):
            result = asyncio.run(app.saasshorts_analyze(
                request,
                x_gemini_key=None,
                authorization=None,
            ))

        self.assertEqual(result["scripts"][0]["full_narration"], narration)
        self.assertNotIn("target_duration_seconds", result["scripts"][0])

    def test_storyboard_ass_has_no_top_overlay_plates(self):
        # User decision 2026-07-10: top hook/overlay plates are visual clutter.
        with tempfile.TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "storyboard.ass")
            shots = [
                {
                    "shot_number": 1,
                    "start": 0,
                    "end": 3,
                    "role": "hook",
                    "overlay_text": "Вес встал?",
                }
            ]

            with patch("saasshorts.transcribe_audio_for_subs", return_value=[
                {"word": "Ты", "start": 0.1, "end": 0.4},
                {"word": "делаешь", "start": 0.4, "end": 0.9},
                {"word": "правильно", "start": 0.9, "end": 1.4},
            ]):
                generate_storyboard_ass_subtitles("voice.mp3", shots, output_path, max_words=2)

            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertNotIn("Style: Overlay", content)
            self.assertNotIn("Style: Hook", content)
            self.assertIn("Style: Subtitle", content)
            self.assertNotIn("ВЕС ВСТАЛ?", content)
            self.assertIn("ТЫ ДЕЛАЕШЬ", content)

    def test_storyboard_ass_uses_submagic_like_safe_zones_and_keyword_highlight(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "storyboard.ass")
            shots = [
                {
                    "shot_number": 1,
                    "start": 0,
                    "end": 3,
                    "role": "hook",
                    "overlay_text": "Неделя без срывов",
                },
                {
                    "shot_number": 2,
                    "start": 3,
                    "end": 6,
                    "role": "problem",
                    "overlay_text": "вечер начинается утром",
                },
            ]

            with patch("saasshorts.transcribe_audio_for_subs", return_value=[
                {"word": "Неделя", "start": 0.1, "end": 0.5},
                {"word": "без", "start": 0.5, "end": 0.7},
                {"word": "срывов", "start": 0.7, "end": 1.1},
                {"word": "начинается", "start": 1.1, "end": 1.7},
            ]):
                generate_storyboard_ass_subtitles("voice.mp3", shots, output_path, max_words=2)

            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("Style: Subtitle,Montserrat ExtraBold,72", content)
            # BorderStyle=1 (outline+shadow, no opaque box), safe-zone margin 520.
            self.assertRegex(content, r"Style: Subtitle,.*?,1,3,2,2,96,96,520,1")
            # Keyword accent: color-only, reset back to white (not \r).
            self.assertIn("{\\c&H0066D1FF&}", content)
            self.assertIn("{\\c&HFFFFFF&}", content)
            self.assertNotIn("\\bord8", content)
            # Pop-in animation on caption lines.
            self.assertIn("\\t(0,90,\\fscx100\\fscy100)", content)
            self.assertNotIn("Overlay", content.split("[Events]")[1])

    def test_builds_kling_v3_text_to_video_multishot_payload_without_native_audio(self):
        shots = [
            {
                "shot_number": 1,
                "start": 0,
                "end": 3,
                "generation_prompt": "close-up portrait, woman looks into camera",
            },
            {
                "shot_number": 2,
                "start": 3,
                "end": 7,
                "generation_prompt": "bright kitchen, woman prepares oatmeal",
            },
        ]

        model_id, payload = build_kling_v3_storyboard_request(
            shots,
            tier="pro",
            generation_mode="multi_shot",
            aspect_ratio="9:16",
        )

        self.assertEqual(model_id, "fal-ai/kling-video/v3/pro/text-to-video")
        self.assertEqual(payload["aspect_ratio"], "9:16")
        self.assertEqual(payload["duration"], "7")
        self.assertEqual(payload["generate_audio"], False)
        self.assertEqual(payload["shot_type"], "customize")
        self.assertEqual(len(payload["multi_prompt"]), 2)
        self.assertEqual(payload["multi_prompt"][0]["duration"], "3")
        self.assertNotIn("prompt", payload)

    def test_builds_kling_v3_image_to_video_payload_from_uploaded_frame(self):
        shots = [
            {
                "shot_number": 1,
                "start": 0,
                "end": 3,
                "generation_prompt": "close-up portrait, woman looks into camera",
                "image_url": "https://cdn.example.com/frame-1.png",
            }
        ]

        model_id, payload = build_kling_v3_storyboard_request(
            shots,
            tier="standard",
            generation_mode="single_shot",
            aspect_ratio="9:16",
        )

        self.assertEqual(model_id, "fal-ai/kling-video/v3/standard/image-to-video")
        self.assertEqual(payload["start_image_url"], "https://cdn.example.com/frame-1.png")
        self.assertEqual(payload["duration"], "3")
        self.assertEqual(payload["generate_audio"], False)
        self.assertNotIn("aspect_ratio", payload)

    def test_builds_veo31_text_to_video_payload_without_native_audio(self):
        model_id, payload = build_kling_v3_storyboard_request(
            [
                {
                    "shot_number": 1,
                    "start": 0,
                    "end": 5,
                    "generation_prompt": "close-up portrait, woman looks into camera",
                }
            ],
            tier="veo31_quality",
            generation_mode="single_shot",
            aspect_ratio="9:16",
        )

        self.assertEqual(model_id, "fal-ai/veo3.1")
        self.assertEqual(payload["aspect_ratio"], "9:16")
        self.assertEqual(payload["duration"], "6s")
        self.assertEqual(payload["resolution"], "1080p")
        self.assertEqual(payload["generate_audio"], False)
        self.assertEqual(payload["auto_fix"], False)
        self.assertNotIn("multi_prompt", payload)

    def test_builds_veo31_image_to_video_payload_from_uploaded_frame(self):
        model_id, payload = build_kling_v3_storyboard_request(
            [
                {
                    "shot_number": 1,
                    "start": 0,
                    "end": 3,
                    "generation_prompt": "close-up portrait, woman looks into camera",
                    "image_url": "https://cdn.example.com/frame-1.png",
                }
            ],
            tier="veo31_quality",
            generation_mode="single_shot",
            aspect_ratio="9:16",
        )

        self.assertEqual(model_id, "fal-ai/veo3.1/image-to-video")
        self.assertEqual(payload["image_url"], "https://cdn.example.com/frame-1.png")
        self.assertEqual(payload["aspect_ratio"], "9:16")
        self.assertEqual(payload["duration"], "4s")
        self.assertEqual(payload["generate_audio"], False)

    def test_ugc_prompt_has_single_full_narration_rule(self):
        source_path = os.path.join(os.path.dirname(__file__), "..", "saasshorts.py")
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("only actor_talking segments", source)
        self.assertIn("full_narration = ALL segment narration joined in timeline order", source)

    def test_split_storyboard_shots_keeps_chunks_under_fifteen_seconds(self):
        shots = [
            {"shot_number": 1, "start": 0, "end": 3, "generation_prompt": "shot 1"},
            {"shot_number": 2, "start": 3, "end": 7, "generation_prompt": "shot 2"},
            {"shot_number": 3, "start": 7, "end": 11, "generation_prompt": "shot 3"},
            {"shot_number": 4, "start": 11, "end": 14, "generation_prompt": "shot 4"},
            {"shot_number": 5, "start": 14, "end": 17, "generation_prompt": "shot 5"},
            {"shot_number": 6, "start": 17, "end": 20, "generation_prompt": "shot 6"},
        ]

        chunks = split_storyboard_shots(shots, max_duration=15)

        self.assertEqual(len(chunks), 2)
        self.assertEqual([shot["shot_number"] for shot in chunks[0]], [1, 2, 3, 4])
        self.assertEqual([shot["shot_number"] for shot in chunks[1]], [5, 6])
        for chunk in chunks:
            self.assertLessEqual(sum(shot["end"] - shot["start"] for shot in chunk), 15)

    def test_storyboard_generation_routes_around_talking_head_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = {
                "title": "Storyboard test",
                "format": "storyboard_v3",
                "duration_seconds": 7,
                "hook_text": "Hook",
                "full_narration": "First line. Second line.",
                "shots": [
                    {
                        "shot_number": 1,
                        "start": 0,
                        "end": 3,
                        "speech": "First line.",
                        "overlay_text": "First",
                        "generation_prompt": "close-up portrait",
                    },
                    {
                        "shot_number": 2,
                        "start": 3,
                        "end": 7,
                        "speech": "Second line.",
                        "overlay_text": "Second",
                        "generation_prompt": "kitchen scene",
                    },
                ],
            }
            config = {
                "fal_key": "fal-test",
                "tts_provider": "fal_minimax",
                "language": "ru",
                "actor_gender": "female",
                "video_mode": "storyboard_v3_pro",
            }

            def fake_storyboard(script_arg, config_arg, output_dir, log=print):
                video_path = os.path.join(output_dir, "storyboard_final.mp4")
                with open(video_path, "wb") as f:
                    f.write(b"storyboard")
                return {
                    "video_path": video_path,
                    "video_filename": os.path.basename(video_path),
                    "srt_path": os.path.join(output_dir, "storyboard_subs.ass"),
                    "actor_image": "",
                    "duration": 7,
                    "cost_estimate": {"storyboard_kling_v3_pro": 0.78, "total": 0.78},
                    "tts_provider": "fal_minimax",
                    "broll_mode": "storyboard",
                    "head_source": "storyboard",
                    "lipsync_model": None,
                    "quality_status": "storyboard",
                    "quality_warnings": [],
                    "talking_head_quality": {},
                }

            with patch("saasshorts.generate_storyboard_video", side_effect=fake_storyboard) as storyboard_mock, \
                 patch("saasshorts.generate_talking_head", side_effect=AssertionError("talking head should not run")), \
                 patch("saasshorts.generate_talking_head_lowcost", side_effect=AssertionError("lowcost head should not run")):
                result = generate_full_video(script, config, tmp)

            self.assertEqual(storyboard_mock.call_count, 1)
            self.assertEqual(result["head_source"], "storyboard")
            self.assertEqual(result["broll_mode"], "storyboard")

    def test_kling_v3_costs_are_exposed_for_standard_and_pro(self):
        self.assertEqual(kling_v3_cost_per_second("standard"), 0.084)
        self.assertEqual(kling_v3_cost_per_second("pro"), 0.112)

    def test_storyboard_video_costs_include_veo31_quality(self):
        self.assertEqual(storyboard_video_cost_per_second("veo31_quality"), 0.20)

    def test_storyboard_generation_can_use_multishot_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = {
                "title": "Multi shot",
                "format": "storyboard_v3",
                "full_narration": "One. Two. Three. Four. Five. Six.",
                "shots": [
                    {"shot_number": 1, "start": 0, "end": 3, "speech": "One.", "generation_prompt": "shot 1"},
                    {"shot_number": 2, "start": 3, "end": 7, "speech": "Two.", "generation_prompt": "shot 2"},
                    {"shot_number": 3, "start": 7, "end": 11, "speech": "Three.", "generation_prompt": "shot 3"},
                    {"shot_number": 4, "start": 11, "end": 14, "speech": "Four.", "generation_prompt": "shot 4"},
                    {"shot_number": 5, "start": 14, "end": 17, "speech": "Five.", "generation_prompt": "shot 5"},
                    {"shot_number": 6, "start": 17, "end": 20, "speech": "Six.", "generation_prompt": "shot 6"},
                ],
            }
            config = {
                "fal_key": "fal-test",
                "tts_provider": "fal_minimax",
                "language": "ru",
                "actor_gender": "female",
                "video_mode": "storyboard_v3_standard",
                "storyboard_generation_mode": "multi_shot",
            }

            def fake_voiceover(text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"voice")
                return {"path": output_path, "provider": "fal_minimax", "voice_id": "Russian_AmbitiousWoman"}

            def fake_chunk(shots, fal_key, output_path, tier="standard"):
                with open(output_path, "wb") as f:
                    f.write(b"chunk")
                return output_path

            def fake_subs(audio_path, shots, output_path, max_words=2, **kwargs):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            def fake_composite(clips, audio_path, srt_path, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"final")
                return output_path

            with patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_voiceover), \
                 patch("saasshorts.generate_storyboard_chunk_clip", side_effect=fake_chunk) as chunk_mock, \
                 patch("saasshorts.generate_storyboard_shot_clip", side_effect=AssertionError("per-shot should not run")), \
                 patch("saasshorts.generate_storyboard_ass_subtitles", side_effect=fake_subs), \
                 patch("saasshorts.composite_storyboard_video", side_effect=fake_composite), \
                 patch("saasshorts._decodable_audio_duration", return_value=20), \
                 patch("saasshorts._get_media_duration", return_value=20):
                result = generate_storyboard_video(script, config, tmp)

            # Shot durations are derived from the voiceover now (not the script's
            # start/end): 6 one-word shots over a 20s track → ~3s each, so the
            # 15s multi-shot cap packs 5 shots into the first chunk, 1 into the second.
            self.assertEqual(chunk_mock.call_count, 2)
            self.assertEqual(len(chunk_mock.call_args_list[0].args[0]), 5)
            self.assertEqual(len(chunk_mock.call_args_list[1].args[0]), 1)
            self.assertEqual(result["cost_estimate"]["storyboard_kling_v3_standard"], 1.51)

    def test_per_shot_durations_derived_from_voiceover(self):
        # The manual seconds field is gone: per-shot length comes from each shot's
        # share of the voiceover, not the script's start/end.
        with tempfile.TemporaryDirectory() as tmp:
            script = {
                "title": "Derive dur",
                "format": "storyboard_v3",
                "full_narration": "One. Two. Three four.",
                "shots": [
                    {"shot_number": 1, "start": 0, "end": 3, "speech": "One.", "generation_prompt": "p1"},
                    {"shot_number": 2, "start": 3, "end": 6, "speech": "Two.", "generation_prompt": "p2"},
                    {"shot_number": 3, "start": 6, "end": 9, "speech": "Three four.", "generation_prompt": "p3"},
                ],
            }
            config = {
                "fal_key": "k", "tts_provider": "fal_minimax", "language": "ru",
                "actor_gender": "female", "video_mode": "storyboard_v3_standard",
                "storyboard_generation_mode": "per_shot",
            }

            def fake_voiceover(text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"voice")
                return {"path": output_path, "provider": "fal_minimax", "voice_id": "v"}

            def fake_shot(shot, fal_key, output_path, tier="standard", **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"clip")
                return output_path

            def fake_subs(audio_path, shots, output_path, max_words=2, **kwargs):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            def fake_composite(clips, audio_path, srt_path, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"final")
                return output_path

            with patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_voiceover), \
                 patch("saasshorts.generate_storyboard_shot_clip", side_effect=fake_shot), \
                 patch("saasshorts.generate_storyboard_ass_subtitles", side_effect=fake_subs), \
                 patch("saasshorts.composite_storyboard_video", side_effect=fake_composite), \
                 patch("saasshorts._decodable_audio_duration", return_value=20), \
                 patch("saasshorts._get_media_duration", return_value=20):
                result = generate_storyboard_video(script, config, tmp)

            durations = [round(s["end"] - s["start"]) for s in result["storyboard_shots"]]
            # 4 spoken words over 20s: the 2-word shot gets double the 1-word shots.
            self.assertEqual(durations, [5, 5, 10])

    def test_scene_edit_rebuilds_generation_prompt(self):
        # «Что в кадре» drives the picture: editing scene rebuilds the English
        # prompt, but a hand-pinned prompt is left alone.
        shots = [
            {"shot_number": 1, "scene": "новая сцена", "_prompt_source_scene": "старая сцена",
             "generation_prompt": "old english prompt", "visual_type": "talking"},
            {"shot_number": 2, "scene": "изменённая", "_prompt_source_scene": "оригинал",
             "generation_prompt": "keep me", "prompt_manual": True, "visual_type": "talking"},
        ]

        class FakeResp:
            text = '[{"n": 0, "prompt": "a bright kitchen, woman smiling to camera"}]'

        with patch("saasshorts._generate_gemini_content", return_value=FakeResp()):
            saasshorts._rebuild_prompts_from_scene(shots, "gkey", actor_description="woman")

        self.assertIn("bright kitchen", shots[0]["generation_prompt"])
        self.assertEqual(shots[0]["_prompt_source_scene"], "новая сцена")
        self.assertEqual(shots[1]["generation_prompt"], "keep me")

    def test_scene_prompt_not_rebuilt_without_baseline(self):
        # First run / legacy: no baseline → trust the existing prompt, just stamp.
        shots = [{"shot_number": 1, "scene": "сцена", "generation_prompt": "orig"}]
        with patch("saasshorts._generate_gemini_content", side_effect=AssertionError("should not call Gemini")):
            saasshorts._rebuild_prompts_from_scene(shots, "gkey")
        self.assertEqual(shots[0]["generation_prompt"], "orig")
        self.assertEqual(shots[0]["_prompt_source_scene"], "сцена")

    def test_shot_previews_attached_from_generated_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip_path = os.path.join(tmp, "vid_shot_01.mp4")
            with open(clip_path, "wb") as f:
                f.write(b"clip")
            shots = [{"shot_number": 1}, {"shot_number": 2}]
            clips = [{"path": clip_path, "shot": {"shot_number": 1}}]

            def fake_ffmpeg(cmd, **kwargs):
                with open(cmd[-1], "wb") as f:
                    f.write(b"jpg")

            with patch("saasshorts.subprocess.run", side_effect=fake_ffmpeg):
                saasshorts._attach_shot_previews(shots, clips, tmp, "vid")

            job = os.path.basename(tmp)
            self.assertEqual(shots[0]["clip_url"], f"/videos/{job}/vid_shot_01.mp4")
            self.assertTrue(shots[0]["preview_frame_url"].endswith("/vid_thumb_01.jpg"))
            self.assertNotIn("clip_url", shots[1])

    def test_frames_only_generates_and_attaches_per_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            shots = [
                {"shot_number": 1, "visual_type": "talking", "scene": "kitchen", "generation_prompt": "p1"},
                {"shot_number": 2, "visual_type": "broll", "scene": "coffee", "generation_prompt": "p2"},
            ]

            def fake_avatar(shot, actor_photo_path, fal_key, output_path, log=print, **kwargs):
                avatar_calls.append((output_path, kwargs.get("framing", "")))
                _charge(kwargs, output_path)
                with open(output_path, "wb") as f:
                    f.write(b"png")
                return output_path

            def fake_broll(shot, fal_key, output_path, log=print, **kwargs):
                _charge(kwargs, output_path)
                with open(output_path, "wb") as f:
                    f.write(b"png")
                return output_path

            def fake_actor(desc, fal_key, output_path):
                with open(output_path, "wb") as f:
                    f.write(b"a")

            avatar_calls = []
            config = {"fal_key": "k", "selected_actor_path": "", "storyboard_generation_mode": "sliced_avatar"}
            with patch("saasshorts._avatar_reference_image", side_effect=fake_avatar), \
                 patch("saasshorts._broll_reference_image", side_effect=fake_broll), \
                 patch("saasshorts.generate_actor_image", side_effect=fake_actor):
                result = saasshorts._generate_storyboard_frames_only(shots, config, tmp, "vid")

            job = os.path.basename(tmp)
            self.assertTrue(result["frames_only"])
            self.assertTrue(shots[0]["local_url"].startswith(f"/videos/{job}/"))
            self.assertTrue(shots[0]["image_path"].endswith(".png"))
            self.assertEqual(shots[0]["preview_frame_url"], shots[0]["local_url"])
            self.assertTrue(shots[1]["image_url"].endswith(".png"))
            self.assertEqual(result["cost_estimate"]["reference_frames_flux"], 0.10)

    def test_frames_only_counts_the_frames_it_failed_to_draw(self):
        """Нулевой результат должен быть виден в ответе, а не только в логах.

        Иначе джоб завершается «успешно», интерфейс молча оставляет старую
        картинку, и пользователь видит «генерация прошла, ничего не изменилось».
        """
        with tempfile.TemporaryDirectory() as tmp:
            shots = [{"shot_number": 1, "visual_type": "talking", "scene": "kitchen",
                      "generation_prompt": "p1"}]

            def fake_actor(desc, fal_key, output_path):
                with open(output_path, "wb") as f:
                    f.write(b"a")

            config = {"fal_key": "k", "frames_only_shot": 1}
            with patch("saasshorts._avatar_reference_image", return_value=""), \
                 patch("saasshorts.generate_actor_image", side_effect=fake_actor):
                result = saasshorts._generate_storyboard_frames_only(shots, config, tmp, "vid")

            self.assertEqual(result["frames_made"], 0)
            self.assertEqual(result["frames_failed"], 1)
            self.assertEqual(result["cost_estimate"]["total"], 0)

    def test_frames_only_stages_two_cameras_not_one_frame_per_talking_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            shots = [
                {"shot_number": i, "visual_type": "talking", "scene": f"s{i}",
                 "generation_prompt": f"p{i}"}
                for i in range(1, 6)
            ]
            avatar_calls = []

            def fake_avatar(shot, actor_photo_path, fal_key, output_path, log=print, **kwargs):
                avatar_calls.append((output_path, kwargs.get("framing", ""),
                                     kwargs.get("scene_override", "")))
                _charge(kwargs, output_path)
                with open(output_path, "wb") as f:
                    f.write(b"png")
                return output_path

            def fake_actor(desc, fal_key, output_path):
                with open(output_path, "wb") as f:
                    f.write(b"a")

            config = {"fal_key": "k", "selected_actor_path": "",
                      "storyboard_generation_mode": "sliced_avatar"}
            with patch("saasshorts._avatar_reference_image", side_effect=fake_avatar), \
                 patch("saasshorts._broll_reference_image",
                       side_effect=AssertionError("no b-roll in this script")), \
                 patch("saasshorts.generate_actor_image", side_effect=fake_actor):
                result = saasshorts._generate_storyboard_frames_only(shots, config, tmp, "vid")

            # Five talking shots, two staged cameras — and only two are billed.
            drawn = {path for path, _, _ in avatar_calls}
            self.assertEqual(len(drawn), len(saasshorts._AVATAR_FRAMINGS))
            self.assertEqual(result["cost_estimate"]["reference_frames_flux"], 0.10)
            # Every talking shot got one of them, alternating, and they all sit on
            # the same set: the background must not change between cuts.
            used = [shot["image_path"] for shot in shots]
            self.assertEqual(set(used), drawn)
            for a, b in zip(used, used[1:]):
                self.assertNotEqual(a, b)
            self.assertEqual({scene for _, _, scene in avatar_calls}, {"p1"})

    def test_frames_only_shot_filter_regenerates_single(self):
        with tempfile.TemporaryDirectory() as tmp:
            shots = [
                {"shot_number": 1, "visual_type": "broll", "scene": "a", "generation_prompt": "p1"},
                {"shot_number": 2, "visual_type": "broll", "scene": "b", "generation_prompt": "p2"},
            ]
            calls = []

            def fake_broll(shot, fal_key, output_path, log=print, **kwargs):
                calls.append(shot["shot_number"])
                with open(output_path, "wb") as f:
                    f.write(b"png")
                return output_path

            config = {"fal_key": "k", "frames_only_shot": 2}
            with patch("saasshorts._broll_reference_image", side_effect=fake_broll):
                saasshorts._generate_storyboard_frames_only(shots, config, tmp, "vid")

            self.assertEqual(calls, [2])
            self.assertNotIn("local_url", shots[0])
            self.assertTrue(shots[1]["local_url"])

    def test_frames_only_passes_the_actor_photo_only_to_flagged_broll(self):
        """Перебивка с нашим персонажем снимается с фото аватара, остальные — нет."""
        with tempfile.TemporaryDirectory() as tmp:
            photo = os.path.join(tmp, "actor.png")
            with open(photo, "wb") as f:
                f.write(b"actor")
            shots = [
                {"shot_number": 1, "visual_type": "broll", "scene": "холодильник",
                 "generation_prompt": "p1", "actor_in_frame": True},
                {"shot_number": 2, "visual_type": "broll", "scene": "яблоко",
                 "generation_prompt": "p2"},
            ]
            calls = {}

            def fake_broll(shot, fal_key, output_path, log=print, **kwargs):
                calls[shot["shot_number"]] = kwargs.get("actor_photo_path", "")
                with open(output_path, "wb") as f:
                    f.write(b"png")
                return output_path

            config = {"fal_key": "k", "selected_actor_path": photo}
            with patch("saasshorts._broll_reference_image", side_effect=fake_broll):
                saasshorts._generate_storyboard_frames_only(shots, config, tmp, "vid")

            self.assertEqual(calls[1], photo)
            self.assertEqual(calls[2], "")

    def test_veo31_storyboard_uses_per_shot_when_multishot_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = {
                "title": "Veo shot",
                "format": "storyboard_v3",
                "full_narration": "One. Two.",
                "shots": [
                    {"shot_number": 1, "start": 0, "end": 4, "speech": "One.", "generation_prompt": "shot 1"},
                    {"shot_number": 2, "start": 4, "end": 8, "speech": "Two.", "generation_prompt": "shot 2"},
                ],
            }
            config = {
                "fal_key": "fal-test",
                "tts_provider": "fal_minimax",
                "language": "ru",
                "actor_gender": "female",
                "video_mode": "storyboard_veo31_quality",
                "storyboard_generation_mode": "multi_shot",
            }

            def fake_voiceover(text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"voice")
                return {"path": output_path, "provider": "fal_minimax", "voice_id": "Russian_AmbitiousWoman"}

            def fake_shot(shot, fal_key, output_path, tier="standard", aspect_ratio="9:16"):
                with open(output_path, "wb") as f:
                    f.write(b"shot")
                return output_path

            def fake_subs(audio_path, shots, output_path, max_words=2, **kwargs):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            def fake_composite(clips, audio_path, srt_path, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"final")
                return output_path

            with patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_voiceover), \
                 patch("saasshorts.generate_storyboard_shot_clip", side_effect=fake_shot) as shot_mock, \
                 patch("saasshorts.generate_storyboard_chunk_clip", side_effect=AssertionError("Veo should not use multi-shot chunks")), \
                 patch("saasshorts.generate_storyboard_ass_subtitles", side_effect=fake_subs), \
                 patch("saasshorts.composite_storyboard_video", side_effect=fake_composite), \
                 patch("saasshorts._decodable_audio_duration", return_value=8), \
                 patch("saasshorts._get_media_duration", return_value=8):
                result = generate_storyboard_video(script, config, tmp)

            self.assertEqual(shot_mock.call_count, 2)
            self.assertEqual(result["storyboard_generation_mode"], "per_shot")
            self.assertEqual(result["cost_estimate"]["storyboard_veo31_veo31_quality"], 1.6)


if __name__ == "__main__":
    unittest.main()

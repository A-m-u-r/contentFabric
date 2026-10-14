import asyncio
import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import saasshorts


NARRATION = (
    '[curious] Твой план работает только в идеальный день?\n'
    'Тогда он уже не работает.  [exhales] Но реальной неделе нужны две версии.\n'
    '[excited] Хочешь обе версии? Напиши «БЭКАП».'
)
TOKENS = list(re.finditer(r'\[[^\]\r\n]+\]|\S+', NARRATION))


def director_answer():
    # Deliberately unequal semantic ranges, not a fixed sentence splitter.
    return [{"title": "План на реальную неделю", "shots": [
        {"start_token": 1, "end_token": 13, "role": "hook",
         "visual_type": "talking", "actor_in_frame": False, "emotion": "curious"},
        {"start_token": 14, "end_token": 20, "role": "solution",
         "visual_type": "broll", "actor_in_frame": False, "emotion": "calm"},
        {"start_token": 21, "end_token": len(TOKENS), "role": "cta",
         "visual_type": "talking", "actor_in_frame": False, "emotion": "excited"},
    ]}]


def visual_answers(count=3):
    return [
        [{"script_index": 0, "set_scene": "Гостиная", "set_prompt": "A living room"}],
        [{"script_index": 0, "shot_number": index,
          "scene": f"Смысловой кадр {index}",
          "generation_prompt": f"vertical 9:16, distinct visual {index}, natural light",
          "camera": ""} for index in range(1, count + 1)],
    ]


class CustomScriptDirectorTests(unittest.TestCase):
    def generate(self, answer=None, **kwargs):
        answer = director_answer() if answer is None else answer
        with patch("google.genai.Client"), \
             patch("saasshorts._generate_analysis_content", return_value=SimpleNamespace(
                 text=json.dumps(answer), paid_provider=False,
             )) as ask, \
             patch("saasshorts._gemini_json_array", side_effect=visual_answers()) as visuals, \
             patch("saasshorts._split_text_for_segments", side_effect=AssertionError("No template splitting")), \
             patch("saasshorts._fal_run", side_effect=AssertionError("No paid fallback")):
            result = saasshorts.generate_custom_script(
                NARRATION, {"product_name": "Test"}, "key", language="ru",
                script_format=kwargs.pop("script_format", "storyboard_v3"), **kwargs,
            )
        return result, ask, visuals

    def test_ai_selects_ranges_but_cannot_rewrite_narration_or_tags(self):
        answer = director_answer()
        answer[0]["full_narration"] = "DO NOT USE THIS REWRITE"
        answer[0]["shots"][0].update(speech="FAKE SPEECH", actor_description="a different actor")
        result, ask, visuals = self.generate(answer, text_model="pro")
        self.assertEqual(result["full_narration"], NARRATION)
        self.assertEqual(len(result["shots"]), 3)
        for shot, proposed in zip(result["shots"], answer[0]["shots"]):
            expected = NARRATION[TOKENS[proposed["start_token"] - 1].start():TOKENS[proposed["end_token"] - 1].end()]
            self.assertEqual(shot["speech"], expected)
            self.assertNotIn("actor_description", shot)
        self.assertEqual(result["shots"][1]["scene"], "Смысловой кадр 2")
        self.assertEqual(result["storyboard_source"], "ai_custom_text")
        self.assertNotIn("target_duration_seconds", result)
        self.assertEqual(result["shots"][-1]["end"], result["duration_seconds"])
        self.assertEqual(result["duration_seconds"], saasshorts._estimate_speech_duration(NARRATION))
        self.assertEqual(ask.call_args.kwargs["text_model"], "pro")
        self.assertFalse(ask.call_args.kwargs.get("fal_fallback_enabled", False))
        self.assertEqual(visuals.call_count, 2)
        self.assertTrue(all(call.kwargs["text_model"] == "pro" for call in visuals.call_args_list))
        self.assertIn("start_token", ask.call_args.kwargs["contents"][0])

    def test_legacy_ugc_also_uses_ai_and_preserves_exact_speech(self):
        result, ask, _ = self.generate(script_format="ugc")
        self.assertEqual(result["full_narration"], NARRATION)
        self.assertNotIn("shots", result)
        self.assertEqual(len(result["segments"]), 3)
        self.assertEqual(result["segments"][1]["visual"], "broll")
        self.assertIn("distinct visual 2", result["segments"][1]["broll_prompt"])
        self.assertEqual(result["segments"][-1]["end"], result["duration_seconds"])
        ask.assert_called_once()

    def test_bad_ranges_fail_instead_of_silently_using_templates(self):
        changes = [
            (0, "start_token", 2),  # missing opening
            (1, "start_token", 13),  # overlap
            (1, "start_token", 15),  # gap
            (2, "end_token", len(TOKENS) - 1),  # missing CTA word
            (0, "start_token", True),
            (0, "end_token", 14.0),
            (0, "end_token", len(TOKENS) + 1),
        ]
        for index, field, value in changes:
            with self.subTest(field=field, value=value):
                answer = director_answer()
                answer[0]["shots"][index][field] = value
                with self.assertRaisesRegex(ValueError, "(?i)storyboard|раскадр"):
                    self.generate(answer)

    def test_audio_tag_cannot_be_left_at_the_end_of_previous_shot(self):
        answer = director_answer()
        answer[0]["shots"][0]["end_token"] = 14
        answer[0]["shots"][1]["start_token"] = 15
        with self.assertRaises(ValueError):
            self.generate(answer)

    def test_rhythm_flag_is_validated(self):
        answer = director_answer()
        answer[0]["shots"][1]["visual_type"] = "talking"
        with self.assertRaises(ValueError):
            self.generate(answer, broll_between_talking=True)
        result, _, _ = self.generate(broll_between_talking=True)
        self.assertEqual([s["visual_type"] for s in result["shots"]], ["talking", "broll", "talking"])

    def test_missing_visuals_are_reported_not_replaced_by_generic_prompts(self):
        with patch("google.genai.Client"), \
             patch("saasshorts._generate_analysis_content", return_value=SimpleNamespace(
                 text=json.dumps(director_answer()), paid_provider=False)), \
             patch("saasshorts._gemini_json_array", return_value=None):
            with self.assertRaises(ValueError):
                saasshorts.generate_custom_script(NARRATION, {}, "key", language="ru")

    def test_multiword_tags_are_indivisible_and_original_whitespace_survives(self):
        narration = '[laughs harder] Первая  фраза.\n\n[whispers] Вторая фраза.'
        answer = [{"shots": [{"start_token": 1, "end_token": 6,
                              "visual_type": "talking", "role": "hook"}]}]
        with patch("google.genai.Client"), \
             patch("saasshorts._generate_analysis_content", return_value=SimpleNamespace(
                 text=json.dumps(answer), paid_provider=False)), \
             patch("saasshorts._gemini_json_array", side_effect=visual_answers(1)):
            result = saasshorts.generate_custom_script(narration, {}, "key", script_format="storyboard_v3")
        self.assertEqual(result["shots"][0]["speech"], narration)

    def test_final_nonverbal_tag_is_preserved(self):
        narration = '[curious] Это мой план. [exhales]'
        answer = [{"shots": [{"start_token": 1, "end_token": 5,
                              "visual_type": "talking", "role": "hook"}]}]
        with patch("google.genai.Client"), \
             patch("saasshorts._generate_analysis_content", return_value=SimpleNamespace(
                 text=json.dumps(answer), paid_provider=False)), \
             patch("saasshorts._gemini_json_array", side_effect=visual_answers(1)):
            result = saasshorts.generate_custom_script(narration, {}, "key")
        self.assertEqual(result["full_narration"], narration)
        self.assertEqual(result["shots"][0]["speech"], narration)

    def test_invalid_metadata_fails_before_visual_requests(self):
        for field in ("emotion", "role", "transition"):
            answer = director_answer()
            answer[0]["shots"][0][field] = ["invalid"]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.generate(answer)

    def test_requested_location_changes_reach_normalized_shots(self):
        decisions = visual_answers()
        decisions[0] = [{"script_index": 0, "sets": [
            {"set_scene": "Гостиная", "set_prompt": "A living room"},
            {"set_scene": "Балкон", "set_prompt": "A balcony"},
        ]}]
        with patch("google.genai.Client"), \
             patch("saasshorts._generate_analysis_content", return_value=SimpleNamespace(
                 text=json.dumps(director_answer()), paid_provider=False)), \
             patch("saasshorts._gemini_json_array", side_effect=decisions):
            result = saasshorts.generate_custom_script(NARRATION, {}, "key", changing_locations=True)
        self.assertTrue(result["set_changes"])
        self.assertEqual(len(result["set_prompts"]), 2)
        self.assertTrue(result["shots"][0]["_set_chosen"])

    def test_invalid_first_answer_can_be_retried_without_template_fallback(self):
        bad = director_answer()
        bad[0]["shots"][-1]["end_token"] -= 1
        with patch("google.genai.Client"), \
             patch("saasshorts._generate_analysis_content", side_effect=[
                 SimpleNamespace(text=json.dumps(answer), paid_provider=False)
                 for answer in (bad, director_answer())
             ]) as ask, \
             patch("saasshorts._gemini_json_array", side_effect=visual_answers()):
            result = saasshorts.generate_custom_script(NARRATION, {}, "key")
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(result["full_narration"], NARRATION)


class CustomAnalyzeRouteTests(unittest.TestCase):
    def test_custom_text_calls_director_with_user_options(self):
        import app
        request = app.SaaSAnalyzeRequest(
            script_mode="custom", script_format="storyboard_v3", custom_script=NARRATION,
            language="ru", text_model="pro", topic="Backup plan", description="Product",
            broll_between_talking=True, changing_locations=True, target_duration_seconds=15,
            generation_preset="expressive",
        )
        with patch("app.resolve_effective_api_key", return_value="key"), \
             patch("app.generate_custom_script", return_value={"full_narration": NARRATION}) as director, \
             patch("app.build_custom_script", side_effect=AssertionError("No automatic splitting")):
            result = asyncio.run(app.saasshorts_analyze(request, authorization=None))
        self.assertEqual(result["scripts"][0]["full_narration"], NARRATION)
        self.assertTrue(director.call_args.kwargs["changing_locations"])
        self.assertTrue(director.call_args.kwargs["broll_between_talking"])
        self.assertEqual(director.call_args.kwargs["text_model"], "pro")
        self.assertEqual(director.call_args.kwargs["generation_preset"], "expressive")
        self.assertNotIn("target_duration_seconds", director.call_args.kwargs)

    def test_manual_storyboard_import_does_not_need_keys_or_ai(self):
        import app
        request = app.SaaSAnalyzeRequest(
            script_mode="custom", script_format="storyboard_v3",
            custom_script="## КАДР 1 — 0:00–0:04\nОна говорит:\n> «Привет, это мой сценарий.»",
        )
        with patch("app.resolve_effective_api_key", side_effect=AssertionError("No keys needed")), \
             patch("app.generate_custom_script", side_effect=AssertionError("No AI needed")):
            result = asyncio.run(app.saasshorts_analyze(request, authorization=None))
        self.assertEqual(len(result["scripts"][0]["shots"]), 1)
        self.assertIn("мой сценарий", result["scripts"][0]["full_narration"])

    def test_plain_text_requires_a_model_key(self):
        import app
        with patch("app.resolve_effective_api_key", return_value=""), \
             self.assertRaises(app.HTTPException) as error:
            asyncio.run(app.saasshorts_analyze(app.SaaSAnalyzeRequest(
                script_mode="custom", custom_script=NARRATION,
            ), authorization=None))
        self.assertEqual(error.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from unittest.mock import patch

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


class SaaSStoryboardTests(unittest.TestCase):
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
        self.assertIn("no burned-in text", shot["generation_prompt"])

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

            self.assertEqual(chunk_mock.call_count, 2)
            self.assertEqual(len(chunk_mock.call_args_list[0].args[0]), 4)
            self.assertEqual(len(chunk_mock.call_args_list[1].args[0]), 2)
            self.assertEqual(result["cost_estimate"]["storyboard_kling_v3_standard"], 1.68)

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

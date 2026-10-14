import copy
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app
import saasshorts


CALM_PROMPT = (
    "Calm, understated conversational delivery to the camera. Relaxed facial expression, "
    "subtle expressions that follow the audio, gentle natural blinking. Small natural lip "
    "movements, relaxed jaw and eyebrows, a faint occasional smile. The body and hands remain "
    "comfortably still in the original pose. One continuous locked-off take."
)


class CalmUgcPresetTests(unittest.TestCase):
    def apply(self, script, preset):
        self.assertTrue(callable(getattr(saasshorts, "apply_generation_preset", None)),
                        "The normal pipeline needs a shared preset, not runtime monkeypatches")
        return saasshorts.apply_generation_preset(script, preset)

    def test_new_api_requests_default_to_approved_voice_and_calm_preset(self):
        request = app.SaaSGenerateRequest(script={}).model_dump()
        self.assertEqual(request.get("generation_preset"), "calm_ugc")
        self.assertEqual(request["elevenlabs_model"], "eleven_v4")
        self.assertEqual(request["elevenlabs_stability"], 0.65)
        self.assertEqual(request["elevenlabs_similarity"], 0.75)
        self.assertEqual(app.SaaSAnalyzeRequest().model_dump().get("generation_preset"), "calm_ugc")

    def test_calm_preset_strips_directions_without_rewriting_or_mutating_source(self):
        source = {
            "full_narration": "[whispers] Сладкое вечером. [excited] Верни обед!",
            "shots": [
                {"shot_number": 1, "visual_type": "talking", "speech": "[whispers] Сладкое вечером.",
                 "emotion": "whisper", "_performance": "whisper", "image_path": "/approved.png"},
                {"shot_number": 2, "visual_type": "broll", "speech": "[excited] Верни обед!",
                 "scene": "Обед и перекус", "generation_prompt": "A sandwich and an apple"},
            ],
        }
        original = copy.deepcopy(source)
        result = self.apply(source, "calm_ugc")
        self.assertEqual(source, original)
        self.assertEqual(result["full_narration"], "Сладкое вечером. Верни обед!")
        self.assertEqual([shot["speech"] for shot in result["shots"]], ["Сладкое вечером.", "Верни обед!"])
        self.assertEqual(result["shots"][0]["image_path"], "/approved.png")
        self.assertEqual(result["shots"][1]["generation_prompt"], original["shots"][1]["generation_prompt"])
        self.assertEqual(saasshorts._shot_performance(result["shots"][0]), "normal")
        self.assertEqual(self.apply(result, "calm_ugc"), result)

    def test_expressive_preset_keeps_authored_audio_directions(self):
        source = {"full_narration": "[whispers] Привет.", "shots": [{"speech": "[whispers] Привет."}]}
        result = self.apply(source, "expressive")
        self.assertEqual(result["full_narration"], source["full_narration"])
        self.assertEqual(result["shots"][0]["speech"], source["shots"][0]["speech"])

    def test_calm_motion_matches_the_approved_paid_take(self):
        prompt = saasshorts._avatar_motion_prompt_for_shot({"_generation_preset": "calm_ugc", "speech": "Привет."})
        self.assertEqual(prompt, CALM_PROMPT)

    def test_simple_avatar_mode_also_receives_calm_motion(self):
        class StopBeforePaidCall(Exception):
            pass
        with tempfile.TemporaryDirectory() as tmp:
            voice = os.path.join(tmp, "calm_voice.mp3")
            for name in (voice, os.path.join(tmp, "calm_actor.png")):
                with open(name, "wb") as handle:
                    handle.write(b"cached")
            signature = saasshorts._tts_signature(
                "Привет.", "elevenlabs", "qa", "Russian_AmbitiousWoman", "ru", "female",
                elevenlabs_model="eleven_v4", elevenlabs_stability=0.65, elevenlabs_similarity=0.75,
            )
            saasshorts._write_tts_metadata(voice, {"signature": signature, "provider": "elevenlabs", "model": "eleven_v4"})
            config = {"generation_preset": "calm_ugc", "fal_key": "no-paid-key", "voice_id": "qa",
                      "language": "ru", "tts_provider": "elevenlabs", "elevenlabs_model": "eleven_v4",
                      "elevenlabs_stability": 0.65, "elevenlabs_similarity": 0.75}
            with patch("saasshorts.prepare_voiceover_for_video_generation", return_value={"path": voice}), \
                 patch("saasshorts.generate_talking_head", side_effect=StopBeforePaidCall) as avatar, \
                 patch("saasshorts.generate_voiceover_with_fallback", side_effect=AssertionError("No paid TTS")):
                with self.assertRaises(StopBeforePaidCall):
                    saasshorts.generate_full_video({"title": "calm", "language": "ru", "full_narration": "[excited] Привет."}, config, tmp)
            self.assertEqual(avatar.call_args.kwargs.get("motion_prompt"), CALM_PROMPT)

    def test_calm_edit_has_no_automatic_camera_punch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "clip.mp4")
            with open(path, "wb") as handle:
                handle.write(b"clip")
            clips = [{"path": path, "duration": 3.0,
                      "shot": {"visual_type": "talking", "_generation_preset": "calm_ugc"}}]
            with patch("saasshorts._get_media_duration", return_value=3.0), \
                 patch("saasshorts._measure_final_loudness", return_value=None), \
                 patch("saasshorts.subprocess.run") as run:
                saasshorts.composite_storyboard_video(clips, "/voice.mp3", "/subs.ass", os.path.join(tmp, "final.mp4"))
            command = run.call_args.args[0]
            graph = command[command.index("-filter_complex") + 1]
            self.assertNotIn("zoompan", graph)

    def test_full_video_passes_prepared_narration_to_existing_storyboard_pipeline(self):
        source = {"format": "storyboard_v3", "full_narration": "[excited] Привет.",
                  "shots": [{"speech": "[excited] Привет.", "visual_type": "talking"}]}
        with tempfile.TemporaryDirectory() as tmp, \
             patch("saasshorts.generate_storyboard_video", return_value={"duration": 3}) as render:
            saasshorts.generate_full_video(source, {"generation_preset": "calm_ugc"}, tmp)
        forwarded = render.call_args.args[0]
        self.assertEqual(forwarded["full_narration"], "Привет.")
        self.assertEqual(forwarded["shots"][0].get("_generation_preset"), "calm_ugc")
        self.assertEqual(source["full_narration"], "[excited] Привет.")

    def test_calm_director_still_chooses_ai_boundaries_without_tagged_speech(self):
        narration = "[curious] Проверь обед. [excited] Верни перекус."
        proposal = [{"title": "Обед", "shots": [
            {"start_token": 1, "end_token": 2, "role": "hook", "visual_type": "talking"},
            {"start_token": 3, "end_token": 4, "role": "cta", "visual_type": "talking"},
        ]}]
        visuals = [
            [{"script_index": 0, "set_scene": "Кухня", "set_prompt": "A kitchen"}],
            [{"script_index": 0, "shot_number": n, "scene": "Спокойный ведущий",
              "generation_prompt": "A person standing calmly in a kitchen", "camera": ""} for n in (1, 2)],
        ]
        with patch("google.genai.Client"), \
             patch("saasshorts._generate_analysis_content", return_value=SimpleNamespace(text=json.dumps(proposal))) as ask, \
             patch("saasshorts._gemini_json_array", side_effect=visuals), \
             patch("saasshorts._fal_run", side_effect=AssertionError("No paid provider in tests")):
            try:
                result = saasshorts.generate_custom_script(narration, {}, "fake", language="ru", generation_preset="calm_ugc")
            except TypeError as error:
                self.fail(str(error))
        self.assertEqual(result["full_narration"], "Проверь обед. Верни перекус.")
        self.assertEqual([shot["speech"] for shot in result["shots"]], ["Проверь обед.", "Верни перекус."])
        self.assertIn("Calm", ask.call_args.kwargs["contents"][0])
        self.assertTrue(all(shot["_generation_preset"] == "calm_ugc" for shot in result["shots"]))


if __name__ == "__main__":
    unittest.main()

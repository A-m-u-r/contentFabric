import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "voice_ab_fal.py"
SPEC = importlib.util.spec_from_file_location("voice_ab_fal", MODULE_PATH)
voice_ab_fal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(voice_ab_fal)


class VoiceAbFalTests(unittest.TestCase):
    def test_presets_keep_same_voice_and_source_text_for_model_comparison(self):
        trials = voice_ab_fal.trials()
        by_code = {trial["code"]: trial for trial in trials}
        self.assertEqual(len(trials), 10)
        self.assertEqual(by_code["A1"]["text"], by_code["A2"]["text"])
        self.assertEqual(by_code["B1"]["text"], by_code["B2"]["text"])
        self.assertEqual({trial["voice"] for trial in trials}, {voice_ab_fal.ANNA_VOICE_ID})
        self.assertEqual(by_code["A1"]["model"], "eleven_v3")
        self.assertEqual(by_code["A2"]["model"], "eleven_v4")
        self.assertEqual(by_code["B2"]["model"], "eleven_v4")

    def test_v4_only_uses_documented_controls(self):
        for trial in voice_ab_fal.trials():
            payload = voice_ab_fal.fal_input(trial)
            self.assertIn("voice", payload)
            self.assertIn("text", payload)
            self.assertNotIn("speed", payload)
            self.assertNotIn("style", payload)
            if trial["model"] == "eleven_v4":
                self.assertEqual(voice_ab_fal.model_id(trial), "elevenlabs/tts/eleven-v4")

    def test_cost_cap_is_below_twenty_cents(self):
        self.assertLessEqual(voice_ab_fal.estimated_cost(voice_ab_fal.trials()), 0.20)

    def test_existing_audio_does_not_submit_another_paid_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = pathlib.Path(tmp) / "A1.mp3"
            audio.write_bytes(b"x" * 1001)
            with patch("saasshorts._fal_run") as submit:
                result = voice_ab_fal.run_trial(voice_ab_fal.trials()[0], "unused", pathlib.Path(tmp))
            self.assertEqual(result, audio)
            submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from saasshorts import (
    _align_shots_to_voiceover,
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
        cm, client = _fake_http_client([_response(403), _response(500)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "voice.mp3")
            with patch("saasshorts.httpx.Client", return_value=cm):
                with self.assertRaises(Exception):
                    generate_voiceover("Привет", "key", out)
        self.assertEqual(client.post.call_count, 2)


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

import os
import tempfile
import unittest
from unittest.mock import patch

from saasshorts import (
    _align_asr_words_to_script,
    _final_audio_filter_parts,
    _pick_background_music,
    _strip_pictographs,
    _subtitle_filter,
    composite_storyboard_video,
    generate_storyboard_ass_subtitles,
)


def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


class AlignAsrWordsToScriptTest(unittest.TestCase):
    def test_misheard_words_replaced_with_script_text(self):
        # The real bug: Whisper base heard «слабое» instead of «слабая».
        asr = [
            _w("Ты", 0.0, 0.3),
            _w("срываешься", 0.3, 1.0),
            _w("не", 1.0, 1.2),
            _w("потому", 1.2, 1.6),
            _w("что", 1.6, 1.8),
            _w("слабое.", 1.8, 2.4),
        ]
        script = "Ты срываешься не потому, что слабая."
        aligned = _align_asr_words_to_script(asr, script, log=lambda *_: None)
        self.assertEqual([w["word"] for w in aligned],
                         ["Ты", "срываешься", "не", "потому,", "что", "слабая."])
        # Timings come from ASR: matched words keep them exactly.
        self.assertEqual(aligned[0]["start"], 0.0)
        self.assertEqual(aligned[1]["end"], 1.0)
        self.assertEqual(aligned[5]["start"], 1.8)
        self.assertEqual(aligned[5]["end"], 2.4)

    def test_extra_asr_words_dropped(self):
        asr = [
            _w("Стоп", 0.0, 0.4),
            _w("э-э", 0.4, 0.7),  # hallucinated filler
            _w("методы", 0.7, 1.3),
        ]
        aligned = _align_asr_words_to_script(asr, "Стоп методы", log=lambda *_: None)
        self.assertEqual([w["word"] for w in aligned], ["Стоп", "методы"])

    def test_missing_script_words_interpolated_monotonically(self):
        asr = [
            _w("кортизол", 0.0, 0.8),
            # whisper swallowed «и грелин»
            _w("физиология", 2.0, 3.0),
        ]
        aligned = _align_asr_words_to_script(
            asr, "кортизол и грелин физиология", log=lambda *_: None
        )
        self.assertEqual(len(aligned), 4)
        prev_end = 0.0
        for w in aligned:
            self.assertGreaterEqual(w["start"], prev_end)
            self.assertGreaterEqual(w["end"], w["start"])
            prev_end = w["end"]
        # The missing words sit inside the gap between their matched neighbours.
        self.assertGreaterEqual(aligned[1]["start"], 0.8)
        self.assertLessEqual(aligned[2]["end"], 2.0)

    def test_mismatched_audio_keeps_raw_asr(self):
        asr = [_w("совсем", 0.0, 0.5), _w("другой", 0.5, 1.0), _w("текст", 1.0, 1.5)]
        aligned = _align_asr_words_to_script(
            asr, "про запуск ракеты в стратосферу без остановки", log=lambda *_: None
        )
        self.assertIs(aligned, asr)

    def test_audio_tags_never_reach_subtitles(self):
        asr = [_w("Стоп,", 0.0, 0.4), _w("стоп!", 0.4, 0.9)]
        aligned = _align_asr_words_to_script(asr, "[sighs] Стоп, стоп!", log=lambda *_: None)
        joined = " ".join(w["word"] for w in aligned)
        self.assertNotIn("sighs", joined)
        self.assertEqual([w["word"] for w in aligned], ["Стоп,", "стоп!"])

    def test_punctuation_only_token_glued_to_previous_word(self):
        asr = [_w("грелин", 0.0, 0.6), _w("это", 0.6, 0.9), _w("физиология", 0.9, 1.6)]
        aligned = _align_asr_words_to_script(
            asr, "грелин — это физиология", log=lambda *_: None
        )
        self.assertEqual([w["word"] for w in aligned], ["грелин —", "это", "физиология"])

    def test_empty_asr_returns_empty(self):
        self.assertEqual(_align_asr_words_to_script([], "текст", log=lambda *_: None), [])


class StripPictographsTest(unittest.TestCase):
    def test_removes_emoji_and_arrows_keeps_text(self):
        self.assertEqual(_strip_pictographs("ТВОЯ НОВАЯ ФОРМА 30+ ⬇️"), "ТВОЯ НОВАЯ ФОРМА 30+")
        self.assertEqual(_strip_pictographs("жми → сюда 🔥"), "жми сюда")
        self.assertEqual(_strip_pictographs("без пиктограмм"), "без пиктограмм")
        self.assertEqual(_strip_pictographs("💪✨"), "")


class StoryboardAssTest(unittest.TestCase):
    def test_ass_uses_bundled_font_no_overlays_no_emoji(self):
        shots = [{
            "shot_number": 1,
            "role": "hook",
            "speech": "Стоп, стоп!",
            "overlay_text": "ТЫ НЕ СЛАБАЯ ⬇️",
            "duration": 5,
        }]
        words = [_w("Стоп,", 0.0, 0.5), _w("стоп!🔥", 0.5, 1.0)]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "subs.ass")
            generate_storyboard_ass_subtitles("unused.mp3", shots, out, words=words)
            with open(out, encoding="utf-8") as f:
                content = f.read()
        self.assertIn("Montserrat ExtraBold", content)
        self.assertNotIn("Arial Black", content)
        self.assertNotIn("⬇", content)
        self.assertNotIn("🔥", content)
        # Top plates are gone: overlay_text must not reach the video.
        self.assertNotIn("ТЫ НЕ СЛАБАЯ", content)
        self.assertIn("СТОП, СТОП!", content)


class SubtitleFilterTest(unittest.TestCase):
    def test_ass_filter_includes_fontsdir_when_available(self):
        with patch("saasshorts.os.path.isdir", return_value=True):
            flt = _subtitle_filter("/app/output/subs.ass")
        self.assertTrue(flt.startswith("ass="))
        self.assertIn("fontsdir=", flt)

    def test_srt_fallback_styled_with_bundled_font(self):
        with patch("saasshorts.os.path.isdir", return_value=True):
            flt = _subtitle_filter("/app/output/subs.srt")
        self.assertIn("subtitles=", flt)
        self.assertIn("Montserrat ExtraBold", flt)


class BackgroundMusicTest(unittest.TestCase):
    def test_pick_is_deterministic_and_skips_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("beat_a.mp3", "beat_b.mp3"):
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(b"x")
            with patch("saasshorts._MUSIC_DIR", tmp):
                first = _pick_background_music("same_title")
                second = _pick_background_music("same_title")
            self.assertEqual(first, second)
            self.assertTrue(first.endswith(".mp3"))
        with patch("saasshorts._MUSIC_DIR", os.path.join(tmp, "missing")):
            self.assertIsNone(_pick_background_music("same_title"))

    def test_final_audio_chain_with_music_ducks_and_normalizes(self):
        parts = ";".join(_final_audio_filter_parts("2", "3", 0.16))
        self.assertIn("sidechaincompress", parts)
        self.assertIn("normalize=0", parts)
        self.assertIn("loudnorm=I=-14", parts)
        self.assertIn("[aout]", parts)

    def test_final_audio_chain_without_music_only_normalizes(self):
        parts = ";".join(_final_audio_filter_parts("2", None, 0.16))
        self.assertNotIn("sidechaincompress", parts)
        self.assertIn("loudnorm=I=-14", parts)


class CompositeStoryboardAudioTest(unittest.TestCase):
    @patch("saasshorts.subprocess.run")
    @patch("saasshorts._get_media_duration", return_value=5.0)
    def test_composite_maps_normalized_audio_and_loops_music(self, _dur, run_mock):
        clips = [{"path": "/tmp/a.mp4", "duration": 5.0}]
        composite_storyboard_video(
            clips, "/tmp/voice.mp3", "/tmp/subs.ass", "/tmp/out.mp4",
            music_path="/tmp/bed.mp3",
        )
        cmd = run_mock.call_args[0][0]
        self.assertIn("-stream_loop", cmd)
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("sidechaincompress", filter_complex)
        self.assertIn("loudnorm", filter_complex)
        map_targets = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-map"]
        self.assertIn("[aout]", map_targets)

    @patch("saasshorts.subprocess.run")
    @patch("saasshorts._get_media_duration", return_value=5.0)
    def test_composite_without_music_still_normalizes(self, _dur, run_mock):
        clips = [{"path": "/tmp/a.mp4", "duration": 5.0}]
        composite_storyboard_video(clips, "/tmp/voice.mp3", "/tmp/subs.ass", "/tmp/out.mp4")
        cmd = run_mock.call_args[0][0]
        self.assertNotIn("-stream_loop", cmd)
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("loudnorm", filter_complex)
        self.assertNotIn("sidechaincompress", filter_complex)


if __name__ == "__main__":
    unittest.main()

import array
import math
import os
import tempfile
import unittest
import wave
from unittest.mock import patch

import saasshorts
from saasshorts import (
    _align_asr_words_to_script,
    _final_audio_filter_parts,
    _loudnorm_filter,
    _pick_background_music,
    _snap_captions_to_speech,
    _strip_pictographs,
    _subtitle_filter,
    composite_storyboard_video,
    generate_storyboard_ass_subtitles,
    generate_tiktok_subs,
)


MEASURED = {
    "input_i": "-15.49",
    "input_tp": "-0.90",
    "input_lra": "3.20",
    "input_thresh": "-25.60",
    "target_offset": "0.30",
}


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
    def test_tiktok_default_emits_one_dialogue_per_word(self):
        words = [
            _w("ONE,", 0.0, 0.3),
            _w("TWO.", 0.3, 0.6),
            _w("WHY?", 0.6, 1.0),
            _w("STOP!", 1.0, 1.3),
            _w("PAUSE…", 1.3, 1.6),
            _w("VALUE:", 1.6, 1.9),
            _w("NEXT;", 1.9, 2.2),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "subs.ass")
            generate_tiktok_subs("unused.mp3", out, words=words)
            with open(out, encoding="utf-8") as f:
                content = f.read()

        dialogue = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(len(dialogue), 7)
        rendered = "\n".join(dialogue)
        for hidden in ("ONE,", "TWO.", "PAUSE…", "VALUE:", "NEXT;"):
            self.assertNotIn(hidden, rendered)
        for visible in ("ONE", "TWO", "WHY?", "STOP!", "PAUSE", "VALUE", "NEXT"):
            self.assertIn(visible, rendered)

    def test_storyboard_default_emits_one_dialogue_per_word(self):
        words = [
            _w("ONE,", 0.0, 0.3),
            _w("TWO.", 0.3, 0.6),
            _w("WHY?", 0.6, 1.0),
            _w("STOP!", 1.0, 1.3),
            _w("PAUSE…", 1.3, 1.6),
            _w("VALUE:", 1.6, 1.9),
            _w("NEXT;", 1.9, 2.2),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "subs.ass")
            with patch("saasshorts._snap_captions_to_speech", return_value=0):
                generate_storyboard_ass_subtitles("unused.mp3", [], out, words=words)
            with open(out, encoding="utf-8") as f:
                content = f.read()

        dialogue = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(len(dialogue), 7)
        rendered = "\n".join(dialogue)
        for hidden in ("ONE,", "TWO.", "PAUSE…", "VALUE:", "NEXT;"):
            self.assertNotIn(hidden, rendered)
        for visible in ("ONE", "TWO", "WHY?", "STOP!", "PAUSE", "VALUE", "NEXT"):
            self.assertIn(visible, rendered)

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
        dialogue = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(len(dialogue), 2)
        self.assertTrue(any(line.endswith("СТОП") for line in dialogue))
        self.assertTrue(any(line.endswith("СТОП!") for line in dialogue))


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
        parts = ";".join(_final_audio_filter_parts("2", "3", 1.0, music_gain_db=-8.6))
        self.assertIn("sidechaincompress", parts)
        self.assertIn("normalize=0", parts)
        self.assertIn("loudnorm=I=-14", parts)
        self.assertIn("[aout]", parts)

    def test_music_bed_is_normalized_and_ducking_is_gentle(self):
        # Подложку не слышно было из-за слепого volume=0.16 поверх и без того
        # тихого трека (-23.7 dBFS) плюс даккинг ratio 12 / release 500ms,
        # который в почти сплошной речи не давал беду подняться вообще.
        parts = ";".join(_final_audio_filter_parts("2", "3", 1.0, music_gain_db=-8.6))
        self.assertIn("volume=-8.60dB", parts)
        self.assertIn("ratio=6", parts)
        self.assertNotIn("ratio=12", parts)
        self.assertNotIn("release=500", parts)

    def test_music_gain_targets_a_fixed_level(self):
        with patch("saasshorts.subprocess.run") as run_mock:
            run_mock.return_value.stderr = "[Parsed_volumedetect_0 @ 0x1] mean_volume: -23.4 dB"
            gain = saasshorts._music_bed_gain_db("/tmp/some-bed.mp3", target_dbfs=-32.0)
        self.assertAlmostEqual(gain, -8.6, places=2)

    def test_unmeasurable_track_is_left_alone(self):
        with patch("saasshorts.subprocess.run", side_effect=OSError("no ffmpeg")):
            self.assertEqual(saasshorts._music_bed_gain_db("/tmp/broken-bed.mp3"), 0.0)

    def test_final_audio_chain_without_music_only_normalizes(self):
        parts = ";".join(_final_audio_filter_parts("2", None, 1.0))
        self.assertNotIn("sidechaincompress", parts)
        self.assertIn("loudnorm=I=-14", parts)


class TwoPassLoudnormTest(unittest.TestCase):
    """Однопроходный loudnorm давит и без того узкую динамику TTS-речи."""

    def test_measured_values_switch_loudnorm_to_linear_gain(self):
        flt = _loudnorm_filter(MEASURED)
        self.assertIn("loudnorm=I=-14:TP=-1.5:LRA=11", flt)
        self.assertIn("measured_I=-15.49", flt)
        self.assertIn("measured_thresh=-25.60", flt)
        self.assertIn("offset=0.30", flt)
        self.assertIn("linear=true", flt)

    def test_without_measurements_stays_one_pass(self):
        flt = _loudnorm_filter(None)
        self.assertNotIn("linear=true", flt)
        self.assertNotIn("measured_I", flt)

    def test_measure_pass_asks_ffmpeg_for_json(self):
        parts = ";".join(_final_audio_filter_parts("2", None, 0.16, print_json=True))
        self.assertIn("print_format=json", parts)

    @patch("saasshorts.subprocess.run")
    @patch("saasshorts._get_media_duration", return_value=5.0)
    @patch("saasshorts._measure_final_loudness", return_value=MEASURED)
    def test_composite_applies_the_measured_pass(self, _measure, _dur, run_mock):
        composite_storyboard_video(
            [{"path": "/tmp/a.mp4", "duration": 5.0}],
            "/tmp/voice.mp3", "/tmp/subs.ass", "/tmp/out.mp4",
        )
        filter_complex = run_mock.call_args[0][0][
            run_mock.call_args[0][0].index("-filter_complex") + 1
        ]
        self.assertIn("linear=true", filter_complex)

    @patch("saasshorts.subprocess.run")
    @patch("saasshorts._get_media_duration", return_value=5.0)
    @patch("saasshorts._measure_final_loudness", return_value=None)
    def test_failed_measurement_falls_back_to_one_pass(self, _measure, _dur, run_mock):
        composite_storyboard_video(
            [{"path": "/tmp/a.mp4", "duration": 5.0}],
            "/tmp/voice.mp3", "/tmp/subs.ass", "/tmp/out.mp4",
        )
        filter_complex = run_mock.call_args[0][0][
            run_mock.call_args[0][0].index("-filter_complex") + 1
        ]
        self.assertIn("loudnorm=I=-14", filter_complex)
        self.assertNotIn("linear=true", filter_complex)


def _write_tone_silence_tone(path, sample_rate=16000):
    """3s: тон, секунда тишины, снова тон — модель паузы от тега [sighs]."""
    frames = array.array("h")
    for i in range(sample_rate * 3):
        t = i / sample_rate
        voiced = t < 1.0 or t >= 2.0
        frames.append(int(12000 * math.sin(2 * math.pi * 220 * t)) if voiced else 0)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames.tobytes())


class SnapCaptionsToSpeechTest(unittest.TestCase):
    """Плашка не должна появляться раньше, чем слышно слово."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.audio = os.path.join(self.tmp.name, "voice.wav")
        _write_tone_silence_tone(self.audio)

    def tearDown(self):
        self.tmp.cleanup()

    def test_caption_starting_in_silence_waits_for_the_voice(self):
        # Whisper отдал слову старт 1.2с, а звук возвращается только на 2.0с.
        chunks = [{"text": "ДЕЛАЮТ ТЕБЯ", "start": 1.2, "end": 2.8}]
        moved = _snap_captions_to_speech(chunks, self.audio)
        self.assertEqual(moved, 1)
        self.assertAlmostEqual(chunks[0]["start"], 1.88, delta=0.06)

    def test_caption_already_on_speech_is_left_alone(self):
        chunks = [{"text": "ТАК, СТОП", "start": 0.3, "end": 0.9}]
        self.assertEqual(_snap_captions_to_speech(chunks, self.audio), 0)
        self.assertEqual(chunks[0]["start"], 0.3)

    def test_caption_is_never_pushed_past_its_own_end(self):
        chunks = [{"text": "ХВОСТ", "start": 1.2, "end": 1.3}]
        self.assertEqual(_snap_captions_to_speech(chunks, self.audio), 0)
        self.assertEqual(chunks[0]["start"], 1.2)

    def test_unreadable_audio_leaves_timings_untouched(self):
        chunks = [{"text": "ЧТО-ТО", "start": 1.2, "end": 2.8}]
        with patch("saasshorts._speech_onset_mask", return_value=None):
            self.assertEqual(_snap_captions_to_speech(chunks, self.audio), 0)
        self.assertEqual(chunks[0]["start"], 1.2)


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

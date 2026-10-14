import hashlib
import itertools
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import saasshorts
from saasshorts import (
    _ensure_slice_audio,
    _split_long_slices,
    build_incremental_voiceover,
    read_voice_manifest,
)

SLUG = "reel"
SETTINGS = {
    "provider": "elevenlabs",
    "fal_key": "fal-test",
    "elevenlabs_key": "el-test",
    "voice_id": "voice_ru",
    "minimax_voice_id": "Russian_AmbitiousWoman",
    "language": "ru",
    "actor_gender": "female",
}


def shot(number, speech, visual_type="talking"):
    return {"shot_number": number, "speech": speech, "visual_type": visual_type,
            "scene": f"scene {number}"}


def spoken_audio(text):
    """Audio shaped like a take: silence, wobbling tone, silence.

    Real samples, not a stub — the builder decodes what the provider returns,
    measures its loudness and cuts it into per-shot pieces, so a five-byte
    placeholder would only ever exercise the fallback.
    """
    rate = saasshorts._VOICE_SAMPLE_RATE
    seconds = max(1.0, len(text) / 15.0)
    t = np.arange(int(rate * seconds)) / rate
    tone = 0.3 * np.sin(2 * np.pi * 220 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    edge = np.zeros(int(rate * 0.25), dtype=np.float32)
    return np.concatenate([edge, tone.astype(np.float32), edge])


def digest(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def manifest_piece(tmp, number):
    entry = read_voice_manifest(tmp, SLUG)[str(number)]
    return os.path.join(tmp, entry["piece"])


class IncrementalVoiceoverTests(unittest.TestCase):
    def setUp(self):
        self.spoken = []

    def fake_tts(self, text, output_path, **kwargs):
        self.spoken.append(text)
        saasshorts._encode_audio_samples(spoken_audio(text), output_path)
        return {"path": output_path, "provider": "elevenlabs",
                "voice_id": "voice_ru", "model": "eleven_v3"}

    def build(self, shots, tmp, **overrides):
        with patch("saasshorts.generate_voiceover_with_fallback", side_effect=self.fake_tts), \
             patch("saasshorts.transcribe_audio_for_subs", return_value=[]):
            return build_incremental_voiceover(
                shots, tmp, SLUG, log=lambda *_: None, **{**SETTINGS, **overrides}
            )

    def test_a_run_of_changed_shots_is_voiced_as_one_take(self):
        shots = [shot(1, "Первая реплика."), shot(2, "Вторая реплика."), shot(3, "Третья реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(shots, tmp)

        # One request for three shots: the fewer joins, the more natural the read.
        self.assertEqual(self.spoken, ["Первая реплика. Вторая реплика. Третья реплика."])
        self.assertEqual([b["shot_number"] for b in result["bounds"]], [1, 2, 3])
        self.assertEqual(result["changed_shots"], [1, 2, 3])
        # The bounds tile the master without holes: the video timeline is built
        # from them, so a gap would be a gap on screen.
        for left, right in zip(result["bounds"], result["bounds"][1:]):
            self.assertAlmostEqual(left["end"], right["start"], places=3)

    def test_an_unchanged_script_costs_nothing_and_moves_nothing(self):
        shots = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            first = self.build(shots, tmp)
            pieces = {n: digest(os.path.join(tmp, f"{SLUG}_speech_{n:02d}.wav")) for n in (1, 2)}
            self.spoken.clear()
            second = self.build(shots, tmp)

            self.assertEqual(self.spoken, [])
            self.assertEqual(second["changed_shots"], [])
            self.assertEqual(second["bounds"], first["bounds"])
            for number, before in pieces.items():
                self.assertEqual(digest(os.path.join(tmp, f"{SLUG}_speech_{number:02d}.wav")), before)

    def test_switching_v3_to_v4_revoices_each_shot_once(self):
        shots = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            self.build(shots, tmp, elevenlabs_model="eleven_v3")
            self.spoken.clear()
            changed = self.build(shots, tmp, elevenlabs_model="eleven_v4")
            self.assertEqual(self.spoken, ["Первая реплика. Вторая реплика."])
            self.assertEqual(changed["changed_shots"], [1, 2])
            self.spoken.clear()
            cached = self.build(shots, tmp, elevenlabs_model="eleven_v4")
            self.assertEqual(self.spoken, [])
            self.assertEqual(cached["changed_shots"], [])

    def test_tuning_v4_revoices_once_then_reuses_audio(self):
        shots = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            self.build(shots, tmp, elevenlabs_model="eleven_v4")
            self.spoken.clear()
            changed = self.build(shots, tmp, elevenlabs_model="eleven_v4",
                                 elevenlabs_stability=0.3, elevenlabs_similarity=0.9)
            self.assertEqual(changed["changed_shots"], [1, 2])
            self.assertEqual(self.spoken, ["Первая реплика. Вторая реплика."])
            self.spoken.clear()
            cached = self.build(shots, tmp, elevenlabs_model="eleven_v4",
                                elevenlabs_stability=0.3, elevenlabs_similarity=0.9)
            self.assertEqual(cached["changed_shots"], [])
            self.assertEqual(self.spoken, [])

    def test_restoring_deleted_shots_only_voices_the_restored_ones(self):
        kept = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        restored = kept + [shot(3, "Третья реплика."), shot(4, "Четвёртая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            first = self.build(kept, tmp)
            untouched = {n: digest(os.path.join(tmp, f"{SLUG}_speech_{n:02d}.wav")) for n in (1, 2)}
            self.spoken.clear()
            second = self.build(restored, tmp)

            # Exactly the restored text, in one take — the kept shots are not re-read.
            self.assertEqual(self.spoken, ["Третья реплика. Четвёртая реплика."])
            self.assertEqual(second["changed_shots"], [3, 4])
            for number, before in untouched.items():
                self.assertEqual(digest(os.path.join(tmp, f"{SLUG}_speech_{number:02d}.wav")), before)
            # Their place in the master has not moved either, so the clips
            # lip-synced against those bounds stay valid.
            self.assertEqual(second["bounds"][:2], first["bounds"][:2])

    def test_a_removed_shot_is_restored_from_its_retired_voice_piece(self):
        complete = [
            shot(1, "Первая реплика."),
            shot(2, "Вторая реплика."),
            shot(3, "Третья реплика."),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            self.build(complete, tmp)
            third_before = digest(manifest_piece(tmp, 3))

            self.spoken.clear()
            self.build(complete[:2], tmp)
            self.assertEqual(self.spoken, [])
            with open(os.path.join(tmp, f"{SLUG}_voice_manifest.json"), encoding="utf-8") as f:
                stored = json.load(f)
            retired = [
                entry for entry in stored["shots"]
                if entry.get("retired") and entry.get("signature")
                == saasshorts._shot_speech_signature(complete[2], **{
                    "provider": SETTINGS["provider"],
                    "elevenlabs_voice_id": SETTINGS["voice_id"],
                    "minimax_voice_id": SETTINGS["minimax_voice_id"],
                    "language": SETTINGS["language"],
                    "actor_gender": SETTINGS["actor_gender"],
                })
            ]
            self.assertEqual(len(retired), 1)

            self.spoken.clear()
            restored = self.build(complete, tmp)

            self.assertEqual(self.spoken, [])
            self.assertEqual(restored["changed_shots"], [])
            self.assertEqual(digest(manifest_piece(tmp, 3)), third_before)

    def test_reordering_shots_reuses_voice_pieces_by_signature(self):
        original = [
            shot(1, "Первая реплика."),
            shot(2, "Вторая реплика."),
            shot(3, "Третья реплика."),
        ]
        reordered = [
            shot(1, "Третья реплика."),
            shot(2, "Первая реплика."),
            shot(3, "Вторая реплика."),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            self.build(original, tmp)
            before = {
                item["speech"]: digest(manifest_piece(tmp, item["shot_number"]))
                for item in original
            }

            self.spoken.clear()
            result = self.build(reordered, tmp)

            self.assertEqual(self.spoken, [])
            self.assertEqual(result["changed_shots"], [])
            after = {
                item["speech"]: digest(manifest_piece(tmp, item["shot_number"]))
                for item in reordered
            }
            self.assertEqual(after, before)

    def test_revoice_uses_the_manifest_piece_after_an_earlier_edit(self):
        original = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        edited = [original[0], shot(2, "Новая вторая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            self.build(original, tmp)
            self.build(edited, tmp)
            edited_piece = manifest_piece(tmp, 2)
            self.assertNotEqual(
                os.path.basename(edited_piece),
                f"{SLUG}_speech_02.wav",
            )

            self.spoken.clear()
            removed = saasshorts.forget_shot_voice(
                tmp, SLUG, [2], log=lambda *_: None
            )
            self.build(edited, tmp)

            self.assertIn(os.path.basename(edited_piece), removed)
            self.assertEqual(self.spoken, ["Новая вторая реплика."])

    def test_voice_preview_resolves_the_piece_recorded_for_the_current_shot(self):
        original = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        edited = [original[0], shot(2, "Новая вторая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            self.build(original, tmp)
            self.build(edited, tmp)
            manifest = read_voice_manifest(tmp, SLUG)

            resolved = saasshorts._voice_piece_for_shot(
                tmp, SLUG, manifest, 2
            )

            self.assertEqual(resolved, manifest_piece(tmp, 2))
            self.assertNotEqual(
                os.path.basename(resolved),
                f"{SLUG}_speech_02.wav",
            )

    def test_editing_one_shot_leaves_both_its_neighbours_alone(self):
        shots = [shot(1, "Первая реплика."), shot(2, "Вторая реплика."), shot(3, "Третья реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            self.build(shots, tmp)
            untouched = {n: digest(os.path.join(tmp, f"{SLUG}_speech_{n:02d}.wav")) for n in (1, 3)}
            self.spoken.clear()
            edited = [shots[0], shot(2, "Совсем другая вторая."), shots[2]]
            result = self.build(edited, tmp)

            self.assertEqual(self.spoken, ["Совсем другая вторая."])
            self.assertEqual(result["changed_shots"], [2])
            for number, before in untouched.items():
                self.assertEqual(digest(os.path.join(tmp, f"{SLUG}_speech_{number:02d}.wav")), before)
            # The pause on the right-hand join is charged to the newer take, so
            # shot 3 — which nobody touched — keeps the bounds of its own audio.
            self.assertAlmostEqual(
                result["bounds"][2]["end"] - result["bounds"][2]["start"],
                result["bounds"][0]["end"] - result["bounds"][0]["start"],
                delta=0.05,
            )

    def test_a_join_between_takes_gets_the_pause_the_voice_takes_anyway(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.build([shot(1, "Первая реплика.")], tmp)
            result = self.build([shot(1, "Первая реплика."), shot(2, "Вторая реплика.")], tmp)

            master = saasshorts._decode_audio_samples(result["path"])
            rate = saasshorts._VOICE_SAMPLE_RATE
            join = int(result["bounds"][1]["start"] * rate)
            window = master[max(0, join - rate): join + rate]
            frames = np.abs(window[:len(window) // 441 * 441].reshape(-1, 441)).max(axis=1)
            quiet = max(
                (len(list(group)) for silent, group in itertools.groupby(frames < 0.02) if silent),
                default=0,
            )
            # Two takes butted together came out with no breath at all (0 ms),
            # which read as gasping through a full stop.
            self.assertGreaterEqual(quiet * 10, 300)

    def test_revoicing_everything_is_still_available(self):
        shots = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            self.build(shots, tmp)
            self.spoken.clear()
            result = self.build(shots, tmp, revoice_all=True)

            self.assertEqual(self.spoken, ["Первая реплика. Вторая реплика."])
            self.assertEqual(result["changed_shots"], [1, 2])

    def test_audio_we_cannot_take_apart_still_renders(self):
        def stub_tts(text, output_path, **kwargs):
            self.spoken.append(text)
            with open(output_path, "wb") as f:
                f.write(b"not really audio")
            return {"path": output_path, "provider": "fal_minimax", "voice_id": "v", "model": "m"}

        shots = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            with patch("saasshorts.generate_voiceover_with_fallback", side_effect=stub_tts), \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]):
                result = build_incremental_voiceover(shots, tmp, SLUG, log=lambda *_: None, **SETTINGS)

            # No per-shot map, so callers fall back to the old alignment — but the
            # take we already paid for becomes the master instead of being redone.
            self.assertEqual(result["bounds"], [])
            self.assertEqual(len(self.spoken), 1)
            self.assertTrue(os.path.exists(os.path.join(tmp, f"{SLUG}_voice.mp3")))

    def test_a_job_recorded_before_pieces_existed_is_not_re_voiced(self):
        shots = [shot(1, "Первая реплика."), shot(2, "Вторая реплика.")]
        with tempfile.TemporaryDirectory() as tmp:
            master = os.path.join(tmp, f"{SLUG}_voice.mp3")
            saasshorts._encode_audio_samples(spoken_audio("legacy"), master)
            saasshorts._write_tts_metadata(master, {
                "signature": saasshorts._tts_signature(
                    "Первая реплика. Вторая реплика.", SETTINGS["provider"], SETTINGS["voice_id"],
                    SETTINGS["minimax_voice_id"], SETTINGS["language"], SETTINGS["actor_gender"],
                ),
                "provider": "elevenlabs",
                "model": "eleven_v3",
            })
            result = self.build(shots, tmp)

            self.assertEqual(self.spoken, [])
            self.assertEqual(result["changed_shots"], [])
            self.assertEqual(result["path"], master)


class SliceIdentityTests(unittest.TestCase):
    def cut(self, tmp, identity, start=0.0, end=2.0):
        slice_path = os.path.join(tmp, "slice_01.mp3")
        clip_path = os.path.join(tmp, "clip_01.mp4")

        def write_slice(audio_path, begin, finish, out):
            with open(out, "wb") as f:
                f.write(b"audio")
            return out

        with patch("saasshorts._slice_voiceover_segment", side_effect=write_slice) as cutter, \
             patch("saasshorts._get_media_duration", return_value=end - start):
            _ensure_slice_audio(os.path.join(tmp, "voice.mp3"), start, end, slice_path,
                                clip_path, log=lambda *_: None, identity=identity)
        return slice_path, clip_path, cutter

    def test_a_slice_is_recut_when_it_belongs_to_another_shot_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            slice_path, clip_path, _ = self.cut(tmp, "3|1|abc")
            with open(clip_path, "wb") as f:
                f.write(b"paid clip")

            _, _, cutter = self.cut(tmp, "4|1|def")
            self.assertTrue(cutter.called)
            # The clip was lip-synced against audio that is no longer this shot's.
            self.assertFalse(os.path.exists(clip_path))

    def test_a_slice_that_still_matches_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.cut(tmp, "3|1|abc")
            _, clip_path, cutter = self.cut(tmp, "3|1|abc")
            self.assertFalse(cutter.called)

    def test_a_legacy_slice_without_an_identity_is_not_thrown_away(self):
        with tempfile.TemporaryDirectory() as tmp:
            slice_path, _, _ = self.cut(tmp, "")
            self.assertFalse(os.path.exists(f"{slice_path}.id.txt"))

            _, _, cutter = self.cut(tmp, "3|1|abc")
            # Re-cutting on a guess would bin an avatar clip nobody asked to redo.
            self.assertFalse(cutter.called)


class StoredJumpCutTests(unittest.TestCase):
    def test_stored_cuts_are_replayed_instead_of_recomputed(self):
        slices = [{"shot": shot(1, "Длинная реплика."), "start": 0.0, "end": 9.0}]
        replayed = _split_long_slices(slices, [], cuts_by_shot={"1": [3.0, 6.0]})

        self.assertEqual([(s["start"], s["end"]) for s in replayed],
                         [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)])

    def test_cuts_that_no_longer_fit_the_audio_are_ignored(self):
        slices = [{"shot": shot(1, "Длинная реплика."), "start": 0.0, "end": 9.0}]
        # 0.5s apart: below the floor Kling needs, so these are stale.
        replayed = _split_long_slices(slices, [], cuts_by_shot={"1": [0.5, 1.0]})

        self.assertNotEqual([(s["start"], s["end"]) for s in replayed],
                            [(0.0, 0.5), (0.5, 1.0), (1.0, 9.0)])


class VoiceManifestTests(unittest.TestCase):
    def test_the_manifest_maps_every_speaking_shot(self):
        shots = [shot(1, "Раз."), shot(2, "", "broll"), shot(3, "Три.")]
        with tempfile.TemporaryDirectory() as tmp:
            def fake_tts(text, output_path, **kwargs):
                saasshorts._encode_audio_samples(spoken_audio(text), output_path)
                return {"path": output_path, "provider": "elevenlabs", "voice_id": "v", "model": "m"}

            with patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_tts), \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]):
                build_incremental_voiceover(shots, tmp, SLUG, log=lambda *_: None, **SETTINGS)

            manifest = read_voice_manifest(tmp, SLUG)
            # The silent b-roll shot carries no audio of its own; the master keeps
            # playing over it, which is the whole point of an insert.
            self.assertEqual(sorted(manifest), ["1", "3"])
            self.assertLess(manifest["1"]["end"], manifest["3"]["start"] + 0.001)


class VoiceProvenanceTests(unittest.TestCase):
    def test_actual_fallback_provider_records_its_own_voice(self):
        metadata = saasshorts._voice_provenance(
            {
                "voice_name": "Anna",
                "minimax_voice_name": "Ambitious Woman",
                "voice_selection_source": "manual",
            },
            provider_used="fal_minimax",
            model_used="minimax-speech-02-hd",
            elevenlabs_voice_id="anna-id",
            minimax_voice_id="Russian_AmbitiousWoman",
        )

        self.assertEqual(metadata, {
            "voice_id": "Russian_AmbitiousWoman",
            "voice_name": "Ambitious Woman",
            "voice_model": "minimax-speech-02-hd",
            "voice_selection_source": "manual",
        })


class VoiceOnlyPreviewTests(unittest.TestCase):
    """Listening to the voiceover before paying for the film."""

    def setUp(self):
        self.spoken = []
        self.tts_settings = []

    def fake_tts(self, text, output_path, **kwargs):
        self.spoken.append(text)
        self.tts_settings.append(kwargs)
        saasshorts._encode_audio_samples(spoken_audio(text), output_path)
        return {"path": output_path, "provider": "elevenlabs",
                "voice_id": "voice_ru", "model": "eleven_v3"}

    @staticmethod
    def decoded_duration(path):
        samples = saasshorts._decode_audio_samples(path)
        return len(samples) / saasshorts._VOICE_SAMPLE_RATE

    SCRIPT = {
        "title": "Voice first",
        "format": "storyboard_v3",
        "shots": [
            {"shot_number": 1, "speech": "Первая реплика.", "visual_type": "talking", "scene": "кухня"},
            {"shot_number": 2, "speech": "Вторая реплика.", "visual_type": "talking", "scene": "кухня"},
            {"shot_number": 3, "speech": "Третья реплика.", "visual_type": "talking", "scene": "кухня"},
        ],
    }
    CONFIG = {
        "fal_key": "fal-test",
        "elevenlabs_key": "el-test",
        "tts_provider": "elevenlabs",
        "voice_id": "voice_ru",
        "language": "ru",
        "actor_gender": "female",
        "video_mode": "storyboard_v3_standard",
        "storyboard_generation_mode": "sliced_avatar",
        "voice_only": True,
    }

    def preview(self, tmp, script=None, config=None):
        # Every paid step of the render is armed to fail: the whole promise of
        # this mode is that listening to the voiceover costs nothing but the read.
        with patch("saasshorts.generate_voiceover_with_fallback", side_effect=self.fake_tts), \
             patch("saasshorts._decodable_audio_duration", side_effect=self.decoded_duration), \
             patch("saasshorts._get_media_duration", side_effect=self.decoded_duration), \
             patch("saasshorts.transcribe_audio_for_subs", return_value=[]), \
             patch("saasshorts.generate_sliced_avatar_clips",
                   side_effect=AssertionError("платная съёмка не должна запускаться")), \
             patch("saasshorts.generate_storyboard_shot_clip",
                   side_effect=AssertionError("платная съёмка не должна запускаться")), \
             patch("saasshorts.composite_storyboard_video",
                   side_effect=AssertionError("сборка ролика не должна запускаться")):
            return saasshorts.generate_storyboard_video(
                script or dict(self.SCRIPT), {**self.CONFIG, **(config or {})}, tmp, log=lambda *_: None
            )

    def test_the_voiceover_comes_back_with_a_piece_per_shot_and_no_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.preview(tmp)

            self.assertTrue(result["voice_only"])
            self.assertEqual(result["video_filename"], "")
            self.assertTrue(result["audio_url"].endswith("_voice.mp3"))
            self.assertGreater(result["duration"], 0)

            heard = result["voice_shots"]
            self.assertEqual([s["shot_number"] for s in heard], [1, 2, 3])
            for entry in heard:
                self.assertGreater(entry["seconds"], 0)
                self.assertTrue(entry["voice_url"].endswith(f"_speech_{entry['shot_number']:02d}.wav"))
            # Каждая реплика лежит в дорожке ровно там, где её будет играть ролик.
            for left, right in zip(heard, heard[1:]):
                self.assertLessEqual(left["end"], right["start"] + 0.001)

    def test_the_preview_says_how_many_paid_clips_this_track_buys(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.preview(tmp)

            # Смысл предпрослушивания — узнать цену съёмки до съёмки: длинная
            # реплика распадается на несколько клипов, и платят за каждый.
            self.assertGreaterEqual(result["voice_clips_planned"], 3)
            self.assertGreater(result["video_cost_estimate"]["total"], 0)
            # Потрачено — только на дубли; съёмка ещё не оплачена.
            self.assertLess(result["cost_estimate"]["total"], 0.1)

    def test_re_reading_one_line_leaves_the_other_takes_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.preview(tmp)
            untouched = {n: digest(os.path.join(tmp, f"voice_first_speech_{n:02d}.wav")) for n in (1, 3)}
            self.spoken.clear()

            removed = saasshorts.forget_shot_voice(tmp, "voice_first", [2], log=lambda *_: None)
            result = self.preview(tmp)

            self.assertEqual(removed, ["voice_first_speech_02.wav"])
            self.assertEqual(self.spoken, ["Вторая реплика."])
            for number, before in untouched.items():
                self.assertEqual(digest(os.path.join(tmp, f"voice_first_speech_{number:02d}.wav")), before)
            self.assertEqual([s["shot_number"] for s in result["voice_shots"]], [1, 2, 3])

    def test_listening_again_without_edits_costs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.preview(tmp)
            self.spoken.clear()
            self.preview(tmp)

            self.assertEqual(self.spoken, [])

    def test_anna_v4_settings_reach_voice_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.preview(tmp, config={
                "voice_id": "anna-id", "voice_name": "Anna",
                "elevenlabs_model": "eleven_v4",
                "elevenlabs_stability": 0.3,
                "elevenlabs_similarity": 0.9,
            })
        self.assertEqual(len(self.tts_settings), 1)
        self.assertEqual(self.tts_settings[0]["elevenlabs_voice_id"], "anna-id")
        self.assertEqual(self.tts_settings[0]["elevenlabs_model"], "eleven_v4")
        self.assertEqual(self.tts_settings[0]["elevenlabs_stability"], 0.3)
        self.assertEqual(self.tts_settings[0]["elevenlabs_similarity"], 0.9)

    def test_the_take_moves_into_the_render_instead_of_being_read_again(self):
        # Ради этого всё и делается: снимать надо под тот дубль, который человек
        # послушал. Дубль каждый раз другой, поэтому «записать заново» — это уже
        # не та озвучка, под которую он утверждал кадры.
        with tempfile.TemporaryDirectory() as preview, tempfile.TemporaryDirectory() as render:
            heard = self.preview(preview)

            saasshorts.adopt_job_artifacts(
                preview, render,
                source_slug="voice_first", target_slug="voice_first",
                source_label="прослушанной озвучки", log=lambda *_: None,
            )
            self.spoken.clear()
            with patch("saasshorts.generate_voiceover_with_fallback",
                       side_effect=AssertionError("утверждённый дубль перезаписывать нельзя")), \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]):
                built = build_incremental_voiceover(
                    [dict(s) for s in self.SCRIPT["shots"]], render, "voice_first",
                    log=lambda *_: None, **SETTINGS
                )

            self.assertEqual(self.spoken, [])
            self.assertEqual(
                [(b["shot_number"], b["start"], b["end"]) for b in built["bounds"]],
                [(s["shot_number"], s["start"], s["end"]) for s in heard["voice_shots"]],
            )

    def test_a_non_storyboard_script_refuses_instead_of_filming(self):
        # Здесь останавливаться негде: дальше по коду сразу платная генерация,
        # и «озвучка» молча превратилась бы в счёт за целый ролик.
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                saasshorts.generate_full_video(
                    {"title": "UGC", "format": "ugc", "full_narration": "Привет.", "segments": []},
                    {**self.CONFIG, "video_mode": "standard"},
                    tmp,
                    log=lambda *_: None,
                )


if __name__ == "__main__":
    unittest.main()

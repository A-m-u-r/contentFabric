import json
import os
import tempfile
import unittest
from unittest.mock import patch

import saasshorts
from saasshorts import (
    apply_lipsync_to_saas_job,
    build_kling_avatar_request,
    build_sync_lipsync_request,
    estimate_sync_lipsync_cost,
    generate_full_video,
    generate_talking_head,
    inspect_talking_head_quality,
    kling_avatar_cost_per_second,
    resolve_saas_lipsync_assets,
    select_best_talking_head_attempt,
)


class SaaSLipSyncTests(unittest.TestCase):
    def test_builds_kling_avatar_standard_and_pro_payloads(self):
        prompt = "Natural UGC creator talking to camera."

        standard_model, standard_payload = build_kling_avatar_request(
            "https://cdn.example/avatar.png",
            "https://cdn.example/voice.mp3",
            prompt,
            tier="standard",
        )
        pro_model, pro_payload = build_kling_avatar_request(
            "https://cdn.example/avatar.png",
            "https://cdn.example/voice.mp3",
            prompt,
            tier="pro",
        )

        self.assertEqual(standard_model, "fal-ai/kling-video/ai-avatar/v2/standard")
        self.assertEqual(pro_model, "fal-ai/kling-video/ai-avatar/v2/pro")
        self.assertEqual(standard_payload, pro_payload)
        self.assertEqual(kling_avatar_cost_per_second("standard"), 0.0562)
        self.assertEqual(kling_avatar_cost_per_second("pro"), 0.115)

    def test_builds_sync3_payload(self):
        model_id, payload = build_sync_lipsync_request(
            "https://cdn.example/head.mp4",
            "https://cdn.example/voice.mp3",
            model="sync-3",
            sync_mode="cut_off",
        )

        self.assertEqual(model_id, "fal-ai/sync-lipsync/v3")
        self.assertEqual(payload["video_url"], "https://cdn.example/head.mp4")
        self.assertEqual(payload["audio_url"], "https://cdn.example/voice.mp3")
        self.assertEqual(payload["sync_mode"], "cut_off")
        self.assertNotIn("model", payload)

    def test_builds_v2_pro_payload(self):
        model_id, payload = build_sync_lipsync_request(
            "https://cdn.example/head.mp4",
            "https://cdn.example/voice.mp3",
            model="lipsync-2-pro",
            sync_mode="remap",
        )

        self.assertEqual(model_id, "fal-ai/sync-lipsync/v2")
        self.assertEqual(payload["model"], "lipsync-2-pro")
        self.assertEqual(payload["sync_mode"], "remap")

    def test_estimates_lipsync_costs_by_duration(self):
        self.assertEqual(estimate_sync_lipsync_cost("lipsync-2", 30), 1.5)
        self.assertEqual(estimate_sync_lipsync_cost("lipsync-2-pro", 30), 2.5)
        self.assertEqual(estimate_sync_lipsync_cost("sync-3", 30), 4.0)

    def test_talking_head_quality_flags_extra_video_tail(self):
        with patch("saasshorts._get_media_duration", return_value=10.21), \
             patch("saasshorts._get_media_stream_duration", side_effect=[12.27, 10.21]):
            report = inspect_talking_head_quality("head.mp4", "voice.mp3", threshold=0.3)

        self.assertEqual(report["status"], "needs_review")
        self.assertAlmostEqual(report["reference_audio_duration"], 10.21, places=2)
        self.assertAlmostEqual(report["video_stream_duration"], 12.27, places=2)
        self.assertAlmostEqual(report["video_reference_delta"], 2.06, places=2)
        self.assertGreater(report["abs_video_reference_delta"], 0.3)
        self.assertTrue(report["warnings"])

    def test_selects_best_talking_head_attempt_without_trimming(self):
        attempts = [
            {
                "name": "base",
                "output_path": "base.mp4",
                "quality": {
                    "status": "needs_review",
                    "abs_video_reference_delta": 2.06,
                },
            },
            {
                "name": "tail_silence",
                "output_path": "tail.mp4",
                "quality": {
                    "status": "needs_review",
                    "abs_video_reference_delta": 0.42,
                },
            },
        ]

        selected = select_best_talking_head_attempt(attempts)

        self.assertEqual(selected["name"], "tail_silence")
        self.assertEqual(selected["output_path"], "tail.mp4")

    def test_prepare_voiceover_trims_tail_silence_and_writes_audit(self):
        class FakeRunResult:
            def __init__(self, stdout="", stderr=""):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = 0

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "voice.mp3")
            with open(audio_path, "wb") as f:
                f.write(b"raw-audio")

            def fake_run(cmd, *args, **kwargs):
                command = " ".join(str(part) for part in cmd)
                if "silencedetect" in command:
                    return FakeRunResult(stderr="silence_start: 3.12\nsilence_end: 4.21 | silence_duration: 1.09\n")
                if "silenceremove" in command:
                    with open(cmd[-1], "wb") as f:
                        f.write(b"clean-audio")
                    return FakeRunResult()
                raise AssertionError(f"Unexpected command: {command}")

            with patch("saasshorts._get_media_duration", side_effect=[4.21, 3.12]), \
                 patch("saasshorts.subprocess.run", side_effect=fake_run):
                report = saasshorts.prepare_voiceover_for_video_generation(audio_path, log=lambda message: None)

            self.assertNotEqual(report["path"], audio_path)
            self.assertTrue(report["trimmed"])
            self.assertAlmostEqual(report["original_duration"], 4.21)
            self.assertAlmostEqual(report["duration"], 3.12)
            self.assertAlmostEqual(report["trailing_silence"], 1.09)
            self.assertTrue(os.path.exists(report["path"]))
            self.assertTrue(os.path.exists(f"{report['path']}.meta.json"))

    def test_prepare_voiceover_falls_back_when_trim_truncates_speech(self):
        # Regression: a conversational voiceover has internal pauses; the trim
        # must never collapse 28.84s of speech to 0.89s (cut at first pause).
        class FakeRunResult:
            def __init__(self, stdout="", stderr=""):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = 0

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "voice.mp3")
            with open(audio_path, "wb") as f:
                f.write(b"raw-audio")

            seen_commands = []

            def fake_run(cmd, *args, **kwargs):
                command = " ".join(str(part) for part in cmd)
                seen_commands.append(command)
                if "silencedetect" in command:
                    return FakeRunResult(stderr="silence_start: 0.89\nsilence_end: 1.40 | silence_duration: 0.51\n")
                if "silenceremove" in command:
                    with open(cmd[-1], "wb") as f:
                        f.write(b"truncated-audio")
                    return FakeRunResult()
                raise AssertionError(f"Unexpected command: {command}")

            with patch("saasshorts._get_media_duration", side_effect=[28.84, 0.89]), \
                 patch("saasshorts.subprocess.run", side_effect=fake_run):
                report = saasshorts.prepare_voiceover_for_video_generation(audio_path, log=lambda message: None)

            self.assertEqual(report["status"], "fallback_raw_audio")
            self.assertEqual(report["path"], audio_path)
            self.assertAlmostEqual(report["duration"], 28.84)
            self.assertFalse(os.path.exists(saasshorts.prepared_voiceover_path(audio_path)))
            trim_command = next(cmd for cmd in seen_commands if "silenceremove" in cmd)
            self.assertIn("areverse", trim_command)
            self.assertNotIn("stop_periods", trim_command)

    def test_full_video_uses_prepared_voiceover_for_kling_subtitles_and_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared_audio_holder = {}

            def fake_actor_image(description, fal_key, output_path):
                with open(output_path, "wb") as f:
                    f.write(b"actor")
                return output_path

            def fake_voiceover(text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"raw-voice-with-tail")
                return {"path": output_path, "provider": "elevenlabs", "voice_id": "voice_ru"}

            def fake_prepare(audio_path, log=print):
                clean_path = audio_path.replace(".mp3", "_clean.mp3")
                with open(clean_path, "wb") as f:
                    f.write(b"clean-voice")
                prepared_audio_holder["path"] = clean_path
                return {
                    "path": clean_path,
                    "original_path": audio_path,
                    "original_duration": 10.2,
                    "duration": 9.1,
                    "trailing_silence": 1.1,
                    "leading_silence": 0.0,
                    "trimmed": True,
                    "status": "trimmed",
                }

            def fake_talking_head(image_path, audio_path, fal_key, output_path, tier="standard", **kwargs):
                self.assertEqual(audio_path, prepared_audio_holder["path"])
                with open(output_path, "wb") as f:
                    f.write(b"head")
                return output_path

            def fake_subs(audio_path, output_path, max_words=2, **kwargs):
                self.assertEqual(audio_path, prepared_audio_holder["path"])
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            def fake_composite(talking_head_path, broll_clips, subtitles_path, hook_text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"final")
                return output_path

            script = {
                "title": "Clean audio",
                "full_narration": "Вся система в гайде. Ссылка в профиле.",
                "hook_text": "Система",
                "segments": [],
            }
            config = {
                "fal_key": "fal-test",
                "elevenlabs_key": "eleven-test",
                "voice_id": "voice_ru",
                "tts_provider": "elevenlabs",
                "language": "ru",
                "actor_gender": "female",
                "video_mode": "standard",
                "broll_mode": "off",
            }

            with patch("saasshorts.generate_actor_image", side_effect=fake_actor_image), \
                 patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_voiceover), \
                 patch("saasshorts.prepare_voiceover_for_video_generation", side_effect=fake_prepare), \
                 patch("saasshorts.generate_talking_head", side_effect=fake_talking_head), \
                 patch("saasshorts.generate_talking_head_lowcost", side_effect=AssertionError("should use Kling")), \
                 patch("saasshorts.inspect_talking_head_quality", return_value={"status": "ok", "warnings": [], "paid_attempts": 1}), \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]), \
                 patch("saasshorts.generate_tiktok_subs", side_effect=fake_subs), \
                 patch("saasshorts.composite_video", side_effect=fake_composite), \
                 patch("saasshorts._get_media_duration", return_value=9.1):
                result = generate_full_video(script, config, tmp)

            self.assertEqual(result["duration"], 9.1)
            self.assertEqual(result["voiceover_preparation"]["path"], prepared_audio_holder["path"])
            self.assertTrue(result["voiceover_preparation"]["trimmed"])
            self.assertGreater(result["voiceover_preparation"]["trailing_silence"], 1.0)

    def test_talking_head_does_not_retry_by_adding_tail_silence_by_default(self):
        class FakeResponse:
            content = b"video-bytes"

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def get(self, url):
                return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            image_path = os.path.join(tmp, "actor.png")
            audio_path = os.path.join(tmp, "voice.mp3")
            output_path = os.path.join(tmp, "head.mp4")
            for path in (image_path, audio_path):
                with open(path, "wb") as f:
                    f.write(b"x")

            def fake_upload(path, fal_key):
                return f"https://cdn.example/{os.path.basename(path)}"

            def fake_tail_audio(source, output, tail_silence=0.45):
                with open(output, "wb") as f:
                    f.write(b"tail")
                return output

            run_results = [
                {
                    "video": {"url": "https://cdn.example/base.mp4"},
                    "_fal_request": {"request_id": "req-base", "model_id": "model"},
                }
            ]
            quality_results = [
                {
                    "status": "needs_review",
                    "warnings": ["Kling returned video 2.00s longer than the reference voiceover."],
                    "abs_video_reference_delta": 2.0,
                }
            ]

            with patch("saasshorts.prepare_kling_actor_image", return_value=image_path), \
                 patch("saasshorts._fal_upload_file", side_effect=fake_upload), \
                 patch("saasshorts._fal_run", side_effect=run_results) as fal_run_mock, \
                 patch("saasshorts.httpx.Client", FakeClient), \
                 patch("saasshorts.create_kling_tail_padded_audio", side_effect=fake_tail_audio) as tail_audio_mock, \
                 patch("saasshorts.inspect_talking_head_quality", side_effect=quality_results):
                result_path = generate_talking_head(image_path, audio_path, "fal-test", output_path, tier="pro")

            self.assertEqual(result_path, output_path)
            self.assertEqual(fal_run_mock.call_count, 1)
            self.assertEqual(tail_audio_mock.call_count, 0)
            with open(output_path, "rb") as f:
                self.assertEqual(f.read(), b"video-bytes")

            quality_path = output_path.replace(".mp4", "_quality.json")
            with open(quality_path, "r", encoding="utf-8") as f:
                quality = json.load(f)

            self.assertEqual(quality["status"], "needs_review")
            self.assertEqual(quality["selected_attempt"], "base")
            self.assertEqual(quality["paid_attempts"], 1)
            self.assertTrue(quality["warnings"])

            base_meta_path = output_path.replace(".mp4", "_base_fal.json")
            with open(base_meta_path, "r", encoding="utf-8") as f:
                base_meta = json.load(f)
            self.assertEqual(base_meta["fal_request"]["request_id"], "req-base")

    def test_resolves_russian_empty_slug_job_assets_and_broll(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in (
                "__head.mp4",
                "__voice.mp3",
                "__subs.ass",
                "__final.mp4",
                "__broll_mockup_0.mp4",
            ):
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(b"x")

            metadata = {
                "hook_text": "hook",
                "segments": [
                    {"visual": "actor_talking", "start": 0, "end": 3},
                    {"visual": "broll", "broll_prompt": "tracker", "start": 3, "end": 6},
                ],
            }
            with open(os.path.join(tmp, "gallery_metadata.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f)

            assets = resolve_saas_lipsync_assets(tmp)

            self.assertEqual(os.path.basename(assets["talking_head"]), "__head.mp4")
            self.assertEqual(os.path.basename(assets["audio"]), "__voice.mp3")
            self.assertEqual(os.path.basename(assets["subtitles"]), "__subs.ass")
            self.assertEqual(os.path.basename(assets["final"]), "__final.mp4")
            self.assertEqual(assets["hook_text"], "hook")
            self.assertEqual(len(assets["broll_clips"]), 1)
            self.assertEqual(os.path.basename(assets["broll_clips"][0]["path"]), "__broll_mockup_0.mp4")
            self.assertEqual(assets["broll_clips"][0]["start"], 3)
            self.assertEqual(assets["broll_clips"][0]["end"], 6)

    def test_lipsync_postprocess_creates_versioned_final_without_overwriting_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("__head.mp4", "__voice.mp3", "__subs.ass"):
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(b"x")
            final_path = os.path.join(tmp, "__final.mp4")
            with open(final_path, "wb") as f:
                f.write(b"original-final")

            with open(os.path.join(tmp, "gallery_metadata.json"), "w", encoding="utf-8") as f:
                json.dump({"hook_text": "hook", "segments": []}, f)

            def fake_lipsync(video_path, audio_path, fal_key, output_path, model="sync-3", sync_mode="cut_off"):
                with open(output_path, "wb") as f:
                    f.write(b"head")
                return output_path

            def fake_composite(talking_head_path, broll_clips, subtitles_path, hook_text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"versioned-final")
                return output_path

            with patch("saasshorts.generate_sync_lipsync_video", side_effect=fake_lipsync), \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]), \
                 patch("saasshorts.composite_video", side_effect=fake_composite), \
                 patch("saasshorts._get_media_duration", return_value=12):
                result = apply_lipsync_to_saas_job(tmp, "fal-test", model="lipsync-2")

            self.assertEqual(os.path.basename(result["video_path"]), "__final_v002_lipsync_2.mp4")
            self.assertEqual(result["video_filename"], "__final_v002_lipsync_2.mp4")
            with open(final_path, "rb") as f:
                self.assertEqual(f.read(), b"original-final")
            with open(result["video_path"], "rb") as f:
                self.assertEqual(f.read(), b"versioned-final")

    def test_reuses_saved_talking_head_template_via_lipsync(self):
        with tempfile.TemporaryDirectory() as tmp:
            reusable_head = os.path.join(tmp, "template_head.mp4")
            reusable_poster = os.path.join(tmp, "template_actor.png")
            with open(reusable_head, "wb") as f:
                f.write(b"old-head")
            with open(reusable_poster, "wb") as f:
                f.write(b"poster")

            def fake_voiceover(text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"voice")
                return {"path": output_path, "provider": "fal_minimax", "voice_id": "Russian_AmbitiousWoman"}

            def fake_lipsync(video_path, audio_path, fal_key, output_path, model="sync-3", sync_mode="cut_off"):
                self.assertEqual(video_path, reusable_head)
                self.assertEqual(model, "lipsync-2-pro")
                with open(output_path, "wb") as f:
                    f.write(b"new-lipsynced-head")
                return output_path

            def fake_subs(audio_path, output_path, max_words=2, **kwargs):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            def fake_composite(talking_head_path, broll_clips, subtitles_path, hook_text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"final")
                return output_path

            script = {
                "title": "Reuse head",
                "full_narration": "Новый текст для той же говорящей головы.",
                "hook_text": "Новый хук",
                "segments": [],
            }
            config = {
                "fal_key": "fal-test",
                "tts_provider": "fal_minimax",
                "language": "ru",
                "actor_gender": "female",
                "reusable_head_path": reusable_head,
                "reusable_head_poster_path": reusable_poster,
                "reusable_head_template_id": "tpl_123",
                "reusable_lipsync_model": "lipsync-2-pro",
                "broll_mode": "off",
            }

            with patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_voiceover), \
                 patch("saasshorts.generate_sync_lipsync_video", side_effect=fake_lipsync) as lipsync_mock, \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]), \
                 patch("saasshorts.generate_tiktok_subs", side_effect=fake_subs), \
                 patch("saasshorts.composite_video", side_effect=fake_composite), \
                 patch("saasshorts._get_media_duration", return_value=18), \
                 patch("saasshorts.generate_talking_head", side_effect=AssertionError("should not generate Kling head")), \
                 patch("saasshorts.generate_talking_head_lowcost", side_effect=AssertionError("should not generate Hailuo head")), \
                 patch("saasshorts.generate_actor_image", side_effect=AssertionError("should not generate actor image")):
                result = generate_full_video(script, config, tmp)

            self.assertEqual(lipsync_mock.call_count, 1)
            self.assertEqual(result["head_source"], "template")
            self.assertEqual(result["head_template_id"], "tpl_123")
            self.assertEqual(result["lipsync_model"], "lipsync-2-pro")
            self.assertEqual(result["cost_estimate"]["talking_head_reuse_lipsync"], 1.5)
            self.assertEqual(result["cost_estimate"]["actor_image_reused"], 0)

    def test_generation_keeps_final_video_when_talking_head_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fake_actor_image(description, fal_key, output_path):
                with open(output_path, "wb") as f:
                    f.write(b"actor")
                return output_path

            def fake_voiceover(text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"voice")
                return {"path": output_path, "provider": "fal_minimax", "voice_id": "Russian_AmbitiousWoman"}

            def fake_talking_head(image_path, audio_path, fal_key, output_path, tier="standard", **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"head")
                quality_path = output_path.replace(".mp4", "_quality.json")
                with open(quality_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "status": "needs_review",
                            "warnings": ["Kling returned video 1.20s longer than voiceover."],
                            "selected_attempt": "base",
                            "attempts": [
                                {
                                    "name": "base",
                                    "quality": {
                                        "status": "needs_review",
                                        "abs_video_reference_delta": 1.2,
                                    },
                                }
                            ],
                        },
                        f,
                    )
                return output_path

            def fake_subs(audio_path, output_path, max_words=2, **kwargs):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            def fake_composite(talking_head_path, broll_clips, subtitles_path, hook_text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"final")
                return output_path

            script = {
                "title": "Needs review",
                "full_narration": "Short voiceover for mismatch review.",
                "hook_text": "Hook",
                "segments": [],
            }
            config = {
                "fal_key": "fal-test",
                "tts_provider": "fal_minimax",
                "language": "ru",
                "actor_gender": "female",
                "video_mode": "premium",
                "broll_mode": "off",
            }

            with patch("saasshorts.generate_actor_image", side_effect=fake_actor_image), \
                 patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_voiceover), \
                 patch("saasshorts.generate_talking_head", side_effect=fake_talking_head), \
                 patch("saasshorts.generate_talking_head_lowcost", side_effect=AssertionError("should use Kling")), \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]), \
                 patch("saasshorts.generate_tiktok_subs", side_effect=fake_subs), \
                 patch("saasshorts.composite_video", side_effect=fake_composite) as composite_mock, \
                 patch("saasshorts._get_media_duration", return_value=10):
                result = generate_full_video(script, config, tmp)

            self.assertEqual(composite_mock.call_count, 1)
            self.assertEqual(result["quality_status"], "needs_review")
            self.assertEqual(result["quality_warnings"], ["Kling returned video 1.20s longer than voiceover."])
            self.assertTrue(os.path.exists(result["video_path"]))


class JumpCutTests(unittest.TestCase):
    def test_selects_cut_points_at_longest_pause_in_window(self):
        # Words 0-3s continuous, big pause at 2.9-3.4s, then 3.4-6s continuous
        words = []
        t = 0.0
        while t < 2.9:
            words.append({"word": "a", "start": t, "end": t + 0.28})
            t += 0.3
        t = 3.4
        while t < 6.0:
            words.append({"word": "b", "start": t, "end": t + 0.28})
            t += 0.3

        cuts = saasshorts._select_jump_cut_points(words, duration=6.0, min_gap=2.2, max_gap=3.8)

        self.assertTrue(cuts, "expected at least one cut")
        # The first cut should land on the phrase boundary (word ending at ~2.98)
        self.assertAlmostEqual(cuts[0], 2.98, delta=0.05)

    def test_falls_back_to_fixed_grid_without_words(self):
        cuts = saasshorts._select_jump_cut_points([], duration=12.0)
        self.assertTrue(cuts)
        for a, b in zip(cuts, cuts[1:]):
            self.assertGreater(b - a, 1.5)
        self.assertLess(cuts[-1], 12.0 - 1.0)

    def test_no_cuts_for_very_short_video(self):
        self.assertEqual(saasshorts._select_jump_cut_points([], duration=3.0), [])

    def test_subsegments_ignore_cuts_near_edges(self):
        subs = saasshorts._punch_in_subsegments(0.0, 10.0, [0.3, 3.0, 6.0, 9.8])
        self.assertEqual(subs, [(0.0, 3.0), (3.0, 6.0), (6.0, 10.0)])

    def test_composite_builds_alternating_punch_in_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            head = os.path.join(tmp, "head.mp4")
            with open(head, "wb") as f:
                f.write(b"head")
            subs_path = os.path.join(tmp, "subs.ass")
            final = os.path.join(tmp, "final.mp4")
            captured = {}

            def fake_run(cmd, check=True, **kwargs):
                captured["cmd"] = cmd

            words = [
                {"word": "w", "start": s / 10, "end": s / 10 + 0.08}
                for s in range(0, 100, 3)
            ]

            with patch("saasshorts._get_media_duration", return_value=10.0), \
                 patch("saasshorts.subprocess.run", side_effect=fake_run):
                saasshorts.composite_video(head, [], subs_path, "hook", final, jump_cut_words=words)

            cmd = captured["cmd"]
            filter_idx = cmd.index("-filter_complex") + 1
            filter_str = cmd[filter_idx]

            # Even shots are full frame, odd shots are punched in
            self.assertIn("crop=938:1668", filter_str)
            self.assertIn("[v0]", filter_str)
            self.assertIn("[v1]", filter_str)
            v0 = [p for p in filter_str.split(";") if p.endswith("[v0]")][0]
            v1 = [p for p in filter_str.split(";") if p.endswith("[v1]")][0]
            self.assertNotIn("crop=938:1668", v0)
            self.assertIn("crop=938:1668", v1)

            # Audio must come from the talking head, uncut — one continuous
            # normalized track, not per-shot slices.
            audio_map = cmd[cmd.index("-map", cmd.index("-map") + 1) + 1]
            self.assertEqual(audio_map, "[aout]")
            self.assertIn("[0:a]loudnorm", filter_str)

    def test_composite_without_punch_in_keeps_single_take(self):
        with tempfile.TemporaryDirectory() as tmp:
            head = os.path.join(tmp, "head.mp4")
            with open(head, "wb") as f:
                f.write(b"head")
            final = os.path.join(tmp, "final.mp4")
            captured = {}

            def fake_run(cmd, check=True, **kwargs):
                captured["cmd"] = cmd

            with patch("saasshorts._get_media_duration", return_value=10.0), \
                 patch("saasshorts.subprocess.run", side_effect=fake_run):
                saasshorts.composite_video(
                    head, [], os.path.join(tmp, "subs.ass"), "hook", final, punch_in=False
                )

            # Video stays one uncut take: no concat chain, no punch-in crop.
            cmd = captured["cmd"]
            filter_str = cmd[cmd.index("-filter_complex") + 1]
            self.assertNotIn("concat=", filter_str)
            self.assertNotIn("crop=938:1668", filter_str)
            self.assertIn("loudnorm", filter_str)


class SlicedAvatarTests(unittest.TestCase):
    def _words(self, phrases):
        """Build word timestamps: phrases = [(word_count, start, end), ...] evenly spaced."""
        words = []
        for count, start, end in phrases:
            step = (end - start) / count
            for k in range(count):
                words.append({
                    "word": "w",
                    "start": start + k * step,
                    "end": start + k * step + step * 0.8,
                })
        return words

    def test_align_snaps_boundary_to_pause(self):
        # Two phrases: 10 words 0-3s, big pause, 10 words 3.6-6.6s
        words = self._words([(10, 0.0, 3.0), (10, 3.6, 6.6)])
        shots = [
            {"shot_number": 1, "speech": "один два три четыре пять шесть семь восемь девять десять"},
            {"shot_number": 2, "speech": "раз два три четыре пять шесть семь восемь девять десять"},
        ]

        slices, skipped = saasshorts._align_shots_to_voiceover(shots, words, 6.6)

        self.assertEqual(len(slices), 2)
        self.assertEqual(skipped, [])
        # Boundary should land inside the 3.0-3.6s pause
        boundary = slices[0]["end"]
        self.assertEqual(boundary, slices[1]["start"])
        self.assertGreater(boundary, 2.9)
        self.assertLess(boundary, 3.7)
        self.assertEqual(slices[0]["start"], 0.0)
        self.assertEqual(slices[1]["end"], 6.6)

    def test_align_prefers_scripted_last_word_over_longer_earlier_pause(self):
        # Real-world case: the pause after "сахара" (decoy) is longer than the
        # pause after the shot's true last word "срываешься" — the boundary
        # must still follow the scripted phrase end.
        words = []
        t = 0.0
        tokens = ["w"] * 8 + ["сахара."] + ["w"] * 3 + ["срываешься."] + ["w"] * 7
        for tok in tokens:
            words.append({"word": tok, "start": t, "end": t + 0.3})
            t += 0.35
            if tok == "сахара.":
                t += 0.5
            elif tok == "срываешься.":
                t += 0.4
        shots = [
            {"shot_number": 1, "speech": "a b c d e f g h сахара а к вечеру срываешься"},
            {"shot_number": 2, "speech": "j k l m n o p"},
        ]

        slices, _ = saasshorts._align_shots_to_voiceover(shots, words, t)

        self.assertGreater(slices[0]["end"], words[12]["end"])
        self.assertLess(slices[0]["end"], words[13]["start"])

    def test_split_long_slices_breaks_into_jumpcuts(self):
        # A single 8.5s talking slice must split into <=5s sub-clips at pauses.
        words = [{"word": "w", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(18)]
        shot = {"visual_type": "talking", "speech": "long monologue"}
        slices = [{"shot": shot, "start": 0.0, "end": 8.5}]

        out = saasshorts._split_long_slices(slices, words)

        self.assertGreater(len(out), 1)
        for sub in out:
            self.assertLessEqual(sub["end"] - sub["start"], saasshorts._MAX_TALKING_SLICE_SECONDS + 0.01)
        # Sub-slices tile the original range with no gaps or overlaps
        self.assertEqual(out[0]["start"], 0.0)
        self.assertEqual(out[-1]["end"], 8.5)
        for a, b in zip(out, out[1:]):
            self.assertEqual(a["end"], b["start"])
        # Each split carries its own shot dict so per-clip punch-ins differ
        self.assertIsNot(out[0]["shot"], out[1]["shot"])

    def test_split_long_slices_leaves_short_and_broll_untouched(self):
        words = [{"word": "w", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(18)]
        short = [{"shot": {"visual_type": "talking"}, "start": 0.0, "end": 4.0}]
        self.assertEqual(len(saasshorts._split_long_slices(short, words)), 1)
        # b-roll plays under the master voiceover: no lip-sync, never split
        broll = [{"shot": {"visual_type": "broll"}, "start": 0.0, "end": 9.0}]
        self.assertEqual(len(saasshorts._split_long_slices(broll, words)), 1)

    def test_align_proportional_without_words(self):
        shots = [
            {"shot_number": 1, "speech": "a b c d e"},
            {"shot_number": 2, "speech": "f g h i j k l m n o"},
        ]
        slices, _ = saasshorts._align_shots_to_voiceover(shots, [], 15.0)
        self.assertEqual(len(slices), 2)
        self.assertAlmostEqual(slices[0]["end"], 5.0, delta=0.01)

    def test_align_skips_shots_without_speech(self):
        shots = [
            {"shot_number": 1, "speech": "hello there my friend"},
            {"shot_number": 2, "speech": ""},
        ]
        slices, skipped = saasshorts._align_shots_to_voiceover(shots, [], 8.0)
        self.assertEqual(len(slices), 1)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["shot_number"], 2)

    def test_storyboard_sliced_avatar_mode_generates_lipsynced_shots(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref1 = os.path.join(tmp, "ref1.png")
            ref2 = os.path.join(tmp, "ref2.png")
            for p in (ref1, ref2):
                with open(p, "wb") as f:
                    f.write(b"img")

            head_calls = []

            def fake_voiceover(text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"voice")
                return {"path": output_path, "provider": "fal_minimax", "voice_id": "v"}

            def fake_prepare(audio_path, log=print):
                return {"path": audio_path, "status": "ok", "trimmed": False}

            def fake_slice(audio_path, start, end, output_path):
                with open(output_path, "wb") as f:
                    f.write(b"slice")
                return output_path

            def fake_talking_head(image_path, audio_path, fal_key, output_path, tier="standard", **kwargs):
                head_calls.append({"image": image_path, "audio": audio_path, "tier": tier, "scene_prompt": kwargs.get("scene_prompt", "")})
                with open(output_path, "wb") as f:
                    f.write(b"clip")
                return output_path

            def fake_composite(clips, audio_path, srt_path, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"final")
                return output_path

            def fake_subs(audio_path, shots, output_path, max_words=2, words=None, **kwargs):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            script = {
                "title": "Sliced avatar",
                "format": "storyboard_v3",
                "language": "ru",
                "full_narration": "Первая фраза кадра. Вторая фраза кадра.",
                "shots": [
                    {"shot_number": 1, "role": "hook", "start": 0, "end": 4,
                     "speech": "Первая фраза кадра.", "image_path": ref1,
                     "scene": "close-up", "overlay_text": "", "transition": "cut"},
                    {"shot_number": 2, "role": "cta", "start": 4, "end": 8,
                     "speech": "Вторая фраза кадра.", "image_path": ref2,
                     "scene": "medium", "overlay_text": "", "transition": "cut"},
                ],
            }
            config = {
                "fal_key": "fal-test",
                "tts_provider": "fal_minimax",
                "language": "ru",
                "video_mode": "storyboard_v3_standard",
                "storyboard_generation_mode": "sliced_avatar",
            }

            with patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_voiceover), \
                 patch("saasshorts.prepare_voiceover_for_video_generation", side_effect=fake_prepare), \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]), \
                 patch("saasshorts._slice_voiceover_segment", side_effect=fake_slice), \
                 patch("saasshorts.generate_talking_head", side_effect=fake_talking_head), \
                 patch("saasshorts.generate_storyboard_shot_clip", side_effect=AssertionError("should not use Kling V3")), \
                 patch("saasshorts.generate_storyboard_ass_subtitles", side_effect=fake_subs), \
                 patch("saasshorts.composite_storyboard_video", side_effect=fake_composite) as composite_mock, \
                 patch("saasshorts.generate_actor_image", side_effect=AssertionError("reference frames should be used")), \
                 patch("saasshorts._get_media_duration", return_value=8.0):
                result = saasshorts.generate_storyboard_video(script, config, tmp)

            self.assertEqual(len(head_calls), 2)
            self.assertEqual({c["image"] for c in head_calls}, {ref1, ref2})
            self.assertEqual({c["tier"] for c in head_calls}, {"standard"})
            scene_prompts = " | ".join(c["scene_prompt"] for c in head_calls)
            self.assertIn("close-up", scene_prompts)
            self.assertIn("medium", scene_prompts)

            clips = composite_mock.call_args[0][0]
            self.assertEqual(len(clips), 2)
            self.assertAlmostEqual(sum(c["duration"] for c in clips), 8.0, delta=0.01)

            self.assertEqual(result["storyboard_generation_mode"], "sliced_avatar")
            self.assertIn("sliced_avatar_kling_standard", result["cost_estimate"])

    def test_storyboard_sliced_avatar_routes_broll_shots_to_v3(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref1 = os.path.join(tmp, "ref1.png")
            ref3 = os.path.join(tmp, "ref3.png")
            for p in (ref1, ref3):
                with open(p, "wb") as f:
                    f.write(b"img")

            head_calls = []
            v3_calls = []

            def fake_voiceover(text, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"voice")
                return {"path": output_path, "provider": "fal_minimax", "voice_id": "v"}

            def fake_prepare(audio_path, log=print):
                return {"path": audio_path, "status": "ok", "trimmed": False}

            def fake_slice(audio_path, start, end, output_path):
                with open(output_path, "wb") as f:
                    f.write(b"slice")
                return output_path

            def fake_talking_head(image_path, audio_path, fal_key, output_path, tier="standard", **kwargs):
                head_calls.append({"image": image_path, "output": output_path})
                with open(output_path, "wb") as f:
                    f.write(b"clip")
                return output_path

            def fake_v3_shot(shot, fal_key, output_path, tier="standard", **kwargs):
                v3_calls.append({"shot": shot, "tier": tier, "output": output_path})
                with open(output_path, "wb") as f:
                    f.write(b"clip")
                return output_path

            def fake_composite(clips, audio_path, srt_path, output_path, **kwargs):
                with open(output_path, "wb") as f:
                    f.write(b"final")
                return output_path

            def fake_subs(audio_path, shots, output_path, max_words=2, words=None, **kwargs):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            script = {
                "title": "Hybrid sliced avatar",
                "format": "storyboard_v3",
                "language": "ru",
                "full_narration": "Раз два три четыре. Пять шесть семь восемь. Девять десять один два.",
                "shots": [
                    {"shot_number": 1, "role": "hook", "start": 0, "end": 4,
                     "speech": "Раз два три четыре.", "image_path": ref1,
                     "scene": "close-up", "overlay_text": "", "transition": "cut",
                     "visual_type": "talking"},
                    {"shot_number": 2, "role": "solution", "start": 4, "end": 8,
                     "speech": "Пять шесть семь восемь.",
                     "scene": "hands chopping vegetables on a wooden board",
                     "overlay_text": "", "transition": "cut",
                     "visual_type": "broll"},
                    {"shot_number": 3, "role": "cta", "start": 8, "end": 12,
                     "speech": "Девять десять один два.", "image_path": ref3,
                     "scene": "medium", "overlay_text": "", "transition": "cut",
                     "visual_type": "talking"},
                ],
            }
            config = {
                "fal_key": "fal-test",
                "tts_provider": "fal_minimax",
                "language": "ru",
                "video_mode": "storyboard_v3_standard",
                "storyboard_generation_mode": "sliced_avatar",
            }

            with patch("saasshorts.generate_voiceover_with_fallback", side_effect=fake_voiceover), \
                 patch("saasshorts.prepare_voiceover_for_video_generation", side_effect=fake_prepare), \
                 patch("saasshorts.transcribe_audio_for_subs", return_value=[]), \
                 patch("saasshorts._slice_voiceover_segment", side_effect=fake_slice), \
                 patch("saasshorts.generate_talking_head", side_effect=fake_talking_head), \
                 patch("saasshorts.generate_storyboard_shot_clip", side_effect=fake_v3_shot), \
                 patch("saasshorts.generate_storyboard_ass_subtitles", side_effect=fake_subs), \
                 patch("saasshorts.composite_storyboard_video", side_effect=fake_composite) as composite_mock, \
                 patch("saasshorts.generate_actor_image", side_effect=AssertionError("broll must not trigger actor generation")), \
                 patch("saasshorts._get_media_duration", return_value=12.0):
                result = saasshorts.generate_storyboard_video(script, config, tmp)

            # Talking shots -> Kling Avatar, broll shot -> Kling V3
            self.assertEqual(len(head_calls), 2)
            self.assertEqual({c["image"] for c in head_calls}, {ref1, ref3})
            self.assertEqual(len(v3_calls), 1)
            self.assertIn("_avatar_broll_02", v3_calls[0]["output"])
            self.assertEqual(v3_calls[0]["tier"], "standard")

            # V3 shot copy: duration ceiled to cover the 4s slice, lips shut
            v3_shot = v3_calls[0]["shot"]
            self.assertEqual(v3_shot["start"], 0)
            self.assertEqual(v3_shot["end"], 4)
            self.assertIn("no lip movement", v3_shot["generation_prompt"])
            self.assertIn("vegetables", v3_shot["generation_prompt"])

            clips = composite_mock.call_args[0][0]
            self.assertEqual(len(clips), 3)
            self.assertAlmostEqual(sum(c["duration"] for c in clips), 12.0, delta=0.01)

            cost = result["cost_estimate"]
            self.assertIn("sliced_avatar_kling_standard", cost)
            self.assertIn("sliced_broll_kling_v3_standard", cost)
            self.assertGreater(cost["sliced_broll_kling_v3_standard"], 0)


if __name__ == "__main__":
    unittest.main()

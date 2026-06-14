import json
import os
import tempfile
import unittest
from unittest.mock import patch

from saasshorts import (
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

    def test_talking_head_retries_with_tail_silence_and_saves_audit_metadata(self):
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
                },
                {
                    "video": {"url": "https://cdn.example/tail.mp4"},
                    "_fal_request": {"request_id": "req-tail", "model_id": "model"},
                },
            ]
            quality_results = [
                {
                    "status": "needs_review",
                    "warnings": ["Kling returned video 2.00s longer than the reference voiceover."],
                    "abs_video_reference_delta": 2.0,
                },
                {
                    "status": "ok",
                    "warnings": [],
                    "abs_video_reference_delta": 0.05,
                },
            ]

            with patch("saasshorts.prepare_kling_actor_image", return_value=image_path), \
                 patch("saasshorts._fal_upload_file", side_effect=fake_upload), \
                 patch("saasshorts._fal_run", side_effect=run_results) as fal_run_mock, \
                 patch("saasshorts.httpx.Client", FakeClient), \
                 patch("saasshorts.create_kling_tail_padded_audio", side_effect=fake_tail_audio) as tail_audio_mock, \
                 patch("saasshorts.inspect_talking_head_quality", side_effect=quality_results):
                result_path = generate_talking_head(image_path, audio_path, "fal-test", output_path, tier="pro")

            self.assertEqual(result_path, output_path)
            self.assertEqual(fal_run_mock.call_count, 2)
            self.assertEqual(tail_audio_mock.call_count, 1)
            with open(output_path, "rb") as f:
                self.assertEqual(f.read(), b"video-bytes")

            quality_path = output_path.replace(".mp4", "_quality.json")
            with open(quality_path, "r", encoding="utf-8") as f:
                quality = json.load(f)

            self.assertEqual(quality["status"], "ok")
            self.assertEqual(quality["selected_attempt"], "tail_silence")
            self.assertEqual(quality["paid_attempts"], 2)

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

            def fake_subs(audio_path, output_path, max_words=2):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            def fake_composite(talking_head_path, broll_clips, subtitles_path, hook_text, output_path):
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

            def fake_talking_head(image_path, audio_path, fal_key, output_path, tier="standard"):
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

            def fake_subs(audio_path, output_path, max_words=2):
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("[Script Info]\n")
                return output_path

            def fake_composite(talking_head_path, broll_clips, subtitles_path, hook_text, output_path):
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
                 patch("saasshorts.generate_tiktok_subs", side_effect=fake_subs), \
                 patch("saasshorts.composite_video", side_effect=fake_composite) as composite_mock, \
                 patch("saasshorts._get_media_duration", return_value=10):
                result = generate_full_video(script, config, tmp)

            self.assertEqual(composite_mock.call_count, 1)
            self.assertEqual(result["quality_status"], "needs_review")
            self.assertEqual(result["quality_warnings"], ["Kling returned video 1.20s longer than voiceover."])
            self.assertTrue(os.path.exists(result["video_path"]))


if __name__ == "__main__":
    unittest.main()

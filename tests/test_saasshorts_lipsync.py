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
    kling_avatar_cost_per_second,
    resolve_saas_lipsync_assets,
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


if __name__ == "__main__":
    unittest.main()

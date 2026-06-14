import json
import os
import tempfile
import unittest

from saasshorts import (
    build_kling_avatar_request,
    build_sync_lipsync_request,
    estimate_sync_lipsync_cost,
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


if __name__ == "__main__":
    unittest.main()

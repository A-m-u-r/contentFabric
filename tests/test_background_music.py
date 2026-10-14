import json
import os
import tempfile
import unittest
import asyncio
from unittest.mock import patch

import app
import saasshorts as shorts


class BackgroundMusicTests(unittest.TestCase):
    def test_unknown_track_is_rejected_before_resolving_paid_keys(self):
        request = app.SaaSGenerateRequest(script={}, music_track="not-a-track.wav")
        with patch.object(app, "resolve_effective_api_key", side_effect=AssertionError("Must reject before paid setup")):
            with self.assertRaises(app.HTTPException) as error:
                asyncio.run(app.saasshorts_generate(request, None, None, None))
        self.assertEqual(error.exception.status_code, 400)

    def test_explicit_track_and_volume_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(shorts, "_MUSIC_DIR", tmp):
            track = os.path.join(tmp, "warm_groove_104.wav")
            with open(track, "wb") as handle:
                handle.write(b"music")
            self.assertEqual(shorts._pick_background_music("seed", "warm_groove_104.wav"), track)
            self.assertEqual(shorts.list_background_music()[0]["id"], "warm_groove_104.wav")
            for unsafe in ("../secret.wav", "/etc/secret.wav", "missing.wav"):
                with self.assertRaises(ValueError):
                    shorts._pick_background_music("seed", unsafe)
        request = app.SaaSGenerateRequest(script={}, music_track="warm_groove_104.wav", music_volume=.8)
        self.assertEqual(request.music_track, "warm_groove_104.wav")
        self.assertEqual(request.music_volume, .8)

    def test_automatic_selection_still_works(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(shorts, "_MUSIC_DIR", tmp):
            for name in ("a.mp3", "b.wav"):
                with open(os.path.join(tmp, name), "wb") as handle:
                    handle.write(b"music")
            self.assertEqual(shorts._pick_background_music("same"), shorts._pick_background_music("same", "auto"))
            self.assertEqual(len(shorts.list_background_music()), 2)


class MusicRemixTests(unittest.TestCase):
    JOB = "26269938-a4b3-4f41-bc29-b34722375e45"

    def make_source(self, tmp):
        job_dir = os.path.join(tmp, f"saas_{self.JOB}")
        os.makedirs(job_dir)
        for name in ("__voice.mp3", "__slice_01.mp3", "__subs.ass", "__avatar_01.mp4", "__avatar_broll_02.mp4", "__storyboard_final.mp4"):
            with open(os.path.join(job_dir, name), "wb") as handle:
                handle.write(b"cached-artifact")
        meta = {"owner_user_id": "owner", "job_id": self.JOB, "video_id": "26269938",
                "video_url": f"/videos/saas_{self.JOB}/__storyboard_final.mp4",
                "title": "Обычный ужин", "language": "ru", "script_format": "storyboard_v3",
                "caption": "Caption", "hashtags": ["#test"], "duration": 6.0,
                "cost_details": {"items": [{"key": "paid", "amount_usd": 1.2, "kind": "estimate"}]},
                "shots": [{"shot_number": 1, "visual_type": "talking", "start": 0, "end": 3,
                           "clip_url": f"/videos/saas_{self.JOB}/__avatar_01.mp4"},
                          {"shot_number": 2, "visual_type": "broll", "start": 3, "end": 6,
                           "clip_url": f"/videos/saas_{self.JOB}/__avatar_broll_02.mp4"}]}
        with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as handle:
            json.dump(meta, handle)
        return job_dir, meta

    def test_local_remix_reuses_paid_assets_and_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, "OUTPUT_DIR", tmp):
            job_dir, meta = self.make_source(tmp)

            def compose(clips, audio, subtitles, output, **kwargs):
                self.assertEqual(len(clips), 2)
                self.assertEqual(clips[0]["duration"], 3)
                self.assertEqual(clips[0]["speech_offset"], .025)
                self.assertEqual(clips[1]["speech_offset"], 0)
                self.assertEqual(audio, os.path.join(job_dir, "__voice.mp3"))
                self.assertEqual(subtitles, os.path.join(job_dir, "__subs.ass"))
                self.assertEqual(kwargs["music_volume"], .8)
                with open(output, "wb") as handle:
                    handle.write(b"remixed-video")

            with patch.object(shorts, "composite_storyboard_video", side_effect=compose) as render, \
                    patch.object(shorts, "_pick_background_music", return_value="bed.wav"), \
                    patch.object(shorts, "_get_media_duration", return_value=6.0), \
                    patch.object(shorts, "_mp3_encoder_delay", return_value=.025), \
                    patch.object(app, "_sync_music_workspaces") as sync, \
                    patch.object(shorts, "generate_full_video", side_effect=AssertionError("Paid pipeline must not run")):
                result = app.remix_local_saas_music(self.JOB, {"id": "owner"}, "warm_groove_104.wav", .8, True)
            self.assertEqual(render.call_count, 1)
            self.assertEqual(sync.call_count, 1)
            self.assertEqual(result["hashtags"], meta["hashtags"])
            self.assertEqual(result["cost_details"], meta["cost_details"])
            self.assertEqual(result["music_track"], "warm_groove_104.wav")
            self.assertTrue(result["video_url"].startswith(f"/videos/saas_{self.JOB}/__music_"))
            self.assertEqual(sum(version["current"] for version in result["versions"]), 1)
            self.assertEqual(result["versions"][-1]["video_url"], result["video_url"])
            self.assertEqual(result["versions"][-1]["edit_kind"], "music")
            self.assertTrue(os.path.exists(os.path.join(job_dir, "__storyboard_final.mp4")))

    def test_cannot_remix_another_owners_reel(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, "OUTPUT_DIR", tmp):
            self.make_source(tmp)
            with self.assertRaises(app.HTTPException) as error:
                app.remix_local_saas_music(self.JOB, {"id": "other"}, "auto", 1, True)
            self.assertEqual(error.exception.status_code, 404)

    def test_missing_clip_fails_without_touching_gallery(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, "OUTPUT_DIR", tmp):
            job_dir, before = self.make_source(tmp)
            os.remove(os.path.join(job_dir, "__avatar_broll_02.mp4"))
            with self.assertRaises(app.HTTPException):
                app.remix_local_saas_music(self.JOB, {"id": "owner"}, "auto", 1, True)
            with open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), before)

    def test_remix_sync_changes_only_matching_owned_workspace(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, "AUTH_DB_PATH", os.path.join(tmp, "auth.db")):
            app.init_auth_db()
            with patch.object(app, "claim_legacy_assets_for_user"):
                owner = app.create_user("music-owner@example.com", "secret123")
                other = app.create_user("music-other@example.com", "secret123")
            profiles = {user["id"]: app.upsert_business_profile(user["id"], {"name": "Music test", "description": "Music editing test"}) for user in (owner, other)}
            source = {"jobId": self.JOB, "customScript": "Keep my narration", "scripts": [{"shots": [1, 2]}],
                      "genResult": {"video_url": f"/videos/saas_{self.JOB}/__storyboard_final.mp4"},
                      "result": {"video_url": f"/videos/saas_{self.JOB}/__storyboard_final.mp4"},
                      "videoPrefs": {"selectedVoice": "anna", "backgroundMusic": True}}
            for user in (owner, other):
                app.save_content_workspace(user["id"], profiles[user["id"]]["id"], "reel", 2, "video", source)
            untouched = {**source, "jobId": "another", "genResult": {}, "result": {}}
            app.save_content_workspace(owner["id"], profiles[owner["id"]]["id"], "another-reel", 2, "video", untouched)
            metadata = {"video_url": f"/videos/saas_{self.JOB}/__music_new.mp4", "duration": 6.0,
                        "background_music": False, "music_track": "light_pulse_96.wav", "music_volume": 0}
            app._sync_music_workspaces(owner["id"], self.JOB, metadata)
            changed = app.get_content_workspace(owner["id"], profiles[owner["id"]]["id"], "reel")
            self.assertEqual(changed["revision"], 3)
            self.assertEqual(changed["snapshot"]["customScript"], source["customScript"])
            self.assertEqual(changed["snapshot"]["scripts"], source["scripts"])
            self.assertEqual(changed["snapshot"]["videoPrefs"]["selectedVoice"], "anna")
            self.assertEqual(changed["snapshot"]["videoPrefs"]["musicVolume"], 0)
            self.assertEqual(changed["snapshot"]["genResult"]["video_url"], metadata["video_url"])
            self.assertEqual(app.get_content_workspace(other["id"], profiles[other["id"]]["id"], "reel")["revision"], 2)
            self.assertEqual(app.get_content_workspace(owner["id"], profiles[owner["id"]]["id"], "another-reel")["revision"], 2)


if __name__ == "__main__":
    unittest.main()

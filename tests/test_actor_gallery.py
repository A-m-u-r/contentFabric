import json
import os
import tempfile
import unittest

import app


class JobActorPortraitGalleryTests(unittest.TestCase):
    """The actor gallery must surface portraits created inside finished video
    jobs, not only the dedicated actor_uploads / saas_actors_* folders."""

    def setUp(self):
        self._prev_output_dir = app.OUTPUT_DIR
        self._tmp = tempfile.TemporaryDirectory()
        app.OUTPUT_DIR = self._tmp.name

    def tearDown(self):
        app.OUTPUT_DIR = self._prev_output_dir
        self._tmp.cleanup()

    def _make_job(self, job_id, actor_name, owner, title):
        job_dir = os.path.join(app.OUTPUT_DIR, f"saas_{job_id}")
        os.makedirs(job_dir, exist_ok=True)
        # Primary portrait plus noise that must NOT be picked as the avatar.
        for name in (
            f"{actor_name}_actor.png",
            f"{actor_name}_actor_ref_02.png",
            f"{actor_name}_avatar_01_actor_9x16.png",
        ):
            with open(os.path.join(job_dir, name), "wb") as f:
                f.write(b"\x89PNG\r\n" + b"0" * 2048)
        meta = {"title": title, "owner_user_id": owner, "created_at": "2026-06-01T00:00:00Z"}
        with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return job_dir

    def test_surfaces_primary_portrait_per_job(self):
        self._make_job("job1", "_30_", "user-a", "Тело после 30")
        images = app.list_local_actor_gallery(owner_user_id="user-a")

        self.assertEqual(len(images), 1)
        entry = images[0]
        self.assertTrue(entry["key"].endswith("_30__actor.png"))
        self.assertNotIn("9x16", entry["key"])
        self.assertNotIn("_ref_", entry["key"])
        self.assertEqual(entry["description"], "Тело после 30")
        self.assertEqual(entry["source"], "job")

    def test_owner_filter_hides_other_users_portraits(self):
        self._make_job("job1", "a", "user-a", "A")
        self._make_job("job2", "b", "user-b", "B")

        mine = app.list_local_actor_gallery(owner_user_id="user-a")
        self.assertEqual([e["description"] for e in mine], ["A"])

        anon = app.list_local_actor_gallery(owner_user_id=None)
        self.assertEqual(len(anon), 2)

    def test_ignores_dedicated_actor_dirs_to_avoid_double_listing(self):
        # saas_actors_* is handled by the normal actor-dir scan; the job scan
        # must skip it so a generated avatar is not listed twice.
        actors_dir = os.path.join(app.OUTPUT_DIR, "saas_actors_xyz")
        os.makedirs(actors_dir, exist_ok=True)
        with open(os.path.join(actors_dir, "actor_01.png"), "wb") as f:
            f.write(b"\x89PNG\r\n" + b"0" * 2048)

        images = app.list_local_actor_gallery(owner_user_id=None)
        keys = [e["key"] for e in images]
        self.assertEqual(len(keys), len(set(keys)))


class CleanupDurableDirTests(unittest.TestCase):
    """cleanup_jobs must never purge reusable-asset dirs, or saved avatars
    (actor_uploads / saas_actors_* / storyboard_frames / head_templates)
    silently vanish after the 1h retention window."""

    def test_avatar_and_asset_dirs_are_protected(self):
        for name in (
            "actor_uploads",
            "storyboard_frames",
            "head_templates",
            "thumbnails",
            "saas_actors_abc123",
        ):
            self.assertTrue(app._is_durable_output_dir(name), name)

    def test_video_job_and_random_dirs_are_not_protected(self):
        for name in ("saas_feddb8e4-f627", "saas_1234", "tmpxyz", "uploads"):
            self.assertFalse(app._is_durable_output_dir(name), name)


class AvatarVoiceBindingTests(unittest.TestCase):
    def setUp(self):
        self._prev_output_dir = app.OUTPUT_DIR
        self._tmp = tempfile.TemporaryDirectory()
        app.OUTPUT_DIR = self._tmp.name

    def tearDown(self):
        app.OUTPUT_DIR = self._prev_output_dir
        self._tmp.cleanup()

    def test_set_and_load_binding_roundtrips(self):
        binding = app.set_avatar_voice_binding(
            "actor_uploads/custom_1.png",
            "D5RRIJYa9pFwxiSpbGbR",
            voice_name="Victoria",
            owner_user_id="user-a",
        )
        self.assertEqual(binding["voice_id"], "D5RRIJYa9pFwxiSpbGbR")
        self.assertEqual(binding["voice_name"], "Victoria")

        loaded = app.load_avatar_voice_bindings()
        self.assertIn("actor_uploads/custom_1.png", loaded)
        self.assertEqual(
            loaded["actor_uploads/custom_1.png"]["voice_id"], "D5RRIJYa9pFwxiSpbGbR"
        )

    def test_empty_voice_id_detaches(self):
        app.set_avatar_voice_binding("k", "vid", voice_name="V", owner_user_id="u")
        self.assertIn("k", app.load_avatar_voice_bindings())

        result = app.set_avatar_voice_binding("k", "", owner_user_id="u")
        self.assertIsNone(result)
        self.assertNotIn("k", app.load_avatar_voice_bindings())

    def test_voice_name_defaults_to_voice_id(self):
        binding = app.set_avatar_voice_binding("k", "vid", voice_name="  ")
        self.assertEqual(binding["voice_name"], "vid")

    def test_load_missing_store_returns_empty(self):
        self.assertEqual(app.load_avatar_voice_bindings(), {})

    def test_resolve_bound_voice_from_local_url(self):
        app.set_avatar_voice_binding(
            "actor_uploads/custom_1.png", "vid-123", voice_name="Victoria"
        )
        bound = app.resolve_avatar_bound_voice("/videos/actor_uploads/custom_1.png")
        self.assertIsNotNone(bound)
        self.assertEqual(bound["voice_id"], "vid-123")

    def test_resolve_bound_voice_ignores_unbound_and_remote(self):
        app.set_avatar_voice_binding("actor_uploads/custom_1.png", "vid-123")
        # No binding for this key
        self.assertIsNone(app.resolve_avatar_bound_voice("/videos/actor_uploads/other.png"))
        # Remote S3 URLs are not resolved
        self.assertIsNone(app.resolve_avatar_bound_voice("https://s3.example/img.png"))
        # Empty input
        self.assertIsNone(app.resolve_avatar_bound_voice(None))

    def test_resolve_bound_voice_skips_non_elevenlabs(self):
        app.set_avatar_voice_binding("actor_uploads/m.png", "minimax-x", provider="fal_minimax")
        self.assertIsNone(app.resolve_avatar_bound_voice("/videos/actor_uploads/m.png"))


if __name__ == "__main__":
    unittest.main()

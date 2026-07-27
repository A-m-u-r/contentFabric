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


class EffectiveVoiceForRequestTests(unittest.TestCase):
    """Привязанный к аватару голос — дефолт, а не замок.

    Раньше он перебивал ручной выбор: юзер выбирал в пикере один голос, а
    ролик говорил другим, и сам пикер превращался в обманку.
    """

    BOUND = {"voice_id": "victoria", "voice_name": "Victoria"}

    def test_manual_pick_wins_over_binding(self):
        voice, source = app.effective_voice_for_request("vika", self.BOUND)
        self.assertEqual(voice, "vika")
        self.assertEqual(source, "override")

    def test_binding_fills_in_when_no_voice_sent(self):
        for empty in (None, "", "   "):
            voice, source = app.effective_voice_for_request(empty, self.BOUND)
            self.assertEqual(voice, "victoria")
            self.assertEqual(source, "bound")

    def test_same_voice_is_not_reported_as_override(self):
        _, source = app.effective_voice_for_request("victoria", self.BOUND)
        self.assertEqual(source, "request")

    def test_no_binding_keeps_the_request_voice(self):
        voice, source = app.effective_voice_for_request("vika", None)
        self.assertEqual(voice, "vika")
        self.assertEqual(source, "request")
        self.assertEqual(app.effective_voice_for_request(None, None), (None, "request"))

    def test_voice_audit_keeps_a_manual_pick_visible_and_named(self):
        audit = app.resolve_voice_audit(
            "anna-id",
            "Anna",
            "manual",
            self.BOUND,
        )

        self.assertEqual(audit, {
            "voice_id": "anna-id",
            "voice_name": "Anna",
            "voice_selection_source": "manual",
            "binding_overridden": True,
        })

    def test_voice_audit_uses_the_avatar_binding_only_as_a_default(self):
        audit = app.resolve_voice_audit(None, None, "default", self.BOUND)

        self.assertEqual(audit["voice_id"], "victoria")
        self.assertEqual(audit["voice_name"], "Victoria")
        self.assertEqual(audit["voice_selection_source"], "avatar_binding")
        self.assertFalse(audit["binding_overridden"])

    def test_finished_voice_metadata_records_the_actual_model(self):
        metadata = app.voice_metadata_for_result(
            {
                "voice_id": "anna-id",
                "voice_name": "Anna",
                "voice_model": "eleven_v3",
                "voice_selection_source": "manual",
            },
            fallback_id="fallback-id",
            fallback_name="Fallback",
            fallback_source="default",
        )

        self.assertEqual(metadata, {
            "voice_id": "anna-id",
            "voice_name": "Anna",
            "voice_model": "eleven_v3",
            "voice_selection_source": "manual",
        })


class SafeOutputSubpathTests(unittest.TestCase):
    """A client-supplied /videos/ reference must never resolve outside
    OUTPUT_DIR (path-traversal guard for the selected-actor image)."""

    def setUp(self):
        self._prev_output_dir = app.OUTPUT_DIR
        self._tmp = tempfile.TemporaryDirectory()
        app.OUTPUT_DIR = self._tmp.name

    def tearDown(self):
        app.OUTPUT_DIR = self._prev_output_dir
        self._tmp.cleanup()

    def test_resolves_normal_reference_inside_output(self):
        rel = "actor_uploads/custom_1.png"
        os.makedirs(os.path.join(app.OUTPUT_DIR, "actor_uploads"), exist_ok=True)
        target = os.path.join(app.OUTPUT_DIR, rel)
        with open(target, "wb") as f:
            f.write(b"x")
        resolved = app._safe_output_subpath(f"/videos/{rel}")
        self.assertEqual(os.path.realpath(resolved), os.path.realpath(target))

    def test_rejects_dotdot_traversal(self):
        self.assertIsNone(app._safe_output_subpath("/videos/../../etc/passwd"))
        self.assertIsNone(app._safe_output_subpath("/videos/x/../../../secret.txt"))
        self.assertIsNone(app._safe_output_subpath("/videos/saas_x/../../../secret.txt"))
        self.assertIsNone(app._safe_output_subpath("../../etc/passwd"))

    def test_rejects_empty_and_root(self):
        self.assertIsNone(app._safe_output_subpath(""))
        self.assertIsNone(app._safe_output_subpath(None))
        self.assertIsNone(app._safe_output_subpath("/videos/"))


class AllowedRemoteActorUrlTests(unittest.TestCase):
    """The http branch of selected_actor_url must only fetch our own S3 bucket
    host, never arbitrary URLs (SSRF guard)."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("AWS_S3_BUCKET", "AWS_REGION")}
        os.environ["AWS_S3_BUCKET"] = "my-clips-bucket"
        os.environ["AWS_REGION"] = "eu-west-3"

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_allows_configured_bucket_host(self):
        self.assertTrue(app._allowed_remote_actor_url(
            "https://my-clips-bucket.s3.eu-west-3.amazonaws.com/actors/x.png"))
        self.assertTrue(app._allowed_remote_actor_url(
            "https://my-clips-bucket.s3.amazonaws.com/actors/x.png"))

    def test_blocks_ssrf_targets(self):
        for url in (
            "http://my-clips-bucket.s3.eu-west-3.amazonaws.com/x.png",  # not https
            "https://169.254.169.254/latest/meta-data/",               # cloud metadata
            "https://localhost/x.png",
            "https://evil.com/x.png",
            "https://my-clips-bucket.s3.eu-west-3.amazonaws.com.evil.com/x.png",  # suffix trick
            "https://other-bucket.s3.eu-west-3.amazonaws.com/x.png",   # wrong bucket
        ):
            self.assertFalse(app._allowed_remote_actor_url(url), url)

    def test_blocks_all_remote_when_no_bucket_configured(self):
        os.environ.pop("AWS_S3_BUCKET", None)
        self.assertFalse(app._allowed_remote_actor_url(
            "https://my-clips-bucket.s3.eu-west-3.amazonaws.com/x.png"))


class PreserveExpiringJobAvatarTests(unittest.TestCase):
    """A job that generated an avatar but never produced a final video should
    have its portrait copied into actor_uploads before cleanup purges it."""

    def setUp(self):
        self._prev_output_dir = app.OUTPUT_DIR
        self._tmp = tempfile.TemporaryDirectory()
        app.OUTPUT_DIR = self._tmp.name

    def tearDown(self):
        app.OUTPUT_DIR = self._prev_output_dir
        self._tmp.cleanup()

    def _job_dir(self, job_id, owner="user-a", title="Мой аватар"):
        job_dir = os.path.join(app.OUTPUT_DIR, f"saas_{job_id}")
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "_30__actor.png"), "wb") as f:
            f.write(b"\x89PNG\r\n" + b"0" * 2048)
        # 9x16 and _ref_ variants must not be chosen as the primary portrait.
        with open(os.path.join(job_dir, "_30__actor_9x16.png"), "wb") as f:
            f.write(b"\x89PNG\r\n" + b"0" * 2048)
        meta = {"title": title, "owner_user_id": owner}
        with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return job_dir

    def test_copies_primary_portrait_into_actor_uploads(self):
        import shutil
        job_dir = self._job_dir("job1")
        app._preserve_expiring_job_avatar(job_dir)
        # Cleanup purges the scratch job dir immediately after preserving.
        shutil.rmtree(job_dir)

        preserved = app.list_local_actor_gallery(owner_user_id="user-a")
        self.assertEqual(len(preserved), 1)
        entry = preserved[0]
        self.assertTrue(entry["key"].startswith("actor_uploads/"))
        self.assertNotIn("9x16", entry["key"])
        self.assertEqual(entry.get("description"), "Мой аватар")

    def test_owner_hint_wins_over_missing_metadata(self):
        job_dir = os.path.join(app.OUTPUT_DIR, "saas_job2")
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "a_actor.png"), "wb") as f:
            f.write(b"\x89PNG\r\n" + b"0" * 2048)
        app._preserve_expiring_job_avatar(job_dir, owner_hint="user-b")
        self.assertEqual(len(app.list_local_actor_gallery(owner_user_id="user-b")), 1)
        self.assertEqual(len(app.list_local_actor_gallery(owner_user_id="user-a")), 0)

    def test_idempotent_second_call_is_noop(self):
        job_dir = self._job_dir("job3")
        app._preserve_expiring_job_avatar(job_dir)
        app._preserve_expiring_job_avatar(job_dir)
        # Two calls must not create two copies in actor_uploads.
        uploads = os.path.join(app.OUTPUT_DIR, "actor_uploads")
        pngs = [f for f in os.listdir(uploads) if f.endswith(".png")]
        self.assertEqual(len(pngs), 1)


if __name__ == "__main__":
    unittest.main()

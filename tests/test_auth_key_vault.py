import json
import os
import tempfile
import unittest

import app


class AuthKeyVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = getattr(app, "AUTH_DB_PATH", None)
        self.old_output_dir = app.OUTPUT_DIR
        app.OUTPUT_DIR = self.tmp.name
        app.AUTH_DB_PATH = os.path.join(self.tmp.name, "auth.db")
        app.init_auth_db()

    def tearDown(self):
        if self.old_db_path is not None:
            app.AUTH_DB_PATH = self.old_db_path
        app.OUTPUT_DIR = self.old_output_dir
        self.tmp.cleanup()

    def test_register_login_and_session_lookup(self):
        user = app.create_user("Owner@Example.com", "secret123", "Owner")
        authed = app.authenticate_user("owner@example.com", "secret123")
        token = app.create_session(user["id"])
        session_user = app.get_user_by_token(token)

        self.assertEqual(user["email"], "owner@example.com")
        self.assertEqual(authed["id"], user["id"])
        self.assertEqual(session_user["id"], user["id"])
        self.assertEqual(session_user["subscription_status"], "free")
        self.assertIsNone(app.authenticate_user("owner@example.com", "wrongpass"))

    def test_saves_and_resolves_user_api_keys_without_exposing_other_users(self):
        owner = app.create_user("owner@example.com", "secret123", "Owner")
        other = app.create_user("other@example.com", "secret123", "Other")

        app.upsert_user_api_key(owner["id"], "fal", "fal-owner")
        app.upsert_user_api_key(other["id"], "fal", "fal-other")

        self.assertEqual(app.get_user_api_key(owner["id"], "fal"), "fal-owner")
        self.assertEqual(app.get_user_api_key(other["id"], "fal"), "fal-other")
        listed = app.list_user_api_key_status(owner["id"])
        self.assertTrue(listed["fal"]["has_key"])
        self.assertNotIn("fal-owner", str(listed))

    def test_platform_keys_require_active_subscription(self):
        user = app.create_user("owner@example.com", "secret123", "Owner")
        old_fal = os.environ.get("FAL_KEY")
        os.environ["FAL_KEY"] = "platform-fal"
        try:
            with self.assertRaises(app.SubscriptionRequiredError):
                app.resolve_effective_api_key("fal", user, None, use_platform_keys=True)

            app.set_user_subscription_status(user["id"], "active")
            active_user = app.get_user_by_id(user["id"])
            self.assertEqual(
                app.resolve_effective_api_key("fal", active_user, None, use_platform_keys=True),
                "platform-fal",
            )
        finally:
            if old_fal is None:
                os.environ.pop("FAL_KEY", None)
            else:
                os.environ["FAL_KEY"] = old_fal

    def test_first_user_claims_legacy_assets(self):
        video_dir = os.path.join(self.tmp.name, "saas_legacy-job")
        os.makedirs(video_dir)
        with open(os.path.join(video_dir, "gallery_metadata.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "Legacy video"}, f)

        head_dir = os.path.join(self.tmp.name, "head_templates", "head_legacy")
        os.makedirs(head_dir)
        with open(os.path.join(head_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump({"label": "Legacy head"}, f)

        actor_dir = os.path.join(self.tmp.name, "actor_uploads")
        os.makedirs(actor_dir)
        actor_meta_path = os.path.join(actor_dir, "custom_legacy.json")
        with open(actor_meta_path, "w", encoding="utf-8") as f:
            json.dump({"url": "/videos/actor_uploads/custom_legacy.png", "storage": "local"}, f)

        user = app.create_user("owner@example.com", "secret123", "Owner")

        with open(os.path.join(video_dir, "gallery_metadata.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["owner_user_id"], user["id"])
        with open(os.path.join(head_dir, "metadata.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["owner_user_id"], user["id"])
        with open(actor_meta_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["owner_user_id"], user["id"])


if __name__ == "__main__":
    unittest.main()

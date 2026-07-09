import os
import tempfile
import unittest

import app


class BusinessProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db_path = app.AUTH_DB_PATH
        self.old_output_dir = app.OUTPUT_DIR
        app.OUTPUT_DIR = os.path.join(self.tmp.name, "output")
        app.AUTH_DB_PATH = os.path.join(app.OUTPUT_DIR, "openshorts.db")
        os.makedirs(app.OUTPUT_DIR, exist_ok=True)
        app.init_auth_db()

    def tearDown(self):
        app.AUTH_DB_PATH = self.old_db_path
        app.OUTPUT_DIR = self.old_output_dir
        self.tmp.cleanup()

    def test_business_profiles_are_saved_per_user_account(self):
        user = app.create_user("owner@example.com", "secret123", "Owner")

        saved = app.upsert_business_profile(user["id"], {
            "name": "Неделя без срывов",
            "description": "7 дней, чтобы пройти неделю структурнее.",
            "topic": "вечерние срывы",
            "script_mode": "ai",
            "script_format": "storyboard_v3",
            "style": "ugc",
            "language": "ru",
            "actor_gender": "female",
            "text_model": "pro",
        })

        profiles = app.list_business_profiles(user["id"])

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["id"], saved["id"])
        self.assertEqual(profiles[0]["name"], "Неделя без срывов")
        self.assertEqual(profiles[0]["script_format"], "storyboard_v3")
        self.assertEqual(profiles[0].get("text_model"), "pro")


if __name__ == "__main__":
    unittest.main()

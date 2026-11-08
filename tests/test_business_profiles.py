import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

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
        self.client = TestClient(app.app)

    def tearDown(self):
        self.client.close()
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
        self.assertNotIn("presenter", profiles[0])

    def account(self, email):
        user_id = app.create_user(email, "secret123")["id"]
        return user_id, {"Authorization": "Bearer " + app.create_session(user_id)}

    def picture(self, owner_id, key, *, camera=None):
        path = os.path.join(app.OUTPUT_DIR, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"image" * 300)
        url = "/videos/" + key
        if camera:
            with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as handle:
                json.dump({"url": url, "owner_user_id": owner_id, "camera": camera}, handle)
        else:
            app._write_local_actor_metadata(path, url, owner_user_id=owner_id)
        return url

    def test_legacy_profile_survives_presenter_migration_without_adding_a_preset(self):
        owner, headers = self.account("legacy@example.com")
        saved = app.upsert_business_profile(owner, {
            "name": "Домашняя кухня", "description": "Короткие рецепты", "text_model": "pro",
        })
        with app._auth_db() as connection:
            connection.execute("ALTER TABLE business_profiles DROP COLUMN presenter_json")

        app.init_auth_db()

        with app._auth_db() as connection:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(business_profiles)")}
        self.assertIn("presenter_json", columns)
        profiles = self.client.get("/api/user/business-profiles", headers=headers).json()["profiles"]
        self.assertEqual(profiles, [saved])
        self.assertNotIn("presenter", profiles[0])

    def test_presenter_is_persisted_preserved_on_profile_edit_and_can_be_cleared(self):
        owner, headers = self.account("presenter@example.com")
        generated_url = "https://example.invalid/actor.png"

        def generate_actor(description, key, directory, prefix, count, **options):
            path = os.path.join(directory, "actor_01.png")
            with open(path, "wb") as handle:
                handle.write(b"image" * 300)
            return [path]

        with patch("app.generate_actor_images", side_effect=generate_actor), \
             patch("app.upload_actor_to_s3", return_value=generated_url):
            generated = self.client.post(
                "/api/saasshorts/actor-options",
                json={"actor_description": "Ведущая на кухне", "num_options": 1},
                headers={**headers, "X-Fal-Key": "test-key"},
            )
        self.assertEqual(generated.json(), {"images": [generated_url]})
        presenter = {
            "actor_url": generated_url,
            "face_url": self.picture(owner, "actor_uploads/face.png"),
            "plate_urls": {"front": self.picture(owner, "storyboard_frames/plate_front_123.png", camera="front")},
            "voice_id": "saved-voice",
            "voice_name": "Анна",
            "tts_provider": "elevenlabs",
            "minimax_voice_id": "backup-voice",
            "elevenlabs_model": "eleven_v4",
            "elevenlabs_stability": 0.45,
            "elevenlabs_similarity": 0.7,
        }
        profile = {"name": "Домашняя кухня", "description": "Короткие рецепты"}
        response = self.client.post("/api/user/business-profiles", json={**profile, "presenter": presenter}, headers=headers)
        self.assertEqual(response.status_code, 200)
        saved = response.json()["profile"]
        self.assertEqual(saved.get("presenter"), presenter)
        self.assertEqual(self.client.get("/api/user/business-profiles", headers=headers).json()["profiles"][0]["presenter"], presenter)

        edit = {**profile, "id": saved["id"], "description": "Рецепты после работы"}
        edited = self.client.post("/api/user/business-profiles", json=edit, headers=headers)
        self.assertEqual(edited.json()["profile"]["presenter"], presenter)
        cleared = self.client.post("/api/user/business-profiles", json={**edit, "presenter": None}, headers=headers)
        self.assertIsNone(cleared.json()["profile"]["presenter"])
        self.assertIsNone(self.client.get("/api/user/business-profiles", headers=headers).json()["profiles"][0]["presenter"])

    def test_presenter_cannot_reference_another_accounts_assets_or_modify_its_profile(self):
        owner, headers = self.account("owner@example.com")
        _, other_headers = self.account("other@example.com")
        photo = self.picture(owner, "actor_uploads/owned.png")
        plate = self.picture(owner, "storyboard_frames/plate_front_123.png", camera="front")
        profile = {"name": "Домашняя кухня", "description": "Короткие рецепты"}
        initial = self.client.post("/api/user/business-profiles", json=profile, headers=headers).json()["profile"]
        for presenter in ({"actor_url": photo}, {"face_url": photo}, {"plate_urls": {"front": plate}}):
            with self.subTest(presenter=presenter):
                response = self.client.post("/api/user/business-profiles", json={**profile, "presenter": presenter}, headers=other_headers)
                self.assertEqual(response.status_code, 400)
        modified = self.client.post("/api/user/business-profiles", headers=other_headers, json={
            **profile, "id": initial["id"], "description": "Чужая правка", "presenter": {"voice_id": "other"},
        })
        self.assertIn(modified.status_code, (400, 404))
        self.assertEqual(app.list_business_profiles(owner), [initial])

        other = self.client.post("/api/user/business-profiles", json=profile, headers=other_headers).json()["profile"]
        wrong_asset = self.client.patch(f"/api/user/business-profiles/{other['id']}/presenter", headers=other_headers,
                                        json={"presenter": {"actor_url": photo}})
        wrong_owner = self.client.patch(f"/api/user/business-profiles/{initial['id']}/presenter", headers=other_headers,
                                        json={"presenter": None})
        self.assertEqual(wrong_asset.status_code, 400)
        self.assertEqual(wrong_owner.status_code, 404)
        self.assertEqual(app.list_business_profiles(owner), [initial])

    def test_presenter_patch_keeps_metadata_edited_after_the_project_was_opened(self):
        _, headers = self.account("two-tabs@example.com")
        created = self.client.post("/api/user/business-profiles", headers=headers, json={
            "name": "Домашняя кухня", "description": "Простые рецепты", "topic": "Завтрак",
        }).json()["profile"]
        edited = self.client.post("/api/user/business-profiles", headers=headers, json={
            **created, "name": "Кухня после работы", "description": "Быстрые ужины", "topic": "Ужин", "style": "educational",
        }).json()["profile"]

        url = f"/api/user/business-profiles/{created['id']}/presenter"
        preset = {"voice_id": "local-voice", "tts_provider": "elevenlabs"}
        for presenter in (preset, None):
            with self.subTest(presenter=presenter):
                response = self.client.patch(url, headers=headers, json={"presenter": presenter})
                self.assertEqual(response.status_code, 200)
                saved = response.json()["profile"]
                self.assertEqual(saved, {**edited, "updated_at": saved["updated_at"], "presenter": presenter})
                self.assertEqual(response.json()["profiles"], [saved])


if __name__ == "__main__":
    unittest.main()

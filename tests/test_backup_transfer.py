import io
import gc
import json
import os
import shutil
import tempfile
import unittest
import zipfile

import app


class BackupTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_output_dir = app.OUTPUT_DIR
        self.old_upload_dir = app.UPLOAD_DIR
        self.old_db_path = app.AUTH_DB_PATH
        self.old_env_path = getattr(app, "ENV_PATH", ".env")

        app.OUTPUT_DIR = os.path.join(self.tmp.name, "output")
        app.UPLOAD_DIR = os.path.join(self.tmp.name, "uploads")
        app.AUTH_DB_PATH = os.path.join(app.OUTPUT_DIR, "openshorts.db")
        app.ENV_PATH = os.path.join(self.tmp.name, ".env")
        os.makedirs(app.OUTPUT_DIR, exist_ok=True)
        os.makedirs(app.UPLOAD_DIR, exist_ok=True)
        app.init_auth_db()

    def tearDown(self):
        app.OUTPUT_DIR = self.old_output_dir
        app.UPLOAD_DIR = self.old_upload_dir
        app.AUTH_DB_PATH = self.old_db_path
        app.ENV_PATH = self.old_env_path
        self.tmp.cleanup()

    def test_backup_archive_includes_db_media_uploads_and_env(self):
        with open(app.ENV_PATH, "w", encoding="utf-8") as f:
            f.write("OPENSHORTS_KEY_VAULT_SECRET=portable-secret\n")

        user = app.create_user("owner@example.com", "secret123", "Owner")
        app.upsert_user_api_key(user["id"], "fal", "fal-secret")

        video_dir = os.path.join(app.OUTPUT_DIR, "saas_video-1")
        os.makedirs(video_dir, exist_ok=True)
        with open(os.path.join(video_dir, "__final.mp4"), "wb") as f:
            f.write(b"video")
        with open(os.path.join(video_dir, "gallery_metadata.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "Transferred video", "owner_user_id": user["id"]}, f)

        actor_dir = os.path.join(app.OUTPUT_DIR, "actor_uploads")
        os.makedirs(actor_dir, exist_ok=True)
        with open(os.path.join(actor_dir, "avatar.png"), "wb") as f:
            f.write(b"avatar")

        upload_path = os.path.join(app.UPLOAD_DIR, "source.png")
        with open(upload_path, "wb") as f:
            f.write(b"upload")

        archive = app.create_backup_archive(user["id"])

        with zipfile.ZipFile(io.BytesIO(archive), "r") as zf:
            names = set(zf.namelist())
            manifest = json.loads(zf.read("openshorts-backup.json").decode("utf-8"))

        self.assertEqual(manifest["format"], "openshorts-backup")
        self.assertEqual(manifest["owner_user_id"], user["id"])
        self.assertIn("output/openshorts.db", names)
        self.assertIn("output/saas_video-1/__final.mp4", names)
        self.assertIn("output/actor_uploads/avatar.png", names)
        self.assertIn("uploads/source.png", names)
        self.assertIn(".env", names)

    def test_restore_backup_archive_restores_files_and_saved_keys(self):
        user = app.create_user("owner@example.com", "secret123", "Owner")
        app.upsert_user_api_key(user["id"], "fal", "fal-secret")

        video_dir = os.path.join(app.OUTPUT_DIR, "saas_video-1")
        os.makedirs(video_dir, exist_ok=True)
        with open(os.path.join(video_dir, "__final.mp4"), "wb") as f:
            f.write(b"video")
        with open(os.path.join(app.UPLOAD_DIR, "source.png"), "wb") as f:
            f.write(b"upload")

        archive = app.create_backup_archive(user["id"])

        gc.collect()
        shutil.rmtree(app.OUTPUT_DIR)
        shutil.rmtree(app.UPLOAD_DIR)
        os.makedirs(app.OUTPUT_DIR, exist_ok=True)
        os.makedirs(app.UPLOAD_DIR, exist_ok=True)

        summary = app.restore_backup_archive(archive)

        self.assertIn("output", summary["restored_roots"])
        self.assertIn("uploads", summary["restored_roots"])
        self.assertTrue(os.path.exists(os.path.join(app.OUTPUT_DIR, "saas_video-1", "__final.mp4")))
        self.assertTrue(os.path.exists(os.path.join(app.UPLOAD_DIR, "source.png")))
        self.assertEqual(app.get_user_api_key(user["id"], "fal"), "fal-secret")

    def test_restore_backup_archive_rejects_path_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("openshorts-backup.json", json.dumps({"format": "openshorts-backup", "version": 1}))
            zf.writestr("../evil.txt", "bad")

        with self.assertRaises(ValueError):
            app.restore_backup_archive(buf.getvalue())

        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "evil.txt")))


if __name__ == "__main__":
    unittest.main()

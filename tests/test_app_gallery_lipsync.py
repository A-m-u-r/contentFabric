import unittest
import json
import os
import tempfile

import app
from app import _job_id_from_saas_video_url


class GalleryLipSyncTests(unittest.TestCase):
    def test_extracts_full_job_id_from_local_gallery_video_url(self):
        video_url = "/videos/saas_26269938-a4b3-4f41-bc29-b34722375e45/__final.mp4?v=123"

        self.assertEqual(
            _job_id_from_saas_video_url(video_url),
            "26269938-a4b3-4f41-bc29-b34722375e45",
        )

    def test_rejects_remote_gallery_video_url(self):
        self.assertIsNone(_job_id_from_saas_video_url("https://cdn.example/video.mp4"))

    def test_saves_local_talking_head_template_from_job(self):
        old_output_dir = app.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            app.OUTPUT_DIR = tmp
            job_id = "26269938-a4b3-4f41-bc29-b34722375e45"
            job_dir = os.path.join(tmp, f"saas_{job_id}")
            os.makedirs(job_dir)

            with open(os.path.join(job_dir, "__head.mp4"), "wb") as f:
                f.write(b"head-video")
            with open(os.path.join(job_dir, "__actor.png"), "wb") as f:
                f.write(b"actor-image")
            with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as f:
                json.dump({"title": "Reusable wellness head", "language": "ru"}, f)

            template = app.save_local_head_template(job_id, label="Reusable wellness head")
            listed = app.list_local_head_templates()
            resolved = app.resolve_head_template_path(template["template_id"])

            self.assertEqual(template["label"], "Reusable wellness head")
            self.assertTrue(template["video_url"].startswith("/videos/head_templates/"))
            self.assertTrue(os.path.exists(os.path.join(tmp, "head_templates", template["template_id"], "head.mp4")))
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["template_id"], template["template_id"])
            self.assertEqual(resolved["head_path"], os.path.join(tmp, "head_templates", template["template_id"], "head.mp4"))
            self.assertTrue(resolved["poster_path"].endswith("actor.png"))
        app.OUTPUT_DIR = old_output_dir

    def test_head_templates_are_filtered_by_owner(self):
        old_output_dir = app.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            app.OUTPUT_DIR = tmp

            for owner_id in ("user_a", "user_b"):
                job_id = f"{owner_id}-job"
                job_dir = os.path.join(tmp, f"saas_{job_id}")
                os.makedirs(job_dir)
                with open(os.path.join(job_dir, "__head.mp4"), "wb") as f:
                    f.write(b"head-video")
                with open(os.path.join(job_dir, "__actor.png"), "wb") as f:
                    f.write(b"actor-image")
                with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as f:
                    json.dump({"title": owner_id, "owner_user_id": owner_id}, f)
                app.save_local_head_template(job_id, owner_user_id=owner_id)

            templates = app.list_local_head_templates(owner_user_id="user_a")
            self.assertEqual(len(templates), 1)
            self.assertEqual(templates[0]["owner_user_id"], "user_a")

        app.OUTPUT_DIR = old_output_dir


if __name__ == "__main__":
    unittest.main()

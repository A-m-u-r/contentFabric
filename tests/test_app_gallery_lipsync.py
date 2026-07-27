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


class StoryboardReshootSourceTests(unittest.TestCase):
    """Пересъёмка тянет файлы из чужого джоба — значит, нужен тот же контроль доступа."""

    JOB_ID = "26269938-a4b3-4f41-bc29-b34722375e45"

    def _job_dir(self, tmp, meta=None):
        job_dir = os.path.join(tmp, f"saas_{self.JOB_ID}")
        os.makedirs(job_dir, exist_ok=True)
        if meta is not None:
            with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f)
        return job_dir

    def test_rejects_an_id_that_is_not_a_uuid(self):
        # id становится именем каталога: "../" увёл бы запись за пределы output.
        with self.assertRaises(app.HTTPException) as raised:
            app._owned_saas_job_dir("../etc", None, "source_job_id")
        self.assertEqual(raised.exception.status_code, 400)

    def test_missing_job_dir_returns_none_instead_of_failing(self):
        old_output_dir = app.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            app.OUTPUT_DIR = tmp
            self.assertIsNone(app._owned_saas_job_dir(self.JOB_ID, None, "source_job_id"))
        app.OUTPUT_DIR = old_output_dir

    def test_another_users_job_is_not_reachable(self):
        old_output_dir = app.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            app.OUTPUT_DIR = tmp
            self._job_dir(tmp, {"title": "Чужой ролик", "owner_user_id": "user_a"})
            with self.assertRaises(app.HTTPException) as raised:
                app._owned_saas_job_dir(self.JOB_ID, {"id": "user_b"}, "source_job_id")
            self.assertEqual(raised.exception.status_code, 404)
            self.assertEqual(
                app._owned_saas_job_dir(self.JOB_ID, {"id": "user_a"}, "source_job_id"),
                os.path.join(tmp, f"saas_{self.JOB_ID}"),
            )
        app.OUTPUT_DIR = old_output_dir

    def test_slug_comes_from_the_title_and_falls_back_to_the_rendered_file(self):
        old_output_dir = app.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            app.OUTPUT_DIR = tmp
            job_dir = self._job_dir(tmp, {"title": "Моя форма 30+"})
            with open(os.path.join(job_dir, "moya_forma_30_storyboard_final.mp4"), "wb") as f:
                f.write(b"cut")
            self.assertEqual(app._storyboard_slug_of_job(job_dir), app.storyboard_title_slug("Моя форма 30+"))

            # Джоб без метаданных: слаг читаем с диска, иначе перенос промахнётся
            # мимо кэша и пользователь заплатит за уже снятые кадры.
            os.remove(os.path.join(job_dir, "gallery_metadata.json"))
            self.assertEqual(app._storyboard_slug_of_job(job_dir), "moya_forma_30")
        app.OUTPUT_DIR = old_output_dir

    def test_preview_job_slug_is_read_off_the_staged_camera_plates(self):
        # У джоба предпросмотра нет ни метаданных, ни готового ролика — только
        # кадры. Без слага перенос промахнётся мимо кэша, и рендер купит заново
        # ровно те картинки, которые пользователь уже одобрил.
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = os.path.join(tmp, "saas_preview")
            os.makedirs(job_dir)
            with open(os.path.join(job_dir, "moya_forma_30_actor_set_medium.png"), "wb") as f:
                f.write(b"plate")
            self.assertEqual(app._frames_slug_of_job(job_dir), "moya_forma_30")

    def test_preview_job_without_plates_falls_back_to_the_usual_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = os.path.join(tmp, "saas_preview")
            os.makedirs(job_dir)
            self.assertEqual(app._frames_slug_of_job(job_dir), "")

    def test_voice_preview_slug_is_read_off_the_recorded_track(self):
        # Джоб прослушивания — это только звук: ни метаданных, ни ролика. Без
        # слага дорожка не переедет в рендер, и он запишет другой дубль вместо
        # того, который человек послушал и утвердил.
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = os.path.join(tmp, "saas_voice")
            os.makedirs(job_dir)
            with open(os.path.join(job_dir, "moya_forma_30_voice.mp3"), "wb") as f:
                f.write(b"take")
            self.assertEqual(app._voice_slug_of_job(job_dir), "moya_forma_30")

            with open(os.path.join(job_dir, "moya_forma_30_voice_manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"shots": []}, f)
            self.assertEqual(app._voice_slug_of_job(job_dir), "moya_forma_30")

    def test_voice_preview_slug_without_a_track_falls_back_to_the_usual_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = os.path.join(tmp, "saas_voice")
            os.makedirs(job_dir)
            self.assertEqual(app._voice_slug_of_job(job_dir), "")


if __name__ == "__main__":
    unittest.main()

import asyncio
import json
import os
import tempfile
import unittest
import uuid

import app


class ContentWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db_path = app.AUTH_DB_PATH
        self.old_output_dir = app.OUTPUT_DIR
        app.OUTPUT_DIR = os.path.join(self.tmp.name, "output")
        app.AUTH_DB_PATH = os.path.join(app.OUTPUT_DIR, "openshorts.db")
        os.makedirs(app.OUTPUT_DIR, exist_ok=True)
        app.init_auth_db()
        self.owner = app.create_user("owner@example.com", "secret123", "Owner")
        self.profile = app.upsert_business_profile(self.owner["id"], {
            "name": "Owner profile",
            "description": "Owner description",
        })

    def tearDown(self):
        app.AUTH_DB_PATH = self.old_db_path
        app.OUTPUT_DIR = self.old_output_dir
        self.tmp.cleanup()

    def _save(self, item_id="item-1", revision=1, stage="script", snapshot=None):
        return app.save_content_workspace(
            self.owner["id"],
            self.profile["id"],
            item_id,
            revision,
            stage,
            snapshot or {"title": "Draft", "blocks": ["intro"]},
        )

    def test_persists_and_returns_decoded_snapshot(self):
        saved = self._save(snapshot={"title": "Plan", "nested": {"frames": [1, 2]}})

        stored = app.get_content_workspace(self.owner["id"], self.profile["id"], "item-1")

        self.assertEqual(saved["revision"], 1)
        self.assertEqual(stored["stage"], "script")
        self.assertEqual(stored["snapshot"], {"title": "Plan", "nested": {"frames": [1, 2]}})

    def test_save_echoes_the_revision_it_was_given(self):
        """Запись возвращает присланную ревизию, а не свою следующую.

        По этому фронт отличает эхо собственного PUT от чужой записи: ревизия в
        ответе больше присланной — значит, писал кто-то ещё, и снапшот надо
        принять. Начни PUT возвращать revision+1 — и автосохранение закольцуется
        (каждый ответ выглядел бы новее локального).
        """
        first = self._save(revision=7, snapshot={"title": "Draft"})
        second = self._save(revision=8, snapshot={"title": "Draft"})

        self.assertEqual((first["revision"], second["revision"]), (7, 8))

    def test_stale_revision_returns_the_newer_stored_workspace(self):
        self._save(revision=4, snapshot={"title": "Newer"})

        stale_result = self._save(revision=3, stage="frames", snapshot={"title": "Older"})

        self.assertEqual(stale_result["revision"], 4)
        self.assertEqual(stale_result["stage"], "script")
        self.assertEqual(stale_result["snapshot"], {"title": "Newer"})

    def test_lists_workspace_summaries_for_one_profile(self):
        self._save(item_id="first", revision=1, stage="script")
        self._save(item_id="second", revision=2, stage="frames")

        summaries = app.list_content_workspace_summaries(self.owner["id"], self.profile["id"])

        self.assertEqual(
            [(summary["item_id"], summary["revision"], summary["stage"]) for summary in summaries],
            [("second", 2, "frames"), ("first", 1, "script")],
        )
        self.assertNotIn("snapshot", summaries[0])

    def test_authenticated_endpoints_save_get_list_and_delete_workspace(self):
        token = app.create_session(self.owner["id"])
        authorization = f"Bearer {token}"
        request = app.ContentWorkspaceRequest(
            revision=1,
            stage="script",
            snapshot={"title": "Endpoint draft"},
        )

        saved = asyncio.run(app.user_save_content_workspace(
            self.profile["id"], "endpoint-item", request, authorization,
        ))
        fetched = asyncio.run(app.user_content_workspace(
            self.profile["id"], "endpoint-item", authorization,
        ))
        listed = asyncio.run(app.user_content_workspace_summaries(self.profile["id"], authorization))
        deleted = asyncio.run(app.user_delete_content_workspace(
            self.profile["id"], "endpoint-item", authorization,
        ))

        self.assertEqual(saved["workspace"]["snapshot"], {"title": "Endpoint draft"})
        self.assertEqual(fetched["workspace"]["item_id"], "endpoint-item")
        self.assertEqual(listed["workspaces"][0]["item_id"], "endpoint-item")
        self.assertEqual(deleted, {"deleted": True})
        self.assertIsNone(app.get_content_workspace(self.owner["id"], self.profile["id"], "endpoint-item"))

    def test_endpoints_reject_unauthenticated_requests(self):
        with self.assertRaises(app.HTTPException) as error:
            asyncio.run(app.user_content_workspace_summaries(self.profile["id"], None))

        self.assertEqual(error.exception.status_code, 401)

    def test_endpoints_reject_profiles_not_owned_by_authenticated_user(self):
        other = app.create_user("other@example.com", "secret123", "Other")
        other_profile = app.upsert_business_profile(other["id"], {
            "name": "Other profile",
            "description": "Other description",
        })
        authorization = f"Bearer {app.create_session(self.owner['id'])}"
        request = app.ContentWorkspaceRequest(revision=1, snapshot={"title": "Not allowed"})

        calls = [
            lambda: app.user_content_workspace_summaries(other_profile["id"], authorization),
            lambda: app.user_content_workspace(other_profile["id"], "item", authorization),
            lambda: app.user_save_content_workspace(other_profile["id"], "item", request, authorization),
            lambda: app.user_delete_content_workspace(other_profile["id"], "item", authorization),
        ]

        for call in calls:
            with self.assertRaises(app.HTTPException) as error:
                asyncio.run(call())
            self.assertEqual(error.exception.status_code, 404)

    def test_endpoint_rejects_invalid_workspace_payloads(self):
        authorization = f"Bearer {app.create_session(self.owner['id'])}"
        invalid_requests = [
            app.ContentWorkspaceRequest(revision=0, snapshot={"title": "Invalid revision"}),
            app.ContentWorkspaceRequest(revision=1, stage="review", snapshot={"title": "Invalid stage"}),
            app.ContentWorkspaceRequest(revision=1, snapshot={"blob": "x" * (2 * 1024 * 1024)}),
        ]

        for request in invalid_requests:
            with self.assertRaises(app.HTTPException) as error:
                asyncio.run(app.user_save_content_workspace(
                    self.profile["id"], "invalid", request, authorization,
                ))
            self.assertEqual(error.exception.status_code, 400)

    def _ready_video(self, owner=None, filename="final.mp4"):
        job_id = str(uuid.uuid4())
        job_dir = os.path.join(app.OUTPUT_DIR, f"saas_{job_id}")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, filename), "wb") as handle:
            handle.write(b"saved video bytes")
        metadata = {"owner_user_id": owner or self.owner["id"],
                    "video_url": f"/videos/saas_{job_id}/{filename}", "duration": 18.9}
        with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as handle:
            json.dump(metadata, handle)
        return job_dir, metadata

    def test_summary_exposes_owned_ready_video_without_large_snapshot(self):
        _, metadata = self._ready_video()
        self._save(stage="video", snapshot={"genStatus": "completed", "genResult": metadata,
                                           "customScript": "Keep this text"})
        summary = app.list_content_workspace_summaries(self.owner["id"], self.profile["id"])[0]
        self.assertNotIn("snapshot", summary)
        self.assertEqual(summary.get("video", {}).get("video_url"), metadata["video_url"])
        self.assertEqual(summary["video"]["duration"], 18.9)
        self.assertEqual(summary["video"]["download_url"],
                         f"/api/user/content-workspaces/{self.profile['id']}/item-1/video")
        self.assertEqual(app.get_content_workspace(self.owner["id"], self.profile["id"], "item-1")
                         ["snapshot"]["customScript"], "Keep this text")

    def test_summary_and_download_use_latest_gallery_edit_not_stale_snapshot(self):
        job_dir, metadata = self._ready_video(filename="food_photos.mp4")
        with open(os.path.join(job_dir, "old.mp4"), "wb") as handle:
            handle.write(b"old video")
        self._save(stage="video", snapshot={"result": {
            "video_url": metadata["video_url"].replace("food_photos", "old")}})
        summary = app.list_content_workspace_summaries(self.owner["id"], self.profile["id"])[0]
        self.assertEqual(summary.get("video", {}).get("filename"), "food_photos.mp4")
        auth = f"Bearer {app.create_session(self.owner['id'])}"
        response = asyncio.run(app.user_content_workspace_video(self.profile["id"], "item-1", auth))
        self.assertEqual(response.path, os.path.join(job_dir, "food_photos.mp4"))
        self.assertIn("attachment", response.headers["content-disposition"])

    def test_missing_file_is_not_marked_ready(self):
        job_dir, metadata = self._ready_video()
        os.remove(os.path.join(job_dir, "final.mp4"))
        self._save(stage="video", snapshot={"result": metadata})
        summary = app.list_content_workspace_summaries(self.owner["id"], self.profile["id"])[0]
        self.assertIsNone(summary.get("video"))

    def test_another_owners_job_cannot_be_downloaded_through_own_workspace(self):
        _, metadata = self._ready_video(owner="someone-else")
        self._save(stage="video", snapshot={"result": metadata})
        summary = app.list_content_workspace_summaries(self.owner["id"], self.profile["id"])[0]
        self.assertIsNone(summary.get("video"))
        auth = f"Bearer {app.create_session(self.owner['id'])}"
        with self.assertRaises(app.HTTPException) as error:
            asyncio.run(app.user_content_workspace_video(self.profile["id"], "item-1", auth))
        self.assertEqual(error.exception.status_code, 404)

    def test_gallery_path_escape_is_not_downloadable(self):
        job_dir, metadata = self._ready_video()
        self._save(stage="video", snapshot={"result": metadata})
        metadata["video_url"] = metadata["video_url"].replace("final.mp4", "../private.mp4")
        with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as handle:
            json.dump(metadata, handle)
        self.assertIsNone(app.list_content_workspace_summaries(self.owner["id"], self.profile["id"])[0].get("video"))

    def test_frames_preview_is_not_a_completed_video(self):
        _, metadata = self._ready_video()
        self._save(stage="frames", snapshot={"genStatus": "completed", "result": metadata})
        self.assertIsNone(app.list_content_workspace_summaries(self.owner["id"], self.profile["id"])[0].get("video"))

    def test_video_download_requires_authentication_and_profile_ownership(self):
        _, metadata = self._ready_video()
        self._save(stage="video", snapshot={"result": metadata})
        with self.assertRaises(app.HTTPException) as error:
            asyncio.run(app.user_content_workspace_video(self.profile["id"], "item-1", None))
        self.assertEqual(error.exception.status_code, 401)
        other = app.create_user("downloader@example.com", "secret123")
        auth = f"Bearer {app.create_session(other['id'])}"
        with self.assertRaises(app.HTTPException) as error:
            asyncio.run(app.user_content_workspace_video(self.profile["id"], "item-1", auth))
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

import asyncio
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()

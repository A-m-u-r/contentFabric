import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import app


class ContentPlanPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db_path = app.AUTH_DB_PATH
        app.AUTH_DB_PATH = os.path.join(self.tmp.name, "auth.db")
        app.init_auth_db()
        with patch("app.claim_legacy_assets_for_user"):
            self.owner = app.create_user("plan-owner@example.com", "secret123")
        self.other = app.create_user("plan-other@example.com", "secret123")
        self.profile = app.upsert_business_profile(self.owner["id"], {
            "name": "Моя Форма 30+", "description": "Тренировки и питание",
        })
        self.plan = {
            "items": [{"item_id": "reel-1", "day": 1, "title": "Первый",
                       "full_narration": "[curious] Привет."}],
            "done": {"reel-1": False},
            "generatedAt": "2026-09-22T00:00:00Z",
        }

    def tearDown(self):
        app.AUTH_DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def test_round_trip_keeps_text_and_checkboxes(self):
        saved = app.save_content_plan(self.owner["id"], self.profile["id"], self.plan)
        self.assertEqual(saved["items"], self.plan["items"])
        self.assertFalse(saved["done"]["reel-1"])

        changed = {**self.plan, "done": {"reel-1": True}}
        app.save_content_plan(self.owner["id"], self.profile["id"], changed)
        loaded = app.get_content_plan(self.owner["id"], self.profile["id"])
        self.assertTrue(loaded["done"]["reel-1"])
        self.assertEqual(loaded["items"][0]["full_narration"], "[curious] Привет.")

    def test_endpoints_reject_another_users_profile(self):
        token = app.create_session(self.other["id"])
        auth = f"Bearer {token}"
        with self.assertRaises(HTTPException) as context:
            asyncio.run(app.user_content_plan(self.profile["id"], auth))
        self.assertEqual(context.exception.status_code, 404)
        with self.assertRaises(HTTPException) as context:
            asyncio.run(app.user_save_content_plan(
                self.profile["id"], app.ContentPlanSaveRequest(plan=self.plan), auth,
            ))
        self.assertEqual(context.exception.status_code, 404)

    def test_endpoints_round_trip_for_owner(self):
        token = app.create_session(self.owner["id"])
        auth = f"Bearer {token}"
        asyncio.run(app.user_save_content_plan(
            self.profile["id"], app.ContentPlanSaveRequest(plan=self.plan), auth,
        ))
        loaded = asyncio.run(app.user_content_plan(self.profile["id"], auth))
        self.assertEqual(loaded["plan"]["items"], self.plan["items"])


if __name__ == "__main__":
    unittest.main()

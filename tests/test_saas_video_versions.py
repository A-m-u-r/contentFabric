import unittest

import app


class SaasVideoVersionsTests(unittest.TestCase):
    def test_legacy_gallery_meta_gets_current_version(self):
        meta = app._with_default_saas_video_versions({
            "video_url": "/videos/saas_job/__final.mp4?v=old",
            "created_at": "2026-06-14T10:00:00Z",
        })

        self.assertEqual(meta["versions"], [{
            "id": "v001",
            "label": "Original",
            "video_url": "/videos/saas_job/__final.mp4",
            "created_at": "2026-06-14T10:00:00Z",
            "current": True,
            "lipsync_model": "",
            "lipsync_sync_mode": "",
        }])

    def test_lipsync_versions_preserve_previous_current_and_mark_new_current(self):
        previous_meta = {
            "video_url": "/videos/saas_job/__final.mp4?v=old",
            "created_at": "2026-06-14T10:00:00Z",
        }

        versions = app._build_saas_video_versions(
            previous_meta,
            "/videos/saas_job/__final_v002_lipsync_2.mp4",
            "lipsync-2",
            "cut_off",
            1.23,
            created_at="2026-06-14T11:00:00Z",
        )

        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]["id"], "v001")
        self.assertEqual(versions[0]["label"], "Original")
        self.assertEqual(versions[0]["video_url"], "/videos/saas_job/__final.mp4")
        self.assertFalse(versions[0]["current"])

        self.assertEqual(versions[1]["id"], "v002")
        self.assertEqual(versions[1]["label"], "Lipsync 2")
        self.assertEqual(versions[1]["video_url"], "/videos/saas_job/__final_v002_lipsync_2.mp4")
        self.assertEqual(versions[1]["lipsync_model"], "lipsync-2")
        self.assertEqual(versions[1]["lipsync_cost_estimate"], 1.23)
        self.assertTrue(versions[1]["current"])

    def test_lipsync_costs_accumulate_for_each_version(self):
        cost = app._add_saas_lipsync_cost(
            {"actor_image_flux": 0.05, "lipsync_v002_lipsync_2": 1.5, "total": 1.55},
            "lipsync-2",
            1.5,
            "v003",
        )

        self.assertEqual(cost["lipsync_v002_lipsync_2"], 1.5)
        self.assertEqual(cost["lipsync_v003_lipsync_2"], 1.5)
        self.assertEqual(cost["total"], 3.05)


if __name__ == "__main__":
    unittest.main()

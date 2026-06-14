import unittest

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


if __name__ == "__main__":
    unittest.main()

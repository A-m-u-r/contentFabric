import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "dashboard" / "src" / "config.js"
GALLERY = ROOT / "dashboard" / "src" / "components" / "UGCGallery.jsx"
APP = ROOT / "dashboard" / "src" / "App.jsx"


class FrontendGalleryMediaAndKeysTests(unittest.TestCase):
    def test_local_dev_api_urls_do_not_depend_on_vite_proxy_port(self):
        config = CONFIG.read_text(encoding="utf-8")

        self.assertIn("LOCAL_BACKEND_ORIGIN", config)
        self.assertIn("window.location.hostname", config)
        self.assertIn("127.0.0.1:8000", config)
        self.assertIn("new URL(path)", config)
        self.assertIn("isLocalApiBase", config)
        self.assertIn("LOCAL_HOSTS.has(parsed.hostname)", config)

    def test_ugc_gallery_normalizes_video_and_avatar_media_urls(self):
        gallery = GALLERY.read_text(encoding="utf-8")

        self.assertIn("const mediaUrl = (url) => getApiUrl(url || '')", gallery)
        self.assertIn("src={mediaUrl(video.video_url)}", gallery)
        self.assertEqual(gallery.count("poster={mediaUrl(video.cover_url || video.actor_url)}"), 2)
        self.assertIn("href={mediaUrl(version.video_url)}", gallery)

    def test_cover_is_downloadable_without_replacing_actor_reference(self):
        gallery = GALLERY.read_text(encoding="utf-8")
        self.assertIn("href={mediaUrl(video.cover_url)}", gallery)
        self.assertIn("Скачать обложку", gallery)

    def test_settings_show_account_key_status_for_replaceable_provider_keys(self):
        app = APP.read_text(encoding="utf-8")

        self.assertIn("ProviderKeyInput", app)
        self.assertIn("hasAccountKey={hasSavedKey('fal')}", app)
        self.assertIn("hasAccountKey={hasSavedKey('elevenlabs')}", app)
        self.assertIn("Сохранено в аккаунте", app)

    def test_settings_expose_transfer_backup_controls(self):
        app = APP.read_text(encoding="utf-8")

        self.assertIn("handleExportBackup", app)
        self.assertIn("handleImportBackup", app)
        self.assertIn("/api/backup/export", app)
        self.assertIn("/api/backup/import", app)
        self.assertIn("backupStatus", app)


if __name__ == "__main__":
    unittest.main()

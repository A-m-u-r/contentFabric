import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LANDING = ROOT / "dashboard" / "src" / "Landing.jsx"
INDEX = ROOT / "dashboard" / "index.html"


class LandingPositioningTests(unittest.TestCase):
    def test_landing_positions_product_as_subscription_series_engine(self):
        landing = LANDING.read_text(encoding="utf-8")
        index = INDEX.read_text(encoding="utf-8")
        combined = f"{landing}\n{index}".lower()

        for banned in ("github", "open source", "self-hosted", "free open source"):
            self.assertNotIn(banned, combined)

        self.assertIn("OpenShorts / series engine", landing)
        self.assertIn("OpenShorts", landing)
        self.assertIn("Подписка", landing)
        self.assertIn("свои API-ключи", landing)
        self.assertIn("TikTok", landing)
        self.assertIn("Instagram", landing)
        self.assertIn("YouTube", landing)

    def test_landing_has_region_based_copy(self):
        landing = LANDING.read_text(encoding="utf-8")

        self.assertRegex(landing, re.compile(r"const\s+LANDING_COPY\s*="))
        self.assertIn("ru:", landing)
        self.assertIn("en:", landing)
        self.assertIn("navigator.language", landing)


if __name__ == "__main__":
    unittest.main()

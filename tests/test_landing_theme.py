import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LANDING = ROOT / "dashboard" / "src" / "Landing.jsx"
CSS = ROOT / "dashboard" / "src" / "index.css"


class LandingThemeTests(unittest.TestCase):
    def test_landing_has_persisted_light_theme_toggle(self):
        landing = LANDING.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")

        self.assertIn("openshorts_landing_theme_v2", landing)
        self.assertIn("theme-light", landing)
        self.assertIn("theme-dark", landing)
        self.assertIn("localStorage.setItem(THEME_KEY", landing)
        self.assertIn("Sun", landing)
        self.assertIn("Moon", landing)
        self.assertIn(".landing-page.theme-light", css)
        self.assertIn(".landing-page.theme-dark", css)


if __name__ == "__main__":
    unittest.main()

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LANDING = ROOT / "dashboard" / "src" / "Landing.jsx"
INDEX = ROOT / "dashboard" / "index.html"
PUBLIC = ROOT / "dashboard" / "public"
FAVICON = ROOT / "dashboard" / "public" / "favicon.svg"


class LandingBrandPolishTests(unittest.TestCase):
    def test_landing_uses_openshorts_brand_and_series_cta(self):
        landing = LANDING.read_text(encoding="utf-8")

        self.assertIn("OpenShorts", landing)
        self.assertIn("Собрать тестовую серию", landing)
        self.assertNotIn(">Контентфабрика<", landing)
        self.assertNotIn("'Контентфабрика:", landing)

    def test_product_cards_are_equal_grid_not_two_plus_one_layout(self):
        landing = LANDING.read_text(encoding="utf-8")

        self.assertIn("copy.productCards.map", landing)
        self.assertIn("md:grid-cols-3", landing)
        self.assertNotIn("copy.productCards.slice(0, 2)", landing)
        self.assertNotIn("lg:grid-cols-[1.1fr_0.9fr]", landing)

    def test_pipeline_uses_factory_line_visual_system(self):
        landing = LANDING.read_text(encoding="utf-8")

        self.assertIn("content-loop-map", landing)
        self.assertIn("content-loop-card", landing)
        self.assertIn("content-loop-return-lane", landing)
        self.assertIn("pipeline-node-pill", landing)
        self.assertNotIn("feedback-return-rail", landing)
        self.assertNotIn("pipeline-step-card", landing)
        self.assertNotIn("pipeline-station", landing)

    def test_logo_is_symbol_not_letter_monogram(self):
        favicon = FAVICON.read_text(encoding="utf-8")

        self.assertIn("playhead", favicon)
        self.assertIn("conveyor", favicon)
        self.assertNotIn("<text", favicon)
        self.assertNotIn("КФ", favicon)

    def test_simple_favicon_assets_are_used(self):
        landing = LANDING.read_text(encoding="utf-8")
        index = INDEX.read_text(encoding="utf-8")

        for filename in ["favicon-32.png", "favicon-192.png", "favicon-512.png"]:
            self.assertTrue((PUBLIC / filename).exists(), filename)

        self.assertIn("/favicon-192.png", landing)
        self.assertIn('/favicon-32.png', index)
        self.assertIn('/favicon-512.png', index)


if __name__ == "__main__":
    unittest.main()

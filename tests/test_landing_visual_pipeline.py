import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LANDING = ROOT / "dashboard" / "src" / "Landing.jsx"
CSS = ROOT / "dashboard" / "src" / "index.css"


class LandingVisualPipelineTests(unittest.TestCase):
    def test_landing_has_hero_product_mockup_and_grouped_pipeline_diagram(self):
        landing = LANDING.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")

        self.assertIn("HeroFactoryMockup", landing)
        self.assertIn("PipelineDiagram", landing)
        self.assertIn("pipelineGroups", landing)
        self.assertIn("idea", landing)
        self.assertIn("video", landing)
        self.assertIn("reaction", landing)
        self.assertIn("scroll-mt-24", landing)
        self.assertIn(".pipeline-diagram", css)
        self.assertIn("content-loop-map", landing)
        self.assertIn("content-loop-connector", landing)
        self.assertIn("content-loop-return-lane", landing)
        self.assertIn(".content-loop-map", css)
        self.assertIn(".content-loop-connector", css)
        self.assertIn(".content-loop-return-lane", css)

    def test_landing_uses_explicit_pipeline_scroll_handler(self):
        landing = LANDING.read_text(encoding="utf-8")

        self.assertIn("scrollToSection", landing)
        self.assertIn("event.preventDefault()", landing)
        self.assertIn("scrollIntoView", landing)
        self.assertIn("window.history.replaceState", landing)


if __name__ == "__main__":
    unittest.main()

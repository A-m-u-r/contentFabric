import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "dashboard" / "src" / "App.jsx"
UGC_GALLERY = ROOT / "dashboard" / "src" / "components" / "UGCGallery.jsx"
LANDING = ROOT / "dashboard" / "src" / "Landing.jsx"
SAAS_SHORTS = ROOT / "dashboard" / "src" / "components" / "SaaShortsTab.jsx"


class UILayoutPolishTests(unittest.TestCase):
    def test_app_shell_uses_mobile_bottom_navigation_instead_of_persistent_sidebar(self):
        app = APP.read_text(encoding="utf-8")

        self.assertIn("MobileTabBar", app)
        self.assertIn("hidden md:flex", app)
        self.assertIn("fixed inset-x-0 bottom-0", app)
        self.assertIn("mb-20", app)
        self.assertIn("md:mb-0", app)

    def test_sidebar_does_not_show_open_source_github_card(self):
        app = APP.read_text(encoding="utf-8")

        self.assertNotIn("https://github.com/mutonby/openshorts", app)
        self.assertNotIn(">Open Source<", app)

    def test_ugc_gallery_uses_responsive_content_grids(self):
        gallery = UGC_GALLERY.read_text(encoding="utf-8")

        self.assertIn("repeat(auto-fit,minmax(150px,1fr))", gallery)
        self.assertIn("repeat(auto-fit,minmax(120px,1fr))", gallery)
        self.assertIn("Генерация требует fal.ai", gallery)
        self.assertNotIn("text-red-300\">Для генерации нужен fal.ai", gallery)

    def test_video_modal_shows_lipsync_cost_estimate_and_compact_model_grid(self):
        gallery = UGC_GALLERY.read_text(encoding="utf-8")

        self.assertIn("pricePerMinute", gallery)
        self.assertIn("selectedLipSyncEstimate", gallery)
        self.assertIn("grid gap-2 md:grid-cols-3", gallery)
        self.assertIn("Примерно", gallery)

    def test_landing_primary_cta_avoids_multicolor_gradient_button(self):
        landing = LANDING.read_text(encoding="utf-8")

        self.assertNotIn("bg-gradient-to-r from-cyan-300 to-amber-200", landing)
        self.assertIn("text-balance", landing)
        self.assertIn("text-pretty", landing)

    def test_generated_scripts_can_be_edited_before_video_configuration(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("editingScriptIndex", tab)
        self.assertIn("handleSaveScriptDraft", tab)
        self.assertIn("Редактировать сценарий", tab)
        self.assertIn("Сохранить сценарий", tab)
        self.assertIn("draft.segments", tab)


    def test_ai_shorts_exposes_storyboard_v3_script_and_video_controls(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("SCRIPT_FORMAT_OPTIONS", tab)
        self.assertIn("storyboard_v3", tab)
        self.assertIn("handleScriptDraftShot", tab)
        self.assertIn("generation_prompt", tab)
        self.assertIn("storyboard_v3_pro", tab)
        self.assertIn("storyboard_veo31_quality", tab)
        self.assertIn("script_format", tab)
        self.assertIn("STORYBOARD_GENERATION_OPTIONS", tab)
        self.assertIn("storyboard_generation_mode", tab)

    def test_ai_shorts_exposes_ai_storyboard_format_selector_in_setup(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("Формат сценария", tab)
        self.assertIn("ИИ сгенерирует кадры, действия, текст на экране и промпты для выбранной видео-модели.", tab)
        self.assertNotIn('<div id="script-format-section" className="hidden">', tab)
        self.assertLess(tab.index("Источник сценария"), tab.index("Формат сценария"))
        self.assertLess(tab.index("Формат сценария"), tab.index("video-mode-section"))

    def test_ai_shorts_storyboard_setup_supports_business_profiles_and_frame_uploads(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("BUSINESS_PROFILES_KEY", tab)
        self.assertIn("handleSaveBusinessProfile", tab)
        self.assertIn("/api/user/business-profiles", tab)
        self.assertIn("handleStoryboardFrameUpload", tab)
        self.assertIn("/api/saasshorts/storyboard-frame-upload", tab)
        self.assertIn("script-format-section", tab)
        self.assertIn("video-mode-section", tab)
        self.assertLess(tab.index("script-format-section"), tab.index("video-mode-section"))
        self.assertNotIn("Website URL", tab)
        self.assertNotIn("https://your-website.com", tab)

    def test_ai_shorts_project_avatar_and_mode_copy_are_clear(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("AI-slop черновик", tab)
        self.assertIn("Основной режим для коротких UGC", tab)
        self.assertIn("дороже", tab)
        self.assertNotIn("Good baseline for tests and daily volume", tab)
        self.assertNotIn("Best choice when the video is going to publish", tab)
        self.assertIn("Количество вариантов сценария", tab)
        self.assertIn("Сейчас:", tab)
        self.assertIn("selectedBusinessProfileId", tab)
        self.assertIn("Библиотека проектов", tab)
        self.assertIn("Аватар проекта", tab)
        self.assertIn("Сохранённые аватары", tab)


if __name__ == "__main__":
    unittest.main()

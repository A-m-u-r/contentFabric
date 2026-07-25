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

        # Shots are edited in the single storyboard editor now — the separate
        # inline draft editor was merged away.
        self.assertIn("handleSelectedScriptShot", tab)
        self.assertIn("updateSelectedScriptShot", tab)
        self.assertIn("Раскадровка", tab)
        self.assertIn("Что в кадре", tab)


    def test_ai_shorts_exposes_storyboard_v3_script_and_video_controls(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("SCRIPT_FORMAT_OPTIONS", tab)
        self.assertIn("storyboard_v3", tab)
        self.assertIn("handleSelectedScriptShot", tab)
        self.assertIn("generation_prompt", tab)
        self.assertIn("storyboard_v3_pro", tab)
        self.assertIn("storyboard_veo31_quality", tab)
        self.assertIn("TEXT_MODEL_OPTIONS", tab)
        self.assertIn("Gemini 3.5 Flash", tab)
        self.assertIn("Gemini 3.1 Pro", tab)
        self.assertIn("text_model: textModel", tab)
        self.assertIn("script_format", tab)
        self.assertIn("STORYBOARD_GENERATION_OPTIONS", tab)
        self.assertIn("storyboard_generation_mode", tab)

    def test_storyboard_editor_can_generate_frames_before_paid_video(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Кадры генерируются/перегенерируются на шаге 2 без платного видео.
        self.assertIn("handleGenerateFrames", tab)
        self.assertIn("frames_only: true", tab)
        # Массовая кнопка платит только за недостающие кадры (готовые из
        # переоткрытой раскадровки уже оплачены в прошлой задаче).
        self.assertIn("Сгенерить недостающие", tab)
        self.assertIn("missingFrameCount", tab)
        self.assertIn("Перегенерить", tab)

    def test_finished_video_can_be_reshot_shot_by_shot(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        gallery = UGC_GALLERY.read_text(encoding="utf-8")

        # Галерея отдаёт джоб с оплаченными клипами, редактор — просит их переиспользовать.
        self.assertIn("job_id: video.job_id || jobIdFromVideoUrl(video.video_url)", gallery)
        self.assertIn("_source_job_id", tab)
        self.assertIn("source_job_id: sourceJobId || undefined", tab)
        self.assertIn("regenerate_shots: reshootShots", tab)
        # Кадр можно снять заново, даже если текст не менялся.
        self.assertIn("Переснять", tab)
        self.assertIn("Не переснимать", tab)
        # Смета честная: платим только за то, что снимается заново.
        self.assertIn("renderPlan", tab)
        self.assertIn("_render_baseline", tab)
        self.assertIn("narrationChanged", tab)
        # С экрана готового ролика можно вернуться в раскадровку и переснять кадр.
        self.assertIn("Переснять кадры", tab)

    def test_reshoot_price_is_one_number_across_the_screen(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Пустой список кадров оценщик читает как «сценария ещё нет» и выдаёт цену
        # типового ролика: плашка обещала $2.51 рядом с кнопкой «бесплатно».
        plan = tab[tab.index("const reshootEstimate"):tab.index("const reshootCost")]
        self.assertLess(plan.index("if (!renderPlan.reshoot.length)"), plan.index("estimateSaasVideoCost"))
        self.assertIn("total: 0, voiceCost: 0, videoCost: 0, brollCost: 0", plan)
        # Карточка сметы тоже показывает цену пересъёмки, а не полного ролика.
        self.assertIn("Стоимость пересъёмки", tab)
        self.assertIn("reshootEstimate ? reshootEstimate.total : estimate.total", tab)
        self.assertIn("пересборка бесплатна", tab)

    def test_shot_frame_preview_stays_a_thumbnail_on_narrow_screens(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Кадр 9:16 во всю ширину карточки давал 734x1306 px на каждый кадр и
        # растягивал раскадровку на 10 000 px — превью держим миниатюрой.
        self.assertIn("grid gap-3 sm:grid-cols-[120px,minmax(0,1fr)]", tab)
        self.assertNotIn("grid gap-3 lg:grid-cols-[120px,minmax(0,1fr)]", tab)
        self.assertIn('aspect-[9/16] w-[104px] shrink-0', tab)

    def test_avatar_and_voice_selection_live_on_setup_step(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Аватар + голос выбираются на шаге Setup (ДО платного превью кадров),
        # а не на шаге раскадровки. Модалка «Настройки аватара» убрана —
        # пол/загрузка/озвучка видны прямо в блоке ведущего.
        self.assertIn('data-section="presenter-section"', tab)
        self.assertIn("Движок озвучки", tab)
        self.assertIn("Голос озвучки", tab)
        self.assertIn("Аватар проекта", tab)
        self.assertIn("Сохранённые аватары", tab)
        # Раскладка модалки удалена вместе с её состоянием.
        self.assertNotIn("avatarSettingsOpen", tab)
        self.assertNotIn("setActorSource", tab)
        # Блок ведущего живёт в Setup — до раздела анализа (шаг 1).
        self.assertLess(tab.index('data-section="presenter-section"'), tab.index("Step 1: Analysis Results"))
        # …и после выбора видео-модели, но до перехода к раскадровке (шаг 2).
        self.assertLess(tab.index('data-section="video-mode-section"'), tab.index('data-section="presenter-section"'))
        self.assertLess(tab.index('data-section="presenter-section"'), tab.index("── Step 2: Configure"))

    def test_selected_voice_does_not_drift_between_generations(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Голос не должен «плавать»: раньше эффект брал ПЕРВЫЙ подходящий голос из
        # ElevenLabs-библиотеки (порядок библиотеки → разный голос между прогонами).
        # Теперь — детерминированный дефолт языка + ручной выбор не затирается.
        self.assertNotIn("sortVoicesForLanguage", tab)
        self.assertNotIn("const matchingVoice = sortVoicesForLanguage", tab)
        # Victoria остаётся утверждённым русским дефолтом.
        self.assertIn("D5RRIJYa9pFwxiSpbGbR", tab)
        # Ручной выбор уважается (не сбрасываем на смене пола/ремаунте).
        self.assertIn("уважаем ручной выбор", tab)

    def test_generated_frames_are_persisted_so_they_survive_reload(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # `scripts` перезагружаются из localStorage-кеша на маунте (loadCache),
        # поэтому мерж сгенерённых кадров ОБЯЗАН писать кеш — иначе после reload
        # preview_frame_url теряются и все превью «пропадают».
        apply = tab[tab.index("const applyGeneratedShots"):]
        apply = apply[:apply.index("\n  };")]
        self.assertIn("persistScripts(next)", apply)
        self.assertIn("preview_frame_url", apply)

    def test_quality_warnings_header_is_not_talking_head_specific(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # В `quality_warnings` падают и замечания vision-QC по b-roll-клипам
        # («Клип 2: деформация кисти»), поэтому шапка про синхронизацию
        # talking-head врала по смыслу.
        self.assertNotIn("Проверь синхронизацию talking-head", tab)
        self.assertIn("Замечания автопроверки", tab)
        self.assertIn("а не блокировка", tab)

    def test_presenter_block_collapses_into_one_summary_row(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Юзер терялся в блоке ведущего: пол, 9 плиток аватаров, загрузка,
        # движок озвучки, список голосов и ручной ID лежали одной простынёй.
        self.assertIn("avatarPickerOpen", tab)
        self.assertIn("voicePickerOpen", tab)
        self.assertIn("Сменить аватар", tab)
        self.assertIn("Сменить голос", tab)
        self.assertIn("selectedVoiceLabel", tab)
        self.assertIn("Ввести ID голоса вручную", tab)
        # Английские огрызки в русском UI убраны.
        self.assertNotIn("Custom ElevenLabs voice ID", tab)
        self.assertNotIn("Selected voice looks Russian-compatible", tab)

    def test_deleted_shots_are_archived_not_lost(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Удалённый кадр уносил с собой сгенерённый текст — вернуть было нечем.
        self.assertIn("shots_archived", tab)
        self.assertIn("restoreArchivedShot", tab)
        self.assertIn("Удалённые кадры", tab)
        # Undo должен откатывать и архив, иначе кадр задвоится.
        undo = tab[tab.index("const undoShotChange"):]
        self.assertIn("shots_archived: entry.archived", undo[:undo.index("\n  };")])

    def test_storyboard_of_a_finished_video_reopens_from_the_gallery(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        gallery = UGC_GALLERY.read_text(encoding="utf-8")

        self.assertIn("saasshorts_pending_storyboard", tab)
        self.assertIn("saasshorts_pending_storyboard", gallery)
        self.assertIn("Редактировать раскадровку", gallery)
        # Кадры, которые уже стоили денег, помечены в редакторе.
        self.assertIn("Кадр готов", tab)
        self.assertIn("Без кадра", tab)
        # Ключ читается в инициализаторе состояния: StrictMode гоняет
        # mount-эффекты дважды и «прочитал-и-удалил» потерял бы значение.
        self.assertIn("const [pendingStoryboard] = useState(() => {", tab)
        # Для роликов, снятых ДО архива удалённых кадров, единственная копия
        # вырезанного текста — full_narration; предлагаем вернуть его кадром.
        self.assertIn("leftoverNarration", tab)
        self.assertIn("Текст сценария вне кадров", tab)
        self.assertIn("addShotWithSpeech", tab)

    def test_restored_shots_get_scene_and_camera_filled_by_ai(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Кадр из архива несёт только реплику. Видео-модель читает промпт,
        # собранный из «Что в кадре», поэтому пустой кадр = случайная картинка.
        self.assertIn("/api/saasshorts/storyboard-shot-fill", tab)
        self.assertIn("fillShotDetails", tab)
        self.assertIn("Заполнить ИИ", tab)
        self.assertIn("emptyShotNumbers", tab)
        # Добавление кадра из остатка сценария сразу дозаполняет его.
        add = tab[tab.index("const addShotWithSpeech"):]
        self.assertIn("fillShotDetails", add[:add.index("\n  };")])

    def test_storyboard_duration_estimate_tracks_voiceover_not_a_flat_floor(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Длина ролика = длина озвучки (бэкенд режет `-shortest`), поэтому оценка
        # секунд не должна иметь плоского пола в 12с, который задваивал смету
        # коротких сценариев (~5с речи показывались как «~12 сек»).
        self.assertNotIn("Math.max(12, Math.min(75, Math.round(words / 2.5)))", tab)
        # Учитываем паузы/теги, чтобы оценка держалась не НИЖЕ реального аудио.
        self.assertIn("tags * 0.8 + pauses * 0.4", tab)
        # И явно поясняем, что видео не длиннее речи.
        self.assertIn("видео не длиннее речи", tab)

    def test_ai_shorts_exposes_ai_storyboard_format_selector_in_setup(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("Формат сценария", tab)
        self.assertIn("ИИ сгенерирует кадры, действия, текст на экране и промпты для выбранной видео-модели.", tab)
        self.assertNotIn('<div id="script-format-section" className="hidden">', tab)
        self.assertLess(tab.index("Источник сценария"), tab.index("Формат сценария"))
        self.assertLess(tab.index("Формат сценария"), tab.index("video-mode-section"))

    def test_ai_shorts_storyboard_setup_supports_business_profiles_and_frame_uploads(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("loadBusinessProfiles", tab)
        self.assertIn("saveBusinessProfiles", tab)
        self.assertIn("handleLoadBusinessProfile", tab)
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

        self.assertIn("Черновик (дёшево)", tab)
        self.assertIn("картинка может плыть и глючить", tab)
        self.assertIn("Оптимально по цене и качеству", tab)
        self.assertIn("дороже", tab)
        self.assertNotIn("Good baseline for tests and daily volume", tab)
        self.assertNotIn("Best choice when the video is going to publish", tab)
        self.assertIn("Количество вариантов сценария", tab)
        self.assertIn("Сейчас:", tab)
        self.assertIn("selectedBusinessProfileId", tab)
        self.assertIn("Управлять проектами", tab)
        self.assertIn("Аватар проекта", tab)
        self.assertIn("Сохранённые аватары", tab)


if __name__ == "__main__":
    unittest.main()

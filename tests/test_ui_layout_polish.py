import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "dashboard" / "src" / "App.jsx"
UGC_GALLERY = ROOT / "dashboard" / "src" / "components" / "UGCGallery.jsx"
LANDING = ROOT / "dashboard" / "src" / "Landing.jsx"
SAAS_SHORTS = ROOT / "dashboard" / "src" / "components" / "SaaShortsTab.jsx"
CONTENT_PLAN = ROOT / "dashboard" / "src" / "components" / "ContentPlanTab.jsx"
BUSINESS_PROFILES = ROOT / "dashboard" / "src" / "lib" / "businessProfiles.js"
CONTENT_PLAN_WORKSPACES = ROOT / "dashboard" / "src" / "lib" / "contentPlanWorkspaces.js"
SERVER = ROOT / "app.py"
PIPELINE = ROOT / "saasshorts.py"


class UILayoutPolishTests(unittest.TestCase):
    def test_content_plan_workspace_helpers_define_stable_local_contracts(self):
        workspaces = CONTENT_PLAN_WORKSPACES.read_text(encoding="utf-8")

        self.assertIn("export function ensurePlanItemIds(items)", workspaces)
        self.assertIn("export function workspaceStorageKey(context)", workspaces)
        self.assertIn("encodeURIComponent(profileId)", workspaces)
        self.assertIn("encodeURIComponent(itemId)", workspaces)
        self.assertIn("export function loadLocalWorkspace(context)", workspaces)
        self.assertIn("export function saveLocalWorkspace(context, snapshot)", workspaces)
        self.assertIn("export function chooseNewestWorkspace(local, remote)", workspaces)
        self.assertIn("export function workspaceStage(snapshot)", workspaces)
        self.assertIn("revision: nextRevision", workspaces)
        self.assertIn("updatedAt", workspaces)
        self.assertIn("not_started", workspaces)
        self.assertIn("frames", workspaces)
        self.assertIn("video", workspaces)
        self.assertIn("failed", workspaces)

    def test_content_plan_workspace_helpers_preserve_numeric_ids_and_prioritize_failures(self):
        workspaces = CONTENT_PLAN_WORKSPACES.read_text(encoding="utf-8")
        tab = CONTENT_PLAN.read_text(encoding="utf-8")

        self.assertIn("typeof item?.item_id === 'number'", workspaces)
        self.assertIn("item_id: String(item.item_id)", workspaces)
        self.assertIn("snapshot?.scripts?.some((script) => hasFrameUrl(script?.shots))", workspaces)
        self.assertIn("const existingItem = items.find((item) => item.item_id === key);", tab)
        self.assertLess(
            workspaces.index("if (hasFailedGeneration(snapshot))"),
            workspaces.index("if (\n    hasText(snapshot?.result?.video_url)"),
        )

    def test_content_plan_uses_item_scoped_identity_and_workspace_hydration(self):
        tab = CONTENT_PLAN.read_text(encoding="utf-8")

        self.assertIn("ensurePlanItemIds", tab)
        self.assertIn("item.item_id", tab)
        self.assertIn("key={item.item_id}", tab)
        self.assertNotIn("key={i}", tab)
        self.assertIn("/api/user/content-workspaces?profile_id=", tab)
        self.assertIn("/api/user/content-workspaces/${encodeURIComponent(selectedId)}/${encodeURIComponent(item.item_id)}", tab)
        self.assertIn("chooseNewestWorkspace(localWorkspace, remoteWorkspace)", tab)
        self.assertIn("setOpeningItemId(item.item_id)", tab)
        self.assertIn("openingItemId === item.item_id", tab)
        self.assertIn("Не начат", tab)
        self.assertIn("Сценарий", tab)
        self.assertIn("Кадры", tab)
        self.assertIn("Видео", tab)
        self.assertIn("Ошибка", tab)

    def test_content_plan_merges_local_workspace_badges_and_uses_utf8_russian_labels(self):
        tab = CONTENT_PLAN.read_text(encoding="utf-8")

        self.assertIn("const localWorkspace = loadLocalWorkspace({ profileId: selectedId, itemId: item.item_id, item });", tab)
        self.assertIn("chooseNewestWorkspace(localWorkspace, workspaceSummaries[item.item_id])", tab)
        self.assertIn("not_started: 'Не начат'", tab)
        self.assertIn("script: 'Сценарий'", tab)
        self.assertIn("frames: 'Кадры'", tab)
        self.assertIn("video: 'Видео'", tab)
        self.assertIn("failed: 'Ошибка'", tab)

    def test_content_plan_sets_structured_pending_context_without_removing_legacy_topic(self):
        profiles = BUSINESS_PROFILES.read_text(encoding="utf-8")
        tab = CONTENT_PLAN.read_text(encoding="utf-8")

        self.assertIn("export function setPendingContentPlanItem(context)", profiles)
        self.assertIn("export function peekPendingContentPlanItem()", profiles)
        self.assertIn("export function clearPendingContentPlanItem()", profiles)
        self.assertIn("setPendingContentPlanItem", tab)
        self.assertIn("setPendingTopic(topic)", tab)

    def test_ai_shorts_resolves_active_workspace_before_one_shared_initial_cache(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("peekPendingContentPlanItem", tab)
        self.assertIn("clearPendingContentPlanItem", tab)
        self.assertIn("loadActiveContentPlanContext", tab)
        self.assertIn("saveActiveContentPlanContext", tab)
        self.assertIn("const pendingContentPlanContext = peekPendingContentPlanItem();", tab)
        self.assertIn(
            "const activeContentPlanContext = pendingContentPlanContext || loadActiveContentPlanContext();",
            tab,
        )
        self.assertIn("const activeWorkspaceKey = activeContentPlanContext", tab)
        self.assertIn("const [initialCache] = useState(() => (", tab)
        self.assertLess(
            tab.index("const activeWorkspaceKey = activeContentPlanContext"),
            tab.index("const [step, setStep] = useState"),
        )
        initializer_block = tab[
            tab.index("export default function SaaShortsTab"):tab.index("// Pre-fill from cache on mount")
        ]
        self.assertNotIn("loadCache()?.", initializer_block)

    def test_ai_shorts_restores_workspace_progress_and_scopes_last_job(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("function loadCache(cacheKey = CACHE_KEY)", tab)
        self.assertIn("function saveCache(cacheKey, input, analysis, webResearch, scripts, progress = {})", tab)
        self.assertIn("function workspaceLastJobKey(cacheKey)", tab)
        self.assertIn("function loadLastJob(cacheKey)", tab)
        self.assertIn("function saveLastJob(cacheKey, jobId)", tab)
        self.assertIn("function clearLastJob(cacheKey)", tab)
        self.assertIn("loadLastJob(activeWorkspaceKey)", tab)
        self.assertIn("saveLastJob(activeWorkspaceKey, data.job_id)", tab)
        self.assertIn("workspaceStep(initialCache)", tab)
        self.assertIn("initialCache?.selectedScript", tab)
        self.assertIn("initialCache?.editedNarration", tab)
        self.assertIn("initialCache?.jobId", tab)
        self.assertIn("initialCache?.genStatus", tab)
        self.assertIn("initialCache?.genResult", tab)

    def test_ai_shorts_queues_authenticated_workspace_sync_and_flushes_on_unmount(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("function queueWorkspaceSync", tab)
        self.assertIn("workspaceSyncTimerRef.current = setTimeout(flushWorkspaceSync, 400);", tab)
        self.assertIn("latestWorkspaceSnapshotRef", tab)
        self.assertIn("keepalive: true", tab)
        self.assertIn(
            "/api/user/content-workspaces/${encodeURIComponent(profileId)}/${encodeURIComponent(itemId)}",
            tab,
        )
        self.assertIn("method: 'PUT'", tab)
        self.assertIn("revision: snapshot.revision", tab)
        self.assertIn("stage: workspaceStage(snapshot)", tab)
        self.assertIn("chooseNewestWorkspace(localWorkspace, remoteWorkspace)", tab)
        self.assertIn("if (!authToken || !activeContentPlanContext) return;", tab)
        self.assertIn("const [workspaceHydrationVersion, setWorkspaceHydrationVersion] = useState(0);", tab)
        persistence_effect = tab[
            tab.index("useEffect(() => {\n    if (workspaceResettingRef.current)"):
            tab.index("useEffect(() => () => {")
        ]
        self.assertIn("workspaceHydrationVersion,", persistence_effect)

    def test_ai_shorts_persists_item_progress_and_resets_only_the_active_workspace(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        workspaces = CONTENT_PLAN_WORKSPACES.read_text(encoding="utf-8")

        self.assertIn("saveLocalWorkspace(activeContentPlanContext, snapshot)", tab)
        self.assertIn("version: CACHE_VERSION", tab)
        self.assertIn("selectedScript,", tab)
        self.assertIn("editedNarration,", tab)
        self.assertIn("jobId,", tab)
        self.assertIn("genStatus,", tab)
        self.assertIn("genResult,", tab)
        self.assertIn("localStorage.removeItem(activeWorkspaceKey)", tab)
        self.assertIn("clearLastJob(activeWorkspaceKey)", tab)
        self.assertIn("clearActiveContentPlanContext()", tab)
        self.assertIn("method: 'DELETE'", tab)
        self.assertIn("if (authToken && activeContentPlanContext)", tab)
        self.assertIn("explicitStage !== 'not_started'", workspaces)

    def test_ai_shorts_reset_deactivates_item_context_before_blank_state_persists(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        reset = tab[tab.index("const handleReset = () => {"):tab.index("const estimateInputText")]

        self.assertIn("const [workspaceContextState, setWorkspaceContextState] = useState", tab)
        self.assertIn("const workspaceResettingRef = useRef(false);", tab)
        self.assertIn("if (workspaceResettingRef.current) {", tab)
        self.assertIn("workspaceResettingRef.current = false;", tab)
        self.assertIn("latestWorkspaceSnapshotRef.current = null;", reset)
        self.assertIn("workspaceResettingRef.current = true;", reset)
        self.assertIn("localStorage.removeItem(activeWorkspaceKey)", reset)
        self.assertIn("clearActiveContentPlanContext();", reset)
        self.assertIn("setWorkspaceContextState({", reset)
        self.assertIn("activeContentPlanContext: null", reset)
        self.assertLess(
            reset.index("setWorkspaceContextState({"),
            reset.index("setStep(0)"),
        )
        self.assertNotIn("saveLocalWorkspace(", reset)

    def test_content_workspace_snapshot_topic_wins_over_context_with_nullish_fallback(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        workspaces = CONTENT_PLAN_WORKSPACES.read_text(encoding="utf-8")

        self.assertIn("topic: snapshot.topic ?? context?.topic ?? '',", workspaces)
        self.assertIn("setTopic(snapshot.topic ?? activeContentPlanContext?.topic", tab)
        self.assertIn("topic: topic.trim(),", tab)

    def test_ai_shorts_uses_shared_progress_step_fallback_for_initial_and_remote_workspaces(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("function workspaceStep(snapshot)", tab)
        self.assertIn("const [step, setStep] = useState(() => workspaceStep(initialCache));", tab)
        self.assertIn("if (restoreStep) setStep(workspaceStep(snapshot));", tab)

    def test_generation_and_result_steps_survive_a_reload(self):
        """Шаги «идёт генерация» и «готовый ролик» восстанавливаются из снапшота.

        Обрезка до шага 2 отнимала у пользователя логи уже запущенной генерации и
        экран результата уже оплаченного рендера: и jobId, и genResult лежат в
        снапшоте, возвращать на раскадровку не из чего.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        step_fn = tab[tab.index("function workspaceStep(snapshot)"):tab.index("export default function SaaShortsTab")]

        self.assertIn("if (desired >= 4) return snapshot?.genResult ? 4 : editorStep;", step_fn)
        self.assertIn("if (desired === 3) return snapshot?.jobId ? 3 : editorStep;", step_fn)
        self.assertNotIn("Math.min(desired, 2)", step_fn)

    def test_frame_preview_reports_a_run_that_drew_nothing(self):
        """«Прошло, но ничего не изменилось» — это отброшенный пустой кадр.

        Джоб превью завершается успешно и с нулём кадров: модель вернула пустое
        изображение, его выбросили. Молчать об этом нельзя — иначе пользователь
        видит ту же картинку и считает, что сломан интерфейс.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("const [framesNotice, setFramesNotice] = useState('');", tab)
        self.assertIn("const framesMade = Number(data.result?.frames_made ?? 0);", tab)
        self.assertIn("const framesFailed = Number(data.result?.frames_failed ?? 0);", tab)
        self.assertIn("{framesNotice && (", tab)

    def test_regenerated_frame_is_not_served_from_browser_cache(self):
        """Ракурс общий, имя файла не меняется — без метки кэш покажет старый кадр."""
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("const bust = result?.frames_only ? `?v=${Date.now()}` : '';", tab)
        self.assertIn("image_preview: g.local_url ? `${getApiUrl(g.local_url)}${bust}` : shot.image_preview,", tab)

    def test_ai_shorts_applies_remote_put_winner_and_replaces_stale_sync_snapshot(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        put_response = tab[
            tab.index("function flushWorkspaceSync()"):
            tab.index("function queueWorkspaceSync")
        ]

        self.assertIn("const saved = saveLocalWorkspace(activeContentPlanContext, remoteWorkspace);", put_response)
        self.assertIn("latestWorkspaceSnapshotRef.current = saved;", put_response)
        self.assertIn("applyWorkspaceSnapshot(saved, { restoreStep: false });", put_response)
        self.assertIn("setWorkspaceHydrationVersion((version) => version + 1);", put_response)

    def test_workspace_sync_ignores_the_echo_of_its_own_put(self):
        """Автосохранение не должно зацикливаться на собственном ответе сервера.

        PUT возвращает ту же ревизию со своим updated_at (всегда чуть позже
        нашего), поэтому «свежее победило» принимало эхо за чужую запись,
        раскладывало его по состоянию и дёргало workspaceHydrationVersion — а он
        стоит в зависимостях эффекта сохранения. Круг: PUT → apply → PUT.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        put_response = tab[
            tab.index("function flushWorkspaceSync()"):
            tab.index("function queueWorkspaceSync")
        ]

        self.assertIn(
            "if (Number(data.workspace.revision) <= Number(snapshot.revision || 0)) return;",
            put_response,
        )
        self.assertLess(
            put_response.index("if (Number(data.workspace.revision)"),
            put_response.index("const remoteWorkspace = {"),
        )

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
        self.assertNotIn("STORYBOARD_PACING_OPTIONS", tab)
        self.assertNotIn("storyboard_pacing: storyboardPacing", tab)
        # Плиты рисуются по числу камер, а не по числу говорящих кадров, а
        # перебивка стоит не меньше пола Kling — смета должна знать и то, и другое.
        self.assertIn("Math.min(talkingShots, TALKING_PLATE_COUNT) * FLUX_FRAME_COST", tab)
        self.assertIn("BROLL_MIN_CLIP_SECONDS", tab)

    def test_a_shot_too_short_for_its_clip_says_so_before_the_money_is_spent(self):
        """Реплика короче пола модели — единственный перерасход, невидимый глазом.

        Кадр на полторы секунды выглядит в редакторе ровно как кадр на три:
        поля «длительность» нет, длину задаёт озвучка. А снимут и посчитают
        минимум модели. Узнавать об этом по отчёту после оплаты — поздно.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("shotIsShorterThanItsClip", tab)
        self.assertIn("shotClipFloorSeconds", tab)
        self.assertIn("платим за полный", tab)
        # Предупреждение и смета обязаны мерить кадр одинаково: разойдись они, и
        # редактор будет спорить сам с собой на той же раскадровке.
        self.assertIn("const share = shotPlannedSeconds(script, shot, totalSeconds);", tab)

    def test_generation_steps_ask_about_the_storyboard_before_the_lipsync(self):
        """Иначе галочки не загорались бы весь прогон.

        Раскадровка пишет построчно «создаю новое lip-sync видео Kling Avatar»,
        так что `isLipSyncJob` истинно и у неё. Подписи этапов берутся от
        раскадровки, и состояние обязано спрашивать в том же порядке — иначе оно
        ищет маркеры `[lipsync N/3]`, которых раскадровочная задача не печатает.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        for binding in ("const labels = isStoryboardJob",
                        "const stepDone = isStoryboardJob",
                        "const stepActive = isStoryboardJob"):
            self.assertIn(binding, tab)
            self.assertNotIn(binding.replace("isStoryboardJob", "isLipSyncJob"), tab)

    def test_ai_shorts_exposes_and_persists_target_duration_presets(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("TARGET_DURATION_OPTIONS", tab)
        for value in ("15", "20", "30", "45"):
            self.assertIn(f"value: {value}", tab)
        self.assertIn(
            "const [targetDurationSeconds, setTargetDurationSeconds]",
            tab,
        )
        self.assertIn("initialCache?.targetDurationSeconds || 20", tab)
        self.assertIn(
            "targetDurationSeconds: snapshot.targetDurationSeconds",
            tab,
        )
        self.assertIn(
            "target_duration_seconds: targetDurationSeconds",
            tab,
        )
        self.assertIn("fallbackSeconds: targetDurationSeconds", tab)
        self.assertIn("fallbackSeconds = TYPICAL_VIDEO_SECONDS", tab)
        self.assertIn('role="group"', tab)
        self.assertIn('aria-labelledby="target-duration-label"', tab)
        self.assertIn("Длина ролика", tab)
        self.assertIn("Применяется ко всем вариантам сценария", tab)

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

    def test_render_starts_from_the_frames_the_user_approved(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Кадр кэшируется по промпту, но внутри папки своего джоба. Без ссылки на
        # джоб предпросмотра рендер рисовал заново ровно те кадры, которые
        # пользователь только что одобрил: второй счёт и другой сэмпл.
        self.assertIn("_frames_job_id", tab)
        self.assertIn("frames_job_id: framesJobId || undefined", tab)
        self.assertIn("applyGeneratedShots(data.result, { frames: framesJobId })", tab)

    def test_voiceover_can_be_heard_and_re_recorded_before_paid_video(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Дорожка задаёт длину ролика, границы кадров и число платных клипов,
        # поэтому её слушают до съёмки, а не после.
        self.assertIn("handleGenerateVoice", tab)
        self.assertIn("voice_only: true", tab)
        self.assertIn("Записать озвучку", tab)
        # Перезапись одной реплики и перечитывание всего текста одним дублем.
        self.assertIn("revoice_shots: shotNumber ? [shotNumber] : []", tab)
        self.assertIn("Перечитать всё одним дублем", tab)
        # Плеер на дорожку целиком и на каждую реплику отдельно.
        self.assertIn("voicePreview.url", tab)
        self.assertIn("getApiUrl(shot.voice_url)", tab)

    def test_render_uses_the_take_the_user_approved(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Дубль каждый раз новый: без ссылки на прослушанный джоб рендер записал
        # бы другой и залипсинчил кадры под звук, которого никто не слышал.
        self.assertIn("_voice_job_id", tab)
        self.assertIn("voice_job_id: voiceJobId || undefined", tab)
        self.assertIn("applyGeneratedShots(data.result, { voice: newVoiceJobId })", tab)
        # Правка реплики после записи должна быть видна, а не всплывать в ролике.
        self.assertIn("текст изменился после записи", tab)

    def test_deleted_shots_come_back_where_they_were(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Раскадровку разбирают, чтобы отрендерить один кадр на пробу. Место
        # кадра держит ключ порядка, а не индекс на момент удаления: индекс верен
        # только при строго обратном возврате, а кнопка «Вернуть» стоит у каждого
        # кадра — и возврат сверху вниз переворачивал блок (03.08, saas_c079a7dc).
        self.assertIn("const withShotOrder", tab)
        self.assertIn("const archivedShotSlot", tab)
        self.assertNotIn("_archived_at: shotIndex", tab)
        slot = tab[tab.index("const archivedShotSlot"):tab.index("const restoredShot")]
        self.assertIn("s._ord > shot._ord", slot)
        # Старые архивы ключа не носят — для них остаётся прежний путь.
        self.assertIn("shot._archived_at", slot)
        self.assertIn("restoreAllArchivedShots", tab)
        self.assertIn("Вернуть все", tab)
        restore_all = tab[tab.index("const restoreAllArchivedShots"):tab.index("const dropArchivedShot")]
        self.assertIn("for (let i = archived.length - 1; i >= 0; i -= 1)", restore_all)

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
        # Речь сравнивается покадрово: озвучка теперь нарезана на куски по кадру,
        # поэтому правка одной реплики больше не пересчитывает весь ролик.
        self.assertIn("const speechChanged", tab)
        self.assertIn("revoicedText", tab)
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

    def test_manual_voice_survives_actor_click_and_is_auditable(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        gallery = UGC_GALLERY.read_text(encoding="utf-8")

        self.assertIn("voiceSelectionSource", tab)
        self.assertIn("voiceSelectionSource !== 'manual'", tab)
        self.assertIn("voice_name: selectedVoiceLabel", tab)
        self.assertIn("voice_selection_source: voiceSelectionSource", tab)
        self.assertIn("loadVideoPrefs(activeWorkspaceKey)", tab)
        self.assertIn("выбран вручную и не заменён привязкой аватара", tab)
        self.assertIn("video.voice_name", gallery)
        self.assertIn("video.voice_model", gallery)

    def test_project_voice_prefs_never_fall_back_to_the_global_project(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")
        loader = tab[tab.index("function loadVideoPrefs"):tab.index("function saveVideoPrefs")]

        self.assertIn("workspaceVideoPrefsKey(cacheKey)", loader)
        self.assertNotIn("localStorage.getItem(VIDEO_PREFS_KEY)", loader)

    def test_generation_logs_distinguish_cached_frames_from_new_video(self):
        server = SERVER.read_text(encoding="utf-8")
        pipeline = PIPELINE.read_text(encoding="utf-8")

        self.assertNotIn('"logs": ["AI Shorts job started."]', server)
        self.assertIn("Задача AI Shorts поставлена в очередь", server)
        self.assertIn("Стартовый PNG взят из предпросмотра", pipeline)
        self.assertIn("создаю новое видео", pipeline)
        self.assertIn("создаю новое lip-sync видео", pipeline)
        self.assertIn("Кадр {job['shot_number']}", pipeline)

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

    def test_the_reel_set_is_its_own_field_above_the_shots(self):
        """Место действия — свойство сценария, а не текст, спрятанный в кадре 1.

        Пока оно жило внутри кадра, туда писали и камеру, и позу, и внешность —
        и всё это уезжало в плиты вместе с комнатой.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("/api/saasshorts/storyboard-set", tab)
        self.assertIn("pickReelSet", tab)
        self.assertIn("Место действия ролика", tab)
        self.assertIn("Подобрать ИИ", tab)
        self.assertIn("set_prompt", tab)
        # Карточка стоит до списка кадров.
        self.assertLess(tab.index("Место действия ролика"), tab.index("Добавить кадр"))
        # У сценариев со своим полем кадр 1 перестаёт быть «тем самым», у старых
        # остаётся: подпись обязана говорить правду про обе схемы.
        self.assertIn("shotIndex === setDefiningShotIndex && !hasOwnSet", tab)
        self.assertIn("Место — из поля «Место действия ролика» выше", tab)

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

    def test_script_cards_always_show_narration_derived_duration(self):
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertNotIn("script.duration_seconds || estimateStoryboardSeconds", tab)
        self.assertIn("estimateStoryboardSeconds(script, script.full_narration || '')", tab)

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

    def test_wizard_steps_can_be_walked_forward_again_after_going_back(self):
        """Уйдя назад в настройку, к своему готовому ролику можно вернуться.

        Раньше «назад» существовало кнопками в подвалах, а «вперёд» — нет: логи и
        результат оплаченного рендера лежали в снапшоте, но открыть их было нечем.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("const stepReady = [", tab)
        self.assertIn("const previousReadyStep =", tab)
        self.assertIn("const nextReadyStep =", tab)
        self.assertIn("setStep(nextReadyStep)", tab)
        self.assertIn("setStep(previousReadyStep)", tab)
        self.assertIn('aria-label="Вперёд"', tab)
        self.assertIn('aria-label="Назад"', tab)
        # Шаг без данных отрисуется пустым, поэтому переход в него закрыт.
        self.assertIn("disabled={!stepReady[i] || i === step}", tab)
        self.assertIn("пока нечего показать", tab)

    def test_storyboard_flags_a_duration_that_missed_the_target(self):
        """«Выбрал 15 секунд — сгенерилось на 24» должно быть видно до рендера.

        Допуск и оценка те же, что на бэкенде, и пересчитываются на каждой правке
        кадров: длину ролика задаёт озвучка, поэтому лишний текст — это лишние
        секунды и лишние оплаченные кадры.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        self.assertIn("const durationGap =", tab)
        self.assertIn("Math.abs(storyboardSeconds - targetDurationSeconds) > 2", tab)
        self.assertIn("{durationGap !== 0 && (", tab)
        self.assertIn("длиннее", tab)
        self.assertIn("короче", tab)

    def test_storyboard_says_who_owns_the_place_and_the_camera(self):
        """Раскадровка перестаёт обещать то, чего снимающий код не делает.

        Говорящие кадры снимаются в одном месте (его задаёт первый из них), а
        ракурсы чередует сборка. Пока это было невидимо, поле «Что в кадре»
        заполнялось текстом вида «та же комната, ракурс чуть сменился» — и не
        менялось ничего, кроме ожиданий.
        """
        tab = SAAS_SHORTS.read_text(encoding="utf-8")

        # Очередь камер — та же, что на бэкенде: шёпот всегда доверительный крупный.
        self.assertIn("const talkingCameras = (() => {", tab)
        self.assertIn("isWhisperShot(shot)", tab)
        self.assertIn("order % 2 === 0 ? 'front' : 'side'", tab)
        self.assertIn("Камера: {CAMERA_LABELS[talkingCameras[shotIndex]]}", tab)
        # Место действия принадлежит одному кадру, а не каждому.
        self.assertIn("const setDefiningShotIndex =", tab)
        self.assertIn("место действия всего ролика", tab)
        self.assertIn("Поза, взгляд, что делают руки", tab)
        self.assertIn("новую комнату или", tab)

    def test_talking_shots_are_told_to_describe_the_moment_not_the_room(self):
        """То же правило — в промптах моделей, иначе они пишут про камеру.

        Модель сочиняла «ракурс чуть сменился» и новую комнату на каждый кадр,
        хотя до картинки доходит одно место действия на весь ролик. Теперь это
        правило живёт там, где кадр рисуется: в проходе по картинкам и в
        дозаполнении полей по реплике.
        """
        pipeline = PIPELINE.read_text(encoding="utf-8")

        self.assertIn("ALL talking shots happen in ONE place", pipeline)
        self.assertIn("The place is already chosen and is NOT yours", pipeline)
        self.assertIn("`scene` is the MOMENT", pipeline)
        self.assertIn("the app stages the talking shots itself and rotates its own cameras",
                      pipeline)
        # И в дозаполнении полей по реплике — оно ходит тем же путём.
        self.assertIn("ALL talking shots happen in ONE place, the one the first talking shot above is", pipeline)


if __name__ == "__main__":
    unittest.main()

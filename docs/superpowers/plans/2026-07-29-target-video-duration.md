# Target Video Duration Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add approximate 15, 20, 30, and 45-second script-generation presets to the first AI Shorts screen.

**Architecture:** Carry one normalized integer `target_duration_seconds` from the React setup screen through FastAPI into `generate_scripts`. A single helper produces the prompt-only duration, word-budget, UGC timeline, and storyboard shot-count instructions. Narration-derived `duration_seconds` remains authoritative after generation.

**Tech Stack:** Python, FastAPI/Pydantic, unittest, React/Vite, existing workspace snapshots.

## Global Constraints

- Duration is controlled only through the Gemini prompt.
- Do not retry, reject, trim, pad, or rewrite a script because of duration.
- Supported targets are exactly 15, 20, 30, and 45; default to 20.
- One selected target applies to every script in a generation batch.
- Custom scripts remain byte-for-byte unchanged.
- Keep the existing maximum of three paid storyboard B-roll clips.
- Do not call Gemini, fal.ai, ElevenLabs, or any other paid provider in tests.

---

### Task 1: Backend Duration Prompt Contract

**Files:**
- Modify: `saasshorts.py`
- Test: `tests/test_saasshorts_storyboard.py`

**Interfaces:**
- Produces: `normalize_target_duration(value: object, default: int = 20) -> int`
- Produces: `_target_duration_prompt(target: int, storyboard: bool) -> str`
- Changes: `generate_scripts(..., target_duration_seconds: int = 20) -> list`

- [ ] **Step 1: Write failing normalization and prompt tests**

Add tests to `SaaSStoryboardTests` that assert:

```python
def test_target_duration_normalizes_supported_presets_and_falls_back_to_twenty(self):
    for value in (15, 20, 30, 45):
        self.assertEqual(saasshorts.normalize_target_duration(value), value)
    self.assertEqual(saasshorts.normalize_target_duration("45"), 45)
    self.assertEqual(saasshorts.normalize_target_duration(29), 20)
    self.assertEqual(saasshorts.normalize_target_duration(None), 20)

def test_storyboard_duration_prompt_uses_selected_target_only(self):
    answer = _storyboard_answer("Thirty", 12)
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=answer)
    with patch("google.genai.Client", return_value=client), \
         patch(
             "saasshorts.refine_storyboard_broll_alignment",
             side_effect=lambda scripts, *_args, **_kwargs: scripts,
         ):
        scripts = saasshorts.generate_scripts(
            analysis={"product_name": "Test"},
            gemini_key="key",
            num_scripts=1,
            script_format="storyboard_v3",
            target_duration_seconds=30,
        )
    prompt = client.models.generate_content.call_args.kwargs["contents"][0]
    self.assertIn("28-32 seconds", prompt)
    self.assertIn("59-63 spoken words", prompt)
    self.assertIn("11-15 visual beats", prompt)
    self.assertNotIn("18-22 seconds total", prompt)
    self.assertEqual(scripts[0]["target_duration_seconds"], 30)
```

Add a second mocked generation test for `script_format="ugc"` and target 45:

```python
self.assertIn("43-47 seconds", prompt)
self.assertIn("92-96 spoken words", prompt)
self.assertIn("five segments", prompt.casefold())
self.assertEqual(scripts[0]["target_duration_seconds"], 45)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
docker compose exec -T -e PYTHONPATH=/app backend python -m unittest tests.test_saasshorts_storyboard.SaaSStoryboardTests
```

Expected: failures because `normalize_target_duration` and the new argument do not exist.

- [ ] **Step 3: Add the duration preset helper**

Add near the storyboard pacing constants:

```python
TARGET_VIDEO_DURATION_DEFAULT = 20
TARGET_VIDEO_DURATION_PRESETS = {
    15: {"minimum": 13, "maximum": 17, "words": "26-30", "beats": "6-8"},
    20: {"minimum": 18, "maximum": 22, "words": "37-41", "beats": "8-10"},
    30: {"minimum": 28, "maximum": 32, "words": "59-63", "beats": "11-15"},
    45: {"minimum": 43, "maximum": 47, "words": "92-96", "beats": "16-22"},
}

def normalize_target_duration(value, default=TARGET_VIDEO_DURATION_DEFAULT):
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return normalized if normalized in TARGET_VIDEO_DURATION_PRESETS else default
```

Implement `_target_duration_prompt` so both formats receive the same target and word budget. For storyboard, append the selected visual-beat count and repeat the three-B-roll ceiling. For UGC, state that all five segment narrations together must fit the word budget.

- [ ] **Step 4: Thread the target through `generate_scripts`**

Add:

```python
target_duration_seconds: int = TARGET_VIDEO_DURATION_DEFAULT
```

Normalize it once before choosing the UGC/storyboard prompt. Inject `_target_duration_prompt(...)` into both prompts. Replace hard-coded UGC `18-22` language and fixed sample duration with the selected values.

Use five evenly distributed illustrative segment bounds:

```python
bounds = [round(target_duration_seconds * index / 5) for index in range(6)]
```

After parsing an AI-generated script, store:

```python
script["target_duration_seconds"] = target_duration_seconds
```

Do this before or after `_finalize_generated_script`; never overwrite its narration-derived `duration_seconds`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Task 1 command again. Expected: all `SaaSStoryboardTests` pass and Gemini remains mocked.

---

### Task 2: FastAPI Propagation And Custom-Script Boundary

**Files:**
- Modify: `app.py`
- Test: `tests/test_saasshorts_storyboard.py`

**Interfaces:**
- Consumes: `generate_scripts(..., target_duration_seconds: int)`
- Produces: `SaaSAnalyzeRequest.target_duration_seconds: int = 20`

- [ ] **Step 1: Write failing API propagation tests**

Extend `SaaSAnalyzePacingContractTests`:

```python
def test_analyze_request_defaults_target_duration_to_twenty(self):
    import app
    self.assertEqual(app.SaaSAnalyzeRequest(description="Test").target_duration_seconds, 20)

def test_analyze_request_passes_target_duration_to_ai_generation(self):
    import app
    request = app.SaaSAnalyzeRequest(
        description="Test product",
        script_format="storyboard_v3",
        target_duration_seconds=45,
    )
    with patch("app.resolve_effective_api_key", return_value="key"), \
         patch("app.generate_scripts", return_value=[]) as generate:
        asyncio.run(app.saasshorts_analyze(
            request,
            x_gemini_key="key",
            authorization=None,
        ))
    self.assertEqual(generate.call_args.kwargs["target_duration_seconds"], 45)
```

Add a custom-script test that posts `target_duration_seconds=15` and asserts the returned custom narration is unchanged and has no duration-based trimming.

- [ ] **Step 2: Run the API contract tests and verify RED**

Run:

```powershell
docker compose exec -T -e PYTHONPATH=/app backend python -m unittest tests.test_saasshorts_storyboard.SaaSAnalyzePacingContractTests
```

Expected: field/propagation assertions fail.

- [ ] **Step 3: Implement the FastAPI field and AI-only propagation**

Add to `SaaSAnalyzeRequest`:

```python
target_duration_seconds: int = 20
```

Pass it to both AI `generate_scripts` calls:

```python
target_duration_seconds=req.target_duration_seconds,
```

Do not pass it to `build_custom_script`, because the custom-script path must not imply that the user text was fitted to a target.

- [ ] **Step 4: Run API tests and verify GREEN**

Run the Task 2 command. Expected: all contract tests pass.

---

### Task 3: First-Screen Duration Control And Persistence

**Files:**
- Modify: `dashboard/src/components/SaaShortsTab.jsx`
- Test: `tests/test_ui_layout_polish.py`

**Interfaces:**
- Produces: `targetDurationSeconds` React state with default `20`
- Sends: `target_duration_seconds: targetDurationSeconds`

- [ ] **Step 1: Write a failing frontend source-contract test**

Add:

```python
def test_ai_shorts_exposes_and_persists_target_duration_presets(self):
    tab = SAAS_SHORTS.read_text(encoding="utf-8")
    self.assertIn("TARGET_DURATION_OPTIONS", tab)
    for value in ("15", "20", "30", "45"):
        self.assertIn(f"value: {value}", tab)
    self.assertIn("const [targetDurationSeconds, setTargetDurationSeconds]", tab)
    self.assertIn("initialCache?.targetDurationSeconds || 20", tab)
    self.assertIn("targetDurationSeconds: snapshot.targetDurationSeconds", tab)
    self.assertIn("target_duration_seconds: targetDurationSeconds", tab)
    self.assertIn("Длина ролика", tab)
    self.assertIn("Применяется ко всем вариантам сценария", tab)
```

- [ ] **Step 2: Run the source-contract test and verify RED**

Run:

```powershell
docker compose exec -T -e PYTHONPATH=/app backend python -m unittest tests.test_ui_layout_polish
```

Expected: the new test fails because the options and state are absent.

- [ ] **Step 3: Add duration options and state**

Define:

```jsx
const TARGET_DURATION_OPTIONS = [
  { value: 15, label: '≈15 сек', desc: 'Короткий охватный ролик' },
  { value: 20, label: '≈20 сек', desc: 'Основной формат' },
  { value: 30, label: '≈30 сек', desc: 'Больше пользы и аргументов' },
  { value: 45, label: '≈45 сек', desc: 'История или экспертный разбор' },
];
```

Initialize state from cache with a 20-second fallback. Include it in:

- `applyWorkspaceSnapshot`;
- `buildWorkspaceSnapshot`;
- local `saveCache` settings;
- workspace persistence effect dependencies;
- the analyze request payload.

- [ ] **Step 4: Add the first-screen control**

Place the control between `Стиль ролика` and `Количество вариантов сценария`.
Use a four-option segmented/button grid with `aria-pressed`, stable responsive
columns, and the selected visual state already used by nearby setup controls.

When `scriptMode === "custom"`, disable the buttons and show:

```text
Для своего текста длительность определяется фактической озвучкой.
```

Otherwise show:

```text
Применяется ко всем вариантам сценария. Итог зависит от темпа озвучки.
```

- [ ] **Step 5: Run frontend source tests and production build**

Run:

```powershell
docker compose exec -T -e PYTHONPATH=/app backend python -m unittest tests.test_ui_layout_polish
docker compose exec -T frontend npm run build
```

Expected: tests pass and Vite completes the production build.

---

### Task 4: Regression Verification And Local Handoff

**Files:**
- Update: `docs/superpowers/plans/2026-07-29-target-video-duration.md`

**Interfaces:**
- Consumes the completed backend, API, and frontend contracts.

- [ ] **Step 1: Run the complete backend suite**

```powershell
docker compose exec -T -e PYTHONPATH=/app backend python -m unittest discover -s tests -p "test_*.py"
```

Expected: all tests pass without real provider calls.

- [ ] **Step 2: Check formatting and review the diff**

```powershell
git diff --check
git diff --stat
```

Confirm no credentials, generated media, provider calls, or unrelated changes were added.

- [ ] **Step 3: Restart backend and frontend**

```powershell
docker compose restart backend frontend
docker compose ps
```

Expected: both services are `Up`.

- [ ] **Step 4: Verify the live local contract**

Check `http://localhost:8000/openapi.json` and confirm
`SaaSAnalyzeRequest.target_duration_seconds.default == 20`. Submit one custom
script through `/api/saasshorts/analyze` to verify the new field is accepted
without calling Gemini or fal.ai.

Open `http://localhost:5175/index.html#app` and verify the four duration choices
appear on the setup screen with `≈20 сек` selected by default.

- [ ] **Step 5: Mark this plan complete**

Change every completed checkbox in this document to `[x]` and record any
pre-existing tooling limitation separately from feature failures.

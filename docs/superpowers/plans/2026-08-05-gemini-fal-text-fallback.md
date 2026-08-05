# Gemini via fal.ai Text Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `POST /api/saasshorts/analyze` automatically continue through paid Google Gemini models on fal.ai when direct Google quota is exhausted or temporarily unavailable.

**Architecture:** Keep the existing direct Google helper unchanged for callers outside SaaS Shorts analysis. Add an analysis-scoped provider wrapper in `saasshorts.py` that first invokes one selected direct Google model and then adapts fal.ai `openrouter/router` output to the existing `.text` response contract. Pass the optional fal.ai key explicitly from the API endpoint through research, analysis, and script generation so no global mutable key state is introduced.

**Tech Stack:** Python 3, FastAPI, Google Gen AI SDK, `httpx`, fal.ai queue API, React/Vite, `unittest`/`pytest`.

## Global Constraints

- Pro routing order is direct `gemini-3.1-pro-preview`, fal.ai `google/gemini-3.1-pro-preview`, then fal.ai `google/gemini-3-flash-preview`.
- A paid fal.ai request starts only after a retryable direct Google availability failure.
- Invalid credentials, invalid requests, permissions, and other definitive 4xx errors do not trigger fal.ai spending.
- Returned fal.ai text, including malformed JSON or low-quality content, does not trigger another automatic paid generation.
- fal.ai Flash runs only after fal.ai Pro returns a retryable provider error without usable output.
- The change applies only to text calls inside `POST /api/saasshorts/analyze`.
- Provider keys remain server-side and must never appear in logs or responses.
- Existing image, video, voice, and moderation routing remains unchanged.

---

## File Structure

- `saasshorts.py`: owns model mapping, direct-to-fal routing, response adaptation, prompt/config translation, and the paid retry boundary.
- `app.py`: resolves the optional fal.ai key and passes analysis fallback settings into the synchronous pipeline.
- `dashboard/src/components/SaaShortsTab.jsx`: includes the user-owned `X-Fal-Key` header in the analyze request.
- `tests/test_saasshorts_text_fallback.py`: isolated unit and endpoint tests for provider routing and payment safety.
- `tests/test_saasshorts_storyboard.py`: existing regression tests run unchanged to protect script generation behavior.

### Task 1: Build the analysis-scoped provider router

**Files:**
- Modify: `saasshorts.py:45-190`
- Test: `tests/test_saasshorts_text_fallback.py`

**Interfaces:**
- Consumes: existing `_generate_gemini_content(...)`, `_fal_run(model_id, input_data, fal_key, timeout=600)`, and `resolve_gemini_text_model(text_model)`.
- Produces: `fal_gemini_text_model_chain(text_model: Optional[str]) -> list[str]`, `FalTextResponse`, and `_generate_analysis_content(..., fal_key=None, fal_fallback_enabled=False, fal_enable_web_search=False, direct_model_chain=None)`.

- [ ] **Step 1: Write routing tests that fail before implementation**

Create `tests/test_saasshorts_text_fallback.py` with these cases:

```python
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import saasshorts


class GeminiFalTextRouterTests(unittest.TestCase):
    def test_direct_success_never_calls_fal(self):
        direct = SimpleNamespace(text='{"ok": true}')
        with patch("saasshorts._generate_gemini_content", return_value=direct), \
             patch("saasshorts._fal_run") as fal_run:
            result = saasshorts._generate_analysis_content(
                MagicMock(),
                contents=["prompt"],
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )
        self.assertIs(result, direct)
        fal_run.assert_not_called()

    def test_quota_exhaustion_uses_fal_pro(self):
        with patch(
            "saasshorts._generate_gemini_content",
            side_effect=saasshorts.GeminiTemporaryError("429 RESOURCE_EXHAUSTED"),
        ), patch(
            "saasshorts._fal_run",
            return_value={"output": '{"ok": true}', "usage": {"cost": 0.01}},
        ) as fal_run:
            result = saasshorts._generate_analysis_content(
                MagicMock(),
                contents=["prompt"],
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )
        self.assertEqual(result.text, '{"ok": true}')
        self.assertTrue(result.paid_provider)
        self.assertEqual(fal_run.call_args.args[0], "openrouter/router")
        self.assertEqual(
            fal_run.call_args.args[1]["model"],
            "google/gemini-3.1-pro-preview",
        )

    def test_nonretryable_google_error_never_calls_fal(self):
        with patch(
            "saasshorts._generate_gemini_content",
            side_effect=ValueError("400 invalid request"),
        ), patch("saasshorts._fal_run") as fal_run:
            with self.assertRaisesRegex(ValueError, "invalid request"):
                saasshorts._generate_analysis_content(
                    MagicMock(),
                    contents=["prompt"],
                    text_model="pro",
                    fal_key="fal-key",
                    fal_fallback_enabled=True,
                )
        fal_run.assert_not_called()

    def test_retryable_fal_pro_error_uses_flash_once(self):
        with patch(
            "saasshorts._generate_gemini_content",
            side_effect=saasshorts.GeminiTemporaryError("503 UNAVAILABLE"),
        ), patch(
            "saasshorts._fal_run",
            side_effect=[RuntimeError("503 provider unavailable"), {"output": "ok"}],
        ) as fal_run:
            result = saasshorts._generate_analysis_content(
                MagicMock(),
                contents=["prompt"],
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )
        self.assertEqual(result.text, "ok")
        self.assertEqual(fal_run.call_count, 2)
        self.assertEqual(
            fal_run.call_args_list[1].args[1]["model"],
            "google/gemini-3-flash-preview",
        )

    def test_missing_fal_key_reports_quota_failure(self):
        with patch(
            "saasshorts._generate_gemini_content",
            side_effect=saasshorts.GeminiTemporaryError("429 RESOURCE_EXHAUSTED"),
        ):
            with self.assertRaisesRegex(
                saasshorts.GeminiTemporaryError,
                "fal.ai fallback key is missing",
            ):
                saasshorts._generate_analysis_content(
                    MagicMock(),
                    contents=["prompt"],
                    text_model="pro",
                    fal_key=None,
                    fal_fallback_enabled=True,
                )
```

- [ ] **Step 2: Run the new tests and confirm the missing router failure**

Run: `python -m pytest tests/test_saasshorts_text_fallback.py -q`

Expected: FAIL because `_generate_analysis_content` and `FalTextResponse` do not exist.

- [ ] **Step 3: Add fal.ai model configuration and response adaptation**

In `saasshorts.py`, add environment-backed defaults and these exact interfaces:

```python
FAL_TEXT_ENDPOINT = os.environ.get("FAL_TEXT_ENDPOINT", "openrouter/router")
FAL_GEMINI_PRO_MODEL = os.environ.get(
    "FAL_GEMINI_PRO_MODEL", "google/gemini-3.1-pro-preview"
)
FAL_GEMINI_FLASH_MODEL = os.environ.get(
    "FAL_GEMINI_FLASH_MODEL", "google/gemini-3-flash-preview"
)
FAL_GEMINI_FAST_FALLBACK_MODEL = os.environ.get(
    "FAL_GEMINI_FAST_FALLBACK_MODEL", "google/gemini-2.5-flash"
)


class FalTextResponse:
    def __init__(self, text, *, usage=None, request_meta=None):
        self.text = text
        self.usage = usage or {}
        self.request_meta = request_meta or {}
        self.paid_provider = True
        self.candidates = []
```

Implement `fal_gemini_text_model_chain` so `pro`, `quality`, and `power` return Pro then Flash; fast presets return Flash then 2.5 Flash; explicit `gemini-*` values map to `google/gemini-*` then Flash with duplicates removed.

- [ ] **Step 4: Implement direct-to-fal routing**

Add `_generate_analysis_content` with this control flow:

```python
def _generate_analysis_content(
    client,
    *,
    contents,
    config=None,
    text_model=None,
    direct_model_chain=None,
    fal_key=None,
    fal_fallback_enabled=False,
    fal_enable_web_search=False,
):
    if not fal_fallback_enabled:
        return _generate_gemini_content(
            client,
            contents=contents,
            config=config,
            text_model=text_model,
            model_chain=direct_model_chain,
        )

    direct_models = direct_model_chain or [resolve_gemini_text_model(text_model)]
    last_error = None
    try:
        return _generate_gemini_content(
            client,
            contents=contents,
            config=config,
            text_model=text_model,
            model_chain=direct_models,
        )
    except GeminiTemporaryError as direct_error:
        last_error = direct_error
        if not fal_key:
            raise GeminiTemporaryError(
                "Google quota is exhausted or temporarily unavailable, and the fal.ai fallback key is missing"
            ) from direct_error

    prompt = _fal_prompt_from_contents(contents)
    input_data = _fal_text_input(
        prompt,
        config=config,
        enable_web_search=fal_enable_web_search,
    )
    for model in fal_gemini_text_model_chain(text_model):
        input_data["model"] = model
        try:
            payload = _fal_run(FAL_TEXT_ENDPOINT, input_data, fal_key)
            error = str(payload.get("error") or "").strip()
            output = payload.get("output")
            if error:
                raise RuntimeError(error)
            if not isinstance(output, str) or not output.strip():
                raise RuntimeError("fal.ai returned no text output")
            return FalTextResponse(
                output,
                usage=payload.get("usage"),
                request_meta=payload.get("_fal_request"),
            )
        except Exception as error:
            last_error = error
            if not _is_retryable_fal_text_error(error):
                break
    raise GeminiTemporaryError(f"Gemini via fal.ai is unavailable: {last_error}")
```

Implement `_fal_prompt_from_contents`, `_fal_text_input`, and `_is_retryable_fal_text_error` directly above this function. Translate `max_output_tokens` to `max_tokens`, copy numeric `temperature`, and set `enable_web_search=True` only when requested. Treat `429`, `503`, `unavailable`, `high demand`, connection, and timeout markers as retryable; do not treat `400`, `401`, `402`, `403`, `balance`, `credit`, `auth`, or `permission` markers as retryable.

- [ ] **Step 5: Run router tests**

Run: `python -m pytest tests/test_saasshorts_text_fallback.py -q`

Expected: PASS for all `GeminiFalTextRouterTests`.

- [ ] **Step 6: Commit the isolated router and tests**

Stage only Task 1 hunks from `saasshorts.py` plus the new test file, leaving pre-existing unrelated hunks unstaged. Commit message: `feat: add fal Gemini text router`.

### Task 2: Integrate the router into SaaS analysis and enforce the paid retry boundary

**Files:**
- Modify: `saasshorts.py:198-280,390-510,1380-1430,1581-1990`
- Test: `tests/test_saasshorts_text_fallback.py`

**Interfaces:**
- Consumes: `_generate_analysis_content(...)` and `FalTextResponse.paid_provider` from Task 1.
- Produces: optional `fal_key: Optional[str]` and `fal_fallback_enabled: bool` keyword parameters on `research_saas_online`, `analyze_saas`, and `generate_scripts`.

- [ ] **Step 1: Write failing integration and payment-boundary tests**

Append tests that assert:

```python
class GeminiFalAnalysisIntegrationTests(unittest.TestCase):
    def test_research_enables_web_search_and_uses_grounding_direct_model(self):
        response = SimpleNamespace(text='{"product_name": "Demo"}', candidates=[])
        with patch("google.genai.Client"), patch(
            "saasshorts._generate_analysis_content", return_value=response
        ) as generate:
            saasshorts.research_saas_online(
                "https://example.com",
                "gemini-key",
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )
        self.assertTrue(generate.call_args.kwargs["fal_enable_web_search"])
        self.assertEqual(
            generate.call_args.kwargs["direct_model_chain"],
            ["gemini-3.1-pro-preview"],
        )

    def test_paid_malformed_script_response_is_not_requested_twice(self):
        response = saasshorts.FalTextResponse("not json")
        ask = MagicMock(return_value=response)
        with self.assertRaisesRegex(Exception, "broken scripts answer"):
            saasshorts._request_gemini_script_batch(
                ask,
                num_scripts=1,
                require_shots=False,
                label="scripts",
            )
        ask.assert_called_once()
```

Also add one test for `analyze_saas` and one for `generate_scripts` asserting that each forwards `fal_key` and `fal_fallback_enabled` to `_generate_analysis_content`.

- [ ] **Step 2: Run the integration tests and confirm signature failures**

Run: `python -m pytest tests/test_saasshorts_text_fallback.py -q`

Expected: FAIL because the three public pipeline functions do not accept fal.ai fallback arguments and the paid response is still retried.

- [ ] **Step 3: Thread fallback arguments through the three analysis functions**

Add these keyword parameters with backward-compatible defaults:

```python
fal_key: Optional[str] = None,
fal_fallback_enabled: bool = False,
```

Replace analysis-scoped `_generate_gemini_content` calls with `_generate_analysis_content`. For ordinary analysis and scripts, pass no custom direct chain so the wrapper uses exactly the selected direct model. For URL research, pass:

```python
direct_model_chain=[resolve_gemini_grounding_model(text_model)],
fal_enable_web_search=True,
```

Keep all callers outside `/api/saasshorts/analyze` on default `fal_fallback_enabled=False`.

- [ ] **Step 4: Prevent an automatic paid retry after returned text**

In `_request_gemini_script_batch`, after parsing and recording the best response but before the existing second-attempt branch, add:

```python
if getattr(response, "paid_provider", False):
    break
```

This permits direct Google to retain its existing malformed-response retry while making any additional paid fal.ai generation a new user action.

- [ ] **Step 5: Run integration and existing script tests**

Run: `python -m pytest tests/test_saasshorts_text_fallback.py tests/test_saasshorts_storyboard.py -q`

Expected: PASS.

- [ ] **Step 6: Commit only Task 2 hunks**

Stage only the new analysis integration and paid-boundary hunks from `saasshorts.py` plus Task 2 test additions. Commit message: `feat: use fal fallback in SaaS analysis`.

### Task 3: Resolve the fal.ai key at the API boundary and send it from the dashboard

**Files:**
- Modify: `app.py:3247-3360`
- Modify: `dashboard/src/components/SaaShortsTab.jsx:1450-1475`
- Test: `tests/test_saasshorts_text_fallback.py`

**Interfaces:**
- Consumes: `fal_key` and `fal_fallback_enabled` parameters from Task 2.
- Produces: `X-Fal-Key` support on `POST /api/saasshorts/analyze` and clear HTTP `503` fallback errors through the existing `GeminiTemporaryError` handler.

- [ ] **Step 1: Write a failing endpoint wiring test**

Add an async endpoint test using a manual description:

```python
class SaaSAnalyzeFalKeyTests(unittest.TestCase):
    def test_analyze_resolves_and_forwards_fal_key(self):
        import asyncio
        import app

        def resolve(provider, user, header, use_platform_keys):
            return {"gemini": "gemini-key", "fal": "fal-key"}[provider]

        request = app.SaaSAnalyzeRequest(description="Test", text_model="pro")
        with patch("app.resolve_effective_api_key", side_effect=resolve), patch(
            "app.generate_scripts", return_value=[]
        ) as generate:
            asyncio.run(
                app.saasshorts_analyze(
                    request,
                    x_gemini_key="gemini-header",
                    x_fal_key="fal-header",
                    authorization=None,
                )
            )
        self.assertEqual(generate.call_args.kwargs["fal_key"], "fal-key")
        self.assertTrue(generate.call_args.kwargs["fal_fallback_enabled"])
```

- [ ] **Step 2: Run the endpoint test and confirm the missing header/signature failure**

Run: `python -m pytest tests/test_saasshorts_text_fallback.py -q`

Expected: FAIL because `saasshorts_analyze` does not accept `x_fal_key` and does not forward the resolved key.

- [ ] **Step 3: Add optional fal.ai key resolution to the endpoint**

Add `x_fal_key: Optional[str] = Header(None, alias="X-Fal-Key")` to `saasshorts_analyze`. Resolve `fal` only for non-custom analysis. If a platform fal.ai key is unavailable, keep `fal_key=None` so direct Google still runs; if fallback is later needed, `_generate_analysis_content` returns the clear missing-key `GeminiTemporaryError`.

Pass these keywords to `research_saas_online`, `analyze_saas`, and both `generate_scripts` branches:

```python
fal_key=fal_key,
fal_fallback_enabled=True,
```

Keep custom-script mode free of fal.ai resolution and generation.

- [ ] **Step 4: Send the user-owned fal.ai key from the dashboard**

In the analyze request header object in `SaaShortsTab.jsx`, add:

```jsx
...(falKey && !isManagedKey(falKey) ? { 'X-Fal-Key': falKey } : {}),
```

Saved and platform sentinel values remain server-resolved and are not sent to the browser API as credentials.

- [ ] **Step 5: Run endpoint tests and build the dashboard**

Run: `python -m pytest tests/test_saasshorts_text_fallback.py tests/test_auth_key_vault.py -q`

Expected: PASS.

Run: `npm run build` from `dashboard`.

Expected: Vite production build completes without JSX errors.

- [ ] **Step 6: Commit only Task 3 hunks**

Stage the endpoint/header hunks and endpoint tests without staging unrelated dirty-file changes. Commit message: `feat: wire fal key into SaaS analysis`.

### Task 4: Verify the complete fallback contract

**Files:**
- Verify: `saasshorts.py`
- Verify: `app.py`
- Verify: `dashboard/src/components/SaaShortsTab.jsx`
- Verify: `tests/test_saasshorts_text_fallback.py`

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: test evidence that direct success is free of fal.ai calls and direct quota failure follows the approved Pro/Flash route without paid content retries.

- [ ] **Step 1: Run focused fallback tests with verbose names**

Run: `python -m pytest tests/test_saasshorts_text_fallback.py -vv`

Expected: every provider, key, web-search, and paid-boundary test passes.

- [ ] **Step 2: Run relevant backend regression suites**

Run: `python -m pytest tests/test_saasshorts_storyboard.py tests/test_auth_key_vault.py -q`

Expected: PASS with no changes to existing direct-Google, custom-script, storyboard, or key-vault behavior.

- [ ] **Step 3: Run syntax and frontend production checks**

Run: `python -m py_compile saasshorts.py app.py`

Expected: no output and exit code `0`.

Run: `npm run build` from `dashboard`.

Expected: production assets are generated successfully.

- [ ] **Step 4: Review the final diff for payment and secret safety**

Run: `git diff --check`.

Run: `rg -n "fal_key|X-Fal-Key|paid_provider|openrouter/router" saasshorts.py app.py dashboard/src/components/SaaShortsTab.jsx tests/test_saasshorts_text_fallback.py`.

Expected: keys appear only in parameters, server-side resolution, authorization headers inside the existing fal runner, and test fixtures; no log statement interpolates a secret.

- [ ] **Step 5: Record final verification without staging unrelated changes**

Do not stage or overwrite pre-existing user changes. If implementation hunks cannot be isolated safely from already modified files, leave those hunks uncommitted and report the verified file paths and test commands instead of committing unrelated work.

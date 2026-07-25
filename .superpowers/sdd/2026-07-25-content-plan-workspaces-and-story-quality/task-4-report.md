# Task 4 Report: Honest Duration and Diverse Hooks

## Delivered

- Added narration-source helpers for storyboard shots, legacy UGC segments, and fallback narration.
- Rebuilt generated `full_narration`, replaced LLM duration metadata with the shared estimate, and marked it with `duration_source: narration_estimate`.
- Updated backend and frontend duration estimates to exclude bracketed audio tags from words while accounting for tag and pause duration.
- Added hook opening extraction, canned-opening rejection, duplicate-opening validation, supplied `Hook:` / `Хук:` enforcement for script 1, and one validation retry without replacing the existing JSON salvage behavior.
- Added hook taxonomy and per-batch diversity instructions to both script formats and content-plan generation.
- Changed script cards to display narration-derived duration only. Existing per-item workspace and truncated JSON recovery code was preserved.

## Verification

- Focused Task 4 tests pass: 9 tests covering duration estimation, stale metadata replacement, hook validation retries, supplied hooks, and UI source behavior.
- Existing truncated Gemini JSON recovery test passes with its retry and salvage behavior intact.
- `npm.cmd run build --prefix dashboard` passes.
- Required unittest suite ran 131 tests: 130 passed; one unrelated Windows path-separator assertion failed in `SaaSExistingShotFrameTests.test_frame_found_via_videos_url_of_an_earlier_job` (`/` versus `\\`).

## Environment Note

The required Python environment initially lacked `httpx`, `google-genai`, and `numpy`; these were installed into the current user's Python site-packages solely to run the declared test command. The test command also needs `PYTHONIOENCODING=utf-8` in this console because existing repository logs contain emoji.

## Round 1 Follow-up

- Added the exact `hook_type` enum to both generated JSON schemas and prompt requirements.
- Made type diversity machine-validatable for multi-script batches: missing, unsupported, and duplicate types trigger the existing single retry; single-script batches remain exempt.
- Replaced bare-prefix canned opening matching with normalized phrase-boundary matching. The validator now permits substantive `Stop approving invoices manually` hooks while rejecting watch/wait-until-the-end phrases, Russian and Spanish equivalents, and hyphenated `Стоп-стоп-стоп` repetition.
- Replaced English and Spanish filler examples with substantive examples compatible with the hook taxonomy.

### Round 1 Verification

- Focused hook suite: 12/12 tests passed.
- Required unittest suite: 134/135 tests passed. The only failure is the existing Windows path-separator assertion in `SaaSExistingShotFrameTests.test_frame_found_via_videos_url_of_an_earlier_job`.
- `npm.cmd run build --prefix dashboard` passed.

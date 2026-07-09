# Storyboard V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `storyboard_v3` produce an editable shot-by-shot script, generate Kling V3 visual clips from those shots, and burn separate overlay text plus speech subtitles into the final video.

**Architecture:** Keep `shots` as the single source of truth. Backend normalizes each shot into timing, role, action, scene, camera, overlay, speech, transition, and Kling prompt fields. Rendering uses Kling V3 clips + external TTS audio + an ASS subtitle file with separate overlay and subtitle styles.

**Tech Stack:** Python/FastAPI backend, fal.ai Kling V3, FFmpeg/ASS subtitles, React dashboard, unittest.

---

### Task 1: Normalize Storyboard Shots

**Files:**
- Modify: `saasshorts.py`
- Test: `tests/test_saasshorts_storyboard.py`

- [ ] Add a test that `normalize_storyboard_shots()` preserves `actor_action`, `role`, `camera`, `overlay_text`, `speech`, and `transition`.
- [ ] Implement missing normalized defaults:
  - `role`: fallback from `type`, then `shot_<n>`.
  - `actor_action`: fallback from `action`.
  - `camera`: fallback to `vertical 9:16 steady handheld`.
  - `transition`: fallback to `cut`.
  - `generation_prompt`: combine English vertical UGC constraints with `scene`, `actor_action`, `camera`, and no text/watermark instruction.
- [ ] Run `docker compose exec -T backend python -m unittest discover -s tests -p test_saasshorts_storyboard.py`.

### Task 2: Generate Storyboard Prompt Shape

**Files:**
- Modify: `saasshorts.py`
- Test: `tests/test_saasshorts_storyboard.py`

- [ ] Add a test that the Gemini storyboard prompt asks for `role`, `actor_action`, `transition`, `overlay_text`, and `speech`.
- [ ] Update the `script_format == "storyboard_v3"` prompt schema and rules to match the desired six-shot storyboard format.
- [ ] Ensure `full_narration` is built from shot `speech`.

### Task 3: ASS Overlay And Speech Subtitles

**Files:**
- Modify: `saasshorts.py`
- Test: `tests/test_saasshorts_storyboard.py`

- [ ] Add a test for a new `generate_storyboard_ass_subtitles(audio_path, shots, output_path)` helper.
- [ ] Implement helper:
  - Generate speech subtitles from Whisper words using `Subtitle` style.
  - Add `Overlay` events from `shot.overlay_text` for shot timing.
  - Use bottom dark boxed subtitles and upper/mid overlay text.
- [ ] Use this helper in `generate_storyboard_video()` instead of plain `generate_tiktok_subs()`.

### Task 4: Composite Storyboard Clips

**Files:**
- Modify: `saasshorts.py`
- Test: `tests/test_saasshorts_storyboard.py`

- [ ] Keep existing `composite_storyboard_video()` path.
- [ ] Ensure final video maps generated storyboard video, external voiceover, and ASS subtitles.
- [ ] Do not use Kling native audio for storyboard mode.

### Task 5: Dashboard Shot Editor

**Files:**
- Modify: `dashboard/src/components/SaaShortsTab.jsx`
- Test: existing frontend text tests if present.

- [ ] Display each shot with `role`, timing, `actor_action`, `overlay_text`, `speech`, `generation_prompt`, and `transition`.
- [ ] Edit all fields and save back into the script.
- [ ] Keep reference image upload per shot.

### Task 6: Verification

**Files:**
- All touched files.

- [ ] Run `docker compose exec -T backend python -m unittest discover -s tests -p test_saasshorts_storyboard.py`.
- [ ] Run `docker compose exec -T backend python -m unittest discover -s tests -p test_saasshorts_lipsync.py`.
- [ ] Run `docker compose exec -T -e PYTHONPYCACHEPREFIX=/tmp/pycache backend python -m py_compile saasshorts.py app.py`.
- [ ] Run `docker compose exec -T frontend npm run build`.

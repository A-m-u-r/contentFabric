# Dynamic Storyboard Pacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new AI storyboards use a denser, varied prompt-only rhythm without automatic semantic repair requests or actor-appearance drift.

**Architecture:** Keep the creative pacing change in `generate_scripts` and the existing duration-preset table. Gemini receives one complete contract that defines beat density, soft B-roll composition, first/last talking shots, and non-adjacent B-roll. Existing image-conditioned frame generation remains the sole appearance authority. Clean English prompts remain usable; actor bindings are removed from contaminated neutral B-roll prompts without substituting localized UI text. Script language and model-prompt language are carried as explicit provenance so the pipeline does not guess language from prompt vocabulary.

**Tech Stack:** Python 3, `unittest`, mocked Google GenAI and fal.ai adapters.

## Global Constraints

- Do not call Gemini, fal.ai, ElevenLabs, or any paid provider from tests.
- Do not add a semantic sequence validator, correction retry, or automatic B-roll-to-talking conversion.
- Apply the profile only to newly AI-generated `storyboard_v3` scripts.
- Keep custom scripts and existing saved storyboards unchanged.
- First and last shots are talking; B-roll is never consecutive.
- Actor appearance comes only from the selected reference image.

---

### Task 1: Dynamic Storyboard Prompt Contract

**Files:**
- Modify: `tests/test_saasshorts_storyboard.py`
- Modify: `saasshorts.py`

**Interfaces:**
- Consumes: `TARGET_VIDEO_DURATION_PRESETS`, `_target_duration_prompt()`, `generate_scripts()`
- Produces: AI storyboard prompt guidance and `storyboard_pacing: "dynamic"` provenance

- [ ] **Step 1: Replace the rollback assertions with failing dynamic-profile tests**

Add assertions that the 20-second prompt contains `8-10 visual beats`,
`STORYBOARD PACING PROFILE`, `35-45%`, the 25-50% soft range, first/last
talking requirements, non-adjacent B-roll, presenter/non-presenter variation,
and `storyboard_pacing: "dynamic"`. Assert that custom scripts still omit the
field.

- [ ] **Step 2: Add a failing test that generation makes no semantic refinement call**

Patch `saasshorts.refine_storyboard_broll_alignment` with an
`AssertionError`. Generate a mocked storyboard and assert generation succeeds,
proving that the automatic second creative request is gone.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_saasshorts_storyboard.SaaSStoryboardTests tests.test_saasshorts_storyboard.SaaSBrollSpeechAlignmentTests
```

Expected: failures for the old visual-beat ranges, missing dynamic prompt,
missing provenance, and the still-active refinement call.

- [ ] **Step 4: Implement the prompt-only dynamic profile**

Change storyboard visual-beat presets to `6-8`, `8-10`, `11-15`, and `16-22`.
Add one `STORYBOARD PACING PROFILE` section to the initial storyboard prompt
with the approved soft B-roll mix and ordering rules. Remove the automatic
`refine_storyboard_broll_alignment()` call from `generate_scripts`. Stamp only
AI-generated storyboard scripts with:

```python
script["storyboard_pacing"] = "dynamic"
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the command from Step 3 and expect all selected tests to pass.

### Task 2: Neutral B-Roll Identity Boundary

**Files:**
- Modify: `tests/test_saasshorts_storyboard.py`
- Modify: `saasshorts.py`

**Interfaces:**
- Consumes: `_build_storyboard_generation_prompt()`
- Produces: actor-conditioned prompts only for talking and presenter B-roll shots

- [ ] **Step 1: Add failing tests for model-supplied and fallback prompts**

Assert that a neutral B-roll shot with `actor_in_frame=false` removes actor
bindings from a contaminated English model prompt without substituting
localized UI fields. Actor references must also be removed from all three
structured fields when no model prompt exists, while a clean English prompt
remains usable. Talking and presenter B-roll must still identify the selected
actor, while a hand-pinned user prompt remains unchanged.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest discover -s tests -p "test_saasshorts_storyboard.py"
```

Expected: a contaminated neutral model prompt is still reused unchanged, and
actor references inside structured fields are still passed through.

- [ ] **Step 3: Enforce the structured identity boundary**

For non-manual neutral B-roll, detect actor/reference bindings with
word-boundary patterns for supported UI languages. Remove identity bindings
from a contaminated English model prompt and fall back to a neutral English
prompt if it cannot be sanitized safely. Sanitize scene, action, and camera
when no model prompt exists, then apply the same English-language guard to the
assembled result. Use explicit script and prompt language provenance: for a
non-English script, only a model prompt tagged as English may bypass the
fallback. Preserve clean provenanced English prompts and manual user prompts.
Remove the global `same actor/character across shots` rule from prompt rebuild
and fill paths.

- [ ] **Step 4: Preserve paid frame caches**

Keep `_avatar_reference_image()`'s existing appearance wording unchanged. It
already preserves the exact hairstyle, and changing the full prompt would
invalidate legacy `.prompt.txt` cache keys.

- [ ] **Step 5: Run the tests and verify GREEN**

Run the command from Step 2 and expect it to pass without a network request.

### Task 3: Regression Verification

**Files:**
- Verify: `tests/`

**Interfaces:**
- Consumes: all modified production behavior
- Produces: regression evidence without paid API calls

- [ ] **Step 1: Run all storyboard and lipsync tests**

```powershell
python -m unittest tests.test_saasshorts_storyboard tests.test_saasshorts_lipsync
```

- [ ] **Step 2: Run the full backend test suite**

```powershell
python -m unittest discover -s tests
```

- [ ] **Step 3: Inspect the diff and confirm scope**

Verify that only the approved documentation, prompt contract, provenance,
automatic-refinement removal, identity boundary, and tests changed.

- [ ] **Step 4: Commit the implementation**

```powershell
git add saasshorts.py tests/test_saasshorts_storyboard.py tests/test_saasshorts_lipsync.py docs/superpowers/plans/2026-07-29-dynamic-storyboard-pacing.md
git commit -m "feat: restore dynamic storyboard pacing"
```

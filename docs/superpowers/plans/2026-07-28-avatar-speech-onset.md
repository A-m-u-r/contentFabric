# Avatar Speech-Onset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start every internal talking shot immediately before audible speech and stage new avatar references with naturally closed lips.

**Architecture:** Add one render-time retiming pass between manifest alignment and performance/length splitting. It mutates adjacent slice boundaries while preserving a contiguous master timeline; reference generation remains in the existing Flux edit path.

**Tech Stack:** Python, unittest, FFmpeg energy mask, existing ASR word timings.

## Global Constraints

- Do not change or regenerate the master voiceover.
- Keep 40 ms of speech preroll.
- Do not call FAL during tests or verification.
- Preserve reusable B-roll video when only its diagnostic audio slice changes.

---

### Task 1: Retiming

**Files:**
- Modify: `saasshorts.py`
- Test: `tests/test_saasshorts_lipsync.py`

**Interfaces:**
- Consumes: slices with `shot`, `start`, `end`; aligned ASR words; master audio.
- Produces: `_retime_talking_slices_to_speech(slices, words, audio_path) -> int`.

- [x] **Step 1: Write the failing integration test**
- [x] **Step 2: Run it and verify the manifest boundary remains too early**
- [x] **Step 3: Implement onset selection from the energy mask and first ASR word**
- [x] **Step 4: Apply it in preview planning and paid render planning**
- [x] **Step 5: Run lip-sync tests**

### Task 2: B-roll Cache

**Files:**
- Modify: `saasshorts.py`
- Test: `tests/test_saasshorts_quality.py`

**Interfaces:**
- Extends: `_ensure_slice_audio(..., invalidate_video: bool = True)`.

- [x] **Step 1: Write the failing cache-preservation test**
- [x] **Step 2: Verify the missing argument fails**
- [x] **Step 3: Separate audio cleanup from video cleanup**
- [x] **Step 4: Pass `invalidate_video=False` for B-roll slices**
- [x] **Step 5: Run quality tests**

### Task 3: Closed-Mouth References

**Files:**
- Modify: `saasshorts.py`
- Test: `tests/test_saasshorts_lipsync.py`

**Interfaces:**
- Extends the prompt built by `_avatar_reference_image`.

- [x] **Step 1: Assert the prompt contains `lips gently closed` and `neutral resting mouth`**
- [x] **Step 2: Verify the assertion fails**
- [x] **Step 3: Add a positive still-before-speech expression instruction**
- [x] **Step 4: Run lip-sync tests**

### Task 4: Verification

**Files:**
- Verify: `saasshorts.py`, targeted test suites, Git diff.

- [x] **Step 1: Run lip-sync, quality, storyboard, and subtitle tests**
- [x] **Step 2: Run a local dry test against the last job's saved words and manifest**
- [x] **Step 3: Confirm no FAL function was invoked**
- [ ] **Step 4: Commit the implementation**

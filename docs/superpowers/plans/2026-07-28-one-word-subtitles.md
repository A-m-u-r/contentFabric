# One-word Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every production subtitle preset show exactly one spoken word per ASS dialogue event.

**Architecture:** Keep the existing ASR alignment, ASS styling and caption writer. Change both subtitle function defaults and both production call sites to `max_words=1`, while retaining the parameter for backward-compatible internal overrides. Rebuild the latest reel by regenerating only its ASS file and recompositing cached media.

**Tech Stack:** Python 3.11, `unittest`, ASS/libass, FFmpeg, Docker Compose.

## Global Constraints

- Apply to both `generate_tiktok_subs` and `generate_storyboard_ass_subtitles`.
- Apply to the classic pipeline and Storyboard V3.
- Do not add a UI setting.
- Preserve punctuation, keyword color accents, pop animation, font and safe zone.
- Do not call TTS, fal.ai or another paid provider while rebuilding the latest reel.

---

### Task 1: Enforce one-word production captions

**Files:**
- Modify: `saasshorts.py:4644-4757`
- Modify: `saasshorts.py:8477-8481`
- Modify: `saasshorts.py:8907`
- Test: `tests/test_saasshorts_subtitles.py`
- Test: `tests/test_saasshorts_storyboard.py`

**Interfaces:**
- Consumes: aligned word dictionaries shaped as `{"word": str, "start": float, "end": float}`.
- Produces: `generate_tiktok_subs(..., max_words: int = 1)` and `generate_storyboard_ass_subtitles(..., max_words: int = 1)` ASS files with one dialogue per word.

- [ ] **Step 1: Write failing tests for both presets**

Add a classic-preset test that calls the default:

```python
def test_tiktok_default_emits_one_dialogue_per_word(self):
    words = [_w("ОДИН,", 0.0, 0.3), _w("ДВА", 0.3, 0.6), _w("ТРИ.", 0.6, 1.0)]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "subs.ass")
        generate_tiktok_subs("unused.mp3", out, words=words)
        content = open(out, encoding="utf-8").read()
    dialogue = [line for line in content.splitlines() if line.startswith("Dialogue:")]
    self.assertEqual(len(dialogue), 3)
    self.assertTrue(any("ОДИН," in line for line in dialogue))
```

Add a Storyboard V3 test with the same three timed words and assert three
`Dialogue:` lines, with `ОДИН,` attached to one event and no punctuation-only
event.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
docker compose exec -T backend python -m unittest discover -s tests -p "test_saasshorts_subtitles.py"
docker compose exec -T backend python -m unittest discover -s tests -p "test_saasshorts_storyboard.py" -k one_dialogue
```

Expected: both new tests fail because the defaults still group up to three
words.

- [ ] **Step 3: Implement the one-word defaults and production calls**

Change the function signatures:

```python
def generate_tiktok_subs(..., max_words: int = 1, ...) -> str:
def generate_storyboard_ass_subtitles(..., max_words: int = 1, ...) -> str:
```

Change both production calls:

```python
generate_storyboard_ass_subtitles(..., max_words=1, ...)
generate_tiktok_subs(..., max_words=1, ...)
```

Update the TikTok docstring from `1-3 words` to `one word at a time`.

- [ ] **Step 4: Run focused and full tests**

Run:

```bash
docker compose exec -T backend python -m unittest discover -s tests -p "test_saasshorts_subtitles.py"
docker compose exec -T backend python -m unittest discover -s tests -p "test_saasshorts_storyboard.py"
docker compose exec -T backend python -m unittest discover -s tests
```

Expected: all tests pass.

- [ ] **Step 5: Commit the production change**

```bash
git add saasshorts.py tests/test_saasshorts_subtitles.py tests/test_saasshorts_storyboard.py
git commit -m "Show subtitles one word at a time"
```

### Task 2: Rebuild and inspect the latest reel

**Files:**
- Regenerate: `output/saas_9646abbe-7baa-469e-8a6a-3cb009d7b154/__subs.ass`
- Create: `output/saas_9646abbe-7baa-469e-8a6a-3cb009d7b154/__storyboard_final_one_word.mp4`
- Replace after verification: `output/saas_9646abbe-7baa-469e-8a6a-3cb009d7b154/__storyboard_final.mp4`

**Interfaces:**
- Consumes: cached master audio, aligned transcript, three cached video clips and the existing `2.14s` whisper marker.
- Produces: a 1080x1920 H.264/AAC MP4 served by the existing gallery URL.

- [ ] **Step 1: Regenerate ASS locally**

Transcribe `__voice.mp3` with the installed local Whisper model, align those
timings to `full_narration` from `gallery_metadata.json`, and call:

```python
generate_storyboard_ass_subtitles(
    audio_path,
    shots,
    subs_path,
    max_words=1,
    words=aligned_words,
    caption_keywords=metadata.get("caption_keywords"),
)
```

Assert that the number of `Dialogue:` events equals the aligned word count and
that every visible event contains one token.

- [ ] **Step 2: Recompose cached clips**

Call `composite_storyboard_video` with:

```python
[
    {"path": "__avatar_01.mp4", "duration": 3.38,
     "shot": {"visual_type": "talking", "_performance": "whisper", "_whisper_start": 2.14}},
    {"path": "__avatar_broll_02.mp4", "duration": 3.44,
     "shot": {"visual_type": "broll"}},
    {"path": "__avatar_03.mp4", "duration": 3.69,
     "shot": {"visual_type": "talking"}},
]
```

Use the cached master audio and regenerated ASS. Do not invoke any generation
endpoint.

- [ ] **Step 3: Verify the artifact**

Run `ffprobe` and require:

```text
video: h264, 1080x1920, 30/1 fps
audio: aac
duration: 10.50s
```

Extract adjacent frames during the first sentence and visually verify that only
one word is visible in each frame, while the subtitle remains inside the safe
zone.

- [ ] **Step 4: Publish locally**

Back up the current canonical MP4, copy the verified one-word version to
`__storyboard_final.mp4`, and confirm HTTP `200 video/mp4` from the existing
gallery URL.

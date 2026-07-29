# Target Video Duration Design

## Goal

Let the user choose an approximate reel duration on the first AI Shorts screen
instead of generating nearly every script around thirty seconds.

## User Experience

Add a `Длина ролика` segmented control next to the other script-generation
settings:

- `≈15 сек` — prompt range 13-17 seconds;
- `≈20 сек` — prompt range 18-22 seconds and the default;
- `≈30 сек` — prompt range 28-32 seconds;
- `≈45 сек` — prompt range 43-47 seconds.

One selected target applies to every script in the current generation batch.
The setting is saved in the current content workspace, restored after reload,
and included in the analyze request.

For a custom script, the selector remains visible but does not rewrite or trim
the supplied text. Its rendered duration continues to be determined by the
actual voiceover.

## Prompt Contract

The API accepts `target_duration_seconds` with supported values 15, 20, 30, and
45. Missing or unsupported values normalize to 20.

Both UGC and storyboard prompts receive:

- the selected target;
- the allowed plus/minus two-second range;
- an approximate spoken-word budget based on the existing 2.2 words/second
  estimator, with room for 2-3 audio tags and marked pauses: 26-30 words at 15
  seconds, 37-41 at 20, 59-63 at 30, and 92-96 at 45;
- the target visual-beat count specified below.

Dynamic storyboard shot-count guidance:

- 15 seconds: 6-8 visual beats;
- 20 seconds: 8-10 visual beats;
- 30 seconds: 11-15 visual beats;
- 45 seconds: 16-22 visual beats.

The existing maximum of three paid B-roll clips remains unchanged. Longer
scripts gain most of their additional visual rhythm from alternating presenter
framings and local edits rather than extra B-roll generations.

## Enforcement Boundary

Duration is controlled only through the generation prompt. The pipeline does
not:

- reject an otherwise valid Gemini answer because its estimated duration is
  outside the requested range;
- make another Gemini request solely to correct duration;
- mechanically trim, pad, or rewrite generated narration;
- modify custom scripts.

After generation, `_finalize_generated_script` remains the source of truth for
the displayed `duration_seconds`, calculated from the narration that will
actually reach TTS. Therefore the UI may honestly show a value outside the
selected range when Gemini did not follow the prompt.

## Data Flow

1. `SaaShortsTab` stores `targetDurationSeconds`, defaulting to 20.
2. Workspace snapshots save and restore `targetDurationSeconds`.
3. `POST /api/saasshorts/analyze` receives `target_duration_seconds`.
4. `generate_scripts` normalizes the value and adds its duration instructions
   to either the UGC or storyboard prompt.
5. Generated scripts store `target_duration_seconds` as provenance while
   `duration_seconds` continues to represent the narration-derived estimate.

## Compatibility

Existing saved workspaces without the field use the 20-second default. Existing
scripts and cached media are not invalidated because duration affects only new
AI script generation.

## Testing

Tests must cover:

- API default and propagation;
- normalization of all supported values and fallback to 20;
- UGC and storyboard prompt ranges, word guidance, and shot-count guidance;
- script provenance metadata;
- frontend control, default, workspace persistence, and analyze payload;
- custom scripts remaining unchanged.

All tests use mocked Gemini responses and must not call Gemini, fal.ai,
ElevenLabs, or any other paid provider.

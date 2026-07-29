# Dynamic Storyboard Pacing Design

## Goal

Restore the denser AI storyboard rhythm while keeping the selected actor
consistent and preventing monotonous runs of similar B-roll.

This design supersedes the B-roll-count guidance in
`2026-07-29-target-video-duration-design.md`. Duration selection itself stays
unchanged.

## Research Basis

TikTok recommends a hook/body/close structure, dynamic transitions, movement,
and faster early scene changes, but does not prescribe a fixed B-roll ratio:

- https://ads.tiktok.com/business/en-US/creative-codes
- https://ads.tiktok.com/business/en-US/blog/creative-best-practices-top-performing-ads

The B-Script study of 1,100 popular talking-head vlogs found that B-roll
placement was strongly connected to nearby transcript concepts. Semantic
recommendations performed better than interval-only recommendations:

- https://arxiv.org/abs/1902.11216

Therefore the product uses a soft visual mix and semantic instructions in the
initial script prompt, not a hard runtime validator.

## Storyboard Rhythm

New AI-generated storyboard scripts use the dynamic pacing profile:

- 15 seconds: 6-8 visual beats;
- 20 seconds: 8-10 visual beats;
- 30 seconds: 11-15 visual beats;
- 45 seconds: 16-22 visual beats.

A visual beat is a semantic section of narration with its own visual state. A
visual change does not have to be B-roll: a medium talking shot followed by a
close whisper shot is a valid pattern interrupt.

Every storyboard follows these structural rules in the initial Gemini prompt:

- the first shot is talking;
- the last shot is talking;
- B-roll shots are never adjacent;
- approximately 35-45% of the spoken timeline may use B-roll, with 25-50% an
  acceptable soft range when the subject needs more or less demonstration;
- approximately 10-20% may show the selected presenter in a relevant action;
- approximately 15-30% may show a product, object, process, space, result, or
  immediately understandable visual analogy;
- these percentages are guidance, not quotas;
- presenter B-roll is used only when the action adds meaning;
- B-roll subject types should vary instead of repeatedly showing the
  presenter, the presenter's back, hands, food, or the same prop;
- every B-roll visual directly illustrates the exact speech assigned to it.

## Actor Continuity

Gemini describes only pose, position, gaze, expression, emotion, gesture,
movement, scene, lighting, and camera. It must not describe physical
appearance.

For every generated frame containing the presenter, the selected reference
image remains the only source of identity and appearance. Frame generation
must preserve the same face, hairstyle, body, outfit, jewelry, and accessories
while changing only staging and camera direction. The wording of the existing
frame prompt stays stable so approved paid-frame caches remain reusable.

For neutral B-roll (`actor_in_frame=false`), a clean English model prompt stays
available to the video model. If it binds the frame to an actor, presenter,
avatar, or reference photo, those identity bindings are removed from the
English prompt. If safe sanitization is impossible, the pipeline uses a neutral
English fallback instead of localized UI text. When no model prompt exists,
scene, action, and camera are sanitized before assembly, and the final automatic
prompt passes the same English-language guard. A prompt explicitly pinned by
the user remains user-owned.

The language guard uses explicit provenance instead of guessing from words.
Generated scripts retain their requested language, and model-generated English
frame prompts are tagged as English. For a non-English script, an untagged
automatic neutral B-roll prompt is treated as untrusted and replaced with the
neutral English fallback. This does not apply to a manual user prompt.

The normal-to-whisper transition remains supported as two talking beats:

1. a normal medium talking shot;
2. a closer hush/whisper talking shot using the same presenter appearance.

## Enforcement Boundary

The dynamic rhythm is prompt-only. The pipeline must not:

- run a local semantic sequence validator;
- make a second Gemini request to repair B-roll selection or ordering;
- convert excess or adjacent B-roll into talking shots;
- reject a generated storyboard because its B-roll ratio differs from the
  soft target;
- alter an existing or custom storyboard automatically.

Existing parser-recovery behavior for malformed or truncated JSON remains
unchanged because it is transport recovery, not creative correction.

## Compatibility

The profile applies only to newly generated AI storyboard scripts. Existing
saved scripts, approved frames, cached voiceovers, and generated clips are not
invalidated.

The generated script stores `storyboard_pacing: "dynamic"` and its requested
language as provenance. Model-generated frame prompts store internal English
provenance. Custom scripts do not receive the dynamic pacing field.

## Testing

Tests use mocked Gemini responses and must not call Gemini, fal.ai,
ElevenLabs, or any other paid provider. They cover:

- dynamic visual-beat ranges for all duration presets;
- the prompt's soft B-roll mix and non-adjacency rules;
- mandatory talking first and last shots;
- variation between presenter and non-presenter B-roll;
- the absence of any automatic B-roll refinement call;
- dynamic provenance on AI-generated storyboard scripts only;
- the existing actor-reference-only appearance contract.

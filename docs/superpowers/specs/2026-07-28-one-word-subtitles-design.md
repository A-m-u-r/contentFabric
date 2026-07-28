# One-word subtitles

## Goal

Show exactly one spoken word at a time in every generated video so captions
change at speech rhythm instead of appearing in two- or three-word groups.

## Scope

- Apply to both `generate_tiktok_subs` and
  `generate_storyboard_ass_subtitles`.
- Apply to the classic pipeline and Storyboard V3.
- Do not add a UI setting. One word is the product default everywhere.
- Keep the grouping helper configurable for internal callers and tests, but all
  production entry points must request one word.

## Caption behavior

- Each ASS dialogue event contains one lexical word.
- Punctuation remains attached to its word and does not become a separate event.
- Emoji and pictographs continue to be removed.
- Start and end times come from the aligned ASR word.
- Events must not overlap.
- Existing pop-in animation, font, outline, shadow, safe-zone position and
  uppercase treatment remain unchanged.
- Storyboard keyword accents remain active: a matching single-word caption is
  colored; other words stay white.
- Hook and overlay plates remain disabled.

## Compatibility and failures

- Existing empty-transcription behavior remains unchanged.
- The public Python functions retain `max_words` for backward compatibility,
  with a default of `1`.
- Production call sites explicitly pass `max_words=1` so a future default
  change cannot silently restore grouped captions.

## Verification

- Unit-test one ASS event per input word in both subtitle generators.
- Test that punctuation stays attached and no standalone punctuation event is
  created.
- Keep the existing style, safe-zone and keyword-highlight tests passing.
- Rebuild the latest reel from cached video, master audio and regenerated ASS
  subtitles without TTS or fal.ai calls.
- Inspect adjacent subtitle frames and verify the final MP4 dimensions, audio
  track and duration.

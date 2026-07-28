# Avatar Speech-Onset Slicing

## Goal

Prevent a Kling Avatar talking shot from opening on dead air. The master
voiceover remains untouched; only render-time visual and per-model audio slice
boundaries move.

## Timeline

Before splitting long shots, inspect every internal boundary that opens a
talking shot. Find the earliest credible speech onset from:

- the decoded audio energy mask;
- the first aligned ASR word inside that shot.

Use the earlier valid onset and retain 40 ms of technical preroll. If this is
later than the manifest boundary, move the shared boundary forward:

- the previous visual receives the pause;
- the talking shot and the audio sent to Kling start immediately before speech;
- slices still tile the whole master voiceover without gaps or overlaps.

The first shot cannot hand its leading pause to an earlier visual and therefore
keeps its original start.

## Cache Behavior

Changing a B-roll slice's audio bounds must not invalidate its video merely
because its unused diagnostic audio slice changed. Kling V3 cache validation
continues to decide whether the existing video covers the new rounded duration.
Talking clips remain invalidated when their audio slice changes.

## Reference Frames

Every newly staged talking reference explicitly asks for a still moment before
speech: calm neutral expression, lips gently closed and resting together.
Existing user-approved frames remain authoritative and are not regenerated
automatically.

## Tests

- A manifest boundary followed by dead air moves to 40 ms before speech.
- The pause extends the preceding B-roll and all slices still tile the track.
- A first talking shot keeps its original start.
- A changed B-roll audio slice does not delete a reusable video.
- A changed talking audio slice still invalidates its lip-synced video.
- The avatar reference prompt requires naturally closed lips.

No test or verification invokes FAL.

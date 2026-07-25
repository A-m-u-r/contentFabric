# Content-plan workspaces and storyboard quality

**Date:** 2026-07-25  
**Status:** Approved  

## Goal

Fix four connected failures in AI Shorts:

1. The displayed duration must reflect the narration that will actually be voiced.
2. Hooks must not begin with the same small set of canned phrases.
3. Every content-plan item must keep its own generation progress.
4. B-roll must illustrate the exact spoken claim instead of defaulting to generic wellness imagery.

## Decisions

### Duration

The final video is driven by the generated voiceover, so an LLM-provided
`duration_seconds` is advisory and must not be shown as authoritative.

- Before TTS, derive an estimated duration from the current spoken text.
- Show the estimate with an approximation marker.
- After TTS or completed generation, store and show the measured audio duration.
- Use the same duration source for cards, cost estimates, and the storyboard header.
- Do not mechanically stretch or trim content to match the LLM's declared duration.

### Hooks

Remove the mandatory Russian preamble chosen from three examples. The first
spoken words must carry the actual hook.

- If a content-plan item supplies a hook, use it as the opening without a preface.
- Otherwise choose from a taxonomy: result-first, costly mistake, contradiction,
  concrete fact, pain question, confession/demo, or open loop.
- In a generated batch, every script must use a different hook type and must not
  repeat the same first three normalized words.
- Keep hooks short enough for the first 1.5-3 seconds and place the hook overlay
  on the first frame.
- Validate generated batches and retry once when duplicate openings are detected.

### Per-video workspace persistence

Use a hybrid model: account-scoped persistence on the backend plus localStorage
as an immediate fallback.

Each generated content-plan item receives a stable `item_id`. A workspace is
identified by `(user_id, business_profile_id, item_id)` and stores:

- the original plan item;
- current wizard step;
- business analysis and web research;
- all generated script variants;
- selected script;
- storyboard edits and generated frame/clip references;
- generation job id and latest result;
- update timestamp and a monotonically increasing revision.

The browser writes to the local workspace immediately and then asynchronously
upserts the same snapshot on the backend. On open:

1. Load the local snapshot immediately.
2. Fetch the account snapshot.
3. Keep the snapshot with the newer revision/update timestamp.
4. Never replace a newer local snapshot with an older server response.

Unauthenticated users keep local-only workspaces. Deleting or rebuilding a
content plan does not silently delete existing workspaces.

The content-plan UI displays item status: not started, script saved, frames
generated, video generated, or failed.

### Semantically aligned B-roll

B-roll planning must begin from the exact speech, not from broad product
keywords.

For every B-roll shot the text model must:

1. Extract the single claim being spoken.
2. Select either a literal demonstration or one clear visual analogy.
3. Explain the claim through one concrete action/change visible in the shot.
4. Reject generic imagery that could fit an unrelated line in the same niche.

People may appear only when the concept needs them, with no identifiable face
unless an actor reference is available. Faceless/profile/back views and
match-cuts are allowed. Readable generated text remains forbidden; numeric
claims can be added later as deterministic overlay graphics.

Example:

- Speech: "Метаболизм естественно замедляется на пару процентов каждые десять лет."
- Good visual: matched faceless shots of the same woman at several life stages
  walking at a subtly slower pace, or an analog metronome slowing slightly.
- Bad visual: avocado preparation, generic salad, kitchen decor, or a scale with
  an unreadable generated display.

A batched text-only refinement pass reviews all B-roll shots after script
generation. It receives the exact speech, neighboring shots, and proposed
visual; it replaces only semantically weak B-roll descriptions and prompts.

## Backend changes

- Add a `content_workspaces` SQLite table with a unique key over user, profile,
  and item.
- Add authenticated list/get/upsert/delete endpoints.
- Enforce ownership through `user_id` on every query.
- Limit snapshot size and validate that the payload is a JSON object.
- Add a batch hook-quality validator and B-roll refinement helper.
- Return measured duration in generation results and preserve it in workspace
  snapshots.

## Frontend changes

- Add stable ids to new and legacy content-plan items.
- Pass a structured pending content-plan context into AI Shorts.
- Replace the single global cache with an active workspace cache key.
- Persist edits, generated scripts, frames, job status, and result for the active
  item.
- Synchronize local snapshots with the authenticated backend.
- Restore the correct workspace when returning to any content-plan item.
- Derive duration from narration everywhere before audio exists.
- Display progress badges in the content plan.

## Error handling

- Local persistence must continue when backend sync fails.
- Server errors are non-destructive and may be retried on the next edit/open.
- Concurrent updates use a client revision; an older revision cannot overwrite
  a newer one.
- A malformed workspace snapshot is rejected with HTTP 400.
- Duplicate hook validation retries generation once, then returns the best batch
  with a warning rather than dropping all scripts.
- B-roll refinement failure keeps the original storyboard editable and reports a
  non-blocking warning.

## Tests

### Backend

- Workspace ownership, upsert, revision ordering, retrieval, and deletion.
- Anonymous requests cannot access account workspaces.
- Duplicate hook openings trigger one retry.
- Distinct hook openings pass without retry.
- B-roll refinement receives exact speech and replaces an unrelated visual.
- Duration metadata is derived from narration rather than trusted LLM output.

### Frontend

- Different content-plan items produce different workspace keys.
- Opening an existing item restores its scripts instead of the global last one.
- Local save happens before backend synchronization.
- A stale server snapshot does not replace a newer local snapshot.
- Script cards use narration-derived duration, not `script.duration_seconds`.
- Content-plan items show their saved generation stage.

## Out of scope

- Social-platform retention analytics and CRM attribution.
- Automatic generated text or numeric labels inside B-roll imagery.
- Training a custom hook or B-roll model.
- Cross-user collaboration on one workspace.

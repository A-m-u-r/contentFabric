# Prompt-scoped Frame Moderation Memory

## Goal

Prevent duplicate paid image-edit requests only when the vendor explicitly confirmed moderation for the same photo, model, and prompt. Never retry, switch models, or spend money without a new explicit user action.

## Current Problem

The backend currently stores only model IDs in `<photo>.blank_models.json`. Any flat or black result is treated as moderation and permanently blocks that model for the photo, regardless of the prompt or whether fal returned a moderation flag. This can preserve a false technical failure indefinitely and makes the UI overstate the cause.

## Chosen Design

Replace the unscoped list with versioned records. Each confirmed refusal stores:

- model ID;
- SHA-256 fingerprint of the exact prompt;
- a stable fingerprint of the conditioning photo content;
- the explicit moderation fields returned by fal;
- record creation time.

A request is skipped only when all three fingerprints match: photo content, model, and prompt. A different prompt or changed photo remains eligible for a manual request.

Legacy JSON arrays of model IDs contain neither prompt identity nor proof of moderation. They are treated as unverified history and do not block requests. The existing legacy memo for the current actor photo may remain on disk because the new reader ignores it; no API request is triggered during migration.

## Explicit Moderation Rule

A blank result is persisted only when fal explicitly reports moderation. The accepted evidence is a truthy moderation field such as `has_nsfw_concepts` or `nsfw_content_detected`, or a structured vendor error whose field and value explicitly identify safety/moderation blocking.

A blank image without explicit moderation evidence remains a failed paid generation for the current run, but it is not remembered as a future block. Endpoint errors, network failures, missing images, and generic text errors are never stored as moderation records.

## Request and Billing Flow

1. The user manually starts frame generation or manually selects a replacement model.
2. Before calling fal, the backend checks for a matching confirmed moderation record.
3. If a matching record exists, the backend returns a `known` block without a paid call.
4. If no matching record exists, the backend performs exactly one request to the user-selected model.
5. The backend never automatically retries the same model and never falls back to another image editor.
6. If the result is blank and explicit moderation evidence is present, the backend records the scoped refusal and reports the paid blocked attempt.
7. If the result is blank without such evidence, the backend reports a technical blank result without creating a persistent block.

Changing code, restarting services, reading or migrating memo files, and opening the modal must never call fal.

## UI Behaviour

The existing replacement-model modal remains a manual decision point. Previously refused alternatives are disabled only when the refusal matches the current photo and prompt. A legacy unverified refusal does not disable a model.

The modal must distinguish:

- confirmed moderation;
- a matching refusal remembered from a previous paid request;
- an unclassified blank/technical generation failure;
- an unavailable endpoint;
- an unreachable service.

Selecting an enabled model is the only action in the modal that may start another paid request. Closing the modal has no side effects.

## Compatibility and Data Safety

The reader accepts both the new versioned object and legacy arrays. Legacy arrays are ignored for blocking and are not destructively deleted. New writes use only the versioned format and preserve valid existing versioned records under the memo lock.

Corrupt or unreadable memo files fail open: the request is allowed only after an explicit user action, and the file is not trusted as evidence of moderation.

## Tests

Backend tests must prove:

- a legacy model-only memo does not block a request;
- a confirmed moderation record blocks the same model, photo, and prompt without calling fal;
- the same photo and model with a different prompt is not blocked;
- changed photo content at the same path is not blocked;
- a blank result with explicit moderation evidence is persisted;
- a blank result without explicit moderation evidence is not persisted;
- no automatic fallback model is called;
- a remembered block records zero new paid calls.

Frontend tests must prove that the modal does not invoke `onPick` on render or close and invokes it only after a user clicks an enabled model.

## Non-goals

- Automatically retrying a failed model.
- Automatically choosing a replacement model.
- Bypassing vendor moderation.
- Refunding earlier paid blank generations.
- Changing fal pricing or billing accounting.

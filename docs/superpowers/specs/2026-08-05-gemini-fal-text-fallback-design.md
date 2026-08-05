# Gemini via fal.ai Text Fallback Design

## Context

`POST /api/saasshorts/analyze` currently sends all text-generation requests directly to the Google Gen AI API. The selected `pro` preset resolves to `gemini-3.1-pro-preview`; when the saved Google project has no quota, Google returns `429 RESOURCE_EXHAUSTED`. The existing direct-Google model chain can then try Flash variants, but those requests still use the same exhausted Google project and therefore cannot provide a reliable fallback.

The application already stores and resolves a server-side fal.ai key and already has a queue client for fal.ai media requests. fal.ai exposes the text endpoint `openrouter/router`, which can route paid requests to Google Gemini models and returns generated text plus usage and cost metadata.

## Goal

Keep direct Google as the first provider, but make SaaS Shorts analysis continue through paid Gemini models on fal.ai when the direct Google request has exhausted quota or is temporarily unavailable.

The approved Pro chain is:

1. Direct Google `gemini-3.1-pro-preview`.
2. fal.ai `openrouter/router` with `google/gemini-3.1-pro-preview`.
3. fal.ai `openrouter/router` with `google/gemini-3-flash-preview` only when the fal.ai Pro attempt fails with a retryable provider error and returns no usable output.

## Scope

The first implementation applies only to the text calls made as part of `POST /api/saasshorts/analyze`:

- optional URL research;
- product analysis;
- script generation.

Other Gemini-powered endpoints keep their current behavior. Image, video, voice, and moderation provider routing are unchanged.

## Provider and model routing

Introduce an analysis-scoped text generation context carrying the optional fal.ai key and a small provider router used by the existing Gemini helper.

For the `pro` preset, the router uses the approved chain exactly. It does not insert a direct-Google Flash call between direct Pro and fal.ai Pro, because that would lower quality while continuing to use the same exhausted Google quota.

For the `fast` preset, use:

1. the configured direct Google fast model;
2. fal.ai `google/gemini-3-flash-preview`;
3. fal.ai `google/gemini-2.5-flash` after a retryable fal.ai error with no usable output.

An explicit `gemini-*` model id is tried directly first, then mapped to the corresponding `google/gemini-*` OpenRouter id when available, with `google/gemini-3-flash-preview` as the final temporary-error fallback.

The fal.ai endpoint id and model ids remain environment-configurable, with these defaults:

- endpoint: `openrouter/router`;
- Pro: `google/gemini-3.1-pro-preview`;
- quality fallback: `google/gemini-3-flash-preview`;
- economical fast fallback: `google/gemini-2.5-flash`.

## Fallback eligibility

A paid fal.ai request is allowed automatically only after the direct Google request has exhausted its bounded retries and ended with a retryable availability error, including:

- `429`, `RESOURCE_EXHAUSTED`, or rate-limit errors;
- `503`, `UNAVAILABLE`, or high-demand errors;
- connection and timeout failures.

The router must not spend fal.ai balance for definitive request failures such as invalid authentication, invalid prompt/configuration, permission errors, or other non-retryable 4xx responses.

## Paid-call boundary

Each logical text step may enqueue at most one fal.ai Pro request. fal.ai Flash may be enqueued only if the Pro request fails with a retryable provider error before producing usable output.

Once fal.ai returns generated text, malformed JSON, validation failure, or an application-level quality failure must not cause an automatic second paid provider request. The current caller may return the error or retain a previously valid result; a new paid generation then requires a new user action.

Queue submission must not be blindly retried after an ambiguous response, because that could enqueue duplicate paid jobs. Connection retries are allowed only when it is known that the request did not reach fal.ai, following the existing `_fal_run` safety rule.

## Request and key handling

`POST /api/saasshorts/analyze` accepts the existing `X-Fal-Key` header in addition to `X-Gemini-Key`. The dashboard includes `X-Fal-Key` when the user supplied an unmanaged key. Saved and platform keys continue to be resolved only on the server through `resolve_effective_api_key`.

The fal.ai key is optional at request start. Direct Google is attempted even when no fal.ai key is configured. If Google becomes eligible for fallback but no fal.ai key is available, return a clear `503` message explaining that Google quota is exhausted and the fal.ai fallback key is missing. Do not expose either provider key in logs or responses.

When `use_platform_keys` is enabled, the endpoint resolves both provider keys under the existing active-subscription rules. When user-owned keys are enabled, it prefers the saved fal.ai key and then the request header, matching current vault behavior.

## Response adaptation

Add a minimal response adapter for fal.ai text output that exposes `.text`, so existing JSON extraction and script validation continue to work without provider-specific branches throughout the pipeline.

The fal.ai `openrouter/router` request contains:

- the existing prompt text;
- the selected OpenRouter model id;
- temperature and maximum output tokens translated from the Google config when present;
- no reasoning output unless explicitly needed;
- web search enabled for the URL-research step, because its prompt requires real sources.

Direct Google grounding metadata remains available on direct success. fal.ai research may not provide the same candidate metadata shape, so `grounding_sources` may be empty while the generated research remains available. This limitation must not break the response schema.

## Error behavior and observability

Log provider transitions, model ids, fal.ai request ids, and final failure categories without logging prompts or secrets. Logs should make the sequence visible, for example:

`direct_google:gemini-3.1-pro-preview -> fal:google/gemini-3.1-pro-preview`

If every eligible provider fails, surface a `GeminiTemporaryError` and return HTTP `503`, not a generic `500`. The user-facing detail should distinguish these cases:

- fal.ai fallback key missing;
- fal.ai balance/authentication problem;
- all configured Google providers temporarily unavailable.

## Testing

Add focused tests covering:

1. Direct Google success never calls fal.ai.
2. Direct Google quota exhaustion calls fal.ai Pro with the original prompt.
3. A non-retryable Google error never calls fal.ai.
4. A retryable fal.ai Pro failure with no output calls fal.ai Flash once.
5. Returned but malformed fal.ai text does not trigger an automatic second paid call.
6. Missing fal.ai key after Google quota exhaustion returns a clear `503`.
7. Saved, header, and platform fal.ai key resolution follows the existing vault rules.
8. The fal.ai response adapter remains compatible with existing JSON parsing.
9. URL research enables fal.ai web search and tolerates absent Google grounding metadata.
10. Existing direct-Google and custom-script paths remain unchanged.

## Non-goals

- Replacing Google with fal.ai for every request.
- Falling back to non-Google language models.
- Changing image/video model routing or moderation retry behavior.
- Automatically repeating a paid call after malformed or low-quality generated content.
- Building new billing UI in this change.

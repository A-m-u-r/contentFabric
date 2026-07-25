# Content-plan Workspaces and Story Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve each content-plan video's progress independently and correct duration, hook diversity, and B-roll semantic alignment.

**Architecture:** Store a versioned workspace snapshot under the authenticated user, business profile, and stable content-plan item id, while mirroring it in localStorage for immediate recovery. Keep duration and story-quality logic in the backend, with small frontend helpers for workspace identity, merge policy, stage display, and narration-derived estimates.

**Tech Stack:** FastAPI, Pydantic, SQLite, Python unittest, React 18, localStorage, Vite.

## Global Constraints

- An older server revision must never overwrite a newer local snapshot.
- Unauthenticated users remain functional with local-only persistence.
- The LLM-provided `duration_seconds` is never authoritative.
- Existing content-plan workspaces survive plan regeneration.
- Generated text inside B-roll imagery remains forbidden.
- No new runtime dependency is added.

---

### Task 1: Account-scoped workspace storage

**Files:**
- Modify: `app.py`
- Create: `tests/test_content_workspaces.py`

**Interfaces:**
- Produces: `save_content_workspace(user_id, profile_id, item_id, revision, stage, snapshot) -> dict`
- Produces: `get_content_workspace(user_id, profile_id, item_id) -> Optional[dict]`
- Produces: `list_content_workspace_summaries(user_id, profile_id) -> list[dict]`
- Produces: `DELETE/GET/PUT /api/user/content-workspaces/...`

- [ ] **Step 1: Write failing persistence and ownership tests**

```python
def test_newer_workspace_revision_wins(self):
    first = save_content_workspace(self.user_id, self.profile_id, "item-1", 2, "script", {"scripts": [1]})
    stale = save_content_workspace(self.user_id, self.profile_id, "item-1", 1, "not_started", {})
    self.assertEqual(stale["revision"], 2)
    self.assertEqual(stale["snapshot"]["scripts"], [1])
```

- [ ] **Step 2: Run the tests and confirm failure**

Run: `python -m unittest tests.test_content_workspaces -v`
Expected: import or table/function failures.

- [ ] **Step 3: Add the table and repository functions**

```sql
CREATE TABLE IF NOT EXISTS content_workspaces (
    user_id TEXT NOT NULL,
    business_profile_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    stage TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, business_profile_id, item_id)
)
```

- [ ] **Step 4: Add authenticated endpoints and payload limits**

```python
class ContentWorkspaceRequest(BaseModel):
    revision: int
    stage: str = "not_started"
    snapshot: Dict[str, Any]
```

Reject non-object snapshots, revisions below one, and serialized payloads above 2 MiB. Verify the business profile belongs to the authenticated user.

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_content_workspaces -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_content_workspaces.py
git commit -m "Add account-scoped content workspaces"
```

### Task 2: Local workspace identity and content-plan status

**Files:**
- Create: `dashboard/src/lib/contentPlanWorkspaces.js`
- Modify: `dashboard/src/lib/businessProfiles.js`
- Modify: `dashboard/src/components/ContentPlanTab.jsx`
- Modify: `tests/test_ui_layout_polish.py`

**Interfaces:**
- Produces: `ensurePlanItemIds(items) -> items`
- Produces: `workspaceStorageKey(context) -> string`
- Produces: `loadLocalWorkspace(context) -> object|null`
- Produces: `saveLocalWorkspace(context, snapshot) -> object`
- Produces: `chooseNewestWorkspace(local, remote) -> object|null`
- Produces: `workspaceStage(snapshot) -> string`
- Produces: pending context `{profileId, itemId, item, topic}`

- [ ] **Step 1: Add failing source-contract tests**

```python
def test_content_plan_uses_item_scoped_workspaces(self):
    plan = CONTENT_PLAN.read_text(encoding="utf-8")
    helpers = WORKSPACES.read_text(encoding="utf-8")
    self.assertIn("ensurePlanItemIds", plan)
    self.assertIn("workspaceStorageKey", helpers)
    self.assertIn("chooseNewestWorkspace", helpers)
    self.assertIn("setPendingContentPlanItem", plan)
```

- [ ] **Step 2: Run the test and confirm failure**

Run: `python -m unittest tests.test_ui_layout_polish -v`
Expected: missing helper and pending-context failures.

- [ ] **Step 3: Implement stable ids and local snapshot merge**

```javascript
export function chooseNewestWorkspace(local, remote) {
  if (!local) return remote || null;
  if (!remote) return local;
  if ((local.revision || 0) !== (remote.revision || 0)) {
    return (local.revision || 0) > (remote.revision || 0) ? local : remote;
  }
  return String(local.updatedAt || '') >= String(remote.updatedAt || '') ? local : remote;
}
```

- [ ] **Step 4: Hydrate before navigation and show progress**

On content-plan item click, retrieve the server workspace when authenticated,
merge it with local state, store the winner locally, set the structured pending
context, and navigate to AI Shorts. Display a compact saved-stage badge.

- [ ] **Step 5: Run tests and build**

Run: `python -m unittest tests.test_ui_layout_polish -v`
Run: `npm run build --prefix dashboard`
Expected: tests and build pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/contentPlanWorkspaces.js dashboard/src/lib/businessProfiles.js dashboard/src/components/ContentPlanTab.jsx tests/test_ui_layout_polish.py
git commit -m "Track progress per content-plan item"
```

### Task 3: AI Shorts workspace restore and server synchronization

**Files:**
- Modify: `dashboard/src/components/SaaShortsTab.jsx`
- Modify: `tests/test_ui_layout_polish.py`

**Interfaces:**
- Consumes: Task 2 workspace helper functions.
- Produces: active per-item cache key, debounced server upsert, per-item job key.

- [ ] **Step 1: Add failing restore/sync contract tests**

```python
def test_ai_shorts_uses_active_content_workspace(self):
    tab = SAAS_SHORTS.read_text(encoding="utf-8")
    self.assertIn("activeWorkspaceKey", tab)
    self.assertIn("queueWorkspaceSync", tab)
    self.assertIn("workspaceLastJobKey", tab)
    self.assertIn("pendingContentPlanItem", tab)
```

- [ ] **Step 2: Run the test and confirm failure**

Run: `python -m unittest tests.test_ui_layout_polish -v`
Expected: missing active-workspace behavior.

- [ ] **Step 3: Parameterize cache and last-job helpers**

```javascript
function loadCache(cacheKey = CACHE_KEY) { /* read cacheKey */ }
function saveCache(cacheKey, input, analysis, webResearch, scripts) { /* return saved snapshot */ }
function workspaceLastJobKey(cacheKey) { return `${cacheKey}:last_job`; }
```

- [ ] **Step 4: Restore the active item and debounce backend writes**

Use the pending content-plan context before state initialization. Save locally
synchronously, queue a 400 ms authenticated PUT, and flush the latest queued
snapshot on unmount with `keepalive: true`.

- [ ] **Step 5: Persist stage, selected script, job, and result**

Store `step`, `selectedScript`, `jobId`, `genStatus`, and `genResult` alongside
analysis and scripts. Reset removes only the active item workspace.

- [ ] **Step 6: Run tests and build**

Run: `python -m unittest tests.test_ui_layout_polish -v`
Run: `npm run build --prefix dashboard`
Expected: tests and build pass.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/SaaShortsTab.jsx tests/test_ui_layout_polish.py
git commit -m "Restore and sync AI Shorts workspaces"
```

### Task 4: Honest duration and diverse hooks

**Files:**
- Modify: `saasshorts.py`
- Modify: `dashboard/src/components/SaaShortsTab.jsx`
- Modify: `tests/test_saasshorts_voiceover.py`
- Modify: `tests/test_ui_layout_polish.py`

**Interfaces:**
- Produces: `_script_spoken_text(script) -> str`
- Produces: `_estimate_speech_duration(text) -> int`
- Produces: `_hook_opening(script, words=3) -> str`
- Extends: `_request_gemini_script_batch(..., batch_validator=None)`

- [ ] **Step 1: Add failing tests**

```python
def test_generated_duration_is_recomputed_from_spoken_text(self):
    scripts = self._scripts_from_response('[{"duration_seconds":21,"shots":[{"speech":"one two three four five"}]}]')
    self.assertNotEqual(scripts[0]["duration_seconds"], 21)

def test_duplicate_hook_openings_trigger_retry(self):
    self.assertEqual(mock_client.models.generate_content.call_count, 2)
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m unittest tests.test_saasshorts_voiceover -v`
Expected: stale duration and single-call duplicate-hook failures.

- [ ] **Step 3: Normalize duration from narration**

Use the same words/tags/pauses formula as the frontend. Recompute
`duration_seconds` after parsing and set `duration_source` to
`narration_estimate`.

- [ ] **Step 4: Replace canned preambles with hook taxonomy**

Explicitly forbid filler openings. Require distinct hook types and distinct
first-three-word prefixes in a batch. If `Хук:` exists in the topic, script one
starts directly with it.

- [ ] **Step 5: Add batch validation and one retry**

Pass a validator into `_request_gemini_script_batch`; rank a valid diverse batch
above a duplicate batch while retaining malformed-JSON recovery.

- [ ] **Step 6: Make every UI duration narration-derived**

Replace the script-card use of `script.duration_seconds` with
`estimateStoryboardSeconds(script)` and label it as approximate.

- [ ] **Step 7: Run tests**

Run: `python -m unittest tests.test_saasshorts_voiceover tests.test_ui_layout_polish -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add saasshorts.py dashboard/src/components/SaaShortsTab.jsx tests/test_saasshorts_voiceover.py tests/test_ui_layout_polish.py
git commit -m "Derive duration and diversify script hooks"
```

### Task 5: Speech-grounded B-roll refinement

**Files:**
- Modify: `saasshorts.py`
- Modify: `tests/test_saasshorts_storyboard.py`

**Interfaces:**
- Produces: `refine_storyboard_broll_alignment(scripts, gemini_key, text_model=None) -> list`
- Consumes: normalized storyboard scripts from Task 4.

- [ ] **Step 1: Add a failing refinement test**

```python
def test_broll_refinement_replaces_unrelated_avocado_visual(self):
    scripts = [{"shots": [{
        "shot_number": 3,
        "visual_type": "broll",
        "speech": "Метаболизм замедляется с возрастом.",
        "scene": "Руки режут авокадо",
        "generation_prompt": "hands slicing avocado",
    }]}]
    refined = refine_storyboard_broll_alignment(scripts, "key")
    self.assertIn("возраст", refined[0]["shots"][0]["scene"].lower())
    self.assertNotIn("avocado", refined[0]["shots"][0]["generation_prompt"].lower())
```

- [ ] **Step 2: Run the test and confirm failure**

Run: `python -m unittest tests.test_saasshorts_storyboard -v`
Expected: missing refinement helper.

- [ ] **Step 3: Implement one batched semantic review call**

Send exact speech, current visual, and neighboring speech. Ask for replacements
only when the proposed visual fails the unrelated-niche test. Allow faceless
human actions when conceptually necessary; forbid generic wellness filler.

- [ ] **Step 4: Invoke refinement after storyboard parsing**

Run it after shot normalization and before returning scripts. Failure logs a
warning and preserves the editable original storyboard.

- [ ] **Step 5: Update shot-fill and scene-rebuild prompts**

Pass exact speech and replace `no people` with `no identifiable faces unless an
actor reference is available`. Require literal demonstration or one clear
visual analogy.

- [ ] **Step 6: Run tests**

Run: `python -m unittest tests.test_saasshorts_storyboard tests.test_saasshorts_quality -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add saasshorts.py tests/test_saasshorts_storyboard.py
git commit -m "Ground B-roll prompts in spoken claims"
```

### Task 6: Full verification

**Files:**
- Verify only.

- [ ] **Step 1: Run backend test suite**

Run: `python -m unittest discover -s tests -v`
Expected: all tests pass.

- [ ] **Step 2: Run frontend checks**

Run: `npm run lint --prefix dashboard`
Run: `npm run build --prefix dashboard`
Expected: lint and build pass.

- [ ] **Step 3: Inspect the content-plan flow**

Open three content-plan items, generate or edit scripts, switch among them, and
verify each restores its own title, shots, selected stage, and status badge.

- [ ] **Step 4: Verify duration and prompt examples**

Confirm the metabolism example shows a narration-derived estimate, contains no
canned preamble, and proposes age/pace/analog-change B-roll rather than avocado.

- [ ] **Step 5: Commit any verification-only test adjustment**

Stage only files changed for this feature and use a focused commit message.

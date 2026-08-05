# Prompt-scoped Frame Moderation Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remember only vendor-confirmed moderation for the same photo content, model, and prompt, while ensuring every paid image-editor request starts from an explicit user click.

**Architecture:** Keep the memo beside the actor photo, but replace the legacy model-ID array with a versioned record object keyed by SHA-256 photo and prompt fingerprints. The backend owns moderation classification and scoped blocking; the modal consumes prompt-scoped alternatives and remains a purely manual trigger.

**Tech Stack:** Python 3.11, `unittest`, FastAPI backend helpers in `saasshorts.py`, React 18, Vite 4, Node's built-in test runner.

## Global Constraints

- Never retry an image editor or switch editors automatically.
- Never call fal while reading/migrating memo files, rendering/closing the modal, restarting services, or running tests.
- One manual selection may call exactly one user-selected image editor.
- Persist a refusal only when fal returns explicit, truthy moderation evidence.
- Match a remembered refusal only on photo SHA-256 + model ID + prompt SHA-256.
- Treat legacy arrays and corrupt memos as unverified and non-blocking; do not delete them destructively.
- Add no frontend test dependency; use the installed Vite transformer and Node test runner.
- Preserve all pre-existing dirty-worktree edits. Do not stage or commit an entire already-modified file unless its unrelated changes have been excluded.

---

### Task 1: Versioned, prompt-scoped moderation records

**Files:**
- Modify: `saasshorts.py:7468-7503`
- Test: `tests/test_saasshorts_storyboard.py:825-1094`

**Interfaces:**
- Produces: `_photo_fingerprint(photo_path: str) -> str`
- Produces: `_prompt_fingerprint(prompt: str) -> str`
- Produces: `_read_moderation_memo(photo_path: str) -> dict`
- Produces: `_models_that_blanked(photo_path: str, prompt: str) -> set[str]`
- Produces: `_remember_confirmed_moderation(photo_path: str, model: str, prompt: str, flags: dict) -> None`
- Memo schema: `{"version": 2, "records": [{"model": str, "photo_sha256": str, "prompt_sha256": str, "flags": dict, "created_at": str}]}`

- [ ] **Step 1: Write failing tests for legacy and corrupt memos**

```python
def test_legacy_model_only_memo_does_not_block_a_paid_request(self):
    with tempfile.TemporaryDirectory() as tmp:
        photo = os.path.join(tmp, "actor.png")
        self._write_png(photo, [[[10, 20, 30]]])
        with open(f"{photo}.blank_models.json", "w", encoding="utf-8") as memo:
            json.dump([saasshorts.DEFAULT_AVATAR_EDIT_MODEL], memo)
        self.assertEqual(saasshorts._models_that_blanked(photo, "new prompt"), set())

def test_corrupt_memo_fails_open(self):
    with tempfile.TemporaryDirectory() as tmp:
        photo = os.path.join(tmp, "actor.png")
        self._write_png(photo, [[[10, 20, 30]]])
        with open(f"{photo}.blank_models.json", "w", encoding="utf-8") as memo:
            memo.write("not json")
        self.assertEqual(saasshorts._models_that_blanked(photo, "prompt"), set())
```

- [ ] **Step 2: Run the legacy tests and verify RED**

Run: `python -m unittest tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_legacy_model_only_memo_does_not_block_a_paid_request tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_corrupt_memo_fails_open -v`

Expected: FAIL because `_models_that_blanked` does not accept a prompt and still trusts the legacy array.

- [ ] **Step 3: Write failing tests for exact prompt/photo matching**

```python
def test_confirmed_moderation_matches_only_same_photo_model_and_prompt(self):
    with tempfile.TemporaryDirectory() as tmp:
        photo = os.path.join(tmp, "actor.png")
        self._write_png(photo, [[[10, 20, 30], [40, 50, 60]]])
        model = saasshorts.DEFAULT_AVATAR_EDIT_MODEL
        flags = {"has_nsfw_concepts": [True]}
        saasshorts._remember_confirmed_moderation(photo, model, "prompt A", flags)
        self.assertEqual(saasshorts._models_that_blanked(photo, "prompt A"), {model})
        self.assertEqual(saasshorts._models_that_blanked(photo, "prompt B"), set())
        self._write_png(photo, [[[70, 80, 90], [100, 110, 120]]])
        self.assertEqual(saasshorts._models_that_blanked(photo, "prompt A"), set())
```

- [ ] **Step 4: Run the matching test and verify RED**

Run: `python -m unittest tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_confirmed_moderation_matches_only_same_photo_model_and_prompt -v`

Expected: FAIL because `_remember_confirmed_moderation` does not exist.

- [ ] **Step 5: Implement the minimal versioned store**

```python
def _photo_fingerprint(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _prompt_fingerprint(prompt: str) -> str:
    return hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()

def _read_moderation_memo(photo_path: str) -> dict:
    try:
        with open(_blank_model_memo(photo_path), encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict) or data.get("version") != 2:
        return {}
    if not isinstance(data.get("records"), list):
        return {}
    return data

def _models_that_blanked(photo_path: str, prompt: str) -> set:
    data = _read_moderation_memo(photo_path)
    if data.get("version") != 2:
        return set()
    try:
        photo_sha = _photo_fingerprint(photo_path)
    except OSError:
        return set()
    prompt_sha = _prompt_fingerprint(prompt)
    return {
        record["model"] for record in data.get("records", [])
        if isinstance(record, dict)
        if record.get("photo_sha256") == photo_sha
        and record.get("prompt_sha256") == prompt_sha
        and record.get("model")
    }

def _remember_confirmed_moderation(photo_path: str, model: str, prompt: str, flags: dict) -> None:
    memo_path = _blank_model_memo(photo_path)
    with _BLANK_MEMO_LOCK:
        data = _read_moderation_memo(photo_path)
        records = list(data.get("records", []))
        photo_sha = _photo_fingerprint(photo_path)
        prompt_sha = _prompt_fingerprint(prompt)
        records = [record for record in records if not (
            isinstance(record, dict)
            and record.get("model") == model
            and record.get("photo_sha256") == photo_sha
            and record.get("prompt_sha256") == prompt_sha
        )]
        records.append({
            "model": model,
            "photo_sha256": photo_sha,
            "prompt_sha256": prompt_sha,
            "flags": flags,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        temporary = f"{memo_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as target:
                json.dump({"version": 2, "records": records}, target, ensure_ascii=False)
            os.replace(temporary, memo_path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
```

Add `from datetime import datetime, timezone` near the imports. The sibling temporary file and `os.replace` ensure concurrent readers never observe partial JSON.

- [ ] **Step 6: Run the Task 1 tests and verify GREEN**

Run: `python -m unittest tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_legacy_model_only_memo_does_not_block_a_paid_request tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_corrupt_memo_fails_open tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_confirmed_moderation_matches_only_same_photo_model_and_prompt -v`

Expected: 3 tests pass; no fal mock is called.

- [ ] **Step 7: Create a scoped checkpoint**

Run: `git diff --check -- saasshorts.py tests/test_saasshorts_storyboard.py`

Because both files already contain user edits, leave them unstaged unless only the new hunks can be isolated safely. In a clean worktree, commit with `git commit -m "fix: scope frame moderation memory to prompt"`.

---

### Task 2: Persist only explicit moderation and never auto-fallback

**Files:**
- Modify: `saasshorts.py:7452-7682`
- Modify: `saasshorts.py:9994-10027`
- Test: `tests/test_saasshorts_storyboard.py:913-1197`

**Interfaces:**
- Consumes: `_models_that_blanked(photo_path, prompt)` and `_remember_confirmed_moderation(...)` from Task 1
- Produces: `_explicit_moderation_flags(result: dict) -> dict`
- Changes: `_report_blocked_editor(..., photo_path: str, prompt: str) -> None`
- Block reasons: `moderation`, `known`, `blank`, `unavailable`, `unreachable`

- [ ] **Step 1: Write failing tests for explicit moderation classification**

```python
def test_only_truthy_explicit_moderation_fields_are_confirmed(self):
    self.assertEqual(
        saasshorts._explicit_moderation_flags({"has_nsfw_concepts": [False]}), {}
    )
    self.assertEqual(
        saasshorts._explicit_moderation_flags({"has_nsfw_concepts": [True]}),
        {"has_nsfw_concepts": [True]},
    )
    self.assertEqual(
        saasshorts._explicit_moderation_flags({"message": "blocked by safety policy"}),
        {"message": "blocked by safety policy"},
    )
    self.assertEqual(saasshorts._explicit_moderation_flags({"error": "timeout"}), {})
```

- [ ] **Step 2: Run the classifier test and verify RED**

Run: `python -m unittest tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_only_truthy_explicit_moderation_fields_are_confirmed -v`

Expected: FAIL because `_explicit_moderation_flags` does not exist.

- [ ] **Step 3: Implement the explicit classifier**

```python
_FAL_BOOLEAN_MODERATION_FIELDS = ("has_nsfw_concepts", "nsfw_content_detected")
_MODERATION_WORDS = ("moderation", "nsfw", "safety policy", "content policy")

def _moderation_value_is_true(value) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(_moderation_value_is_true(item) for item in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return False

def _explicit_moderation_flags(result: dict) -> dict:
    flags = {
        key: result[key] for key in _FAL_BOOLEAN_MODERATION_FIELDS
        if key in result and _moderation_value_is_true(result[key])
    }
    for key in ("error", "message", "detail"):
        value = result.get(key)
        if isinstance(value, str) and any(word in value.lower() for word in _MODERATION_WORDS):
            flags[key] = value
    return flags
```

- [ ] **Step 4: Write failing integration tests for confirmed and unclassified blanks**

```python
def test_blank_without_explicit_moderation_is_not_remembered(self):
    import numpy as np
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "plate.png")
        photo = os.path.join(tmp, "actor.png")
        self._write_png(photo, np.full((8, 8, 3), 100))
        billing = {}
        with patch.object(saasshorts, "_fal_run", return_value={"images": [{"url": "u"}]}), \
             patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"), \
             patch.object(saasshorts.httpx, "Client", return_value=self._fake_httpx_client(
                 out, iter([np.zeros((8, 8, 3))]))):
            self.assertEqual(saasshorts._flux_reference_frame(
                "prompt", "key", out, log=lambda *_: None,
                actor_photo_path=photo, billing=billing,
            ), "")
        self.assertEqual(billing["blocked"][0]["reason"], "blank")
        self.assertEqual(saasshorts._models_that_blanked(photo, "prompt"), set())

def test_confirmed_blank_is_remembered_and_same_prompt_skips_fal(self):
    import numpy as np
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "plate.png")
        photo = os.path.join(tmp, "actor.png")
        self._write_png(photo, np.full((8, 8, 3), 100))
        first_billing = {}
        first_run = MagicMock(return_value={
            "images": [{"url": "u"}], "has_nsfw_concepts": [True],
        })
        with patch.object(saasshorts, "_fal_run", first_run), \
             patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"), \
             patch.object(saasshorts.httpx, "Client", return_value=self._fake_httpx_client(
                 out, iter([np.zeros((8, 8, 3))]))):
            saasshorts._flux_reference_frame(
                "prompt", "key", out, log=lambda *_: None,
                actor_photo_path=photo, billing=first_billing,
            )
        second_billing = {}
        second_run = MagicMock(side_effect=AssertionError("paid retry must not run"))
        with patch.object(saasshorts, "_fal_run", second_run):
            saasshorts._flux_reference_frame(
                "prompt", "key", out, log=lambda *_: None,
                actor_photo_path=photo, billing=second_billing,
            )
        first_run.assert_called_once()
        second_run.assert_not_called()
        self.assertEqual(second_billing.get("calls", 0), 0)
        self.assertEqual(second_billing["blocked"][0]["reason"], "known")

def test_different_prompt_requires_a_new_manual_call(self):
    import numpy as np
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "plate.png")
        photo = os.path.join(tmp, "actor.png")
        self._write_png(photo, np.full((8, 8, 3), 100))
        model = saasshorts.DEFAULT_AVATAR_EDIT_MODEL
        saasshorts._remember_confirmed_moderation(
            photo, model, "prompt A", {"has_nsfw_concepts": [True]},
        )
        run = MagicMock(return_value={"images": [{"url": "u"}]})
        detailed = np.arange(8 * 8 * 3, dtype="uint8").reshape((8, 8, 3))
        with patch.object(saasshorts, "_fal_run", run), \
             patch.object(saasshorts, "_fal_upload_file", return_value="http://photo"), \
             patch.object(saasshorts.httpx, "Client", return_value=self._fake_httpx_client(
                 out, iter([detailed]))):
            made = saasshorts._flux_reference_frame(
                "prompt B", "key", out, log=lambda *_: None,
                actor_photo_path=photo, billing={},
            )
        self.assertEqual(made, out)
        run.assert_called_once()
```

- [ ] **Step 5: Run the three integration tests and verify RED**

Run: `python -m unittest tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_blank_without_explicit_moderation_is_not_remembered tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_confirmed_blank_is_remembered_and_same_prompt_skips_fal tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests.test_different_prompt_requires_a_new_manual_call -v`

Expected: FAIL because current code stores every blank/unavailable result and ignores the prompt.

- [ ] **Step 6: Integrate scoped checks into `_flux_reference_frame`**

Make these exact behavioural changes:

```python
blocked = _models_that_blanked(actor_photo_path, prompt)
if entry["id"] in blocked:
    _report_blocked_editor(billing, entry, "known", {}, False, actor_photo_path, prompt)
    return ""

flags = _explicit_moderation_flags(result)
reason = "moderation" if flags else "blank"
if flags:
    _remember_confirmed_moderation(actor_photo_path, model, prompt, flags)
_report_blocked_editor(billing, entry, reason, flags, True, actor_photo_path, prompt)
```

In the exception branch, report `unavailable` or `unreachable` but never write a moderation memo. Keep the existing `generated` accounting so a failure after generation remains charged. Pass `prompt` into every `_report_blocked_editor` call.

```python
unreachable = isinstance(e, FalUnreachable)
if billing is not None and not generated:
    billing["calls"] = max(0, billing.get("calls", 1) - 1)
if actor_photo_path:
    _report_blocked_editor(
        billing, entry, "unreachable" if unreachable else "unavailable",
        {"error": str(e)}, generated, actor_photo_path, prompt,
    )
return ""
```

- [ ] **Step 7: Make alternatives prompt-scoped**

Inside `_report_blocked_editor`, compute `tried = _models_that_blanked(photo_path, prompt)` and return every catalog model with a `blocked` boolean for that exact prompt. Stop deriving the top-level catalog's `blocked` flag from photo-only history in the frame-generation result; the model selector is not tied to one prompt.

```python
tried = _models_that_blanked(photo_path, prompt) if photo_path else set()
alternatives = [
    {
        "id": model["id"],
        "title": model["title"],
        "vendor": model["vendor"],
        "note": model["note"],
        "blocked": model["id"] in tried,
    }
    for model in AVATAR_EDIT_MODELS
    if model["id"] != entry["id"]
]

avatar_edit_models = [
    {key: model[key] for key in ("id", "title", "vendor", "note")}
    for model in AVATAR_EDIT_MODELS
]
```

- [ ] **Step 8: Update the existing unavailable-endpoint assertion**

Change `test_refused_endpoint_is_reported_as_unavailable_not_moderation` to assert:

```python
self.assertEqual(saasshorts._models_that_blanked(photo, "prompt"), set())
```

This enforces the approved rule that endpoint errors are never persisted as moderation.

- [ ] **Step 9: Run backend regression tests and verify GREEN**

Run: `python -m unittest tests.test_saasshorts_storyboard.SaaSBlankFrameGuardTests -v`

Expected: all `SaaSBlankFrameGuardTests` pass; existing `test_one_click_buys_at_most_one_paid_frame` and `test_chosen_editor_is_the_one_that_gets_called` still prove one selected model per manual operation.

- [ ] **Step 10: Create a scoped checkpoint**

Run: `git diff --check -- saasshorts.py tests/test_saasshorts_storyboard.py`

Do not stage unrelated pre-existing hunks. In a clean worktree, commit with `git commit -m "fix: persist only confirmed frame moderation"`.

---

### Task 3: Keep the replacement modal strictly manual

**Files:**
- Modify: `dashboard/src/components/FrameEditorBlockedModal.jsx:7-140`
- Create: `dashboard/src/components/FrameEditorBlockedModal.test.mjs`

**Interfaces:**
- Consumes: `block.reason`, `block.flags`, and prompt-scoped `block.alternatives` from Task 2
- Guarantees: `onPick(modelId)` runs only from an enabled model button's click handler
- Guarantees: render and both close buttons never call `onPick`

- [ ] **Step 1: Write the Vite-SSR component test**

```javascript
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

let server;
let Modal;

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true },
  });
  ({ default: Modal } = await server.ssrLoadModule('/src/components/FrameEditorBlockedModal.jsx'));
});
after(async () => server?.close());

function elements(node, found = []) {
  if (!node || typeof node !== 'object') return found;
  found.push(node);
  const children = node.props?.children;
  for (const child of (Array.isArray(children) ? children : [children])) elements(child, found);
  return found;
}

test('render and close never select a paid model; enabled click selects exactly once', () => {
  const picked = [];
  let closed = 0;
  const onClose = () => { closed += 1; };
  const tree = Modal({
    block: { model: 'current', title: 'Current', reason: 'blank', alternatives: [
      { id: 'next', title: 'Next', vendor: 'Vendor', note: '', blocked: false },
    ] },
    models: [{ id: 'global', title: 'Global', vendor: 'Old catalog', note: '', blocked: false }],
    onPick: (id) => picked.push(id),
    onClose,
  });
  assert.deepEqual(picked, []);
  const buttons = elements(tree).filter((node) => node.type === 'button');
  buttons.find((button) => button.props.onClick === onClose).props.onClick();
  assert.deepEqual(picked, []);
  assert.equal(closed, 1);
  const modelButton = buttons.find((button) => button.key === 'next');
  modelButton.props.onClick();
  assert.deepEqual(picked, ['next']);
});
```

- [ ] **Step 2: Run the modal test and verify RED**

Run: `node --test src/components/FrameEditorBlockedModal.test.mjs` from `dashboard/`.

Expected: FAIL because the modal prefers the global catalog, so no button with key `next` exists.

- [ ] **Step 3: Implement prompt-scoped modal behaviour**

Add this `REASON_TEXT.blank` entry and prefer `block.alternatives` whenever the property is present:

```javascript
blank:
  'Модель вернула пустой кадр без подтверждённого флага модерации. '
  + 'Результат оплачен, но не запомнен; повтор возможен только вручную.',

const sourceModels = Array.isArray(block.alternatives)
  ? block.alternatives
  : models;
const options = sourceModels.filter((model) => model.id !== block.model);
```

Keep `onPick` only on model button clicks. Keep both close buttons wired only to `onClose`. Disable an alternative only when `busy || model.blocked`.

- [ ] **Step 4: Run the modal test and verify GREEN**

Run: `node --test src/components/FrameEditorBlockedModal.test.mjs` from `dashboard/`.

Expected: 1 test passes and Vite closes cleanly.

- [ ] **Step 5: Build the frontend**

Run: `npm run build` from `dashboard/`.

Expected: Vite production build exits 0.

- [ ] **Step 6: Create a scoped checkpoint**

Run: `git diff --check -- dashboard/src/components/FrameEditorBlockedModal.jsx dashboard/src/components/FrameEditorBlockedModal.test.mjs`

Do not stage the component's unrelated pre-existing hunks. In a clean worktree, commit with `git commit -m "test: keep frame editor retries manual"`.

---

### Task 4: End-to-end verification without paid requests

**Files:**
- Verify: `saasshorts.py`
- Verify: `tests/test_saasshorts_storyboard.py`
- Verify: `dashboard/src/components/FrameEditorBlockedModal.jsx`
- Verify: `dashboard/src/components/FrameEditorBlockedModal.test.mjs`

**Interfaces:**
- Verifies the complete approved behaviour; produces no new API, data, or UI interface.

- [ ] **Step 1: Run the full storyboard test module**

Run: `python -m unittest tests.test_saasshorts_storyboard -v`

Expected: all tests pass with zero real fal calls because external calls are patched.

- [ ] **Step 2: Run all standalone frontend tests**

Run: `node --test src/components/*.test.mjs` from `dashboard/`.

Expected: all Node tests pass.

- [ ] **Step 3: Run the frontend production build**

Run: `npm run build` from `dashboard/`.

Expected: build exits 0.

- [ ] **Step 4: Verify the real legacy memo remains non-destructive and non-blocking**

Run:

```powershell
python -c "from pathlib import Path; import saasshorts; p=Path('output/actor_uploads/custom_b2444a24.png.blank_models.json'); before=p.read_bytes(); print(saasshorts._models_that_blanked('output/actor_uploads/custom_b2444a24.png', 'verification prompt')); assert p.read_bytes() == before"
```

This calls only the memo reader; do not call `_flux_reference_frame` or any endpoint.

Expected: `set()` while the legacy JSON file remains present and unchanged.

- [ ] **Step 5: Inspect the final diff and paid-call boundary**

Run:

```powershell
git diff --check
rg -n "_fal_run\(|handleGenerateFrames\(" saasshorts.py dashboard/src/components/FrameEditorBlockedModal.jsx dashboard/src/components/SaaShortsTab.jsx
```

Expected: `_fal_run` remains inside the backend generation function; the modal itself never calls `handleGenerateFrames`; the parent calls it only inside `onPick`.

- [ ] **Step 6: Report without triggering generation**

Report test counts, build status, and that the legacy memo was ignored. Explicitly state that no fal endpoint or paid generation route was invoked. Leave implementation changes unstaged if clean hunk isolation is not guaranteed in the dirty worktree.

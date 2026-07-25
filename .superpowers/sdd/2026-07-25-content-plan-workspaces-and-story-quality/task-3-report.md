# Task 3 Report: AI Shorts workspace restore and server synchronization

## Status

Completed and verified.

## Implementation

- Added persisted active content-plan context helpers and resolved that context before wizard state initialization.
- Added `activeWorkspaceKey` and a single `initialCache` for all restored wizard state, preserving legacy global-cache behavior when no content-plan item is active.
- Restored item-scoped business input, scripting state, analysis/research/scripts, wizard progress, selected script, narration, generation job/status/result, and storyboard frame edits.
- Parameterized cache and job helpers so item workspaces use isolated cache and last-job keys while legacy global keys remain compatible.
- Added synchronous local workspace persistence with derived stages and debounced authenticated PUT synchronization. Server data is merged through `chooseNewestWorkspace`; a `keepalive` PUT flushes the latest snapshot at unmount.
- Scoped job recovery and reset to the active item. Reset clears the active content-plan context, cancels pending synchronization, and suppresses the immediate persistence effect so a deleted workspace cannot be recreated with a blank snapshot after DELETE.
- Added a hydration-version dependency so a locally restored item is queued for its initial authenticated synchronization after the server read completes.

## TDD Evidence

1. Added the reset persistence-guard source-contract assertion and ran it red: it failed because `workspaceResettingRef` did not exist.
2. Added the reset guard, then reran the focused test green.
3. Added the post-hydration synchronization source-contract assertion and ran it red: it failed because the hydration version was not retained or used as a persistence dependency.
4. Retained `workspaceHydrationVersion` and added it to the persistence effect dependencies, then reran the focused test green.

## Verification

- `C:\Python311\python.exe -m unittest tests.test_ui_layout_polish -v`
  - Passed: 33 tests.
- `npm run build --prefix dashboard`
  - PowerShell's `npm.ps1` is disabled by local execution policy.
  - Equivalent `npm.cmd run build --prefix dashboard` passed outside the filesystem sandbox because esbuild requires parent-directory access.

## Review Notes

- Reviewed the final diff and ran `git diff --check`; no whitespace errors.
- The build emits pre-existing advisory warnings about a stale Browserslist database and chunks above 500 kB. They do not fail the build and were not changed by this task.
- The unrelated untracked `docs/diploma/` directory remains untouched and is excluded from the commit.

## Fix Round 1

### Findings Addressed

- `saveLocalWorkspace` now preserves `snapshot.topic` before falling back to the content-plan context. Nullish fallback preserves an intentionally empty user topic.
- Wizard step selection is centralized in `workspaceStep`. An explicit integer step remains authoritative; snapshots without a step now start at step 1 when analysis, research, scripts, a job, or a result exists.
- A newer workspace returned by a PUT now becomes authoritative everywhere: it is saved locally, replaces `latestWorkspaceSnapshotRef`, is applied to React state, and retriggers persistence from the applied state rather than the stale request snapshot.
- The reset guard remains unchanged.

### TDD Evidence

1. Added source contracts for topic precedence, shared progress-derived step fallback, and applying a remote PUT winner.
2. Ran the three contracts against `63e63ea`; all failed for their intended missing behavior.
3. Implemented the narrow fixes and reran the focused contracts: all three passed.
4. The full UI suite initially exposed one old assertion coupled to the former inline step expression. Updated it to assert the shared helper, preserving the same restore contract.

### Fix Round Verification

- `C:\Python311\python.exe -m unittest tests.test_ui_layout_polish -v`
  - Passed: 36 tests.
- `npm.cmd run build --prefix dashboard`
  - Passed. `npm.ps1` remains blocked by local PowerShell execution policy, so the command uses the Windows npm executable.

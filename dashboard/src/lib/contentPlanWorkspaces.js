const WORKSPACE_KEY_PREFIX = 'saasshorts_content_workspace_';
const ACTIVE_CONTENT_PLAN_CONTEXT_KEY = 'saasshorts_active_content_plan_context';
const WORKSPACE_STAGES = new Set(['not_started', 'script', 'frames', 'video', 'failed']);

function contextIds(context) {
  return {
    profileId: String(context?.profileId || ''),
    itemId: String(context?.itemId ?? context?.item?.item_id ?? ''),
  };
}

function generatedItemId() {
  if (globalThis.crypto?.randomUUID) return `content-plan-${globalThis.crypto.randomUUID()}`;
  return `content-plan-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function ensurePlanItemIds(items) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => {
    if (typeof item?.item_id === 'string' && item.item_id.trim()) return item;
    if (typeof item?.item_id === 'number' && Number.isFinite(item.item_id)) {
      return { ...item, item_id: String(item.item_id) };
    }
    return { ...item, item_id: generatedItemId() };
  });
}

export function workspaceStorageKey(context) {
  const { profileId, itemId } = contextIds(context);
  return `${WORKSPACE_KEY_PREFIX}${encodeURIComponent(profileId)}_${encodeURIComponent(itemId)}`;
}

export function loadLocalWorkspace(context) {
  try {
    const raw = localStorage.getItem(workspaceStorageKey(context));
    const snapshot = raw ? JSON.parse(raw) : null;
    return snapshot && typeof snapshot === 'object' ? snapshot : null;
  } catch {
    return null;
  }
}

export function loadActiveContentPlanContext() {
  try {
    const raw = localStorage.getItem(ACTIVE_CONTENT_PLAN_CONTEXT_KEY);
    const context = raw ? JSON.parse(raw) : null;
    return context && typeof context === 'object' ? context : null;
  } catch {
    return null;
  }
}

export function saveActiveContentPlanContext(context) {
  try {
    if (context) localStorage.setItem(ACTIVE_CONTENT_PLAN_CONTEXT_KEY, JSON.stringify(context));
    else localStorage.removeItem(ACTIVE_CONTENT_PLAN_CONTEXT_KEY);
  } catch { /* ignore */ }
}

export function clearActiveContentPlanContext() {
  try {
    localStorage.removeItem(ACTIVE_CONTENT_PLAN_CONTEXT_KEY);
  } catch { /* ignore */ }
}

function hasText(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function hasFrameUrl(shots) {
  return Array.isArray(shots) && shots.some((shot) => (
    hasText(shot?.preview_frame_url)
    || hasText(shot?.frame_url)
    || hasText(shot?.image_url)
    || hasText(shot?.generated_image_url)
  ));
}

function hasFailedGeneration(snapshot) {
  return (
    snapshot?.failed_generation === true
    || snapshot?.generation_failed === true
    || snapshot?.generation?.status === 'failed'
    || snapshot?.status === 'failed'
  );
}

export function workspaceStage(snapshot) {
  const explicitStage = snapshot?.stage;

  if (hasFailedGeneration(snapshot)) return 'failed';

  if (
    hasText(snapshot?.result?.video_url)
    || hasText(snapshot?.result?.videoUrl)
    || hasText(snapshot?.video_url)
    || hasText(snapshot?.videoUrl)
    || hasText(snapshot?.result_url)
  ) return 'video';
  if (
    hasFrameUrl(snapshot?.shots)
    || hasFrameUrl(snapshot?.generated_shots)
    || hasFrameUrl(snapshot?.frames)
    || (Array.isArray(snapshot?.scripts) && snapshot?.scripts?.some((script) => hasFrameUrl(script?.shots)))
  ) return 'frames';
  if (
    (Array.isArray(snapshot?.scripts) && snapshot.scripts.length > 0)
    || hasText(snapshot?.script)
    || hasText(snapshot?.full_narration)
  ) return 'script';
  if (WORKSPACE_STAGES.has(explicitStage) && explicitStage !== 'not_started') return explicitStage;
  return 'not_started';
}

function workspaceRevision(workspace) {
  const revision = Number(workspace?.revision ?? workspace?.snapshot?.revision);
  return Number.isFinite(revision) ? revision : 0;
}

function workspaceUpdatedAt(workspace) {
  const updatedAt = workspace?.updatedAt
    ?? workspace?.updated_at
    ?? workspace?.snapshot?.updatedAt
    ?? workspace?.snapshot?.updated_at;
  const timestamp = Date.parse(updatedAt || '');
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function chooseNewestWorkspace(local, remote) {
  if (!local) return remote || null;
  if (!remote) return local;
  const localRevision = workspaceRevision(local);
  const remoteRevision = workspaceRevision(remote);
  if (localRevision !== remoteRevision) return localRevision > remoteRevision ? local : remote;
  return workspaceUpdatedAt(local) >= workspaceUpdatedAt(remote) ? local : remote;
}

export function saveLocalWorkspace(context, snapshot) {
  snapshot = snapshot || {};
  const { profileId, itemId } = contextIds(context);
  const previous = loadLocalWorkspace({ profileId, itemId });
  const previousRevision = workspaceRevision(previous);
  const requestedRevision = workspaceRevision(snapshot);
  const nextRevision = requestedRevision > previousRevision ? requestedRevision : previousRevision + 1;
  const saved = {
    ...snapshot,
    version: snapshot.version || 1,
    revision: nextRevision,
    updatedAt: new Date().toISOString(),
    stage: workspaceStage(snapshot),
    profileId,
    itemId,
    item: context?.item ?? snapshot.item,
    topic: context?.topic ?? snapshot.topic ?? '',
  };
  try {
    localStorage.setItem(workspaceStorageKey({ profileId, itemId }), JSON.stringify(saved));
  } catch { /* localStorage full */ }
  return saved;
}

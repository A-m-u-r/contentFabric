// Shared storage for saved business projects (профили бизнеса).
// Used by ProjectsTab (management UI), SaaShortsTab (project picker)
// and ContentPlanTab (plan generation context).

export const BUSINESS_PROFILES_KEY = 'saasshorts_business_profiles';
export const SELECTED_PROFILE_KEY = 'saasshorts_selected_profile_id';
export const PENDING_TOPIC_KEY = 'saasshorts_pending_topic';
export const PENDING_CONTENT_PLAN_ITEM_KEY = 'saasshorts_pending_content_plan_item';

export function loadBusinessProfiles() {
  try {
    const raw = localStorage.getItem(BUSINESS_PROFILES_KEY);
    const profiles = raw ? JSON.parse(raw) : [];
    return Array.isArray(profiles) ? profiles : [];
  } catch {
    return [];
  }
}

export function saveBusinessProfiles(profiles) {
  try {
    localStorage.setItem(BUSINESS_PROFILES_KEY, JSON.stringify(profiles.slice(0, 20)));
  } catch { /* localStorage full */ }
}

export function profileId(profile) {
  return profile?.id || profile?.name || '';
}

export function loadSelectedProfileId() {
  try {
    return localStorage.getItem(SELECTED_PROFILE_KEY) || '';
  } catch {
    return '';
  }
}

export function saveSelectedProfileId(id) {
  try {
    if (id) localStorage.setItem(SELECTED_PROFILE_KEY, id);
    else localStorage.removeItem(SELECTED_PROFILE_KEY);
  } catch { /* ignore */ }
}

// Тема ролика, выбранная в контент-плане: AI Shorts подхватывает её при открытии.
// Чтение и удаление разделены: React StrictMode вызывает mount-эффекты дважды,
// и «читающий + удаляющий» вызов терял тему на втором прогоне.
export function setPendingTopic(topic) {
  try {
    localStorage.setItem(PENDING_TOPIC_KEY, topic || '');
  } catch { /* ignore */ }
}

export function peekPendingTopic() {
  try {
    return localStorage.getItem(PENDING_TOPIC_KEY) || '';
  } catch {
    return '';
  }
}

export function clearPendingTopic() {
  try {
    localStorage.removeItem(PENDING_TOPIC_KEY);
  } catch { /* ignore */ }
}

export function setPendingContentPlanItem(context) {
  try {
    localStorage.setItem(PENDING_CONTENT_PLAN_ITEM_KEY, JSON.stringify(context || null));
  } catch { /* ignore */ }
}

export function peekPendingContentPlanItem() {
  try {
    const raw = localStorage.getItem(PENDING_CONTENT_PLAN_ITEM_KEY);
    const context = raw ? JSON.parse(raw) : null;
    return context && typeof context === 'object' ? context : null;
  } catch {
    return null;
  }
}

export function clearPendingContentPlanItem() {
  try {
    localStorage.removeItem(PENDING_CONTENT_PLAN_ITEM_KEY);
  } catch { /* ignore */ }
}

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

// A project keeps durable media references, never browser-only upload previews.
const durableMediaUrl = (value) => typeof value === 'string' && /^(\/|https?:\/\/)/.test(value) ? value : null;

export function presenterFromPreferences(prefs) {
  return {
    actor_url: durableMediaUrl(prefs.selectedActor),
    face_url: durableMediaUrl(prefs.selectedFace),
    plate_urls: Object.fromEntries(Object.entries(prefs.plateUrls || {})
      .filter(([, url]) => durableMediaUrl(url))),
    voice_id: prefs.selectedVoice || null,
    voice_name: prefs.selectedVoiceName || null,
    tts_provider: prefs.ttsProvider || 'auto',
    minimax_voice_id: prefs.minimaxVoice || null,
    elevenlabs_model: prefs.elevenLabsModel || 'eleven_v4',
    elevenlabs_stability: prefs.elevenLabsStability ?? 0.65,
    elevenlabs_similarity: prefs.elevenLabsSimilarity ?? 0.75,
  };
}

export function preferencesFromPresenter(presenter) {
  if (presenter === undefined) return {}; // Legacy project: retain the current draft.
  return {
    selectedActor: presenter?.actor_url || '',
    selectedFace: presenter?.face_url || '',
    plateUrls: presenter?.plate_urls || {},
    uploadedActorUrl: '',
    selectedVoice: presenter?.voice_id || '',
    selectedVoiceName: presenter?.tts_provider === 'fal_minimax' ? '' : presenter?.voice_name || '',
    voiceSelectionSource: presenter?.voice_id ? 'manual' : 'default',
    ttsProvider: presenter?.tts_provider || 'auto',
    minimaxVoice: presenter?.minimax_voice_id || 'Russian_AmbitiousWoman',
    elevenLabsModel: presenter?.elevenlabs_model || 'eleven_v4',
    elevenLabsStability: presenter?.elevenlabs_stability ?? 0.65,
    elevenLabsSimilarity: presenter?.elevenlabs_similarity ?? 0.75,
  };
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

export function mergeProjectMetadata(accountProfiles, localProfiles, { includeLocalOnly = false } = {}) {
  const aliases = {
    actor_gender: 'actorGender',
    script_format: 'scriptFormat',
    script_mode: 'scriptMode',
    text_model: 'textModel',
  };
  const key = (profile) => String(profileId(profile));
  const localById = new Map(localProfiles.map((profile) => [key(profile), profile]));
  const mergedProfiles = accountProfiles.map((accountProfile) => {
    const localProfile = localById.get(key(accountProfile));
    const merged = { ...localProfile, ...accountProfile };
    for (const [canonical, alias] of Object.entries(aliases)) {
      if (Object.hasOwn(accountProfile, canonical)) delete merged[alias];
    }
    return merged;
  });
  if (!includeLocalOnly) return mergedProfiles;

  const accountIds = new Set(accountProfiles.map(key));
  const browserOnly = localProfiles.filter((profile) => !profile.created_at && !accountIds.has(key(profile)));
  return [...mergedProfiles, ...browserOnly];
}

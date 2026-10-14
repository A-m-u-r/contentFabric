import React, { useEffect, useRef, useState } from 'react';
import { CalendarDays, Sparkles, Loader2, AlertCircle, RefreshCw, Check, Target, ChevronRight, Download, Play, SquarePen } from 'lucide-react';
import { getApiUrl } from '../config';
import {
  loadBusinessProfiles,
  saveBusinessProfiles,
  loadSelectedProfileId,
  saveSelectedProfileId,
  profileId,
  setPendingTopic,
  setPendingContentPlanItem,
} from '../lib/businessProfiles';
import {
  ensurePlanItemIds,
  loadLocalWorkspace,
  saveLocalWorkspace,
  chooseNewestWorkspace,
  workspaceStage,
} from '../lib/contentPlanWorkspaces';

const PLAN_KEY_PREFIX = 'saasshorts_content_plan_';

const PLAN_SIZE_OPTIONS = [
  { id: 8, label: '8 роликов', desc: '2 в неделю' },
  { id: 12, label: '12 роликов', desc: '3 в неделю' },
  { id: 16, label: '16 роликов', desc: '4 в неделю' },
  { id: 30, label: '30 роликов', desc: 'каждый день' },
];

const GOAL_STYLES = {
  'прогрев': 'bg-amber-500/10 text-amber-300 border-amber-500/20',
  'вовлечение': 'bg-blue-500/10 text-blue-300 border-blue-500/20',
  'доверие': 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  'продажа': 'bg-violet-500/10 text-violet-300 border-violet-500/20',
};

const WORKSPACE_STAGE_LABELS = {
  not_started: 'Не начат',
  script: 'Сценарий',
  frames: 'Кадры',
  video: 'Файл недоступен',
  failed: 'Ошибка',
};

function loadPlan(id) {
  try {
    const raw = localStorage.getItem(PLAN_KEY_PREFIX + id);
    const plan = raw ? JSON.parse(raw) : null;
    return plan && Array.isArray(plan.items) ? plan : null;
  } catch {
    return null;
  }
}

function savePlan(id, plan) {
  try {
    localStorage.setItem(PLAN_KEY_PREFIX + id, JSON.stringify(plan));
  } catch { /* localStorage full */ }
}

function upgradePlan(plan) {
  if (!plan) return null;
  const items = ensurePlanItemIds(plan.items);
  const itemIdsChanged = items.some((item, index) => item !== plan.items[index]);
  const done = Object.entries(plan.done || {}).reduce((next, [key, value]) => {
    const existingItem = items.find((item) => item.item_id === key);
    const item = existingItem || (Number.isInteger(Number(key)) ? items[Number(key)] : null);
    next[item?.item_id || key] = value;
    return next;
  }, {});
  const doneChanged = Object.keys(done).some((key) => !Object.prototype.hasOwnProperty.call(plan.done || {}, key));
  return itemIdsChanged || doneChanged ? { ...plan, items, done } : plan;
}

export function mergeContentPlans(local, remote) {
  local = upgradePlan(local);
  remote = upgradePlan(remote);
  if (!remote) return local;
  if (!local) return remote;
  const remoteItems = ensurePlanItemIds(remote.items);
  const remoteIds = new Set(remoteItems.map((item) => item.item_id));
  return {
    ...local,
    ...remote,
    items: [...remoteItems, ...ensurePlanItemIds(local.items).filter((item) => !remoteIds.has(item.item_id))],
    done: { ...(local.done || {}), ...(remote.done || {}) },
  };
}

function itemTopic(item) {
  return [item.topic, item.hook ? `Хук: ${item.hook}` : '', item.cta ? `CTA: ${item.cta}` : '']
    .filter(Boolean)
    .join('\n');
}

export function contentPlanItemProgress(local, remote, manualDone = false) {
  const workspace = chooseNewestWorkspace(local, remote);
  let video = null;
  if (remote && Object.prototype.hasOwnProperty.call(remote, 'video')) {
    video = remote.video;
  } else {
    const result = workspace?.genResult || workspace?.result;
    const url = result?.video_url;
    if (workspaceStage(workspace) === 'video' && typeof url === 'string' && url.startsWith('/videos/saas_')) {
      video = { video_url: url, duration: result.duration, filename: url.split('/').pop() };
    }
  }
  return { workspace, stage: workspace ? workspaceStage(workspace) : null,
    video: video || null, done: Boolean(video) || Boolean(manualDone) };
}

export default function ContentPlanTab({ geminiApiKey, authToken, usePlatformKeys = false, onCreateVideo, onOpenProjects }) {
  const [profiles, setProfiles] = useState(() => loadBusinessProfiles());
  const [selectedId, setSelectedId] = useState(() => loadSelectedProfileId());
  const [numItems, setNumItems] = useState(12);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState(null);
  const [workspaceSummaries, setWorkspaceSummaries] = useState({});
  const [openingItemId, setOpeningItemId] = useState('');
  const [downloadingItemId, setDownloadingItemId] = useState('');
  const planChangeRef = useRef(0);

  const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});
  const isManagedKey = (value) => value === '__saved__' || value === '__platform__';

  const selectedProfile = profiles.find((p) => profileId(p) === selectedId) || null;

  useEffect(() => {
    if (!authToken) return;
    fetch(getApiUrl('/api/user/business-profiles'), { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : { profiles: [] }))
      .then((data) => {
        if (Array.isArray(data.profiles) && data.profiles.length > 0) {
          setProfiles(data.profiles);
          saveBusinessProfiles(data.profiles);
          setSelectedId((current) => {
            if (current && data.profiles.some((profile) => profileId(profile) === current)) return current;
            const firstId = profileId(data.profiles[0]);
            saveSelectedProfileId(firstId);
            return firstId;
          });
        }
      })
      .catch(() => {});
  }, [authToken]);

  useEffect(() => {
    planChangeRef.current += 1;
    const loadedPlan = selectedId ? loadPlan(selectedId) : null;
    const upgradedPlan = upgradePlan(loadedPlan);
    setPlan(upgradedPlan);
    if (selectedId && upgradedPlan !== loadedPlan) savePlan(selectedId, upgradedPlan);
  }, [selectedId]);

  useEffect(() => {
    if (!authToken || !selectedId) return;
    const version = planChangeRef.current;
    let cancelled = false;
    fetch(getApiUrl(`/api/user/content-plan/${encodeURIComponent(selectedId)}`), { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : { plan: null }))
      .then((data) => {
        if (cancelled || version !== planChangeRef.current || !data.plan) return;
        const merged = upgradePlan(mergeContentPlans(loadPlan(selectedId), data.plan));
        setPlan(merged);
        savePlan(selectedId, merged);
        if (JSON.stringify(merged) !== JSON.stringify(data.plan)) {
          fetch(getApiUrl(`/api/user/content-plan/${encodeURIComponent(selectedId)}`), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ plan: merged }),
          }).catch(() => {});
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [authToken, selectedId]);

  const persistPlan = (profileId, nextPlan) => {
    planChangeRef.current += 1;
    setPlan(nextPlan);
    savePlan(profileId, nextPlan);
    if (!authToken) return;
    fetch(getApiUrl(`/api/user/content-plan/${encodeURIComponent(profileId)}`), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ plan: nextPlan }),
    }).then((res) => {
      if (!res.ok) throw new Error('Не удалось сохранить контент-план в аккаунте. Локальная копия сохранена.');
    }).catch((saveError) => setError(saveError.message));
  };

  useEffect(() => {
    if (!authToken || !selectedId) {
      setWorkspaceSummaries({});
      return;
    }
    let cancelled = false;
    fetch(getApiUrl(`/api/user/content-workspaces?profile_id=${encodeURIComponent(selectedId)}`), { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : { workspaces: [] }))
      .then((data) => {
        if (cancelled || !Array.isArray(data.workspaces)) return;
        setWorkspaceSummaries(Object.fromEntries(data.workspaces.map((workspace) => [workspace.item_id, workspace])));
      })
      .catch(() => {
        if (!cancelled) setWorkspaceSummaries({});
      });
    return () => { cancelled = true; };
  }, [authToken, selectedId]);

  const handleSelectProfile = (profile) => {
    const id = profileId(profile);
    setSelectedId(id);
    saveSelectedProfileId(id);
    setError('');
  };

  const handleGenerate = async () => {
    if (!selectedProfile) return;
    if (plan?.items?.length && !window.confirm('Заменить текущий контент-план новым? Черновики роликов сохранятся отдельно.')) return;
    if (!geminiApiKey) {
      setError('Нужен Gemini API ключ — задай его в Настройках.');
      return;
    }
    setGenerating(true);
    setError('');
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/content-plan'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
          ...(geminiApiKey && !isManagedKey(geminiApiKey) ? { 'X-Gemini-Key': geminiApiKey } : {}),
        },
        body: JSON.stringify({
          name: selectedProfile.name,
          description: selectedProfile.description,
          topic: selectedProfile.topic || undefined,
          language: selectedProfile.language || 'ru',
          num_items: numItems,
          period_days: 30,
          use_platform_keys: usePlatformKeys,
        }),
      });
      if (!res.ok) {
        let msg = 'Не удалось сгенерировать план';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
      const data = await res.json();
      const nextPlan = {
        items: ensurePlanItemIds(data.items || []),
        generatedAt: new Date().toISOString(),
        done: {},
      };
      persistPlan(selectedId, nextPlan);
    } catch (e) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const toggleDone = (itemId) => {
    if (!plan) return;
    const nextPlan = { ...plan, done: { ...plan.done, [itemId]: !plan.done?.[itemId] } };
    persistPlan(selectedId, nextPlan);
  };

  const handleCreateVideo = async (item) => {
    if (openingItemId) return;
    const topic = itemTopic(item);
    const context = { profileId: selectedId, itemId: item.item_id, item, topic };
    setOpeningItemId(item.item_id);
    try {
      const localWorkspace = loadLocalWorkspace(context);
      let remoteWorkspace = null;
      if (authToken) {
        try {
          const res = await fetch(
            getApiUrl(`/api/user/content-workspaces/${encodeURIComponent(selectedId)}/${encodeURIComponent(item.item_id)}`),
            { headers: authHeaders() },
          );
          if (res.ok) {
            const data = await res.json();
            if (data.workspace) {
              remoteWorkspace = {
                ...data.workspace.snapshot,
                revision: data.workspace.revision,
                stage: data.workspace.stage,
                updatedAt: data.workspace.updated_at,
              };
            }
          }
        } catch { /* local workspace remains usable */ }
      }
      const newestWorkspace = chooseNewestWorkspace(localWorkspace, remoteWorkspace);
      const readyVideo = contentPlanItemProgress(localWorkspace, workspaceSummaries[item.item_id], false).video;
      const initialWorkspace = newestWorkspace || (item.full_narration ? {
        scriptMode: 'custom',
        scriptFormat: item.format_hint || 'storyboard_v3',
        customScript: item.full_narration,
        targetDurationSeconds: item.target_duration_seconds || 20,
      } : {});
      const workspace = saveLocalWorkspace(context, readyVideo ? { ...initialWorkspace, step: 2 } : initialWorkspace);
      setWorkspaceSummaries((current) => ({
        ...current,
        [item.item_id]: { ...workspace, item_id: item.item_id },
      }));
      setPendingContentPlanItem(context);
      setPendingTopic(topic);
      onCreateVideo?.(item);
    } finally {
      setOpeningItemId('');
    }
  };

  const handleDownloadVideo = async (item, video) => {
    if (downloadingItemId) return;
    setDownloadingItemId(item.item_id);
    setError('');
    try {
      const url = video.download_url || video.video_url;
      const response = await fetch(getApiUrl(url), { headers: authHeaders() });
      if (!response.ok) throw new Error('Не удалось скачать видео. Обнови контент-план и попробуй ещё раз.');
      const blobUrl = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = blobUrl;
      anchor.download = video.filename || `reel-${item.item_id}.mp4`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch (downloadError) {
      setError(downloadError.message);
    } finally {
      setDownloadingItemId('');
    }
  };

  const itemProgress = (item) => contentPlanItemProgress(
    loadLocalWorkspace({ profileId: selectedId, itemId: item.item_id, item }),
    workspaceSummaries[item.item_id], plan?.done?.[item.item_id],
  );
  const doneCount = plan ? plan.items.filter((item) => itemProgress(item).done).length : 0;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="max-w-5xl mx-auto p-6 pb-28 md:pb-8 lg:p-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-violet-500 to-fuchsia-500 rounded-xl flex items-center justify-center">
              <CalendarDays size={20} className="text-white" />
            </div>
            Контент-план
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            План роликов на месяц под выбранный проект: темы, хуки и цели. Каждый пункт можно сразу отправить в AI Shorts.
          </p>
        </div>

        {profiles.length === 0 ? (
          <div className="glass-panel p-10 text-center">
            <Target size={28} className="mx-auto text-zinc-600 mb-3" />
            <p className="text-sm text-zinc-400 font-medium">Сначала создай проект</p>
            <p className="text-xs text-zinc-600 mt-1 mb-4">План строится на описании бизнеса из сохранённого проекта.</p>
            <button type="button" onClick={() => onOpenProjects?.()} className="btn-primary px-4 py-2 text-sm inline-flex items-center gap-2">
              Открыть Проекты <ChevronRight size={14} />
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Выбор проекта и размера плана */}
            <div className="glass-panel p-6 space-y-4">
              <div>
                <span className="block text-xs font-medium text-zinc-400 mb-2">Проект</span>
                <div className="flex flex-wrap gap-2">
                  {profiles.map((profile) => {
                    const id = profileId(profile);
                    const active = selectedId === id;
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => handleSelectProfile(profile)}
                        className={`rounded-xl border px-3 py-2 text-left text-xs transition-all max-w-[240px] ${
                          active
                            ? 'border-primary/50 bg-primary/10 text-violet-200'
                            : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                        }`}
                      >
                        <span className="block font-semibold truncate">{profile.name}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <span className="block text-xs font-medium text-zinc-400 mb-2">Сколько роликов в месяц</span>
                <div className="flex flex-wrap gap-2">
                  {PLAN_SIZE_OPTIONS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => setNumItems(option.id)}
                      className={`rounded-xl border px-3 py-2 text-left transition-all ${
                        numItems === option.id
                          ? 'border-primary/50 bg-primary/10 text-violet-200'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <span className="block text-xs font-semibold">{option.label}</span>
                      <span className="block text-[10px] text-zinc-500">{option.desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              {error && (
                <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                  <AlertCircle size={14} /> {error}
                </div>
              )}

              <button
                type="button"
                onClick={handleGenerate}
                disabled={!selectedProfile || generating}
                className="btn-primary w-full py-3 text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {generating ? (
                  <><Loader2 size={16} className="animate-spin" /> Составляю план... (15-30 сек)</>
                ) : plan ? (
                  <><RefreshCw size={15} /> Пересобрать план</>
                ) : (
                  <><Sparkles size={16} /> Сгенерировать план</>
                )}
              </button>
              {!selectedProfile && (
                <p className="text-center text-[11px] text-zinc-600">Выбери проект, для которого строим план.</p>
              )}
            </div>

            {/* План */}
            {plan && plan.items.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <Sparkles size={18} className="text-primary" />
                    {plan.title || 'План на месяц'}
                  </h2>
                  <span className="text-xs text-zinc-500">
                    {doneCount}/{plan.items.length} сделано
                  </span>
                </div>

                <div className="space-y-3">
                  {plan.items.map((item) => {
                    const { done, stage, video } = itemProgress(item);
                    const goalClass = GOAL_STYLES[item.goal] || 'bg-white/5 text-zinc-400 border-white/10';
                    return (
                      <div
                        key={item.item_id}
                        data-content-plan-item={item.item_id}
                        className={`glass-panel p-4 grid grid-cols-[24px,minmax(0,1fr)] sm:grid-cols-[24px,minmax(0,1fr),auto] gap-3 transition-opacity ${done && !video ? 'opacity-50' : ''}`}
                      >
                        <button
                          type="button"
                          onClick={() => toggleDone(item.item_id)}
                          role="checkbox"
                          aria-checked={done}
                          disabled={Boolean(video)}
                          aria-label={video ? 'Ролик готов' : done ? 'Отметить как несделанное' : 'Отметить как сделанное'}
                          title={video ? 'Ролик готов' : done ? 'Отметить как несделанное' : 'Отметить как сделанное'}
                          className={`mt-0.5 w-6 h-6 shrink-0 rounded-lg border flex items-center justify-center transition-all ${
                            done
                              ? 'border-emerald-500/60 bg-emerald-500/20 text-emerald-300'
                              : 'border-white/15 bg-white/5 text-transparent hover:border-emerald-400/40'
                          }`}
                        >
                          <Check size={13} />
                        </button>

                        <div className="min-w-0 flex-1 space-y-1.5">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[10px] font-mono bg-white/10 text-zinc-300 px-2 py-0.5 rounded-full">
                              День {item.day}
                            </span>
                            <h3 className={`text-sm font-semibold ${done && !video ? 'line-through text-zinc-500' : 'text-zinc-100'}`}>
                              {item.title}
                            </h3>
                            {item.goal && (
                              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${goalClass}`}>
                                {item.goal}
                              </span>
                            )}
                            {(video || stage) && (
                              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${video ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200' : 'border-cyan-400/20 bg-cyan-400/10 text-cyan-200'}`}>
                                {video ? 'Готово' : WORKSPACE_STAGE_LABELS[stage]}
                              </span>
                            )}
                            {video && Number(video.duration) > 0 && (
                              <span className="text-[10px] text-zinc-500">{Number(video.duration).toFixed(1)} с</span>
                            )}
                          </div>
                          {item.hook && (
                            <p className="text-xs text-zinc-300">«{item.hook}»</p>
                          )}
                          {item.topic && (
                            <p className="text-xs text-zinc-500 leading-relaxed">{item.topic}</p>
                          )}
                          {item.cta && (
                            <p className="text-[11px] text-zinc-600">CTA: {item.cta}</p>
                          )}
                          {item.full_narration && (
                            <details className="text-xs text-zinc-300">
                              <summary className="cursor-pointer text-violet-300">Текст озвучки</summary>
                              <p className="mt-2 whitespace-pre-wrap leading-relaxed">{item.full_narration}</p>
                            </details>
                          )}
                        </div>

                        <div className="col-start-2 sm:col-start-auto flex flex-wrap items-center gap-2 sm:self-center">
                          {video && (
                            <>
                              <a href={getApiUrl(video.video_url)} target="_blank" rel="noreferrer"
                                aria-label={`Посмотреть: ${item.title}`} title="Посмотреть видео"
                                className="btn-secondary p-2 text-xs inline-flex items-center justify-center">
                                <Play size={15} />
                              </a>
                              <button type="button" onClick={() => handleDownloadVideo(item, video)}
                                disabled={Boolean(downloadingItemId)} title="Скачать видео"
                                aria-label={`Скачать: ${item.title}`}
                                className="btn-secondary p-2 text-xs inline-flex items-center justify-center disabled:opacity-50">
                                {downloadingItemId === item.item_id ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
                              </button>
                            </>
                          )}
                          <button
                            type="button"
                            onClick={() => handleCreateVideo(item)}
                            disabled={openingItemId === item.item_id}
                            className="btn-secondary px-3 py-2 text-xs flex items-center gap-1.5 text-violet-300"
                          >
                            {openingItemId === item.item_id ? <Loader2 size={12} className="animate-spin" />
                              : video ? <SquarePen size={12} /> : <Sparkles size={12} />}
                            {video ? 'Редактировать' : stage && stage !== 'not_started' ? 'Продолжить' : 'Сделать ролик'}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

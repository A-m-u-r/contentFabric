import React, { useEffect, useState } from 'react';
import { CalendarDays, Sparkles, Loader2, AlertCircle, RefreshCw, Check, Target, ChevronRight } from 'lucide-react';
import { getApiUrl } from '../config';
import {
  loadBusinessProfiles,
  saveBusinessProfiles,
  loadSelectedProfileId,
  saveSelectedProfileId,
  profileId,
  setPendingTopic,
} from '../lib/businessProfiles';

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

export default function ContentPlanTab({ geminiApiKey, authToken, usePlatformKeys = false, onCreateVideo, onOpenProjects }) {
  const [profiles, setProfiles] = useState(() => loadBusinessProfiles());
  const [selectedId, setSelectedId] = useState(() => loadSelectedProfileId());
  const [numItems, setNumItems] = useState(12);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState(null);

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
        }
      })
      .catch(() => {});
  }, [authToken]);

  useEffect(() => {
    setPlan(selectedId ? loadPlan(selectedId) : null);
  }, [selectedId]);

  const handleSelectProfile = (profile) => {
    const id = profileId(profile);
    setSelectedId(id);
    saveSelectedProfileId(id);
    setError('');
  };

  const handleGenerate = async () => {
    if (!selectedProfile) return;
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
        items: data.items || [],
        generatedAt: new Date().toISOString(),
        done: {},
      };
      setPlan(nextPlan);
      savePlan(selectedId, nextPlan);
    } catch (e) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const toggleDone = (index) => {
    if (!plan) return;
    const nextPlan = { ...plan, done: { ...plan.done, [index]: !plan.done?.[index] } };
    setPlan(nextPlan);
    savePlan(selectedId, nextPlan);
  };

  const handleCreateVideo = (item) => {
    const topic = [item.topic, item.hook ? `Хук: ${item.hook}` : '', item.cta ? `CTA: ${item.cta}` : '']
      .filter(Boolean)
      .join('\n');
    setPendingTopic(topic);
    onCreateVideo?.(item);
  };

  const doneCount = plan ? Object.values(plan.done || {}).filter(Boolean).length : 0;

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
                    План на месяц
                  </h2>
                  <span className="text-xs text-zinc-500">
                    {doneCount}/{plan.items.length} сделано
                  </span>
                </div>

                <div className="space-y-3">
                  {plan.items.map((item, i) => {
                    const done = Boolean(plan.done?.[i]);
                    const goalClass = GOAL_STYLES[item.goal] || 'bg-white/5 text-zinc-400 border-white/10';
                    return (
                      <div
                        key={i}
                        className={`glass-panel p-4 flex gap-4 transition-opacity ${done ? 'opacity-50' : ''}`}
                      >
                        <button
                          type="button"
                          onClick={() => toggleDone(i)}
                          aria-label={done ? 'Отметить как несделанное' : 'Отметить как сделанное'}
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
                            <h3 className={`text-sm font-semibold ${done ? 'line-through text-zinc-500' : 'text-zinc-100'}`}>
                              {item.title}
                            </h3>
                            {item.goal && (
                              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${goalClass}`}>
                                {item.goal}
                              </span>
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
                        </div>

                        <button
                          type="button"
                          onClick={() => handleCreateVideo(item)}
                          className="btn-secondary self-center px-3 py-2 text-xs flex items-center gap-1.5 shrink-0 text-violet-300"
                        >
                          <Sparkles size={12} /> Сделать ролик
                        </button>
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

import React, { useEffect, useState } from 'react';
import { Target, Plus, Pencil, Trash2, Check, X, Save, Sparkles, CalendarDays, AlertCircle } from 'lucide-react';
import { getApiUrl } from '../config';
import {
  loadBusinessProfiles,
  saveBusinessProfiles,
  loadSelectedProfileId,
  saveSelectedProfileId,
  profileId,
} from '../lib/businessProfiles';

const LANGUAGE_OPTIONS = [
  { id: 'ru', label: 'Русский', flag: '🇷🇺' },
  { id: 'en', label: 'English', flag: '🇺🇸' },
  { id: 'es', label: 'Español', flag: '🇪🇸' },
];

const GENDER_OPTIONS = [
  { id: 'female', label: 'Женщина', icon: '👩' },
  { id: 'male', label: 'Мужчина', icon: '👨' },
];

const FORMAT_OPTIONS = [
  { id: 'ugc', label: 'UGC 5 частей' },
  { id: 'storyboard_v3', label: 'Раскадровка V3' },
];

const EMPTY_DRAFT = {
  id: '',
  name: '',
  description: '',
  topic: '',
  language: 'ru',
  actorGender: 'female',
  scriptFormat: 'ugc',
};

function draftFromProfile(profile) {
  return {
    id: profile.id || '',
    name: profile.name || '',
    description: profile.description || '',
    topic: profile.topic || '',
    language: profile.language || 'ru',
    actorGender: profile.actorGender || profile.actor_gender || 'female',
    scriptFormat: profile.scriptFormat || profile.script_format || 'ugc',
  };
}

export default function ProjectsTab({ authToken, onUseInShorts, onOpenContentPlan }) {
  const [profiles, setProfiles] = useState(() => loadBusinessProfiles());
  const [selectedId, setSelectedId] = useState(() => loadSelectedProfileId());
  const [draft, setDraft] = useState(null); // null = форма закрыта
  const [formError, setFormError] = useState('');
  const [status, setStatus] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState('');

  const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});

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

  const persist = (next) => {
    setProfiles(next);
    saveBusinessProfiles(next);
  };

  const handleSelect = (profile) => {
    const id = profileId(profile);
    setSelectedId(id);
    saveSelectedProfileId(id);
  };

  const handleSaveDraft = async () => {
    const name = draft.name.trim();
    const description = draft.description.trim();
    if (!name) { setFormError('Дай проекту название.'); return; }
    if (!description) { setFormError('Описание бизнеса обязательно — на нём строятся сценарии.'); return; }

    setFormError('');
    const id = draft.id || `${Date.now()}`;
    const profile = {
      id,
      name,
      description,
      topic: draft.topic.trim(),
      language: draft.language,
      actorGender: draft.actorGender,
      actor_gender: draft.actorGender,
      scriptFormat: draft.scriptFormat,
      script_format: draft.scriptFormat,
      updatedAt: new Date().toISOString(),
    };
    const next = [profile, ...profiles.filter((item) => profileId(item) !== id)].slice(0, 20);
    persist(next);
    handleSelect(profile);
    setDraft(null);
    setStatus(`Проект «${name}» сохранён.`);

    if (authToken) {
      try {
        const res = await fetch(getApiUrl('/api/user/business-profiles'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({
            id,
            name,
            description,
            topic: draft.topic.trim(),
            language: draft.language,
            actor_gender: draft.actorGender,
            script_format: draft.scriptFormat,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data.profiles)) persist(data.profiles);
          setStatus(`Проект «${name}» сохранён в аккаунте.`);
        }
      } catch {
        setStatus(`Проект «${name}» сохранён локально, в аккаунт не записался.`);
      }
    }
  };

  const handleDelete = async (profile) => {
    const id = profileId(profile);
    persist(profiles.filter((item) => profileId(item) !== id));
    setConfirmDeleteId('');
    if (selectedId === id) {
      setSelectedId('');
      saveSelectedProfileId('');
    }
    setStatus(`Проект «${profile.name}» удалён.`);

    if (authToken && profile.id) {
      try {
        const res = await fetch(getApiUrl(`/api/user/business-profiles/${encodeURIComponent(profile.id)}`), {
          method: 'DELETE',
          headers: authHeaders(),
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data.profiles)) persist(data.profiles);
        }
      } catch { /* локально уже удалён */ }
    }
  };

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="max-w-5xl mx-auto p-6 pb-28 md:pb-8 lg:p-8">
        <div className="flex items-start justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-violet-500 to-fuchsia-500 rounded-xl flex items-center justify-center">
                <Target size={20} className="text-white" />
              </div>
              Проекты
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Сохрани бизнес один раз — потом выбирай его в AI Shorts и контент-плане без повторного ввода.
            </p>
          </div>
          <button
            type="button"
            onClick={() => { setDraft({ ...EMPTY_DRAFT }); setFormError(''); setStatus(''); }}
            className="btn-primary px-4 py-2.5 text-sm flex items-center gap-2 shrink-0"
          >
            <Plus size={15} /> Новый проект
          </button>
        </div>

        {status && (
          <p className="mb-4 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-zinc-400">
            {status}
          </p>
        )}

        {/* Форма создания / редактирования */}
        {draft && (
          <div className="glass-panel p-6 mb-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-zinc-100">
                {draft.id ? 'Редактирование проекта' : 'Новый проект'}
              </h2>
              <button
                type="button"
                onClick={() => setDraft(null)}
                className="text-zinc-500 hover:text-white transition-colors"
                aria-label="Закрыть форму"
              >
                <X size={16} />
              </button>
            </div>

            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-zinc-400">Название проекта</span>
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                className="input-field"
                placeholder="Например: Моя Форма 30+"
              />
            </label>

            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-zinc-400">Описание бизнеса / продукта</span>
              <textarea
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                rows={4}
                className="input-field resize-none text-sm"
                placeholder="Что продаём, кому, какой результат, какие ограничения, тон коммуникации."
              />
            </label>

            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-zinc-400">Тема роликов по умолчанию <span className="text-zinc-600">(необязательно)</span></span>
              <input
                value={draft.topic}
                onChange={(e) => setDraft({ ...draft, topic: e.target.value })}
                className="input-field"
                placeholder="Например: почему вечерний срыв начинается утром"
              />
            </label>

            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <span className="block text-xs font-medium text-zinc-400 mb-2">Язык</span>
                <div className="flex gap-1.5">
                  {LANGUAGE_OPTIONS.map((l) => (
                    <button
                      key={l.id}
                      type="button"
                      onClick={() => setDraft({ ...draft, language: l.id })}
                      className={`flex-1 rounded-lg border px-2 py-2 text-center text-xs transition-all ${
                        draft.language === l.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      {l.flag}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <span className="block text-xs font-medium text-zinc-400 mb-2">Пол актёра</span>
                <div className="flex gap-1.5">
                  {GENDER_OPTIONS.map((g) => (
                    <button
                      key={g.id}
                      type="button"
                      onClick={() => setDraft({ ...draft, actorGender: g.id })}
                      className={`flex-1 rounded-lg border px-2 py-2 text-center text-xs transition-all ${
                        draft.actorGender === g.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      {g.icon} {g.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <span className="block text-xs font-medium text-zinc-400 mb-2">Формат сценария</span>
                <div className="flex gap-1.5">
                  {FORMAT_OPTIONS.map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => setDraft({ ...draft, scriptFormat: f.id })}
                      className={`flex-1 rounded-lg border px-2 py-2 text-center text-[11px] transition-all ${
                        draft.scriptFormat === f.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {formError && (
              <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                <AlertCircle size={14} /> {formError}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setDraft(null)} className="btn-secondary px-4 py-2 text-sm">
                Отмена
              </button>
              <button
                type="button"
                onClick={handleSaveDraft}
                className="btn-primary px-4 py-2 text-sm flex items-center gap-2"
              >
                <Save size={14} /> Сохранить проект
              </button>
            </div>
          </div>
        )}

        {/* Список проектов */}
        {profiles.length === 0 && !draft ? (
          <div className="glass-panel p-10 text-center">
            <Target size={28} className="mx-auto text-zinc-600 mb-3" />
            <p className="text-sm text-zinc-400 font-medium">Пока нет ни одного проекта</p>
            <p className="text-xs text-zinc-600 mt-1 mb-4">
              Создай проект с описанием бизнеса — AI Shorts и контент-план будут использовать его как бриф.
            </p>
            <button
              type="button"
              onClick={() => { setDraft({ ...EMPTY_DRAFT }); setFormError(''); }}
              className="btn-primary px-4 py-2 text-sm inline-flex items-center gap-2"
            >
              <Plus size={14} /> Создать первый проект
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {profiles.map((profile) => {
              const id = profileId(profile);
              const active = selectedId === id;
              const lang = LANGUAGE_OPTIONS.find((l) => l.id === (profile.language || 'ru'));
              const format = FORMAT_OPTIONS.find((f) => f.id === (profile.scriptFormat || profile.script_format || 'ugc'));
              return (
                <div
                  key={id}
                  className={`glass-panel p-5 flex flex-col gap-3 transition-all ${
                    active ? 'border-violet-500/50 ring-1 ring-violet-500/20' : ''
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold text-zinc-100 break-words">{profile.name}</h3>
                      {active && (
                        <span className="mt-1 inline-flex items-center gap-1 text-[10px] bg-violet-500/20 text-violet-300 px-2 py-0.5 rounded-full">
                          <Check size={10} /> Активный проект
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => { setDraft(draftFromProfile(profile)); setFormError(''); setStatus(''); }}
                        className="p-1.5 rounded-lg text-zinc-500 hover:text-white hover:bg-white/10 transition-colors"
                        title="Редактировать"
                        aria-label="Редактировать проект"
                      >
                        <Pencil size={14} />
                      </button>
                      {confirmDeleteId === id ? (
                        <span className="flex items-center gap-1 rounded-lg bg-red-500/10 border border-red-500/30 px-2 py-1">
                          <span className="text-[10px] text-red-300">Удалить?</span>
                          <button
                            type="button"
                            onClick={() => handleDelete(profile)}
                            className="text-red-400 hover:text-red-200"
                            aria-label="Подтвердить удаление"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmDeleteId('')}
                            className="text-zinc-500 hover:text-white"
                            aria-label="Отменить удаление"
                          >
                            <X size={13} />
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(id)}
                          className="p-1.5 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="Удалить"
                          aria-label="Удалить проект"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </div>

                  <p className="text-xs text-zinc-500 leading-relaxed line-clamp-3">{profile.description}</p>
                  {profile.topic && (
                    <p className="text-[11px] text-zinc-600 line-clamp-1">Тема: {profile.topic}</p>
                  )}

                  <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                    {lang && <span className="rounded-full bg-white/5 px-2 py-0.5">{lang.flag} {lang.label}</span>}
                    {format && <span className="rounded-full bg-white/5 px-2 py-0.5">{format.label}</span>}
                  </div>

                  <div className="mt-auto flex flex-wrap gap-2 pt-1">
                    {!active && (
                      <button
                        type="button"
                        onClick={() => handleSelect(profile)}
                        className="btn-secondary px-3 py-1.5 text-xs flex items-center gap-1.5"
                      >
                        <Check size={12} /> Сделать активным
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => { handleSelect(profile); onUseInShorts?.(profile); }}
                      className="btn-secondary px-3 py-1.5 text-xs flex items-center gap-1.5 text-violet-300"
                    >
                      <Sparkles size={12} /> Ролик в AI Shorts
                    </button>
                    <button
                      type="button"
                      onClick={() => { handleSelect(profile); onOpenContentPlan?.(profile); }}
                      className="btn-secondary px-3 py-1.5 text-xs flex items-center gap-1.5 text-emerald-300"
                    >
                      <CalendarDays size={12} /> Контент-план
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

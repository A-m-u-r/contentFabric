import React, { useState, useEffect, useRef } from 'react';
import {
  Film,
  Download,
  Copy,
  Check,
  ExternalLink,
  Loader2,
  Play,
  User,
  Volume2,
  RefreshCw,
  X,
  Wand2,
  Upload,
  Pencil,
} from 'lucide-react';
import { getApiUrl } from '../config';

const LIPSYNC_MODEL_OPTIONS = [
  {
    id: 'sync-3',
    label: 'Sync 3',
    quality: 'Лучшее качество',
    price: '~$8 / мин',
    pricePerMinute: 8,
    description: 'Для финального ролика, когда губы заметно не попадают в озвучку.',
  },
  {
    id: 'lipsync-2-pro',
    label: 'Lipsync 2 Pro',
    quality: 'Высокое качество',
    price: '~$5 / мин',
    pricePerMinute: 5,
    description: 'Понятный баланс качества и стоимости для важных тестов.',
  },
  {
    id: 'lipsync-2',
    label: 'Lipsync 2',
    quality: 'Тестовый вариант',
    price: '~$3 / мин',
    pricePerMinute: 3,
    description: 'Дешевле, подходит для быстрых проверок перед финальной версией.',
  },
];

const mediaUrl = (url) => getApiUrl(url || '');

// Always offer the approved Russian recipe even when the ElevenLabs list is
// empty (no key / defaults fallback), so it stays one click away.
const RECOMMENDED_AVATAR_VOICES = [
  { voice_id: 'D5RRIJYa9pFwxiSpbGbR', name: 'Victoria — русский (рекомендуемый)' },
];

function buildVoiceOptions(voices) {
  const seen = new Set();
  const options = [];
  for (const v of [...RECOMMENDED_AVATAR_VOICES, ...(voices || [])]) {
    const id = v.voice_id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    options.push({ voice_id: id, name: v.name || id });
  }
  return options;
}

// Ключ, через который раскадровка готового ролика передаётся во вкладку
// «AI Shorts» (тот же приём, что и с темой из контент-плана).
const PENDING_STORYBOARD_KEY = 'saasshorts_pending_storyboard';

// Ролики до появления job_id в метаданных: id джоба лежит в самом URL видео
// (/videos/saas_<job_id>/файл.mp4).
function jobIdFromVideoUrl(videoUrl) {
  const match = /\/videos\/saas_([0-9a-fA-F-]{36})\//.exec(videoUrl || '');
  return match ? match[1] : '';
}

export default function UGCGallery({ falKey, authToken, usePlatformKeys = false, onEditStoryboard = null }) {
  const [tab, setTab] = useState('videos');
  const [videos, setVideos] = useState([]);
  const [avatars, setAvatars] = useState([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState('');
  const [lipSyncModel, setLipSyncModel] = useState('sync-3');
  const [lipSyncJobs, setLipSyncJobs] = useState({});
  const [headTemplateJobs, setHeadTemplateJobs] = useState({});
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [avatarPrompt, setAvatarPrompt] = useState('');
  const [avatarGenerating, setAvatarGenerating] = useState(false);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [avatarError, setAvatarError] = useState('');
  const [avatarStatus, setAvatarStatus] = useState('');
  const [avatarUploadFile, setAvatarUploadFile] = useState(null);
  const [avatarUploadPreview, setAvatarUploadPreview] = useState(null);
  const [newAvatarUrls, setNewAvatarUrls] = useState([]);
  const [voices, setVoices] = useState([]);
  const [voiceSaving, setVoiceSaving] = useState('');
  const [voiceError, setVoiceError] = useState('');

  const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});
  const isManagedKey = (value) => value === '__saved__' || value === '__platform__';

  const loadGallery = ({ showLoading = true } = {}) => {
    if (showLoading) setLoading(true);
    return Promise.all([
      fetch(getApiUrl('/api/saasshorts/gallery?limit=100'), { headers: authHeaders() }).then(r => r.ok ? r.json() : { videos: [] }),
      fetch(getApiUrl('/api/saasshorts/actor-gallery'), { headers: authHeaders() }).then(r => r.ok ? r.json() : { images: [] }),
    ])
      .then(([vData, aData]) => {
        const nextVideos = vData.videos || [];
        const nextAvatars = aData.images || [];
        setVideos(nextVideos);
        setAvatars(nextAvatars);
        return { videos: nextVideos, avatars: nextAvatars };
      })
      .catch(() => ({ videos: [], avatars: [] }))
      .finally(() => {
        if (showLoading) setLoading(false);
      });
  };

  useEffect(() => {
    loadGallery();
  }, []);

  useEffect(() => {
    const url = getApiUrl(`/api/saasshorts/voices${usePlatformKeys ? '?use_platform_keys=true' : ''}`);
    fetch(url, { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : { voices: [] }))
      .then((data) => setVoices(data.voices || []))
      .catch(() => setVoices([]));
  }, [usePlatformKeys, authToken]);

  const handleAttachVoice = async (avatarKey, voiceId, voiceName) => {
    setVoiceSaving(avatarKey);
    setVoiceError('');
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/avatar-voice'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ avatar_key: avatarKey, voice_id: voiceId || '', voice_name: voiceName || '' }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || 'Не удалось сохранить голос');
      }
      const data = await res.json();
      setAvatars((prev) => prev.map((a) => (a.key === avatarKey ? { ...a, voice: data.voice || null } : a)));
    } catch (e) {
      setVoiceError(e.message || 'Не удалось сохранить голос');
    } finally {
      setVoiceSaving('');
    }
  };

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(''), 2000);
  };

  const handleSelectAvatarFile = (file) => {
    if (!file) return;
    if (!file.type?.startsWith('image/')) {
      setAvatarError('Нужен файл изображения.');
      return;
    }

    const localPreview = URL.createObjectURL(file);
    setAvatarUploadFile(file);
    setAvatarUploadPreview({ localPreview, serverUrl: null });
    setAvatarError('');
    setNewAvatarUrls([]);
    setAvatarStatus('Фото выбрано. Нажми "Сохранить аватар", чтобы добавить его в галерею.');
  };

  const handleSaveAvatar = async () => {
    const file = avatarUploadFile;
    if (!file) {
      setAvatarError('Сначала выбери фото аватара.');
      return;
    }

    setAvatarUploading(true);
    setAvatarError('');
    setAvatarStatus('Сохраняю аватар...');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(getApiUrl('/api/saasshorts/actor-upload'), {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
      });

      if (!res.ok) {
        let msg = 'Не удалось загрузить аватар';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      if (data.url) {
        setAvatarUploadPreview((prev) => ({
          localPreview: prev?.localPreview || data.url,
          serverUrl: data.url,
        }));
        setNewAvatarUrls([data.url]);
        setAvatarUploadFile(null);
        setAvatarStatus(data.storage === 's3' ? 'Аватар сохранен в общей галерее.' : 'Аватар сохранен локально и доступен в этой галерее.');
        await loadGallery({ showLoading: false });
      }
    } catch (e) {
      setAvatarError(e.message || 'Не удалось загрузить аватар');
      setAvatarStatus('');
    } finally {
      setAvatarUploading(false);
    }
  };

  const handleGenerateAvatars = async () => {
    const prompt = avatarPrompt.trim();
    if (!prompt) {
      setAvatarError('Сначала опиши аватара.');
      return;
    }
    if (!falKey) {
      setAvatarError('Нет fal.ai API-ключа. Сначала добавь его в настройках.');
      return;
    }

    setAvatarGenerating(true);
    setAvatarError('');
    setAvatarStatus('');
    setNewAvatarUrls([]);

    try {
      const res = await fetch(getApiUrl('/api/saasshorts/actor-options'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
          ...(falKey && !isManagedKey(falKey) ? { 'X-Fal-Key': falKey } : {}),
        },
        body: JSON.stringify({
          actor_description: prompt,
          num_options: 3,
          use_platform_keys: usePlatformKeys,
        }),
      });

      if (!res.ok) {
        let msg = 'Не удалось сгенерировать аватаров';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      const urls = data.images || [];
      setNewAvatarUrls(urls);
      setAvatarStatus('Новые аватары сохранены в галерею.');
      await loadGallery({ showLoading: false });
    } catch (e) {
      setAvatarError(e.message || 'Не удалось сгенерировать аватаров');
    } finally {
      setAvatarGenerating(false);
    }
  };

  const pollLipSyncJob = (cardId, jobId) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(getApiUrl(`/api/saasshorts/status/${jobId}`), { headers: authHeaders() });
        if (!res.ok) return;
        const data = await res.json();
        const lastLog = data.logs?.[data.logs.length - 1] || '';

        if (data.status === 'completed') {
          clearInterval(interval);
          setLipSyncJobs((prev) => ({
            ...prev,
            [cardId]: {
              status: 'completed',
              message: 'Новая версия сохранена. Предыдущая версия осталась в истории.',
            },
          }));
          const gallery = await loadGallery({ showLoading: false });
          setSelectedVideo((prev) => {
            if (!prev || prev.video_id !== cardId) return prev;
            return gallery.videos.find((video) => video.video_id === cardId) || prev;
          });
        } else if (data.status === 'failed') {
          clearInterval(interval);
          setLipSyncJobs((prev) => ({ ...prev, [cardId]: { status: 'failed', message: lastLog || 'Failed' } }));
        } else {
          setLipSyncJobs((prev) => ({ ...prev, [cardId]: { status: 'processing', message: lastLog || 'Processing...' } }));
        }
      } catch {
        clearInterval(interval);
        setLipSyncJobs((prev) => ({ ...prev, [cardId]: { status: 'failed', message: 'Status check failed' } }));
      }
    }, 2500);
  };

  const handleLipSync = async (video, model = lipSyncModel) => {
    if (!falKey) {
      setLipSyncJobs((prev) => ({
        ...prev,
        [video.video_id]: { status: 'failed', message: 'fal.ai key missing' },
      }));
      return;
    }

    setLipSyncJobs((prev) => ({
      ...prev,
      [video.video_id]: { status: 'processing', message: 'Starting lip-sync...' },
    }));

    try {
      const res = await fetch(getApiUrl('/api/saasshorts/lipsync'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
          ...(falKey && !isManagedKey(falKey) ? { 'X-Fal-Key': falKey } : {}),
        },
        body: JSON.stringify({
          video_url: video.video_url,
          model,
          sync_mode: 'cut_off',
          use_platform_keys: usePlatformKeys,
        }),
      });

      if (!res.ok) {
        let msg = 'Lip-sync failed to start';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      pollLipSyncJob(video.video_id, data.job_id);
    } catch (e) {
      setLipSyncJobs((prev) => ({
        ...prev,
        [video.video_id]: { status: 'failed', message: e.message },
      }));
    }
  };

  const handleSaveHeadTemplate = async (video) => {
    setHeadTemplateJobs((prev) => ({
      ...prev,
      [video.video_id]: { status: 'processing', message: 'Сохраняю talking-head шаблон...' },
    }));
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/head-templates'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          video_url: video.video_url,
          label: video.title || 'Talking head template',
        }),
      });
      if (!res.ok) {
        let msg = 'Не удалось сохранить шаблон';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
      setHeadTemplateJobs((prev) => ({
        ...prev,
        [video.video_id]: { status: 'completed', message: 'Сохранено как reusable talking-head' },
      }));
    } catch (e) {
      setHeadTemplateJobs((prev) => ({
        ...prev,
        [video.video_id]: { status: 'failed', message: e.message || 'Не удалось сохранить шаблон' },
      }));
    }
  };

  if (loading && videos.length === 0 && avatars.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={24} className="animate-spin text-violet-400" />
        <span className="ml-2 text-zinc-400">Загружаю галерею...</span>
      </div>
    );
  }

  return (
    <div className="w-full max-w-full space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-bold text-zinc-200">UGC-галерея</h2>
          <p className="text-xs text-zinc-500">{videos.length} видео · {avatars.length} аватаров</p>
        </div>
        <a
          href={getApiUrl('/gallery')}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-lg px-2 py-2 text-xs text-violet-400 transition-colors hover:bg-violet-500/10 hover:text-violet-300"
        >
          <ExternalLink size={12} /> Публичная галерея
        </a>
      </div>

      {/* Tabs */}
      <div className="flex w-full gap-1 rounded-lg bg-white/5 p-1 sm:w-fit">
        <button
          onClick={() => setTab('videos')}
          className={`flex-1 rounded-md px-4 py-2.5 text-xs font-medium transition-all sm:flex-none ${
            tab === 'videos' ? 'bg-violet-500/20 text-violet-300' : 'text-zinc-400 hover:text-white'
          }`}
        >
          <Film size={12} className="inline mr-1.5" />Видео ({videos.length})
        </button>
        <button
          onClick={() => setTab('avatars')}
          className={`flex-1 rounded-md px-4 py-2.5 text-xs font-medium transition-all sm:flex-none ${
            tab === 'avatars' ? 'bg-violet-500/20 text-violet-300' : 'text-zinc-400 hover:text-white'
          }`}
        >
          <User size={12} className="inline mr-1.5" />Аватары ({avatars.length})
        </button>
      </div>

      {/* Videos Tab */}
      {tab === 'videos' && (
        videos.length === 0 ? (
          <div className="text-center py-16">
            <Film size={40} className="mx-auto text-zinc-700 mb-3" />
            <p className="text-sm text-zinc-500">Пока нет роликов. Сгенерируй первый в AI Shorts.</p>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
            {videos.map((video) => (
              <VideoCard
                key={video.video_id}
                video={video}
                onOpen={setSelectedVideo}
                lipSyncJob={lipSyncJobs[video.video_id]}
              />
            ))}
          </div>
        )
      )}

      {/* Avatars Tab */}
      {tab === 'avatars' && (
        <div className="space-y-5">
          <section className="space-y-4">
            <div>
              <h3 className="text-base font-semibold text-zinc-100">Аватары</h3>
              <p className="text-xs text-zinc-500 mt-1">
                Загружай свои фото или генерируй ИИ-аватаров здесь. Потом выбирай их в генераторе роликов.
              </p>
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(280px,0.9fr)_minmax(320px,1.1fr)]">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 space-y-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 rounded-lg bg-primary/15 p-2 text-violet-300">
                    <Upload size={17} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-zinc-100">Загрузить своего аватара</h4>
                    <p className="text-xs text-zinc-500 mt-1">
                      Подойдет фото лица или портрет в стиле UGC. Оно сохранится в списке аватаров.
                    </p>
                  </div>
                </div>

                <label className="flex min-h-[164px] cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 bg-black/20 px-4 py-5 text-center transition-colors hover:border-primary/50 hover:bg-primary/5">
                  {avatarUploading ? (
                    <Loader2 size={22} className="animate-spin text-violet-300" />
                  ) : avatarUploadPreview ? (
                    <img src={avatarUploadPreview.localPreview} alt="Выбранный аватар" className="h-24 w-20 rounded-xl object-cover border border-white/10" />
                  ) : (
                    <Upload size={22} className="text-zinc-500" />
                  )}
                  <span className="text-sm font-medium text-zinc-300">
                    {avatarUploading ? 'Загружаю...' : 'Выбрать фото'}
                  </span>
                  <span className="text-[11px] text-zinc-600">PNG, JPG или WebP</span>
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      handleSelectAvatarFile(file);
                      e.target.value = '';
                    }}
                  />
                </label>

                <div className="flex flex-col sm:flex-row gap-2">
                  <button
                    type="button"
                    onClick={handleSaveAvatar}
                    disabled={avatarUploading || !avatarUploadFile}
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-white hover:bg-violet-600 disabled:opacity-50 disabled:hover:bg-primary transition-colors"
                  >
                    {avatarUploading ? (
                      <><Loader2 size={16} className="animate-spin" /> Сохраняю...</>
                    ) : (
                      <><Check size={16} /> Сохранить аватар</>
                    )}
                  </button>
                  {avatarUploadPreview && (
                    <button
                      type="button"
                      onClick={() => {
                        setAvatarUploadFile(null);
                        setAvatarUploadPreview(null);
                        setAvatarStatus('');
                      }}
                      className="inline-flex items-center justify-center rounded-xl border border-white/10 px-4 py-3 text-sm font-medium text-zinc-300 hover:bg-white/5 transition-colors"
                    >
                      Сбросить
                    </button>
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-violet-500/20 bg-violet-500/5 p-5 space-y-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 rounded-lg bg-violet-500/20 p-2 text-violet-300">
                    <Wand2 size={17} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-zinc-100">Сгенерировать ИИ-аватаров</h4>
                    <p className="text-xs text-zinc-500 mt-1">
                      Создает 3 варианта и сохраняет их в эту галерею.
                    </p>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">
                    Описание аватара
                  </label>
                  <textarea
                    value={avatarPrompt}
                    onChange={(e) => setAvatarPrompt(e.target.value)}
                    rows={4}
                    className="input-field resize-none text-sm"
                    placeholder="Например: естественный портрет женщины 30 лет, нейтральная одежда, обычный фон, без ноутбука и гарнитуры"
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">
                    Пиши коротко и конкретно. Избегай ноутбуков, гарнитур, микрофонов и студийного ИИ-фона.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={handleGenerateAvatars}
                  disabled={avatarGenerating || !falKey || !avatarPrompt.trim()}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-3 text-sm font-semibold text-white hover:bg-violet-400 disabled:opacity-50 disabled:hover:bg-violet-500 transition-colors"
                >
                  {avatarGenerating ? (
                    <><Loader2 size={16} className="animate-spin" /> Генерирую...</>
                  ) : (
                    <><User size={16} /> Сгенерировать 3 аватара (~$0.06)</>
                  )}
                </button>
                {!falKey && (
                  <p className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                    Генерация требует fal.ai API-ключ. Загрузка фото работает без него.
                  </p>
                )}
              </div>
            </div>

            {avatarStatus && (
              <p className="rounded-lg border border-green-500/20 bg-green-500/10 px-3 py-2 text-xs text-green-200">{avatarStatus}</p>
            )}
            {avatarError && (
              <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">{avatarError}</p>
            )}
          </section>

          {newAvatarUrls.length > 0 && (
            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-violet-300">Новые аватары</h3>
              <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-3">
                {newAvatarUrls.map((url, i) => (
                  <AvatarCard
                    key={`${url}-${i}`}
                    avatar={{ url, key: `new-${i}`, description: avatarPrompt }}
                    copied={copied}
                    onCopy={handleCopy}
                  />
                ))}
              </div>
            </section>
          )}

          {avatars.length === 0 ? (
            <div className="text-center py-12 rounded-2xl border border-dashed border-white/10 bg-white/[0.03]">
              <User size={40} className="mx-auto text-zinc-700 mb-3" />
              <p className="text-sm text-zinc-500">Пока нет сохраненных аватаров. Загрузи фото или сгенерируй первый набор выше.</p>
            </div>
          ) : (
            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Сохраненные аватары</h3>
              {voiceError && (
                <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">{voiceError}</p>
              )}
              <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-3">
                {avatars.map((avatar, i) => (
                  <AvatarCard
                    key={avatar.key || i}
                    avatar={avatar}
                    copied={copied}
                    onCopy={handleCopy}
                    voiceOptions={buildVoiceOptions(voices)}
                    onAttachVoice={handleAttachVoice}
                    voiceSaving={voiceSaving === avatar.key}
                  />
                ))}
              </div>
            </section>
          )}
          </div>
      )}

      {selectedVideo && (
        <VideoActionModal
          video={selectedVideo}
          copied={copied}
          falKey={falKey}
          lipSyncModel={lipSyncModel}
          lipSyncJob={lipSyncJobs[selectedVideo.video_id]}
          headTemplateJob={headTemplateJobs[selectedVideo.video_id]}
          onClose={() => setSelectedVideo(null)}
          onCopy={handleCopy}
          onModelChange={setLipSyncModel}
          onLipSync={handleLipSync}
          onSaveHeadTemplate={handleSaveHeadTemplate}
          onEditStoryboard={(video) => {
            try {
              localStorage.setItem(PENDING_STORYBOARD_KEY, JSON.stringify({
                video_id: video.video_id,
                // Джоб, в котором лежат оплаченные клипы и кадры: пересъёмка
                // берёт из него всё, что пользователь не менял.
                job_id: video.job_id || jobIdFromVideoUrl(video.video_url),
                title: video.title,
                caption: video.caption,
                hashtags: video.hashtags,
                full_narration: video.full_narration,
                actor_description: video.actor_description,
                language: video.language,
                shots: video.shots || [],
                shots_archived: video.shots_archived || [],
                storyboard_generation_mode: video.storyboard_generation_mode,
              }));
            } catch (e) {
              console.warn('Не удалось передать раскадровку', e);
              return;
            }
            setSelectedVideo(null);
            onEditStoryboard?.();
          }}
        />
      )}
    </div>
  );
}

function AvatarCard({ avatar, copied, onCopy, voiceOptions = null, onAttachVoice = null, voiceSaving = false }) {
  const boundVoiceId = avatar.voice?.voice_id || '';
  // Make sure the currently bound voice is always selectable, even if the
  // ElevenLabs list didn't return it — otherwise the dropdown would show
  // "no voice" while a binding exists, and one click would silently drop it.
  const options = boundVoiceId && voiceOptions && !voiceOptions.some((v) => v.voice_id === boundVoiceId)
    ? [{ voice_id: boundVoiceId, name: avatar.voice?.voice_name || boundVoiceId }, ...voiceOptions]
    : voiceOptions;
  return (
    <div className="group rounded-xl overflow-hidden border border-white/10 bg-white/5 hover:border-white/20 transition-all">
      <div className="relative aspect-[3/4] bg-black">
        <img src={mediaUrl(avatar.url)} alt="Аватар" className="w-full h-full object-cover" />
        {boundVoiceId && (
          <span
            className="absolute top-1.5 left-1.5 flex items-center gap-1 rounded-full bg-violet-500/80 px-1.5 py-0.5 text-[8px] font-semibold text-white"
            title={`Голос: ${avatar.voice?.voice_name || boundVoiceId}`}
          >
            <Volume2 size={8} />голос
          </span>
        )}
      </div>
      <div className="p-2 space-y-1">
        {avatar.description ? (
          <div className="relative pr-4">
            <p className="text-[9px] text-zinc-400 line-clamp-2">{avatar.description}</p>
            <button
              type="button"
              onClick={() => onCopy(avatar.description, `avatar-${avatar.key}`)}
              className="absolute top-0 right-0 p-0.5 text-zinc-600 hover:text-zinc-300"
              title="Скопировать prompt"
              aria-label="Скопировать prompt аватара"
            >
              {copied === `avatar-${avatar.key}` ? <Check size={9} /> : <Copy size={9} />}
            </button>
          </div>
        ) : (
          <p className="text-[9px] text-zinc-600 italic">Нет описания</p>
        )}
        {onAttachVoice && voiceOptions && (
          <label className="block space-y-0.5">
            <span className="flex items-center gap-1 text-[8px] uppercase tracking-wide text-zinc-500">
              <Volume2 size={8} />Голос
            </span>
            <select
              value={boundVoiceId}
              disabled={voiceSaving}
              onChange={(e) => {
                const id = e.target.value;
                const opt = options.find((v) => v.voice_id === id);
                onAttachVoice(avatar.key, id, opt?.name || '');
              }}
              className="w-full rounded-md border border-white/10 bg-black/30 px-1.5 py-1 text-[9px] text-zinc-200 focus:border-violet-400/50 focus:outline-none disabled:opacity-50"
              title="Прикрепить голос к этому аватару"
            >
              <option value="">— без голоса —</option>
              {options.map((v) => (
                <option key={v.voice_id} value={v.voice_id}>{v.name}</option>
              ))}
            </select>
          </label>
        )}
        <a
          href={mediaUrl(avatar.url)}
          download
          className="block text-center text-[9px] bg-white/5 hover:bg-white/10 text-zinc-400 py-1 rounded-md transition-colors"
        >
          <Download size={9} className="inline mr-0.5" />Скачать
        </a>
      </div>
    </div>
  );
}

function VideoCard({ video, onOpen, lipSyncJob }) {
  const videoRef = useRef(null);
  const [playing, setPlaying] = useState(false);

  const handleMouseEnter = () => {
    if (videoRef.current) {
      videoRef.current.play().catch(() => {});
      setPlaying(true);
    }
  };

  const handleMouseLeave = () => {
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = 0;
      setPlaying(false);
    }
  };

  const mode = video.video_mode;

  return (
    <button
      type="button"
      onClick={() => onOpen(video)}
      className="group text-left rounded-xl overflow-hidden border border-white/10 bg-white/5 hover:border-white/20 transition-all focus:outline-none focus:ring-2 focus:ring-violet-500/70"
    >
      <div
        className="relative aspect-[9/16] bg-black"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <video
          ref={videoRef}
          src={mediaUrl(video.video_url)}
          poster={mediaUrl(video.actor_url)}
          muted
          playsInline
          preload="metadata"
          className="w-full h-full object-cover"
        />
        {!playing && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/20">
            <Play size={20} className="text-white/70" />
          </div>
        )}
        <div className="absolute top-1.5 right-1.5">
          <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded-full ${
            mode === 'lowcost' ? 'bg-green-500 text-black' :
            mode === 'premium' ? 'bg-violet-500 text-white' :
            'bg-blue-500 text-white'
          }`}>
            {mode === 'lowcost' ? 'LOW COST' : mode === 'premium' ? 'PREMIUM' : 'STANDARD'}
          </span>
        </div>
        {lipSyncJob?.status === 'processing' && (
          <div className="absolute inset-x-1.5 bottom-1.5 rounded-md bg-black/70 px-2 py-1 text-[9px] text-violet-200 flex items-center gap-1">
            <Loader2 size={9} className="animate-spin" /> Lip-sync...
          </div>
        )}
      </div>

      <div className="p-2 space-y-1">
        <h3 className="text-[11px] font-semibold text-zinc-200 truncate">{video.title || 'Untitled'}</h3>
        <p className="text-[9px] text-zinc-500">
          {video.duration?.toFixed(0)}s · ${video.cost_estimate?.total?.toFixed(2) || '?'}
        </p>
        {video.voice_name && (
          <p
            className="truncate text-[9px] text-sky-300/80"
            title={`Голос: ${video.voice_name}${video.voice_id ? ` (${video.voice_id})` : ''}${video.voice_model ? ` · ${video.voice_model}` : ''}`}
          >
            Голос: {video.voice_name}{video.voice_model ? ` · ${video.voice_model}` : ''}
          </p>
        )}
        {video.caption && (
          <p className="text-[9px] text-zinc-400 line-clamp-2">{video.caption}</p>
        )}
        {lipSyncJob?.status === 'failed' && (
          <p className="text-[9px] text-red-400 line-clamp-2">{lipSyncJob.message}</p>
        )}
      </div>
    </button>
  );
}

function VideoActionModal({
  video,
  copied,
  falKey,
  lipSyncModel,
  lipSyncJob,
  headTemplateJob,
  onClose,
  onCopy,
  onModelChange,
  onLipSync,
  onSaveHeadTemplate,
  onEditStoryboard,
}) {
  const caption = video.caption || '';
  const hashtags = (video.hashtags || []).join(' ');
  const isProcessing = lipSyncJob?.status === 'processing';
  const isSavingHeadTemplate = headTemplateJob?.status === 'processing';
  const isLocalSaasVideo = typeof video.video_url === 'string' && video.video_url.includes('/videos/saas_');
  const selectedModel = LIPSYNC_MODEL_OPTIONS.find((option) => option.id === lipSyncModel) || LIPSYNC_MODEL_OPTIONS[0];
  const selectedLipSyncEstimate = ((Number(video.duration) || 0) / 60) * selectedModel.pricePerMinute;
  const versions = Array.isArray(video.versions) ? video.versions.filter((item) => item?.video_url) : [];
  const formatVersionDate = (value) => {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm p-4 flex items-center justify-center">
      <div className="flex w-full max-w-5xl max-h-[92vh] flex-col overflow-hidden rounded-2xl border border-white/10 bg-zinc-950 shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-white/10 px-5 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-violet-300">Готовый ролик</p>
            <h3 className="text-lg font-bold text-zinc-100">{video.title || 'Untitled'}</h3>
            <p className="text-xs text-zinc-500">
              {video.duration?.toFixed(1) || '?'}s В· ${video.cost_estimate?.total?.toFixed(2) || '?'}
            </p>
            {video.voice_name && (
              <p className="mt-1 text-xs text-sky-300/80">
                Голос: {video.voice_name}
                {video.voice_id ? ` (${video.voice_id})` : ''}
                {video.voice_model ? ` · ${video.voice_model}` : ''}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-200"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 gap-5 overflow-y-auto custom-scrollbar p-4 sm:p-5 lg:grid-cols-[minmax(260px,340px),1fr]">
          <div className="space-y-3">
            <div className="rounded-2xl overflow-hidden bg-black border border-white/10">
              <video
                src={mediaUrl(video.video_url)}
                poster={mediaUrl(video.actor_url)}
                controls
                playsInline
                className="w-full aspect-[9/16] object-contain bg-black"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <a
                href={mediaUrl(video.video_url)}
                download
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-white hover:bg-violet-600 transition-colors"
              >
                <Download size={15} /> Скачать
              </a>
              <a
                href={getApiUrl(`/video/${video.video_id}`)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-sm font-semibold text-zinc-200 hover:bg-white/15 transition-colors"
              >
                <ExternalLink size={15} /> Открыть
              </a>
            </div>
            {/* Раскадровка сохраняется вместе с роликом — её можно открыть в
                редакторе, доснять кадры и пересобрать видео. */}
            {(video.shots || []).length > 0 && onEditStoryboard && (
              <button
                type="button"
                onClick={() => onEditStoryboard(video)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-violet-400/30 bg-violet-500/10 px-3 py-2 text-sm font-semibold text-violet-200 transition-colors hover:bg-violet-500/20"
              >
                <Pencil size={15} /> Редактировать раскадровку ({(video.shots || []).length} кадр.)
              </button>
            )}
            {versions.length > 0 && (
              <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-xs font-semibold text-zinc-200">Версии видео</h4>
                  <span className="text-[10px] text-zinc-500">{versions.length}</span>
                </div>
                <div className="space-y-2">
                  {versions.map((version, index) => (
                    <div
                      key={`${version.id || index}-${version.video_url}`}
                      className={`rounded-xl border px-3 py-2 ${
                        version.current
                          ? 'border-primary/30 bg-primary/10'
                          : 'border-white/10 bg-black/20'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold text-zinc-100">
                            {version.id || `v${index + 1}`} · {version.label || 'Версия'}
                          </p>
                          <p className="mt-0.5 text-[10px] text-zinc-500">
                            {formatVersionDate(version.created_at)}
                            {version.lipsync_cost_estimate != null ? ` · ~$${Number(version.lipsync_cost_estimate).toFixed(2)}` : ''}
                          </p>
                        </div>
                        {version.current && (
                          <span className="shrink-0 rounded-full bg-primary/20 px-2 py-0.5 text-[9px] font-semibold text-violet-200">
                            Текущая
                          </span>
                        )}
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        <a
                          href={mediaUrl(version.video_url)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center justify-center gap-1 rounded-lg bg-white/5 px-2 py-2.5 text-[10px] font-semibold text-zinc-300 hover:bg-white/10"
                        >
                          <ExternalLink size={11} /> Смотреть
                        </a>
                        <a
                          href={mediaUrl(version.video_url)}
                          download
                          className="inline-flex items-center justify-center gap-1 rounded-lg bg-white/5 px-2 py-2.5 text-[10px] font-semibold text-zinc-300 hover:bg-white/10"
                        >
                          <Download size={11} /> Скачать
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
            <button
              type="button"
              onClick={() => onSaveHeadTemplate(video)}
              disabled={!isLocalSaasVideo || isSavingHeadTemplate}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-primary/25 bg-primary/10 px-3 py-2 text-sm font-semibold text-violet-200 hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
            >
              {isSavingHeadTemplate ? (
                <>
                  <Loader2 size={15} className="animate-spin" /> Сохраняю шаблон...
                </>
              ) : headTemplateJob?.status === 'completed' ? (
                <>
                  <Check size={15} /> Talking-head сохранен
                </>
              ) : (
                <>
                  <User size={15} /> Сохранить talking-head
                </>
              )}
            </button>
            {!isLocalSaasVideo && (
              <p className="text-xs text-zinc-500">
                Сохранение шаблона доступно для роликов, созданных в AI Shorts.
              </p>
            )}
            {headTemplateJob?.message && (
              <p className={`rounded-lg px-3 py-2 text-xs ${
                headTemplateJob.status === 'failed'
                  ? 'border border-red-500/20 bg-red-500/10 text-red-200'
                  : 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-200'
              }`}>
                {headTemplateJob.message}
              </p>
            )}
          </div>

          <div className="space-y-5">
            <section className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <h4 className="text-sm font-semibold text-zinc-300">Caption</h4>
                {caption && (
                  <button
                    type="button"
                    onClick={() => onCopy(`${caption}\n${hashtags}`, `modal-caption-${video.video_id}`)}
                    className="inline-flex items-center gap-1.5 rounded-lg px-2 py-2 text-xs text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200"
                  >
                    {copied === `modal-caption-${video.video_id}` ? <Check size={13} /> : <Copy size={13} />}
                    Копировать
                  </button>
                )}
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-zinc-300 min-h-[52px]">
                {caption || 'Caption не найден.'}
              </div>
              {hashtags && (
                <p className="text-xs text-violet-300/80">{hashtags}</p>
              )}
            </section>

            <section className="space-y-3 rounded-2xl border border-white/10 bg-white/[0.035] p-4">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-lg bg-violet-500/20 p-2 text-violet-300">
                  <Wand2 size={17} />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-zinc-100">ИИ-действия</h4>
                  <p className="text-xs text-zinc-500">
                    Здесь меняем уже готовый ролик. Для плохого попадания губ используй повторную синхронизацию с сохраненной озвучкой.
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                  <p className="text-xs font-semibold text-zinc-400">Повторная синхронизация губ</p>
                  <p className="text-[11px] text-zinc-500">
                    Примерно ${selectedLipSyncEstimate.toFixed(2)} для этого ролика · {selectedModel.price}
                  </p>
                </div>
                <div className="grid gap-2 md:grid-cols-3">
                  {LIPSYNC_MODEL_OPTIONS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => onModelChange(option.id)}
                      className={`text-left rounded-xl border p-3 transition-colors ${
                        lipSyncModel === option.id
                          ? 'border-violet-400 bg-violet-500/15'
                          : 'border-white/10 bg-black/20 hover:border-white/20'
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-zinc-100">{option.label}</span>
                        <span className="text-[11px] text-zinc-500">{option.price}</span>
                      </div>
                      <p className="mt-1 text-xs text-violet-200">{option.quality}</p>
                      <p className="mt-1 text-xs text-zinc-500">{option.description}</p>
                    </button>
                  ))}
                </div>
              </div>

              {!isLocalSaasVideo && (
                <p className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  Для lip-sync нужны локальные исходники AI Shorts: финальное видео и сохраненная озвучка.
                </p>
              )}

              <button
                type="button"
                onClick={() => onLipSync(video, selectedModel.id)}
                disabled={!falKey || !isLocalSaasVideo || isProcessing}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-3 text-sm font-semibold text-white hover:bg-violet-400 disabled:opacity-50 disabled:hover:bg-violet-500 transition-colors"
              >
                {isProcessing ? (
                  <>
                    <Loader2 size={16} className="animate-spin" /> Синхронизирую губы...
                  </>
                ) : lipSyncJob?.status === 'completed' ? (
                  <>
                    <RefreshCw size={16} /> Обновить ещё раз через {selectedModel.label}
                  </>
                ) : (
                  <>
                    <Volume2 size={16} /> Синхронизировать через {selectedModel.label}
                  </>
                )}
              </button>

              {!falKey && (
                <p className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  Нужен fal.ai API key в настройках приложения.
                </p>
              )}
              {lipSyncJob?.status === 'processing' && lipSyncJob.message && (
                <p className="text-xs text-violet-200">{lipSyncJob.message}</p>
              )}
              {lipSyncJob?.status === 'failed' && (
                <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">{lipSyncJob.message}</p>
              )}
              {lipSyncJob?.status === 'completed' && (
                <p className="rounded-lg border border-green-500/20 bg-green-500/10 px-3 py-2 text-xs text-green-200">
                  Ролик обновлен. Если браузер показывает старый кадр, закрой и открой видео заново.
                </p>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

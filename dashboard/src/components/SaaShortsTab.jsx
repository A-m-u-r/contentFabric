import React, { useState, useEffect, useRef, useLayoutEffect } from 'react';
import { Globe, Sparkles, Download, Copy, Check, ChevronRight, ChevronLeft, Loader2, AlertCircle, Volume2, User, Film, Terminal, ChevronDown, ChevronUp, RefreshCw, Zap, Target, TrendingUp, MessageSquare, Eye, Share2, Calendar, Upload, Pencil, Save, X, Plus, Trash2, Undo2, GripVertical, Settings2 } from 'lucide-react';
import { getApiUrl } from '../config';
import {
  loadBusinessProfiles,
  saveBusinessProfiles,
  loadSelectedProfileId,
  saveSelectedProfileId,
  profileId as businessProfileKey,
  peekPendingTopic,
  clearPendingTopic,
} from '../lib/businessProfiles';

const STYLE_OPTIONS = [
  { id: 'ugc', label: 'Разговор в камеру', desc: 'Живо и по-человечески, как сторис у знакомой' },
  { id: 'educational', label: 'Обучающий', desc: 'Проблема → 2-3 конкретных шага → вывод' },
  { id: 'shock', label: 'Шок-факт', desc: 'Неожиданное заявление первой фразой, потом объяснение' },
  { id: 'story', label: 'История', desc: 'Мини-сюжет от первого лица: было → перелом → стало' },
  { id: 'comparison', label: 'До/после', desc: 'Контраст: как было раньше и как стало теперь' },
];

const SCRIPT_FORMAT_OPTIONS = [
  { id: 'ugc', label: 'Простой (5 частей)', desc: 'Актёр говорит в камеру, между репликами — предметные вставки' },
  { id: 'storyboard_v3', label: 'Раскадровка (рекомендуем)', desc: 'ИИ распишет ролик по кадрам: сцены, реплики, движение камеры' },
];

const TEXT_MODEL_OPTIONS = [
  { id: 'fast', label: 'Gemini 3.5 Flash', desc: 'Максимальная бесплатная модель для генерации текста и сценариев' },
  { id: 'pro', label: 'Gemini 3.1 Pro', desc: 'Платный режим для оффера, раскадровки и сложной логики' },
];

const TTS_PROVIDER_OPTIONS = [
  { id: 'auto', label: 'Auto fallback', desc: 'ElevenLabs first, fal MiniMax if needed' },
  { id: 'elevenlabs', label: 'ElevenLabs', desc: 'Best voice quality, may need paid plan' },
  { id: 'fal_minimax', label: 'fal MiniMax', desc: 'Russian TTS via fal.ai balance' },
];

const BROLL_MODE_OPTIONS = [
  { id: 'mockup', label: 'Кадры с товаром', desc: 'Аккуратные вставки с продуктом, без ИИ-стоков' },
  { id: 'off', label: 'Без вставок', desc: 'Только человек в кадре, ничего не отвлекает' },
  { id: 'ai', label: 'ИИ-картинки', desc: 'Вставки рисует нейросеть — иногда выглядят искусственно' },
];

const STORYBOARD_GENERATION_OPTIONS = [
  {
    id: 'sliced_avatar',
    label: 'Актёр говорит в кадре (рекомендуем)',
    desc: 'Одна озвучка на весь ролик, актёр проговаривает текст — губы совпадают с речью. Лучший вариант, когда в кадре человек.',
  },
  {
    id: 'per_shot',
    label: 'Каждый кадр отдельно',
    desc: 'Ролик собирается из 5–6 отдельных клипов, голос накладывается поверх — губы не попадают в слова. Зато неудачный кадр можно перегенерировать отдельно.',
  },
  {
    id: 'multi_shot',
    label: 'Весь ролик одной генерацией',
    desc: 'Быстрый черновик: всё видео создаётся одним запросом. Дешевле и быстрее, но плохой кадр отдельно не заменить — только перегенерировать весь ролик.',
  },
];

const VIDEO_MODE_OPTIONS = [
  {
    id: 'lowcost',
    label: 'Черновик (дёшево)',
    price: 'from ~$0.45',
    accent: 'green',
    desc: 'Модель Hailuo. Быстро проверить идею ролика — картинка может плыть и глючить, для публикации не годится.',
  },
  {
    id: 'standard',
    label: 'Стандарт',
    price: 'from ~$0.75',
    accent: 'blue',
    desc: 'Модель Kling Avatar v2. Оптимально по цене и качеству — подходит для большинства роликов.',
  },
  {
    id: 'premium',
    label: 'Про',
    price: 'from ~$1.45',
    accent: 'violet',
    desc: 'Kling Avatar v2 Pro: та же модель, но чётче лицо и движения. Примерно вдвое дороже Стандарта.',
  },
  {
    id: 'storyboard_v3_standard',
    label: 'Kling V3 — Стандарт',
    price: 'from ~$1.30',
    accent: 'blue',
    desc: 'Оптимально по цене и качеству. Подходит для большинства роликов.',
  },
  {
    id: 'storyboard_v3_pro',
    label: 'Kling V3 — Про',
    price: 'from ~$1.75',
    accent: 'violet',
    desc: 'Та же модель, но чётче лица, руки и движения. Дороже примерно на треть.',
  },
  {
    id: 'storyboard_veo31_quality',
    label: 'Google Veo 3.1 — Максимум',
    price: 'from ~$3.20',
    accent: 'amber',
    desc: 'Максимум качества картинки в покадровых режимах. Говорящие кадры всё равно делает Kling Avatar, озвучка — наша (ElevenLabs).',
  },
];

function videoModeOption(mode) {
  return VIDEO_MODE_OPTIONS.find((option) => option.id === mode) || VIDEO_MODE_OPTIONS[1];
}

const LIPSYNC_MODEL_OPTIONS = [
  { id: 'sync-3', label: 'Sync 3', desc: 'Best quality, final publish', pricePerMinute: 8 },
  { id: 'lipsync-2-pro', label: 'Lipsync 2 Pro', desc: 'Strong quality, close-up repair', pricePerMinute: 5 },
  { id: 'lipsync-2', label: 'Lipsync 2', desc: 'Cheaper test pass', pricePerMinute: 3 },
];

const MINIMAX_VOICE_OPTIONS = {
  ru: [
    { id: 'Russian_AmbitiousWoman', name: 'Ambitious Woman', desc: 'confident female' },
    { id: 'Russian_BrightHeroine', name: 'Bright Heroine', desc: 'energetic female' },
    { id: 'Russian_ReliableMan', name: 'Reliable Man', desc: 'calm male' },
    { id: 'Russian_AttractiveGuy', name: 'Attractive Guy', desc: 'confident male' },
  ],
  es: [
    { id: 'Spanish_ConfidentWoman', name: 'Confident Woman', desc: 'female' },
    { id: 'Spanish_ReliableMan', name: 'Reliable Man', desc: 'male' },
  ],
  en: [
    { id: 'Wise_Woman', name: 'Wise Woman', desc: 'female' },
    { id: 'Deep_Voice_Man', name: 'Deep Voice Man', desc: 'male' },
  ],
};

function defaultMiniMaxVoice(language, actorGender) {
  if (language === 'ru') return actorGender === 'male' ? 'Russian_ReliableMan' : 'Russian_AmbitiousWoman';
  if (language === 'es') return actorGender === 'male' ? 'Spanish_ReliableMan' : 'Spanish_ConfidentWoman';
  return actorGender === 'male' ? 'Deep_Voice_Man' : 'Wise_Woman';
}

const CACHE_KEY = 'saasshorts_cache';
const CACHE_VERSION = 2;
const CACHE_MAX_AGE = 24 * 60 * 60 * 1000; // 24 hours

function voiceLanguageScore(voice, language) {
  const labels = voice.labels || {};
  const verifiedLanguages = (voice.verified_languages || [])
    .map((item) => [item.language, item.locale, item.accent, item.model_id].filter(Boolean).join(' '))
    .join(' ');
  const haystack = [
    voice.name,
    voice.category,
    voice.description,
    verifiedLanguages,
    labels.accent,
    labels.language,
    labels.description,
    labels.use_case,
  ].filter(Boolean).join(' ').toLowerCase();

  if (language === 'ru') {
    if (haystack.includes('russian') || haystack.includes('russia') || haystack.includes('ru ') || haystack.endsWith('ru') || haystack.includes('рус')) return 0;
    if (haystack.includes('slavic') || haystack.includes('eastern european')) return 1;
    return 3;
  }

  if (language === 'es') {
    if (haystack.includes('spanish') || haystack.includes('latin')) return 0;
    return 2;
  }

  if (haystack.includes('american') || haystack.includes('british') || haystack.includes('english')) return 0;
  return 1;
}

function sortVoicesForLanguage(voices, language) {
  return [...voices].sort((a, b) => voiceLanguageScore(a, language) - voiceLanguageScore(b, language));
}

function voiceMatchesGenderOrUnknown(voice, actorGender) {
  const gender = (voice.labels?.gender || '').toLowerCase();
  return !gender || gender === actorGender;
}

function voiceVisibleForLanguage(voice, language, actorGender) {
  const score = voiceLanguageScore(voice, language);
  if (language === 'ru') {
    return score <= 1 || voiceMatchesGenderOrUnknown(voice, actorGender);
  }
  return voiceMatchesGenderOrUnknown(voice, actorGender);
}

function voiceLanguageSummary(voice) {
  const verified = voice.verified_languages || [];
  if (verified.length > 0) {
    return verified.map((item) => item.language || item.locale).filter(Boolean).join(', ');
  }
  return voice.labels?.language || '';
}

function voiceFitLabel(voice, language) {
  const score = voiceLanguageScore(voice, language);
  if (language === 'ru') {
    if (score === 0) return 'Russian fit';
    if (score === 1) return 'Close accent';
    return 'Not Russian';
  }
  if (language === 'es') {
    return score === 0 ? 'Spanish fit' : 'Other accent';
  }
  return score === 0 ? 'English fit' : 'Other accent';
}

function OptionPicker({ value, onChange, options, disabled = false, placeholder = 'Select...', className = '', renderValue, renderOption }) {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value);

  return (
    <div
      className={`relative ${className}`}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className="input-field w-full min-h-[44px] py-2 pr-10 text-left flex items-center justify-between gap-3 disabled:opacity-50"
      >
        <span className="min-w-0 truncate">
          {selected ? (renderValue ? renderValue(selected) : selected.label) : placeholder}
        </span>
        <ChevronDown size={16} className={`shrink-0 text-zinc-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && !disabled && (
        <div className="absolute z-50 mt-2 w-full max-h-72 overflow-y-auto rounded-xl border border-white/10 bg-zinc-950 shadow-2xl custom-scrollbar">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={`w-full px-3 py-2.5 text-left transition-colors ${
                option.value === value
                  ? 'bg-violet-500/20 text-violet-200'
                  : 'text-zinc-300 hover:bg-white/10'
              }`}
            >
              {renderOption ? renderOption(option) : (
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-sm">{option.label}</span>
                  {option.value === value && <Check size={14} className="text-violet-300 shrink-0" />}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function estimateSpeechSeconds(text) {
  const words = (text || '').trim().split(/\s+/).filter(Boolean).length;
  return Math.max(12, Math.min(75, Math.round(words / 2.5)));
}

function isStoryboardScript(script) {
  return script?.format === 'storyboard_v3' || Array.isArray(script?.shots);
}

function activeVideoModeOptions(scriptFormat) {
  if (scriptFormat === 'storyboard_v3') {
    return VIDEO_MODE_OPTIONS.filter((option) => option.id.startsWith('storyboard_'));
  }
  return VIDEO_MODE_OPTIONS.filter((option) => !option.id.startsWith('storyboard_'));
}

function estimateStoryboardSeconds(script, fallbackText) {
  // The rendered length is driven by the voiceover (assembled from each shot's
  // speech), NOT by the shots' start/end — the backend tiles shots across the
  // voiceover and ignores their durations. So estimate from spoken words, the
  // same way the pipeline does; otherwise trimming shot lengths would falsely
  // lower the quote while the real cost (set by the narration) stays put.
  if (Array.isArray(script?.shots) && script.shots.length > 0) {
    const speech = script.shots.map((shot) => shot.speech || '').join(' ').trim();
    if (speech) return estimateSpeechSeconds(speech);
  }
  return estimateSpeechSeconds(fallbackText);
}

// Тарифы за секунду — зеркало бэкенда (KLING_AVATAR_TIERS / storyboard_video_cost_per_second).
const AVATAR_RATE = { standard: 0.0562, pro: 0.115 };
const STORYBOARD_RATE = { storyboard_v3_standard: 0.084, storyboard_v3_pro: 0.112, storyboard_veo31_quality: 0.20 };
const FLUX_FRAME_COST = 0.05; // Flux-кадр под каждый b-roll (image-first)
const TYPICAL_VIDEO_SECONDS = 35; // до генерации сценария длительность неизвестна

// Textarea that grows to fit its content instead of clipping to a fixed number
// of rows and showing the ugly native scrollbar. `minRows` sets the resting
// height; it never scrolls — it just gets taller as you type.
function AutoTextarea({ value, minRows = 3, className = '', ...props }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      value={value}
      rows={minRows}
      className={`resize-none overflow-hidden ${className}`}
      {...props}
    />
  );
}

function pluralShots(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'кадр';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'кадра';
  return 'кадров';
}

// Duration of a single shot in whole seconds (min 1). We keep the storyboard on
// a "each shot has a length" model; absolute start/end are derived from it.
function shotDurationSeconds(shot) {
  const raw = Number(shot?.end ?? 0) - Number(shot?.start ?? 0);
  if (Number.isFinite(raw) && raw >= 1) return Math.round(raw);
  const explicit = Number(shot?.duration ?? 0);
  return explicit >= 1 ? Math.round(explicit) : 3;
}

// Re-flow the timeline so shots are back-to-back: each shot keeps its own
// length, but start/end are recomputed sequentially from the first shot's
// anchor. Runs after any add / remove / reorder / duplicate / length edit so
// the timing never ends up with gaps or overlaps.
function resequenceShotTimeline(shots) {
  let cursor = shots.length ? Number(shots[0].start ?? 0) || 0 : 0;
  return shots.map((shot) => {
    const dur = shotDurationSeconds(shot);
    const start = cursor;
    const end = start + dur;
    cursor = end;
    return { ...shot, start, end };
  });
}

// Total storyboard length in whole seconds.
function splitStoryboardSeconds(script, totalSeconds) {
  // Говорящие кадры и b-roll тарифицируются разными моделями. Бэкенд нарезает
  // время по словам речи (а не по длительностям кадров) и пропускает кадры без
  // речи — поэтому долю b-roll считаем по словам, и только у кадров с речью.
  if (Array.isArray(script?.shots) && script.shots.length > 0) {
    const wordsOf = (shot) => (shot.speech || '').trim().split(/\s+/).filter(Boolean).length;
    const totalWords = script.shots.reduce((sum, shot) => sum + wordsOf(shot), 0);
    let brollWords = 0;
    let brollShots = 0;
    let talkingShots = 0;
    for (const shot of script.shots) {
      const words = wordsOf(shot);
      if (words <= 0) continue; // кадры без речи не генерируются
      if ((shot.visual_type || '').toLowerCase() === 'broll') {
        brollWords += words;
        brollShots += 1;
      } else {
        talkingShots += 1;
      }
    }
    const broll = totalWords > 0 ? (brollWords / totalWords) * totalSeconds : 0;
    return { talking: Math.max(0, totalSeconds - broll), broll, brollShots, talkingShots };
  }
  // Сценария ещё нет: типичная раскадровка ~70% речи в кадре и 2 b-roll вставки.
  return { talking: totalSeconds * 0.7, broll: totalSeconds * 0.3, brollShots: 2, talkingShots: 3 };
}

function estimateSaasVideoCost({ text, videoMode, ttsProvider, brollMode, hasSelectedActor, hasReusableHead = false, lipsyncModel = 'sync-3', script = null, storyboardGenerationMode = 'sliced_avatar' }) {
  // Длительность: реальные кадры сценария > оценка по тексту озвучки > типичный ролик.
  // Описание бизнеса — не текст озвучки, по нему длительность не считаем.
  const hasNarration = Boolean((text || '').trim());
  const seconds = hasNarration ? estimateSpeechSeconds(text) : TYPICAL_VIDEO_SECONDS;
  const storyboardSeconds = Array.isArray(script?.shots) && script.shots.length > 0
    ? estimateStoryboardSeconds(script, text)
    : seconds;
  const ttsRate = ttsProvider === 'fal_minimax' ? 0.0001 : 0.00003;
  const voiceCost = hasNarration ? (text || '').length * ttsRate : storyboardSeconds * 13 * 0.00003;
  const storyboardMode = videoMode.startsWith('storyboard_');
  const actorCost = (hasSelectedActor || hasReusableHead || storyboardMode) ? 0 : 0.05;
  let videoCost = 0;
  let brollCost = 0;

  if (hasReusableHead) {
    const option = LIPSYNC_MODEL_OPTIONS.find((item) => item.id === lipsyncModel) || LIPSYNC_MODEL_OPTIONS[0];
    videoCost = (seconds / 60) * option.pricePerMinute;
  } else if (storyboardMode && storyboardGenerationMode === 'sliced_avatar') {
    // Говорящие кадры — Kling Avatar, b-roll — Kling V3 + Flux-кадр (как на бэкенде).
    const avatarTier = videoMode === 'storyboard_v3_standard' ? 'standard' : 'pro';
    const brollRate = STORYBOARD_RATE[videoMode] && videoMode !== 'storyboard_veo31_quality'
      ? STORYBOARD_RATE[videoMode]
      : STORYBOARD_RATE.storyboard_v3_standard;
    const { talking, broll, brollShots, talkingShots } = splitStoryboardSeconds(script, storyboardSeconds);
    // Каждый говорящий кадр стартует со свежего Flux-кадра (аватар + сцена),
    // как b-roll — иначе Kling клонирует человека по краям из одного фото.
    videoCost = talking * AVATAR_RATE[avatarTier] + talkingShots * FLUX_FRAME_COST;
    brollCost = broll * brollRate + brollShots * FLUX_FRAME_COST;
  } else if (storyboardMode) {
    videoCost = storyboardSeconds * (STORYBOARD_RATE[videoMode] || STORYBOARD_RATE.storyboard_v3_standard);
  } else if (videoMode === 'lowcost') {
    videoCost = 0.19 + 0.20;
  } else if (videoMode === 'premium') {
    videoCost = seconds * 0.115;
  } else {
    videoCost = seconds * 0.0562;
  }

  if (!storyboardMode) {
    brollCost = brollMode === 'ai' ? 0.10 : 0;
  }
  const total = actorCost + voiceCost + videoCost + brollCost;
  return {
    seconds: storyboardMode ? storyboardSeconds : seconds,
    actorCost,
    voiceCost,
    videoCost,
    brollCost,
    total,
  };
}

function formatUsd(value) {
  return `$${Math.max(value, 0).toFixed(2)}`;
}

function loadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const cache = JSON.parse(raw);
    if (cache.version !== CACHE_VERSION) {
      localStorage.removeItem(CACHE_KEY);
      return null;
    }
    if (Date.now() - cache.timestamp > CACHE_MAX_AGE) {
      localStorage.removeItem(CACHE_KEY);
      return null;
    }
    return cache;
  } catch { return null; }
}

// Последний запущенный job генерации: страница может перезагрузиться посреди
// (или сразу после) генерации, а job живёт на сервере — по сохранённому id
// мастер снова подцепляется к статусу и результату.
const LAST_JOB_KEY = 'saasshorts_last_job';

function loadLastJob() {
  try {
    return JSON.parse(localStorage.getItem(LAST_JOB_KEY) || 'null');
  } catch {
    return null;
  }
}

function saveLastJob(jobId) {
  try {
    localStorage.setItem(LAST_JOB_KEY, JSON.stringify({ jobId, savedAt: Date.now() }));
  } catch { /* localStorage full */ }
}

function clearLastJob() {
  try {
    localStorage.removeItem(LAST_JOB_KEY);
  } catch { /* ignore */ }
}

// Выбор голоса, провайдера озвучки и актёра должен переживать перезагрузку:
// иначе повторный запуск после reload уходит с дефолтами (английская Rachel
// вместо выбранного голоса, сгенерированный Flux-актёр вместо загруженного фото).
const VIDEO_PREFS_KEY = 'saasshorts_video_prefs';

function loadVideoPrefs() {
  try {
    return JSON.parse(localStorage.getItem(VIDEO_PREFS_KEY) || 'null') || {};
  } catch {
    return {};
  }
}

function saveVideoPrefs(prefs) {
  try {
    localStorage.setItem(VIDEO_PREFS_KEY, JSON.stringify(prefs));
  } catch { /* localStorage full */ }
}

function saveCache(input, analysis, webResearch, scripts) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      version: CACHE_VERSION,
      ...input,
      analysis,
      webResearch,
      scripts,
      timestamp: Date.now(),
    }));
  } catch { /* localStorage full */ }
}

export default function SaaShortsTab({
  geminiApiKey,
  elevenLabsKey,
  falKey,
  uploadPostKey,
  uploadUserId,
  authToken,
  usePlatformKeys = false,
  onManageProjects,
}) {
  // Wizard state
  const [step, setStep] = useState(() => {
    const cache = loadCache();
    return cache ? 1 : 0;
  });

  // Step 0: Business brief
  const [url] = useState('');
  const [videoMode, setVideoMode] = useState('standard'); // "lowcost", "standard", or "premium"
  const [description, setDescription] = useState(() => loadCache()?.description || '');
  const [topic, setTopic] = useState(() => loadCache()?.topic || '');
  const [businessName, setBusinessName] = useState(() => loadCache()?.businessName || '');
  const [businessProfiles, setBusinessProfiles] = useState(() => loadBusinessProfiles());
  const [selectedBusinessProfileId, setSelectedBusinessProfileId] = useState(() => loadSelectedProfileId() || loadCache()?.businessProfileId || '');
  const [scriptMode, setScriptMode] = useState(() => loadCache()?.scriptMode || 'ai'); // "ai" or "custom"
  const [scriptFormat, setScriptFormat] = useState(() => loadCache()?.scriptFormat || 'ugc');
  const [textModel, setTextModel] = useState(() => loadCache()?.textModel || 'fast');
  const [customScript, setCustomScript] = useState(() => loadCache()?.customScript || '');
  const [style, setStyle] = useState('ugc');
  const [language, setLanguage] = useState('ru');
  const [actorGender, setActorGender] = useState('female');
  const [numScripts, setNumScripts] = useState(3);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState('');
  const [fromCache, setFromCache] = useState(() => !!loadCache());

  // Step 1: Analysis results
  const [analysis, setAnalysis] = useState(() => loadCache()?.analysis || null);
  const [webResearch, setWebResearch] = useState(() => loadCache()?.webResearch || null);
  const [scripts, setScripts] = useState(() => loadCache()?.scripts || []);
  const [selectedScript, setSelectedScript] = useState(0);
  // Undo stack for storyboard shot edits: snapshots of shots before each
  // add / delete / reorder, tagged with the script they belong to.
  const [shotHistory, setShotHistory] = useState([]);
  // Drag-and-drop reordering of storyboard shots.
  const [dragShotIndex, setDragShotIndex] = useState(null);
  const [dragOverShotIndex, setDragOverShotIndex] = useState(null);
  // Which shots have the (optional, technical) "prompt for the AI" field open.
  const [openPromptShots, setOpenPromptShots] = useState({});
  const [openAdvancedShots, setOpenAdvancedShots] = useState({});

  // Step 2: Configure
  const [voices, setVoices] = useState([]);
  const [ttsProvider, setTtsProvider] = useState(() => loadVideoPrefs().ttsProvider || 'auto');
  const [brollMode, setBrollMode] = useState('mockup');
  const [storyboardGenerationMode, setStoryboardGenerationMode] = useState('sliced_avatar');
  // Тонкие настройки пайплайна: по умолчанию всё включено, «!== false» —
  // чтобы старые prefs без этих полей не выключали фичи.
  const [backgroundMusic, setBackgroundMusic] = useState(() => loadVideoPrefs().backgroundMusic !== false);
  const [clipVisionQc, setClipVisionQc] = useState(() => loadVideoPrefs().clipVisionQc !== false);
  const [brollImageFirst, setBrollImageFirst] = useState(() => loadVideoPrefs().brollImageFirst !== false);
  const [selectedVoice, setSelectedVoice] = useState(() => loadVideoPrefs().selectedVoice || 'D5RRIJYa9pFwxiSpbGbR');
  const [minimaxVoice, setMinimaxVoice] = useState('Russian_AmbitiousWoman');
  const [actorDescription, setActorDescription] = useState('');
  const [editedNarration, setEditedNarration] = useState('');
  const [actorOptions, setActorOptions] = useState([]);
  const [selectedActor, setSelectedActor] = useState(() => loadVideoPrefs().selectedActor || null);
  // Пол/озвучка/загрузка аватара спрятаны в модалку, чтобы блок выбора
  // аватара не был перегружен (видна только сетка аватаров + «Настройки»).
  const [avatarSettingsOpen, setAvatarSettingsOpen] = useState(false);
  const [generatingActors, setGeneratingActors] = useState(false);
  const [actorGallery, setActorGallery] = useState([]);
  const [loadingGallery, setLoadingGallery] = useState(false);
  const [headTemplates, setHeadTemplates] = useState([]);
  const [loadingHeadTemplates, setLoadingHeadTemplates] = useState(false);
  const [selectedHeadTemplate, setSelectedHeadTemplate] = useState('');
  const [savingHeadTemplate, setSavingHeadTemplate] = useState(false);
  const [headTemplateStatus, setHeadTemplateStatus] = useState('');

  const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});
  const isManagedKey = (value) => value === '__saved__' || value === '__platform__';
  const [uploadedActorPreview, setUploadedActorPreview] = useState(() => {
    // {localPreview, serverUrl}; после перезагрузки превью строим от серверного URL
    const url = loadVideoPrefs().uploadedActorUrl;
    return url ? { localPreview: getApiUrl(url), serverUrl: url } : null;
  });
  const [actorUploadStatus, setActorUploadStatus] = useState('');
  const [productPhoto, setProductPhoto] = useState(null); // {preview, serverUrl}
  const [productDescription, setProductDescription] = useState('');

  // Step 3: Generate
  const [generating, setGenerating] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [genLogs, setGenLogs] = useState([]);
  const [genStatus, setGenStatus] = useState('idle');
  const [genResult, setGenResult] = useState(null);
  const [lipSyncModel, setLipSyncModel] = useState('sync-3');
  const [lipSyncing, setLipSyncing] = useState(false);
  // Frames-only preview: generate/regenerate the start frames of each shot on
  // step 2 (перед платной генерацией видео), staying on the storyboard editor.
  const [framesGenerating, setFramesGenerating] = useState(false);
  const [framesShot, setFramesShot] = useState(null); // shot_number currently regenerating, or null for «все»

  // Publish
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState(null);
  const [publishPlatforms, setPublishPlatforms] = useState({ tiktok: true, instagram: true, youtube: true });
  const [isScheduling, setIsScheduling] = useState(false);
  const [scheduleDate, setScheduleDate] = useState('');

  // UI
  const [copied, setCopied] = useState('');
  const [logsExpanded, setLogsExpanded] = useState(true);

  // Pre-fill from cache on mount
  useEffect(() => {
    if (fromCache && scripts.length > 0) {
      setEditedNarration(scripts[0].full_narration || '');
    }
  }, []);

  // Активный проект со страницы «Проекты» + тема, выбранная в контент-плане.
  // Тема читается lazy-инициализатором и очищается отдельно: StrictMode гоняет
  // mount-эффект дважды, и повторный прогон не должен терять уже снятую тему.
  const [pendingTopicOnMount] = useState(() => peekPendingTopic());
  useEffect(() => {
    const storedId = loadSelectedProfileId();
    if (storedId) {
      const profile = loadBusinessProfiles().find((item) => businessProfileKey(item) === storedId);
      // Кеш держит правки пользователя для того же проекта; при смене
      // активного проекта на странице «Проекты» кеш надо перезаписать.
      const cachedId = loadCache()?.businessProfileId || '';
      if (profile && (!description.trim() || storedId !== cachedId)) {
        handleLoadBusinessProfile(profile);
      }
    }
    if (pendingTopicOnMount) {
      setTopic(pendingTopicOnMount);
      setStep(0);
      setFromCache(false);
      clearPendingTopic();
    }
  }, []);

  // Восстановление генерации после перезагрузки страницы: по сохранённому
  // job_id снова подцепляемся к статусу/результату. Если пользователь пришёл
  // из контент-плана делать новый ролик — старый job не восстанавливаем.
  // After a render the backend returns each shot's generated frame/clip URLs (and
  // the rebuilt prompt baseline). Merge them into the matching script by title so
  // the storyboard editor shows the actual generated frames and future «Что в кадре»
  // edits diff against the new baseline.
  const applyGeneratedShots = (result) => {
    const genShots = result?.shots;
    const title = result?.script?.title;
    if (!Array.isArray(genShots) || !genShots.length || !title) return;
    const byNumber = new Map(genShots.map((s, i) => [s.shot_number ?? (i + 1), s]));
    setScripts((prev) => prev.map((script) => {
      if (script.title !== title || !Array.isArray(script.shots) || !script.shots.length) return script;
      const shots = script.shots.map((shot, i) => {
        const g = byNumber.get(shot.shot_number ?? (i + 1));
        if (!g) return shot;
        return {
          ...shot,
          preview_frame_url: g.preview_frame_url || shot.preview_frame_url,
          clip_url: g.clip_url || shot.clip_url,
          // Frames-only render also attaches the start frame the video will reuse.
          image_url: g.image_url || shot.image_url,
          local_url: g.local_url || shot.local_url,
          image_path: g.image_path || shot.image_path,
          image_preview: g.local_url ? getApiUrl(g.local_url) : shot.image_preview,
          generation_prompt: g.generation_prompt || shot.generation_prompt,
          _prompt_source_scene: g._prompt_source_scene ?? shot._prompt_source_scene,
        };
      });
      return { ...script, shots };
    }));
  };

  useEffect(() => {
    if (pendingTopicOnMount) return;
    const last = loadLastJob();
    if (!last?.jobId) return;
    (async () => {
      try {
        const res = await fetch(getApiUrl(`/api/saasshorts/status/${last.jobId}`), { headers: authHeaders() });
        if (!res.ok) {
          // Job вычищен на сервере (рестарт или >1ч) — готовое видео остаётся в галерее UGC
          if (res.status === 404) clearLastJob();
          return;
        }
        const data = await res.json();
        setJobId(last.jobId);
        if (data.logs) setGenLogs(data.logs);
        if (data.status === 'completed') {
          setGenStatus('completed');
          setGenResult(data.result);
          applyGeneratedShots(data.result);
          setStep(4);
        } else if (data.status === 'failed') {
          setGenStatus('failed');
          setStep(3);
        } else {
          setGenStatus('processing');
          setGenerating(true);
          setStep(3);
        }
      } catch { /* backend недоступен — оставляем мастер как есть */ }
    })();
  }, []);

  // Fetch actor gallery on mount
  useEffect(() => {
    setLoadingGallery(true);
    fetch(getApiUrl('/api/saasshorts/actor-gallery'), { headers: authHeaders() })
      .then(res => res.ok ? res.json() : { images: [] })
      .then(data => setActorGallery(data.images || []))
      .catch(() => {})
      .finally(() => setLoadingGallery(false));
  }, []);

  useEffect(() => {
    refreshHeadTemplates();
  }, []);

  useEffect(() => {
    if (!authToken) return;
    fetch(getApiUrl('/api/user/business-profiles'), { headers: authHeaders() })
      .then((res) => res.ok ? res.json() : { profiles: [] })
      .then((data) => {
        if (Array.isArray(data.profiles) && data.profiles.length > 0) {
          setBusinessProfiles(data.profiles);
          saveBusinessProfiles(data.profiles);
        }
      })
      .catch(() => {});
  }, [authToken]);

  // Fetch voices on mount
  useEffect(() => {
    if (elevenLabsKey) {
      fetchVoices();
    }
  }, [elevenLabsKey]);

  // Reset selected voice when actor gender or language changes.
  // Восстановленный из prefs голос не затираем, пока комбинация язык+пол
  // та же, при которой пользователь его выбирал.
  const voiceAutoKeyRef = useRef(loadVideoPrefs().voiceKey || '');
  useEffect(() => {
    const comboKey = `${language}-${actorGender}`;
    if (voiceAutoKeyRef.current === comboKey) return;
    voiceAutoKeyRef.current = comboKey;
    const genderDefaults = {
      'en-female': '21m00Tcm4TlvDq8ikWAM',  // Rachel
      'en-male': '29vD33N1CtxCmqQRPOHJ',    // Drew
      'es-female': 'EXAVITQu4vr4xnSDxMaL',  // Bella
      'es-male': 'ErXwobaYiN019PkySvjV',     // Antoni
      'ru-female': 'D5RRIJYa9pFwxiSpbGbR',  // Victoria — родной русский, утверждённый дефолт
      'ru-male': '29vD33N1CtxCmqQRPOHJ',    // Multilingual fallback
    };
    // Prefer a voice that matches both gender and selected language/accent.
    const matchingVoice = sortVoicesForLanguage(
      voices.filter(v => voiceVisibleForLanguage(v, language, actorGender)),
      language
    )[0];
    if (matchingVoice) {
      setSelectedVoice(matchingVoice.voice_id);
    } else {
      setSelectedVoice(genderDefaults[`${language}-${actorGender}`] || genderDefaults['en-female']);
    }
  }, [actorGender, language]);

  // Персистим выбор озвучки и актёра (см. loadVideoPrefs)
  useEffect(() => {
    saveVideoPrefs({
      selectedVoice,
      voiceKey: `${language}-${actorGender}`,
      ttsProvider,
      selectedActor: selectedActor || '',
      uploadedActorUrl: uploadedActorPreview?.serverUrl || '',
      backgroundMusic,
      clipVisionQc,
      brollImageFirst,
    });
  }, [selectedVoice, ttsProvider, selectedActor, uploadedActorPreview, language, actorGender, backgroundMusic, clipVisionQc, brollImageFirst]);

  useEffect(() => {
    setMinimaxVoice(defaultMiniMaxVoice(language, actorGender));
  }, [actorGender, language]);

  useEffect(() => {
    const allowed = activeVideoModeOptions(scriptFormat).map((option) => option.id);
    if (!allowed.includes(videoMode)) {
      setVideoMode(scriptFormat === 'storyboard_v3' ? 'storyboard_v3_standard' : 'standard');
    }
  }, [scriptFormat, videoMode]);

  // Poll generation status
  useEffect(() => {
    let interval;
    if (jobId && genStatus === 'processing') {
      interval = setInterval(async () => {
        try {
          const res = await fetch(getApiUrl(`/api/saasshorts/status/${jobId}`), { headers: authHeaders() });
          if (res.status === 404) {
            // Job lost (server restart) — treat as failed so Retry appears
            setGenStatus('failed');
            setGenerating(false);
            setLipSyncing(false);
            setGenLogs((prev) => [...prev, 'Job lost after server restart. Click Retry to resume from cached assets.']);
            clearInterval(interval);
            return;
          }
          if (!res.ok) return;
          const data = await res.json();
          if (data.logs) setGenLogs(data.logs);
          if (data.status === 'completed') {
            setGenStatus('completed');
            setGenResult(data.result);
            applyGeneratedShots(data.result);
            setGenerating(false);
            setLipSyncing(false);
            setStep(4);
            clearInterval(interval);
          } else if (data.status === 'failed') {
            setGenStatus('failed');
            setGenerating(false);
            setLipSyncing(false);
            clearInterval(interval);
          }
        } catch (e) {
          console.error('Poll error:', e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId, genStatus]);

  const fetchVoices = async () => {
    try {
      const headers = { ...authHeaders() };
      if (elevenLabsKey && !isManagedKey(elevenLabsKey)) headers['X-ElevenLabs-Key'] = elevenLabsKey;
      const res = await fetch(getApiUrl(`/api/saasshorts/voices${usePlatformKeys ? '?use_platform_keys=true' : ''}`), { headers });
      if (res.ok) {
        const data = await res.json();
        setVoices(data.voices || []);
      }
    } catch (e) {
      console.error('Voices fetch error:', e);
    }
  };

  const handleLoadBusinessProfile = (profile) => {
    if (!profile) return;
    const id = businessProfileKey(profile);
    setSelectedBusinessProfileId(id);
    saveSelectedProfileId(id);
    setBusinessName(profile.name || '');
    setDescription(profile.description || '');
    setTopic(profile.topic || '');
    if (profile.scriptMode || profile.script_mode) setScriptMode(profile.scriptMode || profile.script_mode);
    if (profile.scriptFormat || profile.script_format) setScriptFormat(profile.scriptFormat || profile.script_format);
    if (profile.textModel || profile.text_model) setTextModel(profile.textModel || profile.text_model);
    if (profile.style) setStyle(profile.style);
    if (profile.language) setLanguage(profile.language);
    if (profile.actorGender || profile.actor_gender) setActorGender(profile.actorGender || profile.actor_gender);
  };

  const handleAnalyze = async () => {
    const isCustom = scriptMode === 'custom';
    if (isCustom && !customScript.trim()) return;
    if (!isCustom && !description.trim()) return;
    if (!isCustom && !geminiApiKey) {
      setAnalyzeError('Gemini API key required. Set it in Settings.');
      return;
    }

    setAnalyzing(true);
    setAnalyzeError('');

    try {
      const res = await fetch(getApiUrl('/api/saasshorts/analyze'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
          ...(geminiApiKey && !isManagedKey(geminiApiKey) ? { 'X-Gemini-Key': geminiApiKey } : {}),
        },
        body: JSON.stringify({
          url: undefined,
          description: description.trim() || undefined,
          topic: topic.trim() || undefined,
          script_mode: scriptMode,
          script_format: scriptFormat,
          text_model: textModel,
          custom_script: isCustom ? customScript.trim() : undefined,
          num_scripts: numScripts,
          style,
          language,
          actor_gender: actorGender,
          use_platform_keys: usePlatformKeys,
        }),
      });

      if (!res.ok) {
        let msg = 'Analysis failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      setAnalysis(data.analysis);
      setWebResearch(data.web_research || null);
      setScripts(data.scripts);
      setShotHistory([]);
      setSelectedScript(0);
      setFromCache(false);

      // Cache results
      saveCache({
        url: '',
        businessProfileId: selectedBusinessProfileId,
        businessName: businessName.trim(),
        description: description.trim(),
        topic: topic.trim(),
        scriptMode,
        scriptFormat,
        textModel,
        customScript: isCustom ? customScript.trim() : '',
      }, data.analysis, data.web_research, data.scripts);

      // Pre-fill actor description and narration from first script
      if (data.scripts.length > 0) {
        setActorDescription('');
        setEditedNarration(data.scripts[0].full_narration || '');
      }

      setStep(1);
    } catch (e) {
      setAnalyzeError(e.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleSelectScript = (idx) => {
    setSelectedScript(idx);
    if (scripts[idx]) {
      setActorDescription('');
      setActorOptions([]);
      setEditedNarration(scripts[idx].full_narration || '');
    }
  };

  const persistScripts = (nextScripts) => {
    saveCache({
      url: '',
      businessProfileId: selectedBusinessProfileId,
      businessName: businessName.trim(),
      description: description.trim(),
      topic: topic.trim(),
      scriptMode,
      scriptFormat,
      textModel,
      customScript: scriptMode === 'custom' ? customScript.trim() : '',
    }, analysis, webResearch, nextScripts);
  };

  const updateSelectedScriptShot = (shotIndex, patch) => {
    const nextScripts = scripts.map((script, idx) => {
      if (idx !== selectedScript) return script;
      return {
        ...script,
        format: 'storyboard_v3',
        shots: (script.shots || []).map((shot, j) => (
          j === shotIndex ? { ...shot, ...patch } : shot
        )),
      };
    });
    setScripts(nextScripts);
    persistScripts(nextScripts);
  };

  const handleSelectedScriptShot = (shotIndex, field, value) => {
    updateSelectedScriptShot(shotIndex, {
      [field]: field === 'start' || field === 'end' ? Number(value) : value,
    });
  };

  // Keep shot_number in sync with position after add / delete / reorder.
  const renumberShots = (shots) => shots.map((shot, idx) => ({ ...shot, shot_number: idx + 1 }));

  const makeBlankShot = (shots) => {
    const last = shots[shots.length - 1];
    const start = last ? Number(last.end ?? last.start ?? 0) : 0;
    return {
      shot_number: shots.length + 1,
      start,
      end: start + 3,
      role: '',
      scene: '',
      actor_action: '',
      action: '',
      camera: '',
      speech: '',
      overlay_text: '',
      transition: 'cut',
      generation_prompt: '',
      visual_type: 'avatar',
    };
  };

  // Rewrite the selected script's shots (add / remove / reorder), renumber and
  // persist. Snapshots the pre-change shots onto the undo stack first.
  const mutateSelectedScriptShots = (mutator) => {
    const prevShots = (scripts[selectedScript]?.shots || []).map((shot) => ({ ...shot }));
    const nextScripts = scripts.map((script, idx) => {
      if (idx !== selectedScript) return script;
      const shots = resequenceShotTimeline(renumberShots(mutator([...(script.shots || [])])));
      return { ...script, format: 'storyboard_v3', shots };
    });
    setShotHistory((history) => [
      ...history.slice(-49),
      { scriptIndex: selectedScript, shots: prevShots },
    ]);
    setScripts(nextScripts);
    persistScripts(nextScripts);
  };

  const undoShotChange = () => {
    let restoreIdx = -1;
    for (let i = shotHistory.length - 1; i >= 0; i -= 1) {
      if (shotHistory[i].scriptIndex === selectedScript) { restoreIdx = i; break; }
    }
    if (restoreIdx === -1) return;
    const entry = shotHistory[restoreIdx];
    const nextScripts = scripts.map((script, idx) => (
      idx === entry.scriptIndex
        ? { ...script, format: 'storyboard_v3', shots: entry.shots }
        : script
    ));
    setScripts(nextScripts);
    persistScripts(nextScripts);
    setShotHistory((history) => history.filter((_, i) => i !== restoreIdx));
  };

  const addSelectedScriptShot = (afterIndex = null) => {
    mutateSelectedScriptShots((shots) => {
      const blank = makeBlankShot(shots);
      const at = afterIndex == null ? shots.length : afterIndex + 1;
      shots.splice(at, 0, blank);
      return shots;
    });
  };

  const removeSelectedScriptShot = (shotIndex) => {
    mutateSelectedScriptShots((shots) => {
      if (shots.length <= 1) return shots; // keep at least one shot
      shots.splice(shotIndex, 1);
      return shots;
    });
  };

  const moveSelectedScriptShot = (shotIndex, direction) => {
    mutateSelectedScriptShots((shots) => {
      const target = shotIndex + direction;
      if (target < 0 || target >= shots.length) return shots;
      [shots[shotIndex], shots[target]] = [shots[target], shots[shotIndex]];
      return shots;
    });
  };

  const duplicateSelectedScriptShot = (shotIndex) => {
    mutateSelectedScriptShots((shots) => {
      const original = shots[shotIndex];
      if (!original) return shots;
      // Deep-ish copy; the generated-frame status is per-run, so drop it.
      const { frame_status, ...rest } = original;
      shots.splice(shotIndex + 1, 0, { ...rest });
      return shots;
    });
  };

  // Drag-and-drop reorder: move the dragged shot to the drop target's slot.
  const dropShotOnto = (toIndex) => {
    const from = dragShotIndex;
    setDragShotIndex(null);
    setDragOverShotIndex(null);
    if (from == null || from === toIndex) return;
    mutateSelectedScriptShots((shots) => {
      const [moved] = shots.splice(from, 1);
      shots.splice(toIndex, 0, moved);
      return shots;
    });
  };

  const handleStoryboardFrameUpload = async (shotIndex, file) => {
    if (!file || !scripts[selectedScript]) return;
    const localPreview = URL.createObjectURL(file);
    updateSelectedScriptShot(shotIndex, {
      image_preview: localPreview,
      frame_status: 'Загружаю кадр...',
    });

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('shot_number', String((scripts[selectedScript].shots?.[shotIndex]?.shot_number || shotIndex + 1)));

      const res = await fetch(getApiUrl('/api/saasshorts/storyboard-frame-upload'), {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) {
        let msg = 'Не удалось загрузить кадр';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      updateSelectedScriptShot(shotIndex, {
        image_url: data.image_url || data.url || data.local_url,
        local_url: data.local_url || data.url,
        image_path: data.image_path,
        image_key: data.key,
        image_preview: data.local_url ? getApiUrl(data.local_url) : localPreview,
        frame_status: 'Кадр сохранён',
      });
    } catch (err) {
      updateSelectedScriptShot(shotIndex, {
        image_preview: localPreview,
        frame_status: err.message || 'Ошибка загрузки кадра',
      });
    }
  };

  // Сгенерировать начальные кадры шотов (Flux) БЕЗ платной генерации видео.
  // shotNumber задан → перегенерировать один кадр, иначе все. По готовности
  // мержим кадры в редактор (applyGeneratedShots) и остаёмся на шаге 2.
  const handleGenerateFrames = async (shotNumber = null) => {
    if (!falKey) {
      alert('fal.ai API key required. Set it in Settings.');
      return;
    }
    if (framesGenerating) return;

    setFramesGenerating(true);
    setFramesShot(shotNumber);

    try {
      const scriptToSend = { ...scripts[selectedScript] };
      scriptToSend._product_name = analysis?.product_name || analysis?.name || '';
      scriptToSend._business_name = businessName.trim();
      scriptToSend._business_description = description.trim();
      scriptToSend._video_topic = topic.trim();
      scriptToSend._product_url = '';

      const headers = {
        'Content-Type': 'application/json',
        ...authHeaders(),
      };
      if (falKey && !isManagedKey(falKey)) headers['X-Fal-Key'] = falKey;

      const res = await fetch(getApiUrl('/api/saasshorts/generate'), {
        method: 'POST',
        headers,
        body: JSON.stringify({
          script: scriptToSend,
          voice_id: selectedVoice,
          tts_provider: ttsProvider,
          minimax_voice_id: minimaxVoice,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          video_mode: videoMode,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          use_platform_keys: usePlatformKeys,
          broll_image_first: brollImageFirst,
          frames_only: true,
          frames_only_shot: shotNumber ?? undefined,
        }),
      });

      if (!res.ok) {
        let msg = 'Frame generation failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const { job_id: framesJobId } = await res.json();

      // Собственный опрос — не трогаем основной genStatus/step, чтобы остаться
      // в редакторе раскадровки (шаг 2).
      const deadline = Date.now() + 5 * 60 * 1000;
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await new Promise((r) => setTimeout(r, 2000));
        if (Date.now() > deadline) throw new Error('Frame generation timed out');
        const poll = await fetch(getApiUrl(`/api/saasshorts/status/${framesJobId}`), { headers: authHeaders() });
        if (!poll.ok) continue;
        const data = await poll.json();
        if (data.status === 'completed') {
          applyGeneratedShots(data.result);
          break;
        }
        if (data.status === 'failed') {
          throw new Error(data.error || 'Frame generation failed');
        }
      }
    } catch (e) {
      alert(`Не удалось сгенерировать кадры: ${e.message}`);
    } finally {
      setFramesGenerating(false);
      setFramesShot(null);
    }
  };

  const handleGenerate = async () => {
    if (!falKey) {
      alert('fal.ai API key required. Set it in Settings.');
      return;
    }
    if (ttsProvider === 'elevenlabs' && !elevenLabsKey) {
      alert('ElevenLabs API key required. Set it in Settings.');
      return;
    }

    setGenerating(true);
    setGenLogs(['Starting video generation...']);
    setGenStatus('processing');
    setGenResult(null);
    setStep(3);

    try {
      // Update script with edited narration
      const scriptToSend = { ...scripts[selectedScript] };
      scriptToSend._product_name = analysis?.product_name || analysis?.name || '';
      scriptToSend._business_name = businessName.trim();
      scriptToSend._business_description = description.trim();
      scriptToSend._video_topic = topic.trim();
      scriptToSend._product_url = '';
      if (editedNarration !== scriptToSend.full_narration) {
        scriptToSend.full_narration = editedNarration;
      }

      const headers = {
        'Content-Type': 'application/json',
        ...authHeaders(),
      };
      if (falKey && !isManagedKey(falKey)) headers['X-Fal-Key'] = falKey;
      if (elevenLabsKey && !isManagedKey(elevenLabsKey)) headers['X-ElevenLabs-Key'] = elevenLabsKey;

      const res = await fetch(getApiUrl('/api/saasshorts/generate'), {
        method: 'POST',
        headers,
        body: JSON.stringify({
          script: scriptToSend,
          voice_id: selectedVoice,
          tts_provider: ttsProvider,
          minimax_voice_id: minimaxVoice,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          video_mode: videoMode,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          reusable_head_template_id: selectedHeadTemplate || undefined,
          reusable_lipsync_model: lipSyncModel,
          use_platform_keys: usePlatformKeys,
          background_music: backgroundMusic,
          clip_vision_qc: clipVisionQc,
          broll_image_first: brollImageFirst,
        }),
      });

      if (!res.ok) {
        let msg = 'Generation failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      setJobId(data.job_id);
      saveLastJob(data.job_id);
    } catch (e) {
      setGenStatus('failed');
      setGenLogs((prev) => [...prev, `Error: ${e.message}`]);
      setGenerating(false);
    }
  };

  const handleRetry = async () => {
    if (!jobId) return;
    setGenerating(true);
    setGenLogs(['Retrying from cached assets...']);
    setGenStatus('processing');
    setGenResult(null);

    try {
      const scriptToSend = { ...scripts[selectedScript] };
      scriptToSend._product_name = analysis?.product_name || analysis?.name || '';
      scriptToSend._business_name = businessName.trim();
      scriptToSend._business_description = description.trim();
      scriptToSend._video_topic = topic.trim();
      scriptToSend._product_url = '';
      if (editedNarration !== scriptToSend.full_narration) {
        scriptToSend.full_narration = editedNarration;
      }

      const headers = {
        'Content-Type': 'application/json',
        ...authHeaders(),
      };
      if (falKey && !isManagedKey(falKey)) headers['X-Fal-Key'] = falKey;
      if (elevenLabsKey && !isManagedKey(elevenLabsKey)) headers['X-ElevenLabs-Key'] = elevenLabsKey;

      const res = await fetch(getApiUrl('/api/saasshorts/generate'), {
        method: 'POST',
        headers,
        body: JSON.stringify({
          script: scriptToSend,
          voice_id: selectedVoice,
          tts_provider: ttsProvider,
          minimax_voice_id: minimaxVoice,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          retry_job_id: jobId,
          video_mode: videoMode,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          reusable_head_template_id: selectedHeadTemplate || undefined,
          reusable_lipsync_model: lipSyncModel,
          use_platform_keys: usePlatformKeys,
          background_music: backgroundMusic,
          clip_vision_qc: clipVisionQc,
          broll_image_first: brollImageFirst,
        }),
      });

      if (!res.ok) {
        let msg = 'Retry failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      setJobId(data.job_id);
      saveLastJob(data.job_id);
    } catch (e) {
      setGenStatus('failed');
      setGenLogs((prev) => [...prev, `Retry error: ${e.message}`]);
      setGenerating(false);
    }
  };

  const handleLipSync = async () => {
    if (!jobId) {
      alert('No generated video job to lip-sync.');
      return;
    }
    if (!falKey) {
      alert('fal.ai API key required. Set it in Settings.');
      return;
    }

    const selected = LIPSYNC_MODEL_OPTIONS.find((item) => item.id === lipSyncModel);
    setLipSyncing(true);
    setGenerating(true);
    setGenLogs([`Starting lip-sync post-process (${selected?.label || lipSyncModel})...`]);
    setGenStatus('processing');
    setStep(3);

    try {
      const res = await fetch(getApiUrl('/api/saasshorts/lipsync'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
          ...(falKey && !isManagedKey(falKey) ? { 'X-Fal-Key': falKey } : {}),
        },
        body: JSON.stringify({
          job_id: jobId,
          model: lipSyncModel,
          sync_mode: 'cut_off',
          use_platform_keys: usePlatformKeys,
        }),
      });

      if (!res.ok) {
        let msg = 'Lip-sync failed to start';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
    } catch (e) {
      setGenStatus('failed');
      setGenLogs((prev) => [...prev, `Lip-sync error: ${e.message}`]);
      setGenerating(false);
      setLipSyncing(false);
    }
  };

  const refreshActorGallery = async () => {
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/actor-gallery'), { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        setActorGallery(data.images || []);
      }
    } catch (e) {
      console.error('Actor gallery refresh failed:', e);
    }
  };

  const refreshHeadTemplates = async () => {
    setLoadingHeadTemplates(true);
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/head-templates'), { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        setHeadTemplates(data.templates || []);
      }
    } catch (e) {
      console.error('Head templates refresh failed:', e);
    } finally {
      setLoadingHeadTemplates(false);
    }
  };

  const handleSaveHeadTemplate = async () => {
    if (!jobId) {
      setHeadTemplateStatus('Нет job_id для сохранения talking-head.');
      return;
    }
    setSavingHeadTemplate(true);
    setHeadTemplateStatus('Сохраняю talking-head шаблон...');
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/head-templates'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          job_id: jobId,
          label: genResult?.script?.title || 'Talking head template',
        }),
      });
      if (!res.ok) {
        let msg = 'Не удалось сохранить talking-head шаблон';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
      const data = await res.json();
      await refreshHeadTemplates();
      setSelectedHeadTemplate(data.template?.template_id || '');
      setHeadTemplateStatus('Talking-head шаблон сохранен. Его можно выбрать в следующем ролике.');
    } catch (e) {
      setHeadTemplateStatus(e.message || 'Не удалось сохранить talking-head шаблон');
    } finally {
      setSavingHeadTemplate(false);
    }
  };

  const handleActorUpload = async (file) => {
    if (!file) return;
    const localPreview = URL.createObjectURL(file);
    setActorUploadStatus('Uploading and saving...');
    setUploadedActorPreview({ localPreview, serverUrl: null });
    setSelectedActor(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(getApiUrl('/api/saasshorts/actor-upload'), {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) {
        let msg = 'Upload failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      if (data.url) {
        setUploadedActorPreview({ localPreview, serverUrl: data.url });
        setSelectedActor(data.url);
        setActorUploadStatus(data.saved ? 'Saved to avatars and selected.' : 'Selected locally. S3 gallery save unavailable.');
        if (data.saved) await refreshActorGallery();
      }
    } catch (err) {
      console.error('Upload failed:', err);
      setActorUploadStatus(err.message || 'Upload failed');
    }
  };

  const handleCopy = (text, label) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(''), 2000);
  };

  const handleReset = () => {
    setStep(0);
    setAnalyzeError('');
    setAnalysis(null);
    setWebResearch(null);
    setScripts([]);
    setShotHistory([]);
    setFromCache(false);
    localStorage.removeItem(CACHE_KEY);
    clearLastJob();
    setSelectedScript(0);
    setJobId(null);
    setGenLogs([]);
    setGenStatus('idle');
    setGenResult(null);
    setGenerating(false);
    setLipSyncing(false);
    setActorDescription('');
    setEditedNarration('');
  };

  const estimateInputText = (() => {
    if (scriptMode === 'custom' && customScript.trim()) return customScript;
    if (editedNarration.trim()) return editedNarration;
    if (scripts[selectedScript]?.full_narration) return scripts[selectedScript].full_narration;
    // Описание бизнеса — не текст озвучки: длительность по нему не оцениваем,
    // иначе плитки показывают цену 75-секундного ролика вместо типичных ~35с.
    return '';
  })();

  const estimateForMode = (modeId) => estimateSaasVideoCost({
    text: estimateInputText,
    videoMode: modeId,
    ttsProvider,
    brollMode,
    hasSelectedActor: Boolean(selectedActor),
    script: scripts[selectedScript],
    storyboardGenerationMode,
  });

  const estimateModePriceLabel = (modeId) => `~${formatUsd(estimateForMode(modeId).total)}`;
  const currentScript = scripts[selectedScript];
  const storyboardSelected = isStoryboardScript(currentScript);

  // ─── Render Steps ─────────────────────────────────────────────────

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="max-w-5xl mx-auto p-6 pb-28 md:pb-8 lg:p-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-violet-500 to-fuchsia-500 rounded-xl flex items-center justify-center">
                <Zap size={20} className="text-white" />
              </div>
              AI Shorts
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Generate viral UGC videos for any product or business
            </p>
          </div>
          {step > 0 && (
            <button onClick={handleReset} className="text-sm text-zinc-400 hover:text-white flex items-center gap-1 transition-colors">
              <RefreshCw size={14} /> Start over
            </button>
          )}
        </div>

        {/* Progress Steps */}
        <div className="flex items-center gap-2 mb-8">
          {['Setup', 'Analysis', 'Configure', 'Generate', 'Result'].map((label, i) => (
            <React.Fragment key={i}>
              {i > 0 && <div className={`flex-1 h-px ${i <= step ? 'bg-violet-500' : 'bg-white/10'}`} />}
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                i === step ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30' :
                i < step ? 'bg-violet-500/10 text-violet-400' :
                'bg-white/5 text-zinc-600'
              }`}>
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  i < step ? 'bg-violet-500 text-white' :
                  i === step ? 'bg-violet-500/30 text-violet-300' :
                  'bg-white/10 text-zinc-600'
                }`}>
                  {i < step ? <Check size={10} /> : i + 1}
                </span>
                <span className="hidden sm:inline">{label}</span>
              </div>
            </React.Fragment>
          ))}
        </div>

        {/* ── Step 0: URL Input ────────────────────────────────── */}
        {step === 0 && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-6">
            <div className="glass-panel p-8 space-y-6">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <div className="min-w-0 flex-1">
                  <label className="block text-sm font-medium text-zinc-300 mb-2">
                    <span className="inline-flex items-center gap-1.5"><Target size={14} className="text-violet-300" /> Проект</span>
                  </label>
                  {businessProfiles.length > 0 ? (
                    <OptionPicker
                      value={selectedBusinessProfileId}
                      onChange={(value) => {
                        const profile = businessProfiles.find((item) => businessProfileKey(item) === value);
                        if (profile) handleLoadBusinessProfile(profile);
                      }}
                      options={businessProfiles.map((profile) => ({
                        value: businessProfileKey(profile),
                        label: profile.name,
                      }))}
                      placeholder="Выбери сохранённый проект..."
                    />
                  ) : (
                    <p className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-xs text-zinc-500">
                      Нет сохранённых проектов — можно заполнить описание вручную или создать проект.
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => onManageProjects?.()}
                  className="btn-secondary px-4 py-3 text-sm flex items-center justify-center gap-2 shrink-0"
                >
                  <Settings2 size={14} /> Управлять проектами
                </button>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Описание бизнеса / продукта <span className="text-zinc-600">(обязательно)</span>
                </label>
                <AutoTextarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  minRows={3}
                  className="input-field text-sm"
                  placeholder="Что продаём, кому, какой результат, какие ограничения, тон коммуникации."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-3">Источник сценария</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {[
                    { id: 'ai', label: 'Сгенерировать варианты', desc: 'ИИ возьмёт проект, тему и формат как бриф' },
                    { id: 'custom', label: 'Мой точный текст', desc: 'Не переписывать озвучку перед генерацией' },
                  ].map((mode) => (
                    <button
                      key={mode.id}
                      onClick={() => setScriptMode(mode.id)}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        scriptMode === mode.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <div className="text-xs font-semibold">{mode.label}</div>
                      <div className="text-[10px] text-zinc-500 mt-0.5">{mode.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div data-section="text-model-section">
                <label className="block text-sm font-medium text-zinc-300 mb-3">Модель текста</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {TEXT_MODEL_OPTIONS.map((model) => (
                    <button
                      key={model.id}
                      onClick={() => setTextModel(model.id)}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        textModel === model.id
                          ? model.id === 'pro'
                            ? 'border-amber-500/50 bg-amber-500/10 text-amber-200'
                            : 'border-blue-500/50 bg-blue-500/10 text-blue-200'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold">{model.label}</span>
                        {model.id === 'pro' && (
                          <span className="text-[10px] rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-300">paid</span>
                        )}
                      </div>
                      <div className="text-[10px] text-zinc-500 mt-0.5">{model.desc}</div>
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-zinc-600 mt-1">
                  Pro дороже и медленнее, но лучше подходит для сильного оффера, точной раскадровки и русского текста.
                </p>
              </div>

              <div data-section="script-format-section">
                <label className="block text-sm font-medium text-zinc-300 mb-3">Формат сценария</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {SCRIPT_FORMAT_OPTIONS.map((format) => (
                    <button
                      key={format.id}
                      onClick={() => setScriptFormat(format.id)}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        scriptFormat === format.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <div className="text-xs font-semibold">{format.label}</div>
                      <div className="text-[10px] text-zinc-500 mt-0.5">{format.desc}</div>
                    </button>
                  ))}
                </div>
                {scriptFormat === 'storyboard_v3' && (
                  <p className="text-[10px] text-zinc-500 mt-2">
                    ИИ сгенерирует кадры, действия, текст на экране и промпты для выбранной видео-модели.
                  </p>
                )}
              </div>

              {/* Video Mode Selector */}
              <div data-section="video-mode-section">
                <label className="block text-sm font-medium text-zinc-300 mb-1">Модель видео и качество</label>
                <p className="text-[11px] text-zinc-500 mb-3">Какая ИИ-модель нарисует картинку и насколько детально. Цена — оценка за весь ролик.</p>
                <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))' }}>
                  {activeVideoModeOptions(scriptFormat).map((mode) => {
                    const active = videoMode === mode.id;
                    const activeClass =
                      mode.id === 'lowcost' ? 'border-green-500/50 bg-green-500/10 ring-1 ring-green-500/30' :
                      mode.id === 'storyboard_veo31_quality' ? 'border-amber-500/50 bg-amber-500/10 ring-1 ring-amber-500/30' :
                      mode.id === 'standard' || mode.id === 'storyboard_v3_standard' ? 'border-blue-500/50 bg-blue-500/10 ring-1 ring-blue-500/30' :
                      'border-violet-500/50 bg-violet-500/10 ring-1 ring-violet-500/30';
                    const textClass =
                      active && mode.id === 'lowcost' ? 'text-green-300' :
                      active && mode.id === 'storyboard_veo31_quality' ? 'text-amber-300' :
                      active && (mode.id === 'standard' || mode.id === 'storyboard_v3_standard') ? 'text-blue-300' :
                      active && (mode.id === 'premium' || mode.id === 'storyboard_v3_pro') ? 'text-violet-300' :
                      'text-zinc-300';
                    const priceClass =
                      mode.id === 'lowcost' ? 'text-green-400 bg-green-500/10' :
                      mode.id === 'storyboard_veo31_quality' ? 'text-amber-400 bg-amber-500/10' :
                      mode.id === 'standard' || mode.id === 'storyboard_v3_standard' ? 'text-blue-400 bg-blue-500/10' :
                      'text-violet-400 bg-violet-500/10';

                    return (
                      <button
                        key={mode.id}
                        onClick={() => setVideoMode(mode.id)}
                        className={`p-4 rounded-xl border text-left transition-all ${
                          active ? activeClass : 'border-white/10 bg-white/5 hover:bg-white/10'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className={`text-sm font-semibold ${textClass}`}>{mode.label}</span>
                          <span className={`text-xs font-mono px-2 py-0.5 rounded-full whitespace-nowrap ${priceClass}`}>
                            {estimateModePriceLabel(mode.id)}
                          </span>
                        </div>
                        <p className="text-[11px] text-zinc-500 leading-relaxed">{mode.desc}</p>
                      </button>
                    );
                  })}
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  {[
                    {
                      checked: backgroundMusic,
                      toggle: () => setBackgroundMusic((v) => !v),
                      label: '🎵 Фоновая музыка',
                      hint: 'Тихая музыкальная подложка под озвучкой',
                    },
                    {
                      checked: clipVisionQc,
                      toggle: () => setClipVisionQc((v) => !v),
                      label: '👁 ИИ-проверка кадров',
                      hint: 'Gemini ищет брак в готовых клипах (~$0.001 за ролик), только предупреждает',
                    },
                    {
                      checked: brollImageFirst,
                      toggle: () => setBrollImageFirst((v) => !v),
                      label: '🖼 B-roll через кадр-референс',
                      hint: 'Сначала Flux-картинка, потом анимация — стабильнее композиция (+$0.05 за b-roll кадр)',
                    },
                  ].map((opt) => (
                    <button
                      key={opt.label}
                      type="button"
                      onClick={opt.toggle}
                      title={opt.hint}
                      className={`px-3 py-1.5 rounded-full border text-[11px] transition-all ${
                        opt.checked
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-500 hover:text-zinc-300'
                      }`}
                    >
                      {opt.checked ? '✓ ' : ''}{opt.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="hidden">
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  {url.trim() ? 'Extra context' : 'Describe your product/business'} <span className="text-zinc-600">{url.trim() ? '(optional)' : '(required if no URL)'}</span>
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="input-field resize-none text-sm"
                  placeholder="e.g. Pizzería artesanal en Madrid, Coach de productividad, Tienda de ropa deportiva, App de meditación..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Тема текущего ролика <span className="text-zinc-600">(необязательно, но лучше заполнить)</span>
                </label>
                <AutoTextarea
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  minRows={2}
                  className="input-field text-sm"
                  placeholder="Напр.: Почему вечерний срыв начинается утром; Что съесть в 17:00, чтобы не тянуло на сладкое вечером..."
                />
                <p className="text-[10px] text-zinc-600 mt-1">В AI-режиме варианты сценариев строятся вокруг этой темы. В ручном режиме тема нужна для заголовка, caption и визуальных подсказок.</p>
              </div>

              {scriptMode === 'custom' && (
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">
                    Точный текст озвучки <span className="text-zinc-600">(обязательно)</span>
                  </label>
                  <AutoTextarea
                    value={customScript}
                    onChange={(e) => setCustomScript(e.target.value)}
                    minRows={7}
                    className="input-field font-mono text-xs"
                    placeholder={`Ты срываешься вечером не потому, что слабая.\nЧасто проблема начинается утром: кофе вместо завтрака, маленький обед...\nНапиши "НЕДЕЛЯ" - пришлю чеклист антисрыв-вечера.`}
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">
                    {customScript.length} символов &middot; ~{Math.max(1, Math.round(customScript.trim().split(/\s+/).filter(Boolean).length / 2.5))} сек озвучки. Этот текст не будет переписан перед генерацией.
                  </p>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 bg-white/5 border border-white/10 rounded-xl px-3 py-2.5">
                <span className="text-xs text-zinc-500">
                  Язык сценария — из проекта:
                  <span className="text-zinc-300 ml-1.5 font-medium">
                    {({ en: '🇺🇸 English', es: '🇪🇸 Español', ru: '🇷🇺 Русский' })[language] || language}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => onManageProjects?.()}
                  className="text-[11px] text-violet-300 hover:text-violet-200"
                >
                  Изменить в Проектах
                </button>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Стиль ролика</label>
                <p className="text-[11px] text-zinc-500 mb-3">Задаёт структуру сценария: с чего начнётся ролик и как построен рассказ.</p>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  {STYLE_OPTIONS.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setStyle(s.id)}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        style === s.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <div className="text-xs font-medium">{s.label}</div>
                      <div className="text-[10px] text-zinc-500 mt-0.5">{s.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between gap-3 mb-2">
                  <label className="block text-sm font-medium text-zinc-300">Количество вариантов сценария</label>
                  <span className="text-[11px] text-zinc-500">Сейчас: {numScripts}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {[1, 2, 3, 5].map((n) => (
                    <button
                      key={n}
                      onClick={() => setNumScripts(n)}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        numScripts === n
                          ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30'
                          : 'bg-white/5 text-zinc-400 border border-white/10 hover:bg-white/10'
                      }`}
                    >
                      {n} {n === 1 ? 'вариант' : n < 5 ? 'варианта' : 'вариантов'}
                    </button>
                  ))}
                </div>
              </div>

              {analyzeError && (
                <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                  <AlertCircle size={14} />
                  {analyzeError}
                </div>
              )}

              <button
                onClick={handleAnalyze}
                disabled={analyzing || (scriptMode === 'custom' ? !customScript.trim() : (!url.trim() && !description.trim()))}
                className="btn-primary w-full py-3 text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {analyzing ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    {scriptMode === 'custom' ? 'Готовим ваш текст...' : (url.trim() ? 'Изучаем сайт и пишем сценарии... (45-90с)' : 'Пишем сценарии... (20-40с)')}
                  </>
                ) : (
                  <>
                    <Sparkles size={16} />
                    {scriptMode === 'custom' ? 'Подготовить мой текст' : (url.trim() ? 'Изучить сайт и написать сценарии' : 'Написать сценарии')}
                  </>
                )}
              </button>
            </div>

            {/* Info cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="glass-panel p-4">
                <Target size={16} className="text-violet-400 mb-2" />
                <h3 className="text-sm font-medium text-zinc-300">Deep Research</h3>
                <p className="text-xs text-zinc-500 mt-1">AI analyzes your product via URL scraping + web research, or generates directly from your description.</p>
              </div>
              <div className="glass-panel p-4">
                <MessageSquare size={16} className="text-violet-400 mb-2" />
                <h3 className="text-sm font-medium text-zinc-300">Pain Point Scripts</h3>
                <p className="text-xs text-zinc-500 mt-1">Generates hook-problem-solution scripts targeting your audience&apos;s real pain points.</p>
              </div>
              <div className="glass-panel p-4">
                <Film size={16} className="text-violet-400 mb-2" />
                <h3 className="text-sm font-medium text-zinc-300">Ваши AI-ролики</h3>
                <p className="text-xs text-zinc-500 mt-1">Realistic AI-generated actors with lip-sync, b-roll, and viral subtitles. From ~$0.50/video.</p>
              </div>
            </div>
          </div>
        )}

        {/* ── Step 1: Analysis Results ─────────────────────────── */}
        {step === 1 && analysis && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-6">
            {/* Analysis Summary */}
            <div className="glass-panel p-6">
              <div className="flex items-start justify-between gap-3 mb-4">
                <h2 className="text-lg font-semibold flex items-start gap-2 min-w-0">
                  <Eye size={18} className="text-violet-400 shrink-0 mt-1" />
                  <span className="break-words">{analysis.product_name || 'Analysis'}</span>
                </h2>
                <div className="flex items-center gap-2 shrink-0">
                  {fromCache && (
                    <span className="text-[10px] bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded-full border border-amber-500/20 flex items-center gap-1">
                      Cached
                      <button onClick={() => { setStep(0); setFromCache(false); }} className="hover:text-white ml-1" title="Re-analyze">
                        <RefreshCw size={9} />
                      </button>
                    </span>
                  )}
                  {analysis.industry && (
                    <span className="text-xs bg-violet-500/10 text-violet-400 px-2 py-1 rounded-full border border-violet-500/20">
                      {analysis.industry}
                    </span>
                  )}
                </div>
              </div>
              {(analysis.one_liner || analysis.description) && (
                <p className="text-sm text-zinc-400 mb-4">{analysis.one_liner || analysis.description}</p>
              )}

              {((analysis.pain_points || []).length > 0 || (analysis.emotional_hooks || []).length > 0) ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(analysis.pain_points || []).length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Pain Points</h3>
                      <div className="space-y-1.5">
                        {(analysis.pain_points || []).map((pp, i) => (
                          <div key={i} className="flex items-start gap-2 text-sm">
                            <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${
                              pp.intensity === 'high' ? 'bg-red-400' : pp.intensity === 'medium' ? 'bg-yellow-400' : 'bg-green-400'
                            }`} />
                            <div>
                              <span className="text-zinc-300">{pp.pain}</span>
                              {pp.source && pp.source !== 'website' && (
                                <span className="ml-1.5 text-[9px] bg-primary/10 text-violet-300 px-1 py-0.5 rounded">{pp.source}</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {(analysis.emotional_hooks || []).length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Emotional Hooks</h3>
                      <div className="space-y-1.5">
                        {(analysis.emotional_hooks || []).map((h, i) => (
                          <div key={i} className="text-sm text-zinc-300 flex items-start gap-2">
                            <TrendingUp size={12} className="text-violet-400 mt-1 shrink-0" />
                            {h}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-zinc-600">
                  Быстрый режим: сценарии построены напрямую из описания проекта, без глубокого анализа болей аудитории.
                </p>
              )}
            </div>

            {/* Web Research Results */}
            {webResearch && (
              <div className="glass-panel p-6">
                <h3 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
                  <Globe size={14} className="text-violet-400" />
                  Web Research (Google Search)
                  {webResearch.grounding_sources && (
                    <span className="text-[10px] bg-primary/10 text-violet-300 px-2 py-0.5 rounded-full ml-auto">
                      {webResearch.grounding_sources.length} sources
                    </span>
                  )}
                </h3>

                {/* Real user reviews */}
                {webResearch.real_reviews && webResearch.real_reviews.length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Real User Reviews</h4>
                    <div className="space-y-2">
                      {webResearch.real_reviews.slice(0, 5).map((review, i) => (
                        <div key={i} className="text-xs bg-white/5 rounded-lg p-2.5 border border-white/5">
                          <p className="text-zinc-300 italic">&quot;{review.quote}&quot;</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-zinc-600">{review.source}</span>
                            <span className={`px-1 py-0.5 rounded text-[9px] ${
                              review.sentiment === 'positive' ? 'bg-green-500/10 text-green-400' :
                              review.sentiment === 'negative' ? 'bg-red-500/10 text-red-400' :
                              'bg-zinc-500/10 text-zinc-400'
                            }`}>{review.sentiment}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Competitors */}
                {webResearch.competitors && webResearch.competitors.length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Competitors</h4>
                    <div className="flex flex-wrap gap-2">
                      {webResearch.competitors.map((c, i) => (
                        <span key={i} className="text-xs bg-white/5 px-2 py-1 rounded-lg text-zinc-400 border border-white/5" title={c.comparison}>
                          {c.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Sources */}
                {webResearch.grounding_sources && webResearch.grounding_sources.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Sources</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {webResearch.grounding_sources.slice(0, 8).map((src, i) => (
                        <a
                          key={i}
                          href={src.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-violet-400 hover:text-violet-300 bg-primary/5 px-2 py-0.5 rounded-full border border-primary/10 hover:border-primary/30 transition-colors truncate max-w-[200px]"
                          title={src.title}
                        >
                          {src.title || (() => { try { return new URL(src.url).hostname; } catch { return src.url; } })()}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Scripts */}
            <div>
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Sparkles size={18} className="text-yellow-400" />
                Generated Scripts
                <span className="text-xs bg-white/10 px-2 py-0.5 rounded-full ml-auto">
                  {scripts.length} {scripts.length === 1 ? 'сценарий' : scripts.length < 5 ? 'сценария' : 'сценариев'}
                </span>
              </h2>

              <div className="grid grid-cols-1 gap-4">
                {scripts.map((script, i) => (
                  <div
                    key={i}
                    onClick={() => handleSelectScript(i)}
                    className={`glass-panel p-5 cursor-pointer transition-all ${
                      selectedScript === i
                        ? 'border-violet-500/50 bg-violet-500/5 ring-1 ring-violet-500/20'
                        : 'hover:bg-white/5'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold ${
                          selectedScript === i ? 'bg-violet-500 text-white' : 'bg-white/10 text-zinc-400'
                        }`}>
                          {i + 1}
                        </span>
                        <div>
                          <h3 className="text-sm font-semibold text-zinc-200">{script.title}</h3>
                          <span className="text-[10px] text-zinc-500">
                            {[
                              `${script.duration_seconds || estimateStoryboardSeconds(script)} сек`,
                              script.style,
                              script.target_platform,
                            ].filter(Boolean).join(' · ')}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {selectedScript === i && (
                          <span className="text-[10px] bg-violet-500/20 text-violet-300 px-2 py-0.5 rounded-full">Выбран</span>
                        )}
                        <button
                          type="button"
                          aria-label="Открыть раскадровку"
                          onClick={(event) => { event.stopPropagation(); setSelectedScript(i); setStep(2); }}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5 text-[11px] font-medium text-zinc-300 transition-colors hover:border-violet-400/40 hover:bg-violet-500/10 hover:text-violet-100"
                        >
                          <Pencil size={12} /> Раскадровка
                        </button>
                      </div>
                    </div>

                    {(
                      <>
                        {isStoryboardScript(script) ? (
                          <div className="space-y-2">
                            {(script.shots || []).map((shot, j) => (
                              <div key={j} className="grid gap-3 rounded-lg border border-white/5 bg-white/[0.03] p-3 text-xs md:grid-cols-[82px,minmax(0,1fr)]">
                                <div className="text-violet-300 font-semibold">
                                  КАДР {shot.shot_number || j + 1}
                                </div>
                                <div className="min-w-0 space-y-1">
                                  <p className="text-zinc-300 leading-relaxed">{shot.scene || shot.generation_prompt}</p>
                                  {shot.speech && <p className="text-zinc-500 leading-relaxed">«{shot.speech}»</p>}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <>
                            {/* Segments preview */}
                            <div className="flex gap-1 mb-3">
                              {(script.segments || []).map((seg, j) => (
                                <div
                                  key={j}
                                  className={`h-1.5 rounded-full ${
                                    seg.type === 'hook' ? 'bg-red-400' :
                                    seg.type === 'problem' ? 'bg-yellow-400' :
                                    seg.type === 'solution' ? 'bg-green-400' :
                                    'bg-blue-400'
                                  }`}
                                  style={{ flex: (seg.end - seg.start) }}
                                  title={`${seg.type}: ${seg.start}s-${seg.end}s`}
                                />
                              ))}
                            </div>

                            <div className="space-y-2">
                              {(script.segments || []).map((seg, j) => (
                                <div key={j} className="flex gap-3 text-xs">
                                  <span className={`shrink-0 px-1.5 py-0.5 rounded font-mono uppercase tracking-wider ${
                                    seg.type === 'hook' ? 'bg-red-500/20 text-red-300' :
                                    seg.type === 'problem' ? 'bg-yellow-500/20 text-yellow-300' :
                                    seg.type === 'solution' ? 'bg-green-500/20 text-green-300' :
                                    'bg-blue-500/20 text-blue-300'
                                  }`}>
                                    {seg.type}
                                  </span>
                                  <span className="text-zinc-400 leading-relaxed">{seg.narration}</span>
                                </div>
                              ))}
                            </div>
                          </>
                        )}

                        {(script.hashtags || []).length > 0 && (
                          <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-3 flex-wrap">
                            {(script.hashtags || []).slice(0, 4).map((tag, j) => (
                              <span key={j} className="text-[10px] text-zinc-500">{tag}</span>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep(0)} className="btn-secondary px-4 py-2 text-sm flex items-center gap-2">
                <ChevronLeft size={14} /> Назад
              </button>
              <button onClick={() => setStep(2)} className="btn-primary px-6 py-2 text-sm flex items-center gap-2">
                К настройке ролика <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: Configure ────────────────────────────────── */}
        {step === 2 && scripts[selectedScript] && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-6">
            <div className="glass-panel p-6 space-y-5">
              <h2 className="text-lg font-semibold">Настройка ролика</h2>
              <p className="text-sm text-zinc-500">
                Сценарий: <strong className="text-zinc-300">{scripts[selectedScript].title}</strong>
              </p>

              {storyboardSelected && (
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
                        <Film size={14} /> Кадры ролика
                      </h3>
                      <p className="text-[11px] text-zinc-500 mt-0.5 max-w-xl">
                        Ролик собирается по кадрам. Для каждого укажи, что в кадре и что человек говорит.
                        Кадры можно добавлять, дублировать, удалять и перетаскивать за уголок <GripVertical size={11} className="inline align-[-1px] text-zinc-500" />, чтобы поменять порядок.
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {shotHistory.some((entry) => entry.scriptIndex === selectedScript) && (
                        <button
                          type="button"
                          onClick={undoShotChange}
                          title="Отменить последнее действие с кадрами"
                          className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-zinc-300 transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-violet-200"
                        >
                          <Undo2 size={13} /> Отменить
                        </button>
                      )}
                      <span className="rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-zinc-400">
                        {(scripts[selectedScript].shots || []).length} {pluralShots((scripts[selectedScript].shots || []).length)}
                      </span>
                      <span className="rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-zinc-400">
                        ~{estimateStoryboardSeconds(scripts[selectedScript], '')} сек
                      </span>
                    </div>
                  </div>

                  {/* Сгенерировать стартовые кадры (Flux) до платного видео,
                      чтобы увидеть и утвердить композицию каждого шота. */}
                  <div className="rounded-xl border border-primary/20 bg-primary/[0.04] p-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-[11px] text-zinc-400 max-w-md">
                      Сгенерируй стартовые кадры и проверь композицию до платной генерации видео.
                      Кадры можно перегенерировать по одному или заменить своим фото — видео переиспользует их.
                    </p>
                    <button
                      type="button"
                      onClick={() => handleGenerateFrames(null)}
                      disabled={framesGenerating}
                      className="btn-secondary shrink-0 px-3 py-2 text-[12px] flex items-center justify-center gap-1.5 disabled:opacity-50"
                    >
                      {framesGenerating && framesShot === null
                        ? (<><Loader2 size={13} className="animate-spin" /> Генерирую…</>)
                        : (<><Sparkles size={13} /> Сгенерить кадры (~{formatUsd(((scripts[selectedScript].shots || []).length) * 0.05)})</>)}
                    </button>
                  </div>

                  <div className="space-y-2.5">
                    {(scripts[selectedScript].shots || []).map((shot, shotIndex) => {
                      const shots = scripts[selectedScript].shots || [];
                      const previewUrl = shot.image_preview
                        || (shot.local_url ? getApiUrl(shot.local_url) : '')
                        || (shot.image_url?.startsWith('/videos/') ? getApiUrl(shot.image_url) : shot.image_url)
                        || (shot.preview_frame_url ? getApiUrl(shot.preview_frame_url) : '');
                      // After a render the shot carries its generated frame/clip; a manually
                      // uploaded photo still wins so the user's choice isn't overwritten.
                      const isGeneratedPreview = !shot.image_preview && !shot.local_url && !shot.image_url && Boolean(shot.preview_frame_url);
                      const clipUrl = shot.clip_url ? getApiUrl(shot.clip_url) : '';
                      const inputId = `storyboard-frame-${selectedScript}-${shotIndex}`;
                      const isBroll = (shot.visual_type || '').toLowerCase().replace(/[-_]/g, '').includes('broll');

                      return (
                        <div
                          key={shotIndex}
                          onDragOver={(event) => {
                            if (dragShotIndex === null) return;
                            event.preventDefault();
                            if (dragOverShotIndex !== shotIndex) setDragOverShotIndex(shotIndex);
                          }}
                          onDrop={(event) => { event.preventDefault(); dropShotOnto(shotIndex); }}
                          className={`rounded-xl border bg-black/20 p-3 transition-all ${
                            dragShotIndex === shotIndex
                              ? 'border-primary/40 opacity-50'
                              : dragOverShotIndex === shotIndex && dragShotIndex !== null
                                ? 'border-primary/60 ring-1 ring-primary/40'
                                : 'border-white/10'
                          }`}
                        >
                          {/* Header: drag handle + number + actions. The shot
                              type is set (and shown) by the Говорит/Перебивка
                              toggle below, so no separate read-only badge here. */}
                          <div className="mb-3 flex items-center justify-between gap-2">
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                draggable
                                onDragStart={() => setDragShotIndex(shotIndex)}
                                onDragEnd={() => { setDragShotIndex(null); setDragOverShotIndex(null); }}
                                aria-label="Перетащить кадр"
                                title="Потяни, чтобы поменять порядок"
                                className="cursor-grab rounded-md p-1 text-zinc-600 transition-colors hover:text-zinc-300 active:cursor-grabbing"
                              >
                                <GripVertical size={15} />
                              </button>
                              <span className="inline-flex h-6 min-w-[24px] items-center justify-center rounded-full bg-primary/15 px-2 text-xs font-semibold text-violet-200">
                                {shotIndex + 1}
                              </span>
                            </div>
                            <div className="flex items-center gap-0.5">
                              <button
                                type="button"
                                onClick={() => moveSelectedScriptShot(shotIndex, -1)}
                                disabled={shotIndex === 0}
                                aria-label="Переместить кадр выше"
                                title="Выше"
                                className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
                              >
                                <ChevronUp size={15} />
                              </button>
                              <button
                                type="button"
                                onClick={() => moveSelectedScriptShot(shotIndex, 1)}
                                disabled={shotIndex === shots.length - 1}
                                aria-label="Переместить кадр ниже"
                                title="Ниже"
                                className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
                              >
                                <ChevronDown size={15} />
                              </button>
                              <button
                                type="button"
                                onClick={() => duplicateSelectedScriptShot(shotIndex)}
                                aria-label="Дублировать кадр"
                                title="Дублировать кадр"
                                className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200"
                              >
                                <Copy size={15} />
                              </button>
                              <button
                                type="button"
                                onClick={() => removeSelectedScriptShot(shotIndex)}
                                disabled={shots.length <= 1}
                                aria-label="Удалить кадр"
                                title="Удалить кадр"
                                className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-30 disabled:hover:bg-transparent"
                              >
                                <Trash2 size={15} />
                              </button>
                            </div>
                          </div>

                          <div className="grid gap-3 lg:grid-cols-[120px,minmax(0,1fr)]">
                            <div className="space-y-2">
                              <div className="aspect-[9/16] overflow-hidden rounded-lg border border-white/10 bg-zinc-950">
                                {previewUrl ? (
                                  <img src={previewUrl} alt={`Кадр ${shotIndex + 1}`} className="h-full w-full object-cover" />
                                ) : (
                                  <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-center text-[10px] text-zinc-600">
                                    <Upload size={18} />
                                    Своё фото
                                  </div>
                                )}
                              </div>
                              <input
                                id={inputId}
                                type="file"
                                accept="image/*"
                                className="hidden"
                                onChange={(event) => {
                                  const file = event.target.files?.[0];
                                  if (file) handleStoryboardFrameUpload(shotIndex, file);
                                  event.target.value = '';
                                }}
                              />
                              <label htmlFor={inputId} className="btn-secondary w-full cursor-pointer px-2 py-2 text-[11px] flex items-center justify-center gap-1.5">
                                <Upload size={12} /> Загрузить фото
                              </label>
                              <button
                                type="button"
                                onClick={() => handleGenerateFrames(shot.shot_number ?? (shotIndex + 1))}
                                disabled={framesGenerating}
                                title="Сгенерировать/перегенерировать кадр по описанию"
                                className="btn-secondary w-full px-2 py-2 text-[11px] flex items-center justify-center gap-1.5 disabled:opacity-50"
                              >
                                {framesGenerating && framesShot === (shot.shot_number ?? (shotIndex + 1))
                                  ? (<><Loader2 size={12} className="animate-spin" /> Кадр…</>)
                                  : (<><RefreshCw size={12} /> {previewUrl ? 'Перегенерить' : 'Сгенерить кадр'}</>)}
                              </button>
                              {isGeneratedPreview && (
                                <p className="text-[10px] text-violet-300/80">Сгенерённый кадр</p>
                              )}
                              {clipUrl && (
                                <a
                                  href={clipUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="btn-secondary w-full px-2 py-1.5 text-[11px] flex items-center justify-center gap-1.5"
                                >
                                  ▶ Клип
                                </a>
                              )}
                              {shot.frame_status && (
                                <p className="text-[10px] text-zinc-500">{shot.frame_status}</p>
                              )}
                            </div>

                            <div className="space-y-3">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="inline-flex overflow-hidden rounded-lg border border-white/10 text-[11px]">
                                  <button
                                    type="button"
                                    onClick={() => handleSelectedScriptShot(shotIndex, 'visual_type', 'avatar')}
                                    className={`px-2.5 py-1 transition-colors ${!isBroll ? 'bg-primary/15 text-violet-200' : 'text-zinc-500 hover:text-zinc-300'}`}
                                  >
                                    Говорит
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleSelectedScriptShot(shotIndex, 'visual_type', 'broll')}
                                    className={`px-2.5 py-1 transition-colors ${isBroll ? 'bg-primary/15 text-violet-200' : 'text-zinc-500 hover:text-zinc-300'}`}
                                  >
                                    Перебивка
                                  </button>
                                </div>
                              </div>
                              <label className="space-y-1.5 text-xs text-zinc-400 block">
                                <span>Что в кадре</span>
                                <textarea
                                  className="input-field min-h-[58px] resize-y py-2 text-sm leading-relaxed"
                                  value={shot.scene || ''}
                                  onChange={(event) => handleSelectedScriptShot(shotIndex, 'scene', event.target.value)}
                                  placeholder="Опиши, что видно в кадре"
                                />
                              </label>
                              <label className="space-y-1.5 text-xs text-zinc-400 block">
                                <span>{isBroll ? 'Текст за кадром (озвучка)' : 'Что говорит'}</span>
                                <textarea
                                  className="input-field min-h-[58px] resize-y py-2 text-sm leading-relaxed"
                                  value={shot.speech || ''}
                                  onChange={(event) => handleSelectedScriptShot(shotIndex, 'speech', event.target.value)}
                                  placeholder={isBroll ? 'Что звучит голосом, пока показываем вставку (можно оставить пустым)' : 'Реплика для этого кадра'}
                                />
                              </label>
                              {isBroll && (
                                <p className="-mt-1.5 text-[10px] text-zinc-600">
                                  В перебивке лицо не показываем, но озвучка продолжает звучать поверх вставки.
                                </p>
                              )}
                              {(() => {
                                // Collapsed by default: the prompt is auto-derived from the
                                // scene/speech and is noise for most users. They open it only
                                // when they deliberately want to hand-tune how the shot is drawn.
                                const promptOpen = shotIndex in openPromptShots
                                  ? openPromptShots[shotIndex]
                                  : false;
                                return (
                                  <div>
                                    <button
                                      type="button"
                                      onClick={() => setOpenPromptShots((m) => ({ ...m, [shotIndex]: !promptOpen }))}
                                      className="inline-flex items-center gap-1 text-[11px] text-zinc-500 transition-colors hover:text-zinc-300"
                                    >
                                      <ChevronDown size={12} className={`transition-transform ${promptOpen ? 'rotate-180' : ''}`} />
                                      Подсказка для нейросети
                                      <span className="text-zinc-600">— ручной промпт, перебивает «Что в кадре»</span>
                                    </button>
                                    {promptOpen && (
                                      <div className="mt-1.5 space-y-1">
                                        <input
                                          className="input-field py-2 text-sm"
                                          value={shot.generation_prompt || ''}
                                          onChange={(event) => updateSelectedScriptShot(shotIndex, { generation_prompt: event.target.value, prompt_manual: true })}
                                          placeholder="English prompt: close-up, warm light, realistic"
                                        />
                                        {shot.prompt_manual && (
                                          <button
                                            type="button"
                                            onClick={() => updateSelectedScriptShot(shotIndex, { prompt_manual: false })}
                                            className="text-[10px] text-zinc-500 transition-colors hover:text-zinc-300"
                                          >
                                            Сбросить — строить кадр из «Что в кадре»
                                          </button>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })()}
                              {(() => {
                                const advOpen = Boolean(openAdvancedShots[shotIndex]);
                                return (
                                  <div>
                                    <button
                                      type="button"
                                      onClick={() => setOpenAdvancedShots((m) => ({ ...m, [shotIndex]: !advOpen }))}
                                      className="inline-flex items-center gap-1 text-[11px] text-zinc-500 transition-colors hover:text-zinc-300"
                                    >
                                      <ChevronDown size={12} className={`transition-transform ${advOpen ? 'rotate-180' : ''}`} />
                                      Расширенные
                                      <span className="text-zinc-600">— роль, переход, действие, камера</span>
                                    </button>
                                    {advOpen && (
                                      <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                                        <label className="space-y-1 text-[11px] text-zinc-500 block">
                                          <span>Роль кадра</span>
                                          <input
                                            className="input-field py-1.5 text-sm"
                                            value={shot.role || ''}
                                            onChange={(event) => handleSelectedScriptShot(shotIndex, 'role', event.target.value)}
                                            placeholder="hook / problem / cta"
                                          />
                                        </label>
                                        <label className="space-y-1 text-[11px] text-zinc-500 block">
                                          <span>Переход после кадра</span>
                                          <input
                                            className="input-field py-1.5 text-sm"
                                            value={shot.transition || ''}
                                            onChange={(event) => handleSelectedScriptShot(shotIndex, 'transition', event.target.value)}
                                            placeholder="cut / smooth_0.3s"
                                          />
                                        </label>
                                        <label className="space-y-1 text-[11px] text-zinc-500 block sm:col-span-2">
                                          <span>Действие актёра</span>
                                          <textarea
                                            className="input-field min-h-[48px] resize-y py-1.5 text-sm leading-relaxed"
                                            value={shot.actor_action || shot.action || ''}
                                            onChange={(event) => handleSelectedScriptShot(shotIndex, 'actor_action', event.target.value)}
                                          />
                                        </label>
                                        <label className="space-y-1 text-[11px] text-zinc-500 block sm:col-span-2">
                                          <span>Камера</span>
                                          <input
                                            className="input-field py-1.5 text-sm"
                                            value={shot.camera || ''}
                                            onChange={(event) => handleSelectedScriptShot(shotIndex, 'camera', event.target.value)}
                                            placeholder="крупный план, лёгкая ручная камера"
                                          />
                                        </label>
                                      </div>
                                    )}
                                  </div>
                                );
                              })()}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <button
                    type="button"
                    onClick={() => addSelectedScriptShot()}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 py-2.5 text-sm text-zinc-400 transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-violet-200"
                  >
                    <Plus size={16} /> Добавить кадр
                  </button>
                </div>
              )}

              {storyboardSelected && (
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                    <Film size={14} /> Способ генерации видео
                  </label>
                  <div className="grid sm:grid-cols-2 gap-2">
                    {STORYBOARD_GENERATION_OPTIONS.map((option) => (
                      <button
                        key={option.id}
                        onClick={() => setStoryboardGenerationMode(option.id)}
                        className={`p-3 rounded-lg border text-left transition-all ${
                          storyboardGenerationMode === option.id
                            ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                            : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                        }`}
                      >
                        <div className="text-sm font-semibold">{option.label}</div>
                        <div className="text-[10px] text-zinc-500 mt-1">{option.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* TTS Provider */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                  <Volume2 size={14} /> TTS Provider
                </label>
                <div className="grid sm:grid-cols-3 gap-2">
                  {TTS_PROVIDER_OPTIONS.map((option) => (
                    <button
                      key={option.id}
                      onClick={() => setTtsProvider(option.id)}
                      className={`p-3 rounded-lg border text-left transition-all ${
                        ttsProvider === option.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <div className="text-sm font-semibold">{option.label}</div>
                      <div className="text-[10px] text-zinc-500 mt-1">{option.desc}</div>
                    </button>
                  ))}
                </div>
                {ttsProvider === 'auto' && (
                  <p className="text-[10px] text-zinc-500 mt-2">
                    Tries ElevenLabs first. If a library voice requires a paid plan or fails, generation continues with fal MiniMax.
                  </p>
                )}
                {ttsProvider === 'fal_minimax' && (
                  <p className="text-[10px] text-zinc-500 mt-2">
                    Uses fal.ai balance for voiceover. ElevenLabs key is not required in this mode.
                  </p>
                )}
              </div>

              {(ttsProvider === 'auto' || ttsProvider === 'fal_minimax') && (
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">
                    fal MiniMax fallback voice
                  </label>
                  <OptionPicker
                    value={minimaxVoice}
                    onChange={setMinimaxVoice}
                    options={(MINIMAX_VOICE_OPTIONS[language] || MINIMAX_VOICE_OPTIONS.en).map((voice) => ({
                      value: voice.id,
                      label: `${voice.name} - ${voice.desc}`,
                      name: voice.name,
                      desc: voice.desc,
                    }))}
                    renderOption={(option) => (
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold truncate">{option.name}</div>
                          <div className="text-[10px] text-zinc-500 truncate">{option.desc}</div>
                        </div>
                        {option.value === minimaxVoice && <Check size={14} className="text-violet-300 shrink-0" />}
                      </div>
                    )}
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">
                    Used immediately in fal MiniMax mode, or only if ElevenLabs fails in Auto fallback mode.
                  </p>
                </div>
              )}

              {/* Настройки аватара: пол, озвучка, загрузка — спрятаны в модалку,
                  чтобы блок выбора аватара оставался чистым (только сетка + кнопка). */}
              {avatarSettingsOpen && (
                <div
                  className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
                  onClick={() => setAvatarSettingsOpen(false)}
                >
                  <div
                    className="glass-panel max-h-[85vh] w-full max-w-lg space-y-5 overflow-y-auto p-5 custom-scrollbar"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <div className="flex items-center justify-between">
                      <h3 className="flex items-center gap-2 text-base font-semibold text-zinc-100">
                        <Settings2 size={15} /> Настройки аватара
                      </h3>
                      <button
                        type="button"
                        onClick={() => setAvatarSettingsOpen(false)}
                        className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-white/10 hover:text-zinc-200"
                        aria-label="Закрыть"
                      >
                        <X size={16} />
                      </button>
                    </div>

                    {/* Пол актёра */}
                    <div>
                      <label className="mb-2 block text-sm font-medium text-zinc-300">Пол актёра</label>
                      <div className="flex items-center gap-3">
                        <div className="flex gap-1 rounded-lg bg-white/5 p-1">
                          {[
                            { id: 'female', label: '👩 Женщина' },
                            { id: 'male', label: '👨 Мужчина' },
                          ].map((g) => (
                            <button
                              key={g.id}
                              type="button"
                              onClick={() => setActorGender(g.id)}
                              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                                actorGender === g.id
                                  ? 'bg-violet-500/25 text-violet-200'
                                  : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-200'
                              }`}
                            >
                              {g.label}
                            </button>
                          ))}
                        </div>
                        <span className="text-[10px] text-zinc-600">влияет на голос по умолчанию и генерацию аватара</span>
                      </div>
                    </div>

                    {/* Загрузить свой аватар */}
                    <div>
                      <label className="mb-2 block text-sm font-medium text-zinc-300">Загрузить свой аватар</label>
                      <div className="flex items-center gap-3">
                        <label className="flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-white/20 bg-white/5 px-4 py-3 text-sm text-zinc-400 transition-colors hover:border-white/30 hover:bg-white/10">
                          <Upload size={14} />
                          <span>Загрузить и сохранить аватар</span>
                          <input
                            type="file"
                            accept="image/*"
                            className="hidden"
                            onChange={async (e) => {
                              const file = e.target.files?.[0];
                              await handleActorUpload(file);
                              e.target.value = '';
                            }}
                          />
                        </label>
                        {uploadedActorPreview && (
                          <button
                            type="button"
                            onClick={() => {
                              if (uploadedActorPreview.serverUrl) {
                                setSelectedActor(uploadedActorPreview.serverUrl);
                              }
                            }}
                            className={`relative h-20 w-16 flex-shrink-0 overflow-hidden rounded-lg border-2 transition-all ${
                              selectedActor === uploadedActorPreview.serverUrl
                                ? 'border-violet-500 ring-2 ring-violet-500/30'
                                : 'border-white/20 hover:border-white/40'
                            }`}
                          >
                            <img src={uploadedActorPreview.localPreview} alt="Uploaded" className="h-full w-full object-cover" />
                            {selectedActor === uploadedActorPreview.serverUrl && (
                              <div className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-violet-500">
                                <Check size={8} className="text-white" />
                              </div>
                            )}
                            {!uploadedActorPreview.serverUrl && (
                              <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                                <Loader2 size={12} className="animate-spin text-white" />
                              </div>
                            )}
                          </button>
                        )}
                      </div>
                      {actorUploadStatus && (
                        <p className={`mt-2 text-[10px] ${actorUploadStatus.toLowerCase().includes('fail') ? 'text-red-300' : 'text-zinc-500'}`}>
                          {actorUploadStatus}
                        </p>
                      )}
                    </div>

                    {/* Voice Selection */}
                    {ttsProvider !== 'fal_minimax' && (() => {
                const boundVoice = actorGallery.find((a) => a.url === selectedActor)?.voice;
                return (
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                    <Volume2 size={14} /> Голос озвучки {language === 'es' ? '(испанский)' : language === 'ru' ? '(русский)' : '(английский)'}
                  </label>
                  {boundVoice?.voice_id ? (
                    // Голос привязан к аватару — бэкенд использует именно его,
                    // поэтому ручной выбор здесь скрыт, чтобы не вводить в заблуждение.
                    <div className="mb-2 flex items-start gap-2 rounded-lg border border-violet-400/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-200">
                      <Volume2 size={12} className="mt-0.5 shrink-0" />
                      <span>Аватар привязан к голосу <b>{boundVoice.voice_name || boundVoice.voice_id}</b> — он и будет использован для ролика. Сменить можно во вкладке «Аватары».</span>
                    </div>
                  ) : (
                  <>
                {(() => {
                  // Filter voices by language/accent
                  const filtered = voices.length > 0
                    ? voices.filter((v) => {
                        return voiceVisibleForLanguage(v, language, actorGender);
                      })
                      .sort((a, b) => voiceLanguageScore(a, language) - voiceLanguageScore(b, language))
                    : [];
                  const hasLanguageVoice = filtered.some((v) => voiceLanguageScore(v, language) === 0);

                  if (filtered.length > 0) {
                    return (
                      <div className="space-y-1.5 max-h-48 overflow-y-auto custom-scrollbar">
                        {filtered.map((v) => (
                          <div
                            key={v.voice_id}
                            role="button"
                            tabIndex={0}
                            onClick={() => setSelectedVoice(v.voice_id)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                setSelectedVoice(v.voice_id);
                              }
                            }}
                            className={`w-full flex items-center gap-3 p-2.5 rounded-lg border text-left transition-all ${
                              selectedVoice === v.voice_id
                                ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                                : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                            }`}
                          >
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium truncate">{v.name}</div>
                              <div className="text-[10px] text-zinc-500">
                                {[voiceLanguageSummary(v), v.labels?.accent, v.labels?.gender, v.category].filter(Boolean).join(' · ')}
                              </div>
                              {language === 'ru' && (
                                <span className={`inline-flex mt-1 text-[9px] font-semibold px-1.5 py-0.5 rounded-full ${
                                  voiceLanguageScore(v, language) === 0
                                    ? 'bg-green-500/15 text-green-300'
                                    : 'bg-amber-500/15 text-amber-300'
                                }`}>
                                  {voiceFitLabel(v, language)}
                                </span>
                              )}
                            </div>
                            {v.preview_url && (
                              <button
                                onClick={(e) => { e.stopPropagation(); new Audio(v.preview_url).play(); }}
                                className="shrink-0 w-7 h-7 rounded-full bg-white/10 hover:bg-violet-500/30 flex items-center justify-center transition-colors"
                                title="Preview voice"
                              >
                                <Volume2 size={12} />
                              </button>
                            )}
                            {selectedVoice === v.voice_id && <Check size={14} className="text-violet-400 shrink-0" />}
                          </div>
                        ))}
                        {language === 'ru' && !hasLanguageVoice && (
                          <p className="text-[10px] text-amber-400/80 pt-1">
                            No Russian-accent ElevenLabs voice found. Add or select a Russian voice for natural Russian speech.
                          </p>
                        )}
                      </div>
                    );
                  }

                  // Fallback defaults by gender + language
                  const defaults = {
                    'en-female': [
                      { id: '21m00Tcm4TlvDq8ikWAM', name: 'Rachel (calm)' },
                      { id: 'EXAVITQu4vr4xnSDxMaL', name: 'Bella (soft)' },
                    ],
                    'en-male': [
                      { id: '29vD33N1CtxCmqQRPOHJ', name: 'Drew (confident)' },
                      { id: 'TxGEqnHWrfWFTfGW9XjX', name: 'Josh (deep)' },
                      { id: 'yoZ06aMxZJJ28mfd3POQ', name: 'Sam (raspy)' },
                    ],
                    'es-female': [
                      { id: 'EXAVITQu4vr4xnSDxMaL', name: 'Bella (suave)' },
                      { id: '21m00Tcm4TlvDq8ikWAM', name: 'Rachel (calmada)' },
                    ],
                    'es-male': [
                      { id: 'ErXwobaYiN019PkySvjV', name: 'Antoni (cálido)' },
                      { id: '29vD33N1CtxCmqQRPOHJ', name: 'Drew (confiado)' },
                    ],
                  };
                  defaults['ru-female'] = [
                    { id: '21m00Tcm4TlvDq8ikWAM', name: 'Rachel (multilingual fallback)' },
                    { id: 'EXAVITQu4vr4xnSDxMaL', name: 'Bella (multilingual fallback)' },
                  ];
                  defaults['ru-male'] = [
                    { id: '29vD33N1CtxCmqQRPOHJ', name: 'Drew (multilingual fallback)' },
                    { id: 'ErXwobaYiN019PkySvjV', name: 'Antoni (multilingual fallback)' },
                  ];
                  const key = `${language}-${actorGender}`;
                  const opts = defaults[key] || defaults['en-female'];
                  return (
                    <OptionPicker
                      value={selectedVoice}
                      onChange={setSelectedVoice}
                      options={opts.map((o) => ({ value: o.id, label: o.name }))}
                    />
                  );
                })()}
                {(() => {
                  if (language !== 'ru' || !selectedVoice) return null;
                  const selectedVoiceMeta = voices.find((v) => v.voice_id === selectedVoice);

                  if (!selectedVoiceMeta) {
                    return (
                      <div className="mt-2 p-2.5 rounded-lg border border-amber-500/20 bg-amber-500/10 text-[11px] text-amber-200">
                        Custom voice ID selected. Make sure this ElevenLabs voice is Russian or Russian-accented before generating.
                      </div>
                    );
                  }

                  const selectedScore = voiceLanguageScore(selectedVoiceMeta, language);
                  if (selectedScore === 0) {
                    return (
                      <div className="mt-2 p-2.5 rounded-lg border border-green-500/20 bg-green-500/10 text-[11px] text-green-200">
                        Selected voice looks Russian-compatible.
                      </div>
                    );
                  }

                  return (
                    <div className="mt-2 p-2.5 rounded-lg border border-amber-500/20 bg-amber-500/10 text-[11px] text-amber-200">
                      Selected voice looks non-Russian ({selectedVoiceMeta.labels?.accent || 'unknown accent'}). For natural Russian speech, paste a Russian ElevenLabs voice ID below or add a Russian voice in ElevenLabs.
                    </div>
                  );
                })()}
                <div className="mt-3">
                  <label className="block text-[11px] font-medium text-zinc-400 mb-1">
                    Custom ElevenLabs voice ID
                  </label>
                  <input
                    value={selectedVoice}
                    onChange={(e) => setSelectedVoice(e.target.value.trim())}
                    className="input-field text-xs font-mono"
                    placeholder="Paste Russian voice_id from ElevenLabs..."
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">
                    Use this if your Russian voice exists in ElevenLabs but does not appear in the filtered list.
                  </p>
                </div>
                <p className="text-[10px] text-zinc-600 mt-1">
                  {language === 'es'
                    ? `Voces ${actorGender === 'female' ? 'femeninas' : 'masculinas'} · Todas hablan español con modelo multilingual · Click altavoz para preview`
                    : `${actorGender === 'female' ? 'Female' : 'Male'} voices · Click speaker to preview`}
                </p>
                  </>
                  )}
                </div>
                );
              })()}

                    <button
                      type="button"
                      onClick={() => setAvatarSettingsOpen(false)}
                      className="btn-primary w-full py-2.5 text-sm"
                    >
                      Готово
                    </button>
                  </div>
                </div>
              )}

              {/* B-roll Mode */}
              {!storyboardSelected && (
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                  <Film size={14} /> Что показывать, пока идёт речь
                </label>
                <div className="grid sm:grid-cols-3 gap-2">
                  {BROLL_MODE_OPTIONS.map((option) => (
                    <button
                      key={option.id}
                      onClick={() => setBrollMode(option.id)}
                      className={`p-3 rounded-lg border text-left transition-all ${
                        brollMode === option.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <div className="text-sm font-semibold">{option.label}</div>
                      <div className="text-[10px] text-zinc-500 mt-1">{option.desc}</div>
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-zinc-600 mt-2">
                  По умолчанию — кадры с товаром: яркие «киношные» сцены от нейросети часто наоборот снижают доверие к ролику.
                </p>
              </div>
              )}

              {/* Talking-head source */}
              {!storyboardSelected && (
              <div className="p-4 rounded-xl border border-white/10 bg-white/5 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 flex items-center gap-2">
                      <User size={14} /> Кто говорит в кадре
                    </label>
                    <p className="text-xs text-zinc-500 mt-1">
                      Один раз сгенерировать говорящего человека — это дорого. Зато потом можно сохранить его и менять только озвучку — это уже дёшево.
                    </p>
                  </div>
                  {loadingHeadTemplates && <Loader2 size={14} className="animate-spin text-zinc-500 shrink-0" />}
                </div>

                <div className="grid sm:grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedHeadTemplate('')}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      !selectedHeadTemplate
                        ? 'border-primary/50 bg-primary/10 text-violet-200'
                        : 'border-white/10 bg-black/20 text-zinc-400 hover:bg-white/10'
                    }`}
                  >
                    <div className="text-sm font-semibold">Сгенерировать заново</div>
                    <div className="text-[10px] text-zinc-500 mt-1">Нейросеть создаст нового говорящего человека под эту озвучку.</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (headTemplates[0]) setSelectedHeadTemplate(headTemplates[0].template_id);
                    }}
                    disabled={headTemplates.length === 0}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      selectedHeadTemplate
                        ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                        : 'border-white/10 bg-black/20 text-zinc-400 hover:bg-white/10 disabled:opacity-40'
                    }`}
                  >
                    <div className="text-sm font-semibold">Взять сохранённого</div>
                    <div className="text-[10px] text-zinc-500 mt-1">
                      {headTemplates.length > 0 ? 'Дешевле: берём готового человека и только переозвучиваем.' : 'Сначала сохрани говорящего из готового ролика.'}
                    </div>
                  </button>
                </div>

                {headTemplates.length > 0 && (
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                    {headTemplates.map((tpl) => (
                      <button
                        key={tpl.template_id}
                        type="button"
                        onClick={() => setSelectedHeadTemplate(tpl.template_id)}
                        className={`overflow-hidden rounded-xl border text-left transition-all ${
                          selectedHeadTemplate === tpl.template_id
                            ? 'border-violet-500 ring-2 ring-violet-500/25 bg-violet-500/10'
                            : 'border-white/10 bg-black/20 hover:border-white/25'
                        }`}
                      >
                        <div className="aspect-[9/16] bg-black">
                          {tpl.poster_url ? (
                            <img src={tpl.poster_url} alt={tpl.label} className="h-full w-full object-cover" />
                          ) : (
                            <video src={tpl.video_url} muted playsInline preload="metadata" className="h-full w-full object-cover" />
                          )}
                        </div>
                        <div className="p-2">
                          <div className="text-[11px] font-semibold text-zinc-200 truncate">{tpl.label || 'Talking head'}</div>
                          <div className="text-[9px] text-zinc-500 truncate">{tpl.language || 'template'} · lipsync only</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {selectedHeadTemplate && (
                  <div className="rounded-lg border border-violet-500/20 bg-violet-500/10 p-3 space-y-2">
                    <p className="text-xs text-violet-200">
                      Выбран сохранённый talking-head. Аватар ниже не нужен: приложение возьмёт видео-шаблон и пересинхронизирует губы под текущую озвучку.
                    </p>
                    <OptionPicker
                      value={lipSyncModel}
                      onChange={setLipSyncModel}
                      options={LIPSYNC_MODEL_OPTIONS.map((option) => ({
                        value: option.id,
                        label: `${option.label} - $${option.pricePerMinute}/min`,
                        ...option,
                      }))}
                    />
                  </div>
                )}
              </div>
              )}

              {/* Actor Selection: Gallery + Generate New */}
              <div className={selectedHeadTemplate ? 'opacity-50 pointer-events-none' : ''}>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <label className="flex items-center gap-2 text-sm font-medium text-zinc-300">
                    <User size={14} /> Аватар проекта {storyboardSelected && <span className="text-zinc-600">(необязательно)</span>}
                  </label>
                  <button
                    type="button"
                    onClick={() => setAvatarSettingsOpen(true)}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-zinc-300 transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-violet-200"
                  >
                    <Settings2 size={13} /> Настройки аватара
                  </button>
                </div>
                <p className="text-xs text-zinc-500 mb-3">
                  Аватар задаёт лицо говорящего в кадре — оно берётся из фото, а не из текста.
                  Без выбранного аватара система придумает случайного человека, и в каждом ролике он будет
                  разным. Для постоянного персонажа проекта выбери или загрузи аватар. Пол, озвучку и
                  загрузку фото настрой в «Настройках аватара».
                </p>

                <div className="space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-semibold text-zinc-300">Сохранённые аватары ({actorGallery.length})</p>
                      {selectedActor && (
                        <button
                          type="button"
                          onClick={() => setSelectedActor(null)}
                          className="text-[11px] text-zinc-500 hover:text-zinc-200"
                        >
                          Сбросить выбор
                        </button>
                      )}
                    </div>
                    {loadingGallery ? (
                      <p className="text-xs text-zinc-500 flex items-center gap-1">
                        <Loader2 size={12} className="animate-spin" /> Загружаю сохранённые аватары...
                      </p>
                    ) : actorGallery.length > 0 ? (
                      <div className="grid grid-cols-4 sm:grid-cols-6 gap-2 max-h-56 overflow-y-auto pr-1 custom-scrollbar">
                        {actorGallery.map((img, i) => (
                          <button
                            key={img.url}
                            type="button"
                            onClick={() => {
                              setSelectedActor(img.url);
                              // Avatar carries its own bound voice — apply it.
                              if (img.voice?.voice_id) setSelectedVoice(img.voice.voice_id);
                            }}
                            className={`relative rounded-lg overflow-hidden border-2 transition-all aspect-[3/4] ${
                              selectedActor === img.url
                                ? 'border-violet-500 ring-2 ring-violet-500/30 scale-[1.02]'
                                : 'border-white/10 hover:border-white/30'
                            }`}
                            title={
                              img.voice?.voice_name
                                ? `${img.description || `Аватар ${i + 1}`} · голос: ${img.voice.voice_name}`
                                : (img.description || `Аватар ${i + 1}`)
                            }
                          >
                            <img src={img.url} alt={`Actor ${i + 1}`} className="w-full h-full object-cover" />
                            {img.voice?.voice_id && (
                              <span className="absolute bottom-0 inset-x-0 flex items-center justify-center gap-0.5 bg-violet-600/80 py-0.5 text-[8px] font-semibold text-white">
                                <Volume2 size={8} />голос
                              </span>
                            )}
                            {selectedActor === img.url && (
                              <div className="absolute top-1 right-1 w-5 h-5 bg-violet-500 rounded-full flex items-center justify-center shadow-lg">
                                <Check size={10} className="text-white" />
                              </div>
                            )}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="p-3 rounded-xl border border-dashed border-white/15 bg-white/5 text-xs text-zinc-500">
                        В галерее пока нет аватаров. Открой «Настройки аватара», чтобы загрузить своё фото.
                      </div>
                    )}
                  </div>

                {!selectedActor && (
                  <p className="text-xs text-amber-400 mt-3 flex items-center gap-1">
                    <AlertCircle size={12} /> Выбери или загрузи аватара, чтобы продолжить
                  </p>
                )}
              </div>

              {false && (
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                  <User size={14} /> AI Actor — Choose Your Actor
                </label>

                {/* Existing Gallery from S3 */}
                {actorGallery.length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs text-zinc-400 mb-2">Previously generated actors (click to select):</p>
                    <div className="grid grid-cols-4 sm:grid-cols-6 gap-2 max-h-48 overflow-y-auto pr-1">
                      {actorGallery.map((img, i) => (
                        <button
                          key={img.url}
                          onClick={() => setSelectedActor(img.url)}
                          className={`relative rounded-lg overflow-hidden border-2 transition-all aspect-[3/4] ${
                            selectedActor === img.url ? 'border-violet-500 ring-2 ring-violet-500/30 scale-[1.02]' : 'border-white/10 hover:border-white/30'
                          }`}
                        >
                          <img src={img.url} alt={`Actor ${i+1}`} className="w-full h-full object-cover" />
                          {selectedActor === img.url && (
                            <div className="absolute top-1 right-1 w-5 h-5 bg-violet-500 rounded-full flex items-center justify-center shadow-lg">
                              <Check size={10} className="text-white" />
                            </div>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {loadingGallery && (
                  <p className="text-xs text-zinc-500 mb-3 flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Loading actor gallery...</p>
                )}

                {/* Upload Custom Actor */}
                <div className="mb-4">
                  <div className="flex items-center gap-3">
                    <label className="flex-1 flex items-center justify-center gap-2 text-sm bg-white/5 text-zinc-400 px-4 py-3 rounded-lg border border-dashed border-white/20 hover:bg-white/10 hover:border-white/30 transition-colors cursor-pointer">
                      <Upload size={14} />
                      <span>Upload your own photo</span>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={async (e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          // Show instant preview
                          const localPreview = URL.createObjectURL(file);
                          setUploadedActorPreview({ localPreview, serverUrl: null });
                          setSelectedActor(null);

                          const formData = new FormData();
                          formData.append('file', file);
                          try {
                            const res = await fetch(getApiUrl('/api/saasshorts/actor-upload'), {
                              method: 'POST',
                              body: formData,
                            });
                            if (res.ok) {
                              const data = await res.json();
                              if (data.url) {
                                setUploadedActorPreview({ localPreview, serverUrl: data.url });
                                setSelectedActor(data.url);
                              }
                            }
                          } catch (err) { console.error('Upload failed:', err); }
                          e.target.value = '';
                        }}
                      />
                    </label>
                    {uploadedActorPreview && (
                      <button
                        onClick={() => {
                          if (uploadedActorPreview.serverUrl) {
                            setSelectedActor(uploadedActorPreview.serverUrl);
                          }
                        }}
                        className={`relative w-16 h-20 rounded-lg overflow-hidden border-2 transition-all flex-shrink-0 ${
                          selectedActor === uploadedActorPreview.serverUrl
                            ? 'border-violet-500 ring-2 ring-violet-500/30'
                            : 'border-white/20 hover:border-white/40'
                        }`}
                      >
                        <img src={uploadedActorPreview.localPreview} alt="Uploaded" className="w-full h-full object-cover" />
                        {selectedActor === uploadedActorPreview.serverUrl && (
                          <div className="absolute top-1 right-1 w-4 h-4 bg-violet-500 rounded-full flex items-center justify-center">
                            <Check size={8} className="text-white" />
                          </div>
                        )}
                        {!uploadedActorPreview.serverUrl && (
                          <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                            <Loader2 size={12} className="animate-spin text-white" />
                          </div>
                        )}
                      </button>
                    )}
                  </div>
                </div>

                {/* Generate New Actors */}
                <p className="text-xs text-zinc-500 mb-2">{actorGallery.length > 0 ? 'Or generate new actors:' : 'Or describe your actor:'}</p>
                <textarea
                  value={actorDescription}
                  onChange={(e) => { setActorDescription(e.target.value); setActorOptions([]); }}
                  rows={2}
                  className="input-field resize-none text-sm"
                  placeholder="e.g. A young woman in her late 20s, dark hair, casual outfit..."
                />


                <button
                  onClick={async () => {
                    if (!falKey || !actorDescription) return;
                    setGeneratingActors(true);
                    setActorOptions([]);
                    setSelectedActor(null);
                    try {
                      const res = await fetch(getApiUrl('/api/saasshorts/actor-options'), {
                        method: 'POST',
                        headers: {
                          'Content-Type': 'application/json',
                          ...authHeaders(),
                          ...(falKey && !isManagedKey(falKey) ? { 'X-Fal-Key': falKey } : {}),
                        },
                        body: JSON.stringify({
                          actor_description: actorDescription,
                          num_options: 3,
                          use_platform_keys: usePlatformKeys,
                        }),
                      });
                      if (res.ok) {
                        const data = await res.json();
                        setActorOptions(data.images || []);
                        // Refresh gallery to include newly uploaded actors
                        const galRes = await fetch(getApiUrl('/api/saasshorts/actor-gallery'), { headers: authHeaders() });
                        if (galRes.ok) {
                          const galData = await galRes.json();
                          setActorGallery(galData.images || []);
                        }
                      }
                    } catch (e) { console.error(e); }
                    finally { setGeneratingActors(false); }
                  }}
                  disabled={generatingActors || !falKey || !actorDescription}
                  className="mt-2 w-full text-sm bg-violet-500/20 text-violet-300 px-4 py-2.5 rounded-lg hover:bg-violet-500/30 transition-colors disabled:opacity-40 flex items-center justify-center gap-2 font-medium"
                >
                  {generatingActors ? <><Loader2 size={14} className="animate-spin" /> Generating 3 actors...</> : <><User size={14} /> {actorOptions.length > 0 ? 'Regenerate Actors' : 'Generate 3 New Actors'} (~$0.06)</>}
                </button>

                {/* Newly Generated Actor Options */}
                {actorOptions.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs text-zinc-400 mb-2">New actors (select one):</p>
                    <div className="grid grid-cols-3 gap-3">
                      {actorOptions.map((imgUrl, i) => (
                        <button
                          key={imgUrl}
                          onClick={() => setSelectedActor(imgUrl)}
                          className={`relative rounded-xl overflow-hidden border-2 transition-all aspect-[9/16] ${
                            selectedActor === imgUrl ? 'border-violet-500 ring-2 ring-violet-500/30 scale-[1.02]' : 'border-white/10 hover:border-white/30'
                          }`}
                        >
                          <img src={imgUrl} alt={`New ${i+1}`} className="w-full h-full object-cover" />
                          {selectedActor === imgUrl && (
                            <div className="absolute top-2 right-2 w-6 h-6 bg-violet-500 rounded-full flex items-center justify-center shadow-lg">
                              <Check size={12} className="text-white" />
                            </div>
                          )}
                          <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/60 to-transparent p-2">
                            <span className="text-[10px] text-white/80">New {i+1}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {!storyboardSelected && !selectedActor && (actorOptions.length > 0 || actorGallery.length > 0) && (
                  <p className="text-xs text-amber-400 mt-2 flex items-center gap-1"><AlertCircle size={12} /> Select an actor to continue</p>
                )}
              </div>

              )}

              {/* Narration Edit — только для UGC. В раскадровке озвучка
                  собирается из речи кадров (saasshorts.py: full_narration от shots),
                  поэтому отдельное поле пряталось бы за источник правды и молча
                  теряло текст, которого нет ни в одном кадре. */}
              {!storyboardSelected && (
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                    <MessageSquare size={14} /> Текст озвучки
                  </label>
                  <textarea
                    value={editedNarration}
                    onChange={(e) => setEditedNarration(e.target.value)}
                    rows={5}
                    className="input-field resize-none font-mono text-xs"
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">{editedNarration.length} chars &middot; ~{estimateSpeechSeconds(editedNarration)}s speech</p>
                </div>
              )}

              {/* Cost Estimate */}
              {(() => {
                const estimate = estimateSaasVideoCost({
                  text: editedNarration,
                  videoMode,
                  ttsProvider,
                  brollMode,
                  hasSelectedActor: Boolean(selectedActor),
                  hasReusableHead: Boolean(selectedHeadTemplate),
                  lipsyncModel: lipSyncModel,
                  script: scripts[selectedScript],
                  storyboardGenerationMode,
                });
                const costDetails =
                  selectedHeadTemplate
                    ? 'Сохранённый talking-head + новая озвучка + Sync Lipsync. Быстрее, чем заново генерировать Kling/Hailuo.'
                    : videoMode === 'storyboard_v3_standard'
                    ? (storyboardGenerationMode === 'sliced_avatar'
                        ? 'Озвучка ElevenLabs. Говорящие кадры — Kling Avatar (липсинк), b-roll — Kling V3; под каждый кадр ещё Flux-кадр.'
                        : 'Озвучка ElevenLabs + видео Kling V3: кадры генерятся отдельно, липсинк не гарантирован.')
                    : videoMode === 'storyboard_v3_pro'
                    ? 'Озвучка ElevenLabs + видео Kling V3 Pro: выше детализация лиц и движений, тариф выше.'
                    : videoMode === 'storyboard_veo31_quality'
                    ? 'Озвучка ElevenLabs + видео Google Veo 3.1 — самая качественная и самая дорогая картинка.'
                    : videoMode === 'lowcost'
                    ? 'Озвучка + Hailuo 2.3 + VEED Lipsync. Дешёвый черновик: качество может плыть.'
                    : videoMode === 'premium'
                      ? 'Озвучка + Kling Avatar v2 Pro: чётче лицо и движения, тариф примерно вдвое выше.'
                      : 'Озвучка + Kling Avatar v2 Standard. Основной режим: хорошее качество по разумной цене.';

                return (
                  <div className="max-w-2xl p-4 bg-white/5 rounded-xl border border-white/10">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-sm font-semibold text-zinc-300">Примерная стоимость</div>
                        <div className="text-[11px] text-zinc-600 mt-1">{costDetails}</div>
                      </div>
                      <span className="text-lg text-green-400 font-semibold whitespace-nowrap">{formatUsd(estimate.total)}</span>
                    </div>

                    <div className="mt-4 space-y-2 text-sm">
                      {[
                        ['Длительность', `~${estimate.seconds} сек`],
                        ['Озвучка', formatUsd(estimate.voiceCost)],
                        ['Видео', formatUsd(estimate.videoCost)],
                        ['Аватар', formatUsd(estimate.actorCost)],
                        ['B-roll', formatUsd(estimate.brollCost)],
                      ].map(([label, value]) => (
                        <div key={label} className="flex items-center justify-between gap-4 border-t border-white/5 pt-2 first:border-t-0 first:pt-0">
                          <span className="text-zinc-500">{label}</span>
                          <span className="font-mono text-zinc-300">{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Missing keys warning */}
              {(!falKey || (ttsProvider === 'elevenlabs' && !elevenLabsKey)) && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg flex items-center gap-2 text-sm text-amber-400">
                  <AlertCircle size={14} />
                  {!falKey && 'fal.ai API key missing. '}{ttsProvider === 'elevenlabs' && !elevenLabsKey && 'ElevenLabs API key missing. '}
                  Set them in Settings.
                </div>
              )}
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep(1)} className="btn-secondary px-4 py-2 text-sm flex items-center gap-2">
                <ChevronLeft size={14} /> Назад
              </button>
              <button
                onClick={handleGenerate}
                disabled={!falKey || (ttsProvider === 'elevenlabs' && !elevenLabsKey) || (!storyboardSelected && !selectedActor && !selectedHeadTemplate) || generating}
                className="btn-primary px-6 py-2 text-sm flex items-center gap-2 disabled:opacity-50"
              >
                {generating ? (
                  <><Loader2 size={14} className="animate-spin" /> Генерирую...</>
                ) : (!storyboardSelected && !selectedActor && !selectedHeadTemplate) ? (
                  <><User size={14} /> Сначала выбери актёра</>
                ) : storyboardSelected ? (
                  <><Film size={14} /> Сгенерировать видео ({formatUsd(estimateSaasVideoCost({ text: editedNarration, videoMode, ttsProvider, brollMode, hasSelectedActor: Boolean(selectedActor), hasReusableHead: false, lipsyncModel: lipSyncModel, script: scripts[selectedScript], storyboardGenerationMode }).total)})</>
                ) : selectedHeadTemplate ? (
                  <><Volume2 size={14} /> Видео из сохранённой головы ({formatUsd(estimateSaasVideoCost({ text: editedNarration, videoMode, ttsProvider, brollMode, hasSelectedActor: Boolean(selectedActor), hasReusableHead: true, lipsyncModel: lipSyncModel, script: scripts[selectedScript], storyboardGenerationMode }).total)})</>
                ) : (
                  <><Film size={14} /> Собрать ролик ({formatUsd(estimateSaasVideoCost({ text: editedNarration, videoMode, ttsProvider, brollMode, hasSelectedActor: Boolean(selectedActor), hasReusableHead: false, lipsyncModel: lipSyncModel, script: scripts[selectedScript] }).total)})</>
                )}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Generation Progress ──────────────────────── */}
        {step === 3 && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-6">
            <div className="glass-panel p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Film size={18} className={genStatus === 'processing' ? 'text-violet-400 animate-pulse' : genStatus === 'completed' ? 'text-green-400' : 'text-red-400'} />
                  Video Generation
                </h2>
                <span className={`text-xs px-2 py-1 rounded-full border ${
                  genStatus === 'processing' ? 'bg-violet-500/10 border-violet-500/20 text-violet-300' :
                  genStatus === 'completed' ? 'bg-green-500/10 border-green-500/20 text-green-400' :
                  'bg-red-500/10 border-red-500/20 text-red-400'
                }`}>
                  {genStatus.toUpperCase()}
                </span>
              </div>

              {/* Progress steps */}
              <div className="space-y-2 mb-4">
                {(() => {
                  const logStr = genLogs.join(' ').toLowerCase();
                  const isLipSyncJob = logStr.includes('lip-sync') || logStr.includes('lipsync');
                  const isStoryboardJob = logStr.includes('storyboard') || logStr.includes('kling v3');
                  const noBroll = !isLipSyncJob && brollMode === 'off';
                  const labels = isStoryboardJob
                    ? [
                      'Generating Russian voiceover',
                      'Generating Kling V3 shots',
                      'Adding subtitles',
                      'Assembling storyboard edit',
                    ]
                    : isLipSyncJob
                    ? [
                      'Finding cached head + voiceover',
                      'Running lip-sync model',
                      'Re-compositing final video',
                      'Saving updated result',
                    ]
                    : [
                      'Generating actor image + voiceover',
                      'Creating talking head video (2-5 min)',
                      ...(noBroll ? [] : [
                        brollMode === 'mockup'
                          ? 'Preparing product mockup inserts'
                          : 'Generating b-roll clips',
                      ]),
                      'Adding subtitles + assembling final video',
                    ];

                  return labels.map((label, i) => {
                    const normalStepDone = () => {
                      if (i === 0) return logStr.includes('[2/6]') || logStr.includes('[3/6]');
                      if (i === 1) {
                        return logStr.includes('[4/6]') || logStr.includes('[5/6]') || logStr.includes('[6/6]') || logStr.includes('talking head ready') || genStatus === 'completed';
                      }
                      if (noBroll) return genStatus === 'completed';
                      if (i === 2) return logStr.includes('[5/6]') || logStr.includes('[6/6]') || genStatus === 'completed';
                      return genStatus === 'completed';
                    };
                    const normalStepActive = () => {
                      if (i === 0) return logStr.includes('[1/6]') && !normalStepDone();
                      if (i === 1) return logStr.includes('[3/6]') && !normalStepDone();
                      if (noBroll) {
                        return (logStr.includes('[4/6]') || logStr.includes('[5/6]') || logStr.includes('[6/6]')) && genStatus !== 'completed';
                      }
                      if (i === 2) return logStr.includes('[4/6]') && !logStr.includes('[5/6]') && !logStr.includes('[6/6]');
                      return (logStr.includes('[5/6]') || logStr.includes('[6/6]')) && genStatus !== 'completed';
                    };
                    const stepDone = isLipSyncJob
                      ? (
                        i === 0 ? logStr.includes('[lipsync 1/3]') || logStr.includes('[lipsync 2/3]') :
                        i === 1 ? logStr.includes('[lipsync 2/3]') || logStr.includes('[lipsync 3/3]') :
                        i === 2 ? logStr.includes('[lipsync 3/3]') || genStatus === 'completed' :
                        genStatus === 'completed'
                      )
                      : isStoryboardJob
                      ? (
                        i === 0 ? logStr.includes('[2/5]') || logStr.includes('[3/5]') :
                        i === 1 ? logStr.includes('[3/5]') || logStr.includes('[4/5]') || genStatus === 'completed' :
                        i === 2 ? logStr.includes('[4/5]') || genStatus === 'completed' :
                        genStatus === 'completed'
                      )
                      : normalStepDone();
                    const stepActive = isLipSyncJob
                      ? (
                        i === 0 ? logStr.includes('post-process started') && !stepDone :
                        i === 1 ? logStr.includes('[lipsync 1/3]') && !logStr.includes('[lipsync 2/3]') :
                        i === 2 ? logStr.includes('[lipsync 2/3]') && !logStr.includes('[lipsync 3/3]') :
                        logStr.includes('[lipsync 3/3]') && genStatus !== 'completed'
                      )
                      : isStoryboardJob
                      ? (
                        i === 0 ? logStr.includes('[1/5]') && !stepDone :
                        i === 1 ? logStr.includes('[2/5]') && !stepDone :
                        i === 2 ? logStr.includes('[3/5]') && !stepDone :
                        logStr.includes('[4/5]') && genStatus !== 'completed'
                      )
                      : normalStepActive();

                    return (
                      <div key={i} className="flex items-center gap-3 text-sm">
                        {stepDone ? (
                          <Check size={14} className="text-green-400" />
                        ) : stepActive ? (
                          <Loader2 size={14} className="text-violet-400 animate-spin" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-white/20" />
                        )}
                        <span className={stepDone ? 'text-zinc-400' : stepActive ? 'text-white' : 'text-zinc-600'}>
                          {label}
                        </span>
                      </div>
                    );
                  });
                })()}
              </div>

              {/* Logs Terminal */}
              <div className="bg-[#0c0c0e] rounded-xl border border-white/10 overflow-hidden">
                <div className="px-4 py-2 border-b border-white/5 flex items-center justify-between bg-white/5">
                  <span className="text-xs font-mono text-zinc-400 flex items-center gap-2">
                    <Terminal size={12} /> Generation Logs
                  </span>
                  <button onClick={() => setLogsExpanded(!logsExpanded)} className="text-zinc-500 hover:text-white transition-colors">
                    <ChevronDown size={14} className={logsExpanded ? '' : 'rotate-180'} />
                  </button>
                </div>
                {logsExpanded && (
                  <div className="p-4 max-h-64 overflow-y-auto font-mono text-xs space-y-1 custom-scrollbar">
                    {genLogs.map((log, i) => (
                      <div key={i} className={`${log.toLowerCase().includes('error') ? 'text-red-400' : log.includes('✅') ? 'text-green-400' : 'text-zinc-400'}`}>
                        {log}
                      </div>
                    ))}
                    {genStatus === 'processing' && (
                      <div className="animate-pulse text-violet-400/70">_</div>
                    )}
                  </div>
                )}
              </div>

              {/* Retry button when failed */}
              {genStatus === 'failed' && (
                <div className="mt-4 p-4 bg-red-500/5 border border-red-500/20 rounded-xl space-y-3">
                  <div className="flex items-center gap-2">
                    <AlertCircle size={16} className="text-red-400 shrink-0" />
                    <span className="text-sm text-red-300">Generation failed. You can retry or go back to change settings.</span>
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={() => { setStep(2); setGenStatus('idle'); setGenerating(false); }}
                      className="btn-secondary px-4 py-2 text-sm flex items-center gap-2"
                    >
                      <ChevronLeft size={14} /> Change Voice/Settings
                    </button>
                    <button
                      onClick={handleRetry}
                      disabled={generating}
                      className="btn-primary px-4 py-2 text-sm flex items-center gap-2"
                    >
                      <RefreshCw size={14} /> Retry
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Step 4: Results ──────────────────────────────────── */}
        {step === 4 && genResult && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-6">
            <div className="glass-panel p-6">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Sparkles className="text-yellow-400" size={18} />
                Your AI Short is Ready!
              </h2>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Video Player */}
                <div className="aspect-[9/16] max-h-[500px] bg-black rounded-xl overflow-hidden relative">
                  <video
                    src={getApiUrl(genResult.video_url)}
                    controls
                    className="w-full h-full object-contain"
                    autoPlay
                  />
                </div>

                {/* Details */}
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-zinc-300 mb-1">{genResult.script?.title}</h3>
                    <p className="text-xs text-zinc-500">{genResult.duration?.toFixed(1)}s &middot; 9:16 vertical</p>
                  </div>

                  {genResult.quality_warnings?.length > 0 && (
                    <div className="p-3 bg-amber-500/10 rounded-lg border border-amber-500/25 space-y-2">
                      <div className="flex items-center gap-2 text-xs font-semibold text-amber-200">
                        <AlertCircle size={14} />
                        Проверь синхронизацию talking-head
                      </div>
                      <div className="space-y-1">
                        {genResult.quality_warnings.map((warning, i) => (
                          <p key={i} className="text-xs text-amber-100/80">{warning}</p>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Cost breakdown */}
                  {genResult.cost_estimate && (
                    <div className="p-3 bg-white/5 rounded-lg border border-white/10 space-y-1">
                      <div className="text-xs font-semibold text-zinc-300 mb-2">Cost Breakdown</div>
                      {Object.entries(genResult.cost_estimate).filter(([k]) => k !== 'total').map(([k, v]) => (
                        <div key={k} className="flex justify-between text-xs">
                          <span className="text-zinc-500">{k.replace(/_/g, ' ')}</span>
                          <span className="text-zinc-400">${v}</span>
                        </div>
                      ))}
                      <div className="flex justify-between text-sm font-semibold border-t border-white/10 pt-1 mt-1">
                        <span className="text-zinc-300">Total</span>
                        <span className="text-green-400">${genResult.cost_estimate.total}</span>
                      </div>
                    </div>
                  )}

                  {/* Caption */}
                  {genResult.script?.caption && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-zinc-400">Подпись под видео</span>
                        <button
                          onClick={() => handleCopy(genResult.script.caption, 'caption')}
                          className="text-xs text-zinc-500 hover:text-white flex items-center gap-1"
                        >
                          {copied === 'caption' ? <Check size={10} /> : <Copy size={10} />}
                          {copied === 'caption' ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                      <p className="text-xs text-zinc-400 bg-white/5 p-2 rounded-lg">{genResult.script.caption}</p>
                    </div>
                  )}

                  {/* Hashtags */}
                  {genResult.script?.hashtags && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-zinc-400">Hashtags</span>
                        <button
                          onClick={() => handleCopy(genResult.script.hashtags.join(' '), 'hashtags')}
                          className="text-xs text-zinc-500 hover:text-white flex items-center gap-1"
                        >
                          {copied === 'hashtags' ? <Check size={10} /> : <Copy size={10} />}
                          {copied === 'hashtags' ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {genResult.script.hashtags.map((tag, i) => (
                          <span key={i} className="text-[10px] bg-violet-500/10 text-violet-300 px-2 py-0.5 rounded-full">{tag}</span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-3 pt-2">
                    <a
                      href={getApiUrl(genResult.video_url)}
                      download
                      className="btn-primary px-4 py-2 text-sm flex items-center gap-2"
                    >
                      <Download size={14} /> Download
                    </a>
                    <button
                      onClick={handleReset}
                      className="btn-secondary px-4 py-2 text-sm flex items-center gap-2"
                    >
                      <RefreshCw size={14} /> New Video
                    </button>
                  </div>

                  <div className="p-4 bg-primary/5 rounded-xl border border-primary/20 space-y-2">
                    <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
                      <User size={14} /> Reuse this talking head
                    </h3>
                    <p className="text-xs text-zinc-500">
                      Save the cached talking-head source. Next time you can generate a new voiceover and only run lipsync against this head.
                    </p>
                    <button
                      type="button"
                      onClick={handleSaveHeadTemplate}
                      disabled={savingHeadTemplate || !jobId}
                      className="btn-secondary px-4 py-2 text-sm flex items-center gap-2 disabled:opacity-50"
                    >
                      {savingHeadTemplate ? (
                        <><Loader2 size={14} className="animate-spin" /> Saving...</>
                      ) : (
                        <><Check size={14} /> Save talking-head template</>
                      )}
                    </button>
                    {headTemplateStatus && (
                      <p className={`text-[11px] ${headTemplateStatus.toLowerCase().includes('не удалось') ? 'text-red-300' : 'text-violet-200'}`}>
                        {headTemplateStatus}
                      </p>
                    )}
                  </div>

                  {/* Standalone Lip-sync */}
                  <div className="p-4 bg-violet-500/5 rounded-xl border border-violet-500/20 space-y-3">
                    <div>
                      <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
                        <Volume2 size={14} /> Improve lip-sync
                      </h3>
                      <p className="text-xs text-zinc-500 mt-1">
                        Re-sync the current talking-head video to the saved voiceover, then rebuild the final edit.
                      </p>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3">
                      <OptionPicker
                        value={lipSyncModel}
                        onChange={setLipSyncModel}
                        disabled={lipSyncing || generating}
                        options={LIPSYNC_MODEL_OPTIONS.map((option) => ({
                          value: option.id,
                          label: `${option.label} - ${option.desc}`,
                          ...option,
                        }))}
                        renderOption={(option) => (
                          <div className="flex items-center justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-sm font-semibold truncate">{option.label}</div>
                              <div className="text-[10px] text-zinc-500 truncate">{option.desc}</div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <span className="text-[10px] text-zinc-500">${option.pricePerMinute}/min</span>
                              {option.value === lipSyncModel && <Check size={14} className="text-violet-300" />}
                            </div>
                          </div>
                        )}
                      />
                      <button
                        onClick={handleLipSync}
                        disabled={lipSyncing || generating || !jobId}
                        className="btn-secondary px-4 py-2 text-sm flex items-center justify-center gap-2 disabled:opacity-50"
                      >
                        {lipSyncing ? (
                          <><Loader2 size={14} className="animate-spin" /> Syncing...</>
                        ) : (
                          <><Volume2 size={14} /> Re-sync lips</>
                        )}
                      </button>
                    </div>
                    {genResult.lipsync_model && (
                      <p className="text-[11px] text-violet-300">
                        Last post-process: {genResult.lipsync_model} / {genResult.lipsync_sync_mode || 'cut_off'}
                      </p>
                    )}
                  </div>

                  {/* Publish to Social Media */}
                  <div className="p-4 bg-white/5 rounded-xl border border-white/10 space-y-3 mt-2">
                    <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
                      <Share2 size={14} /> Publish to Social Media
                    </h3>

                    {!uploadPostKey ? (
                      <p className="text-xs text-zinc-500">Set your Upload-Post API key in Settings to enable publishing.</p>
                    ) : (
                      <>
                        {/* Platform checkboxes */}
                        <div className="flex gap-4">
                          {[
                            { id: 'tiktok', label: 'TikTok', icon: '🎵' },
                            { id: 'instagram', label: 'Instagram', icon: '📸' },
                            { id: 'youtube', label: 'YouTube', icon: '▶️' },
                          ].map((p) => (
                            <label key={p.id} className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={publishPlatforms[p.id]}
                                onChange={(e) => setPublishPlatforms({ ...publishPlatforms, [p.id]: e.target.checked })}
                                className="w-3.5 h-3.5 rounded border-zinc-600 bg-black/50 text-violet-500 focus:ring-violet-500"
                              />
                              <span>{p.icon}</span> {p.label}
                            </label>
                          ))}
                        </div>

                        {/* Schedule toggle */}
                        <div className="flex items-center gap-3">
                          <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={isScheduling}
                              onChange={(e) => setIsScheduling(e.target.checked)}
                              className="w-3.5 h-3.5 rounded border-zinc-600 bg-black/50 text-violet-500 focus:ring-violet-500"
                            />
                            <Calendar size={12} /> Schedule
                          </label>
                          {isScheduling && (
                            <input
                              type="datetime-local"
                              value={scheduleDate}
                              onChange={(e) => setScheduleDate(e.target.value)}
                              className="input-field text-xs py-1 px-2 w-auto"
                            />
                          )}
                        </div>

                        {/* Publish button */}
                        <button
                          onClick={async () => {
                            const selected = Object.keys(publishPlatforms).filter(k => publishPlatforms[k]);
                            if (selected.length === 0) { setPublishResult({ ok: false, msg: 'Select at least one platform' }); return; }
                            if (isScheduling && !scheduleDate) { setPublishResult({ ok: false, msg: 'Select a date' }); return; }

                            setPublishing(true);
                            setPublishResult(null);
                            try {
                              const payload = {
                                job_id: jobId,
                                api_key: uploadPostKey,
                                user_id: uploadUserId,
                                platforms: selected,
                                title: genResult.script?.title,
                                description: genResult.script?.caption || genResult.script?.full_narration,
                                use_platform_keys: usePlatformKeys,
                              };
                              if (isScheduling && scheduleDate) {
                                payload.scheduled_date = new Date(scheduleDate).toISOString();
                                payload.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
                              }
                              const res = await fetch(getApiUrl('/api/saasshorts/post'), {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                                body: JSON.stringify(payload),
                              });
                              if (!res.ok) {
                                const err = await res.json().catch(() => ({ detail: 'Failed' }));
                                throw new Error(err.detail || 'Failed');
                              }
                              setPublishResult({ ok: true, msg: isScheduling ? 'Scheduled!' : 'Published!' });
                            } catch (e) {
                              setPublishResult({ ok: false, msg: e.message });
                            } finally {
                              setPublishing(false);
                            }
                          }}
                          disabled={publishing}
                          className="w-full btn-primary py-2 text-sm flex items-center justify-center gap-2 disabled:opacity-50"
                        >
                          {publishing ? (
                            <><Loader2 size={14} className="animate-spin" /> {isScheduling ? 'Scheduling...' : 'Publishing...'}</>
                          ) : (
                            <><Share2 size={14} /> {isScheduling ? 'Schedule Post' : 'Publish Now'}</>
                          )}
                        </button>

                        {publishResult && (
                          <p className={`text-xs ${publishResult.ok ? 'text-green-400' : 'text-red-400'}`}>
                            {publishResult.msg}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

import React, { useState, useEffect, useRef, useLayoutEffect } from 'react';
import { Globe, Sparkles, Download, Copy, Check, ChevronRight, ChevronLeft, Loader2, AlertCircle, Volume2, User, Film, Terminal, ChevronDown, ChevronUp, RefreshCw, Zap, Target, TrendingUp, MessageSquare, Eye, Share2, Calendar, Upload, Pencil, Save, Plus, Trash2, Undo2, GripVertical, Settings2 } from 'lucide-react';
import { getApiUrl } from '../config';
import FrameEditorBlockedModal from './FrameEditorBlockedModal';
import ImageLightbox from './ImageLightbox';
import {
  loadBusinessProfiles,
  saveBusinessProfiles,
  loadSelectedProfileId,
  saveSelectedProfileId,
  profileId as businessProfileKey,
  peekPendingTopic,
  clearPendingTopic,
  peekPendingContentPlanItem,
  clearPendingContentPlanItem,
} from '../lib/businessProfiles';
import {
  workspaceStorageKey,
  loadLocalWorkspace,
  saveLocalWorkspace,
  chooseNewestWorkspace,
  workspaceStage,
  loadActiveContentPlanContext,
  saveActiveContentPlanContext,
  clearActiveContentPlanContext,
} from '../lib/contentPlanWorkspaces';

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

const TARGET_DURATION_OPTIONS = [
  { value: 15, label: '≈15 сек', desc: 'Короткий охватный ролик' },
  { value: 20, label: '≈20 сек', desc: 'Основной формат' },
  { value: 30, label: '≈30 сек', desc: 'Больше пользы и аргументов' },
  { value: 45, label: '≈45 сек', desc: 'История или экспертный разбор' },
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
  // Итоговая длина ролика = длина озвучки: бэкенд тайлит кадры по аудио
  // (_align_shots_to_voiceover) и режет финал `-shortest`, так что видео НИКОГДА
  // не длиннее речи. Значит и смету надо считать по озвучке.
  //
  // Оценка держится СЛЕГКА выше реального аудио, чтобы при генерации не списалось
  // больше, чем показали:
  //  • 2.2 сл/с — консервативный темп (медленнее «читательских» 2.5, с запасом
  //    под русскую речь);
  //  • теги [sighs]/[laughs] и паузы «…»/«—» ElevenLabs проговаривает как
  //    придыхания/паузы — это реальные секунды, которых нет в счёте слов;
  //  • пол 5с — реалистичный минимум говорящего кадра.
  // Прежний плоский пол 12с задваивал смету коротких сценариев: ролик на ~5с речи
  // показывал «~12 сек» и удвоенную стоимость.
  const raw = text || '';
  const tags = (raw.match(/\[[^\]]+\]/g) || []).length;
  const spoken = raw.replace(/\[[^\]]+\]/g, ' ').trim();
  const words = spoken ? spoken.split(/\s+/).filter(Boolean).length : 0;
  if (!words && !tags) return 0;
  const pauses = (raw.match(/\.{3}|…|—/g) || []).length;
  const seconds = words / 2.2 + tags * 0.8 + pauses * 0.4;
  return Math.max(5, Math.min(90, Math.round(seconds)));
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
// Зеркало `_KLING_MIN_CLIP_SECONDS`: клипов короче у Kling не бывает, и платят
// за три секунды даже под полусекундную реплику.
const BROLL_MIN_CLIP_SECONDS = 3;
// Зеркало `_billed_avatar_seconds`. Замерено по 24 клипам на диске: Kling Avatar
// не отдаёт клип короче 64 кадров при 30 fps, а выше пола округляет длину вверх
// до блока в 8 кадров. Платят за отданное, а не за длину реплики.
const TALKING_MIN_CLIP_SECONDS = 64 / 30;
const TALKING_CLIP_BLOCK_SECONDS = 8 / 30;
const billedTalkingSeconds = (seconds) => Math.max(
  TALKING_MIN_CLIP_SECONDS,
  Math.ceil(Math.max(0, seconds) / TALKING_CLIP_BLOCK_SECONDS) * TALKING_CLIP_BLOCK_SECONDS,
);
// Говорящие кадры делят несколько плит одного сета (средний/крупный), а не
// носят по кадру каждый: плита рисуется раз на ролик и переиспользуется.
const TALKING_PLATE_COUNT = 2;

const shotWordCount = (shot) => (shot?.speech || '').trim().split(/\s+/).filter(Boolean).length;

const isBrollShot = (shot) => (shot?.visual_type || '').toLowerCase().replace(/[-_]/g, '').includes('broll');

// Пол клипа у модели, которой снимут этот кадр. Короче она не отдаёт — и короче
// не считает: реплика на секунду приедет клипом на два и оплатится как два.
const shotClipFloorSeconds = (shot) => (
  isBrollShot(shot) ? BROLL_MIN_CLIP_SECONDS : TALKING_MIN_CLIP_SECONDS
);

// Сколько секунд ролика достанется кадру. Поля «длительность» больше нет и не
// будет: бэкенд нарезает готовую озвучку по словам, так что доля кадра — это
// доля его слов. Та же формула, что в `splitStoryboardSeconds`, иначе смета и
// предупреждение под кадром разошлись бы между собой.
function shotPlannedSeconds(script, shot, totalSeconds) {
  const words = shotWordCount(shot);
  if (words <= 0) return 0;
  const totalWords = (script?.shots || []).reduce((sum, item) => sum + shotWordCount(item), 0);
  return totalWords > 0 ? (words / totalWords) * totalSeconds : 0;
}
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

// Клип ≠ кадр: длинная реплика снимается несколькими клипами, и платят именно
// за них — поэтому в смете считаются клипы.
function pluralClips(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'клипом';
  return 'клипами';
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
    let brollShots = 0;
    let talkingShots = 0;
    // Кадр тарифицируется по снятому клипу, а клип не короче пола своей модели:
    // под полсекунды речи Kling V3 снимет три секунды и три возьмёт в счёт.
    // Поэтому у каждого кадра своя цена, а не доля от общей длительности.
    let talkingBilled = 0;
    let brollBilled = 0;
    for (const shot of script.shots) {
      if (shotWordCount(shot) <= 0) continue; // кадры без речи не генерируются
      const share = shotPlannedSeconds(script, shot, totalSeconds);
      if (isBrollShot(shot)) {
        brollShots += 1;
        brollBilled += Math.max(BROLL_MIN_CLIP_SECONDS, Math.ceil(share));
      } else {
        talkingShots += 1;
        talkingBilled += billedTalkingSeconds(share);
      }
    }
    return { talking: talkingBilled, broll: brollBilled, brollShots, talkingShots };
  }
  // Сценария ещё нет: типичная раскадровка ~70% речи в кадре и 2 b-roll вставки.
  return { talking: totalSeconds * 0.7, broll: totalSeconds * 0.3, brollShots: 2, talkingShots: 3 };
}

function estimateSaasVideoCost({ text, videoMode, ttsProvider, brollMode, hasSelectedActor, hasReusableHead = false, lipsyncModel = 'sync-3', script = null, storyboardGenerationMode = 'sliced_avatar', fallbackSeconds = TYPICAL_VIDEO_SECONDS }) {
  // Длительность: реальные кадры сценария > оценка по тексту озвучки > типичный ролик.
  // Описание бизнеса — не текст озвучки, по нему длительность не считаем.
  const hasNarration = Boolean((text || '').trim());
  const safeFallbackSeconds = Number.isFinite(Number(fallbackSeconds))
    ? Math.max(5, Math.min(90, Number(fallbackSeconds)))
    : TYPICAL_VIDEO_SECONDS;
  const seconds = hasNarration ? estimateSpeechSeconds(text) : safeFallbackSeconds;
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
    // Говорящие кадры стартуют с плит одного сета: их столько же, сколько камер,
    // а не сколько кадров, и второй раз они не рисуются.
    videoCost = talking * AVATAR_RATE[avatarTier]
      + Math.min(talkingShots, TALKING_PLATE_COUNT) * FLUX_FRAME_COST;
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

function loadCache(cacheKey = CACHE_KEY) {
  try {
    const raw = localStorage.getItem(cacheKey);
    if (!raw) return null;
    const cache = JSON.parse(raw);
    if (cache.version !== CACHE_VERSION) {
      localStorage.removeItem(cacheKey);
      return null;
    }
    if (Date.now() - cache.timestamp > CACHE_MAX_AGE) {
      localStorage.removeItem(cacheKey);
      return null;
    }
    return cache;
  } catch { return null; }
}

// Последний запущенный job генерации: страница может перезагрузиться посреди
// (или сразу после) генерации, а job живёт на сервере — по сохранённому id
// мастер снова подцепляется к статусу и результату.
const LAST_JOB_KEY = 'saasshorts_last_job';
// Раскадровка готового ролика, переданная из UGC-галереи по кнопке «Редактировать».
const PENDING_STORYBOARD_KEY = 'saasshorts_pending_storyboard';

// Готовое видео лежит по /videos/saas_<job_id>/файл.mp4 — из этого же URL берём
// джоб, из которого пересъёмка забирает оплаченные клипы.
function jobIdFromVideoUrl(videoUrl) {
  const match = /\/videos\/saas_([0-9a-fA-F-]{36})\//.exec(videoUrl || '');
  return match ? match[1] : '';
}

function workspaceLastJobKey(cacheKey) {
  return !cacheKey || cacheKey === CACHE_KEY ? LAST_JOB_KEY : `${cacheKey}_last_job`;
}

function loadLastJob(cacheKey) {
  try {
    return JSON.parse(localStorage.getItem(workspaceLastJobKey(cacheKey)) || 'null');
  } catch {
    return null;
  }
}

function saveLastJob(cacheKey, jobId) {
  try {
    localStorage.setItem(workspaceLastJobKey(cacheKey), JSON.stringify({ jobId, savedAt: Date.now() }));
  } catch { /* localStorage full */ }
}

function clearLastJob(cacheKey) {
  try {
    localStorage.removeItem(workspaceLastJobKey(cacheKey));
  } catch { /* ignore */ }
}

// Выбор голоса, провайдера озвучки и актёра должен переживать перезагрузку:
// иначе повторный запуск после reload уходит с дефолтами (английская Rachel
// вместо выбранного голоса, сгенерированный Flux-актёр вместо загруженного фото).
const VIDEO_PREFS_KEY = 'saasshorts_video_prefs';

function workspaceVideoPrefsKey(cacheKey) {
  return !cacheKey || cacheKey === CACHE_KEY
    ? VIDEO_PREFS_KEY
    : `${cacheKey}_video_prefs`;
}

function loadVideoPrefs(cacheKey = CACHE_KEY) {
  try {
    const scoped = localStorage.getItem(workspaceVideoPrefsKey(cacheKey));
    return scoped ? (JSON.parse(scoped) || {}) : {};
  } catch {
    return {};
  }
}

function saveVideoPrefs(cacheKey, prefs) {
  try {
    localStorage.setItem(workspaceVideoPrefsKey(cacheKey), JSON.stringify(prefs));
  } catch { /* localStorage full */ }
}

function saveCache(cacheKey, input, analysis, webResearch, scripts, progress = {}) {
  try {
    localStorage.setItem(cacheKey, JSON.stringify({
      version: CACHE_VERSION,
      ...input,
      analysis,
      webResearch,
      scripts,
      ...progress,
      timestamp: Date.now(),
    }));
  } catch { /* localStorage full */ }
}

function resolveActiveWorkspaceContext() {
  const pendingContentPlanContext = peekPendingContentPlanItem();
  const activeContentPlanContext = pendingContentPlanContext || loadActiveContentPlanContext();
  if (pendingContentPlanContext) {
    saveActiveContentPlanContext(pendingContentPlanContext);
    clearPendingContentPlanItem();
    clearPendingTopic();
  }
  return { activeContentPlanContext, pendingContentPlanContext };
}

function workspaceHasProgress(snapshot) {
  return Boolean(
    snapshot?.analysis
    || snapshot?.webResearch
    || snapshot?.scripts?.length
    || snapshot?.jobId
    || snapshot?.genResult,
  );
}

// Никогда не открываем мастер на шаге, который нечем отрисовать. Каждый шаг
// отрисовывается только при своих данных (шаг 1 — при analysis, шаг 2 — при
// scripts), поэтому «есть прогресс → шаг 1» давал пустой экран: например,
// сценарии сохранены, а analysis === null (ручной сценарий, импорт из галереи).
// Единственным выходом оставалось «Начать заново», т.е. потеря работы.
//
// Шаги 3 (логи генерации) и 4 (готовый ролик) — полноправные: и jobId, и
// genResult лежат в снапшоте, так что после перезагрузки возвращаемся к своей
// генерации, а не к настройке. Резать их до 2, как здесь было, значит отнимать
// у пользователя и логи, и результат уже оплаченного рендера.
function workspaceStep(snapshot) {
  const hasAnalysis = Boolean(snapshot?.analysis);
  const hasScripts = Array.isArray(snapshot?.scripts) && snapshot.scripts.length > 0;
  const desired = Number.isInteger(snapshot?.step)
    ? snapshot.step
    : (workspaceHasProgress(snapshot) ? 1 : 0);
  const editorStep = hasScripts ? 2 : (hasAnalysis ? 1 : 0);

  if (desired >= 4) return snapshot?.genResult ? 4 : editorStep;
  if (desired === 3) return snapshot?.jobId ? 3 : editorStep;
  if (desired === 2) return editorStep;
  if (desired === 1) return hasAnalysis ? 1 : (hasScripts ? 2 : 0);
  return 0;
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
  const [workspaceContextState, setWorkspaceContextState] = useState(resolveActiveWorkspaceContext);
  const { activeContentPlanContext, pendingContentPlanContext } = workspaceContextState;
  const activeWorkspaceKey = activeContentPlanContext
    ? workspaceStorageKey(activeContentPlanContext)
    : CACHE_KEY;
  const [initialVideoPrefs] = useState(() => loadVideoPrefs(activeWorkspaceKey));
  const [initialCache] = useState(() => (
    activeContentPlanContext
      ? loadLocalWorkspace(activeContentPlanContext)
      : loadCache(activeWorkspaceKey)
  ));
  const [pendingTopicOnMount] = useState(() => peekPendingTopic());
  const initialHasProgress = workspaceHasProgress(initialCache);

  // Wizard state
  const [step, setStep] = useState(() => workspaceStep(initialCache));

  // Раскадровка, переданная из галереи кнопкой «Редактировать». Читаем ОДИН раз
  // в инициализаторе: StrictMode гоняет mount-эффекты дважды, и «прочитал и
  // удалил» внутри эффекта потерял бы значение на втором прогоне.
  const [pendingStoryboard] = useState(() => {
    try {
      const raw = localStorage.getItem(PENDING_STORYBOARD_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  // Step 0: Business brief
  const [url] = useState('');
  const [videoMode, setVideoMode] = useState('standard'); // "lowcost", "standard", or "premium"
  const [description, setDescription] = useState(() => initialCache?.description || '');
  const [topic, setTopic] = useState(() => (
    initialCache?.topic ?? activeContentPlanContext?.topic ?? activeContentPlanContext?.item?.topic ?? ''
  ));
  const [businessName, setBusinessName] = useState(() => initialCache?.businessName || '');
  const [businessProfiles, setBusinessProfiles] = useState(() => loadBusinessProfiles());
  const [selectedBusinessProfileId, setSelectedBusinessProfileId] = useState(() => (
    initialCache?.businessProfileId || activeContentPlanContext?.profileId || loadSelectedProfileId() || ''
  ));
  const [scriptMode, setScriptMode] = useState(() => initialCache?.scriptMode || 'ai'); // "ai" or "custom"
  const [scriptFormat, setScriptFormat] = useState(() => initialCache?.scriptFormat || 'ugc');
  // Не ставить два говорящих кадра подряд. По умолчанию выключено: каждая
  // перебивка — отдельный платный клип, который тарифицируется от трёх секунд.
  const [changingLocations, setChangingLocations] = useState(
    () => Boolean(initialCache?.changingLocations),
  );
  const [brollBetweenTalking, setBrollBetweenTalking] = useState(
    () => Boolean(initialCache?.brollBetweenTalking),
  );
  const [targetDurationSeconds, setTargetDurationSeconds] = useState(
    () => initialCache?.targetDurationSeconds || 20,
  );
  const [textModel, setTextModel] = useState(() => initialCache?.textModel || 'fast');
  const [customScript, setCustomScript] = useState(() => initialCache?.customScript || '');
  const [style, setStyle] = useState('ugc');
  const [language, setLanguage] = useState('ru');
  const [actorGender, setActorGender] = useState('female');
  const [numScripts, setNumScripts] = useState(3);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState('');
  const [fromCache, setFromCache] = useState(initialHasProgress);

  // Step 1: Analysis results
  const [analysis, setAnalysis] = useState(() => initialCache?.analysis || null);
  const [webResearch, setWebResearch] = useState(() => initialCache?.webResearch || null);
  const [scripts, setScripts] = useState(() => initialCache?.scripts || []);
  const [selectedScript, setSelectedScript] = useState(() => initialCache?.selectedScript ?? 0);
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
  const [ttsProvider, setTtsProvider] = useState(() => initialVideoPrefs.ttsProvider || 'auto');
  const [brollMode, setBrollMode] = useState('mockup');
  const [storyboardGenerationMode, setStoryboardGenerationMode] = useState('sliced_avatar');
  // Тонкие настройки пайплайна: по умолчанию всё включено, «!== false» —
  // чтобы старые prefs без этих полей не выключали фичи.
  const [backgroundMusic, setBackgroundMusic] = useState(() => initialVideoPrefs.backgroundMusic !== false);
  const [clipVisionQc, setClipVisionQc] = useState(() => initialVideoPrefs.clipVisionQc !== false);
  const [brollImageFirst, setBrollImageFirst] = useState(() => initialVideoPrefs.brollImageFirst !== false);
  const [selectedVoice, setSelectedVoice] = useState(() => initialVideoPrefs.selectedVoice || 'D5RRIJYa9pFwxiSpbGbR');
  const [selectedVoiceName, setSelectedVoiceName] = useState(() => initialVideoPrefs.selectedVoiceName || '');
  const [voiceSelectionSource, setVoiceSelectionSource] = useState(
    () => initialVideoPrefs.voiceSelectionSource || 'default',
  );
  const [minimaxVoice, setMinimaxVoice] = useState('Russian_AmbitiousWoman');
  const [actorDescription, setActorDescription] = useState('');
  const [editedNarration, setEditedNarration] = useState(() => initialCache?.editedNarration || '');
  const [actorOptions, setActorOptions] = useState([]);
  const [selectedActor, setSelectedActor] = useState(() => initialVideoPrefs.selectedActor || null);
  // Блок ведущего свёрнут до одной строки «кто говорит + каким голосом».
  // Сетка аватаров сама открывается, пока ведущий не выбран.
  const [avatarPickerOpen, setAvatarPickerOpen] = useState(() => !initialVideoPrefs.selectedActor);
  const [voicePickerOpen, setVoicePickerOpen] = useState(false);
  // Кадры, которые сейчас дозаполняет ИИ (сцена/камера/действие), и ошибка этого запроса.
  const [fillingShots, setFillingShots] = useState([]);
  const [pickingSet, setPickingSet] = useState(false);
  const [fillError, setFillError] = useState('');
  // Номера кадров, которые пользователь просит переснять, хотя текст не менялся:
  // без этого их отдал бы кэш прошлого рендера.
  const [reshootShots, setReshootShots] = useState([]);
  // Прочитать весь текст одним дублем вместо пошотных кусков: швов не будет
  // совсем, но пересниматься придётся всем говорящим кадрам.
  const [revoiceAll, setRevoiceAll] = useState(false);
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
  const selectVoiceManually = (voiceId, voiceName = '') => {
    setSelectedVoice(voiceId);
    setSelectedVoiceName(voiceName || voiceId);
    setVoiceSelectionSource('manual');
  };
  const [uploadedActorPreview, setUploadedActorPreview] = useState(() => {
    // {localPreview, serverUrl}; после перезагрузки превью строим от серверного URL
    const url = initialVideoPrefs.uploadedActorUrl;
    return url ? { localPreview: getApiUrl(url), serverUrl: url } : null;
  });
  const [actorUploadStatus, setActorUploadStatus] = useState('');
  // Портрет крупно — отдельно от аватара. С общего плана лицо не снимается:
  // оно занимает проценты кадра, и генератор дорисовывает черты сам, каждый раз
  // по-своему. Портрет несёт поры, веснушки и цвет губ — то, по чему человека и
  // узнают.
  const [selectedFace, setSelectedFace] = useState(() => initialVideoPrefs.selectedFace || null);
  const [faceUploadStatus, setFaceUploadStatus] = useState('');
  const [uploadingFace, setUploadingFace] = useState(false);
  // Готовые плиты ракурсов: {front, side}. Что лежит здесь — копируется в ролик
  // как есть, без единого платного вызова на постановку камеры.
  const [plateUrls, setPlateUrls] = useState(() => initialVideoPrefs.plateUrls || {});
  const [uploadingPlate, setUploadingPlate] = useState('');
  const [plateUploadStatus, setPlateUploadStatus] = useState('');
  // Кадр, открытый на весь экран: {src, alt, caption}. Кадры живут миниатюрами,
  // а утверждают их именно по деталям лица — по 104 пикселям это не решается.
  const [lightbox, setLightbox] = useState(null);
  const [productPhoto, setProductPhoto] = useState(null); // {preview, serverUrl}
  const [productDescription, setProductDescription] = useState('');

  // Step 3: Generate
  const [generating, setGenerating] = useState(false);
  const [jobId, setJobId] = useState(() => initialCache?.jobId || null);
  const [genLogs, setGenLogs] = useState([]);
  const [genStatus, setGenStatus] = useState(() => initialCache?.genStatus || 'idle');
  const [genResult, setGenResult] = useState(() => initialCache?.genResult || null);
  const [lipSyncModel, setLipSyncModel] = useState('sync-3');
  const [lipSyncing, setLipSyncing] = useState(false);
  // Frames-only preview: generate/regenerate the start frames of each shot on
  // step 2 (перед платной генерацией видео), staying on the storyboard editor.
  const [framesGenerating, setFramesGenerating] = useState(false);
  const [framesShot, setFramesShot] = useState(null); // shot_number currently regenerating, or null for «все»
  // Что сказать после превью кадров: «прошло, но ничего не изменилось» — это
  // всегда отброшенный пустой кадр, и молчать об этом нельзя.
  const [framesNotice, setFramesNotice] = useState('');
  // Прослушивание озвучки до платного видео: дорожка задаёт длину ролика,
  // границы кадров и число оплачиваемых клипов, поэтому её слушают первой.
  const [voiceGenerating, setVoiceGenerating] = useState(false);
  const [voiceShot, setVoiceShot] = useState(null); // shot_number, чью реплику перезаписываем
  const [voiceNotice, setVoiceNotice] = useState('');
  // Кто ставит ведущего в кадр. Пусто = дефолт бэкенда. Модель меняется только
  // руками: молчаливый перебор редакторов оплачивался пользователем, который о
  // нём не знал.
  const [avatarEditModel, setAvatarEditModel] = useState('');
  const [avatarEditModels, setAvatarEditModels] = useState([]);
  // Отказ редактора: что ответила модель и с какого кадра начинать повтор.
  const [frameBlock, setFrameBlock] = useState(null);

  // Publish
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState(null);
  const [publishPlatforms, setPublishPlatforms] = useState({ tiktok: true, instagram: true, youtube: true });
  const [isScheduling, setIsScheduling] = useState(false);
  const [scheduleDate, setScheduleDate] = useState('');

  // UI
  const [copied, setCopied] = useState('');
  const [logsExpanded, setLogsExpanded] = useState(true);
  const workspaceSyncTimerRef = useRef(null);
  const latestWorkspaceSnapshotRef = useRef(null);
  const workspaceResettingRef = useRef(false);
  const workspaceHydratedRef = useRef(!authToken || !activeContentPlanContext);
  const [workspaceHydrationVersion, setWorkspaceHydrationVersion] = useState(0);

  const workspaceEndpoint = (context = activeContentPlanContext) => {
    const profileId = context?.profileId || '';
    const itemId = context?.itemId ?? context?.item?.item_id ?? '';
    return `/api/user/content-workspaces/${encodeURIComponent(profileId)}/${encodeURIComponent(itemId)}`;
  };

  // restoreStep=false — для чужой записи, приехавшей во время работы: подхватить
  // её данные можно, а вот перекинуть пользователя на другой шаг мастера посреди
  // генерации нельзя.
  const applyWorkspaceSnapshot = (snapshot, { restoreStep = true } = {}) => {
    if (!snapshot) return;
    setDescription(snapshot.description || '');
    setTopic(snapshot.topic ?? activeContentPlanContext?.topic ?? activeContentPlanContext?.item?.topic ?? '');
    setBusinessName(snapshot.businessName || '');
    setSelectedBusinessProfileId(snapshot.businessProfileId || activeContentPlanContext?.profileId || '');
    setScriptMode(snapshot.scriptMode || 'ai');
    setScriptFormat(snapshot.scriptFormat || 'ugc');
    setTargetDurationSeconds(snapshot.targetDurationSeconds || 20);
    setBrollBetweenTalking(Boolean(snapshot.brollBetweenTalking));
    setChangingLocations(Boolean(snapshot.changingLocations));
    setTextModel(snapshot.textModel || 'fast');
    setCustomScript(snapshot.customScript || '');
    setAnalysis(snapshot.analysis || null);
    setWebResearch(snapshot.webResearch || null);
    setScripts(snapshot.scripts || []);
    if (restoreStep) setStep(workspaceStep(snapshot));
    setSelectedScript(snapshot.selectedScript ?? 0);
    setEditedNarration(snapshot.editedNarration || '');
    setJobId(snapshot.jobId || null);
    setGenStatus(snapshot.genStatus || 'idle');
    setGenResult(snapshot.genResult || null);
    setFromCache(workspaceHasProgress(snapshot));
  };

  const buildWorkspaceSnapshot = (overrides = {}) => ({
    version: CACHE_VERSION,
    url: '',
    businessProfileId: selectedBusinessProfileId,
    businessName: businessName.trim(),
    description: description.trim(),
    topic: topic.trim(),
    scriptMode,
    scriptFormat,
    targetDurationSeconds,
    brollBetweenTalking,
    changingLocations,
    textModel,
    customScript: scriptMode === 'custom' ? customScript.trim() : '',
    analysis,
    webResearch,
    scripts,
    step,
    selectedScript,
    editedNarration,
    jobId,
    genStatus,
    genResult,
    result: genResult,
    status: genStatus === 'failed' ? 'failed' : undefined,
    timestamp: Date.now(),
    ...overrides,
  });

  function flushWorkspaceSync() {
    if (workspaceSyncTimerRef.current) {
      clearTimeout(workspaceSyncTimerRef.current);
      workspaceSyncTimerRef.current = null;
    }
    if (!authToken || !activeContentPlanContext) return Promise.resolve();
    const snapshot = latestWorkspaceSnapshotRef.current;
    if (!snapshot) return Promise.resolve();
    return fetch(getApiUrl(workspaceEndpoint()), {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify({
        revision: snapshot.revision,
        stage: workspaceStage(snapshot),
        snapshot,
      }),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data?.workspace || !activeContentPlanContext) return;
        // Ответ на собственный PUT — это эхо: сервер возвращает ту же ревизию,
        // что мы прислали, только со своим updated_at (а он всегда на миллисекунды
        // позже нашего). chooseNewestWorkspace честно объявлял такое эхо «более
        // свежим», мы раскладывали его обратно по состоянию и дёргали
        // workspaceHydrationVersion — а он стоит в зависимостях эффекта
        // сохранения. Круг замыкался: PUT → apply → PUT, по несколько раз в
        // секунду, пока открыта вкладка (в базе накопилось 10 000 ревизий одной
        // записи). Принимаем только чужую запись — со строго большей ревизией.
        if (Number(data.workspace.revision) <= Number(snapshot.revision || 0)) return;
        const remoteWorkspace = {
          ...data.workspace.snapshot,
          revision: data.workspace.revision,
          updatedAt: data.workspace.updated_at,
        };
        const localWorkspace = loadLocalWorkspace(activeContentPlanContext);
        const newestWorkspace = chooseNewestWorkspace(localWorkspace, remoteWorkspace);
        if (newestWorkspace === remoteWorkspace) {
          const saved = saveLocalWorkspace(activeContentPlanContext, remoteWorkspace);
          latestWorkspaceSnapshotRef.current = saved;
          applyWorkspaceSnapshot(saved, { restoreStep: false });
          setWorkspaceHydrationVersion((version) => version + 1);
        }
      })
      .catch(() => {});
  }

  function queueWorkspaceSync(snapshot) {
    latestWorkspaceSnapshotRef.current = snapshot;
    if (!authToken || !activeContentPlanContext) return;
    if (workspaceSyncTimerRef.current) clearTimeout(workspaceSyncTimerRef.current);
    workspaceSyncTimerRef.current = setTimeout(flushWorkspaceSync, 400);
  }

  const persistWorkspaceSnapshot = (overrides = {}) => {
    const snapshot = buildWorkspaceSnapshot(overrides);
    if (activeContentPlanContext) {
      const saved = saveLocalWorkspace(activeContentPlanContext, snapshot);
      queueWorkspaceSync(saved);
      return saved;
    }
    saveCache(
      activeWorkspaceKey,
      {
        url: '',
        businessProfileId: snapshot.businessProfileId,
        businessName: snapshot.businessName,
        description: snapshot.description,
        topic: snapshot.topic,
        scriptMode: snapshot.scriptMode,
        scriptFormat: snapshot.scriptFormat,
        targetDurationSeconds: snapshot.targetDurationSeconds,
        textModel: snapshot.textModel,
        customScript: snapshot.customScript,
      },
      snapshot.analysis,
      snapshot.webResearch,
      snapshot.scripts,
      {
        step: snapshot.step,
        selectedScript: snapshot.selectedScript,
        editedNarration: snapshot.editedNarration,
        jobId: snapshot.jobId,
        genStatus: snapshot.genStatus,
        genResult: snapshot.genResult,
      },
    );
    return snapshot;
  };

  // Pre-fill from cache on mount
  useEffect(() => {
    if (fromCache && scripts.length > 0 && !initialCache?.editedNarration) {
      setEditedNarration(scripts[selectedScript]?.full_narration || scripts[0].full_narration || '');
    }
  }, []);

  useEffect(() => {
    if (!authToken || !activeContentPlanContext) {
      workspaceHydratedRef.current = true;
      return undefined;
    }
    let cancelled = false;
    workspaceHydratedRef.current = false;
    fetch(getApiUrl(workspaceEndpoint()), { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || !data?.workspace) return;
        const remoteWorkspace = {
          ...data.workspace.snapshot,
          revision: data.workspace.revision,
          updatedAt: data.workspace.updated_at,
        };
        const localWorkspace = loadLocalWorkspace(activeContentPlanContext);
        const newestWorkspace = chooseNewestWorkspace(localWorkspace, remoteWorkspace);
        if (newestWorkspace === remoteWorkspace) {
          const saved = saveLocalWorkspace(activeContentPlanContext, remoteWorkspace);
          applyWorkspaceSnapshot(saved);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (cancelled) return;
        workspaceHydratedRef.current = true;
        setWorkspaceHydrationVersion((version) => version + 1);
      });
    return () => {
      cancelled = true;
    };
  }, [authToken, activeWorkspaceKey]);

  useEffect(() => {
    if (workspaceResettingRef.current) {
      workspaceResettingRef.current = false;
      return;
    }
    if (!workspaceHydratedRef.current) return;
    persistWorkspaceSnapshot();
  }, [
    description,
    topic,
    businessName,
    selectedBusinessProfileId,
    scriptMode,
    scriptFormat,
    targetDurationSeconds,
    brollBetweenTalking,
    changingLocations,
    textModel,
    customScript,
    analysis,
    webResearch,
    scripts,
    step,
    selectedScript,
    editedNarration,
    jobId,
    genStatus,
    genResult,
    workspaceHydrationVersion,
  ]);

  useEffect(() => () => {
    if (workspaceSyncTimerRef.current) clearTimeout(workspaceSyncTimerRef.current);
    const snapshot = latestWorkspaceSnapshotRef.current;
    if (!authToken || !activeContentPlanContext || !snapshot) return;
    const { profileId, itemId } = activeContentPlanContext;
    fetch(getApiUrl(`/api/user/content-workspaces/${encodeURIComponent(profileId)}/${encodeURIComponent(itemId)}`), {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify({
        revision: snapshot.revision,
        stage: workspaceStage(snapshot),
        snapshot,
      }),
      keepalive: true,
    }).catch(() => {});
  }, [authToken, activeWorkspaceKey]);

  // Активный проект со страницы «Проекты» + тема, выбранная в контент-плане.
  // Тема читается lazy-инициализатором и очищается отдельно: StrictMode гоняет
  // mount-эффект дважды, и повторный прогон не должен терять уже снятую тему.
  useEffect(() => {
    const storedId = activeContentPlanContext?.profileId || loadSelectedProfileId();
    if (storedId) {
      const profile = loadBusinessProfiles().find((item) => businessProfileKey(item) === storedId);
      // Кеш держит правки пользователя для того же проекта; при смене
      // активного проекта на странице «Проекты» кеш надо перезаписать.
      const cachedId = initialCache?.businessProfileId || '';
      if (profile && (!description.trim() || storedId !== cachedId)) {
        handleLoadBusinessProfile(profile);
      }
    }
    if (activeContentPlanContext) {
      setTopic(initialCache?.topic ?? activeContentPlanContext.topic ?? activeContentPlanContext.item?.topic ?? '');
    } else if (pendingTopicOnMount) {
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
  const applyGeneratedShots = (result, previewJobs = {}) => {
    const genShots = result?.shots;
    const title = result?.script?.title;
    if (!Array.isArray(genShots) || !genShots.length || !title) return;
    const byNumber = new Map(genShots.map((s, i) => [s.shot_number ?? (i + 1), s]));
    // Перерисованный кадр ложится по тому же адресу: ракурс общий на весь ролик,
    // имя файла не меняется. Браузер отдаёт картинку из кэша, и «Перегенерить»
    // выглядит как «ничего не произошло» даже когда кадр честно нарисован заново.
    const bust = result?.frames_only ? `?v=${Date.now()}` : '';
    const next = scripts.map((script) => {
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
          image_preview: g.local_url ? `${getApiUrl(g.local_url)}${bust}` : shot.image_preview,
          generation_prompt: g.generation_prompt || shot.generation_prompt,
          _prompt_source_scene: g._prompt_source_scene ?? shot._prompt_source_scene,
          _render_files: g._render_files || shot._render_files,
          // Реплика, записанная голосом: её кусок дорожки, длина и во сколько
          // платных клипов она превратится. `voice_speech` — текст, который
          // реально прочитан: по нему видно, что реплику после этого правили.
          voice_url: g.voice_url || shot.voice_url,
          voice_speech: g.voice_speech ?? shot.voice_speech,
          voice_start: g.voice_start ?? shot.voice_start,
          voice_end: g.voice_end ?? shot.voice_end,
          voice_seconds: g.voice_seconds ?? shot.voice_seconds,
          voice_clips: g.voice_clips ?? shot.voice_clips,
        };
      });
      // Снятый ролик становится новым источником для пересъёмки, а его кадры —
      // точкой отсчёта: с этого момента «изменённым» считается то, что правили
      // после рендера. Превью кадров (frames_only) роликом не является.
      const renderedJobId = (result?.frames_only || result?.voice_only)
        ? ''
        : jobIdFromVideoUrl(result?.video_url);
      if (!renderedJobId) {
        // Джоб предпросмотра: клипов в нём нет, зато есть оплаченные кадры и
        // утверждённые дубли. Рендер заберёт их оттуда — иначе он переделал бы
        // ровно то, что пользователь только что посмотрел, послушал и одобрил.
        return {
          ...script,
          shots,
          ...(previewJobs.frames ? { _frames_job_id: previewJobs.frames } : {}),
          ...(previewJobs.voice ? {
            _voice_job_id: previewJobs.voice,
            _voice_track: result?.audio_url || '',
            _voice_seconds: result?.duration || 0,
            _voice_clips: result?.voice_clips_planned || 0,
            _voice_model: result?.voice_model || '',
            _voice_provider: result?.voice_provider || '',
            _voice_id: result?.voice_id || '',
            _voice_name: result?.voice_name || '',
            _voice_selection_source: result?.voice_selection_source || '',
            _voice_shoot_cost: result?.video_cost_estimate?.total ?? null,
          } : {}),
        };
      }
      return {
        ...script,
        shots,
        _source_job_id: renderedJobId,
        _render_baseline: shots,
        // Снятый ролик сам стал источником звука и кадров, а папки превью
        // вычищаются через сутки — держать ссылки на них уже не на что.
        _frames_job_id: '',
        _voice_job_id: '',
        _voice_track: '',
      };
    });
    if (!result?.frames_only && jobIdFromVideoUrl(result?.video_url)) setReshootShots([]);
    setScripts(next);
    // Persist to the localStorage cache: `scripts` are re-loaded from it on mount
    // (loadCache), so without this the freshly generated preview_frame_url values
    // are dropped and every generated frame "disappears" after a page reload.
    persistScripts(next);
  };

  useEffect(() => {
    if (pendingTopicOnMount && !pendingContentPlanContext) return;
    const last = loadLastJob(activeWorkspaceKey);
    if (!last?.jobId) return;
    (async () => {
      try {
        const res = await fetch(getApiUrl(`/api/saasshorts/status/${last.jobId}`), { headers: authHeaders() });
        if (!res.ok) {
          // Job вычищен на сервере (рестарт или >1ч) — готовое видео остаётся в галерее UGC
          if (res.status === 404) clearLastJob(activeWorkspaceKey);
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

  // Держим голос на утверждённом дефолте языка и НЕ даём ему «плавать».
  // Раньше эффект брал первый подходящий голос из ElevenLabs-библиотеки — из-за
  // порядка библиотеки один и тот же проект получал то Victoria, то другой голос
  // между генерациями. Теперь: детерминированный дефолт по языку/полу, и ручной
  // выбор НЕ затирается на смене пола / ремаунте — только когда реально нужно
  // (сменился язык, голос не выбран, или голос не того языка).
  const voiceAutoKeyRef = useRef(initialVideoPrefs.voiceKey || '');
  useEffect(() => {
    const comboKey = `${language}-${actorGender}`;
    if (voiceAutoKeyRef.current === comboKey) return;
    const prevLang = voiceAutoKeyRef.current.split('-')[0] || '';
    voiceAutoKeyRef.current = comboKey;
    const genderDefaults = {
      'en-female': '21m00Tcm4TlvDq8ikWAM',  // Rachel
      'en-male': '29vD33N1CtxCmqQRPOHJ',    // Drew
      'es-female': 'EXAVITQu4vr4xnSDxMaL',  // Bella
      'es-male': 'ErXwobaYiN019PkySvjV',     // Antoni
      'ru-female': 'D5RRIJYa9pFwxiSpbGbR',  // Victoria — родной русский, утверждённый дефолт
      'ru-male': '29vD33N1CtxCmqQRPOHJ',    // Multilingual fallback
    };
    const curated = genderDefaults[comboKey] || genderDefaults['en-female'];
    const languageChanged = Boolean(prevLang) && prevLang !== language;
    const wrongForLanguage =
      (language === 'ru' && selectedVoice === '21m00Tcm4TlvDq8ikWAM') ||  // Rachel (англ.) на русском
      (language !== 'ru' && selectedVoice === 'D5RRIJYa9pFwxiSpbGbR');    // Victoria (рус.) на не-русском
    if (!selectedVoice || languageChanged || wrongForLanguage) {
      setSelectedVoice(curated);
      setSelectedVoiceName('');
      setVoiceSelectionSource('default');
    }
    // Иначе уважаем ручной выбор — на смене пола/ремаунте не трогаем.
  }, [actorGender, language, selectedVoice]);

  // Персистим выбор озвучки и актёра (см. loadVideoPrefs)
  useEffect(() => {
    saveVideoPrefs(activeWorkspaceKey, {
      selectedVoice,
      selectedVoiceName,
      voiceSelectionSource,
      voiceKey: `${language}-${actorGender}`,
      ttsProvider,
      selectedActor: selectedActor || '',
      selectedFace: selectedFace || '',
      plateUrls,
      uploadedActorUrl: uploadedActorPreview?.serverUrl || '',
      backgroundMusic,
      clipVisionQc,
      brollImageFirst,
    });
  }, [activeWorkspaceKey, selectedVoice, selectedVoiceName, voiceSelectionSource, ttsProvider, selectedActor, selectedFace, plateUrls, uploadedActorPreview, language, actorGender, backgroundMusic, clipVisionQc, brollImageFirst]);

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
    if (profile.targetDurationSeconds || profile.target_duration_seconds) {
      setTargetDurationSeconds(Number(profile.targetDurationSeconds || profile.target_duration_seconds) || 20);
    }
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
          target_duration_seconds: targetDurationSeconds,
          text_model: textModel,
          custom_script: isCustom ? customScript.trim() : undefined,
          num_scripts: numScripts,
          style,
          language,
          actor_gender: actorGender,
          broll_between_talking: brollBetweenTalking,
          changing_locations: changingLocations,
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

      const firstNarration = data.scripts[0]?.full_narration || '';
      persistWorkspaceSnapshot({
        analysis: data.analysis,
        webResearch: data.web_research || null,
        scripts: data.scripts,
        step: 1,
        selectedScript: 0,
        editedNarration: firstNarration,
        customScript: isCustom ? customScript.trim() : '',
      });

      // Pre-fill actor description and narration from first script
      if (data.scripts.length > 0) {
        setActorDescription('');
        setEditedNarration(firstNarration);
      }

      setStep(1);
    } catch (e) {
      setAnalyzeError(e.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleSelectScript = (idx) => {
    const nextNarration = scripts[idx]?.full_narration || '';
    setSelectedScript(idx);
    if (scripts[idx]) {
      setActorDescription('');
      setActorOptions([]);
      setEditedNarration(nextNarration);
    }
    persistWorkspaceSnapshot({ selectedScript: idx, editedNarration: nextNarration });
  };

  const persistScripts = (nextScripts) => {
    persistWorkspaceSnapshot({ scripts: nextScripts });
  };

  // Открытие раскадровки готового ролика из галереи: кадры приходят вместе с
  // уже сгенерёнными превью и клипами (их URL лежат в метаданных ролика), плюс
  // архив удалённых кадров — так к ролику можно доснять кадры, ничего не
  // переписывая заново.
  useEffect(() => {
    if (!pendingStoryboard?.shots?.length) return;
    try {
      localStorage.removeItem(PENDING_STORYBOARD_KEY);
    } catch {
      /* приватный режим — переживём */
    }
    const restored = {
      title: pendingStoryboard.title || 'Раскадровка ролика',
      caption: pendingStoryboard.caption || '',
      hashtags: pendingStoryboard.hashtags || [],
      full_narration: pendingStoryboard.full_narration || '',
      actor_description: pendingStoryboard.actor_description || '',
      language: pendingStoryboard.language || 'ru',
      format: 'storyboard_v3',
      shots: pendingStoryboard.shots,
      shots_archived: pendingStoryboard.shots_archived || [],
      _source_video_id: pendingStoryboard.video_id || '',
      // Джоб с оплаченными клипами + слепок кадров на момент открытия: по нему
      // видно, что пользователь реально изменил, а значит — за что платить.
      _source_job_id: pendingStoryboard.job_id || '',
      _render_baseline: pendingStoryboard.shots,
    };
    // Тот же ролик открыт повторно — обновляем запись, а не плодим копии.
    const existing = scripts.findIndex((script) => script.title === restored.title);
    const next = existing >= 0
      ? scripts.map((script, i) => (i === existing ? restored : script))
      : [restored, ...scripts];
    setScripts(next);
    persistScripts(next);
    setSelectedScript(existing >= 0 ? existing : 0);
    setScriptFormat('storyboard_v3');
    if (pendingStoryboard.storyboard_generation_mode) {
      setStoryboardGenerationMode(pendingStoryboard.storyboard_generation_mode);
    }
    setStep(2);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Место действия — свойство сценария, а не кадра: одна комната на все
  // говорящие кадры (`_pinned_avatar_set` на бэкенде). Раньше оно жило внутри
  // кадра 1 и потому собирало на себя всё, что туда написали, — камеру, позу,
  // внешность, — и всё это уезжало в плиты.
  const updateSelectedScript = (patch) => {
    const nextScripts = scripts.map((script, idx) => (
      idx === selectedScript ? { ...script, ...patch } : script
    ));
    setScripts(nextScripts);
    persistScripts(nextScripts);
  };

  // Keep shot_number in sync with position after add / delete / reorder.
  const renumberShots = (shots) => shots.map((shot, idx) => ({ ...shot, shot_number: idx + 1 }));

  // Ключ порядка `_ord`. Нужен архиву: удалённый кадр обязан вернуться туда,
  // где стоял, при любом порядке нажатий «Вернуть». Номер для этого не годится
  // (перенумеровывается), индекс на момент удаления — тоже: он верен только
  // пока возвращают строго в обратном порядке. Кнопка «Вернуть» стоит у каждого
  // кадра, и естественный порядок — сверху вниз — ровно обратный правильному:
  // три кадра, удалённые с одной позиции, возвращались перевёрнутым блоком.
  // Так 03.08 раскадровка собралась в другом порядке (джоб saas_c079a7dc).
  //
  // Ключ описывает ПОЗИЦИЮ, а не кадр: набор ключей в живом списке при
  // перестановке не меняется, кадры едут между ними. Поэтому после любой правки
  // ключи просто раздаются заново сверху вниз — и «вернуть на своё место»
  // остаётся осмысленным даже после ручного переупорядочивания.
  const withShotOrder = (shots) => {
    const pool = shots.map((s) => s._ord).filter((v) => typeof v === 'number').sort((a, b) => a - b);
    let taken = 0;
    let prev = null;
    return shots.map((shot, i) => {
      if (typeof shot._ord === 'number') {
        const ord = pool[taken];
        taken += 1;
        prev = ord;
        return ord === shot._ord ? shot : { ...shot, _ord: ord };
      }
      // Кадр без ключа — новый (или пришёл из раскадровки, сделанной до этого
      // правила). Ставим его между соседями: дробный ключ не сдвигает чужие и
      // не сталкивается с ключом, уехавшим в архив.
      const next = pool[taken];
      let ord;
      if (next === undefined) ord = prev === null ? i : prev + 1;
      else ord = prev === null ? next - 1 : (prev + next) / 2;
      prev = ord;
      return { ...shot, _ord: ord };
    });
  };

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
  const mutateSelectedScriptShots = (mutator, archiveMutator = null) => {
    const current = scripts[selectedScript] || {};
    const prevShots = (current.shots || []).map((shot) => ({ ...shot }));
    const prevArchived = (current.shots_archived || []).map((shot) => ({ ...shot }));
    const nextScripts = scripts.map((script, idx) => {
      if (idx !== selectedScript) return script;
      // Ключи порядка проставляем ДО правки: архиву нужен ключ того кадра,
      // который сейчас удаляют, а он берётся из этого же списка.
      const before = withShotOrder(script.shots || []);
      const shots = resequenceShotTimeline(renumberShots(withShotOrder(mutator([...before]))));
      const archived = archiveMutator
        ? archiveMutator([...(script.shots_archived || [])], before)
        : (script.shots_archived || []);
      return { ...script, format: 'storyboard_v3', shots, shots_archived: archived };
    });
    setShotHistory((history) => [
      ...history.slice(-49),
      { scriptIndex: selectedScript, shots: prevShots, archived: prevArchived },
    ]);
    setScripts(nextScripts);
    persistScripts(nextScripts);
    // Возвращаем результат: состояние обновляется асинхронно, а вызывающему
    // коду (дозаполнение нового кадра ИИ) свежие кадры нужны прямо сейчас.
    return nextScripts;
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
        // Архив откатывается вместе с кадрами: иначе undo удаления вернул бы
        // кадр в список, оставив его копию в «удалённых».
        ? { ...script, format: 'storyboard_v3', shots: entry.shots, shots_archived: entry.archived || [] }
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

  // Удаление кадра = архив, а не потеря. Текст, сцена и промпт уезжают в
  // `shots_archived`, попадают в метаданные ролика вместе с раскадровкой и
  // возвращаются одной кнопкой — заново придумывать удалённый кадр не нужно.
  const removeSelectedScriptShot = (shotIndex) => {
    const shots = scripts[selectedScript]?.shots || [];
    if (shots.length <= 1) return; // keep at least one shot
    // Кадр уносит в архив свой ключ порядка — по нему и вернётся на место.
    // `_archived_at` (индекс на момент удаления) больше не пишем: он врал при
    // любом возврате, кроме строго обратного, и читается теперь только у
    // архивов, снятых до появления ключа.
    mutateSelectedScriptShots(
      (next) => { next.splice(shotIndex, 1); return next; },
      (archived, before) => [...archived, { ...before[shotIndex] }],
    );
  };

  // Кадру нужны сцена, камера и действие — видео-модель читает промпт, а не
  // реплику. Пустой кадр = случайная картинка, поэтому добавленные и
  // восстановленные кадры дозаполняем текстовым запросом к Gemini (бесплатно).
  const fillShotDetails = async (shotNumbers, scriptsOverride = null) => {
    // Состояние React обновляется асинхронно, поэтому только что добавленный
    // кадр приходит сюда явным срезом, а не читается из `scripts`.
    const base = scriptsOverride || scripts;
    const script = base[selectedScript];
    const targets = (script?.shots || []).filter((shot) => shotNumbers.includes(shot.shot_number));
    if (!targets.length) return;
    setFillingShots(shotNumbers);
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/storyboard-shot-fill'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
          ...(geminiApiKey && !isManagedKey(geminiApiKey) ? { 'X-Gemini-Key': geminiApiKey } : {}),
        },
        body: JSON.stringify({
          script: {
            title: script.title,
            actor_description: script.actor_description || actorDescription,
            _video_topic: topic,
            shots: (script.shots || []).map((shot) => ({
              shot_number: shot.shot_number,
              speech: shot.speech,
              scene: shot.scene,
              visual_type: shot.visual_type,
            })),
          },
          shots: targets,
          language,
          actor_gender: actorGender,
          text_model: textModel,
          use_platform_keys: usePlatformKeys,
        }),
      });
      if (!res.ok) {
        let msg = 'Не удалось заполнить кадр';
        try { const err = await res.json(); msg = err.detail || msg; } catch { /* оставим дефолт */ }
        throw new Error(msg);
      }
      const data = await res.json();
      const byNumber = new Map((data.shots || []).map((shot) => [shot.shot_number, shot]));
      const next = base.map((item, idx) => {
        if (idx !== selectedScript) return item;
        return {
          ...item,
          shots: (item.shots || []).map((shot) => byNumber.get(shot.shot_number) || shot),
        };
      });
      setScripts(next);
      persistScripts(next);
    } catch (e) {
      setFillError(e.message || 'Не удалось заполнить кадр');
      setTimeout(() => setFillError(''), 6000);
    } finally {
      setFillingShots([]);
    }
  };

  // Подобрать место действия — отдельный текстовый запрос, fal.ai не трогается.
  // Переподбирать можно сколько угодно, пока кадры не отрисованы: плиты рисуются
  // по `set_prompt`, и смена места до съёмки не стоит ничего.
  const pickReelSet = async () => {
    const script = scripts[selectedScript];
    if (!script) return;
    setPickingSet(true);
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/storyboard-set'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
          ...(geminiApiKey && !isManagedKey(geminiApiKey) ? { 'X-Gemini-Key': geminiApiKey } : {}),
        },
        body: JSON.stringify({
          script: {
            title: script.title,
            _video_topic: topic,
            shots: (script.shots || []).map((shot) => ({
              shot_number: shot.shot_number,
              speech: shot.speech,
            })),
          },
          language,
          text_model: textModel,
          use_platform_keys: usePlatformKeys,
        }),
      });
      if (!res.ok) {
        let msg = 'Не удалось подобрать место';
        try { const err = await res.json(); msg = err.detail || msg; } catch { /* оставим дефолт */ }
        throw new Error(msg);
      }
      const data = await res.json();
      // Подобранное, а не выбранное: комнату по-прежнему держит фото ведущего,
      // пока человек не впишет своё место руками.
      updateSelectedScript({
        set_scene: data.set_scene || '',
        set_prompt: data.set_prompt || '',
        set_source: 'ai',
      });
    } catch (e) {
      setFillError(e.message || 'Не удалось подобрать место');
      setTimeout(() => setFillError(''), 6000);
    } finally {
      setPickingSet(false);
    }
  };

  const addShotWithSpeech = async (speech) => {
    const shotNumber = (scripts[selectedScript]?.shots || []).length + 1;
    const nextScripts = mutateSelectedScriptShots(
      (next) => [...next, { ...makeBlankShot(next), speech }],
    );
    await fillShotDetails([shotNumber], nextScripts);
  };

  // Куда вернуть кадр — на то место, откуда его удалили. Индекс записан при
  // удалении, поэтому возврат с конца архива это точная отмена удалений: порядок
  // кадров совпадает с исходным, даже если удаляли вразнобой. Старые записи без
  // индекса уходят в конец, как раньше.
  // Куда вернуть кадр: перед первым живым кадром, чей ключ порядка больше. Это
  // не зависит от того, сколько кадров вернули до него и в каком порядке.
  const archivedShotSlot = (shot, shots) => {
    if (typeof shot?._ord === 'number') {
      const at = shots.findIndex((s) => typeof s._ord === 'number' && s._ord > shot._ord);
      return at === -1 ? shots.length : at;
    }
    // Архив, снятый до появления ключа: остаётся старый индекс. Он верен только
    // при «Вернуть все» (там возврат идёт с конца), но лучше, чем ничего.
    const at = Number.isInteger(shot?._archived_at) ? shot._archived_at : shots.length;
    return Math.max(0, Math.min(at, shots.length));
  };

  const restoredShot = (shot) => {
    const rest = { ...shot };
    delete rest._archived_at;
    return rest;
  };

  const restoreArchivedShot = (archiveIndex) => {
    const archived = scripts[selectedScript]?.shots_archived || [];
    const shot = archived[archiveIndex];
    if (!shot) return;
    mutateSelectedScriptShots(
      (next) => {
        next.splice(archivedShotSlot(shot, next), 0, restoredShot(shot));
        return next;
      },
      (list) => list.filter((_, i) => i !== archiveIndex),
    );
  };

  // Собрать раскадровку обратно одним нажатием. Идём с конца архива: кадрам с
  // ключом порядка направление безразлично, а вот у архивов, снятых до него,
  // сохранённый индекс верен только при возврате в обратном порядке.
  const restoreAllArchivedShots = () => {
    const archived = scripts[selectedScript]?.shots_archived || [];
    if (!archived.length) return;
    mutateSelectedScriptShots(
      (next) => {
        for (let i = archived.length - 1; i >= 0; i -= 1) {
          next.splice(archivedShotSlot(archived[i], next), 0, restoredShot(archived[i]));
        }
        return next;
      },
      () => [],
    );
  };

  const dropArchivedShot = (archiveIndex) => {
    mutateSelectedScriptShots(
      (next) => next,
      (list) => list.filter((_, i) => i !== archiveIndex),
    );
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
      // Ключ порядка тоже: копия — отдельный кадр, ей нужен свой, иначе архив
      // не отличит её от оригинала.
      const { frame_status, _ord, ...rest } = original;
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
  // modelOverride — выбор из модалки отказа: setState асинхронен, а запрос уходит
  // сразу, поэтому модель передаётся аргументом, а не читается из стейта.
  const handleGenerateFrames = async (shotNumber = null, modelOverride = null) => {
    if (!falKey) {
      alert('fal.ai API key required. Set it in Settings.');
      return;
    }
    if (framesGenerating) return;

    const editModel = modelOverride ?? avatarEditModel;
    setFramesGenerating(true);
    setFramesShot(shotNumber);
    setFramesNotice('');

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
          voice_name: selectedVoiceLabel,
          voice_selection_source: voiceSelectionSource,
          tts_provider: ttsProvider,
          minimax_voice_id: minimaxVoice,
          minimax_voice_name: minimaxVoiceLabel,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          selected_face_url: selectedFace || undefined,
          plate_urls: plateUrls,
          video_mode: videoMode,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          use_platform_keys: usePlatformKeys,
          broll_image_first: brollImageFirst,
          frames_only: true,
          frames_only_shot: shotNumber ?? undefined,
          avatar_edit_model: editModel || undefined,
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
          applyGeneratedShots(data.result, { frames: framesJobId });
          // Джоб «успешен» и с нулём кадров: модель может вернуть пустую
          // картинку, её отбрасывают, и раньше пользователь видел ровно то же
          // самое изображение без единого слова о том, что произошло.
          const framesMade = Number(data.result?.frames_made ?? 0);
          const framesFailed = Number(data.result?.frames_failed ?? 0);
          // Пустой кадр тарифицируется наравне с картинкой, поэтому в сообщении
          // о неудаче стоит сумма: молчать о списании нельзя.
          const charged = Number(data.result?.frames_charged ?? 0);
          const spent = charged ? ` Списано: ${formatUsd(charged * 0.05)}.` : ' Денег не списано.';
          // Каталог редакторов приходит с результатом — он же помечает, кто уже
          // отказал на этом фото.
          const catalogue = data.result?.avatar_edit_models || [];
          if (catalogue.length) setAvatarEditModels(catalogue);
          if (data.result?.avatar_edit_model) setAvatarEditModel(data.result.avatar_edit_model);
          // Отказ модели показываем модалкой, а не строкой в углу: это решение
          // пользователя (другая модель или другое фото), а не уведомление.
          const blocked = data.result?.frames_blocked || [];
          if (blocked.length) {
            setFrameBlock({
              ...blocked[0],
              shotNumber,
              spentUsd: charged ? formatUsd(charged * 0.05) : '',
            });
          }
          setFramesNotice(
            framesFailed && !framesMade
              ? `Кадр не нарисовался: модель вернула пустое изображение.${spent}`
              : framesFailed
                ? `Готово кадров: ${framesMade}. Не получилось: ${framesFailed} — модель вернула пустое изображение.${spent}`
                : '',
          );
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

  // Записать озвучку БЕЗ платной генерации видео и остаться в редакторе.
  // shotNumber — перезаписать одну реплику, everything — перечитать весь текст
  // одним дублем. Дубль каждый раз новый, поэтому уже одобренные куски дорожки
  // переносятся из прошлого превью: иначе правка одной реплики меняла бы голос
  // во всём ролике.
  const handleGenerateVoice = async (shotNumber = null, everything = false) => {
    if (ttsProvider === 'elevenlabs' && !elevenLabsKey) {
      alert('ElevenLabs API key required. Set it in Settings.');
      return;
    }
    if (voiceGenerating) return;

    setVoiceGenerating(true);
    setVoiceShot(shotNumber);
    setVoiceNotice('');

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
      if (elevenLabsKey && !isManagedKey(elevenLabsKey)) headers['X-ElevenLabs-Key'] = elevenLabsKey;

      const res = await fetch(getApiUrl('/api/saasshorts/generate'), {
        method: 'POST',
        headers,
        body: JSON.stringify({
          script: scriptToSend,
          voice_id: selectedVoice,
          voice_name: selectedVoiceLabel,
          voice_selection_source: voiceSelectionSource,
          tts_provider: ttsProvider,
          minimax_voice_id: minimaxVoice,
          minimax_voice_name: minimaxVoiceLabel,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          selected_face_url: selectedFace || undefined,
          plate_urls: plateUrls,
          video_mode: videoMode,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          use_platform_keys: usePlatformKeys,
          voice_only: true,
          // Галочка «одним дублем» действует в момент записи — иначе человек
          // слушал бы дорожку со стыками, а ролик снимался бы под другую.
          revoice_all: everything || revoiceAll,
          revoice_shots: shotNumber ? [shotNumber] : [],
          // Дубли, которые уже слушали, переезжают в новый джоб как есть.
          voice_job_id: voiceJobId || undefined,
          // Пересъёмка: у снятого ролика звук уже есть, и перезаписывать его
          // целиком значит отправить на пересъёмку все говорящие кадры.
          source_job_id: sourceJobId || undefined,
        }),
      });

      if (!res.ok) {
        let msg = 'Voiceover failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const { job_id: newVoiceJobId } = await res.json();

      // Свой опрос, как и у кадров: основной genStatus/step не трогаем, чтобы
      // остаться в редакторе раскадровки.
      const deadline = Date.now() + 5 * 60 * 1000;
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await new Promise((r) => setTimeout(r, 2000));
        if (Date.now() > deadline) throw new Error('Voiceover timed out');
        const poll = await fetch(getApiUrl(`/api/saasshorts/status/${newVoiceJobId}`), { headers: authHeaders() });
        if (!poll.ok) continue;
        const data = await poll.json();
        if (data.status === 'completed') {
          applyGeneratedShots(data.result, { voice: newVoiceJobId });
          // Подмена движка или модели слышна как «диктор вместо человека» —
          // об этом говорим словами, а не оставляем догадываться на слух.
          setVoiceNotice((data.result?.quality_warnings || []).join(' '));
          break;
        }
        if (data.status === 'failed') {
          throw new Error(data.error || 'Voiceover failed');
        }
      }
    } catch (e) {
      alert(`Не удалось записать озвучку: ${e.message}`);
    } finally {
      setVoiceGenerating(false);
      setVoiceShot(null);
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
          voice_name: selectedVoiceLabel,
          voice_selection_source: voiceSelectionSource,
          tts_provider: ttsProvider,
          minimax_voice_id: minimaxVoice,
          minimax_voice_name: minimaxVoiceLabel,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          selected_face_url: selectedFace || undefined,
          plate_urls: plateUrls,
          video_mode: videoMode,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          // Кадры ведущего в платном рендере рисует та же модель, что выбрана в
          // превью, — иначе выбор чинил бы только превью.
          avatar_edit_model: avatarEditModel || undefined,
          reusable_head_template_id: selectedHeadTemplate || undefined,
          reusable_lipsync_model: lipSyncModel,
          use_platform_keys: usePlatformKeys,
          background_music: backgroundMusic,
          clip_vision_qc: clipVisionQc,
          broll_image_first: brollImageFirst,
          // Пересъёмка готового ролика: снятые кадры переезжают из прошлого
          // джоба, платим только за изменённые и явно отмеченные.
          source_job_id: sourceJobId || undefined,
          // Кадры, одобренные в предпросмотре, переезжают в рендер как есть:
          // в ролик попадает ровно то, что человек утвердил, и второй раз за
          // ту же картинку никто не платит.
          frames_job_id: framesJobId || undefined,
          // Ролик снимается под ту дорожку, которую человек послушал: заново
          // записанный дубль звучит иначе, и липсинк лёг бы под другой звук.
          voice_job_id: voiceJobId || undefined,
          regenerate_shots: reshootShots,
          // Прослушанная дорожка уже записана так, как надо, — перечитывать её
          // на съёмке значит выбросить утверждённый дубль и записать другой.
          revoice_all: voiceJobId ? false : revoiceAll,
        }),
      });

      if (!res.ok) {
        let msg = 'Generation failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      setJobId(data.job_id);
      saveLastJob(activeWorkspaceKey, data.job_id);
      persistWorkspaceSnapshot({ jobId: data.job_id, genStatus: 'processing', genResult: null, step: 3 });
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
          voice_name: selectedVoiceLabel,
          voice_selection_source: voiceSelectionSource,
          tts_provider: ttsProvider,
          minimax_voice_id: minimaxVoice,
          minimax_voice_name: minimaxVoiceLabel,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          selected_face_url: selectedFace || undefined,
          plate_urls: plateUrls,
          retry_job_id: jobId,
          video_mode: videoMode,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          avatar_edit_model: avatarEditModel || undefined,
          // Повтор после сбоя тоже начинает с одобренных кадров и дубля: то,
          // что уже нарисовано, записано и оплачено, не переделывается.
          frames_job_id: framesJobId || undefined,
          voice_job_id: voiceJobId || undefined,
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
      saveLastJob(activeWorkspaceKey, data.job_id);
      persistWorkspaceSnapshot({ jobId: data.job_id, genStatus: 'processing', genResult: null });
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

  // Каталог редакторов кадра — справочник, ключи не нужны. Тянем один раз, чтобы
  // модель можно было сменить заранее, а не только после отказа.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(getApiUrl('/api/saasshorts/frame-editors'));
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || !data.models?.length) return;
        setAvatarEditModels((prev) => (prev.length ? prev : data.models));
        setAvatarEditModel((prev) => prev || data.default || '');
      } catch (e) {
        console.error('Frame editors catalogue failed:', e);
      }
    })();
    return () => { cancelled = true; };
  }, []);

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
    setActorUploadStatus('Загружаю и сохраняю...');
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
        let msg = 'Не удалось загрузить фото';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      if (data.url) {
        setUploadedActorPreview({ localPreview, serverUrl: data.url });
        setSelectedActor(data.url);
        setActorUploadStatus(data.saved ? 'Сохранено в аватары и выбрано.' : 'Выбрано локально: сохранить в галерею не вышло.');
        if (data.saved) await refreshActorGallery();
      }
    } catch (err) {
      console.error('Upload failed:', err);
      setActorUploadStatus(err.message || 'Не удалось загрузить фото');
    }
  };

  // Портрет едет тем же маршрутом, что и аватар: одна ручка загрузки, одно
  // хранилище. Разное у них только назначение — этот кадр уходит источником
  // лица в постановочные кадры говорящих шотов.
  const handleFaceUpload = async (file) => {
    if (!file) return;
    setUploadingFace(true);
    setFaceUploadStatus('Загружаю портрет...');
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/actor-upload'), {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) {
        let msg = 'Не удалось загрузить портрет';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
      const data = await res.json();
      if (data.url) {
        setSelectedFace(data.url);
        setFaceUploadStatus('Портрет выбран источником лица.');
      }
    } catch (err) {
      console.error('Face upload failed:', err);
      setFaceUploadStatus(err.message || 'Не удалось загрузить портрет');
    } finally {
      setUploadingFace(false);
    }
  };

  // Плита ракурса, принесённая руками. Ходит в тот же эндпоинт, что и кадры
  // шотов, но с именем камеры: тогда картинка становится общей для всех
  // говорящих кадров этого ракурса и не рисуется вовсе.
  const handlePlateUpload = async (camera, file) => {
    if (!file) return;
    setUploadingPlate(camera);
    setPlateUploadStatus('Загружаю ракурс...');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('camera', camera);
    try {
      const res = await fetch(getApiUrl('/api/saasshorts/storyboard-frame-upload'), {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) {
        let msg = 'Не удалось загрузить ракурс';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
      const data = await res.json();
      const url = data.image_url || data.url;
      if (url) {
        setPlateUrls((prev) => ({ ...prev, [camera]: url }));
        setPlateUploadStatus('Ракурс загружен — рисоваться он не будет.');
      }
    } catch (err) {
      console.error('Plate upload failed:', err);
      setPlateUploadStatus(err.message || 'Не удалось загрузить ракурс');
    } finally {
      setUploadingPlate('');
    }
  };

  const handleCopy = (text, label) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(''), 2000);
  };

  const handleReset = () => {
    workspaceResettingRef.current = true;
    latestWorkspaceSnapshotRef.current = null;
    if (workspaceSyncTimerRef.current) {
      clearTimeout(workspaceSyncTimerRef.current);
      workspaceSyncTimerRef.current = null;
    }
    if (activeContentPlanContext) {
      localStorage.removeItem(activeWorkspaceKey);
      clearLastJob(activeWorkspaceKey);
      if (authToken && activeContentPlanContext) {
        fetch(getApiUrl(workspaceEndpoint(activeContentPlanContext)), {
          method: 'DELETE',
          headers: authHeaders(),
        }).catch(() => {});
      }
      clearActiveContentPlanContext();
      setWorkspaceContextState({
        activeContentPlanContext: null,
        pendingContentPlanContext: null,
      });
      setTopic('');
    } else {
      localStorage.removeItem(CACHE_KEY);
      clearLastJob(CACHE_KEY);
    }
    setStep(0);
    setAnalyzeError('');
    setAnalysis(null);
    setWebResearch(null);
    setScripts([]);
    setShotHistory([]);
    setFromCache(false);
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
    fallbackSeconds: targetDurationSeconds,
  });

  const estimateModePriceLabel = (modeId) => `~${formatUsd(estimateForMode(modeId).total)}`;
  const currentScript = scripts[selectedScript];
  const storyboardSelected = isStoryboardScript(currentScript);

  // Текст исходного сценария, который не попал ни в один кадр (кадры удалили
  // до генерации). Для уже готового ролика full_narration — единственная
  // уцелевшая копия удалённых реплик, поэтому предлагаем вернуть их кадром.
  const leftoverNarration = (() => {
    const narration = (currentScript?.full_narration || '').trim();
    if (!narration || !isStoryboardScript(currentScript)) return [];
    const norm = (text) => (text || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
    const known = norm([
      ...(currentScript.shots || []).map((shot) => shot.speech || ''),
      ...(currentScript.shots_archived || []).map((shot) => shot.speech || ''),
    ].join(' '));
    return narration
      .split(/(?<=[.!?…])\s+/)
      .map((sentence) => sentence.trim())
      .filter((sentence) => norm(sentence).length > 8 && !known.includes(norm(sentence)));
  })();

  // Кадры с репликой, но без описания сцены: видео-модель читает промпт, а он
  // строится из «Что в кадре» — такой кадр отрисуется наугад.
  const emptyShotNumbers = (currentScript?.shots || [])
    .filter((shot) => (shot.speech || '').trim() && !(shot.scene || '').trim())
    .map((shot) => shot.shot_number);

  // Кадры, за которые ещё не платили: у остальных уже есть стартовый кадр,
  // своё фото или снятый клип, и повторная генерация — деньги на ветер.
  const shotHasFrame = (shot) => Boolean(
    shot?.clip_url || shot?.image_preview || shot?.local_url || shot?.image_url || shot?.preview_frame_url
  );
  const missingFrameCount = (currentScript?.shots || []).filter((shot) => !shotHasFrame(shot)).length;

  // Говорящие кадры снимаются двумя общими ракурсами на весь ролик, поэтому
  // платим не за кадр, а за камеру: b-roll по картинке на кадр, говорящие —
  // максимум две на всех. Оценка сверху: уже отрисованный ракурс бесплатен.
  const AVATAR_FRAMING_COUNT = 2;
  const isBrollShot = (shot) => (shot?.visual_type || '')
    .toLowerCase().replace(/[-_]/g, '').includes('broll');

  // Какой ракурс достанется говорящему кадру. Та же очередь, что на бэкенде
  // (`_avatar_framing_for_shot`): шёпот всегда доверительный, остальные по кругу.
  // Показываем это в карточке, потому что раньше про ракурс писала сценарная
  // модель — в текст, который снимающий код не читает. Камеры отличаются точкой
  // съёмки, а не крупностью: дистанция у всех одна, иначе склейка читается
  // наездом, а не сменой камеры.
  const CAMERA_LABELS = {
    front: 'прямо в камеру',
    side: 'вполоборота, сбоку',
    hush: 'доверительный, снизу',
  };
  const isWhisperShot = (shot) => /\[(whispers?|whispering)\]/i.test(shot?.speech || '');
  const talkingCameras = (() => {
    const byIndex = {};
    let order = 0;
    (currentScript?.shots || []).forEach((shot, index) => {
      if (isBrollShot(shot)) return;
      byIndex[index] = isWhisperShot(shot)
        ? 'hush'
        : (order % 2 === 0 ? 'front' : 'side');
      order += 1;
    });
    return byIndex;
  })();
  // Кадр, который задаёт место действия всем говорящим: его описание бэкенд
  // закрепляет за ролик целиком (`_pinned_avatar_set`), у остальных читает
  // только действие.
  const setDefiningShotIndex = (currentScript?.shots || [])
    .findIndex((shot) => !isBrollShot(shot));
  // У сценариев, снятых после разделения запросов, место лежит в своём поле, и
  // кадр 1 перестаёт быть «тем самым». У старых поля нет — там работает прежняя
  // схема, и подписи обязаны говорить правду про обе.
  const hasOwnSet = Boolean((currentScript?.set_prompt || '').trim());
  // Место, вписанное руками, перебивает комнату с фото ведущего; подобранное
  // ИИ — нет: та модель фото не видела и описывает комнату наугад.
  const setChosenByUser = hasOwnSet && currentScript?.set_source === 'user';
  // Мест может быть несколько — опция «менять локации». Первое всегда лежит и в
  // `set_scene`, поэтому редактируемое поле остаётся одним и тем же.
  const reelLocations = Array.isArray(currentScript?.set_scenes)
    ? currentScript.set_scenes.filter((place) => (place || '').trim())
    : [];
  const billableFrameCount = (() => {
    const missing = (currentScript?.shots || []).filter((shot) => !shotHasFrame(shot));
    const talking = missing.filter((shot) => !isBrollShot(shot)).length;
    return missing.length - talking + Math.min(talking, AVATAR_FRAMING_COUNT);
  })();

  // Пересъёмка готового ролика: клипы прошлого рендера переносятся в новый джоб,
  // поэтому платим только за кадры, которые реально снимаются заново.
  const sourceJobId = currentScript?._source_job_id || '';
  // Джоб предпросмотра кадров. Кадр кэшируется по промпту, но лежит в папке
  // своего джоба, поэтому рендеру нужно сказать, откуда его взять.
  const framesJobId = currentScript?._frames_job_id || '';
  // Джоб прослушанной озвучки: дубль каждый раз новый, поэтому рендеру надо
  // сказать, где лежит тот самый, который человек утвердил.
  const voiceJobId = currentScript?._voice_job_id || '';
  // Записанная дорожка: сама запись, её длина и во сколько платных клипов
  // распадётся по ней съёмка. Живёт в сценарии, а не в стейте, — иначе после
  // перезагрузки страницы слушать было бы нечего.
  const voicePreview = (() => {
    const track = currentScript?._voice_track || '';
    if (!track) return null;
    const shots = currentScript?.shots || [];
    return {
      url: getApiUrl(track),
      seconds: Number(currentScript?._voice_seconds || 0),
      clips: Number(currentScript?._voice_clips || 0),
      model: currentScript?._voice_model || '',
      voiceId: currentScript?._voice_id || '',
      voiceName: currentScript?._voice_name || '',
      voiceSource: currentScript?._voice_selection_source || '',
      shootCost: currentScript?._voice_shoot_cost,
      // Реплики, переписанные уже после записи. Съёмка перезапишет их сама, но
      // услышать их до готового ролика можно только записав озвучку ещё раз.
      stale: shots
        .filter((shot) => typeof shot.voice_speech === 'string'
          && (shot.speech || '').trim() !== shot.voice_speech)
        .map((shot, index) => shot.shot_number ?? (index + 1)),
    };
  })();
  const renderPlan = (() => {
    const shots = currentScript?.shots || [];
    const baseline = currentScript?._render_baseline;
    const wholeNarration = shots.map((shot) => (shot.speech || '').trim()).filter(Boolean).join(' ');
    if (!sourceJobId || !Array.isArray(baseline) || !baseline.length) {
      return { reshoot: shots, reused: [], revoicedText: '', isReshoot: false };
    }
    if (revoiceAll) {
      // Один дубль на весь ролик — значит и звук у каждого кадра новый.
      return { reshoot: shots, reused: [], revoicedText: wholeNarration, isReshoot: true };
    }
    const baseByNumber = new Map(baseline.map((shot, i) => [shot.shot_number ?? (i + 1), shot]));
    // Озвучка теперь пошотная: правка одной реплики переписывает её кусок звука
    // и только его, поэтому соседние клипы больше не сгорают вместе с ней.
    const speechChanged = (shot, index) => {
      const before = baseByNumber.get(shot.shot_number ?? (index + 1));
      return !before || (shot.speech || '').trim() !== (before.speech || '').trim();
    };
    const changed = (shot, index) => {
      const before = baseByNumber.get(shot.shot_number ?? (index + 1));
      if (!before) return true;
      return ['scene', 'generation_prompt', 'visual_type', 'image_path', 'local_url'].some(
        (field) => (shot[field] || '') !== (before[field] || ''),
      );
    };
    const reshoot = shots.filter((shot, index) => (
      !shot.clip_url
      || reshootShots.includes(shot.shot_number ?? (index + 1))
      || speechChanged(shot, index)
      || changed(shot, index)
    ));
    const reshootSet = new Set(reshoot);
    return {
      reshoot,
      reused: shots.filter((shot) => !reshootSet.has(shot)),
      // Платим за озвучку ровно тех реплик, что переписаны.
      revoicedText: shots
        .filter((shot, index) => speechChanged(shot, index))
        .map((shot) => (shot.speech || '').trim())
        .join(' '),
      isReshoot: true,
    };
  })();
  const reshootEstimate = (() => {
    if (!renderPlan.isReshoot) return null;
    // Пустой список кадров оценщик читает как «сценария ещё нет» и выдаёт цену
    // типового ролика — а платить не за что: считаем ноль явно.
    if (!renderPlan.reshoot.length) {
      return { total: 0, voiceCost: 0, videoCost: 0, brollCost: 0 };
    }
    const billable = estimateSaasVideoCost({
      text: renderPlan.revoicedText || '',
      videoMode,
      ttsProvider,
      brollMode: 'off',
      hasSelectedActor: Boolean(selectedActor),
      script: { ...currentScript, shots: renderPlan.reshoot },
      storyboardGenerationMode,
    });
    // Озвучиваются только переписанные реплики — остальные куски звука берутся
    // из прошлого рендера как есть.
    const voiceCost = renderPlan.revoicedText ? billable.voiceCost : 0;
    return {
      total: billable.videoCost + billable.brollCost + voiceCost,
      voiceCost,
      videoCost: billable.videoCost,
      brollCost: billable.brollCost,
    };
  })();
  const reshootCost = reshootEstimate ? reshootEstimate.total : null;

  // Свёрнутая строка «ведущий + голос» над раскрывающимися панелями.
  const selectedActorPreviewUrl = (() => {
    if (!selectedActor) return '';
    if (uploadedActorPreview?.serverUrl === selectedActor) return uploadedActorPreview.localPreview;
    return actorGallery.find((actor) => actor.url === selectedActor)?.url || selectedActor;
  })();
  const minimaxVoiceLabel = (MINIMAX_VOICE_OPTIONS[language] || MINIMAX_VOICE_OPTIONS.en)
    .find((voice) => voice.id === minimaxVoice)?.name || minimaxVoice;
  const knownDefaultVoiceNames = {
    D5RRIJYa9pFwxiSpbGbR: 'Victoria',
    '21m00Tcm4TlvDq8ikWAM': 'Rachel',
    '29vD33N1CtxCmqQRPOHJ': 'Drew',
    EXAVITQu4vr4xnSDxMaL: 'Bella',
    ErXwobaYiN019PkySvjV: 'Antoni',
  };
  const selectedVoiceLabel = ttsProvider === 'fal_minimax'
    ? minimaxVoiceLabel
    : (voices.find((voice) => voice.voice_id === selectedVoice)?.name
      || selectedVoiceName
      || knownDefaultVoiceNames[selectedVoice]
      || selectedVoice
      || 'по умолчанию');

  // Насколько сценарий разошёлся с выбранным хронометражом. Допуск тот же, что
  // на бэкенде (`_TARGET_DURATION_TOLERANCE`). Считаем по той же оценке, что
  // показана рядом, и на каждой правке кадров: выбрать 15 секунд и получить 24
  // молча — это то, о чём человек узнавал уже по готовому ролику.
  const storyboardSeconds = scripts[selectedScript]
    ? estimateStoryboardSeconds(scripts[selectedScript], '')
    : 0;
  const durationGap = storyboardSeconds && targetDurationSeconds
    && Math.abs(storyboardSeconds - targetDurationSeconds) > 2
    ? storyboardSeconds - targetDurationSeconds
    : 0;

  // Шаг открывается только когда его есть чем отрисовать — те же условия, что
  // у блоков ниже, иначе переход даёт пустой экран. Отсюда же берётся «вперёд»:
  // уйдя с готового ролика назад в настройку, вернуться к нему было нельзя,
  // хотя и логи, и результат лежат в снапшоте.
  const stepReady = [
    true,
    Boolean(analysis),
    Boolean(scripts[selectedScript]),
    Boolean(jobId),
    Boolean(genResult),
  ];
  // Ближайший доступный шаг, а не step±1: пропущенный шаг (сценарий импортирован
  // без анализа, ролик открыт из галереи без логов) не должен упирать стрелку.
  const previousReadyStep = [...stepReady.keys()].filter((i) => i < step && stepReady[i]).pop();
  const nextReadyStep = [...stepReady.keys()].find((i) => i > step && stepReady[i]);

  // ─── Render Steps ─────────────────────────────────────────────────

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      {/* На телефоне вложенные отступы (страница → панель → блок кадров →
          карточка) съедали 39% ширины экрана — на узких экранах поля меньше. */}
      <div className="max-w-5xl mx-auto p-4 pb-28 sm:p-6 md:pb-8 lg:p-8">
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

        {/* Progress Steps — сама полоска и есть навигация: шаг с данными
            открывается кликом, стрелки ходят по доступным шагам в обе стороны. */}
        <div className="flex items-center gap-2 mb-8">
          <button
            type="button"
            onClick={() => setStep(previousReadyStep)}
            disabled={previousReadyStep === undefined}
            title="Назад"
            aria-label="Назад"
            className="shrink-0 w-7 h-7 rounded-full bg-white/5 text-zinc-400 flex items-center justify-center transition-colors enabled:hover:bg-white/10 enabled:hover:text-white disabled:opacity-25"
          >
            <ChevronLeft size={14} />
          </button>
          {['Setup', 'Analysis', 'Configure', 'Generate', 'Result'].map((label, i) => (
            <React.Fragment key={i}>
              {i > 0 && <div className={`flex-1 h-px ${i <= step ? 'bg-violet-500' : 'bg-white/10'}`} />}
              <button
                type="button"
                onClick={() => setStep(i)}
                disabled={!stepReady[i] || i === step}
                title={stepReady[i] ? label : `${label} — пока нечего показать`}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  i === step ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30' :
                  stepReady[i] ? 'bg-violet-500/10 text-violet-400 hover:bg-violet-500/20 hover:text-violet-300' :
                  'bg-white/5 text-zinc-600 cursor-not-allowed'
                }`}
              >
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  i < step ? 'bg-violet-500 text-white' :
                  i === step ? 'bg-violet-500/30 text-violet-300' :
                  stepReady[i] ? 'bg-violet-500/20 text-violet-300' :
                  'bg-white/10 text-zinc-600'
                }`}>
                  {i < step ? <Check size={10} /> : i + 1}
                </span>
                <span className="hidden sm:inline">{label}</span>
              </button>
            </React.Fragment>
          ))}
          <button
            type="button"
            onClick={() => setStep(nextReadyStep)}
            disabled={nextReadyStep === undefined}
            title="Вперёд"
            aria-label="Вперёд"
            className="shrink-0 w-7 h-7 rounded-full bg-white/5 text-zinc-400 flex items-center justify-center transition-colors enabled:hover:bg-white/10 enabled:hover:text-white disabled:opacity-25"
          >
            <ChevronRight size={14} />
          </button>
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

              {/* ── Ведущий: аватар + голос ─────────────────────────────
                  Выбор аватара и озвучки живёт здесь (на Setup), ДО платного
                  превью кадров на шаге раскадровки — чтобы кадры сразу строились
                  с нужным лицом и голосом, а не переигрывались после. */}
              <div data-section="presenter-section" className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                <div>
                  <label className="flex items-center gap-2 text-sm font-medium text-zinc-300">
                    <User size={14} /> Аватар проекта{' '}
                    {(scriptFormat === 'storyboard_v3' || String(videoMode || '').startsWith('storyboard')) && (
                      <span className="text-zinc-600">(необязательно)</span>
                    )}
                  </label>
                  <p className="text-xs text-zinc-500 mt-2 mb-3">
                    Лицо ведущего берётся из фото. Без аватара система придумает случайного человека —
                    в каждом ролике разного.
                  </p>

                  {/* Что выбрано сейчас: одна строка вместо простыни настроек.
                      Всё остальное раскрывается по кнопке. */}
                  <div className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-black/20 p-2.5">
                    <div className="h-12 w-9 shrink-0 overflow-hidden rounded-md border border-white/10 bg-zinc-900">
                      {selectedActorPreviewUrl ? (
                        <button
                          type="button"
                          onClick={() => setLightbox({
                            src: selectedActorPreviewUrl,
                            alt: 'Выбранный аватар',
                            caption: 'Аватар — источник причёски, фигуры и одежды',
                          })}
                          title="Открыть аватар на весь экран"
                          className="h-full w-full cursor-zoom-in"
                        >
                          <img src={selectedActorPreviewUrl} alt="Выбранный аватар" className="h-full w-full object-cover" />
                        </button>
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-zinc-700">
                          <User size={14} />
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-zinc-200">
                        {selectedActor
                          ? (actorGallery.find((actor) => actor.url === selectedActor)?.description || 'Аватар выбран')
                          : 'Случайное лицо (аватар не выбран)'}
                      </p>
                      <p className="truncate text-[11px] text-zinc-500">
                        Голос: {selectedVoiceLabel}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setAvatarPickerOpen((open) => !open)}
                      className="rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-zinc-300 transition-colors hover:border-primary/40 hover:text-violet-200"
                    >
                      {avatarPickerOpen ? 'Свернуть' : 'Сменить аватар'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setVoicePickerOpen((open) => !open)}
                      className="rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-zinc-300 transition-colors hover:border-primary/40 hover:text-violet-200"
                    >
                      {voicePickerOpen ? 'Свернуть' : 'Сменить голос'}
                    </button>
                  </div>

                  {avatarPickerOpen && (<>
                  {/* Пол актёра */}
                  <div className="mb-3 flex flex-wrap items-center gap-3">
                    <span className="text-xs font-medium text-zinc-400">Пол</span>
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

                  {/* Сохранённые аватары. Ряды НЕ обрезаем: скролл с фиксированной
                      высотой резал плитки пополам — казалось, что вёрстка поехала. */}
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
                    ) : (
                      <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 lg:grid-cols-8">
                        {actorGallery.map((img, i) => (
                          <button
                            key={img.url}
                            type="button"
                            onClick={() => {
                              setSelectedActor(img.url);
                              // Привязка — только дефолт. Ручной выбор голоса
                              // клик по фотографии аватара больше не заменяет.
                              if (img.voice?.voice_id && voiceSelectionSource !== 'manual') {
                                setSelectedVoice(img.voice.voice_id);
                                setSelectedVoiceName(img.voice.voice_name || img.voice.voice_id);
                                setVoiceSelectionSource('avatar_binding');
                              }
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
                        {/* Загрузка — такая же плитка в конце сетки: отдельная
                            широкая кнопка и висящее сбоку превью выглядели как
                            два оторванных друг от друга элемента. Загруженное
                            фото сразу выбирается и приезжает в сетку. */}
                        <label className="flex aspect-[3/4] cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-white/15 bg-white/5 text-center text-[10px] leading-tight text-zinc-500 transition-colors hover:border-primary/40 hover:text-violet-200">
                          {uploadedActorPreview && !uploadedActorPreview.serverUrl ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <>
                              <Upload size={14} />
                              <span>Своё фото</span>
                            </>
                          )}
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
                      </div>
                    )}
                    {!loadingGallery && actorGallery.length === 0 && (
                      <p className="text-[11px] text-zinc-500">
                        Сохранённых аватаров пока нет — загрузи фото, чтобы у роликов было одно лицо.
                      </p>
                    )}
                    {actorUploadStatus && (
                      <p className={`text-[10px] ${/не удалось|fail/i.test(actorUploadStatus) ? 'text-red-300' : 'text-zinc-500'}`}>
                        {actorUploadStatus}
                      </p>
                    )}
                  </div>

                  {/* Портрет крупно — отдельно от аватара. На общем плане лицо
                      занимает проценты кадра, и генератор дорисовывает черты
                      сам: отсюда «человек меняется» между дублями. */}
                  <div className="mt-4 space-y-2 rounded-xl border border-white/10 bg-black/20 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-semibold text-zinc-300">Портрет крупно (источник лица)</p>
                      {selectedFace && (
                        <button
                          type="button"
                          onClick={() => { setSelectedFace(null); setFaceUploadStatus(''); }}
                          className="text-[11px] text-zinc-500 hover:text-zinc-200"
                        >
                          Убрать
                        </button>
                      )}
                    </div>
                    <p className="text-[11px] leading-relaxed text-zinc-500">
                      Необязательно. Лицо берётся отсюда, а причёска, фигура и одежда — с аватара выше.
                      Нужен один человек, вертикальный кадр по грудь, лицо крупно и в резкости.
                    </p>
                    <div className="flex items-center gap-3">
                      <div className="h-16 w-12 shrink-0 overflow-hidden rounded-md border border-white/10 bg-zinc-900">
                        {selectedFace ? (
                          <button
                            type="button"
                            onClick={() => setLightbox({
                              src: getApiUrl(selectedFace),
                              alt: 'Портрет ведущего',
                              caption: 'Портрет — источник лица',
                            })}
                            title="Открыть портрет на весь экран"
                            className="h-full w-full cursor-zoom-in"
                          >
                            <img src={getApiUrl(selectedFace)} alt="Портрет ведущего" className="h-full w-full object-cover" />
                          </button>
                        ) : (
                          <div className="flex h-full w-full items-center justify-center text-zinc-700">
                            <User size={14} />
                          </div>
                        )}
                      </div>
                      <label className="cursor-pointer rounded-lg border border-dashed border-white/15 px-3 py-2 text-[11px] text-zinc-400 transition-colors hover:border-primary/40 hover:text-violet-200">
                        {uploadingFace ? (
                          <span className="flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Загружаю...</span>
                        ) : (
                          <span className="flex items-center gap-1"><Upload size={12} /> {selectedFace ? 'Заменить портрет' : 'Загрузить портрет'}</span>
                        )}
                        <input
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={async (e) => {
                            const file = e.target.files?.[0];
                            await handleFaceUpload(file);
                            e.target.value = '';
                          }}
                        />
                      </label>
                    </div>
                    {faceUploadStatus && (
                      <p className={`text-[10px] ${/не удалось|fail/i.test(faceUploadStatus) ? 'text-red-300' : 'text-zinc-500'}`}>
                        {faceUploadStatus}
                      </p>
                    )}
                  </div>

                  {/* Свои ракурсы. Всё, что загружено сюда, не рисуется: ни
                      одного платного вызова на постановку, и лицо ровно то,
                      которое человек выбрал, — генератор его не пересочиняет. */}
                  <div className="mt-4 space-y-2 rounded-xl border border-white/10 bg-black/20 p-3">
                    <p className="text-xs font-semibold text-zinc-300">Свои ракурсы ведущего</p>
                    <p className="text-[11px] leading-relaxed text-zinc-500">
                      Необязательно. Загруженный ракурс становится общим для всех говорящих
                      кадров этой камеры и не генерируется — это ноль платных кадров на
                      постановку. Шёпотные кадры берут фронтальный.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { key: 'front', label: 'Фронт' },
                        { key: 'side', label: 'Вполоборота' },
                      ].map((slot) => (
                        <div key={slot.key} className="space-y-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-medium text-zinc-400">{slot.label}</span>
                            {plateUrls[slot.key] && (
                              <button
                                type="button"
                                onClick={() => {
                                  setPlateUrls((prev) => {
                                    const next = { ...prev };
                                    delete next[slot.key];
                                    return next;
                                  });
                                  setPlateUploadStatus('');
                                }}
                                className="text-[10px] text-zinc-500 hover:text-zinc-200"
                              >
                                Убрать
                              </button>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="h-16 w-9 shrink-0 overflow-hidden rounded-md border border-white/10 bg-zinc-900">
                              {plateUrls[slot.key] ? (
                                <button
                                  type="button"
                                  onClick={() => setLightbox({
                                    src: getApiUrl(plateUrls[slot.key]),
                                    alt: `Ракурс «${slot.label}»`,
                                    caption: `Ракурс «${slot.label}» — загружен вручную`,
                                  })}
                                  title="Открыть на весь экран"
                                  className="h-full w-full cursor-zoom-in"
                                >
                                  <img
                                    src={getApiUrl(plateUrls[slot.key])}
                                    alt={`Ракурс «${slot.label}»`}
                                    className="h-full w-full object-cover"
                                  />
                                </button>
                              ) : (
                                <div className="flex h-full w-full items-center justify-center text-zinc-700">
                                  <User size={14} />
                                </div>
                              )}
                            </div>
                            <label className="cursor-pointer rounded-lg border border-dashed border-white/15 px-2 py-1.5 text-[10px] text-zinc-400 transition-colors hover:border-primary/40 hover:text-violet-200">
                              {uploadingPlate === slot.key ? (
                                <span className="flex items-center gap-1"><Loader2 size={11} className="animate-spin" /> Загружаю...</span>
                              ) : (
                                <span className="flex items-center gap-1"><Upload size={11} /> {plateUrls[slot.key] ? 'Заменить' : 'Загрузить'}</span>
                              )}
                              <input
                                type="file"
                                accept="image/*"
                                className="hidden"
                                onChange={async (e) => {
                                  const file = e.target.files?.[0];
                                  await handlePlateUpload(slot.key, file);
                                  e.target.value = '';
                                }}
                              />
                            </label>
                          </div>
                        </div>
                      ))}
                    </div>
                    {plateUploadStatus && (
                      <p className={`text-[10px] ${/не удалось|fail/i.test(plateUploadStatus) ? 'text-red-300' : 'text-zinc-500'}`}>
                        {plateUploadStatus}
                      </p>
                    )}
                  </div>
                  </>)}
                </div>

                {/* Движок озвучки (TTS provider) */}
                {voicePickerOpen && (<>
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                    <Volume2 size={14} /> Движок озвучки
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
                      Сначала ElevenLabs. Если голос из библиотеки требует платный план или падает — озвучка продолжится через fal MiniMax.
                    </p>
                  )}
                  {ttsProvider === 'fal_minimax' && (
                    <p className="text-[10px] text-zinc-500 mt-2">
                      Озвучка через баланс fal.ai. Ключ ElevenLabs в этом режиме не нужен.
                    </p>
                  )}
                </div>

                {(ttsProvider === 'auto' || ttsProvider === 'fal_minimax') && (
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Голос fal MiniMax (резервный)
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
                      Используется сразу в режиме fal MiniMax или как запасной, если ElevenLabs не сработал в режиме Auto.
                    </p>
                  </div>
                )}

                {/* Голос озвучки (ElevenLabs) */}
                {ttsProvider !== 'fal_minimax' && (() => {
                  const boundVoice = actorGallery.find((a) => a.url === selectedActor)?.voice;
                  const manualVoiceOverridesBinding = Boolean(
                    boundVoice?.voice_id
                    && selectedVoice
                    && selectedVoice !== boundVoice.voice_id,
                  );
                  return (
                    <div>
                      <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                        <Volume2 size={14} /> Голос озвучки {language === 'es' ? '(испанский)' : language === 'ru' ? '(русский)' : '(английский)'}
                      </label>
                      {boundVoice?.voice_id && (
                        <div className={`mb-2 flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${
                          manualVoiceOverridesBinding
                            ? 'border-amber-400/30 bg-amber-500/10 text-amber-100'
                            : 'border-violet-400/30 bg-violet-500/10 text-violet-200'
                        }`}>
                          <Volume2 size={12} className="mt-0.5 shrink-0" />
                          {manualVoiceOverridesBinding ? (
                            <span>
                              Голос <b>{selectedVoiceLabel}</b> выбран вручную и не заменён привязкой аватара
                              {' '}<b>{boundVoice.voice_name || boundVoice.voice_id}</b>.
                            </span>
                          ) : (
                            <span>
                              У аватара есть привязанный голос <b>{boundVoice.voice_name || boundVoice.voice_id}</b>.
                              Он используется как дефолт, пока ты не выберешь другой.
                            </span>
                          )}
                        </div>
                      )}
                      {(() => {
                        // Filter voices by language/accent
                        const filtered = voices.length > 0
                          ? voices.filter((v) => voiceVisibleForLanguage(v, language, actorGender))
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
                                  onClick={() => selectVoiceManually(v.voice_id, v.name)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      selectVoiceManually(v.voice_id, v.name);
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
                            onChange={(voiceId) => {
                              const option = opts.find((item) => item.id === voiceId);
                              selectVoiceManually(voiceId, option?.name || voiceId);
                            }}
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
                              Голос задан вручную по ID. Убедись, что он русский или с русским акцентом.
                            </div>
                          );
                        }

                        const selectedScore = voiceLanguageScore(selectedVoiceMeta, language);
                        if (selectedScore === 0) return null;

                        return (
                          <div className="mt-2 p-2.5 rounded-lg border border-amber-500/20 bg-amber-500/10 text-[11px] text-amber-200">
                            Голос не похож на русский ({selectedVoiceMeta.labels?.accent || 'акцент неизвестен'}).
                            Для естественной русской речи выбери русский голос или вставь его ID ниже.
                          </div>
                        );
                      })()}
                      {/* Ручной ID нужен раз в год — прячем, чтобы не мозолил глаза. */}
                      <details className="mt-3 rounded-lg border border-white/10 bg-black/20">
                        <summary className="cursor-pointer list-none px-3 py-2 text-[11px] text-zinc-500 hover:text-zinc-300">
                          Ввести ID голоса вручную
                        </summary>
                        <div className="border-t border-white/10 p-3">
                          <input
                            value={selectedVoice}
                            onChange={(e) => selectVoiceManually(e.target.value.trim())}
                            className="input-field text-xs font-mono"
                            placeholder="voice_id из ElevenLabs..."
                          />
                          <p className="text-[10px] text-zinc-600 mt-1">
                            Пригодится, если нужный голос есть в ElevenLabs, но не попал в список выше.
                          </p>
                        </div>
                      </details>
                      <p className="text-[10px] text-zinc-600 mt-1">
                        {actorGender === 'female' ? 'Женские' : 'Мужские'} голоса · нажми на динамик, чтобы послушать
                      </p>
                    </div>
                  );
                })()}
                </>)}
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
                <p className="text-[10px] text-zinc-600 mt-1">В ИИ-режиме варианты сценариев строятся вокруг этой темы. В ручном режиме тема нужна для заголовка, caption и визуальных подсказок.</p>
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

              <div data-section="target-duration-section">
                <div id="target-duration-label" className="block text-sm font-medium text-zinc-300 mb-1">Длина ролика</div>
                <p className="text-[11px] text-zinc-500 mb-3">
                  {scriptMode === 'custom'
                    ? 'Для своего текста длительность определяется фактической озвучкой.'
                    : 'Применяется ко всем вариантам сценария. Итог может отличаться на пару секунд из-за темпа озвучки.'}
                </p>
                <div
                  role="group"
                  aria-labelledby="target-duration-label"
                  className="grid grid-cols-2 sm:grid-cols-4 gap-2"
                >
                  {TARGET_DURATION_OPTIONS.map((option) => {
                    const active = targetDurationSeconds === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        aria-pressed={active}
                        disabled={scriptMode === 'custom'}
                        onClick={() => setTargetDurationSeconds(option.value)}
                        className={`min-h-[64px] rounded-lg border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                          active
                            ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                            : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                        }`}
                      >
                        <span className="block text-sm font-medium">{option.label}</span>
                        <span className="mt-1 block text-[10px] leading-4 text-zinc-500">{option.desc}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Ритм перебивок. Умолчание — редкая перебивка: она стоит целый
                  клип и тарифицируется от трёх секунд, поэтому чередование
                  заметно поднимает смету. Опция для тех, кому важнее монтаж. */}
              {scriptFormat === 'storyboard_v3' && (
                <div data-section="broll-rhythm-section">
                  <label className="flex cursor-pointer items-start gap-2.5">
                    <input
                      type="checkbox"
                      checked={brollBetweenTalking}
                      onChange={(event) => setBrollBetweenTalking(event.target.checked)}
                      disabled={scriptMode === 'custom'}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-violet-500 disabled:opacity-40"
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-zinc-300">
                        Перебивка между кадрами с ведущим
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-snug text-zinc-500">
                        Два говорящих кадра подряд не ставятся — между ними всегда вставка.
                        Ролик монтажнее, но дороже: перебивка это отдельный клип, и короче трёх
                        секунд он не тарифицируется.
                      </span>
                    </span>
                  </label>
                </div>
              )}

              {/* Смена локаций. Умолчание — одно место на ролик: так он читается
                  как одна съёмка и стоит две плиты. Каждая новая комната — своя
                  плита на каждую снимающую в ней камеру, поэтому опция. */}
              {scriptFormat === 'storyboard_v3' && (
                <div data-section="changing-locations-section">
                  <label className="flex cursor-pointer items-start gap-2.5">
                    <input
                      type="checkbox"
                      checked={changingLocations}
                      onChange={(event) => setChangingLocations(event.target.checked)}
                      disabled={scriptMode === 'custom'}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-violet-500 disabled:opacity-40"
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-zinc-300">
                        Менять локации по ходу ролика
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-snug text-zinc-500">
                        ИИ подбирает до трёх мест и меняет их каждые три говорящих кадра —
                        другой угол той же квартиры или другое место, как ляжет по тексту.
                        Дороже: каждая комната это свои постановочные кадры. Комнату с фото
                        ведущего при этом заменяет выдуманная.
                      </span>
                    </span>
                  </label>
                </div>
              )}

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
                <h3 className="text-sm font-medium text-zinc-300">Ваши ИИ-ролики</h3>
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
                              `≈${estimateStoryboardSeconds(script, script.full_narration || '')} сек`,
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
            <div className="glass-panel p-4 sm:p-6 space-y-5">
              <h2 className="text-lg font-semibold">Настройка ролика</h2>
              <p className="text-sm text-zinc-500">
                Сценарий: <strong className="text-zinc-300">{scripts[selectedScript].title}</strong>
              </p>

              {storyboardSelected && (
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3 sm:p-4 space-y-4">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
                        <Film size={14} /> Кадры ролика
                      </h3>
                      <p className="text-[11px] text-zinc-500 mt-0.5 max-w-xl">
                        Ролик собирается по кадрам. Для каждого укажи, что в кадре и что человек говорит.
                        Кадры можно добавлять, дублировать, удалять и перетаскивать за уголок <GripVertical size={11} className="inline align-[-1px] text-zinc-500" />, чтобы поменять порядок.
                      </p>
                      {/* Одно место на все говорящие кадры и своя очередь камер —
                          иначе непонятно, почему описание «другой ракурс» ничего
                          не меняет, а фон вдруг остаётся прежним. */}
                      {setDefiningShotIndex >= 0 && (
                        <p className="text-[11px] text-zinc-500 mt-1 max-w-xl">
                          {reelLocations.length > 1
                            ? `Место меняется по ходу ролика: ${reelLocations.length} локации, каждые три говорящих кадра.`
                            : <>Все говорящие кадры сняты в одном месте — {hasOwnSet
                              ? 'оно в поле «Место действия ролика» ниже'
                              : `его задаёт кадр ${setDefiningShotIndex + 1}`}.</>}
                          {' '}Между ними чередуются камеры, поэтому ракурс в описании кадра указывать не нужно.
                        </p>
                      )}
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
                      <span
                        className="rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-zinc-400"
                        title="≈ длина озвучки. По ней собирается ролик — видео не длиннее речи, лишние кадры не оплачиваются."
                      >
                        ~{storyboardSeconds} сек
                      </span>
                      {durationGap !== 0 && (
                        <span
                          className="rounded-full bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-200"
                          title={`Хронометраж выбран на первом шаге: ~${targetDurationSeconds} сек. Длину ролика задаёт озвучка, так что лишний текст — это лишние секунды и лишние оплаченные кадры. Уберите или сократите реплики, либо смените цель.`}
                        >
                          {durationGap > 0 ? 'длиннее' : 'короче'} цели
                          на {Math.abs(durationGap)} сек
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Пересъёмка готового ролика: клипы прошлого рендера
                      переносятся в новый джоб, поэтому неизменённые кадры
                      ничего не стоят — платим за то, что правили. */}
                  {renderPlan.isReshoot && (
                    <div className="rounded-xl border border-green-500/20 bg-green-500/[0.05] p-3">
                      <p className="text-[11px] text-green-100/80">
                        Ролик уже снят. {renderPlan.reshoot.length === 0
                          ? (<>
                              Все {renderPlan.reused.length} {pluralShots(renderPlan.reused.length)} возьмём
                              из прошлого рендера — пересборка бесплатна.
                              Кнопка «Переснять» на кадре заставит его сняться ещё раз, даже если текст не менялся.
                            </>)
                          : (<>
                              Возьмём {renderPlan.reused.length} {pluralShots(renderPlan.reused.length)} из прошлого
                              рендера бесплатно, снимем заново {renderPlan.reshoot.length}
                              {reshootCost !== null ? ` (~${formatUsd(reshootCost)})` : ''}.
                              Кнопка «Переснять» на кадре заставит его сняться ещё раз, даже если текст не менялся.
                            </>)}
                      </p>
                      {/* Пошотная озвучка оставляет на границе правки один стык.
                          Замеры говорят, что он тише обычного перехода между
                          предложениями, но если он всё же слышен — вот выход. */}
                      <label className="mt-2 flex items-start gap-2 text-[11px] text-green-100/70">
                        <input
                          type="checkbox"
                          checked={revoiceAll}
                          onChange={(event) => setRevoiceAll(event.target.checked)}
                          className="mt-0.5 w-3.5 h-3.5 rounded border-green-500/40 bg-black/40 text-green-400 focus:ring-green-500"
                        />
                        <span>
                          Перечитать весь текст одним дублем
                          <span className="text-green-100/40"> — ни одного стыка в озвучке, но тогда переснимаются все говорящие кадры</span>
                        </span>
                      </label>
                    </div>
                  )}

                  {/* Кадры без описания сцены: ИИ-генерация видео читает промпт,
                      собранный из «Что в кадре», а не реплику. */}
                  {emptyShotNumbers.length > 0 && (
                    <div className="flex flex-col gap-2 rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-3 sm:flex-row sm:items-center sm:justify-between">
                      <p className="max-w-md text-[11px] text-amber-100/80">
                        В {emptyShotNumbers.length} {pluralShots(emptyShotNumbers.length)} есть реплика, но не описано, что в кадре.
                        Без этого нейросеть нарисует случайную сцену.
                      </p>
                      <button
                        type="button"
                        onClick={() => fillShotDetails(emptyShotNumbers)}
                        disabled={fillingShots.length > 0}
                        className="btn-secondary shrink-0 px-3 py-2 text-[12px] flex items-center justify-center gap-1.5 disabled:opacity-50"
                      >
                        {fillingShots.length > 0
                          ? (<><Loader2 size={13} className="animate-spin" /> Заполняю…</>)
                          : (<><Sparkles size={13} /> Заполнить {emptyShotNumbers.length} {pluralShots(emptyShotNumbers.length)} ИИ</>)}
                      </button>
                    </div>
                  )}
                  {fillError && (
                    <p className="text-[11px] text-red-300">{fillError}</p>
                  )}

                  {/* Место действия — одно на весь ролик и своё поле. Пока оно
                      жило внутри кадра 1, в плиты вместе с комнатой уезжало всё,
                      что там оказалось: «static camera» — и обе камеры выходили
                      одним анфасом, «a beautiful woman» — и редактор рисовал своё
                      лицо вместо выбранного. */}
                  <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[12px] font-semibold text-zinc-200">
                        Место действия ролика
                      </span>
                      <button
                        type="button"
                        onClick={pickReelSet}
                        disabled={pickingSet}
                        className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-zinc-400 transition-colors hover:border-primary/40 hover:text-violet-200 disabled:opacity-50"
                        title="Подобрать место по тексту ролика (Gemini, бесплатно)"
                      >
                        {pickingSet
                          ? (<><Loader2 size={11} className="animate-spin" /> Подбираю…</>)
                          : (<><Sparkles size={11} /> Подобрать ИИ</>)}
                      </button>
                    </div>
                    <textarea
                      className="input-field min-h-[58px] resize-y py-2 text-sm leading-relaxed"
                      value={currentScript?.set_scene || ''}
                      onChange={(event) => updateSelectedScript({
                        set_scene: event.target.value,
                        set_prompt: event.target.value,
                        set_source: 'user',
                      })}
                      placeholder="Комната, свет, поверхности, что на них стоит — здесь снят весь ролик"
                    />
                    {/* Что сейчас в силе — видно, а не угадывается. Описание,
                        подобранное ИИ, фото ведущего не видело: там уже снята
                        своя комната, и текст её перекрашивал (светлая дневная
                        кухня уезжала в вечернюю). Поэтому текст вступает в дело
                        только когда место вписал человек. */}
                    {reelLocations.length > 1 && (
                      <ul className="space-y-0.5 text-[10px] leading-snug text-zinc-500">
                        {reelLocations.map((place, index) => (
                          <li key={`${index}-${place.slice(0, 12)}`}>
                            <span className="text-zinc-400">Локация {index + 1}:</span> {place}
                            {index === 0 ? ' (её и правит поле выше)' : ''}
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="text-[10px] leading-snug text-zinc-500">
                      {reelLocations.length > 1
                        ? 'Локации меняются по ходу ролика — каждая снимается своими постановочными кадрами.'
                        : setChosenByUser
                          ? 'Снимаем в этом месте — текст перебивает комнату с фото ведущего.'
                          : 'Сейчас комната берётся с фото ведущего — та же, что за спиной на портрете. Впиши своё место, если нужна другая.'}
                      {' '}Только место: людей, ракурс и внешность сюда писать не нужно — человека
                      ставит приложение, камеры чередует само. Пока кадры не отрисованы,
                      переподбор ничего не стоит.
                    </p>
                  </div>

                  {/* Озвучка идёт первой: её длина — это длина ролика, её паузы —
                      границы кадров, а длинная реплика режется на несколько
                      платных клипов. Стоит копейки, поэтому слушаем до съёмки. */}
                  <div className="rounded-xl border border-sky-500/20 bg-sky-500/[0.04] p-3 space-y-3">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div className="max-w-md">
                        <h4 className="text-[12px] font-semibold text-sky-100 flex items-center gap-1.5">
                          <Volume2 size={13} /> Озвучка
                        </h4>
                        <p className="text-[11px] text-zinc-400 mt-0.5">
                          По ней собирается ролик: её длина задаёт длину видео, паузы — границы кадров,
                          а длинная реплика снимается несколькими платными клипами.
                          Послушай и перезапиши до съёмки — после неё голос уже не поменять,
                          не переснимая всё заново.
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleGenerateVoice(null, false)}
                          disabled={voiceGenerating}
                          className="btn-secondary px-3 py-2 text-[12px] flex items-center justify-center gap-1.5 disabled:opacity-50"
                        >
                          {voiceGenerating && voiceShot === null
                            ? (<><Loader2 size={13} className="animate-spin" /> Записываю…</>)
                            : voicePreview
                              ? (<><RefreshCw size={13} /> Обновить озвучку</>)
                              : (<><Volume2 size={13} /> Записать озвучку</>)}
                        </button>
                        {voicePreview && (
                          <button
                            type="button"
                            onClick={() => handleGenerateVoice(null, true)}
                            disabled={voiceGenerating}
                            title="Перечитать весь текст одним дублем: ни одного стыка, но все реплики звучат заново"
                            className="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-zinc-300 transition-colors hover:border-sky-400/40 hover:text-sky-200 disabled:opacity-50"
                          >
                            Перечитать всё одним дублем
                          </button>
                        )}
                      </div>
                    </div>

                    {voicePreview && (
                      <div className="space-y-2">
                        <audio
                          controls
                          preload="metadata"
                          src={voicePreview.url}
                          className="h-9 w-full"
                        />
                        <p className="text-[11px] font-medium text-sky-100">
                          Голос: {voicePreview.voiceName || selectedVoiceLabel}
                          {voicePreview.voiceId ? ` · ${voicePreview.voiceId}` : ''}
                        </p>
                        <p className="text-[11px] text-zinc-400">
                          {voicePreview.seconds ? `${voicePreview.seconds.toFixed(1)} с` : 'длина неизвестна'}
                          {voicePreview.clips
                            ? ` · снимется ${voicePreview.clips} ${pluralClips(voicePreview.clips)}${
                                voicePreview.shootCost != null ? ` (~${formatUsd(voicePreview.shootCost)})` : ''
                              }`
                            : ''}
                          {voicePreview.model ? ` · ${voicePreview.model}` : ''}
                        </p>
                        {voicePreview.stale.length > 0 && (
                          <p className="text-[11px] text-amber-100/80">
                            После записи изменились реплики {voicePreview.stale.join(', ')}.
                            При съёмке они перезапишутся сами, но услышать их заранее можно,
                            только записав озвучку ещё раз.
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  {voiceNotice && (
                    <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-3">
                      <p className="text-[11px] text-amber-100/80">{voiceNotice}</p>
                    </div>
                  )}

                  {/* Сгенерировать стартовые кадры (Flux) до платного видео,
                      чтобы увидеть и утвердить композицию каждого шота. */}
                  <div className="rounded-xl border border-primary/20 bg-primary/[0.04] p-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-[11px] text-zinc-400 max-w-md">
                      Сгенерируй стартовые кадры и проверь композицию до платной генерации видео.
                      Говорящие кадры снимаются двумя общими ракурсами — за них платишь дважды,
                      сколько бы их ни было; у каждой перебивки свой кадр. Готовые пропускаются.
                      Перегенерить кадр или заменить его своим фото можно по кнопке на самом кадре.
                    </p>
                    <button
                      type="button"
                      onClick={() => handleGenerateFrames(null)}
                      disabled={framesGenerating || missingFrameCount === 0}
                      className="btn-secondary shrink-0 px-3 py-2 text-[12px] flex items-center justify-center gap-1.5 disabled:opacity-50"
                    >
                      {framesGenerating && framesShot === null
                        ? (<><Loader2 size={13} className="animate-spin" /> Генерирую…</>)
                        : missingFrameCount === 0
                          ? (<><Check size={13} /> Все кадры готовы</>)
                          : (<><Sparkles size={13} /> Сгенерить недостающие: {missingFrameCount} (~{formatUsd(billableFrameCount * 0.05)})</>)}
                    </button>
                  </div>

                  {framesNotice && (
                    <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-3">
                      <p className="text-[11px] text-amber-100/80">{framesNotice}</p>
                    </div>
                  )}

                  {/* Какой моделью рисуется ведущий. Строка появляется, как
                      только бэкенд прислал каталог: до этого выбирать не из чего. */}
                  {avatarEditModels.length > 0 && (
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-[11px] text-zinc-400">
                        Ведущего в кадр ставит{' '}
                        <span className="text-zinc-200">
                          {(avatarEditModels.find((m) => m.id === avatarEditModel) || avatarEditModels[0]).title}
                        </span>
                        . Если модель откажет — предложу сменить её, подменять сама она не будет.
                      </p>
                      <select
                        value={avatarEditModel || avatarEditModels[0].id}
                        onChange={(e) => setAvatarEditModel(e.target.value)}
                        disabled={framesGenerating}
                        className="input-field shrink-0 text-[12px] py-1.5"
                      >
                        {avatarEditModels.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.title}{model.blocked ? ' — уже отказала' : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

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
                      const shotNumber = shot.shot_number ?? (shotIndex + 1);
                      const markedForReshoot = reshootShots.includes(shotNumber);
                      const inputId = `storyboard-frame-${selectedScript}-${shotIndex}`;
                      const isBroll = isBrollShot(shot);
                      // Сколько экрана достанется кадру и сколько мы за него
                      // заплатим. Расходятся они у коротких реплик: клип короче
                      // пола модель не отдаёт, а счёт выставляет по отданному.
                      const plannedSeconds = shotPlannedSeconds(scripts[selectedScript], shot, storyboardSeconds);
                      const clipFloorSeconds = shotClipFloorSeconds(shot);
                      const shotIsShorterThanItsClip = plannedSeconds > 0
                        && plannedSeconds < clipFloorSeconds - 0.05;

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
                              {/* Что по этому кадру уже оплачено и лежит на диске:
                                  снятый клип или только стартовый кадр. */}
                              {clipUrl && markedForReshoot ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                                  <RefreshCw size={10} /> Переснимем
                                </span>
                              ) : clipUrl ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-green-500/15 px-2 py-0.5 text-[10px] font-semibold text-green-300">
                                  <Check size={10} /> Снят
                                </span>
                              ) : previewUrl ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold text-violet-300">
                                  <Check size={10} /> Кадр готов
                                </span>
                              ) : (
                                <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-zinc-500">
                                  Без кадра
                                </span>
                              )}
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

                          <div className="grid gap-3 sm:grid-cols-[120px,minmax(0,1fr)]">
                            {/* Кадр вертикальный: во всю ширину карточки он вырастал
                                на полтора экрана и растягивал раскадровку на десять
                                тысяч пикселей. Держим превью миниатюрой, а на
                                телефоне ставим кнопки рядом с ним, а не под ним. */}
                            <div className="flex gap-2 sm:block">
                              <div className="aspect-[9/16] w-[104px] shrink-0 overflow-hidden rounded-lg border border-white/10 bg-zinc-950 sm:mb-2 sm:w-full">
                                {previewUrl ? (
                                  // Кнопка, а не картинка с onClick: кадр открывается
                                  // и с клавиатуры, и читалка называет его вслух.
                                  <button
                                    type="button"
                                    onClick={() => setLightbox({
                                      src: previewUrl,
                                      alt: `Кадр ${shotIndex + 1}`,
                                      caption: `Кадр ${shotIndex + 1} — нажми на фон или Esc, чтобы закрыть`,
                                    })}
                                    title="Открыть кадр на весь экран"
                                    className="group h-full w-full cursor-zoom-in"
                                  >
                                    <img
                                      src={previewUrl}
                                      alt={`Кадр ${shotIndex + 1}`}
                                      className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
                                    />
                                  </button>
                                ) : (
                                  <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-center text-[10px] text-zinc-600">
                                    <Upload size={18} />
                                    Своё фото
                                  </div>
                                )}
                              </div>
                              <div className="flex min-w-0 flex-1 flex-col gap-2">
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
                              {/* Кадр уже снят: без явной отметки следующий рендер
                                  возьмёт готовый клип и денег не потратит. */}
                              {clipUrl && renderPlan.isReshoot && (
                                <button
                                  type="button"
                                  onClick={() => setReshootShots((prev) => (
                                    prev.includes(shotNumber)
                                      ? prev.filter((num) => num !== shotNumber)
                                      : [...prev, shotNumber]
                                  ))}
                                  title={markedForReshoot
                                    ? 'Не переснимать — оставить снятый клип'
                                    : 'Снять этот кадр заново при следующей генерации видео'}
                                  className={`w-full rounded-lg border px-2 py-1.5 text-[11px] flex items-center justify-center gap-1.5 transition-colors ${
                                    markedForReshoot
                                      ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
                                      : 'border-white/10 text-zinc-400 hover:border-amber-500/40 hover:text-amber-200'
                                  }`}
                                >
                                  <RefreshCw size={12} /> {markedForReshoot ? 'Не переснимать' : 'Переснять'}
                                </button>
                              )}
                              {shot.frame_status && (
                                <p className="text-[10px] text-zinc-500">{shot.frame_status}</p>
                              )}
                              </div>
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
                                {/* Ракурс — решение сборки, а не текста: она
                                    чередует камеры одного сета. Раньше это было
                                    невидимо, и человек просил крупный план в
                                    описании, где его никто не читает. */}
                                {!isBroll && talkingCameras[shotIndex] && (
                                  <span
                                    className="rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-zinc-400"
                                    title="Ракурс чередуется автоматически между говорящими кадрами, чтобы соседние склейки не читались как сбой. В описании кадра его задать нельзя."
                                  >
                                    Камера: {CAMERA_LABELS[talkingCameras[shotIndex]]}
                                  </span>
                                )}
                              </div>
                              <label className="space-y-1.5 text-xs text-zinc-400 block">
                                <div className="flex items-center justify-between gap-2">
                                  <span>
                                    {isBroll
                                      ? 'Что в кадре'
                                      : (shotIndex === setDefiningShotIndex && !hasOwnSet
                                        ? 'Что в кадре — место действия всего ролика'
                                        : 'Что делает')}
                                  </span>
                                  {/* Пустая сцена = случайная картинка: промпт для
                                      видео-модели строится именно отсюда. */}
                                  <button
                                    type="button"
                                    onClick={() => fillShotDetails([shot.shot_number])}
                                    disabled={fillingShots.includes(shot.shot_number)}
                                    className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-zinc-400 transition-colors hover:border-primary/40 hover:text-violet-200 disabled:opacity-50"
                                    title="Заполнить сцену, камеру и действие по реплике (Gemini, бесплатно)"
                                  >
                                    {fillingShots.includes(shot.shot_number)
                                      ? (<><Loader2 size={11} className="animate-spin" /> Заполняю…</>)
                                      : (<><Sparkles size={11} /> Заполнить ИИ</>)}
                                  </button>
                                </div>
                                <textarea
                                  className="input-field min-h-[58px] resize-y py-2 text-sm leading-relaxed"
                                  value={shot.scene || ''}
                                  onChange={(event) => handleSelectedScriptShot(shotIndex, 'scene', event.target.value)}
                                  placeholder={isBroll
                                    ? 'Опиши, что видно в кадре'
                                    : (shotIndex === setDefiningShotIndex && !hasOwnSet
                                      ? 'Комната, свет, что в руках — это место остаётся до конца ролика'
                                      : 'Поза, взгляд, что делают руки')}
                                />
                                {/* Место и камеру у говорящих кадров задаём не
                                    словами: комната одна на весь ролик, ракурсы
                                    чередует сборка. Без этой строчки поле снова
                                    заполняли текстом вида «ракурс чуть сменился»,
                                    которого в картинке никогда не будет. */}
                                {!isBroll && (hasOwnSet || shotIndex !== setDefiningShotIndex) && (
                                  <p className="text-[10px] leading-snug text-zinc-500">
                                    {setChosenByUser
                                      ? 'Место — из поля «Место действия ролика» выше'
                                      : (hasOwnSet
                                        ? 'Место — с фото ведущего, одно на весь ролик'
                                        : `Место то же, что в кадре ${setDefiningShotIndex + 1}`)}
                                    {' '}— новую комнату или ракурс отсюда не заказать.
                                    Пиши, что меняется в самом человеке.
                                  </p>
                                )}
                              </label>
                              <label className="space-y-1.5 text-xs text-zinc-400 block">
                                <span>{isBroll ? 'Текст за кадром (озвучка)' : 'Что говорит'}</span>
                                <textarea
                                  className="input-field min-h-[58px] resize-y py-2 text-sm leading-relaxed"
                                  value={shot.speech || ''}
                                  onChange={(event) => handleSelectedScriptShot(shotIndex, 'speech', event.target.value)}
                                  placeholder={isBroll ? 'Что звучит голосом, пока показываем вставку (можно оставить пустым)' : 'Реплика для этого кадра'}
                                />
                                {/* Реплика короче пола клипа — единственное место,
                                    где счёт растёт молча: на экране кадр мелькнёт,
                                    а модель снимет и посчитает свой минимум. Видно
                                    это должно быть здесь, до оплаты, а не в отчёте
                                    после. Сборка потом дотянет кадр соседней
                                    тишиной, но занимать её не всегда есть у кого. */}
                                {shotIsShorterThanItsClip && (
                                  <p className="text-[10px] leading-snug text-amber-400/80">
                                    Коротко: {plannedSeconds.toFixed(1)} с речи при клипе от{' '}
                                    {clipFloorSeconds.toFixed(1)} с — платим за полный.
                                    Добавь слов или слей с соседним кадром.
                                  </p>
                                )}
                              </label>
                              {/* Записанная реплика: послушать именно её, увидеть
                                  её длину (её задаёт голос, а не поле «секунды»)
                                  и заказать другой дубль, не трогая остальные. */}
                              {(shot.voice_url || shot.voice_seconds > 0) && (
                                <div className="-mt-1 flex flex-wrap items-center gap-2">
                                  {shot.voice_url && (
                                    <audio
                                      controls
                                      preload="none"
                                      src={getApiUrl(shot.voice_url)}
                                      className="h-8 w-full max-w-[240px]"
                                    />
                                  )}
                                  <span className="text-[10px] text-zinc-500">
                                    {Number(shot.voice_seconds || 0).toFixed(1)} с
                                    {shot.voice_clips > 1 ? ` · ${shot.voice_clips} ${pluralClips(shot.voice_clips)}` : ''}
                                  </span>
                                  {typeof shot.voice_speech === 'string'
                                    && (shot.speech || '').trim() !== shot.voice_speech && (
                                    <span className="text-[10px] text-amber-300/80">текст изменился после записи</span>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => handleGenerateVoice(shotNumber)}
                                    disabled={voiceGenerating}
                                    title="Прочитать эту реплику заново. Остальные дубли останутся как есть."
                                    className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-zinc-400 transition-colors hover:border-sky-400/40 hover:text-sky-200 disabled:opacity-50"
                                  >
                                    {voiceGenerating && voiceShot === shotNumber
                                      ? (<><Loader2 size={11} className="animate-spin" /> Пишу…</>)
                                      : (<><Volume2 size={11} /> Перезаписать</>)}
                                  </button>
                                </div>
                              )}
                              {isBroll && (
                                <div className="-mt-1.5 space-y-1.5">
                                  <p className="text-[10px] text-zinc-600">
                                    В перебивке лицо не показываем, но озвучка продолжает звучать поверх вставки.
                                  </p>
                                  {/* Кадр перебивки рисуется отдельно от аватара, поэтому по
                                      тексту сцены мы не угадаем, наш это человек или чужой.
                                      Без галочки «женский силуэт со спины» — посторонняя
                                      женщина посреди ролика. */}
                                  <label className="flex items-start gap-2 text-[11px] text-zinc-400">
                                    <input
                                      type="checkbox"
                                      checked={Boolean(shot.actor_in_frame)}
                                      onChange={(event) => handleSelectedScriptShot(shotIndex, 'actor_in_frame', event.target.checked)}
                                      className="mt-0.5 w-3.5 h-3.5 rounded border-zinc-600 bg-black/50 text-violet-500 focus:ring-violet-500"
                                    />
                                    <span>
                                      В кадре наш персонаж
                                      <span className="text-zinc-600"> — со спины, руки или силуэт: кадр снимем с фото аватара, лицо не покажем</span>
                                    </span>
                                  </label>
                                </div>
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

                  {/* Реплики исходного сценария, которых нет ни в одном кадре —
                      для старых роликов это всё, что уцелело от удалённых кадров. */}
                  {leftoverNarration.length > 0 && (
                    <details className="rounded-xl border border-white/10 bg-black/20">
                      <summary className="cursor-pointer list-none px-3 py-2 text-xs text-zinc-400 hover:text-zinc-200">
                        Текст сценария вне кадров ({leftoverNarration.length}) — можно вернуть кадром
                      </summary>
                      <div className="space-y-2 border-t border-white/10 p-3">
                        {leftoverNarration.map((sentence, i) => (
                          <div key={i} className="flex items-start gap-2 rounded-lg border border-white/10 bg-white/[0.02] p-2">
                            <p className="min-w-0 flex-1 text-xs text-zinc-300">{sentence}</p>
                            <button
                              type="button"
                              onClick={() => addShotWithSpeech(sentence)}
                              className="shrink-0 rounded-md border border-white/10 px-2 py-1 text-[11px] text-zinc-300 transition-colors hover:border-primary/40 hover:text-violet-200"
                            >
                              Добавить кадром
                            </button>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  {/* Удалённые кадры: текст никуда не девается, кадр возвращается
                      одной кнопкой. Уезжает в метаданные ролика вместе с раскадровкой. */}
                  {(scripts[selectedScript].shots_archived || []).length > 0 && (
                    <details className="rounded-xl border border-white/10 bg-black/20">
                      <summary className="cursor-pointer list-none px-3 py-2 text-xs text-zinc-400 hover:text-zinc-200">
                        Удалённые кадры ({(scripts[selectedScript].shots_archived || []).length}) — текст сохранён, вернутся на свои места
                      </summary>
                      <div className="space-y-2 border-t border-white/10 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-[11px] text-zinc-500">
                            Кадры помнят свои позиции — можно спокойно разобрать раскадровку
                            на тестовый рендер и собрать обратно.
                          </p>
                          <button
                            type="button"
                            onClick={restoreAllArchivedShots}
                            className="shrink-0 rounded-md border border-primary/40 px-2 py-1 text-[11px] text-violet-200 transition-colors hover:bg-primary/10"
                          >
                            Вернуть все ({(scripts[selectedScript].shots_archived || []).length})
                          </button>
                        </div>
                        {(scripts[selectedScript].shots_archived || []).map((shot, i) => (
                          <div key={i} className="flex items-start gap-2 rounded-lg border border-white/10 bg-white/[0.02] p-2">
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-xs text-zinc-300">{shot.speech || shot.scene || 'Пустой кадр'}</p>
                              {shot.scene && shot.speech && (
                                <p className="truncate text-[10px] text-zinc-600">{shot.scene}</p>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={() => restoreArchivedShot(i)}
                              className="shrink-0 rounded-md border border-white/10 px-2 py-1 text-[11px] text-zinc-300 transition-colors hover:border-primary/40 hover:text-violet-200"
                            >
                              Вернуть
                            </button>
                            <button
                              type="button"
                              onClick={() => dropArchivedShot(i)}
                              aria-label="Забыть кадр"
                              title="Забыть окончательно"
                              className="shrink-0 rounded-md p-1 text-zinc-600 transition-colors hover:text-red-300"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
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

                // Пересъёмка: в счёт идёт только то, что снимается заново, —
                // иначе карточка обещала бы полную цену рядом с кнопкой
                // «Пересобрать ролик (бесплатно)».
                const shotCount = (currentScript?.shots || []).length;
                const rows = reshootEstimate
                  ? [
                      ['Длительность', `~${estimate.seconds} сек`],
                      ['Переснимаем', `${renderPlan.reshoot.length} из ${shotCount}`],
                      ['Озвучка', formatUsd(reshootEstimate.voiceCost)],
                      ['Видео', formatUsd(reshootEstimate.videoCost)],
                      ['B-roll', formatUsd(reshootEstimate.brollCost)],
                    ]
                  : [
                      ['Длительность', `~${estimate.seconds} сек`],
                      ['Озвучка', formatUsd(estimate.voiceCost)],
                      ['Видео', formatUsd(estimate.videoCost)],
                      ['Аватар', formatUsd(estimate.actorCost)],
                      ['B-roll', formatUsd(estimate.brollCost)],
                    ];

                return (
                  <div className="max-w-2xl p-4 bg-white/5 rounded-xl border border-white/10">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-sm font-semibold text-zinc-300">
                          {reshootEstimate ? 'Стоимость пересъёмки' : 'Примерная стоимость'}
                        </div>
                        <div className="text-[11px] text-zinc-600 mt-1">
                          {reshootEstimate
                            ? `Кадры, которые не менялись, переезжают из прошлого рендера бесплатно. С нуля этот ролик стоил бы ${formatUsd(estimate.total)}.`
                            : costDetails}
                        </div>
                      </div>
                      <span className="text-lg text-green-400 font-semibold whitespace-nowrap">
                        {formatUsd(reshootEstimate ? reshootEstimate.total : estimate.total)}
                      </span>
                    </div>

                    <div className="mt-4 space-y-2 text-sm">
                      {rows.map(([label, value]) => (
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
                  <><User size={14} /> Выбери аватара на шаге «Setup»</>
                ) : storyboardSelected && reshootCost !== null ? (
                  // Пересъёмка: снятые кадры переезжают из прошлого джоба, в цене
                  // только то, что снимается заново. Ничего не менялось — значит
                  // ролик просто пересобирается из готовых клипов.
                  renderPlan.reshoot.length === 0
                    ? (<><Film size={14} /> Пересобрать ролик (бесплатно)</>)
                    : (<><Film size={14} /> Переснять {renderPlan.reshoot.length} {pluralShots(renderPlan.reshoot.length)} ({formatUsd(reshootCost)})</>)
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
                    // Тот же порядок, что у `labels` выше, и это не вкусовщина.
                    // Раскадровка пишет построчно «создаю новое lip-sync видео
                    // Kling Avatar», от этого `isLipSyncJob` истинно и у неё —
                    // и когда состояние спрашивали про липсинк раньше, чем про
                    // раскадровку, оно искало маркеры `[lipsync N/3]`, которых
                    // раскадровочная задача не печатает никогда. Подписи брались
                    // от раскадровки, галочки от липсинка, и кружки не
                    // заполнялись до самого конца.
                    const stepDone = isStoryboardJob
                      ? (
                        i === 0 ? logStr.includes('[2/5]') || logStr.includes('[3/5]') :
                        i === 1 ? logStr.includes('[3/5]') || logStr.includes('[4/5]') || genStatus === 'completed' :
                        i === 2 ? logStr.includes('[4/5]') || genStatus === 'completed' :
                        genStatus === 'completed'
                      )
                      : isLipSyncJob
                      ? (
                        i === 0 ? logStr.includes('[lipsync 1/3]') || logStr.includes('[lipsync 2/3]') :
                        i === 1 ? logStr.includes('[lipsync 2/3]') || logStr.includes('[lipsync 3/3]') :
                        i === 2 ? logStr.includes('[lipsync 3/3]') || genStatus === 'completed' :
                        genStatus === 'completed'
                      )
                      : normalStepDone();
                    const stepActive = isStoryboardJob
                      ? (
                        i === 0 ? logStr.includes('[1/5]') && !stepDone :
                        i === 1 ? logStr.includes('[2/5]') && !stepDone :
                        i === 2 ? logStr.includes('[3/5]') && !stepDone :
                        logStr.includes('[4/5]') && genStatus !== 'completed'
                      )
                      : isLipSyncJob
                      ? (
                        i === 0 ? logStr.includes('post-process started') && !stepDone :
                        i === 1 ? logStr.includes('[lipsync 1/3]') && !logStr.includes('[lipsync 2/3]') :
                        i === 2 ? logStr.includes('[lipsync 2/3]') && !logStr.includes('[lipsync 3/3]') :
                        logStr.includes('[lipsync 3/3]') && genStatus !== 'completed'
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

                  {/* Сюда падают и предупреждения о длительностях липсинка, и
                      визуальные замечания vision-QC по конкретным клипам —
                      поэтому шапка нейтральная, а не «про talking-head». */}
                  {genResult.quality_warnings?.length > 0 && (
                    <div className="p-3 bg-amber-500/10 rounded-lg border border-amber-500/25 space-y-2">
                      <div className="flex items-center gap-2 text-xs font-semibold text-amber-200">
                        <AlertCircle size={14} />
                        Замечания автопроверки
                      </div>
                      <div className="space-y-1">
                        {genResult.quality_warnings.map((warning, i) => (
                          <p key={i} className="text-xs text-amber-100/80">{warning}</p>
                        ))}
                      </div>
                      <p className="text-[11px] text-amber-100/50">
                        Это подсказки ИИ, а не блокировка: решай сам, стоит ли перегенерить кадр.
                      </p>
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
                  <div className="flex flex-wrap gap-3 pt-2">
                    <a
                      href={getApiUrl(genResult.video_url)}
                      download
                      className="btn-primary px-4 py-2 text-sm flex items-center gap-2"
                    >
                      <Download size={14} /> Download
                    </a>
                    {/* Возврат в раскадровку: снятые кадры уже помечены, следующий
                        прогон переснимет только те, что тронули. */}
                    {isStoryboardScript(currentScript) && (
                      <button
                        onClick={() => { setStep(2); setGenStatus('idle'); setGenerating(false); }}
                        className="btn-secondary px-4 py-2 text-sm flex items-center gap-2"
                      >
                        <Film size={14} /> Переснять кадры
                      </button>
                    )}
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

      {/* Отказ редактора кадра: показываем дословный ответ модели и даём выбрать
          другую. Молчаливой подмены больше нет — она оплачивалась пользователем,
          который о ней не знал. */}
      <FrameEditorBlockedModal
        block={frameBlock}
        models={avatarEditModels}
        spentUsd={frameBlock?.spentUsd || ''}
        busy={framesGenerating}
        onClose={() => setFrameBlock(null)}
        onPick={(modelId) => {
          const retryShot = frameBlock?.shotNumber ?? null;
          setAvatarEditModel(modelId);
          setFrameBlock(null);
          handleGenerateFrames(retryShot, modelId);
        }}
      />

      {/* Кадр во весь экран. Живёт на уровне вкладки, а не внутри карточки шота:
          из карточки он был бы прижат её overflow и вылезал бы поверх соседей. */}
      <ImageLightbox
        src={lightbox?.src || ''}
        alt={lightbox?.alt || ''}
        caption={lightbox?.caption || ''}
        onClose={() => setLightbox(null)}
      />
    </div>
  );
}

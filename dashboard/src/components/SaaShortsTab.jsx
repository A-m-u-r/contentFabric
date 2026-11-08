import React, { useState, useEffect, useId, useRef, useLayoutEffect } from 'react';
import { Sparkles, Download, Copy, Check, ArrowLeft, ChevronRight, ChevronLeft, Loader2, AlertCircle, Volume2, User, Film, Terminal, ChevronDown, ChevronUp, RefreshCw, MessageSquare, Share2, Calendar, Upload, Save, Plus, Trash2 } from 'lucide-react';
import { getApiUrl } from '../config';
import FrameEditorBlockedModal from './FrameEditorBlockedModal';
import ImageLightbox from './ImageLightbox';
import MusicPicker, { musicRequestSettings } from './MusicPicker';
import StoryboardEditor from './StoryboardEditor';
import MediaPlayer from './MediaPlayer';
import './ShortsWorkflow.css';
import {
  loadBusinessProfiles,
  saveBusinessProfiles,
  loadSelectedProfileId,
  saveSelectedProfileId,
  presenterFromPreferences,
  preferencesFromPresenter,
  mergeProjectMetadata,
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

export function buildSaaSAnalyzeHeaders({
  baseHeaders = {},
  geminiApiKey,
  falKey,
  isManagedKey,
}) {
  return {
    ...baseHeaders,
    ...(geminiApiKey && !isManagedKey(geminiApiKey) ? { 'X-Gemini-Key': geminiApiKey } : {}),
    ...(falKey && !isManagedKey(falKey) ? { 'X-Fal-Key': falKey } : {}),
  };
}

export function isManualStoryboardImport(scriptMode, scriptFormat, text) {
  return scriptMode === 'custom' && scriptFormat === 'storyboard_v3'
    && /^\s*(?:#+\s*)?(?:КАДР|РљРђР”Р |SHOT)\s*\d+[^\n]*/im.test(text || '');
}

export function contentPlanScriptDefaults(item) {
  return item?.full_narration
    ? { scriptMode: 'custom', scriptFormat: item.format_hint || 'storyboard_v3', customScript: item.full_narration }
    : {};
}

export function videoPrefsForContentItem(item, saved = {}) {
  if (!item?.voice_id || (item.voice_preset_version && saved.voicePresetVersion === item.voice_preset_version)) {
    return saved;
  }
  const preset = {
    selectedVoice: item.voice_id,
    selectedVoiceName: item.voice_name || item.voice_id,
    voiceSelectionSource: 'manual',
    ttsProvider: item.tts_provider || 'elevenlabs',
    elevenLabsModel: item.elevenlabs_model || 'eleven_v4',
    elevenLabsStability: item.elevenlabs_stability ?? 0.5,
    elevenLabsSimilarity: item.elevenlabs_similarity ?? 0.75,
    voicePresetVersion: item.voice_preset_version || '',
  };
  return item.voice_preset_version ? { ...saved, ...preset } : { ...preset, ...saved };
}

const GENERATION_PRESET_VERSION = 'calm-ugc-20261004';

export function generationPresetPreferences(preset, saved = {}) {
  if (preset !== 'calm_ugc') return { ...saved, generationPreset: 'expressive' };
  return {
    ...saved,
    generationPreset: preset,
    generationPresetVersion: GENERATION_PRESET_VERSION,
    ttsProvider: 'elevenlabs',
    elevenLabsModel: 'eleven_v4',
    elevenLabsStability: 0.65,
    elevenLabsSimilarity: 0.75,
    backgroundMusic: true,
    storyboardGenerationMode: 'sliced_avatar',
    videoMode: 'storyboard_v3_standard',
  };
}

export function initializeGenerationPreferences(saved = {}) {
  if (saved.generationPreset === 'expressive'
    || (saved.generationPreset === 'calm_ugc' && saved.generationPresetVersion === GENERATION_PRESET_VERSION)) {
    return saved;
  }
  return generationPresetPreferences('calm_ugc', saved);
}

function GenerationPresetPicker({ value, onChange, disabled }) {
  return (
    <fieldset disabled={disabled} data-section="generation-preset-section">
      <legend className="mb-2 text-sm font-medium text-zinc-300">Подача</legend>
      <div className="inline-flex max-w-full rounded-lg border border-white/10 p-1 bg-black/20">
        {[['calm_ugc', 'Спокойный UGC'], ['expressive', 'Выразительная']].map(([id, label]) => (
          <button key={id} type="button" aria-pressed={value === id} onClick={() => onChange(id)}
            className={`min-h-10 px-3 py-2 rounded-md text-xs font-medium transition-colors disabled:opacity-50 ${
              value === id ? 'bg-white/10 text-white' : 'text-zinc-400 hover:text-white'
            }`}>
            {label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export function generationSpeech(text, preset) {
  const speech = text || '';
  return preset === 'calm_ugc'
    ? speech.replace(/\[[A-Za-z][^\]\n]*\]/g, ' ').replace(/\s{2,}/g, ' ').trim()
    : speech.trim();
}

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

const ELEVENLABS_MODEL_OPTIONS = [
  { id: 'eleven_v3', label: 'Eleven v3' },
  { id: 'eleven_v4', label: 'Eleven v4' },
];

export function elevenLabsTtsSettings(model, stability, similarity) {
  return model === 'eleven_v4'
    ? { elevenlabs_model: model, elevenlabs_stability: stability, elevenlabs_similarity: similarity }
    : { elevenlabs_model: model };
}

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
const useTextareaLayout = typeof window === 'undefined' ? useEffect : useLayoutEffect;

function AutoTextarea({ value, minRows = 3, className = '', ...props }) {
  const ref = useRef(null);
  useTextareaLayout(() => {
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
  onOpenSettings,
}) {
  const [workspaceContextState, setWorkspaceContextState] = useState(resolveActiveWorkspaceContext);
  const { activeContentPlanContext, pendingContentPlanContext } = workspaceContextState;
  const activeWorkspaceKey = activeContentPlanContext
    ? workspaceStorageKey(activeContentPlanContext)
    : CACHE_KEY;
  const [initialCache] = useState(() => (
    activeContentPlanContext
      ? loadLocalWorkspace(activeContentPlanContext)
      : loadCache(activeWorkspaceKey)
  ));
  const [initialVideoPrefs] = useState(() => initializeGenerationPreferences(
    initialCache?.videoPrefs || videoPrefsForContentItem(
      activeContentPlanContext?.item, loadVideoPrefs(activeWorkspaceKey),
    ),
  ));
  const planScriptDefaults = contentPlanScriptDefaults(activeContentPlanContext?.item);
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
  const [generationPreset, setGenerationPreset] = useState(initialVideoPrefs.generationPreset);
  const [videoMode, setVideoMode] = useState(initialVideoPrefs.videoMode || 'standard');
  const [description, setDescription] = useState(() => initialCache?.description || '');
  const [topic, setTopic] = useState(() => (
    initialCache?.topic ?? activeContentPlanContext?.topic ?? activeContentPlanContext?.item?.topic ?? ''
  ));
  const [businessName, setBusinessName] = useState(() => initialCache?.businessName || '');
  const [businessProfiles, setBusinessProfiles] = useState(() => loadBusinessProfiles());
  const [profilesLoading, setProfilesLoading] = useState(Boolean(authToken));
  const [profilesError, setProfilesError] = useState('');
  const [profilesReload, setProfilesReload] = useState(0);
  const [presenterSaving, setPresenterSaving] = useState(false);
  const [presenterSaveStatus, setPresenterSaveStatus] = useState(null);
  const [selectedBusinessProfileId, setSelectedBusinessProfileId] = useState(() => (
    initialCache?.businessProfileId || activeContentPlanContext?.profileId || loadSelectedProfileId() || ''
  ));
  const selectedBusinessProfile = businessProfiles.find((profile) =>
    String(businessProfileKey(profile)) === String(selectedBusinessProfileId));
  const profileContextRef = useRef(null);
  profileContextRef.current = { id: selectedBusinessProfileId, description, topic };
  const [scriptMode, setScriptMode] = useState(() => initialCache?.scriptMode || planScriptDefaults.scriptMode || 'ai'); // "ai" or "custom"
  const [scriptFormat, setScriptFormat] = useState(() => initialCache?.scriptFormat || planScriptDefaults.scriptFormat
    || (initialVideoPrefs.generationPreset === 'calm_ugc' ? 'storyboard_v3' : 'ugc'));
  const [changingLocations, setChangingLocations] = useState(
    () => Boolean(initialCache?.changingLocations),
  );
  const [brollBetweenTalking, setBrollBetweenTalking] = useState(
    () => initialCache?.brollBetweenTalking ?? initialVideoPrefs.generationPreset === 'calm_ugc',
  );
  const [targetDurationSeconds, setTargetDurationSeconds] = useState(
    () => initialCache?.targetDurationSeconds || 20,
  );
  const [textModel, setTextModel] = useState(() => initialCache?.textModel || 'fast');
  const [customScript, setCustomScript] = useState(() => initialCache?.customScript || planScriptDefaults.customScript || '');
  const manualStoryboardImport = isManualStoryboardImport(scriptMode, scriptFormat, customScript);
  const analyzeNeedsGemini = !manualStoryboardImport && !geminiApiKey;
  const [style, setStyle] = useState(initialCache?.style || 'ugc');
  const [language, setLanguage] = useState(initialVideoPrefs.language || 'ru');
  const [actorGender, setActorGender] = useState(initialVideoPrefs.actorGender || 'female');
  const [numScripts, setNumScripts] = useState(initialCache?.numScripts || 3);
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
  const storyboardFieldId = useId();

  // Step 2: Configure
  const [voices, setVoices] = useState([]);
  const [ttsProvider, setTtsProvider] = useState(() => initialVideoPrefs.ttsProvider || 'auto');
  const [elevenLabsModel, setElevenLabsModel] = useState(() => initialVideoPrefs.elevenLabsModel || 'eleven_v4');
  const [elevenLabsStability, setElevenLabsStability] = useState(() => initialVideoPrefs.elevenLabsStability ?? 0.65);
  const [elevenLabsSimilarity, setElevenLabsSimilarity] = useState(() => initialVideoPrefs.elevenLabsSimilarity ?? 0.75);
  const [brollMode, setBrollMode] = useState('mockup');
  const [storyboardGenerationMode, setStoryboardGenerationMode] = useState(initialVideoPrefs.storyboardGenerationMode || 'sliced_avatar');
  // Тонкие настройки пайплайна: по умолчанию всё включено, «!== false» —
  // чтобы старые prefs без этих полей не выключали фичи.
  const [backgroundMusic, setBackgroundMusic] = useState(() => initialVideoPrefs.backgroundMusic !== false);
  const [musicTrack, setMusicTrack] = useState(() => initialVideoPrefs.musicTrack || 'auto');
  const [musicVolume, setMusicVolume] = useState(() => initialVideoPrefs.musicVolume ?? 1);
  const [musicSaving, setMusicSaving] = useState(false);
  const [musicError, setMusicError] = useState('');
  const [clipVisionQc, setClipVisionQc] = useState(() => initialVideoPrefs.clipVisionQc !== false);
  const [brollImageFirst, setBrollImageFirst] = useState(() => initialVideoPrefs.brollImageFirst !== false);
  const [selectedVoice, setSelectedVoice] = useState(() => initialVideoPrefs.selectedVoice || 'D5RRIJYa9pFwxiSpbGbR');
  const [selectedVoiceName, setSelectedVoiceName] = useState(() => initialVideoPrefs.selectedVoiceName || '');
  const [voiceSelectionSource, setVoiceSelectionSource] = useState(
    () => initialVideoPrefs.voiceSelectionSource || 'default',
  );
  const [minimaxVoice, setMinimaxVoice] = useState(initialVideoPrefs.minimaxVoice || 'Russian_AmbitiousWoman');
  const [actorDescription, setActorDescription] = useState('');
  const [editedNarration, setEditedNarration] = useState(() => initialCache?.editedNarration || '');
  const [actorOptions, setActorOptions] = useState([]);
  const [selectedActor, setSelectedActor] = useState(() => initialVideoPrefs.selectedActor || null);
  // Блок ведущего свёрнут до одной строки «кто говорит + каким голосом».
  // Сетка аватаров сама открывается, пока ведущий не выбран.
  const [avatarPickerOpen, setAvatarPickerOpen] = useState(false);
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

  const currentVideoPrefs = {
    generationPreset,
    generationPresetVersion: GENERATION_PRESET_VERSION,
    selectedVoice, selectedVoiceName, voiceSelectionSource,
    voiceKey: `${language}-${actorGender}`,
    ttsProvider, elevenLabsModel, elevenLabsStability, elevenLabsSimilarity,
    voicePresetVersion: activeContentPlanContext?.item?.voice_preset_version || '',
    selectedActor: selectedActor || '', selectedFace: selectedFace || '', plateUrls,
    uploadedActorUrl: uploadedActorPreview?.serverUrl || '',
    backgroundMusic, musicTrack, musicVolume, clipVisionQc, brollImageFirst, videoMode, storyboardGenerationMode,
    minimaxVoice, language, actorGender,
  };

  const restoreVideoPreferences = (prefs) => {
    setGenerationPreset(prefs.generationPreset);
    if (prefs.ttsProvider) setTtsProvider(prefs.ttsProvider);
    if (prefs.elevenLabsModel) setElevenLabsModel(prefs.elevenLabsModel);
    if (prefs.elevenLabsStability != null) setElevenLabsStability(prefs.elevenLabsStability);
    if (prefs.elevenLabsSimilarity != null) setElevenLabsSimilarity(prefs.elevenLabsSimilarity);
    if (prefs.backgroundMusic != null) setBackgroundMusic(prefs.backgroundMusic);
    if (prefs.musicTrack != null) setMusicTrack(prefs.musicTrack);
    if (prefs.musicVolume != null) setMusicVolume(prefs.musicVolume);
    if (prefs.videoMode) setVideoMode(prefs.videoMode);
    if (prefs.storyboardGenerationMode) setStoryboardGenerationMode(prefs.storyboardGenerationMode);
    if (prefs.selectedVoice != null) setSelectedVoice(prefs.selectedVoice);
    if (prefs.selectedVoiceName != null) setSelectedVoiceName(prefs.selectedVoiceName);
    if (prefs.voiceSelectionSource) setVoiceSelectionSource(prefs.voiceSelectionSource);
    if (prefs.selectedActor != null) setSelectedActor(prefs.selectedActor || null);
    if (prefs.selectedFace != null) setSelectedFace(prefs.selectedFace || null);
    if (prefs.plateUrls) setPlateUrls(prefs.plateUrls);
    if (prefs.uploadedActorUrl != null) setUploadedActorPreview(prefs.uploadedActorUrl
      ? { localPreview: getApiUrl(prefs.uploadedActorUrl), serverUrl: prefs.uploadedActorUrl } : null);
    if (prefs.clipVisionQc != null) setClipVisionQc(prefs.clipVisionQc);
    if (prefs.brollImageFirst != null) setBrollImageFirst(prefs.brollImageFirst);
    if (prefs.language) setLanguage(prefs.language);
    if (prefs.actorGender) setActorGender(prefs.actorGender);
    if (prefs.minimaxVoice) setMinimaxVoice(prefs.minimaxVoice);
  };

  const selectGenerationPreset = (preset) => {
    restoreVideoPreferences(generationPresetPreferences(preset, currentVideoPrefs));
    if (preset === 'calm_ugc') {
      setScriptFormat('storyboard_v3');
      setBrollBetweenTalking(true);
      setChangingLocations(false);
    }
  };

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
    if (snapshot.videoPrefs) restoreVideoPreferences(initializeGenerationPreferences(snapshot.videoPrefs));
    setDescription(snapshot.description || '');
    setTopic(snapshot.topic ?? activeContentPlanContext?.topic ?? activeContentPlanContext?.item?.topic ?? '');
    setBusinessName(snapshot.businessName || '');
    setSelectedBusinessProfileId(snapshot.businessProfileId || activeContentPlanContext?.profileId || '');
    setScriptMode(snapshot.scriptMode || planScriptDefaults.scriptMode || 'ai');
    setScriptFormat(snapshot.scriptFormat || planScriptDefaults.scriptFormat || 'ugc');
    setTargetDurationSeconds(snapshot.targetDurationSeconds || 20);
    setBrollBetweenTalking(Boolean(snapshot.brollBetweenTalking));
    setChangingLocations(Boolean(snapshot.changingLocations));
    setTextModel(snapshot.textModel || 'fast');
    setCustomScript(snapshot.customScript || planScriptDefaults.customScript || '');
    setStyle(snapshot.style || 'ugc');
    setNumScripts(snapshot.numScripts || 3);
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
    videoPrefs: currentVideoPrefs,
    customScript,
    style,
    numScripts,
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
        style: snapshot.style,
        numScripts: snapshot.numScripts,
        videoPrefs: snapshot.videoPrefs,
        brollBetweenTalking: snapshot.brollBetweenTalking,
        changingLocations: snapshot.changingLocations,
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
    style,
    numScripts,
    analysis,
    webResearch,
    scripts,
    step,
    selectedScript,
    editedNarration,
    jobId,
    genStatus,
    genResult,
    generationPreset, videoMode, storyboardGenerationMode, selectedVoice, selectedVoiceName,
    voiceSelectionSource, ttsProvider, elevenLabsModel, elevenLabsStability, elevenLabsSimilarity,
    selectedActor, selectedFace, plateUrls, uploadedActorPreview, backgroundMusic, musicTrack, musicVolume,
    clipVisionQc, brollImageFirst, language, actorGender, minimaxVoice,
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
    const renderedJobId = (result.frames_only || result.voice_only) ? '' : jobIdFromVideoUrl(result.video_url);
    // Перерисованный кадр ложится по тому же адресу: ракурс общий на весь ролик,
    // имя файла не меняется. Браузер отдаёт картинку из кэша, и «Перегенерить»
    // выглядит как «ничего не произошло» даже когда кадр честно нарисован заново.
    const bust = result?.frames_only ? `?v=${Date.now()}` : '';
    const next = scripts.map((script) => {
      if (script.title !== title || !Array.isArray(script.shots) || !script.shots.length) return script;
      const shots = script.shots.map((shot, i) => {
        const g = byNumber.get(shot.shot_number ?? (i + 1));
        if (!g) return renderedJobId ? { ...shot, timeline_start: undefined, timeline_end: undefined } : shot;
        return {
          ...shot,
          preview_frame_url: g.preview_frame_url || shot.preview_frame_url,
          clip_url: g.clip_url || shot.clip_url,
          ...(renderedJobId ? { timeline_start: g.timeline_start, timeline_end: g.timeline_end } : {}),
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
            _voice_requested_model: elevenLabsModel,
            _voice_generation_preset: generationPreset,
            _voice_requested_stability: elevenLabsStability,
            _voice_requested_similarity: elevenLabsSimilarity,
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
        _source_video_url: result.video_url,
        _source_waveform: undefined,
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
    if (!authToken) { setProfilesLoading(false); return; }
    let cancelled = false;
    setProfilesLoading(true);
    setProfilesError('');
    fetch(getApiUrl('/api/user/business-profiles'), { headers: authHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error('Не удалось загрузить проекты из аккаунта.');
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        if (!Array.isArray(data.profiles)) throw new Error('Не удалось загрузить проекты из аккаунта.');
        // Keep browser-only projects available until the user saves them to the account.
        const local = loadBusinessProfiles();
        const next = mergeProjectMetadata(data.profiles, local, { includeLocalOnly: true });
        setBusinessProfiles(next);
        saveBusinessProfiles(next);
        const context = profileContextRef.current;
        const profile = next.find((item) => String(businessProfileKey(item)) === String(context.id));
        if (profile && !context.description.trim()) {
          handleLoadBusinessProfile(profile, { preserveScriptChoices: true,
            preserveTopic: Boolean(context.topic) || Boolean(activeContentPlanContext) });
        }
      })
      .catch(() => { if (!cancelled) setProfilesError('Не удалось загрузить проекты из аккаунта. Проверь подключение и повтори.'); })
      .finally(() => { if (!cancelled) setProfilesLoading(false); });
    return () => { cancelled = true; };
  }, [authToken, profilesReload]);

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
    if (voiceAutoKeyRef.current === comboKey && selectedVoice) return;
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
    saveVideoPrefs(activeWorkspaceKey, currentVideoPrefs);
  }, [activeWorkspaceKey, generationPreset, videoMode, storyboardGenerationMode, minimaxVoice,
    selectedVoice, selectedVoiceName, voiceSelectionSource, ttsProvider, elevenLabsModel,
    elevenLabsStability, elevenLabsSimilarity, selectedActor, selectedFace, plateUrls,
    uploadedActorPreview, language, actorGender, backgroundMusic, clipVisionQc, brollImageFirst]);

  const minimaxAutoKeyRef = useRef(`${initialVideoPrefs.language || 'ru'}-${initialVideoPrefs.actorGender || 'female'}`);
  useEffect(() => {
    const comboKey = `${language}-${actorGender}`;
    if (minimaxAutoKeyRef.current === comboKey) return;
    minimaxAutoKeyRef.current = comboKey;
    setMinimaxVoice(defaultMiniMaxVoice(language, actorGender));
  }, [actorGender, language]);

  useEffect(() => {
    setPresenterSaveStatus(null);
  }, [selectedActor, selectedFace, plateUrls, selectedVoice, selectedVoiceName,
    minimaxVoice, ttsProvider, elevenLabsModel, elevenLabsStability, elevenLabsSimilarity]);

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

  const handleLoadBusinessProfile = (profile, { preserveScriptChoices = false, preserveTopic = false } = {}) => {
    if (!profile) return;
    const id = businessProfileKey(profile);
    setSelectedBusinessProfileId(id);
    saveSelectedProfileId(id);
    setBusinessName(profile.name || '');
    setDescription(profile.description || '');
    if (!preserveTopic) setTopic(profile.topic || '');
    if (!preserveScriptChoices && !planScriptDefaults.customScript) {
      if (profile.scriptMode || profile.script_mode) setScriptMode(profile.scriptMode || profile.script_mode);
      if (profile.scriptFormat || profile.script_format) setScriptFormat(profile.scriptFormat || profile.script_format);
    }
    if (profile.targetDurationSeconds || profile.target_duration_seconds) {
      setTargetDurationSeconds(Number(profile.targetDurationSeconds || profile.target_duration_seconds) || 20);
    }
    if (profile.textModel || profile.text_model) setTextModel(profile.textModel || profile.text_model);
    if (profile.style) setStyle(profile.style);
    if (profile.language) setLanguage(profile.language);
    if (profile.actorGender || profile.actor_gender) setActorGender(profile.actorGender || profile.actor_gender);
    if (profile.presenter !== undefined) {
      const prefs = preferencesFromPresenter(profile.presenter);
      if (!profile.presenter?.minimax_voice_id) prefs.minimaxVoice = defaultMiniMaxVoice(
        profile.language || language, profile.actorGender || profile.actor_gender || actorGender);
      // Applying a project is an explicit voice choice, including across languages.
      voiceAutoKeyRef.current = `${profile.language || language}-${profile.actorGender || profile.actor_gender || actorGender}`;
      minimaxAutoKeyRef.current = voiceAutoKeyRef.current;
      restoreVideoPreferences({ ...currentVideoPrefs, ...prefs });
      if (profile.language) setLanguage(profile.language);
      if (profile.actorGender || profile.actor_gender) setActorGender(profile.actorGender || profile.actor_gender);
    }
    setPresenterSaveStatus(null);
  };

  const handleSaveProjectPresenter = async () => {
    if (!selectedBusinessProfile || presenterSaving) return;
    const profile = selectedBusinessProfile;
    const id = String(businessProfileKey(profile));
    const presenter = presenterFromPreferences({ ...currentVideoPrefs, selectedVoiceName: selectedVoiceLabel });
    const updated = { ...profile, presenter, updatedAt: new Date().toISOString() };
    setPresenterSaving(true);
    setPresenterSaveStatus(null);
    try {
      let saved = updated;
      if (authToken) {
        const existingAccountProfile = Boolean(profile.created_at);
        const res = await fetch(getApiUrl(existingAccountProfile
          ? `/api/user/business-profiles/${encodeURIComponent(id)}/presenter` : '/api/user/business-profiles'), {
          method: existingAccountProfile ? 'PATCH' : 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify(existingAccountProfile ? { presenter } : {
            ...updated, id,
            actor_gender: profile.actorGender || profile.actor_gender || 'female',
            script_mode: profile.scriptMode || profile.script_mode || 'ai',
            script_format: profile.scriptFormat || profile.script_format || 'ugc',
            target_duration_seconds: profile.targetDurationSeconds || profile.target_duration_seconds || null,
            text_model: profile.textModel || profile.text_model || 'fast',
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Не удалось сохранить. Попробуй ещё раз.');
        saved = data.profiles?.find((item) => String(businessProfileKey(item)) === id);
        if (!saved || !saved.presenter) throw new Error('Сервер пока не поддерживает сохранение ведущего. Обнови сервер и повтори.');
      }
      setBusinessProfiles((current) => {
        const next = current.map((item) => String(businessProfileKey(item)) === id
          ? mergeProjectMetadata([saved], [updated])[0] : item);
        saveBusinessProfiles(next);
        return next;
      });
      if (String(profileContextRef.current.id) === id) setPresenterSaveStatus({
        text: authToken ? `Аватар и голос сохранены в проекте «${profile.name}».` : 'Сохранено в проекте в этом браузере.',
      });
    } catch (error) {
      if (String(profileContextRef.current.id) === id) setPresenterSaveStatus({ text: error.message, error: true });
    } finally {
      setPresenterSaving(false);
    }
  };

  const handleAnalyze = async () => {
    const isCustom = scriptMode === 'custom';
    if (isCustom && !customScript.trim()) return;
    if (!isCustom && !description.trim()) return;
    if (analyzeNeedsGemini) {
      setAnalyzeError('Подключи ключ Gemini в настройках, чтобы создать сценарий с ИИ.');
      return;
    }

    setAnalyzing(true);
    setAnalyzeError('');

    try {
      const res = await fetch(getApiUrl('/api/saasshorts/analyze'), {
        method: 'POST',
        headers: buildSaaSAnalyzeHeaders({
          baseHeaders: { 'Content-Type': 'application/json', ...authHeaders() },
          geminiApiKey,
          falKey,
          isManagedKey,
        }),
        body: JSON.stringify({
          url: undefined,
          description: description.trim() || undefined,
          topic: topic.trim() || undefined,
          script_mode: scriptMode,
          script_format: scriptFormat,
          generation_preset: generationPreset,
          target_duration_seconds: targetDurationSeconds,
          text_model: textModel,
          custom_script: isCustom ? customScript.trim() : undefined,
          num_scripts: isCustom ? 1 : numScripts,
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
      generation_preset: pendingStoryboard.generation_preset || 'expressive',
      shots: pendingStoryboard.shots,
      shots_archived: pendingStoryboard.shots_archived || [],
      _source_video_id: pendingStoryboard.video_id || '',
      _source_video_url: pendingStoryboard.video_url || '',
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
    restoreVideoPreferences({
      generationPreset: pendingStoryboard.generation_preset || 'expressive',
      selectedVoice: pendingStoryboard.voice_id,
      selectedVoiceName: pendingStoryboard.voice_name,
      voiceSelectionSource: pendingStoryboard.voice_id ? 'manual' : undefined,
      elevenLabsModel: ['eleven_v3', 'eleven_v4'].includes(pendingStoryboard.voice_model)
        ? pendingStoryboard.voice_model : undefined,
      elevenLabsStability: pendingStoryboard.voice_settings?.stability,
      elevenLabsSimilarity: pendingStoryboard.voice_settings?.similarity_boost,
      ttsProvider: pendingStoryboard.tts_provider,
      backgroundMusic: pendingStoryboard.background_music,
      musicTrack: pendingStoryboard.music_track || 'auto',
      musicVolume: pendingStoryboard.music_volume ?? 1,
      videoMode: pendingStoryboard.video_mode,
    });
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
  const reorderSelectedScriptShot = (from, toIndex) => {
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
          ...elevenLabsTtsSettings(elevenLabsModel, elevenLabsStability, elevenLabsSimilarity),
          minimax_voice_id: minimaxVoice,
          minimax_voice_name: minimaxVoiceLabel,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          selected_face_url: selectedFace || undefined,
          plate_urls: plateUrls,
          video_mode: videoMode,
          generation_preset: generationPreset,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          use_platform_keys: usePlatformKeys,
          broll_image_first: brollImageFirst,
          frames_only: true,
          ...musicRequestSettings(backgroundMusic, musicTrack, musicVolume),
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
          ...elevenLabsTtsSettings(elevenLabsModel, elevenLabsStability, elevenLabsSimilarity),
          minimax_voice_id: minimaxVoice,
          minimax_voice_name: minimaxVoiceLabel,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          selected_face_url: selectedFace || undefined,
          plate_urls: plateUrls,
          video_mode: videoMode,
          generation_preset: generationPreset,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          use_platform_keys: usePlatformKeys,
          voice_only: true,
          ...musicRequestSettings(backgroundMusic, musicTrack, musicVolume),
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
          ...elevenLabsTtsSettings(elevenLabsModel, elevenLabsStability, elevenLabsSimilarity),
          minimax_voice_id: minimaxVoice,
          minimax_voice_name: minimaxVoiceLabel,
          actor_gender: actorGender,
          language,
          actor_description: actorDescription || undefined,
          selected_actor_url: selectedActor || undefined,
          selected_face_url: selectedFace || undefined,
          plate_urls: plateUrls,
          video_mode: videoMode,
          generation_preset: generationPreset,
          broll_mode: storyboardSelected ? 'off' : brollMode,
          storyboard_generation_mode: storyboardGenerationMode,
          // Кадры ведущего в платном рендере рисует та же модель, что выбрана в
          // превью, — иначе выбор чинил бы только превью.
          avatar_edit_model: avatarEditModel || undefined,
          reusable_head_template_id: selectedHeadTemplate || undefined,
          reusable_lipsync_model: lipSyncModel,
          use_platform_keys: usePlatformKeys,
          ...musicRequestSettings(backgroundMusic, musicTrack, musicVolume),
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
          ...elevenLabsTtsSettings(elevenLabsModel, elevenLabsStability, elevenLabsSimilarity),
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
          generation_preset: generationPreset,
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
          ...musicRequestSettings(backgroundMusic, musicTrack, musicVolume),
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
      requestedModel: currentScript?._voice_requested_model || '',
      settingsChanged: (currentScript?._voice_generation_preset != null
          && currentScript._voice_generation_preset !== generationPreset)
        || (currentScript?._voice_requested_stability != null && elevenLabsModel === 'eleven_v4'
          && (currentScript._voice_requested_stability !== elevenLabsStability
            || currentScript._voice_requested_similarity !== elevenLabsSimilarity)),
      voiceId: currentScript?._voice_id || '',
      voiceName: currentScript?._voice_name || '',
      voiceSource: currentScript?._voice_selection_source || '',
      shootCost: currentScript?._voice_shoot_cost,
      // Реплики, переписанные уже после записи. Съёмка перезапишет их сама, но
      // услышать их до готового ролика можно только записав озвучку ещё раз.
      stale: shots
        .filter((shot) => typeof shot.voice_speech === 'string'
          && generationSpeech(shot.speech, generationPreset) !== shot.voice_speech)
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
  const durationGap = scriptMode !== 'custom' && storyboardSeconds && targetDurationSeconds
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


  const renderGenerationSettings = (isLight = false) => (
    <>
      <GenerationPresetPicker value={generationPreset} onChange={selectGenerationPreset}
        disabled={generating || framesGenerating || voiceGenerating} />
      <MusicPicker enabled={backgroundMusic} value={musicTrack} volume={musicVolume}
        onEnabledChange={setBackgroundMusic} onChange={setMusicTrack} onVolumeChange={setMusicVolume}
        disabled={generating || framesGenerating || voiceGenerating || musicSaving} />
      {sourceJobId && renderPlan.reshoot.length === 0 && (
        <button type="button" disabled={generating || framesGenerating || voiceGenerating || musicSaving}
          onClick={async () => {
            setMusicSaving(true); setMusicError('');
            try {
              const response = await fetch(getApiUrl('/api/saasshorts/music'), {
                method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ job_id: sourceJobId, ...musicRequestSettings(backgroundMusic, musicTrack, musicVolume) }),
              });
              const data = await response.json();
              if (!response.ok) throw new Error(data.detail || 'Не удалось сохранить музыку');
              setGenResult((previous) => ({ ...previous, ...data.video }));
              setGenStatus('completed'); setJobId(sourceJobId); setStep(4);
            } catch (error) { setMusicError(error.message); }
            finally { setMusicSaving(false); }
          }}
          className={isLight ? 'storyboard-editor__button' : 'inline-flex min-h-10 items-center gap-2 rounded-md border border-white/15 px-3 py-2 text-sm text-zinc-200 hover:bg-white/5 disabled:opacity-50'}>
          {musicSaving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          {musicSaving ? 'Сохраняю...' : 'Сохранить музыку · $0'}
        </button>
      )}
      {musicError && <p role="alert" className={isLight ? 'storyboard-editor__notice' : 'text-sm text-red-300'} data-tone="error">{musicError}</p>}
    </>
  );

  const renderCostEstimate = (isLight = false) => {
    const estimate = estimateSaasVideoCost({
      text: editedNarration,
      videoMode,
      ttsProvider,
      brollMode,
      hasSelectedActor: Boolean(selectedActor),
      hasReusableHead: !isLight && Boolean(selectedHeadTemplate),
      lipsyncModel: lipSyncModel,
      script: scripts[selectedScript],
      storyboardGenerationMode,
    });
    const costDetails =
      !isLight && selectedHeadTemplate
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
      <div className={isLight ? 'storyboard-editor__section' : 'max-w-2xl p-4 bg-white/5 rounded-xl border border-white/10'}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className={isLight ? 'text-sm font-semibold' : 'text-sm font-semibold text-zinc-300'}>
              {reshootEstimate ? 'Стоимость пересъёмки' : 'Примерная стоимость'}
            </div>
            <div className={isLight ? 'text-xs text-[#545967] mt-1' : 'text-[11px] text-zinc-600 mt-1'}>
              {reshootEstimate
                ? `Кадры, которые не менялись, переезжают из прошлого рендера бесплатно. С нуля этот ролик стоил бы ${formatUsd(estimate.total)}.`
                : costDetails}
            </div>
          </div>
          <span className={isLight ? 'text-lg font-semibold whitespace-nowrap' : 'text-lg text-green-400 font-semibold whitespace-nowrap'}>
            {formatUsd(reshootEstimate ? reshootEstimate.total : estimate.total)}
          </span>
        </div>

        <div className={isLight ? 'storyboard-editor__estimate-lines mt-4' : 'mt-4 space-y-2 text-sm'}>
          {rows.map(([label, value]) => (
            <div key={label} className={isLight ? 'flex justify-between gap-4' : 'flex items-center justify-between gap-4 border-t border-white/5 pt-2 first:border-t-0 first:pt-0'}>
              <span className={isLight ? 'text-[#545967]' : 'text-zinc-500'}>{label}</span>
              <span className={isLight ? 'tabular-nums' : 'font-mono text-zinc-300'}>{value}</span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderStoryboardSettings = () => (
    <>
      {renderGenerationSettings(true)}
      {/* Место действия — одно на весь ролик и своё поле. Пока оно
          жило внутри кадра 1, в плиты вместе с комнатой уезжало всё,
          что там оказалось: «static camera» — и обе камеры выходили
          одним анфасом, «a beautiful woman» — и редактор рисовал своё
          лицо вместо выбранного. */}
      <div className="rounded-md border border-[#dfe1e7] bg-[#f7f7fa] p-3 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[12px] font-semibold text-[#545967]">
            Место действия ролика
          </span>
          <button
            type="button"
            onClick={pickReelSet}
            disabled={pickingSet}
            className="inline-flex items-center gap-1 rounded-md border border-[#dfe1e7] px-2 py-0.5 text-xs text-[#545967] transition-colors hover:border-primary/40 hover:text-[#574585] disabled:opacity-50"
            title="Подобрать место по тексту ролика (Gemini, бесплатно)"
          >
            {pickingSet
              ? (<><Loader2 size={11} className="animate-spin" /> Подбираю…</>)
              : (<><Sparkles size={11} /> Подобрать ИИ</>)}
          </button>
        </div>
        <textarea
          className="storyboard-editor__input min-h-[58px] resize-y py-2 text-sm leading-relaxed"
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
          <ul className="space-y-0.5 text-xs leading-snug text-[#545967]">
            {reelLocations.map((place, index) => (
              <li key={`${index}-${place.slice(0, 12)}`}>
                <span className="text-[#545967]">Локация {index + 1}:</span> {place}
                {index === 0 ? ' (её и правит поле выше)' : ''}
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs leading-snug text-[#545967]">
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
      <div className="rounded-md border border-sky-500/20 bg-sky-500/[0.04] p-3 space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-md">
            <h4 className="text-[12px] font-semibold text-[#574585] flex items-center gap-1.5">
              <Volume2 size={13} /> Озвучка
            </h4>
            <p className="text-xs text-[#545967] mt-0.5">
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
              className="storyboard-editor__button px-3 py-2 text-[12px] flex items-center justify-center gap-1.5 disabled:opacity-50"
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
                className="rounded-md border border-[#dfe1e7] px-2.5 py-1 text-xs text-[#545967] transition-colors hover:border-sky-400/40 hover:text-[#574585] disabled:opacity-50"
              >
                Перечитать всё одним дублем
              </button>
            )}
          </div>
        </div>

        {voicePreview && (
          <div className="space-y-2">
            <MediaPlayer
              kind="audio"
              label="Озвучка ролика"
              preload="metadata"
              src={voicePreview.url}
              className="w-full"
            />
            <p className="text-xs font-medium text-[#574585]">
              Голос: {voicePreview.voiceName || selectedVoiceLabel}
              {voicePreview.voiceId ? ` · ${voicePreview.voiceId}` : ''}
            </p>
            <p className="text-xs text-[#545967]">
              {voicePreview.seconds ? `${voicePreview.seconds.toFixed(1)} с` : 'длина неизвестна'}
              {voicePreview.clips
                ? ` · снимется ${voicePreview.clips} ${pluralClips(voicePreview.clips)}${
                    voicePreview.shootCost != null ? ` (~${formatUsd(voicePreview.shootCost)})` : ''
                  }`
                : ''}
              {voicePreview.model ? ` · ${voicePreview.model}` : ''}
            </p>
            {voicePreview.stale.length > 0 && (
              <p className="text-xs text-[#674619]">
                После записи изменились реплики {voicePreview.stale.join(', ')}.
                При съёмке они перезапишутся сами, но услышать их заранее можно,
                только записав озвучку ещё раз.
              </p>
            )}
            {ttsProvider !== 'fal_minimax'
              && (voicePreview.settingsChanged || (voicePreview.requestedModel
                ? voicePreview.requestedModel !== elevenLabsModel
                : elevenLabsModel === 'eleven_v4' && voicePreview.model !== 'eleven_v4')) && (
              <p className="text-xs text-[#674619]">
                Параметры этой записи отличаются от выбранных. При следующей генерации
                озвучка будет записана заново; сначала обнови её для прослушивания.
              </p>
            )}
          </div>
        )}
      </div>

      {voiceNotice && (
        <div className="rounded-md border border-amber-500/25 bg-amber-500/[0.06] p-3">
          <p className="text-xs text-[#674619]">{voiceNotice}</p>
        </div>
      )}

      {/* Сгенерировать стартовые кадры (Flux) до платного видео,
          чтобы увидеть и утвердить композицию каждого шота. */}
      <div className="rounded-md border border-primary/20 bg-primary/[0.04] p-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-[#545967] max-w-md">
          Сгенерируй стартовые кадры и проверь композицию до платной генерации видео.
          Говорящие кадры снимаются двумя общими ракурсами — за них платишь дважды,
          сколько бы их ни было; у каждой перебивки свой кадр. Готовые пропускаются.
          Перегенерить кадр или заменить его своим фото можно по кнопке на самом кадре.
        </p>
        <button
          type="button"
          onClick={() => handleGenerateFrames(null)}
          disabled={framesGenerating || missingFrameCount === 0}
          className="storyboard-editor__button shrink-0 px-3 py-2 text-[12px] flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          {framesGenerating && framesShot === null
            ? (<><Loader2 size={13} className="animate-spin" /> Генерирую…</>)
            : missingFrameCount === 0
              ? (<><Check size={13} /> Все кадры готовы</>)
              : (<><Sparkles size={13} /> Сгенерить недостающие: {missingFrameCount} (~{formatUsd(billableFrameCount * 0.05)})</>)}
        </button>
      </div>

      {framesNotice && (
        <div className="rounded-md border border-amber-500/25 bg-amber-500/[0.06] p-3">
          <p className="text-xs text-[#674619]">{framesNotice}</p>
        </div>
      )}

      {/* Какой моделью рисуется ведущий. Строка появляется, как
          только бэкенд прислал каталог: до этого выбирать не из чего. */}
      {avatarEditModels.length > 0 && (
        <div className="rounded-md border border-[#dfe1e7] bg-[#f7f7fa] p-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[#545967]">
            Ведущего в кадр ставит{' '}
            <span className="text-[#545967]">
              {(avatarEditModels.find((m) => m.id === avatarEditModel) || avatarEditModels[0]).title}
            </span>
            . Если модель откажет — предложу сменить её, подменять сама она не будет.
          </p>
          <select
            value={avatarEditModel || avatarEditModels[0].id}
            onChange={(e) => setAvatarEditModel(e.target.value)}
            disabled={framesGenerating}
            className="storyboard-editor__input shrink-0 text-[12px] py-1.5"
          >
            {avatarEditModels.map((model) => (
              <option key={model.id} value={model.id}>
                {model.title}{model.blocked ? ' — уже отказала' : ''}
              </option>
            ))}
          </select>
        </div>
      )}
      <div>
        <label className="block text-sm font-medium text-[#545967] mb-2 flex items-center gap-2">
          <Film size={14} /> Способ генерации видео
        </label>
        <div className="grid sm:grid-cols-2 gap-2">
          {STORYBOARD_GENERATION_OPTIONS.map((option) => (
            <button
              key={option.id}
              onClick={() => setStoryboardGenerationMode(option.id)}
              className={`p-3 rounded-md border text-left transition-all ${
                storyboardGenerationMode === option.id
                  ? 'border-violet-500/50 bg-violet-500/10 text-[#574585]'
                  : 'border-[#dfe1e7] bg-[#f7f7fa] text-[#545967] hover:bg-[#f7f7fa]'
              }`}
            >
              <div className="text-sm font-semibold">{option.label}</div>
              <div className="text-xs text-[#545967] mt-1">{option.desc}</div>
            </button>
          ))}
        </div>
      </div>
      {/* Пересъёмка готового ролика: клипы прошлого рендера
          переносятся в новый джоб, поэтому неизменённые кадры
          ничего не стоят — платим за то, что правили. */}
      {renderPlan.isReshoot && (
        <div className="rounded-md border border-green-500/20 bg-green-500/[0.05] p-3">
          <p className="text-xs text-[#35634d]">
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
          <label className="mt-2 flex items-start gap-2 text-xs text-[#35634d]">
            <input
              type="checkbox"
              checked={revoiceAll}
              onChange={(event) => setRevoiceAll(event.target.checked)}
              className="mt-0.5 w-3.5 h-3.5 rounded border-green-500/40 bg-white text-[#35634d] focus:ring-green-500"
            />
            <span>
              Перечитать весь текст одним дублем
              <span className="text-[#35634d]"> — ни одного стыка в озвучке, но тогда переснимаются все говорящие кадры</span>
            </span>
          </label>
        </div>
      )}
      {/* Реплики исходного сценария, которых нет ни в одном кадре —
          для старых роликов это всё, что уцелело от удалённых кадров. */}
      {leftoverNarration.length > 0 && (
        <details className="rounded-md border border-[#dfe1e7] bg-[#f7f7fa]">
          <summary className="cursor-pointer list-none px-3 py-2 text-xs text-[#545967] hover:text-[#545967]">
            Текст сценария вне кадров ({leftoverNarration.length}) — можно вернуть кадром
          </summary>
          <div className="space-y-2 border-t border-[#dfe1e7] p-3">
            {leftoverNarration.map((sentence, i) => (
              <div key={i} className="flex items-start gap-2 rounded-md border border-[#dfe1e7] bg-[#f7f7fa] p-2">
                <p className="min-w-0 flex-1 text-xs text-[#545967]">{sentence}</p>
                <button
                  type="button"
                  onClick={() => addShotWithSpeech(sentence)}
                  className="shrink-0 rounded-md border border-[#dfe1e7] px-2 py-1 text-xs text-[#545967] transition-colors hover:border-primary/40 hover:text-[#574585]"
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
        <details className="rounded-md border border-[#dfe1e7] bg-[#f7f7fa]">
          <summary className="cursor-pointer list-none px-3 py-2 text-xs text-[#545967] hover:text-[#545967]">
            Удалённые кадры ({(scripts[selectedScript].shots_archived || []).length}) — текст сохранён, вернутся на свои места
          </summary>
          <div className="space-y-2 border-t border-[#dfe1e7] p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-[#545967]">
                Кадры помнят свои позиции — можно спокойно разобрать раскадровку
                на тестовый рендер и собрать обратно.
              </p>
              <button
                type="button"
                onClick={restoreAllArchivedShots}
                className="shrink-0 rounded-md border border-primary/40 px-2 py-1 text-xs text-[#574585] transition-colors hover:bg-primary/10"
              >
                Вернуть все ({(scripts[selectedScript].shots_archived || []).length})
              </button>
            </div>
            {(scripts[selectedScript].shots_archived || []).map((shot, i) => (
              <div key={i} className="flex items-start gap-2 rounded-md border border-[#dfe1e7] bg-[#f7f7fa] p-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs text-[#545967]">{shot.speech || shot.scene || 'Пустой кадр'}</p>
                  {shot.scene && shot.speech && (
                    <p className="truncate text-xs text-[#545967]">{shot.scene}</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => restoreArchivedShot(i)}
                  className="shrink-0 rounded-md border border-[#dfe1e7] px-2 py-1 text-xs text-[#545967] transition-colors hover:border-primary/40 hover:text-[#574585]"
                >
                  Вернуть
                </button>
                <button
                  type="button"
                  onClick={() => dropArchivedShot(i)}
                  aria-label="Забыть кадр"
                  title="Забыть окончательно"
                  className="shrink-0 rounded-md p-1 text-[#545967] transition-colors hover:text-[#8f263b]"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        </details>
      )}
    </>
  );

  const renderStoryboardShot = ({ shot, imageUrl, clipUrl, shotNumber, markedForReshoot, plannedSeconds }, shotIndex) => {
    const isBroll = isBrollShot(shot);
    const clipFloorSeconds = shotClipFloorSeconds(shot);
    const shotIsShorterThanItsClip = plannedSeconds > 0 && plannedSeconds < clipFloorSeconds - 0.05;
    return (
      <>
        <label className="storyboard-editor__field">
          <span>Тип кадра</span>
          <select className="storyboard-editor__input" value={isBroll ? 'broll' : 'avatar'}
            onChange={(event) => handleSelectedScriptShot(shotIndex, 'visual_type', event.target.value)}>
            <option value="avatar">{actorGender === 'male' ? 'Ведущий' : 'Ведущая'}</option>
            <option value="broll">Перебивка</option>
          </select>
        </label>
        <label className="storyboard-editor__field">
          <span>{isBroll ? 'Текст за кадром' : 'Реплика'}</span>
          <textarea
            className="storyboard-editor__input min-h-[58px] resize-y py-2 text-sm leading-relaxed"
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
            <p className="text-xs leading-snug text-[#674619]">
              Коротко: {plannedSeconds.toFixed(1)} с речи при клипе от{' '}
              {clipFloorSeconds.toFixed(1)} с — платим за полный.
              Добавь слов или слей с соседним кадром.
            </p>
          )}
        </label>
        <div className="storyboard-editor__field">
          <div className="flex items-center justify-between gap-2">
            <label htmlFor={storyboardFieldId + '-scene'}>
              {isBroll
                ? 'Что в кадре'
                : (shotIndex === setDefiningShotIndex && !hasOwnSet
                  ? 'Что в кадре — место действия всего ролика'
                  : 'Что делает')}
            </label>
            {/* Пустая сцена = случайная картинка: промпт для
                видео-модели строится именно отсюда. */}
            <button
              type="button"
              onClick={() => fillShotDetails([shotNumber])}
              disabled={fillingShots.includes(shotNumber)}
              className="inline-flex items-center gap-1 rounded-md border border-[#dfe1e7] px-2 py-0.5 text-xs text-[#545967] transition-colors hover:border-primary/40 hover:text-[#574585] disabled:opacity-50"
              title="Заполнить сцену, камеру и действие по реплике (Gemini, бесплатно)"
            >
              {fillingShots.includes(shotNumber)
                ? (<><Loader2 size={11} className="animate-spin" /> Заполняю…</>)
                : (<><Sparkles size={11} /> Заполнить ИИ</>)}
            </button>
          </div>
          <textarea
            id={storyboardFieldId + '-scene'}
            className="storyboard-editor__input min-h-[58px] resize-y py-2 text-sm leading-relaxed"
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
            <p className="text-xs leading-snug text-[#545967]">
              {setChosenByUser
                ? 'Место — из настроек ролика'
                : (hasOwnSet
                  ? 'Место — с фото ведущего, одно на весь ролик'
                  : `Место то же, что в кадре ${setDefiningShotIndex + 1}`)}
              {'. Опиши здесь позу, взгляд или жест ведущего.'}
            </p>
          )}
        </div>
        {/* Записанная реплика: послушать именно её, увидеть
            её длину (её задаёт голос, а не поле «секунды»)
            и заказать другой дубль, не трогая остальные. */}
        {(shot.voice_url || shot.voice_seconds > 0) && (
          <div className="-mt-1 flex flex-wrap items-center gap-2">
            {shot.voice_url && (
              <MediaPlayer
                kind="audio"
                label={`Реплика ${shotNumber}`}
                compact
                preload="none"
                src={getApiUrl(shot.voice_url)}
                className="w-full max-w-[280px]"
              />
            )}
            <span className="text-xs text-[#545967]">
              {Number(shot.voice_seconds || 0).toFixed(1)} с
              {shot.voice_clips > 1 ? ` · ${shot.voice_clips} ${pluralClips(shot.voice_clips)}` : ''}
            </span>
            {typeof shot.voice_speech === 'string'
              && (shot.speech || '').trim() !== shot.voice_speech && (
              <span className="text-xs text-[#674619]">текст изменился после записи</span>
            )}
            <button
              type="button"
              onClick={() => handleGenerateVoice(shotNumber)}
              disabled={voiceGenerating}
              title="Прочитать эту реплику заново. Остальные дубли останутся как есть."
              className="inline-flex items-center gap-1 rounded-md border border-[#dfe1e7] px-2 py-0.5 text-xs text-[#545967] transition-colors hover:border-sky-400/40 hover:text-[#574585] disabled:opacity-50"
            >
              {voiceGenerating && voiceShot === shotNumber
                ? (<><Loader2 size={11} className="animate-spin" /> Пишу…</>)
                : (<><Volume2 size={11} /> Перезаписать</>)}
            </button>
          </div>
        )}
        {isBroll && (
          <div className="-mt-1.5 space-y-1.5">
            <p className="text-xs text-[#545967]">
              В перебивке лицо не показываем, но озвучка продолжает звучать поверх вставки.
            </p>
            {/* Кадр перебивки рисуется отдельно от аватара, поэтому по
                тексту сцены мы не угадаем, наш это человек или чужой.
                Без галочки «женский силуэт со спины» — посторонняя
                женщина посреди ролика. */}
            <label className="flex items-start gap-2 text-xs text-[#545967]">
              <input
                type="checkbox"
                checked={Boolean(shot.actor_in_frame)}
                onChange={(event) => handleSelectedScriptShot(shotIndex, 'actor_in_frame', event.target.checked)}
                className="mt-0.5 w-3.5 h-3.5 rounded border-[#afb3c0] bg-white text-[#574585] focus:ring-violet-500"
              />
              <span>
                В кадре наш персонаж
                <span className="text-[#545967]"> — со спины, руки или силуэт: кадр снимем с фото аватара, лицо не покажем</span>
              </span>
            </label>
          </div>
        )}
        <details className="storyboard-editor__disclosure">
          <summary>Камера и промпт <ChevronDown size={15} /></summary>
          {!isBroll && talkingCameras[shotIndex] && (
            <p className="mb-2 text-xs text-[#545967]">Ракурс ведущего при сборке: {CAMERA_LABELS[talkingCameras[shotIndex]]}.</p>
          )}
          <label className="storyboard-editor__field">
            <span>Камера</span>
            <input className="storyboard-editor__input" value={shot.camera || ''}
              onChange={(event) => handleSelectedScriptShot(shotIndex, 'camera', event.target.value)}
              placeholder="Крупный план, лёгкая ручная камера" />
          </label>
          <label className="storyboard-editor__field">
            <span>Действие актёра</span>
            <textarea className="storyboard-editor__input" rows={2} value={shot.actor_action || shot.action || ''}
              onChange={(event) => handleSelectedScriptShot(shotIndex, 'actor_action', event.target.value)} />
          </label>
          <label className="storyboard-editor__field">
            <span>Промпт кадра</span>
            <input className="storyboard-editor__input" value={shot.generation_prompt || ''}
              onChange={(event) => updateSelectedScriptShot(shotIndex, { generation_prompt: event.target.value, prompt_manual: true })}
              placeholder="Промпт на английском" />
          </label>
          {shot.prompt_manual && (
            <button type="button" className="storyboard-editor__button storyboard-editor__button--plain"
              onClick={() => updateSelectedScriptShot(shotIndex, { prompt_manual: false })}>Использовать описание кадра</button>
          )}
          <label className="storyboard-editor__field">
            <span>Роль кадра</span>
            <input className="storyboard-editor__input" value={shot.role || ''}
              onChange={(event) => handleSelectedScriptShot(shotIndex, 'role', event.target.value)}
              placeholder="hook / problem / cta" />
          </label>
          <label className="storyboard-editor__field">
            <span>Переход после кадра</span>
            <input className="storyboard-editor__input" value={shot.transition || ''}
              onChange={(event) => handleSelectedScriptShot(shotIndex, 'transition', event.target.value)}
              placeholder="cut / smooth_0.3s" />
          </label>
        </details>
        <details className="storyboard-editor__disclosure">
          <summary>Изображение и пересъёмка <ChevronDown size={15} /></summary>
          <div className="storyboard-editor__actions">
            <input id={storyboardFieldId + '-photo'} type="file" accept="image/*" className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) handleStoryboardFrameUpload(shotIndex, file);
                event.target.value = '';
              }} />
            <label htmlFor={storyboardFieldId + '-photo'} className="storyboard-editor__button cursor-pointer"><Upload size={15} /> Загрузить фото</label>
            <button type="button" className="storyboard-editor__button" onClick={() => handleGenerateFrames(shotNumber)} disabled={framesGenerating}>
              {framesGenerating && framesShot === shotNumber ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
              {imageUrl ? 'Обновить кадр' : 'Создать кадр'}
            </button>
            {clipUrl && renderPlan.isReshoot && (
              <button type="button" className="storyboard-editor__button" aria-pressed={markedForReshoot}
                onClick={() => setReshootShots((previous) => (
                  previous.includes(shotNumber) ? previous.filter((number) => number !== shotNumber) : [...previous, shotNumber]
                ))}>
                <RefreshCw size={15} /> {markedForReshoot ? 'Не переснимать' : 'Переснять'}
              </button>
            )}
          </div>
        </details>
        {shot.frame_status && <p className="storyboard-editor__notice" role="status">{shot.frame_status}</p>}
      </>
    );
  };

  const storyboardEditor = step === 2 && storyboardSelected;
  const storyboardFrames = storyboardEditor ? (currentScript.shots || []).map((shot, index) => {
    const imageUrl = shot.image_preview
      || (shot.local_url ? getApiUrl(shot.local_url) : '')
      || (shot.image_url?.startsWith('/videos/') ? getApiUrl(shot.image_url) : shot.image_url)
      || (shot.preview_frame_url ? getApiUrl(shot.preview_frame_url) : '');
    const clipUrl = shot.clip_url ? getApiUrl(shot.clip_url) : '';
    const shotNumber = shot.shot_number ?? (index + 1);
    const markedForReshoot = reshootShots.includes(shotNumber);
    const plannedSeconds = shotPlannedSeconds(currentScript, shot, storyboardSeconds);
    return {
      shot, imageUrl, clipUrl, shotNumber, markedForReshoot, plannedSeconds,
      status: markedForReshoot && clipUrl ? 'reshoot' : clipUrl || imageUrl ? 'ready' : 'missing',
      statusLabel: clipUrl ? (markedForReshoot ? 'Переснимем' : 'Снят') : imageUrl ? 'Кадр готов' : 'Без кадра',
    };
  }) : [];
  const storyboardBaseline = currentScript?._render_baseline;
  const storyboardSourceVideo = storyboardEditor && currentScript._source_video_url
    && storyboardFrames.length === storyboardBaseline?.length
    && storyboardFrames.every(({ shot }, index) => {
      const previous = storyboardBaseline[index];
      return previous && [
        'shot_number', 'speech', 'scene', 'generation_prompt', 'prompt_manual', 'visual_type', 'start', 'end',
        'actor_in_frame', 'actor_action', 'camera', 'transition', 'role',
        'image_path', 'image_url', 'image_preview', 'local_url', 'clip_url', 'timeline_start', 'timeline_end',
      ].every((field) => shot[field] === previous[field]);
    }) ? getApiUrl(currentScript._source_video_url) : '';
  const storyboardVoice = voicePreview && !voicePreview.settingsChanged && !voicePreview.stale.length
    && storyboardFrames.every(({ shot }) => !shot.speech?.trim() || typeof shot.voice_speech === 'string')
    ? voicePreview : null;
  const storyboardPrice = storyboardEditor
    ? reshootCost ?? estimateSaasVideoCost({
        text: editedNarration, videoMode, ttsProvider, brollMode, hasSelectedActor: Boolean(selectedActor),
        hasReusableHead: false, lipsyncModel: lipSyncModel, script: currentScript, storyboardGenerationMode,
      }).total
    : 0;
  const storyboardMissingKey = !falKey || (ttsProvider === 'elevenlabs' && !elevenLabsKey);
  const storyboardNotice = storyboardEditor && (durationGap || emptyShotNumbers.length > 0 || fillError || storyboardMissingKey || framesNotice || voiceNotice) && (
    <div className="storyboard-editor__notices">
      {durationGap !== 0 && <p className="storyboard-editor__notice" data-tone="warning">
        Сценарий {durationGap > 0 ? 'длиннее' : 'короче'} цели на {Math.abs(durationGap)} с.
        {' '}Озвучка займёт около {storyboardSeconds} с при цели {targetDurationSeconds} с.
      </p>}
      {/* Кадры без описания сцены: ИИ-генерация видео читает промпт,
          собранный из «Что в кадре», а не реплику. */}
      {emptyShotNumbers.length > 0 && (
        <div className="flex flex-col gap-2 rounded-md border border-amber-500/25 bg-amber-500/[0.06] p-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-md text-xs text-[#674619]">
            В {emptyShotNumbers.length} {pluralShots(emptyShotNumbers.length)} есть реплика, но не описано, что в кадре.
            Без этого нейросеть нарисует случайную сцену.
          </p>
          <button
            type="button"
            onClick={() => fillShotDetails(emptyShotNumbers)}
            disabled={fillingShots.length > 0}
            className="storyboard-editor__button shrink-0 px-3 py-2 text-[12px] flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            {fillingShots.length > 0
              ? (<><Loader2 size={13} className="animate-spin" /> Заполняю…</>)
              : (<><Sparkles size={13} /> Заполнить {emptyShotNumbers.length} {pluralShots(emptyShotNumbers.length)} ИИ</>)}
          </button>
        </div>
      )}
      {fillError && (
        <p className="text-xs text-[#8f263b]">{fillError}</p>
      )}
      {storyboardMissingKey && <p className="storyboard-editor__notice" data-tone="warning">
        {falKey ? 'Добавь ключ ElevenLabs в настройках.' : 'Добавь ключ fal.ai в настройках.'}
      </p>}
      {framesNotice && <p className="storyboard-editor__notice" role="status">{framesNotice}</p>}
      {voiceNotice && <p className="storyboard-editor__notice" role="status">{voiceNotice}</p>}
    </div>
  );

  const studioStep = step === 0 || step === 1;
  const stepTitle = ['Бриф ролика', 'Сценарий', 'Настройка ролика', 'Сборка ролика', 'Готовый ролик'][step];
  const resetDraft = () => {
    if (window.confirm('Сбросить текущий черновик и начать заново?')) handleReset();
  };
  const workflowNav = (
    <nav aria-label="Этапы создания ролика">
      <ol className="shorts-workflow__steps">
        {['Бриф', 'Сценарий', currentScript && !storyboardSelected ? 'Настройка' : 'Раскадровка', 'Сборка', 'Результат'].map((label, index) => (
          <li key={label}>
            <button type="button" aria-label={label} aria-current={index === step ? 'step' : undefined}
              disabled={!stepReady[index] || index === step} onClick={() => setStep(index)}>
              <span aria-hidden="true">{index + 1}</span><span>{label}</span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );

  const briefProductField = (
    <div className="shorts-workflow__field">
      <label htmlFor="shorts-setup-description">
        Что ты предлагаешь и кому{' '}
        <span className="shorts-workflow__required">{scriptMode === 'custom' ? 'Необязательно' : 'Обязательно'}</span>
      </label>
      <AutoTextarea
        id="shorts-setup-description"
        aria-required={scriptMode !== 'custom'}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        minRows={3}
        className="shorts-workflow__input"
        placeholder="Например, я тренер. Помогаю женщинам после 30 наладить питание и заниматься дома."
      />
    </div>
  );
  const briefExtras = (
    <>
      <div className="shorts-workflow__field">
        <label htmlFor="shorts-setup-topic">
          Тема ролика <span className="shorts-workflow__muted">· необязательно</span>
        </label>
        <AutoTextarea
          id="shorts-setup-topic"
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          minRows={1}
          className="shorts-workflow__input"
          placeholder="Например, ужин за 15 минут"
        />
      </div>

    </>
  );

  // ─── Render Steps ─────────────────────────────────────────────────

  return (
    <>
      {storyboardEditor ? (
        <StoryboardEditor
          key={activeWorkspaceKey + ':' + selectedScript}
          title={currentScript.title || topic || 'Новый ролик'}
          projectName={businessName}
          shots={storyboardFrames}
          sourceVideo={storyboardSourceVideo}
          voice={storyboardVoice}
          waveform={currentScript._source_waveform}
          onBack={() => setStep(previousReadyStep)}
          onResult={nextReadyStep !== undefined ? () => setStep(nextReadyStep) : undefined}
          resultLabel={nextReadyStep === 3 ? 'К генерации' : 'К результату'}
          onAdd={() => addSelectedScriptShot()}
          onDuplicate={duplicateSelectedScriptShot}
          onRemove={removeSelectedScriptShot}
          onMove={moveSelectedScriptShot}
          onReorder={reorderSelectedScriptShot}
          onUndo={shotHistory.some((entry) => entry.scriptIndex === selectedScript) ? undoShotChange : undefined}
          onEnlarge={(src, index) => setLightbox({ src, alt: 'Кадр ' + (index + 1), caption: 'Кадр ' + (index + 1) })}
          settingsBlocked={Boolean(frameBlock)}
          settings={renderStoryboardSettings()}
          estimate={renderCostEstimate(true)}
          renderShot={renderStoryboardShot}
          notice={storyboardNotice}
          renderAction={(
            <button type="button" className="storyboard-editor__button storyboard-editor__button--primary"
              disabled={storyboardMissingKey || generating || storyboardFrames.length === 0} onClick={handleGenerate}>
              {generating && <Loader2 size={15} className="animate-spin" />}
              {generating ? 'Собираю…' : reshootEstimate
                ? (renderPlan.reshoot.length === 0 ? 'Пересобрать бесплатно' : 'Переснять ' + renderPlan.reshoot.length + ' ' + pluralShots(renderPlan.reshoot.length))
                : 'Собрать ролик'}
              {(!reshootEstimate || renderPlan.reshoot.length > 0) && <span>≈ {formatUsd(storyboardPrice)}</span>}
            </button>
          )}
        />
      ) : (
    <div key={studioStep ? step : 'workflow'} className="shorts-workflow" data-shorts-workflow={step}
      data-shorts-studio={studioStep || undefined}>
      <div className="shorts-workflow__layout">
        {studioStep ? (
          <header className="shorts-workflow__studio-header">
            <div className="shorts-workflow__studio-toolbar">
              <div className="shorts-workflow__studio-leading">
                {step === 1 ? (
                  <>
                    <button type="button" onClick={() => setStep(0)} className="shorts-workflow__button shorts-workflow__button--plain">
                      <ArrowLeft size={16} aria-hidden="true" /> <span>Назад</span>
                    </button>
                    <button type="button" onClick={resetDraft} className="shorts-workflow__button shorts-workflow__button--icon"
                      aria-label="Сбросить черновик" title="Сбросить черновик">
                      <RefreshCw size={15} aria-hidden="true" />
                    </button>
                  </>
                ) : (
                  <button type="button" className="shorts-workflow__button shorts-workflow__button--plain"
                    aria-controls="shorts-brief-resources" onClick={() => {
                      const resources = document.getElementById('shorts-brief-resources');
                      resources?.scrollIntoView({ block: 'start' });
                      resources?.querySelector('select, button')?.focus({ preventScroll: true });
                    }}>
                    <User size={15} aria-hidden="true" /> Ведущий и голос
                  </button>
                )}
              </div>
              <div className="shorts-workflow__studio-heading">
                <h1>{stepTitle}</h1>
                <span>{businessName || 'Создание ролика'}</span>
              </div>
              <div className="shorts-workflow__studio-actions">
                {step === 0 ? (
                  <span className="shorts-workflow__step-status">Шаг 1 из 5</span>
                ) : (
                  <button type="button" onClick={() => setStep(2)} disabled={!currentScript}
                    className="shorts-workflow__button shorts-workflow__button--primary">
                    {storyboardSelected ? 'К раскадровке' : 'К настройке ролика'} <ChevronRight size={15} aria-hidden="true" />
                  </button>
                )}
              </div>
            </div>
            <div className="shorts-workflow__studio-nav">
              {workflowNav}

            </div>
          </header>
        ) : (
          <header className="shorts-workflow__header">
            <div className="shorts-workflow__headline">
              <h1>{stepTitle}</h1>
              <button type="button" className="shorts-workflow__button shorts-workflow__button--plain shorts-workflow__reset"
                aria-label="Сбросить черновик" onClick={resetDraft}>
                <span>Сбросить черновик</span><span aria-hidden="true">Сбросить</span>
              </button>
            </div>
            {workflowNav}
          </header>
        )}

        {/* ── Step 0: Brief ────────────────────────────────────── */}
        {step === 0 && (
          <div className="shorts-workflow__page shorts-workflow__setup" data-shorts-setup>
            <section className="shorts-workflow__project-start" aria-labelledby="shorts-project-start-title">
              <div className="shorts-workflow__project-heading">
                <h2 id="shorts-project-start-title">Выбери проект</h2>
                <p className="shorts-workflow__muted">Описание, сохранённый аватар и голос подставятся автоматически.</p>
              </div>
              <div className="shorts-workflow__field shorts-workflow__saved-project">
                <label htmlFor="shorts-setup-project">Сохранённый проект</label>
                <select id="shorts-setup-project" className="shorts-workflow__input"
                  disabled={presenterSaving || (profilesLoading && !businessProfiles.length)}
                  value={selectedBusinessProfile ? String(businessProfileKey(selectedBusinessProfile)) : ''}
                  onChange={(event) => {
                    const profile = businessProfiles.find((item) => String(businessProfileKey(item)) === event.target.value);
                    if (profile) handleLoadBusinessProfile(profile, { preserveScriptChoices: true });
                    else {
                      setSelectedBusinessProfileId('');
                      saveSelectedProfileId('');
                      setBusinessName('');
                      setPresenterSaveStatus(null);
                    }
                  }}>
                  <option value="">{profilesLoading && !businessProfiles.length ? 'Загружаем проекты…' : 'Без проекта — заполнить вручную'}</option>
                  {businessProfiles.map((profile) => <option key={businessProfileKey(profile)} value={businessProfileKey(profile)}>{profile.name}</option>)}
                </select>
                {onManageProjects && <button type="button" onClick={onManageProjects}
                  className="shorts-workflow__button shorts-workflow__button--plain">{businessProfiles.length ? 'Управлять проектами' : 'Создать проект'}</button>}
              </div>
              {profilesError ? <p className="shorts-workflow__notice" data-tone="error" role="alert">
                {profilesError} <button type="button" className="shorts-workflow__button" onClick={() => setProfilesReload((value) => value + 1)}>Повторить</button>
              </p> : !profilesLoading && !businessProfiles.length && <p className="shorts-workflow__muted">
                {authToken ? 'В этом аккаунте пока нет сохранённых проектов.' : 'В этом браузере пока нет сохранённых проектов.'} Можно создать проект или заполнить бриф ниже.
              </p>}
            </section>
            <div className="shorts-workflow__setup-main">
              <div className="shorts-workflow__intro">
                <h2>Подготовим сценарий</h2>
                <p>{selectedBusinessProfile ? `Используем проект «${selectedBusinessProfile.name}». Выбери, как подготовить текст.` : 'Достаточно описания продукта или твоего готового текста.'}</p>
              </div>
              <section className="shorts-workflow__section" aria-labelledby="shorts-setup-script">
                <div className="shorts-workflow__section-heading">
                  <span className="shorts-workflow__section-number" aria-hidden="true">1</span>
                  <h3 id="shorts-setup-script">Как подготовим текст?</h3>
                </div>
                <div className="shorts-workflow__choices" role="group" aria-labelledby="shorts-setup-script">
                  {[
                    { id: 'ai', label: 'Написать с ИИ', description: 'Опиши продукт — получишь варианты' },
                    { id: 'custom', label: 'Вставить готовый текст', description: 'Используем твои реплики' },
                  ].map((mode) => (
                    <button key={mode.id} type="button" aria-pressed={scriptMode === mode.id}
                      onClick={() => { setScriptMode(mode.id); setAnalyzeError(''); }}
                      className="shorts-workflow__choice">
                      <span className="shorts-workflow__choice-mark" aria-hidden="true">
                        {scriptMode === mode.id && <Check size={14} />}
                      </span>
                      <span className="shorts-workflow__choice-copy">
                        <strong>{mode.label}</strong>
                        <span className="shorts-workflow__muted">{mode.description}</span>
                      </span>
                    </button>
                  ))}
                </div>
              </section>
              <section className="shorts-workflow__section" aria-labelledby="shorts-setup-brief">
                <div className="shorts-workflow__section-heading">
                  <span className="shorts-workflow__section-number" aria-hidden="true">2</span>
                  <h3 id="shorts-setup-brief">{scriptMode === 'custom' ? 'Добавь свой текст' : selectedBusinessProfile ? 'Описание из проекта' : 'Расскажи о продукте'}</h3>
                </div>
                {scriptMode === 'custom' ? (
                  <div className="shorts-workflow__field">
                    <label htmlFor="shorts-setup-narration">
                      Текст озвучки <span className="shorts-workflow__required">Обязательно</span>
                    </label>
                    <AutoTextarea id="shorts-setup-narration" aria-required="true"
                      aria-describedby="shorts-setup-narration-help" value={customScript}
                      onChange={(event) => setCustomScript(event.target.value)} minRows={4}
                      className="shorts-workflow__input" placeholder="Вставь текст, который должен произнести ведущий." />
                    <p id="shorts-setup-narration-help" className="shorts-workflow__muted">
                      {manualStoryboardImport
                        ? 'Готовая раскадровка распознана. Можно импортировать кадры.'
                        : 'Этот текст станет озвучкой. ИИ предложит кадры к нему.'}
                    </p>
                    {!manualStoryboardImport && isManualStoryboardImport('custom', 'storyboard_v3', customScript) && (
                      <div className="shorts-workflow__notice">
                        <span>В тексте уже есть заголовки кадров.</span>
                        <button type="button" className="shorts-workflow__button" onClick={() => setScriptFormat('storyboard_v3')}>
                          Использовать формат раскадровки
                        </button>
                      </div>
                    )}
                  </div>
                ) : selectedBusinessProfile && description.trim() ? (
                  <>
                    <p className="shorts-workflow__muted">Описание уже заполнено. Можно сразу написать сценарии или уточнить его для этого ролика.</p>
                    <details className="shorts-workflow__details shorts-workflow__project-description">
                      <summary>Посмотреть или изменить описание <ChevronDown size={15} aria-hidden="true" /></summary>
                      {briefProductField}
                    </details>
                  </>
                ) : briefProductField}
              </section>
              <div className="shorts-workflow__next-step">
                <div className="shorts-workflow__next-copy">
                  <h3>{manualStoryboardImport ? 'Дальше — проверка сценария' : 'Дальше — выбор сценария'}</h3>
                  <p id="shorts-brief-next-help">
                    {(scriptMode === 'custom' ? !customScript.trim() : !description.trim())
                      ? (scriptMode === 'custom' ? 'Вставь текст в поле выше, чтобы продолжить.' : 'Добавь описание продукта в поле выше, чтобы продолжить.')
                      : manualStoryboardImport ? 'Проверь импортированные кадры, затем открой раскадровку.'
                        : 'Проверь варианты и выбери тот, который пойдёт в ролик.'}
                  </p>
                </div>
                <button type="button" onClick={handleAnalyze}
                  disabled={analyzing || analyzeNeedsGemini || (scriptMode === 'custom' ? !customScript.trim() : !description.trim())}
                  aria-describedby="shorts-brief-next-help" className="shorts-workflow__button shorts-workflow__button--primary">
                  {analyzing && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
                  {analyzing
                    ? (manualStoryboardImport ? 'Импортируем раскадровку…' : 'Готовим сценарий…')
                    : manualStoryboardImport ? 'Импортировать раскадровку'
                      : scriptMode === 'custom' ? 'Подготовить ролик' : 'Написать сценарии'}
                </button>
                {(analyzeNeedsGemini || analyzeError) && (
                  <div className="shorts-workflow__studio-feedback">
                    {analyzeNeedsGemini && (
                      <div className="shorts-workflow__notice" data-shorts-api-note>
                        <span>Для сценариев с ИИ нужен ключ Gemini.</span>
                        {onOpenSettings && <button type="button" className="shorts-workflow__button" onClick={onOpenSettings}>Подключить Gemini</button>}
                      </div>
                    )}
                    {analyzeError && (
                      <p className="shorts-workflow__notice" data-tone="error" role="alert">
                        <AlertCircle size={16} aria-hidden="true" /> {analyzeError}
                      </p>
                    )}
                  </div>
                )}
              </div>
              <details className="shorts-workflow__details shorts-workflow__project-details">
                <summary>
                  {scriptMode === 'custom' ? 'Описание продукта и тема' : 'Уточнить тему ролика'}
                  <span className="shorts-workflow__muted">Необязательно</span><ChevronDown size={15} aria-hidden="true" />
                </summary>
                <div className="shorts-workflow__section">
                  {scriptMode === 'custom' && briefProductField}
                  {briefExtras}
                </div>
              </details>
            </div>

            <aside id="shorts-brief-resources" className="shorts-workflow__resources"
              aria-labelledby="shorts-brief-resources-title">
              <div className="shorts-workflow__studio-panel-head">
                <h2 id="shorts-brief-resources-title">Ведущий и голос</h2>
              </div>
              <section data-section="presenter-section" className="shorts-workflow__section" aria-labelledby="shorts-setup-presenter">
                <div>
                  <h3 id="shorts-setup-presenter" className="shorts-workflow__section-title">Аватар и озвучка</h3>
                  {/* Что выбрано сейчас: одна строка вместо простыни настроек.
                      Всё остальное раскрывается по кнопке. */}
                  <div className="shorts-workflow__presenter-summary">
                    <div className="h-12 w-9 shrink-0 overflow-hidden rounded-md border border-slate-200 bg-slate-100">
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
                          <img src={getApiUrl(selectedActorPreviewUrl)} alt="Выбранный аватар" className="h-full w-full object-cover" />
                        </button>
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-slate-600">
                          <User size={14} />
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {selectedActor
                          ? (actorGallery.find((actor) => actor.url === selectedActor)?.description || 'Аватар выбран')
                          : 'Аватар не выбран'}
                      </p>
                      <p className="shorts-workflow__muted truncate">
                        Голос: {selectedVoiceLabel}
                      </p>
                    </div>
                    <button
                      type="button"
                      aria-expanded={avatarPickerOpen}
                      onClick={() => setAvatarPickerOpen((open) => !open)}
                      className="shorts-workflow__button shorts-workflow__button--plain"
                    >
                      {avatarPickerOpen ? 'Скрыть аватары' : selectedActor ? 'Сменить аватар' : 'Выбрать аватар'}
                    </button>
                    <button
                      type="button"
                      aria-expanded={voicePickerOpen}
                      onClick={() => setVoicePickerOpen((open) => !open)}
                      className="shorts-workflow__button shorts-workflow__button--plain"
                    >
                      {voicePickerOpen ? 'Скрыть настройки голоса' : 'Выбрать голос'}
                    </button>
                  </div>

                  <div className="shorts-workflow__presenter-save">
                    {selectedBusinessProfile ? <>
                      <p className="shorts-workflow__muted">{selectedBusinessProfile.presenter
                        ? `Для проекта «${selectedBusinessProfile.name}». Сохрани изменения, чтобы использовать их в следующих роликах.`
                        : 'Сохрани аватар и голос в проект — они будут выбираться автоматически.'}</p>
                      <button type="button" className="shorts-workflow__button" disabled={presenterSaving}
                        onClick={handleSaveProjectPresenter}>
                        {presenterSaving ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Save size={14} aria-hidden="true" />}
                        {presenterSaving ? 'Сохраняем…' : 'Сохранить в проект'}
                      </button>
                    </> : <p className="shorts-workflow__muted">Чтобы запомнить аватар и голос, выбери проект в начале брифа.</p>}
                    {presenterSaveStatus && <p role="status" className="shorts-workflow__muted"
                      data-tone={presenterSaveStatus.error ? 'error' : undefined}>{presenterSaveStatus.text}</p>}
                  </div>

                  {avatarPickerOpen && (<>
                  {/* Пол актёра */}
                  <div className="mb-3 flex flex-wrap items-center gap-3">
                    <span className="text-xs font-medium text-slate-700">Пол</span>
                    <div className="flex gap-1 rounded-md bg-slate-50 p-1">
                      {[
                        { id: 'female', label: 'Женщина' },
                        { id: 'male', label: 'Мужчина' },
                      ].map((g) => (
                        <button
                          key={g.id}
                          type="button"
                          aria-pressed={actorGender === g.id}
                          onClick={() => setActorGender(g.id)}
                          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                            actorGender === g.id
                              ? 'bg-slate-200 text-slate-900'
                              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                          }`}
                        >
                          {g.label}
                        </button>
                      ))}
                    </div>
                    <span className="text-xs text-slate-600">влияет на голос по умолчанию и генерацию аватара</span>
                  </div>

                  {/* Сохранённые аватары. Ряды НЕ обрезаем: скролл с фиксированной
                      высотой резал плитки пополам — казалось, что вёрстка поехала. */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-semibold text-slate-800">Сохранённые аватары ({actorGallery.length})</p>
                      {selectedActor && (
                        <button
                          type="button"
                          onClick={() => setSelectedActor(null)}
                          className="text-xs text-slate-600 hover:text-slate-900"
                        >
                          Сбросить выбор
                        </button>
                      )}
                    </div>
                    {loadingGallery ? (
                      <p className="text-xs text-slate-600 flex items-center gap-1">
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
                            className={`relative rounded-md overflow-hidden border-2 transition-all aspect-[3/4] ${
                              selectedActor === img.url
                                ? 'border-slate-500 ring-2 ring-slate-300'
                                : 'border-slate-200 hover:border-slate-400'
                            }`}
                            title={
                              img.voice?.voice_name
                                ? `${img.description || `Аватар ${i + 1}`} · голос: ${img.voice.voice_name}`
                                : (img.description || `Аватар ${i + 1}`)
                            }
                          >
                            <img src={img.url} alt={`Actor ${i + 1}`} className="w-full h-full object-cover" />
                            {img.voice?.voice_id && (
                              <span className="absolute bottom-0 inset-x-0 flex items-center justify-center gap-0.5 bg-slate-800/80 py-0.5 text-[8px] font-semibold text-white">
                                <Volume2 size={8} />голос
                              </span>
                            )}
                            {selectedActor === img.url && (
                              <div className="absolute top-1 right-1 w-5 h-5 bg-slate-700 rounded-full flex items-center justify-center">
                                <Check size={10} className="text-white" />
                              </div>
                            )}
                          </button>
                        ))}
                        {/* Загрузка — такая же плитка в конце сетки: отдельная
                            широкая кнопка и висящее сбоку превью выглядели как
                            два оторванных друг от друга элемента. Загруженное
                            фото сразу выбирается и приезжает в сетку. */}
                        <label className="flex aspect-[3/4] cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed border-slate-300 bg-slate-50 text-center text-xs leading-tight text-slate-600 transition-colors hover:border-slate-400 hover:text-slate-900 focus-within:ring-2 focus-within:ring-slate-400">
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
                            className="sr-only"
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
                      <p className="text-xs text-slate-600">
                        Сохранённых аватаров пока нет — загрузи фото, чтобы у роликов было одно лицо.
                      </p>
                    )}
                    {actorUploadStatus && (
                      <p className={`text-xs ${/не удалось|fail/i.test(actorUploadStatus) ? 'text-red-700' : 'text-slate-600'}`}>
                        {actorUploadStatus}
                      </p>
                    )}
                  </div>

                  {/* Портрет крупно — отдельно от аватара. На общем плане лицо
                      занимает проценты кадра, и генератор дорисовывает черты
                      сам: отсюда «человек меняется» между дублями. */}
                  <div className="mt-4 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-semibold text-slate-800">Портрет крупно (источник лица)</p>
                      {selectedFace && (
                        <button
                          type="button"
                          onClick={() => { setSelectedFace(null); setFaceUploadStatus(''); }}
                          className="text-xs text-slate-600 hover:text-slate-900"
                        >
                          Убрать
                        </button>
                      )}
                    </div>
                    <p className="text-xs leading-relaxed text-slate-600">
                      Необязательно. Лицо берётся отсюда, а причёска, фигура и одежда — с аватара выше.
                      Нужен один человек, вертикальный кадр по грудь, лицо крупно и в резкости.
                    </p>
                    <div className="flex items-center gap-3">
                      <div className="h-16 w-12 shrink-0 overflow-hidden rounded-md border border-slate-200 bg-slate-100">
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
                          <div className="flex h-full w-full items-center justify-center text-slate-600">
                            <User size={14} />
                          </div>
                        )}
                      </div>
                      <label className="cursor-pointer rounded-md border border-dashed border-slate-300 px-3 py-2 text-xs text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900 focus-within:ring-2 focus-within:ring-slate-400">
                        {uploadingFace ? (
                          <span className="flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Загружаю...</span>
                        ) : (
                          <span className="flex items-center gap-1"><Upload size={12} /> {selectedFace ? 'Заменить портрет' : 'Загрузить портрет'}</span>
                        )}
                        <input
                          type="file"
                          accept="image/*"
                          className="sr-only"
                          onChange={async (e) => {
                            const file = e.target.files?.[0];
                            await handleFaceUpload(file);
                            e.target.value = '';
                          }}
                        />
                      </label>
                    </div>
                    {faceUploadStatus && (
                      <p className={`text-xs ${/не удалось|fail/i.test(faceUploadStatus) ? 'text-red-700' : 'text-slate-600'}`}>
                        {faceUploadStatus}
                      </p>
                    )}
                  </div>

                  {/* Свои ракурсы. Всё, что загружено сюда, не рисуется: ни
                      одного платного вызова на постановку, и лицо ровно то,
                      которое человек выбрал, — генератор его не пересочиняет. */}
                  <div className="mt-4 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs font-semibold text-slate-800">Свои ракурсы ведущего</p>
                    <p className="text-xs leading-relaxed text-slate-600">
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
                            <span className="text-xs font-medium text-slate-700">{slot.label}</span>
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
                                className="text-xs text-slate-600 hover:text-slate-900"
                              >
                                Убрать
                              </button>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="h-16 w-9 shrink-0 overflow-hidden rounded-md border border-slate-200 bg-slate-100">
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
                                <div className="flex h-full w-full items-center justify-center text-slate-600">
                                  <User size={14} />
                                </div>
                              )}
                            </div>
                            <label className="cursor-pointer rounded-md border border-dashed border-slate-300 px-2 py-1.5 text-xs text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900 focus-within:ring-2 focus-within:ring-slate-400">
                              {uploadingPlate === slot.key ? (
                                <span className="flex items-center gap-1"><Loader2 size={11} className="animate-spin" /> Загружаю...</span>
                              ) : (
                                <span className="flex items-center gap-1"><Upload size={11} /> {plateUrls[slot.key] ? 'Заменить' : 'Загрузить'}</span>
                              )}
                              <input
                                type="file"
                                accept="image/*"
                                className="sr-only"
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
                      <p className={`text-xs ${/не удалось|fail/i.test(plateUploadStatus) ? 'text-red-700' : 'text-slate-600'}`}>
                        {plateUploadStatus}
                      </p>
                    )}
                  </div>
                  </>)}
                </div>

                {/* Движок озвучки (TTS provider) */}
                {voicePickerOpen && (<>
                <div>
                  <label className="block text-sm font-medium text-slate-800 mb-2 flex items-center gap-2">
                    <Volume2 size={14} /> Движок озвучки
                  </label>
                  <div className="grid sm:grid-cols-3 gap-2">
                    {TTS_PROVIDER_OPTIONS.map((option) => (
                      <button
                        key={option.id}
                        type="button"
                        aria-pressed={ttsProvider === option.id}
                        onClick={() => setTtsProvider(option.id)}
                        className={`p-3 rounded-md border text-left transition-all ${
                          ttsProvider === option.id
                            ? 'border-slate-400 bg-slate-100 text-slate-900'
                            : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
                        }`}
                      >
                        <div className="text-sm font-semibold">{option.label}</div>
                        <div className="text-xs text-slate-600 mt-1">{option.desc}</div>
                      </button>
                    ))}
                  </div>
                  {ttsProvider === 'auto' && (
                    <p className="text-xs text-slate-600 mt-2">
                      Сначала ElevenLabs. Если голос из библиотеки требует платный план или падает — озвучка продолжится через fal MiniMax.
                    </p>
                  )}
                  {ttsProvider === 'fal_minimax' && (
                    <p className="text-xs text-slate-600 mt-2">
                      Озвучка через баланс fal.ai. Ключ ElevenLabs в этом режиме не нужен.
                    </p>
                  )}
                </div>

                {(ttsProvider === 'auto' || ttsProvider === 'fal_minimax') && (
                  <div>
                    <label className="block text-sm font-medium text-slate-800 mb-2">
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
                            <div className="text-xs text-slate-600 truncate">{option.desc}</div>
                          </div>
                          {option.value === minimaxVoice && <Check size={14} className="text-slate-700 shrink-0" />}
                        </div>
                      )}
                    />
                    <p className="text-xs text-slate-600 mt-1">
                      Используется сразу в режиме fal MiniMax или как запасной, если ElevenLabs не сработал в режиме Auto.
                    </p>
                  </div>
                )}

                {ttsProvider !== 'fal_minimax' && (
                  <div>
                    <label className="block text-sm font-medium text-slate-800 mb-2">Модель ElevenLabs</label>
                    <div role="group" aria-label="Модель ElevenLabs" className="grid grid-cols-2 gap-2">
                      {ELEVENLABS_MODEL_OPTIONS.map((option) => (
                        <button
                          key={option.id}
                          type="button"
                          aria-pressed={elevenLabsModel === option.id}
                          onClick={() => setElevenLabsModel(option.id)}
                          className={`min-h-11 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                            elevenLabsModel === option.id
                              ? 'border-slate-400 bg-slate-100 text-slate-900'
                              : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
                          }`}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                    {elevenLabsModel === 'eleven_v4' && (
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <label className="block text-xs text-slate-800">
                          <span className="flex justify-between"><span>Стабильность</span><span>{elevenLabsStability.toFixed(2)}</span></span>
                          <input
                            type="range" min="0" max="1" step="0.05"
                            value={elevenLabsStability}
                            onChange={(event) => setElevenLabsStability(Number(event.target.value))}
                            className="mt-2 w-full accent-slate-700"
                          />
                        </label>
                        <label className="block text-xs text-slate-800">
                          <span className="flex justify-between"><span>Сходство с голосом</span><span>{elevenLabsSimilarity.toFixed(2)}</span></span>
                          <input
                            type="range" min="0" max="1" step="0.05"
                            value={elevenLabsSimilarity}
                            onChange={(event) => setElevenLabsSimilarity(Number(event.target.value))}
                            className="mt-2 w-full accent-slate-700"
                          />
                        </label>
                      </div>
                    )}
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
                      <label className="block text-sm font-medium text-slate-800 mb-2 flex items-center gap-2">
                        <Volume2 size={14} /> Голос озвучки {language === 'es' ? '(испанский)' : language === 'ru' ? '(русский)' : '(английский)'}
                      </label>
                      {boundVoice?.voice_id && (
                        <div className={`mb-2 flex items-start gap-2 rounded-md border px-3 py-2 text-xs ${
                          manualVoiceOverridesBinding
                            ? 'border-amber-400/30 bg-amber-500/10 text-amber-900'
                            : 'border-slate-300 bg-slate-100 text-slate-900'
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
                        const selectedVoiceMissing = selectedVoice && !voices.some((v) => v.voice_id === selectedVoice);

                        if (filtered.length > 0) {
                          return (
                            <div className="space-y-1.5 max-h-48 overflow-y-auto custom-scrollbar">
                              {selectedVoiceMissing && (
                                <div className="w-full flex items-center gap-3 p-2.5 rounded-md border border-slate-400 bg-slate-100 text-slate-900">
                                  <div className="min-w-0 flex-1">
                                    <div className="text-sm font-medium truncate">{selectedVoiceName || selectedVoice}</div>
                                    <div className="text-xs text-slate-700">Выбранный голос · ID сохранён</div>
                                  </div>
                                  <Check size={14} className="shrink-0" />
                                </div>
                              )}
                              {filtered.map((v) => (
                                <div
                                  key={v.voice_id}
                                  role="button"
                                  aria-pressed={selectedVoice === v.voice_id}
                                  tabIndex={0}
                                  onClick={() => selectVoiceManually(v.voice_id, v.name)}
                                  onKeyDown={(e) => {
                                    if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                                      e.preventDefault();
                                      selectVoiceManually(v.voice_id, v.name);
                                    }
                                  }}
                                  className={`w-full flex items-center gap-3 p-2.5 rounded-md border text-left transition-all ${
                                    selectedVoice === v.voice_id
                                      ? 'border-slate-400 bg-slate-100 text-slate-700'
                                      : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
                                  }`}
                                >
                                  <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium truncate">{v.name}</div>
                                    <div className="text-xs text-slate-600">
                                      {[voiceLanguageSummary(v), v.labels?.accent, v.labels?.gender, v.category].filter(Boolean).join(' · ')}
                                    </div>
                                    {language === 'ru' && (
                                      <span className={`inline-flex mt-1 text-[9px] font-semibold px-1.5 py-0.5 rounded-full ${
                                        voiceLanguageScore(v, language) === 0
                                          ? 'bg-green-500/15 text-green-800'
                                          : 'bg-amber-500/15 text-amber-900'
                                      }`}>
                                        {voiceFitLabel(v, language)}
                                      </span>
                                    )}
                                  </div>
                                  {v.preview_url && (
                                    <button
                                      onClick={(e) => { e.stopPropagation(); new Audio(v.preview_url).play(); }}
                                      className="shrink-0 w-7 h-7 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-colors"
                                      aria-label={`Послушать голос ${v.name}`}
                                      title="Послушать голос"
                                    >
                                      <Volume2 size={12} />
                                    </button>
                                  )}
                                  {selectedVoice === v.voice_id && <Check size={14} className="text-slate-700 shrink-0" />}
                                </div>
                              ))}
                              {language === 'ru' && !hasLanguageVoice && (
                                <p className="text-xs text-amber-800 pt-1">
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
                            <div className="mt-2 p-2.5 rounded-md border border-amber-500/20 bg-amber-500/10 text-xs text-amber-900">
                              Голос задан вручную по ID. Убедись, что он русский или с русским акцентом.
                            </div>
                          );
                        }

                        const selectedScore = voiceLanguageScore(selectedVoiceMeta, language);
                        if (selectedScore === 0) return null;

                        return (
                          <div className="mt-2 p-2.5 rounded-md border border-amber-500/20 bg-amber-500/10 text-xs text-amber-900">
                            Голос не похож на русский ({selectedVoiceMeta.labels?.accent || 'акцент неизвестен'}).
                            Для естественной русской речи выбери русский голос или вставь его ID ниже.
                          </div>
                        );
                      })()}
                      {/* Ручной ID нужен раз в год — прячем, чтобы не мозолил глаза. */}
                      <details className="mt-3 rounded-md border border-slate-200 bg-slate-50">
                        <summary className="cursor-pointer list-none px-3 py-2 text-xs text-slate-600 hover:text-slate-800">
                          Ввести ID голоса вручную
                        </summary>
                        <div className="border-t border-slate-200 p-3">
                          <input
                            value={selectedVoice}
                            onChange={(e) => selectVoiceManually(e.target.value.trim())}
                            className="shorts-workflow__input font-mono" aria-label="ID голоса ElevenLabs"
                            placeholder="voice_id из ElevenLabs..."
                          />
                          <p className="text-xs text-slate-600 mt-1">
                            Пригодится, если нужный голос есть в ElevenLabs, но не попал в список выше.
                          </p>
                        </div>
                      </details>
                      <p className="text-xs text-slate-600 mt-1">
                        {actorGender === 'female' ? 'Женские' : 'Мужские'} голоса · нажми на динамик, чтобы послушать
                      </p>
                    </div>
                  );
                })()}
                </>)}
              </section>

            <details className="shorts-workflow__setup-side">
              <summary className="shorts-workflow__studio-panel-head">
                <h2>Настройки ролика</h2><span>Необязательно</span><ChevronDown size={16} aria-hidden="true" />
                <span className="shorts-workflow__settings-summary">
                  {scriptMode === 'custom' ? 'Длина по тексту' : '≈ ' + targetDurationSeconds + ' с'} · {selectedVoiceLabel}
                </span>
              </summary>
              <div className="shorts-workflow__side-content">
                <div className="shorts-workflow__form-grid">
                  <div className="shorts-workflow__field" data-section="script-format-section">
                    <label htmlFor="shorts-setup-format">Формат сценария</label>
                    <select
                      id="shorts-setup-format"
                      className="shorts-workflow__input"
                      value={scriptFormat}
                      onChange={(event) => setScriptFormat(event.target.value)}
                    >
                      {SCRIPT_FORMAT_OPTIONS.map((option) => (
                        <option key={option.id} value={option.id}>{option.label}</option>
                      ))}
                    </select>
                    <p className="shorts-workflow__muted">
                      {manualStoryboardImport
                        ? 'В раскадровку попадут ваши кадры и реплики.'
                        : SCRIPT_FORMAT_OPTIONS.find((option) => option.id === scriptFormat)?.desc}
                    </p>
                  </div>
                  <div className="shorts-workflow__field" data-section="target-duration-section">
                    <label htmlFor="shorts-setup-duration">Длина ролика</label>
                    <select
                      id="shorts-setup-duration"
                      className="shorts-workflow__input"
                      disabled={scriptMode === 'custom'}
                      value={scriptMode === 'custom' ? 'speech' : targetDurationSeconds}
                      onChange={(event) => setTargetDurationSeconds(Number(event.target.value))}
                    >
                      {scriptMode === 'custom' && <option value="speech">По длительности озвучки</option>}
                      {TARGET_DURATION_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                    <p className="shorts-workflow__muted">
                      {scriptMode === 'custom'
                        ? 'Длительность зависит от текста и темпа речи.'
                        : (TARGET_DURATION_OPTIONS.find((option) => option.value === Number(targetDurationSeconds))?.desc
                          || 'Ориентир для сценария') + '. Итог зависит от темпа речи.'}
                    </p>
                  </div>
                </div>
              <details className="shorts-workflow__details">
                <summary>
                  <strong>Параметры генерации</strong>
                  <span className="shorts-workflow__muted">{videoModeOption(videoMode).label}</span>
                  <ChevronDown size={15} aria-hidden="true" />
                </summary>
                <div className="shorts-workflow__section">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="shorts-workflow__field" data-section="generation-preset-section">
                      <label htmlFor="shorts-setup-preset">Подача</label>
                      <select
                        id="shorts-setup-preset"
                        className="shorts-workflow__input"
                        value={generationPreset}
                        disabled={analyzing}
                        onChange={(event) => selectGenerationPreset(event.target.value)}
                      >
                        <option value="calm_ugc">Спокойный UGC</option>
                        <option value="expressive">Выразительная</option>
                      </select>
                    </div>
                    <div className="shorts-workflow__field">
                      <label htmlFor="shorts-setup-style">Стиль ролика</label>
                      <select
                        id="shorts-setup-style"
                        className="shorts-workflow__input"
                        value={style}
                        onChange={(event) => setStyle(event.target.value)}
                      >
                        {STYLE_OPTIONS.map((option) => (
                          <option key={option.id} value={option.id}>{option.label}</option>
                        ))}
                      </select>
                      <p className="shorts-workflow__muted">{STYLE_OPTIONS.find((option) => option.id === style)?.desc}</p>
                    </div>
                    <div className="shorts-workflow__field" data-section="text-model-section">
                      <label htmlFor="shorts-setup-text-model">Модель текста</label>
                      <select
                        id="shorts-setup-text-model"
                        className="shorts-workflow__input"
                        value={textModel}
                        onChange={(event) => setTextModel(event.target.value)}
                      >
                        {TEXT_MODEL_OPTIONS.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.label}{model.id === 'pro' ? ' · платно' : ''}
                          </option>
                        ))}
                      </select>
                      <p className="shorts-workflow__muted">{TEXT_MODEL_OPTIONS.find((model) => model.id === textModel)?.desc}</p>
                    </div>
                    <div className="shorts-workflow__field" data-section="video-mode-section">
                      <label htmlFor="shorts-setup-video-model">Модель видео и качество</label>
                      <select
                        id="shorts-setup-video-model"
                        className="shorts-workflow__input"
                        value={videoMode}
                        onChange={(event) => setVideoMode(event.target.value)}
                      >
                        {activeVideoModeOptions(scriptFormat).map((mode) => (
                          <option key={mode.id} value={mode.id}>{mode.label} · {estimateModePriceLabel(mode.id)}</option>
                        ))}
                      </select>
                      <p className="shorts-workflow__muted">{videoModeOption(videoMode).desc} Цена указана за ролик.</p>
                    </div>
                    {scriptMode !== 'custom' && (
                      <div className="shorts-workflow__field">
                        <label htmlFor="shorts-setup-count">Количество вариантов сценария</label>
                        <select
                          id="shorts-setup-count"
                          className="shorts-workflow__input"
                          value={numScripts}
                          onChange={(event) => setNumScripts(Number(event.target.value))}
                        >
                          {[1, 2, 3, 5].map((count) => <option key={count} value={count}>{count}</option>)}
                        </select>
                      </div>
                    )}
                  </div>

                  <div className="grid gap-3">
                    {scriptFormat === 'storyboard_v3' && (
                      <>
                        <label className="flex items-start gap-3" data-section="broll-rhythm-section">
                          <input
                            type="checkbox"
                            checked={brollBetweenTalking}
                            onChange={(event) => setBrollBetweenTalking(event.target.checked)}
                            disabled={manualStoryboardImport}
                            className="mt-1"
                          />
                          <span>
                            Перебивка между кадрами с ведущим
                            <span className="shorts-workflow__muted block">Каждая вставка считается отдельным клипом от трёх секунд.</span>
                          </span>
                        </label>
                        <label className="flex items-start gap-3" data-section="changing-locations-section">
                          <input
                            type="checkbox"
                            checked={changingLocations}
                            onChange={(event) => setChangingLocations(event.target.checked)}
                            disabled={manualStoryboardImport}
                            className="mt-1"
                          />
                          <span>
                            Менять локации по ходу ролика
                            <span className="shorts-workflow__muted block">ИИ подбирает до трёх мест. Для каждой локации нужны отдельные постановочные кадры.</span>
                          </span>
                        </label>
                      </>
                    )}
                    <label className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={clipVisionQc}
                        onChange={(event) => setClipVisionQc(event.target.checked)}
                        className="mt-1"
                      />
                      <span>
                        ИИ-проверка кадров
                        <span className="shorts-workflow__muted block">Gemini отмечает возможный брак в готовом видео. Примерно $0.001 за ролик.</span>
                      </span>
                    </label>
                    <label className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={brollImageFirst}
                        onChange={(event) => setBrollImageFirst(event.target.checked)}
                        className="mt-1"
                      />
                      <span>
                        Подготовить изображение для каждой перебивки
                        <span className="shorts-workflow__muted block">Сначала изображение, затем анимация. Доплата $0.05 за кадр перебивки.</span>
                      </span>
                    </label>
                  </div>

                  <MusicPicker
                    enabled={backgroundMusic}
                    value={musicTrack}
                    volume={musicVolume}
                    onEnabledChange={setBackgroundMusic}
                    onChange={setMusicTrack}
                    onVolumeChange={setMusicVolume}
                  />
                </div>
              </details>
              </div>
            </details>
            </aside>
          </div>
        )}

        {/* ── Step 1: Analysis Results ─────────────────────────── */}
        {step === 1 && analysis && (
          <div className="shorts-workflow__page shorts-workflow__review">
            <div className="shorts-workflow__intro">
              <h2>Выбери сценарий</h2>
              <p>Нажми на вариант, прочитай текст и открой его в {storyboardSelected ? 'раскадровке' : 'настройках ролика'}.</p>
            </div>
            <section className="shorts-workflow__review-options" aria-labelledby="shorts-review-options">
              <div className="shorts-workflow__studio-panel-head">
                <h2 id="shorts-review-options">Варианты сценария</h2>
                <span>{scripts.length}</span>
              </div>
              {scripts.length > 0 ? (
                <ul className="shorts-workflow__review-list">
                  {scripts.map((script, i) => (
                    <li key={i}>
                      <button
                        type="button"
                        className="shorts-workflow__choice"
                        data-shorts-script-option={i + 1}
                        aria-pressed={selectedScript === i}
                        aria-controls="shorts-review-preview"
                        onClick={() => handleSelectScript(i)}
                      >
                        <span className="shorts-workflow__muted">{String(i + 1).padStart(2, '0')}</span>
                        <span className="min-w-0">
                          <span className="block font-medium break-words">{script.title || 'Вариант ' + (i + 1)}</span>
                          <span className="shorts-workflow__muted block">
                            {[
                              '≈ ' + estimateStoryboardSeconds(script, script.full_narration || '') + ' с',
                              script.shots?.length ? script.shots.length + ' ' + pluralShots(script.shots.length) : null,
                            ].filter(Boolean).join(' · ')}
                          </span>
                        </span>
                        {selectedScript === i && <span className="shorts-workflow__selection-status"><Check size={14} aria-hidden="true" /> Выбран</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="shorts-workflow__notice" data-empty>Вариантов пока нет.</p>
              )}
            </section>

            <section id="shorts-review-preview" className="shorts-workflow__review-detail" data-shorts-script-detail
              aria-label="Выбранный сценарий">
              <div className="shorts-workflow__studio-panel-head">
                <h2>Предпросмотр сценария</h2>
                {currentScript && <span>Вариант {String(selectedScript + 1).padStart(2, '0')}</span>}
              </div>
              <div className="shorts-workflow__review-content">
                {currentScript ? (
                  <>
                    <div className="shorts-workflow__review-meta">
                      <h3>{currentScript.title || 'Вариант ' + (selectedScript + 1)}</h3>
                      <p className="shorts-workflow__muted">
                        {[
                          '≈ ' + estimateStoryboardSeconds(currentScript, currentScript.full_narration || '') + ' с',
                          isStoryboardScript(currentScript) && currentScript.shots?.length
                            ? currentScript.shots.length + ' ' + pluralShots(currentScript.shots.length) : null,
                        ].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                    {isStoryboardScript(currentScript) && (currentScript.shots || []).length > 0 ? (
                      <ol className="shorts-workflow__review-rows">
                        {currentScript.shots.map((shot, j) => (
                          <li key={j} className="shorts-workflow__review-row">
                            <span className="shorts-workflow__shot-label">Кадр {shot.shot_number || j + 1}</span>
                            <div className="min-w-0 break-words">
                              {shot.speech && <p className="whitespace-pre-wrap">{shot.speech}</p>}
                              {(shot.scene || shot.generation_prompt) && (
                                <p className="shorts-workflow__scene-note"><span>В кадре</span> {shot.scene || shot.generation_prompt}</p>
                              )}
                            </div>
                          </li>
                        ))}
                      </ol>
                    ) : (currentScript.segments || []).length > 0 ? (
                      <ol className="shorts-workflow__review-rows">
                        {currentScript.segments.map((segment, j) => (
                          <li key={j} className="shorts-workflow__review-row">
                            <div className="shorts-workflow__muted">
                              <p>{{ hook: 'Начало', problem: 'Проблема', solution: 'Решение', cta: 'Призыв' }[segment.type] || segment.type}</p>
                              {segment.start != null && segment.end != null && <p>{segment.start}–{segment.end} с</p>}
                            </div>
                            <p className="min-w-0 whitespace-pre-wrap break-words">{segment.narration}</p>
                          </li>
                        ))}
                      </ol>
                    ) : currentScript.full_narration && (
                      <p className="mt-3 whitespace-pre-wrap break-words">{currentScript.full_narration}</p>
                    )}
                    {(currentScript.hashtags || []).length > 0 && (
                      <p className="shorts-workflow__muted mt-3 break-words">{currentScript.hashtags.slice(0, 4).join(' · ')}</p>
                    )}
                  </>
                ) : (
                  <p className="shorts-workflow__notice" data-empty>Сценарии пока не готовы. Вернись к брифу, чтобы создать варианты.</p>
                )}

                <details className="shorts-workflow__details shorts-workflow__review-analysis">
                  <summary>Анализ проекта и источники <ChevronDown size={15} /></summary>
                  <div className="space-y-4">
                    <div>
                      <h3 className="font-semibold break-words">{analysis.product_name || 'Анализ проекта'}</h3>
                      {analysis.industry && <p className="shorts-workflow__muted">{analysis.industry}</p>}
                      {(analysis.one_liner || analysis.description) && <p className="mt-2 break-words">{analysis.one_liner || analysis.description}</p>}
                      {fromCache && (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span className="shorts-workflow__muted">Сохранённый анализ</span>
                          <button
                            type="button"
                            className="shorts-workflow__button shorts-workflow__button--plain"
                            onClick={() => { setStep(0); setFromCache(false); }}
                          >
                            <RefreshCw size={14} /> Повторить анализ
                          </button>
                        </div>
                      )}
                    </div>

                    {(analysis.pain_points || []).length > 0 && (
                      <div>
                        <h3 className="font-semibold">Проблемы аудитории</h3>
                        <ul className="mt-2 space-y-2">
                          {analysis.pain_points.map((point, i) => (
                            <li key={i}>
                              <p>{point.pain}</p>
                              <p className="shorts-workflow__muted">
                                {[
                                  { high: 'Сильная', medium: 'Средняя', low: 'Слабая' }[point.intensity],
                                  point.source !== 'website' && point.source,
                                ].filter(Boolean).join(' · ')}
                              </p>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {(analysis.emotional_hooks || []).length > 0 && (
                      <div>
                        <h3 className="font-semibold">Что привлечёт внимание</h3>
                        <ul className="mt-2 list-disc space-y-1 pl-4">
                          {analysis.emotional_hooks.map((hook, i) => <li key={i}>{hook}</li>)}
                        </ul>
                      </div>
                    )}
                    {(analysis.pain_points || []).length === 0 && (analysis.emotional_hooks || []).length === 0 && (
                      <p className="shorts-workflow__muted">В быстром режиме сценарии строятся по описанию проекта.</p>
                    )}

                    {webResearch && (
                      <section className="space-y-3">
                        <h3 className="font-semibold">Исследование в интернете</h3>
                        {(webResearch.real_reviews || []).length > 0 && (
                          <div>
                            <h4 className="font-medium">Отзывы</h4>
                            <ul className="mt-2 space-y-2">
                              {webResearch.real_reviews.slice(0, 5).map((review, i) => (
                                <li key={i}>
                                  <p className="break-words">«{review.quote}»</p>
                                  <p className="shorts-workflow__muted">
                                    {[
                                      review.source,
                                      { positive: 'Положительный', negative: 'Отрицательный', neutral: 'Нейтральный' }[review.sentiment],
                                    ].filter(Boolean).join(' · ')}
                                  </p>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {(webResearch.competitors || []).length > 0 && (
                          <div>
                            <h4 className="font-medium">Конкуренты</h4>
                            <ul className="mt-2 space-y-2">
                              {webResearch.competitors.map((competitor, i) => (
                                <li key={i}>
                                  <p>{competitor.name}</p>
                                  {competitor.comparison && <p className="shorts-workflow__muted">{competitor.comparison}</p>}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {(webResearch.grounding_sources || []).length > 0 && (
                          <div>
                            <h4 className="font-medium">Источники <span className="shorts-workflow__muted">{webResearch.grounding_sources.length}</span></h4>
                            <ul className="mt-2 space-y-1">
                              {webResearch.grounding_sources.slice(0, 8).map((source, i) => (
                                <li key={i}>
                                  <a href={source.url} target="_blank" rel="noopener noreferrer" className="break-words underline underline-offset-2">
                                    {source.title || source.url}
                                  </a>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </section>
                    )}
                  </div>
                </details>
              </div>
            </section>
          </div>
        )}

        {/* ── Step 2: Configure ────────────────────────────────── */}
        {step === 2 && scripts[selectedScript] && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-6">
            <div className="glass-panel p-4 sm:p-6 space-y-5">
              <h2 className="text-lg font-semibold">Настройка ролика</h2>
              {renderGenerationSettings()}
              <p className="text-sm text-zinc-500">
                Сценарий: <strong className="text-zinc-300">{scripts[selectedScript].title}</strong>
              </p>

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

              {renderCostEstimate()}

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
              <button onClick={() => setStep(previousReadyStep)} className="btn-secondary px-4 py-2 text-sm flex items-center gap-2">
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
                  <MediaPlayer
                    src={getApiUrl(genResult.video_url)}
                    label="Готовый ролик"
                    className="w-full h-full"
                    mediaClassName="object-contain"
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

    </div>
      )}

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
    </>
  );
}

import React, { useState, useEffect } from 'react';
import { Globe, Sparkles, Download, Copy, Check, ChevronRight, ChevronLeft, Loader2, AlertCircle, Volume2, User, Film, Terminal, ChevronDown, RefreshCw, Zap, Target, TrendingUp, MessageSquare, Eye, Share2, Calendar, Upload } from 'lucide-react';
import { getApiUrl } from '../config';

const STYLE_OPTIONS = [
  { id: 'ugc', label: 'UGC Natural', desc: 'Authentic, talking to camera' },
  { id: 'educational', label: 'Educational', desc: 'Clear explanations' },
  { id: 'shock', label: 'Shock/Discovery', desc: 'Surprising opener' },
  { id: 'story', label: 'Storytelling', desc: 'Mini narrative arc' },
  { id: 'comparison', label: 'Before/After', desc: 'Comparison style' },
];

const TTS_PROVIDER_OPTIONS = [
  { id: 'auto', label: 'Auto fallback', desc: 'ElevenLabs first, fal MiniMax if needed' },
  { id: 'elevenlabs', label: 'ElevenLabs', desc: 'Best voice quality, may need paid plan' },
  { id: 'fal_minimax', label: 'fal MiniMax', desc: 'Russian TTS via fal.ai balance' },
];

const BROLL_MODE_OPTIONS = [
  { id: 'mockup', label: 'Product mockups', desc: 'Clean local inserts, no AI stock scenes' },
  { id: 'off', label: 'Off', desc: 'Talking head only, fewer distractions' },
  { id: 'ai', label: 'AI b-roll', desc: 'Flux image inserts, can look synthetic' },
];

const VIDEO_MODE_OPTIONS = [
  {
    id: 'lowcost',
    label: 'Супер дешёвый',
    price: 'from ~$0.45',
    accent: 'green',
    desc: 'Draft mode: Hailuo + VEED lipsync. Cheap, but can loop or drift.',
  },
  {
    id: 'standard',
    label: 'Средний',
    price: 'from ~$0.75',
    accent: 'blue',
    desc: 'Kling Avatar v2 Standard. Good baseline for tests and daily volume.',
  },
  {
    id: 'premium',
    label: 'Премиум',
    price: 'from ~$1.45',
    accent: 'violet',
    desc: 'Kling Avatar v2 Pro. Best choice when the video is going to publish.',
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

function estimateSaasVideoCost({ text, videoMode, ttsProvider, brollMode, hasSelectedActor, hasReusableHead = false, lipsyncModel = 'sync-3' }) {
  const seconds = estimateSpeechSeconds(text);
  const ttsRate = ttsProvider === 'fal_minimax' ? 0.0001 : 0.00003;
  const voiceCost = (text || '').length * ttsRate;
  const actorCost = (hasSelectedActor || hasReusableHead) ? 0 : 0.05;
  let videoCost = 0;

  if (hasReusableHead) {
    const option = LIPSYNC_MODEL_OPTIONS.find((item) => item.id === lipsyncModel) || LIPSYNC_MODEL_OPTIONS[0];
    videoCost = (seconds / 60) * option.pricePerMinute;
  } else if (videoMode === 'lowcost') {
    videoCost = 0.19 + 0.20;
  } else if (videoMode === 'premium') {
    videoCost = seconds * 0.115;
  } else {
    videoCost = seconds * 0.0562;
  }

  const brollCost = brollMode === 'ai' ? 0.10 : 0;
  const total = actorCost + voiceCost + videoCost + brollCost;
  return {
    seconds,
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

export default function SaaShortsTab({ geminiApiKey, elevenLabsKey, falKey, uploadPostKey, uploadUserId }) {
  // Wizard state
  const [step, setStep] = useState(() => {
    const cache = loadCache();
    return cache ? 1 : 0;
  });

  // Step 0: URL input
  const [url, setUrl] = useState(() => loadCache()?.url || '');
  const [videoMode, setVideoMode] = useState('standard'); // "lowcost", "standard", or "premium"
  const [description, setDescription] = useState(() => loadCache()?.description || '');
  const [topic, setTopic] = useState(() => loadCache()?.topic || '');
  const [scriptMode, setScriptMode] = useState(() => loadCache()?.scriptMode || 'ai'); // "ai" or "custom"
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

  // Step 2: Configure
  const [voices, setVoices] = useState([]);
  const [ttsProvider, setTtsProvider] = useState('auto');
  const [brollMode, setBrollMode] = useState('mockup');
  const [selectedVoice, setSelectedVoice] = useState('21m00Tcm4TlvDq8ikWAM');
  const [minimaxVoice, setMinimaxVoice] = useState('Russian_AmbitiousWoman');
  const [actorDescription, setActorDescription] = useState('');
  const [editedNarration, setEditedNarration] = useState('');
  const [actorOptions, setActorOptions] = useState([]);
  const [selectedActor, setSelectedActor] = useState(null);
  const [actorSource, setActorSource] = useState('saved');
  const [generatingActors, setGeneratingActors] = useState(false);
  const [actorGallery, setActorGallery] = useState([]);
  const [loadingGallery, setLoadingGallery] = useState(false);
  const [headTemplates, setHeadTemplates] = useState([]);
  const [loadingHeadTemplates, setLoadingHeadTemplates] = useState(false);
  const [selectedHeadTemplate, setSelectedHeadTemplate] = useState('');
  const [savingHeadTemplate, setSavingHeadTemplate] = useState(false);
  const [headTemplateStatus, setHeadTemplateStatus] = useState('');
  const [uploadedActorPreview, setUploadedActorPreview] = useState(null); // {localPreview, serverUrl}
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

  // Fetch actor gallery on mount
  useEffect(() => {
    setLoadingGallery(true);
    fetch(getApiUrl('/api/saasshorts/actor-gallery'))
      .then(res => res.ok ? res.json() : { images: [] })
      .then(data => setActorGallery(data.images || []))
      .catch(() => {})
      .finally(() => setLoadingGallery(false));
  }, []);

  useEffect(() => {
    refreshHeadTemplates();
  }, []);

  // Fetch voices on mount
  useEffect(() => {
    if (elevenLabsKey) {
      fetchVoices();
    }
  }, [elevenLabsKey]);

  // Reset selected voice when actor gender changes
  useEffect(() => {
    const genderDefaults = {
      'en-female': '21m00Tcm4TlvDq8ikWAM',  // Rachel
      'en-male': '29vD33N1CtxCmqQRPOHJ',    // Drew
      'es-female': 'EXAVITQu4vr4xnSDxMaL',  // Bella
      'es-male': 'ErXwobaYiN019PkySvjV',     // Antoni
      'ru-female': '21m00Tcm4TlvDq8ikWAM',  // Multilingual fallback
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

  useEffect(() => {
    setMinimaxVoice(defaultMiniMaxVoice(language, actorGender));
  }, [actorGender, language]);

  // Poll generation status
  useEffect(() => {
    let interval;
    if (jobId && genStatus === 'processing') {
      interval = setInterval(async () => {
        try {
          const res = await fetch(getApiUrl(`/api/saasshorts/status/${jobId}`));
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
      const res = await fetch(getApiUrl('/api/saasshorts/voices'), {
        headers: { 'X-ElevenLabs-Key': elevenLabsKey },
      });
      if (res.ok) {
        const data = await res.json();
        setVoices(data.voices || []);
      }
    } catch (e) {
      console.error('Voices fetch error:', e);
    }
  };

  const handleAnalyze = async () => {
    const isCustom = scriptMode === 'custom';
    if (isCustom && !customScript.trim()) return;
    if (!isCustom && !url.trim() && !description.trim()) return;
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
          'X-Gemini-Key': geminiApiKey,
        },
        body: JSON.stringify({
          url: url.trim() || undefined,
          description: description.trim() || undefined,
          topic: topic.trim() || undefined,
          script_mode: scriptMode,
          custom_script: isCustom ? customScript.trim() : undefined,
          num_scripts: numScripts,
          style,
          language,
          actor_gender: actorGender,
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
      setSelectedScript(0);
      setFromCache(false);

      // Cache results
      saveCache({
        url: url.trim(),
        description: description.trim(),
        topic: topic.trim(),
        scriptMode,
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
      scriptToSend._product_url = url;
      if (editedNarration !== scriptToSend.full_narration) {
        scriptToSend.full_narration = editedNarration;
      }

      const headers = {
        'Content-Type': 'application/json',
        'X-Fal-Key': falKey,
      };
      if (elevenLabsKey) headers['X-ElevenLabs-Key'] = elevenLabsKey;

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
          broll_mode: brollMode,
          reusable_head_template_id: selectedHeadTemplate || undefined,
          reusable_lipsync_model: lipSyncModel,
        }),
      });

      if (!res.ok) {
        let msg = 'Generation failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      setJobId(data.job_id);
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
      scriptToSend._product_url = url;
      if (editedNarration !== scriptToSend.full_narration) {
        scriptToSend.full_narration = editedNarration;
      }

      const headers = {
        'Content-Type': 'application/json',
        'X-Fal-Key': falKey,
      };
      if (elevenLabsKey) headers['X-ElevenLabs-Key'] = elevenLabsKey;

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
          retry_job_id: jobId,
          video_mode: videoMode,
          broll_mode: brollMode,
          reusable_head_template_id: selectedHeadTemplate || undefined,
          reusable_lipsync_model: lipSyncModel,
        }),
      });

      if (!res.ok) {
        let msg = 'Retry failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const data = await res.json();
      setJobId(data.job_id);
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
          'X-Fal-Key': falKey,
        },
        body: JSON.stringify({
          job_id: jobId,
          model: lipSyncModel,
          sync_mode: 'cut_off',
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
      const res = await fetch(getApiUrl('/api/saasshorts/actor-gallery'));
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
      const res = await fetch(getApiUrl('/api/saasshorts/head-templates'));
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
        headers: { 'Content-Type': 'application/json' },
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
    setUrl('');
    setAnalyzeError('');
    setAnalysis(null);
    setWebResearch(null);
    setScripts([]);
    setFromCache(false);
    localStorage.removeItem(CACHE_KEY);
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
    return [description, topic].filter(Boolean).join(' ');
  })();

  const estimateForMode = (modeId) => estimateSaasVideoCost({
    text: estimateInputText,
    videoMode: modeId,
    ttsProvider,
    brollMode,
    hasSelectedActor: Boolean(selectedActor),
  });

  const estimateModePriceLabel = (modeId) => `~${formatUsd(estimateForMode(modeId).total)}`;

  // ─── Render Steps ─────────────────────────────────────────────────

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="max-w-5xl mx-auto p-6 lg:p-8">
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
              {/* Video Mode Selector */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-3">Video Mode</label>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {VIDEO_MODE_OPTIONS.map((mode) => {
                    const active = videoMode === mode.id;
                    const activeClass =
                      mode.id === 'lowcost' ? 'border-green-500/50 bg-green-500/10 ring-1 ring-green-500/30' :
                      mode.id === 'standard' ? 'border-blue-500/50 bg-blue-500/10 ring-1 ring-blue-500/30' :
                      'border-violet-500/50 bg-violet-500/10 ring-1 ring-violet-500/30';
                    const textClass =
                      active && mode.id === 'lowcost' ? 'text-green-300' :
                      active && mode.id === 'standard' ? 'text-blue-300' :
                      active && mode.id === 'premium' ? 'text-violet-300' :
                      'text-zinc-300';
                    const priceClass =
                      mode.id === 'lowcost' ? 'text-green-400 bg-green-500/10' :
                      mode.id === 'standard' ? 'text-blue-400 bg-blue-500/10' :
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
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">Website URL <span className="text-zinc-600">(optional)</span></label>
                <div className="flex gap-3">
                  <div className="relative flex-1">
                    <Globe size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-zinc-500" />
                    <input
                      type="url"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://your-website.com"
                      className="input-field !pl-12"
                      onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                    />
                  </div>
                </div>
                <p className="text-[10px] text-zinc-600 mt-1">If provided, we'll scrape and research your site automatically</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-3">Script Input Mode</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {[
                    { id: 'ai', label: 'AI generate scripts', desc: 'Use product + topic as a brief' },
                    { id: 'custom', label: 'Use my exact script', desc: 'Keep narration text unchanged' },
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

              <div>
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
                  Current video topic <span className="text-zinc-600">(optional, but recommended)</span>
                </label>
                <textarea
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  rows={2}
                  className="input-field resize-none text-sm"
                  placeholder="e.g. Почему вечерний срыв начинается утром; What to eat at 5 PM to avoid night cravings..."
                />
                <p className="text-[10px] text-zinc-600 mt-1">AI mode will generate scripts around this topic. Custom mode uses it for title, hook overlay, caption and b-roll prompts.</p>
              </div>

              {scriptMode === 'custom' && (
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">
                    Exact narration script <span className="text-zinc-600">(required)</span>
                  </label>
                  <textarea
                    value={customScript}
                    onChange={(e) => setCustomScript(e.target.value)}
                    rows={7}
                    className="input-field resize-none font-mono text-xs"
                    placeholder={`Ты срываешься вечером не потому, что слабая.\nЧасто проблема начинается утром: кофе вместо завтрака, маленький обед...\nНапиши "НЕДЕЛЯ" - пришлю чеклист антисрыв-вечера.`}
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">
                    {customScript.length} chars &middot; ~{Math.max(1, Math.round(customScript.trim().split(/\s+/).filter(Boolean).length / 2.5))}s speech. This text will not be rewritten before video generation.
                  </p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-3">Language</label>
                <div className="flex gap-2 mb-6">
                  {[
                    { id: 'en', label: 'English', flag: '🇺🇸' },
                    { id: 'es', label: 'Español', flag: '🇪🇸' },
                    { id: 'ru', label: 'Русский', flag: '🇷🇺' },
                  ].map((l) => (
                    <button
                      key={l.id}
                      onClick={() => setLanguage(l.id)}
                      className={`flex-1 p-3 rounded-xl border text-center transition-all ${
                        language === l.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <span className="text-lg">{l.flag}</span>
                      <div className="text-xs font-medium mt-1">{l.label}</div>
                    </button>
                  ))}
                </div>

                <label className="block text-sm font-medium text-zinc-300 mb-3">Actor</label>
                <div className="flex gap-2 mb-6">
                  {[
                    { id: 'female', label: 'Woman', icon: '👩' },
                    { id: 'male', label: 'Man', icon: '👨' },
                  ].map((g) => (
                    <button
                      key={g.id}
                      onClick={() => setActorGender(g.id)}
                      className={`flex-1 p-3 rounded-xl border text-center transition-all ${
                        actorGender === g.id
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:bg-white/10'
                      }`}
                    >
                      <span className="text-lg">{g.icon}</span>
                      <div className="text-xs font-medium mt-1">{g.label}</div>
                    </button>
                  ))}
                </div>

                <label className="block text-sm font-medium text-zinc-300 mb-3">Video Style</label>
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
                <label className="block text-sm font-medium text-zinc-300 mb-2">Number of Scripts</label>
                <div className="flex gap-2">
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
                      {n}
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
                    {scriptMode === 'custom' ? 'Preparing custom script...' : (url.trim() ? 'Scraping + Researching web + Generating scripts... (45-90s)' : 'Generating scripts... (20-40s)')}
                  </>
                ) : (
                  <>
                    <Sparkles size={16} />
                    {scriptMode === 'custom' ? 'Prepare Custom Script' : (url.trim() ? 'Research & Generate Scripts' : 'Generate Scripts')}
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
                <h3 className="text-sm font-medium text-zinc-300">AI Actor Videos</h3>
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
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Eye size={18} className="text-violet-400" />
                  {analysis.product_name || 'Analysis'}
                </h2>
                <div className="flex items-center gap-2">
                  {fromCache && (
                    <span className="text-[10px] bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded-full border border-amber-500/20 flex items-center gap-1">
                      Cached
                      <button onClick={() => { setStep(0); setFromCache(false); }} className="hover:text-white ml-1" title="Re-analyze">
                        <RefreshCw size={9} />
                      </button>
                    </span>
                  )}
                  <span className="text-xs bg-violet-500/10 text-violet-400 px-2 py-1 rounded-full border border-violet-500/20">
                    {analysis.industry}
                  </span>
                </div>
              </div>
              <p className="text-sm text-zinc-400 mb-4">{analysis.one_liner}</p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                            <span className="ml-1.5 text-[9px] bg-blue-500/10 text-blue-400 px-1 py-0.5 rounded">{pp.source}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
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
              </div>
            </div>

            {/* Web Research Results */}
            {webResearch && (
              <div className="glass-panel p-6">
                <h3 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
                  <Globe size={14} className="text-blue-400" />
                  Web Research (Google Search)
                  {webResearch.grounding_sources && (
                    <span className="text-[10px] bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full ml-auto">
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
                          className="text-[10px] text-blue-400 hover:text-blue-300 bg-blue-500/5 px-2 py-0.5 rounded-full border border-blue-500/10 hover:border-blue-500/30 transition-colors truncate max-w-[200px]"
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
                <span className="text-xs bg-white/10 px-2 py-0.5 rounded-full ml-auto">{scripts.length} scripts</span>
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
                          <span className="text-[10px] text-zinc-500">{script.duration_seconds}s &middot; {script.style} &middot; {script.target_platform}</span>
                        </div>
                      </div>
                      {selectedScript === i && (
                        <span className="text-[10px] bg-violet-500/20 text-violet-300 px-2 py-0.5 rounded-full">Selected</span>
                      )}
                    </div>

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

                    {/* Hook text & hashtags */}
                    <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-3 flex-wrap">
                      <span className="text-[10px] bg-red-500/10 text-red-300 px-2 py-0.5 rounded-full">
                        Hook: &quot;{script.hook_text}&quot;
                      </span>
                      {(script.hashtags || []).slice(0, 4).map((tag, j) => (
                        <span key={j} className="text-[10px] text-zinc-500">{tag}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep(0)} className="btn-secondary px-4 py-2 text-sm flex items-center gap-2">
                <ChevronLeft size={14} /> Back
              </button>
              <button onClick={() => setStep(2)} className="btn-primary px-6 py-2 text-sm flex items-center gap-2">
                Configure Video <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: Configure ────────────────────────────────── */}
        {step === 2 && scripts[selectedScript] && (
          <div className="animate-[fadeIn_0.3s_ease-out] space-y-6">
            <div className="glass-panel p-6 space-y-5">
              <h2 className="text-lg font-semibold">Configure Video</h2>
              <p className="text-sm text-zinc-500">
                Script: <strong className="text-zinc-300">{scripts[selectedScript].title}</strong>
              </p>

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

              {/* Voice Selection */}
              {ttsProvider !== 'fal_minimax' && (
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                  <Volume2 size={14} /> Voice {language === 'es' ? '(Spanish)' : language === 'ru' ? '(Russian)' : '(English)'}
                </label>
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
              </div>
              )}

              {/* B-roll Mode */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                  <Film size={14} /> B-roll
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
                  Product mockups are the default for this offer because dramatic AI lifestyle scenes often reduce trust.
                </p>
              </div>

              {/* Talking-head source */}
              <div className="p-4 rounded-xl border border-white/10 bg-white/5 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 flex items-center gap-2">
                      <User size={14} /> Источник говорящей головы
                    </label>
                    <p className="text-xs text-zinc-500 mt-1">
                      Можно один раз сгенерировать дорогой talking-head, сохранить его и дальше менять только озвучку через lipsync.
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
                        ? 'border-blue-500/50 bg-blue-500/10 text-blue-200'
                        : 'border-white/10 bg-black/20 text-zinc-400 hover:bg-white/10'
                    }`}
                  >
                    <div className="text-sm font-semibold">Создать новую</div>
                    <div className="text-[10px] text-zinc-500 mt-1">Kling/Hailuo генерирует новый talking-head под эту озвучку.</div>
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
                    <div className="text-sm font-semibold">Использовать сохранённую</div>
                    <div className="text-[10px] text-zinc-500 mt-1">
                      {headTemplates.length > 0 ? 'Дешевле: новая озвучка + Sync Lipsync.' : 'Сначала сохрани talking-head из готового ролика.'}
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

              {/* Actor Selection: Gallery + Generate New */}
              <div className={selectedHeadTemplate ? 'opacity-50 pointer-events-none' : ''}>
                <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                  <User size={14} /> AI Actor
                </label>

                <div className="grid grid-cols-2 gap-1 bg-white/5 p-1 rounded-xl mb-3">
                  {[
                    { id: 'saved', label: 'Saved' },
                    { id: 'upload', label: 'Upload' },
                  ].map((source) => (
                    <button
                      key={source.id}
                      type="button"
                      onClick={() => setActorSource(source.id)}
                      className={`px-3 py-2 rounded-lg text-xs font-semibold transition-colors ${
                        actorSource === source.id
                          ? 'bg-violet-500/25 text-violet-200'
                          : 'text-zinc-500 hover:text-zinc-200 hover:bg-white/5'
                      }`}
                    >
                      {source.label}
                    </button>
                  ))}
                </div>

                {actorSource === 'saved' && (
                  <div className="space-y-3">
                    {loadingGallery ? (
                      <p className="text-xs text-zinc-500 flex items-center gap-1">
                        <Loader2 size={12} className="animate-spin" /> Loading saved avatars...
                      </p>
                    ) : actorGallery.length > 0 ? (
                      <div className="grid grid-cols-4 sm:grid-cols-6 gap-2 max-h-56 overflow-y-auto pr-1 custom-scrollbar">
                        {actorGallery.map((img, i) => (
                          <button
                            key={img.url}
                            type="button"
                            onClick={() => setSelectedActor(img.url)}
                            className={`relative rounded-lg overflow-hidden border-2 transition-all aspect-[3/4] ${
                              selectedActor === img.url
                                ? 'border-violet-500 ring-2 ring-violet-500/30 scale-[1.02]'
                                : 'border-white/10 hover:border-white/30'
                            }`}
                            title={img.description || `Saved avatar ${i + 1}`}
                          >
                            <img src={img.url} alt={`Actor ${i + 1}`} className="w-full h-full object-cover" />
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
                        No saved avatars yet. Create avatars in UGC Gallery / Avatars, or upload a photo here.
                      </div>
                    )}
                  </div>
                )}

                {actorSource === 'upload' && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <label className="flex-1 flex items-center justify-center gap-2 text-sm bg-white/5 text-zinc-400 px-4 py-3 rounded-xl border border-dashed border-white/20 hover:bg-white/10 hover:border-white/30 transition-colors cursor-pointer">
                        <Upload size={14} />
                        <span>Upload and save avatar</span>
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
                    {actorUploadStatus && (
                      <p className={`text-[10px] ${actorUploadStatus.toLowerCase().includes('fail') ? 'text-red-300' : 'text-zinc-500'}`}>
                        {actorUploadStatus}
                      </p>
                    )}
                  </div>
                )}

                {!selectedActor && (
                  <p className="text-xs text-amber-400 mt-3 flex items-center gap-1">
                    <AlertCircle size={12} /> Select or upload an actor to continue
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
                        headers: { 'Content-Type': 'application/json', 'X-Fal-Key': falKey },
                        body: JSON.stringify({ actor_description: actorDescription, num_options: 3 }),
                      });
                      if (res.ok) {
                        const data = await res.json();
                        setActorOptions(data.images || []);
                        // Refresh gallery to include newly uploaded actors
                        const galRes = await fetch(getApiUrl('/api/saasshorts/actor-gallery'));
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

                {!selectedActor && (actorOptions.length > 0 || actorGallery.length > 0) && (
                  <p className="text-xs text-amber-400 mt-2 flex items-center gap-1"><AlertCircle size={12} /> Select an actor to continue</p>
                )}
              </div>

              )}

              {/* Narration Edit */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
                  <MessageSquare size={14} /> Narration Script
                </label>
                <textarea
                  value={editedNarration}
                  onChange={(e) => setEditedNarration(e.target.value)}
                  rows={5}
                  className="input-field resize-none font-mono text-xs"
                />
                <p className="text-[10px] text-zinc-600 mt-1">{editedNarration.length} chars &middot; ~{estimateSpeechSeconds(editedNarration)}s speech</p>
              </div>

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
                });
                const costDetails =
                  selectedHeadTemplate
                    ? 'Saved talking head + new voiceover + Sync Lipsync. Faster and cheaper than regenerating Kling/Hailuo.'
                    : videoMode === 'lowcost'
                    ? 'Озвучка + Hailuo 2.3 + VEED Lipsync. Дешевый черновой режим, качество может плыть.'
                    : videoMode === 'premium'
                      ? 'Озвучка + Kling Avatar v2 Pro. Лучший вариант для публикации.'
                      : 'Озвучка + Kling Avatar v2 Standard. Баланс цены и качества.';

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
                <ChevronLeft size={14} /> Back
              </button>
              <button
                onClick={handleGenerate}
                disabled={!falKey || (ttsProvider === 'elevenlabs' && !elevenLabsKey) || (!selectedActor && !selectedHeadTemplate) || generating}
                className="btn-primary px-6 py-2 text-sm flex items-center gap-2 disabled:opacity-50"
              >
                {generating ? (
                  <><Loader2 size={14} className="animate-spin" /> Generating...</>
                ) : (!selectedActor && !selectedHeadTemplate) ? (
                  <><User size={14} /> Select an actor first</>
                ) : selectedHeadTemplate ? (
                  <><Volume2 size={14} /> Generate via saved head ({formatUsd(estimateSaasVideoCost({ text: editedNarration, videoMode, ttsProvider, brollMode, hasSelectedActor: Boolean(selectedActor), hasReusableHead: true, lipsyncModel }).total)})</>
                ) : (
                  <><Film size={14} /> Generate Video ({formatUsd(estimateSaasVideoCost({ text: editedNarration, videoMode, ttsProvider, brollMode, hasSelectedActor: Boolean(selectedActor), hasReusableHead: false, lipsyncModel }).total)})</>
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
                  const noBroll = !isLipSyncJob && brollMode === 'off';
                  const labels = isLipSyncJob
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
                      : normalStepDone();
                    const stepActive = isLipSyncJob
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
                        <span className="text-xs font-medium text-zinc-400">Caption</span>
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

                  <div className="p-4 bg-blue-500/5 rounded-xl border border-blue-500/20 space-y-2">
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
                      <p className={`text-[11px] ${headTemplateStatus.toLowerCase().includes('не удалось') ? 'text-red-300' : 'text-blue-200'}`}>
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
                              };
                              if (isScheduling && scheduleDate) {
                                payload.scheduled_date = new Date(scheduleDate).toISOString();
                                payload.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
                              }
                              const res = await fetch(getApiUrl('/api/saasshorts/post'), {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
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

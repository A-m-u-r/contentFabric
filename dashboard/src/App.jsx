import React, { useState, useEffect } from 'react';
import { Upload, Download, Archive, FileVideo, Sparkles, Youtube, Instagram, Share2, LogOut, ChevronDown, Check, Activity, LayoutDashboard, Settings, PlusCircle, History, Menu, X, Terminal, Shield, LayoutGrid, Image, RotateCcw, Calendar, AlertTriangle, KeyRound, Bot, Users, Smartphone, ExternalLink, Copy, CheckCircle2, Target, CalendarDays } from 'lucide-react';
import KeyInput from './components/KeyInput';
import MediaInput from './components/MediaInput';
import ResultCard from './components/ResultCard';
import ProcessingAnimation from './components/ProcessingAnimation';
// import Gallery from './components/Gallery';
import ThumbnailStudio from './components/ThumbnailStudio';
import SaaShortsTab from './components/SaaShortsTab';
import ProjectsTab from './components/ProjectsTab';
import ContentPlanTab from './components/ContentPlanTab';
import UGCGallery from './components/UGCGallery';
import ScheduleWeekModal from './components/ScheduleWeekModal';
import { getApiUrl } from './config';
import { useRuntimeLocalization } from './localization/runtimeLocalization';

// Enhanced "Encryption" using XOR + Base64 with a Salt
// This is better than plain Base64 but still client-side.
const SECRET_KEY = import.meta.env.VITE_ENCRYPTION_KEY || "OpenShorts-Static-Salt-Change-Me";
const ENCRYPTION_PREFIX = "ENC:";

const encrypt = (text) => {
  if (!text) return '';
  try {
    const xor = text.split('').map((c, i) =>
      String.fromCharCode(c.charCodeAt(0) ^ SECRET_KEY.charCodeAt(i % SECRET_KEY.length))
    ).join('');
    return ENCRYPTION_PREFIX + btoa(xor);
  } catch (e) {
    console.error("Encryption failed", e);
    return text;
  }
};

const decrypt = (text) => {
  if (!text) return '';
  if (text.startsWith(ENCRYPTION_PREFIX)) {
    try {
      const raw = text.slice(ENCRYPTION_PREFIX.length);
      // Check if it's plain base64 or our custom XOR (simple try)
      const xor = atob(raw);
      const result = xor.split('').map((c, i) =>
        String.fromCharCode(c.charCodeAt(0) ^ SECRET_KEY.charCodeAt(i % SECRET_KEY.length))
      ).join('');
      return result;
    } catch (e) {
      // Fallback if decryption fails (might be old plain text)
      return '';
    }
  }
  // Backward compatibility: If no prefix, assume old plain text (or return empty if you want to force re-login)
  // For migration: Return text as is, so it populates the field, and next save will encrypt it.
  return text;
};

// Simple TikTok icon sine Lucide might not have it or it varies
const TikTokIcon = ({ size = 16, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M19.589 6.686a4.793 4.793 0 0 1-3.77-4.245V2h-3.445v13.672a2.896 2.896 0 0 1-5.201 1.743l-.002-.001.002.001a2.895 2.895 0 0 1 3.183-4.51v-3.5a6.329 6.329 0 0 0-5.394 10.692 6.33 6.33 0 0 0 10.857-4.424V8.687a8.182 8.182 0 0 0 4.773 1.526V6.79a4.831 4.831 0 0 1-1.003-.104z" />
  </svg>
);

const UserProfileSelector = ({ profiles, selectedUserId, onSelect }) => {
  const [isOpen, setIsOpen] = useState(false);

  if (!profiles || profiles.length === 0) return null;

  const selectedProfile = profiles.find(p => p.username === selectedUserId) || profiles[0];

  return (
    <div className="relative z-50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm text-zinc-300 hover:bg-white/5 transition-colors min-w-[180px]"
      >
        <span className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center text-[10px] font-bold text-white">
            {selectedProfile?.username?.substring(0, 1).toUpperCase() || "U"}
          </div>
          <span className="font-medium text-white truncate max-w-[100px]">{selectedProfile?.username || "Select User"}</span>
        </span>
        <ChevronDown size={14} className={`text-zinc-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute top-full mt-2 right-0 w-64 bg-[#1a1a1a] border border-white/10 rounded-xl shadow-2xl overflow-hidden">
          <div className="max-h-60 overflow-y-auto custom-scrollbar">
            {profiles.map((profile) => (
              <button
                key={profile.username}
                onClick={() => {
                  onSelect(profile.username);
                  setIsOpen(false);
                }}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors text-left group border-b border-white/5 last:border-0"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/20 to-purple-500/20 flex items-center justify-center text-xs font-bold text-white border border-white/10 shrink-0">
                    {profile.username.substring(0, 2).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-zinc-200 group-hover:text-white transition-colors truncate">
                      {profile.username}
                    </div>
                    <div className="flex gap-2 mt-0.5">
                      {/* Status indicators */}
                      <div className={`flex items-center gap-1 text-[10px] ${profile.connected.includes('tiktok') ? 'text-zinc-300' : 'text-zinc-600'}`}>
                        <TikTokIcon size={10} />
                      </div>
                      <div className={`flex items-center gap-1 text-[10px] ${profile.connected.includes('instagram') ? 'text-pink-400' : 'text-zinc-600'}`}>
                        <Instagram size={10} />
                      </div>
                      <div className={`flex items-center gap-1 text-[10px] ${profile.connected.includes('youtube') ? 'text-red-400' : 'text-zinc-600'}`}>
                        <Youtube size={10} />
                      </div>
                    </div>
                  </div>
                </div>
                {selectedUserId === profile.username && <Check size={14} className="text-primary shrink-0" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const SESSION_KEY = 'openshorts_session';
const SESSION_MAX_AGE = 3600000; // 1 hour (matches server job retention)
const AUTH_TOKEN_KEY = 'openshorts_auth_token';
const USE_PLATFORM_KEYS_KEY = 'openshorts_use_platform_keys';

// Mock polling function
const pollJob = async (jobId) => {
  const res = await fetch(getApiUrl(`/api/status/${jobId}`));
  if (!res.ok) throw new Error('Status check failed');
  return res.json();
};

const AuthScreen = ({ mode, setMode, loading, error, onSubmit }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const isRegister = mode === 'register';

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="w-full max-w-md glass-panel p-8 space-y-6">
        <div className="space-y-2">
          <div className="w-11 h-11 rounded-xl bg-violet-500/15 text-violet-300 flex items-center justify-center">
            <Shield size={22} />
          </div>
          <h1 className="text-2xl font-bold text-white">
            {isRegister ? 'Создать аккаунт' : 'Войти в аккаунт'}
          </h1>
        </div>

        <div className="space-y-3">
          {isRegister && (
            <input
              className="input-field"
              aria-label="Имя"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Имя"
            />
          )}
          <input
            className="input-field"
            type="email"
            aria-label="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@example.com"
          />
          <input
            className="input-field"
            type="password"
            aria-label="Пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Пароль, минимум 8 символов"
          />
          {error && (
            <div className="rounded-xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-sm text-red-200">
              {error}
            </div>
          )}
          <button
            className="btn-primary w-full py-3"
            disabled={loading}
            onClick={() => onSubmit({ email, password, name })}
          >
            {loading ? 'Подождите...' : isRegister ? 'Зарегистрироваться' : 'Войти'}
          </button>
        </div>

        <button
          type="button"
          className="inline-flex rounded-lg px-2 py-2 text-sm text-zinc-400 transition-colors hover:bg-white/5 hover:text-white"
          onClick={() => setMode(isRegister ? 'login' : 'register')}
        >
          {isRegister ? 'Уже есть аккаунт? Войти' : 'Нет аккаунта? Зарегистрироваться'}
        </button>
      </div>
    </div>
  );
};

const ProviderKeyInput = ({
  title,
  description,
  value,
  onChange,
  placeholder,
  hasAccountKey,
  onSave,
  actionLabel = 'Сохранить',
  savedLabel = 'Сохранено в аккаунте',
  help,
  links = [],
}) => {
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const hasDraftKey = Boolean(value?.trim()) && value !== '__saved__' && value !== '__platform__';

  const handleSave = async () => {
    setMessage('');
    if (!hasDraftKey) {
      setMessage(hasAccountKey ? 'Вставь новый ключ, чтобы заменить текущий.' : 'Вставь API-ключ перед сохранением.');
      return;
    }

    setSaving(true);
    try {
      await onSave(value.trim());
      setMessage(savedLabel);
    } catch (e) {
      setMessage(e.message || 'Не удалось сохранить ключ.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
          <p className="text-xs leading-relaxed text-zinc-500">{description}</p>
        </div>
        <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
          hasAccountKey
            ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200'
            : 'border-amber-500/25 bg-amber-500/10 text-amber-200'
        }`}>
          {hasAccountKey ? <CheckCircle2 size={13} /> : <KeyRound size={13} />}
          {hasAccountKey ? savedLabel : 'Не сохранено'}
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr),auto]">
        <input
          type="password"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setMessage('');
          }}
          className="input-field"
          placeholder={hasAccountKey ? 'Ключ скрыт. Вставь новый, чтобы заменить.' : placeholder}
          autoComplete="off"
        />
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="btn-primary whitespace-nowrap px-4 py-3 text-sm"
        >
          {saving ? 'Сохраняю...' : hasAccountKey ? 'Заменить' : actionLabel}
        </button>
      </div>

      {message && (
        <p className={`rounded-lg border px-3 py-2 text-xs ${
          message === savedLabel
            ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200'
            : 'border-amber-500/20 bg-amber-500/10 text-amber-200'
        }`}>
          {message}
        </p>
      )}

      {(help || links.length > 0) && (
        <div className="space-y-3 text-xs leading-relaxed text-zinc-500">
          {help && <p>{help}</p>}
          {links.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {links.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-xl border border-white/10 bg-black/20 p-3 transition-colors hover:border-white/20 hover:bg-white/[0.04]"
                >
                  <span className="flex items-center gap-2 font-medium text-zinc-300">
                    {link.label}
                    <ExternalLink size={12} className="text-zinc-500" />
                  </span>
                  {link.caption && <span className="mt-1 block text-[11px] text-zinc-600">{link.caption}</span>}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Russian plural for "клип": 1 клип, 2 клипа, 5 клипов.
const clipsPlural = (n) => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'клип';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'клипа';
  return 'клипов';
};

function App() {
  useRuntimeLocalization('ru');

  const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_KEY) || '');
  const [authUser, setAuthUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authMode, setAuthMode] = useState('login');
  const [authError, setAuthError] = useState('');
  const [apiKeyStatus, setApiKeyStatus] = useState({});
  const [usePlatformKeys, setUsePlatformKeys] = useState(() => localStorage.getItem(USE_PLATFORM_KEYS_KEY) === '1');
  const [legacyClaimStatus, setLegacyClaimStatus] = useState('');
  const [backupStatus, setBackupStatus] = useState('');
  const [backupImporting, setBackupImporting] = useState(false);

  const [apiKey, setApiKey] = useState(localStorage.getItem('gemini_key') || import.meta.env.VITE_GEMINI_API_KEY || '');
  // Social API State - Load encrypted or plain
  const [uploadPostKey, setUploadPostKey] = useState(() => {
    const stored = localStorage.getItem('uploadPostKey_v3');
    if (stored) return decrypt(stored);
    return '';
  });
  // ElevenLabs API State - Load encrypted
  const [elevenLabsKey, setElevenLabsKey] = useState(() => {
    const stored = localStorage.getItem('elevenLabsKey_v1');
    if (stored) return decrypt(stored);
    return '';
  });

  // fal.ai API State - Load encrypted
  const [falKey, setFalKey] = useState(() => {
    const stored = localStorage.getItem('falKey_v1');
    if (stored) return decrypt(stored);
    return '';
  });

  const [uploadUserId, setUploadUserId] = useState(() => localStorage.getItem('uploadUserId') || '');
  const [userProfiles, setUserProfiles] = useState([]); // List of {username, connected: []}
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState('idle'); // idle, processing, complete, error
  const [results, setResults] = useState(null);
  const [logs, setLogs] = useState([]);
  const [logsVisible, setLogsVisible] = useState(true);
  const [processingMedia, setProcessingMedia] = useState(null);
  const [activeTab, setActiveTab] = useState('saasshorts'); // saasshorts (главный), dashboard, settings

  const [sessionRecovered, setSessionRecovered] = useState(false);
  const [showScheduleWeek, setShowScheduleWeek] = useState(false);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);

  // Sync state for original video playback
  const [syncedTime, setSyncedTime] = useState(0);
  const [isSyncedPlaying, setIsSyncedPlaying] = useState(false);
  const [syncTrigger, setSyncTrigger] = useState(0);

  const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});
  const hasSavedKey = (provider) => Boolean(apiKeyStatus?.[provider]?.has_key);
  const canUsePlatformKeys = authUser?.subscription_status === 'active';
  const usingPlatformKeys = usePlatformKeys && canUsePlatformKeys;
  const effectiveGeminiKey = usingPlatformKeys ? '__platform__' : (hasSavedKey('gemini') ? '__saved__' : apiKey);
  const effectiveFalKey = usingPlatformKeys ? '__platform__' : (hasSavedKey('fal') ? '__saved__' : falKey);
  const effectiveElevenLabsKey = usingPlatformKeys ? '__platform__' : (hasSavedKey('elevenlabs') ? '__saved__' : elevenLabsKey);
  const effectiveUploadPostKey = usingPlatformKeys ? '__platform__' : (hasSavedKey('upload_post') ? '__saved__' : uploadPostKey);

  const handleClipPlay = (startTime) => {
    setSyncedTime(startTime);
    setIsSyncedPlaying(true);
    setSyncTrigger(prev => prev + 1);
  };

  const handleClipPause = () => {
    setIsSyncedPlaying(false);
  };

  const applyAuthPayload = (data, tokenOverride) => {
    if (tokenOverride) {
      setAuthToken(tokenOverride);
      localStorage.setItem(AUTH_TOKEN_KEY, tokenOverride);
    }
    setAuthUser(data.user || null);
    setApiKeyStatus(data.api_keys || {});
  };

  const loadMe = async (token = authToken) => {
    if (!token) {
      setAuthLoading(false);
      return;
    }
    try {
      const res = await fetch(getApiUrl('/api/auth/me'), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Session expired');
      const data = await res.json();
      applyAuthPayload(data, token);
    } catch {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      setAuthToken('');
      setAuthUser(null);
      setApiKeyStatus({});
    } finally {
      setAuthLoading(false);
    }
  };

  useEffect(() => {
    loadMe(authToken);
  }, []);

  useEffect(() => {
    localStorage.setItem(USE_PLATFORM_KEYS_KEY, usePlatformKeys ? '1' : '0');
  }, [usePlatformKeys]);

  const handleAuthSubmit = async ({ email, password, name }) => {
    setAuthError('');
    setAuthLoading(true);
    try {
      const res = await fetch(getApiUrl(authMode === 'register' ? '/api/auth/register' : '/api/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, name }),
      });
      if (!res.ok) {
        let msg = 'Auth failed';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
      const data = await res.json();
      applyAuthPayload(data, data.token);
    } catch (e) {
      setAuthError(e.message || 'Auth failed');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(SESSION_KEY);
    setAuthToken('');
    setAuthUser(null);
    setApiKeyStatus({});
    setStatus('idle');
  };

  const handleSaveApiKey = async (provider, value) => {
    const cleaned = (value || '').trim();
    if (!cleaned || cleaned === '__saved__' || cleaned === '__platform__') return;
    const res = await fetch(getApiUrl('/api/user/api-keys'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify({ provider, api_key: cleaned }),
    });
    if (!res.ok) {
      let msg = 'Не удалось сохранить API-ключ';
      try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
      throw new Error(msg);
    }
    const data = await res.json();
    setApiKeyStatus(data.api_keys || {});
    return data.api_keys || {};
  };

  const handleClaimLegacyAssets = async () => {
    setLegacyClaimStatus('Переношу старые данные...');
    try {
      const res = await fetch(getApiUrl('/api/user/claim-legacy-assets'), {
        method: 'POST',
        headers: authHeaders(),
      });
      if (!res.ok) {
        let msg = 'Не удалось перенести старые данные';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
      const data = await res.json();
      const c = data.claimed || {};
      setLegacyClaimStatus(`Перенесено: видео ${c.videos || 0}, talking-head ${c.head_templates || 0}, аватары ${c.actors || 0}.`);
    } catch (e) {
      setLegacyClaimStatus(e.message || 'Не удалось перенести старые данные');
    }
  };

  const handleExportBackup = async () => {
    setBackupStatus('Готовлю архив переноса...');
    try {
      const res = await fetch(getApiUrl('/api/backup/export'), {
        headers: authHeaders(),
      });
      if (!res.ok) {
        let msg = 'Не удалось скачать backup';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }

      const blob = await res.blob();
      const disposition = res.headers.get('content-disposition') || '';
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
      const filename = filenameMatch?.[1] || `content-factory-backup-${new Date().toISOString().slice(0, 10)}.zip`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setBackupStatus('Архив скачан. Перенеси ZIP на другой компьютер и импортируй его в настройках.');
    } catch (e) {
      setBackupStatus(e.message || 'Не удалось скачать backup');
    }
  };

  const handleImportBackup = async (file) => {
    if (!file) return;
    setBackupImporting(true);
    setBackupStatus('Импортирую backup...');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(getApiUrl('/api/backup/import'), {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) {
        let msg = 'Не удалось импортировать backup';
        try { const err = await res.json(); msg = err.detail || msg; } catch { msg = await res.text() || msg; }
        throw new Error(msg);
      }
      const data = await res.json();
      setBackupStatus(`Backup восстановлен: файлов ${data.restored_files || 0}. Если ключи не видны, перезапусти backend и войди заново.`);
      await loadMe();
    } catch (e) {
      setBackupStatus(e.message || 'Не удалось импортировать backup');
    } finally {
      setBackupImporting(false);
    }
  };

  // Session Recovery: Restore on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(SESSION_KEY);
      if (!saved) return;
      const session = JSON.parse(saved);
      if (Date.now() - session.timestamp > SESSION_MAX_AGE) {
        localStorage.removeItem(SESSION_KEY);
        return;
      }
      if (session.jobId && session.status && session.status !== 'idle') {
        setJobId(session.jobId);
        setResults(session.results || null);
        if (session.processingMedia) setProcessingMedia(session.processingMedia);
        if (session.activeTab) setActiveTab(session.activeTab);
        // If was processing, resume polling; if complete/error, just show results
        setStatus(session.status === 'processing' ? 'processing' : session.status);
        setSessionRecovered(true);
        setTimeout(() => setSessionRecovered(false), 5000);
      }
    } catch (e) {
      localStorage.removeItem(SESSION_KEY);
    }
  }, []);

  // Session Recovery: Save state changes
  useEffect(() => {
    if (status === 'idle') {
      localStorage.removeItem(SESSION_KEY);
      return;
    }
    try {
      const sessionData = {
        jobId,
        status,
        results,
        processingMedia: processingMedia?.type === 'url' ? processingMedia : null,
        activeTab,
        timestamp: Date.now()
      };
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionData));
    } catch (e) {
      // localStorage full or serialization error - ignore
    }
  }, [jobId, status, results, activeTab]);

  useEffect(() => {
    // Encrypt Gemini Key too for consistency if desired, but user asked specifically about Social integration not saving well.
    // For now keeping gemini plain for compatibility unless requested.
    if (apiKey) localStorage.setItem('gemini_key', apiKey);
  }, [apiKey]);

  useEffect(() => {
    if (uploadPostKey) {
      localStorage.setItem('uploadPostKey_v3', encrypt(uploadPostKey));
    }
    if (uploadUserId) {
      localStorage.setItem('uploadUserId', uploadUserId);
    }
  }, [uploadPostKey, uploadUserId]);

  useEffect(() => {
    if (elevenLabsKey) {
      localStorage.setItem('elevenLabsKey_v1', encrypt(elevenLabsKey));
    }
  }, [elevenLabsKey]);

  useEffect(() => {
    if (falKey) {
      localStorage.setItem('falKey_v1', encrypt(falKey));
    }
  }, [falKey]);

  useEffect(() => {
    if (effectiveUploadPostKey && userProfiles.length === 0) {
      fetchUserProfiles({ silent: true });
    }
  }, [effectiveUploadPostKey, authToken, usePlatformKeys]);

  useEffect(() => {
    let interval;
    if ((status === 'processing' || status === 'completed') && jobId) {
      interval = setInterval(async () => {
        try {
          const data = await pollJob(jobId);
          console.log("Job status:", data);

          // Update results if available (real-time)
          if (data.result) {
            setResults(data.result);
          }

          if (data.status === 'completed') {
            setStatus('complete');
            clearInterval(interval);
          } else if (data.status === 'failed') {
            setStatus('error');
            const errorMsg = data.error || (data.logs && data.logs.length > 0 ? data.logs[data.logs.length - 1] : "Process failed");
            setLogs(prev => [...prev, "Error: " + errorMsg]);
            clearInterval(interval);
          } else {
            // Update logs if available
            if (data.logs) setLogs(data.logs);
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [status, jobId]);


  const fetchUserProfiles = async ({ silent = false } = {}) => {
    if (!effectiveUploadPostKey) return;
    try {
      const headers = { ...authHeaders() };
      if (!['__saved__', '__platform__'].includes(effectiveUploadPostKey)) {
        headers['X-Upload-Post-Key'] = effectiveUploadPostKey;
      }
      const path = `/api/social/user${usingPlatformKeys ? '?use_platform_keys=true' : ''}`;
      const res = await fetch(getApiUrl(path), { headers });
      if (!res.ok) throw new Error("Failed to fetch");
      const data = await res.json();
      if (data.profiles && data.profiles.length > 0) {
        setUserProfiles(data.profiles);
        // Auto select first if none selected
        if (!uploadUserId) {
          setUploadUserId(data.profiles[0].username);
        }
      } else {
        if (!silent) alert("No profiles found for this API Key.");
      }
    } catch (e) {
      if (!silent) alert("Error fetching User Profiles. Please check key.");
      console.error(e);
    }
  };

  const handleProcess = async (data) => {
    if (!effectiveGeminiKey) {
      setShowKeyModal(true);
      return;
    }
    setStatus('processing');
    setLogs(["Starting process..."]);
    setResults(null);
    setProcessingMedia(data);

    try {
      let body;
      const headers = { ...authHeaders() };
      if (!['__saved__', '__platform__'].includes(effectiveGeminiKey)) {
        headers['X-Gemini-Key'] = effectiveGeminiKey;
      }
      if (usingPlatformKeys) headers['X-Use-Platform-Keys'] = 'true';

      if (data.type === 'url') {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify({ url: data.payload, acknowledged: !!data.acknowledged, use_platform_keys: usingPlatformKeys });
      } else {
        const formData = new FormData();
        formData.append('file', data.payload);
        formData.append('acknowledged', data.acknowledged ? 'true' : 'false');
        body = formData;
      }

      const res = await fetch(getApiUrl('/api/process'), {
        method: 'POST',
        headers,
        body
      });

      if (!res.ok) throw new Error(await res.text());
      const resData = await res.json();
      setJobId(resData.job_id);

    } catch (e) {
      setStatus('error');
      setLogs(l => [...l, `Error starting job: ${e.message}`]);
    }
  };

  const handleReset = () => {
    setStatus('idle');
    setJobId(null);
    setResults(null);
    setLogs([]);
    setProcessingMedia(null);
    localStorage.removeItem(SESSION_KEY);
  };

  // --- UI Components ---

  // One nav config drives both the desktop sidebar and the mobile bar so they
  // can never drift. A single brand accent (violet) marks the active tab.
  const navItems = [
    { id: 'saasshorts', label: 'AI Shorts', shortLabel: 'Shorts', icon: Sparkles },
    { id: 'dashboard', label: 'Генератор клипов', shortLabel: 'Клипы', icon: LayoutDashboard },
    { id: 'projects', label: 'Проекты', shortLabel: 'Проекты', icon: Target },
    { id: 'content-plan', label: 'Контент-план', shortLabel: 'План', icon: CalendarDays },
    // 'ai-agent' скрыт из навигации: сейчас это маркетинговая страница со
    // ссылкой на публичный GitHub, а не рабочая фича. Вернём, когда будет что показать.
    { id: 'ugc-gallery', label: 'UGC-галерея', shortLabel: 'UGC', icon: LayoutGrid },
    { id: 'thumbnails', label: 'YouTube-студия', shortLabel: 'YouTube', icon: Image },
    { id: 'settings', label: 'Настройки', shortLabel: 'Ключи', icon: Settings },
  ];
  const NAV_ACTIVE = 'bg-primary/10 text-primary';
  const NAV_INACTIVE = 'text-zinc-400 hover:text-white hover:bg-white/5';
  const activeNavItem = navItems.find((item) => item.id === activeTab) || navItems[0];
  const ActiveHeaderIcon = activeNavItem.icon;

  const Sidebar = () => (
    <div className="relative z-20 hidden w-20 shrink-0 flex-col border-r border-white/5 bg-surface transition-all duration-300 md:flex xl:w-64">
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-white/5 rounded-lg flex items-center justify-center shrink-0 overflow-hidden border border-white/5">
          <img src="/favicon.svg" alt="" className="w-full h-full object-cover" />
        </div>
        <span className="font-bold text-lg text-white hidden xl:block tracking-tight">Контентфабрика</span>
      </div>

      <nav className="flex-1 px-4 py-4 space-y-1.5">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
              title={item.label}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors ${isActive ? NAV_ACTIVE : NAV_INACTIVE}`}
            >
              <Icon size={20} className="shrink-0" />
              <span className="font-medium hidden xl:block">{item.label}</span>
            </button>
          );
        })}
      </nav>

    </div>
  );

  // Bottom bar keeps one clean row: the 4 primary tabs + an «Ещё» button that
  // reveals the rest in a popover. Everything stays reachable on mobile without
  // a cramped two-row bar.
  const MobileTabBar = () => {
    const primary = navItems.slice(0, 4);
    const overflow = navItems.slice(4);
    const overflowActive = overflow.some((item) => item.id === activeTab);
    const tabButtonClass = (isActive) =>
      `flex min-h-[54px] flex-col items-center justify-center gap-1 rounded-xl px-0.5 text-[10px] font-semibold transition-colors ${
        isActive ? 'bg-primary/10 text-primary' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-200'
      }`;

    return (
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-background/95 px-2 pb-3 pt-2 backdrop-blur md:hidden">
        {mobileMoreOpen && (
          <>
            <div className="fixed inset-0 z-0" onClick={() => setMobileMoreOpen(false)} />
            <div className="absolute bottom-full right-2 z-10 mb-2 w-56 rounded-2xl border border-white/10 bg-[#1a1a1a] p-2 shadow-2xl">
              {overflow.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => { setActiveTab(item.id); setMobileMoreOpen(false); }}
                    aria-current={isActive ? 'page' : undefined}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${
                      isActive ? 'bg-primary/10 text-primary' : 'text-zinc-300 hover:bg-white/5'
                    }`}
                  >
                    <Icon size={18} className="shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </>
        )}
        <div className="relative z-10 grid gap-1" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }}>
          {primary.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => { setActiveTab(item.id); setMobileMoreOpen(false); }}
                aria-label={item.label}
                aria-current={isActive ? 'page' : undefined}
                className={tabButtonClass(isActive)}
              >
                <Icon size={18} className="shrink-0" />
                <span className="max-w-full truncate">{item.shortLabel}</span>
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => setMobileMoreOpen((v) => !v)}
            aria-label="Ещё разделы"
            aria-expanded={mobileMoreOpen}
            className={tabButtonClass(overflowActive || mobileMoreOpen)}
          >
            <Menu size={18} className="shrink-0" />
            <span className="max-w-full truncate">Ещё</span>
          </button>
        </div>
      </nav>
    );
  };

  if (authLoading && !authUser) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center text-zinc-400">
        Загрузка аккаунта...
      </div>
    );
  }

  if (!authUser) {
    return (
      <AuthScreen
        mode={authMode}
        setMode={setAuthMode}
        loading={authLoading}
        error={authError}
        onSubmit={handleAuthSubmit}
      />
    );
  }

  return (
    <div className="flex h-dvh bg-background overflow-hidden selection:bg-primary/30">
      <Sidebar />

      <main className="relative mb-20 flex min-w-0 flex-1 flex-col overflow-hidden md:mb-0">
        {/* Background Gradients */}
        <div className="absolute inset-0 overflow-hidden -z-10 pointer-events-none">
          <div className="absolute -top-[10%] -right-[10%] w-[50%] h-[50%] bg-primary/5 rounded-full blur-[120px]" />
        </div>

        {/* Top Header */}
        <header className="h-16 border-b border-white/5 bg-background/50 backdrop-blur-md flex items-center justify-between px-4 md:px-6 shrink-0 z-10">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 md:hidden">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/5 text-violet-300">
                <ActiveHeaderIcon size={17} />
              </div>
              <span className="text-sm font-semibold text-zinc-100">{activeNavItem.label}</span>
            </div>
            {status !== 'idle' && (
              <button
                type="button"
                onClick={handleReset}
                className="hidden sm:flex items-center gap-2 rounded-lg px-2 py-2 text-sm text-zinc-400 transition-colors hover:bg-white/5 hover:text-white"
              >
                <PlusCircle size={16} />
                <span>Новый проект</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-zinc-300">
              <Users size={13} />
              <span>{authUser.email}</span>
              <span className={`rounded-full px-2 py-0.5 ${
                authUser.subscription_status === 'active'
                  ? 'bg-green-500/15 text-green-300'
                  : 'bg-zinc-500/15 text-zinc-400'
              }`}>
                {authUser.subscription_status === 'active' ? 'Подписка active' : 'Free'}
              </span>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex items-center gap-1.5 rounded-lg px-2 py-2 text-xs text-zinc-500 transition-colors hover:bg-white/5 hover:text-white"
            >
              <LogOut size={14} /> Выйти
            </button>

            {userProfiles.length > 0 && (
              <UserProfileSelector
                profiles={userProfiles}
                selectedUserId={uploadUserId}
                onSelect={setUploadUserId}
              />
            )}

          </div>
        </header>

        {/* Persistent Missing Key Banner — visible on every screen */}
        {!effectiveGeminiKey && activeTab !== 'settings' && (
          <div className="mx-6 mt-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-center justify-between gap-4 shrink-0 animate-[fadeIn_0.3s_ease-out]">
            <div className="flex items-center gap-3 text-sm text-amber-200">
              <KeyRound size={16} className="shrink-0 text-amber-400" />
              <div>
                <span className="font-semibold">Не хватает обязательного API-ключа.</span>{' '}
                <span className="text-amber-200/80">
                  Укажи API-ключ Gemini, чтобы пользоваться Контентфабрикой.
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setActiveTab('settings')}
              className="shrink-0 rounded-lg bg-amber-500 px-3 py-2 text-xs font-medium text-black transition-colors hover:bg-amber-400"
            >
              Настройки
            </button>
          </div>
        )}

        {/* Session Recovery Banner */}
        {sessionRecovered && (
          <div className="mx-6 mt-2 p-3 bg-primary/10 border border-primary/20 rounded-xl flex items-center justify-between animate-[fadeIn_0.3s_ease-out] shrink-0">
            <div className="flex items-center gap-2 text-sm text-primary">
              <RotateCcw size={16} />
              <span className="font-medium">Сессия восстановлена</span>
              <span className="text-zinc-400 text-xs">Предыдущая работа возвращена.</span>
            </div>
            <button
              type="button"
              aria-label="Скрыть сообщение восстановления"
              onClick={() => setSessionRecovered(false)}
              className="rounded-lg p-2 text-zinc-500 transition-colors hover:bg-white/5 hover:text-white"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        )}

        {/* Main Workspace */}
        <div className="flex-1 overflow-hidden relative">

          {/* View: Settings */}
          {activeTab === 'settings' && (
            <div className="h-full overflow-y-auto p-6 pb-28 md:p-8 md:pb-8 max-w-2xl mx-auto animate-[fadeIn_0.3s_ease-out]">
              <div className="flex items-center justify-between mb-8">
                <h1 className="text-2xl font-bold">Настройки</h1>
                <div className="px-3 py-1 bg-green-500/10 border border-green-500/20 rounded-full text-[10px] text-green-400 font-medium flex items-center gap-2">
                  <Shield size={12} /> Ключи хранятся в аккаунте на backend
                </div>
              </div>
              <div className="glass-panel p-5 mb-8 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">Аккаунт и подписка</h2>
                    <p className="text-xs text-zinc-500 mt-1">
                      {authUser.email} · статус: {authUser.subscription_status}
                    </p>
                  </div>
                  <label className="flex items-center gap-2 text-sm text-zinc-300">
                    <input
                      type="checkbox"
                      checked={usePlatformKeys}
                      onChange={(e) => setUsePlatformKeys(e.target.checked)}
                      disabled={!canUsePlatformKeys}
                    />
                    Использовать ключи платформы
                  </label>
                </div>
                {!canUsePlatformKeys && (
                  <p className="text-xs text-amber-300">
                    Platform keys будут доступны после активации подписки. Сейчас можно использовать только свои сохранённые ключи.
                  </p>
                )}
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-zinc-200">Старые локальные данные</p>
                    <p className="text-xs text-zinc-500">Перенести legacy-видео, аватары и talking-head шаблоны в текущий аккаунт.</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleClaimLegacyAssets}
                    className="btn-secondary px-3 py-2 text-xs"
                  >
                    Забрать старые данные
                  </button>
                </div>
                {legacyClaimStatus && (
                  <p className="text-xs text-zinc-400">{legacyClaimStatus}</p>
                )}
                <div className="rounded-xl border border-sky-500/20 bg-sky-500/[0.06] p-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex min-w-0 gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-sky-500/10 text-sky-300">
                        <Archive size={18} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-zinc-100">Перенос на другой компьютер</p>
                        <p className="mt-1 text-xs leading-relaxed text-zinc-500">
                          ZIP включает аккаунты, сохранённые API-ключи, видео, аватары, шаблоны talking-head, uploads и секрет расшифровки.
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
                      <button
                        type="button"
                        onClick={handleExportBackup}
                        className="btn-primary inline-flex items-center justify-center gap-2 px-3 py-2 text-xs"
                      >
                        <Download size={14} />
                        Скачать backup
                      </button>
                      <label className={`btn-secondary inline-flex cursor-pointer items-center justify-center gap-2 px-3 py-2 text-xs ${backupImporting ? 'pointer-events-none opacity-60' : ''}`}>
                        <Upload size={14} />
                        {backupImporting ? 'Импортирую...' : 'Импортировать'}
                        <input
                          type="file"
                          accept=".zip,application/zip"
                          className="sr-only"
                          disabled={backupImporting}
                          onChange={(e) => {
                            handleImportBackup(e.target.files?.[0]);
                            e.target.value = '';
                          }}
                        />
                      </label>
                    </div>
                  </div>
                  <p className="mt-3 text-[11px] leading-relaxed text-sky-100/70">
                    Архив содержит чувствительные данные. Храни его как пароль: не отправляй в публичные чаты и не загружай в чужие облака.
                  </p>
                  {backupStatus && (
                    <p className="mt-3 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-zinc-300">{backupStatus}</p>
                  )}
                </div>
              </div>
              <KeyInput
                onKeySet={setApiKey}
                savedKey={apiKey}
                onAccountSave={(key) => handleSaveApiKey('gemini', key)}
                hasAccountKey={hasSavedKey('gemini')}
              />

              <div className="glass-panel p-6 mt-8">
                <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h2 className="text-lg font-semibold">Интеграции и API-ключи</h2>
                    <p className="mt-1 text-xs leading-relaxed text-zinc-500">
                      Секреты хранятся в backend vault текущего аккаунта. Мы показываем только статус, сам ключ обратно не раскрываем.
                    </p>
                  </div>
                  <span className="w-fit rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] uppercase tracking-wider text-zinc-400">
                    Хранилище аккаунта
                  </span>
                </div>

                <div className="space-y-4">
                  <ProviderKeyInput
                    title="Upload-Post"
                    description="Публикация готовых роликов в TikTok, Instagram Reels и YouTube Shorts."
                    value={uploadPostKey}
                    onChange={setUploadPostKey}
                    placeholder="ey..."
                    hasAccountKey={hasSavedKey('upload_post')}
                    actionLabel="Подключить"
                    onSave={async (key) => {
                      localStorage.setItem('uploadPostKey_v3', encrypt(key));
                      await handleSaveApiKey('upload_post', key);
                      await fetchUserProfiles();
                    }}
                    help="Нужен только для публикации из приложения. Генерация роликов работает без него."
                    links={[
                      { label: 'Войти в Upload-Post', caption: 'Создать аккаунт', href: 'https://app.upload-post.com/login' },
                      { label: 'Профили', caption: 'Подключить соцсети', href: 'https://app.upload-post.com/manage-users' },
                      { label: 'API Key', caption: 'Создать ключ', href: 'https://app.upload-post.com/api-keys' },
                    ]}
                  />

                  <ProviderKeyInput
                    title="ElevenLabs"
                    description="Озвучка и русские голоса для AI Shorts. Библиотечные голоса могут требовать платный план ElevenLabs."
                    value={elevenLabsKey}
                    onChange={setElevenLabsKey}
                    placeholder="sk_..."
                    hasAccountKey={hasSavedKey('elevenlabs')}
                    onSave={async (key) => {
                      localStorage.setItem('elevenLabsKey_v1', encrypt(key));
                      await handleSaveApiKey('elevenlabs', key);
                    }}
                    links={[
                      { label: 'ElevenLabs', caption: 'Открыть кабинет', href: 'https://elevenlabs.io/app' },
                      { label: 'API Keys', caption: 'Создать ключ', href: 'https://elevenlabs.io/app/settings/api-keys' },
                    ]}
                  />

                  <ProviderKeyInput
                    title="fal.ai"
                    description="Генерация аватаров, talking-head видео, b-roll и повторный lip-sync."
                    value={falKey}
                    onChange={setFalKey}
                    placeholder="fal_..."
                    hasAccountKey={hasSavedKey('fal')}
                    onSave={async (key) => {
                      localStorage.setItem('falKey_v1', encrypt(key));
                      await handleSaveApiKey('fal', key);
                    }}
                    links={[
                      { label: 'fal.ai Dashboard', caption: 'Создать аккаунт', href: 'https://fal.ai/dashboard' },
                      { label: 'API Keys', caption: 'Создать ключ', href: 'https://fal.ai/dashboard/keys' },
                    ]}
                  />
                </div>
              </div>
            </div>
          )}

          {/* View: SaaS Shorts */}
          {activeTab === 'saasshorts' && (
            <SaaShortsTab
              geminiApiKey={effectiveGeminiKey}
              elevenLabsKey={effectiveElevenLabsKey}
              falKey={effectiveFalKey}
              uploadPostKey={effectiveUploadPostKey}
              uploadUserId={uploadUserId}
              authToken={authToken}
              usePlatformKeys={usingPlatformKeys}
              onManageProjects={() => setActiveTab('projects')}
            />
          )}

          {/* View: Projects */}
          {activeTab === 'projects' && (
            <ProjectsTab
              authToken={authToken}
              onUseInShorts={() => setActiveTab('saasshorts')}
              onOpenContentPlan={() => setActiveTab('content-plan')}
            />
          )}

          {/* View: Content plan */}
          {activeTab === 'content-plan' && (
            <ContentPlanTab
              geminiApiKey={effectiveGeminiKey}
              authToken={authToken}
              usePlatformKeys={usingPlatformKeys}
              onCreateVideo={() => setActiveTab('saasshorts')}
              onOpenProjects={() => setActiveTab('projects')}
            />
          )}

          {/* View: AI Agent */}
          {activeTab === 'ai-agent' && (
            <div className="h-full overflow-y-auto custom-scrollbar p-6 pb-28 md:p-10 md:pb-10 animate-[fadeIn_0.3s_ease-out]">
              <div className="max-w-4xl mx-auto space-y-8">

                {/* Header */}
                <div className="space-y-3">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/30 text-[11px] uppercase tracking-wider text-primary font-semibold">
                    <Bot size={12} /> Автономный скилл
                  </div>
                  <h1 className="text-3xl md:text-4xl font-black bg-gradient-to-b from-white to-white/60 bg-clip-text text-transparent">
                    Персональная команда клипмейкеров
                  </h1>
                  <p className="text-zinc-400 text-base md:text-lg leading-relaxed max-w-2xl">
                    Кладёшь видео в папку — команда ИИ-клипмейкеров находит вирусные моменты, нарезает их и ставит в очередь на твоё одобрение. Как редакция коротких видео, работающая 24/7 на автопилоте.
                  </p>
                </div>

                {/* Mobile-format warning */}
                <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 flex items-start gap-3">
                  <Smartphone size={20} className="text-amber-400 shrink-0 mt-0.5" />
                  <div className="text-sm text-amber-100">
                    <p className="font-semibold text-amber-300 mb-1">Загружай видео уже в вертикальном формате (9:16).</p>
                    <p className="text-amber-100/80 leading-relaxed">
                      Агент не перекадрирует горизонтальное видео. Убедись, что каждый исходник снят или заранее обрезан под мобильный/портретный формат, прежде чем класть его в папку.
                    </p>
                  </div>
                </div>

                {/* Workflow */}
                <div className="grid md:grid-cols-3 gap-4">
                  <div className="glass-panel p-5 space-y-2">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                      <Upload size={18} />
                    </div>
                    <h3 className="font-semibold text-white">1. Кладёшь видео</h3>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                      Положи длинное вертикальное видео в отслеживаемую папку. За один прогон скилл берёт одно видео.
                    </p>
                  </div>

                  <div className="glass-panel p-5 space-y-2">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                      <Users size={18} />
                    </div>
                    <h3 className="font-semibold text-white">2. ИИ-клипмейкеры работают</h3>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                      Whisper расшифровывает речь, Gemini 3 Flash находит вирусные моменты, FFmpeg режет клипы и добавляет хук-плашку.
                    </p>
                  </div>

                  <div className="glass-panel p-5 space-y-2">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                      <CheckCircle2 size={18} />
                    </div>
                    <h3 className="font-semibold text-white">3. Ты проверяешь — он публикует</h3>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                      Одобряешь понравившиеся клипы, и скилл сам публикует их в TikTok, Reels и YouTube Shorts через Upload-Post.
                    </p>
                  </div>
                </div>

                {/* Repo CTA */}
                <div className="glass-panel p-6 md:p-8 space-y-5">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                      <h2 className="text-xl font-bold text-white mb-1">skill-autoshorts</h2>
                      <p className="text-sm text-zinc-400">
                        Скилл Claude Code, на котором работает этот процесс. Установи один раз и запускай, когда нужна свежая порция клипов.
                      </p>
                    </div>
                    <a
                      href="https://github.com/mutonby/skill-autoshorts"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-primary py-2 px-4 text-sm flex items-center gap-2 shrink-0"
                    >
                      Открыть на GitHub <ExternalLink size={14} />
                    </a>
                  </div>

                  <div className="bg-[#0c0c0e] border border-white/10 rounded-lg p-4 font-mono text-xs text-zinc-300 flex items-center justify-between gap-3">
                    <span className="truncate">git clone https://github.com/mutonby/skill-autoshorts</span>
                    <button
                      type="button"
                      aria-label="Скопировать команду установки"
                      onClick={() => navigator.clipboard.writeText('git clone https://github.com/mutonby/skill-autoshorts')}
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-white/5 hover:text-white"
                      title="Скопировать"
                    >
                      <Copy size={14} />
                    </button>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-3 text-sm">
                    <div className="flex items-start gap-2 text-zinc-300">
                      <Check size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                      <span>Ежедневная партия — одно длинное видео за прогон</span>
                    </div>
                    <div className="flex items-start gap-2 text-zinc-300">
                      <Check size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                      <span>Расшифровка Whisper с точностью до слова</span>
                    </div>
                    <div className="flex items-start gap-2 text-zinc-300">
                      <Check size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                      <span>Поиск моментов мультимодальным Gemini 3 Flash</span>
                    </div>
                    <div className="flex items-start gap-2 text-zinc-300">
                      <Check size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                      <span>Автопубликация в TikTok, Reels и YouTube Shorts</span>
                    </div>
                  </div>
                </div>

              </div>
            </div>
          )}

          {/* View: UGC Gallery */}
          {activeTab === 'ugc-gallery' && (
            <div className="h-full overflow-y-auto custom-scrollbar p-6 pb-28 md:p-8 md:pb-8">
              <UGCGallery
                falKey={effectiveFalKey}
                authToken={authToken}
                usePlatformKeys={usingPlatformKeys}
                onEditStoryboard={() => setActiveTab('saasshorts')}
              />
            </div>
          )}

          {/* View: Thumbnails */}
          {activeTab === 'thumbnails' && (
            <ThumbnailStudio geminiApiKey={effectiveGeminiKey} uploadPostKey={effectiveUploadPostKey} uploadUserId={uploadUserId} />
          )}

          {/* View: Gallery */}
          {/* {activeTab === 'gallery' && (
            <Gallery />
          )} */}

          {/* View: Dashboard (Idle) */}
          {activeTab === 'dashboard' && status === 'idle' && (
            <div className="h-full flex flex-col items-center justify-center p-6 animate-[fadeIn_0.3s_ease-out]">
              <div className="max-w-xl w-full text-center space-y-8">
                <div className="space-y-4">
                  <h1 className="text-4xl md:text-5xl font-black bg-gradient-to-b from-white to-white/60 bg-clip-text text-transparent">
                    Вирусные клипы из длинного видео
                  </h1>
                  <p className="text-zinc-400 text-lg">
                    Загрузи длинное вертикальное видео — ИИ сам найдёт лучшие моменты и нарежет из них клипы.
                  </p>
                </div>

                <MediaInput onProcess={handleProcess} isProcessing={status === 'processing'} />

                <div className="flex items-center justify-center gap-8 text-zinc-500 text-sm">
                  <span className="flex items-center gap-2"><Youtube size={16} /> YouTube</span>
                  <span className="flex items-center gap-2"><Instagram size={16} /> Instagram</span>
                  <span className="flex items-center gap-2"><TikTokIcon size={16} /> TikTok</span>
                </div>
              </div>
            </div>
          )}

          {/* View: Processing / Results (Split View) */}
          {activeTab === 'dashboard' && (status === 'processing' || status === 'complete' || status === 'error') && (
            <div className="h-full flex flex-col md:flex-row animate-[fadeIn_0.3s_ease-out]">

              {/* Left Panel: Preview & Status */}
              <div className={`${status === 'complete' ? 'w-full md:w-[30%] lg:w-[25%]' : 'w-full md:w-[55%] lg:w-[60%]'} h-full flex flex-col border-r border-white/5 bg-black/20 p-6 pb-28 md:pb-6 overflow-y-auto custom-scrollbar transition-all duration-700 ease-in-out`}>
                <div className="mb-6 flex items-center justify-between">
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <Activity className={`text-primary ${status === 'processing' ? 'animate-pulse' : ''}`} size={20} />
                    Анализ в реальном времени
                  </h2>
                  <span className={`text-xs px-2 py-1 rounded-full border ${status === 'processing' ? 'bg-primary/10 border-primary/20 text-primary' :
                    status === 'complete' ? 'bg-green-500/10 border-green-500/20 text-green-400' :
                      'bg-red-500/10 border-red-500/20 text-red-400'
                    }`}>
                    {status === 'processing' ? 'Обработка' : status === 'complete' ? 'Готово' : 'Ошибка'}
                  </span>
                </div>

                {/* Video Preview */}
                {processingMedia && (
                  <ProcessingAnimation
                    media={processingMedia}
                    isComplete={status === 'complete'}
                    syncedTime={syncedTime}
                    isSyncedPlaying={isSyncedPlaying}
                    syncTrigger={syncTrigger}
                  />
                )}

                {/* Logs Terminal */}
                <div className={`bg-[#0c0c0e] rounded-xl border border-white/10 overflow-hidden flex flex-col transition-all duration-500 ${status === 'complete' ? 'h-32 min-h-0 opacity-50 hover:opacity-100' : 'flex-1 min-h-[200px]'}`}>
                  <div className="px-4 py-2 border-b border-white/5 flex items-center justify-between bg-white/5 shrink-0">
                    <span className="text-xs font-mono text-zinc-400 flex items-center gap-2">
                      <Terminal size={12} /> Логи процесса
                    </span>
                    <button onClick={() => setLogsVisible(!logsVisible)} className="text-zinc-500 hover:text-white transition-colors">
                      {logsVisible ? <ChevronDown size={14} /> : <ChevronDown size={14} className="rotate-180" />}
                    </button>
                  </div>
                  {logsVisible && (
                    <div className="flex-1 p-4 overflow-y-auto font-mono text-xs space-y-1.5 custom-scrollbar text-zinc-400">
                      {logs.map((log, i) => (
                        <div key={i} className={`flex gap-2 ${log.toLowerCase().includes('error') ? 'text-red-400' : 'text-zinc-400'}`}>
                          <span className="text-zinc-700 shrink-0">{new Date().toLocaleTimeString()}</span>
                          <span>{log}</span>
                        </div>
                      ))}
                      {status === 'processing' && (
                        <div className="animate-pulse text-primary/70">_</div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Right Panel: Results Grid */}
              <div className={`${status === 'complete' ? 'w-full md:w-[70%] lg:w-[75%]' : 'w-full md:w-[45%] lg:w-[40%]'} h-full flex flex-col bg-background p-6 pb-28 md:pb-6 transition-all duration-700 ease-in-out`}>
                <h2 className="text-lg font-semibold mb-6 flex items-center gap-2 shrink-0">
                  <Sparkles className="text-yellow-400" size={20} />
                  Готовые клипы
                  {results?.clips?.length > 0 && (
                    <span className="text-xs bg-white/10 text-white px-2 py-0.5 rounded-full ml-auto">
                      {results.clips.length} {clipsPlural(results.clips.length)}
                    </span>
                  )}
                  {results?.cost_analysis && (
                    <span className="text-xs bg-green-500/10 border border-green-500/20 text-green-400 px-2 py-0.5 rounded-full ml-2" title={`Input: ${results.cost_analysis.input_tokens} | Output: ${results.cost_analysis.output_tokens}`}>
                      ${results.cost_analysis.total_cost.toFixed(5)}
                    </span>
                  )}
                  {results?.clips?.length > 1 && status === 'complete' && (
                    <button
                      onClick={() => setShowScheduleWeek(true)}
                      className="ml-auto flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-purple-500/20 to-indigo-500/20 hover:from-purple-500/30 hover:to-indigo-500/30 border border-purple-500/30 text-purple-300 hover:text-purple-200 rounded-full text-xs font-bold transition-all"
                    >
                      <Calendar size={14} />
                      Запланировать неделю
                    </button>
                  )}
                </h2>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-1">
                  {results && results.clips && results.clips.length > 0 ? (
                    <div className={`grid gap-4 pb-10 ${status === 'complete' ? 'grid-cols-1 xl:grid-cols-2' : 'grid-cols-1'}`}>
                      {results.clips.map((clip, i) => (
                        <ResultCard
                          key={i}
                          clip={clip}
                          index={i}
                          jobId={jobId}
                          uploadPostKey={effectiveUploadPostKey}
                          uploadUserId={uploadUserId}
                          geminiApiKey={effectiveGeminiKey}
                          elevenLabsKey={effectiveElevenLabsKey}
                          authToken={authToken}
                          usePlatformKeys={usingPlatformKeys}
                          onPlay={(time) => handleClipPlay(time)}
                          onPause={handleClipPause}
                        />
                      ))}
                    </div>
                  ) : (
                    status === 'processing' ? (
                      <div className="h-full flex flex-col items-center justify-center text-zinc-500 space-y-4 opacity-50">
                        <div className="w-12 h-12 rounded-full border-2 border-zinc-800 border-t-primary animate-spin" />
                        <p className="text-sm">Ждём клипы...</p>
                      </div>
                    ) : status === 'error' ? (
                      <div className="h-full flex flex-col items-center justify-center text-red-400 space-y-2">
                        <p>Не удалось сгенерировать.</p>
                      </div>
                    ) : null
                  )}
                </div>
              </div>

            </div>
          )}

        </div>

      </main>
      <MobileTabBar />

      {/* Missing API Key Modal */}
      {showKeyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowKeyModal(false)}>
          <div className="bg-[#18181b] border border-white/10 rounded-2xl p-6 max-w-md w-full mx-4 space-y-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-white">Нужен API-ключ Gemini</h2>
            <p className="text-sm text-zinc-400">
              Контентфабрике нужен API-ключ <strong className="text-zinc-200">Gemini</strong> для анализа и генерации сценариев. Upload-Post опционален и нужен только для публикации.
            </p>

            {/* Gemini block */}
            <div className={`rounded-lg p-4 space-y-2 border ${!effectiveGeminiKey ? 'bg-primary/5 border-primary/30' : 'bg-white/5 border-white/10 opacity-70'}`}>
              <p className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
                {effectiveGeminiKey ? <Check size={12} className="text-green-400" /> : <AlertTriangle size={12} className="text-amber-400" />}
                Ключ Gemini {effectiveGeminiKey && <span className="text-green-400">— задан</span>}
              </p>
              {!effectiveGeminiKey && (
                <>
                  <ol className="text-xs text-zinc-400 space-y-1 list-decimal list-inside">
                    <li>Открой <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer" className="text-primary underline">aistudio.google.com/app/apikey</a></li>
                    <li>Войди под своим аккаунтом Google</li>
                    <li>Нажми «Create API Key»</li>
                    <li>Скопируй ключ и вставь ниже</li>
                  </ol>
                  <input
                    type="text"
                    placeholder="Вставь сюда API-ключ Gemini..."
                    className="w-full bg-black/50 border border-white/20 rounded-lg px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-primary"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && e.target.value.trim()) {
                        setApiKey(e.target.value.trim());
                      }
                    }}
                  />
                </>
              )}
            </div>

            {/* Upload-Post block */}
            <div className={`rounded-lg p-4 space-y-2 border ${!effectiveUploadPostKey ? 'bg-white/5 border-white/10' : 'bg-white/5 border-white/10 opacity-70'}`}>
              <p className="text-xs font-semibold text-zinc-200 flex items-center gap-2">
                {effectiveUploadPostKey ? <Check size={12} className="text-green-400" /> : <AlertTriangle size={12} className="text-zinc-500" />}
                Ключ Upload-Post {effectiveUploadPostKey && <span className="text-green-400">— задан</span>}
              </p>
              {!effectiveUploadPostKey && (
                <>
                  <p className="text-xs text-zinc-400">
                    Опционально. Добавь, только если хочешь публиковать прямо в TikTok, Instagram Reels и YouTube Shorts.
                  </p>
                  <ol className="text-xs text-zinc-400 space-y-1 list-decimal list-inside">
                    <li>Зарегистрируйся на <a href="https://app.upload-post.com/login" target="_blank" rel="noopener noreferrer" className="text-primary underline">app.upload-post.com</a></li>
                    <li>Подключи аккаунты TikTok, Instagram или YouTube</li>
                    <li>Открой <a href="https://app.upload-post.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-primary underline">API Keys</a> и создай ключ</li>
                    <li>Вставь его ниже</li>
                  </ol>
                  <input
                    type="text"
                    placeholder="Вставь сюда API-ключ Upload-Post..."
                    className="w-full bg-black/50 border border-white/20 rounded-lg px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-primary"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && e.target.value.trim()) {
                        setUploadPostKey(e.target.value.trim());
                      }
                    }}
                  />
                </>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowKeyModal(false)}
                className="flex-1 text-sm text-zinc-400 py-2 rounded-lg border border-white/10 hover:bg-white/5 transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={() => { setShowKeyModal(false); setActiveTab('settings'); }}
                className="flex-1 text-sm text-white py-2 rounded-lg bg-primary hover:bg-violet-600 transition-colors font-medium"
              >
                Открыть настройки
              </button>
            </div>
          </div>
        </div>
      )}

      <ScheduleWeekModal
        isOpen={showScheduleWeek}
        onClose={() => setShowScheduleWeek(false)}
        clips={results?.clips || []}
        jobId={jobId}
        uploadPostKey={uploadPostKey}
        uploadUserId={uploadUserId}
      />
    </div>
  );
}

export default App;

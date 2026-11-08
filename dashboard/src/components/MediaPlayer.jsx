import React, { forwardRef, useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, Headphones, Loader2, Maximize2, Minimize2, Pause, Play, Volume2, VolumeX } from 'lucide-react';
import './MediaPlayer.css';

export function formatMediaTime(value) {
  const seconds = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds / 60) % 60;
  const remainder = String(seconds % 60).padStart(2, '0');
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${remainder}` : `${minutes}:${remainder}`;
}

export function clampMediaTime(time, duration) {
  return Number.isFinite(duration) && duration > 0
    ? Math.min(duration, Math.max(0, Number(time) || 0)) : 0;
}

export function mediaKeyboardAction(key, tagName, currentTime, duration) {
  if (['BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'A'].includes(tagName)) return null;
  if (key === ' ' || key.toLowerCase() === 'k') return { type: 'toggle' };
  if (key === 'ArrowRight') return { type: 'seek', time: clampMediaTime(currentTime + 5, duration) };
  if (key === 'ArrowLeft') return { type: 'seek', time: clampMediaTime(currentTime - 5, duration) };
  if (key.toLowerCase() === 'm') return { type: 'mute' };
  return null;
}

// One branded player for voice takes, music previews and finished videos.
// The forwarded ref deliberately remains the media element for existing editors.
const MediaPlayer = forwardRef(function MediaPlayer({
  kind = 'video', src, poster, label = kind === 'audio' ? 'Озвучка' : 'Видео',
  className = '', mediaClassName = '', compact = false, disabled = false,
  preload = 'metadata', muted: initialMuted = false, defaultVolume = 1,
  onPlay, onPause, onEnded, onLoadedMetadata, onDurationChange, onTimeUpdate,
  onVolumeChange, onWaiting, onCanPlay, onPlaying, onError, onKeyDown, controls: _nativeControls,
  ...mediaProps
}, forwardedRef) {
  const mediaRef = useRef(null);
  const rootRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [volume, setVolume] = useState(Math.min(1, Math.max(0, defaultVolume)));
  const [muted, setMuted] = useState(initialMuted);
  const [buffering, setBuffering] = useState(false);
  const [error, setError] = useState('');
  const [volumeOpen, setVolumeOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const volumeButtonRef = useRef(null);
  const audio = kind === 'audio';
  const unavailable = disabled || !src;
  const silent = muted || volume === 0;

  const setMediaRef = useCallback((element) => {
    mediaRef.current = element;
    if (typeof forwardedRef === 'function') forwardedRef(element);
    else if (forwardedRef) forwardedRef.current = element;
  }, [forwardedRef]);

  useEffect(() => {
    setPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    setError('');
    setBuffering(false);
  }, [src]);

  useEffect(() => {
    const media = mediaRef.current;
    if (!media) return;
    media.muted = initialMuted;
    media.volume = Math.min(1, Math.max(0, defaultVolume));
    setMuted(media.muted);
    setVolume(media.volume);
  }, [initialMuted, defaultVolume]);

  useEffect(() => {
    if (disabled) mediaRef.current?.pause();
  }, [disabled]);

  useEffect(() => {
    const update = () => setFullscreen(document.fullscreenElement === rootRef.current);
    document.addEventListener('fullscreenchange', update);
    return () => document.removeEventListener('fullscreenchange', update);
  }, []);

  async function togglePlayback() {
    const media = mediaRef.current;
    if (!media || unavailable) return;
    if (!media.paused) { media.pause(); return; }
    setError('');
    try {
      if (media.ended) media.currentTime = 0;
      await media.play();
    } catch (failure) {
      // Aborted loads are expected when switching between saved takes.
      if (failure.name !== 'AbortError') setError('Не удалось воспроизвести. Попробуйте ещё раз.');
      setBuffering(false);
    }
  }

  function seek(time) {
    if (unavailable || !mediaRef.current || !duration) return;
    const target = clampMediaTime(time, duration);
    mediaRef.current.currentTime = target;
    setCurrentTime(target);
  }

  function toggleMute() {
    const media = mediaRef.current;
    if (!media || unavailable) return;
    if (media.muted || media.volume === 0) {
      media.muted = false;
      if (!media.volume) media.volume = 1;
    } else media.muted = true;
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement === rootRef.current) await document.exitFullscreen();
      else if (rootRef.current?.requestFullscreen) await rootRef.current.requestFullscreen();
      else if (mediaRef.current?.webkitEnterFullscreen) mediaRef.current.webkitEnterFullscreen();
    } catch { setError('Полноэкранный режим недоступен в этом браузере.'); }
  }

  function handleKeyboard(event) {
    onKeyDown?.(event);
    if (event.defaultPrevented || event.target.isContentEditable || unavailable) return;
    if (event.key === 'Escape' && volumeOpen) {
      setVolumeOpen(false);
      volumeButtonRef.current?.focus();
      return;
    }
    const action = mediaKeyboardAction(event.key, event.target.tagName, currentTime, duration);
    if (!action) return;
    event.preventDefault();
    if (action.type === 'toggle') togglePlayback();
    if (action.type === 'seek') seek(action.time);
    if (action.type === 'mute') toggleMute();
  }

  const Media = audio ? 'audio' : 'video';
  const percent = duration > 0 ? Math.min(100, currentTime / duration * 100) : 0;
  const playLabel = playing ? (audio ? 'Приостановить озвучку' : 'Приостановить видео')
    : (audio ? 'Воспроизвести озвучку' : 'Воспроизвести видео');

  const playButton = <button type="button" className="cf-media-player__button cf-media-player__play"
    disabled={unavailable} aria-label={playLabel} title={playing ? 'Пауза · пробел' : 'Воспроизвести · пробел'}
    onClick={togglePlayback}>
    {buffering ? <Loader2 size={19} className="cf-media-player__spinner" />
      : playing ? <Pause size={19} fill="currentColor" strokeWidth={1.6} />
        : <Play size={19} fill="currentColor" strokeWidth={1.6} />}
  </button>;

  const timeline = <input className="cf-media-player__seek" type="range" min="0" max={duration || 0} step="0.01"
    value={Math.min(currentTime, duration || 0)} disabled={unavailable || !duration}
    aria-label="Позиция воспроизведения" aria-valuetext={`${formatMediaTime(currentTime)} из ${formatMediaTime(duration)}`}
    style={{ '--media-progress': `${percent}%` }} onChange={(event) => seek(event.target.value)} />;

  const soundControls = <div className="cf-media-player__sound"
    onMouseEnter={() => { if (!unavailable) setVolumeOpen(true); }}
    onMouseLeave={(event) => { if (!event.currentTarget.contains(document.activeElement)) setVolumeOpen(false); }}
    onFocus={() => { if (!unavailable) setVolumeOpen(true); }}
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setVolumeOpen(false); }}>
    <button ref={volumeButtonRef} type="button" className="cf-media-player__button" disabled={unavailable}
      aria-label={silent ? 'Включить звук' : 'Выключить звук'} title={silent ? 'Включить звук · M' : 'Выключить звук · M'}
      aria-pressed={silent} onClick={toggleMute}>
      {silent ? <VolumeX size={18} /> : <Volume2 size={18} />}
    </button>
    {volumeOpen && <div className="cf-media-player__volume-popover">
      <label>Громкость <output>{silent ? 0 : Math.round(volume * 100)}%</output>
        <input type="range" min="0" max="1" step="0.05" value={silent ? 0 : volume} aria-label="Громкость воспроизведения"
          style={{ '--media-progress': `${(silent ? 0 : volume) * 100}%` }}
          onChange={(event) => {
            const media = mediaRef.current;
            if (media) { media.volume = Number(event.target.value); media.muted = false; }
          }} />
      </label>
    </div>}
  </div>;

  return <div ref={rootRef} className={`cf-media-player cf-media-player--${kind} ${compact ? 'cf-media-player--compact' : ''} ${className}`}
    data-media-player={kind} data-playing={playing} aria-disabled={unavailable} tabIndex={unavailable ? -1 : 0}
    role="group" aria-label={label} onKeyDown={handleKeyboard}>
    <Media {...mediaProps} ref={setMediaRef} src={src} poster={audio ? undefined : poster}
      preload={preload} muted={initialMuted} playsInline controls={false}
      className={`cf-media-player__media ${mediaClassName}`} aria-label={label}
      onPlay={(event) => { setPlaying(true); setBuffering(false); onPlay?.(event); }}
      onPause={(event) => { setPlaying(false); setBuffering(false); onPause?.(event); }}
      onEnded={(event) => { setPlaying(false); setBuffering(false); onEnded?.(event); }}
      onLoadedMetadata={(event) => { setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0); onLoadedMetadata?.(event); }}
      onDurationChange={(event) => { setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0); onDurationChange?.(event); }}
      onTimeUpdate={(event) => { setCurrentTime(event.currentTarget.currentTime); onTimeUpdate?.(event); }}
      onVolumeChange={(event) => { setVolume(event.currentTarget.volume); setMuted(event.currentTarget.muted); onVolumeChange?.(event); }}
      onWaiting={(event) => { setBuffering(true); onWaiting?.(event); }}
      onCanPlay={(event) => { setBuffering(false); onCanPlay?.(event); }}
      onPlaying={(event) => { setBuffering(false); onPlaying?.(event); }}
      onError={(event) => { setError('Не удалось загрузить файл. Проверьте подключение или откройте его заново.'); setBuffering(false); onError?.(event); }} />
    {audio ? <div className="cf-media-player__audio-controls">
      {playButton}
      <div className="cf-media-player__audio-track">
        <span className="cf-media-player__title"><Headphones size={12} aria-hidden="true" />{label}</span>
        {timeline}
        <div className="cf-media-player__time"><span>{formatMediaTime(currentTime)}</span><span>{formatMediaTime(duration)}</span></div>
      </div>
      {soundControls}
    </div> : <>
      {!playing && !error && <button type="button" className="cf-media-player__center-play" disabled={unavailable}
        aria-label="Начать просмотр" onClick={togglePlayback}><Play size={27} fill="currentColor" strokeWidth={1.5} /></button>}
      <div className="cf-media-player__video-controls">
        {timeline}
        <div className="cf-media-player__control-row">
          {playButton}
          <span className="cf-media-player__time">{formatMediaTime(currentTime)}<span className="cf-media-player__duration"> / {formatMediaTime(duration)}</span></span>
          {soundControls}
          <button type="button" className="cf-media-player__button" disabled={unavailable}
            aria-label={fullscreen ? 'Выйти из полного экрана' : 'На весь экран'} onClick={toggleFullscreen}>
            {fullscreen ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
          </button>
        </div>
      </div>
    </>}
    {error && <div className="cf-media-player__error" role="alert"><AlertCircle size={14} />{error}</div>}
  </div>;
});

export default MediaPlayer;

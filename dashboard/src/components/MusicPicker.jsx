import React, { useEffect, useId, useState } from 'react';
import { Music2 } from 'lucide-react';
import { getApiUrl } from '../config';

export function musicRequestSettings(enabled, track = 'auto', volume = 1) {
  return { background_music: enabled, music_track: track, music_volume: volume };
}

export function musicPreferencesFromVideo(video = {}) {
  return { backgroundMusic: video.background_music !== false,
    musicTrack: video.music_track || 'auto', musicVolume: video.music_volume ?? 1 };
}

export default function MusicPicker({ enabled, value, volume, onEnabledChange, onChange, onVolumeChange, disabled = false }) {
  const id = useId();
  const [tracks, setTracks] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    fetch(getApiUrl('/api/saasshorts/music-tracks'), { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('Не удалось загрузить музыку');
        return response.json();
      })
      .then((data) => setTracks(data.tracks || []))
      .catch((failure) => { if (failure.name !== 'AbortError') setError(failure.message); });
    return () => controller.abort();
  }, []);
  const selected = tracks.find((track) => track.id === value);
  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-3" data-section="music-picker">
      <label className="flex items-center gap-2 text-sm font-medium text-zinc-300">
        <Music2 size={15} />
        <input type="checkbox" checked={enabled} onChange={(event) => onEnabledChange(event.target.checked)}
          className="accent-violet-500" />
        Музыка
      </label>
      {enabled && <>
        <label htmlFor={`${id}-track`} className="sr-only">Музыкальный трек</label>
        <select id={`${id}-track`} aria-label="Музыкальный трек" value={value} onChange={(event) => onChange(event.target.value)}
          className="min-h-10 w-full max-w-full rounded-md border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 disabled:opacity-50">
          <option value="auto">Автоматический выбор</option>
          {value !== 'auto' && !selected && <option value={value}>{value}</option>}
          {tracks.map((track) => <option key={track.id} value={track.id}>{track.name}</option>)}
        </select>
        <div className="flex items-center gap-3">
          <label htmlFor={`${id}-volume`} className="shrink-0 text-xs text-zinc-400">Громкость</label>
          <input id={`${id}-volume`} aria-label="Громкость музыки" type="range" min="0" max="2" step="0.05"
            value={volume} onChange={(event) => onVolumeChange(Number(event.target.value))}
            className="min-w-0 flex-1 accent-violet-500" />
          <output className="w-10 shrink-0 text-right text-xs tabular-nums text-zinc-400">{Math.round(volume * 100)}%</output>
        </div>
        {selected && <audio key={selected.id} aria-label={`Прослушать ${selected.name}`} controls preload="none"
          src={getApiUrl(selected.preview_url)} className="h-9 w-full max-w-full" />}
      </>}
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
    </fieldset>
  );
}

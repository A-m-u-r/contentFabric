import React from 'react';
import { Image, Pause, Play, SkipBack, SkipForward } from 'lucide-react';

export function storyboardTiming(frames, sourceVideo, voice) {
  const starts = frames.map(({ shot }) => shot.timeline_start);
  const ends = frames.map(({ shot }) => shot.timeline_end);
  const exactVideo = sourceVideo && frames.length && starts[0] === 0
    && starts.every((start, index) => Number.isFinite(start) && Number.isFinite(ends[index])
      && ends[index] > start && (!index || Math.abs(start - ends[index - 1]) < 0.002));
  if (exactVideo) {
    return { starts, duration: ends.at(-1), kind: 'video', src: sourceVideo };
  }

  const voiceStarts = frames.map(({ shot }) => shot.voice_start);
  const lastVoiceEnd = frames.at(-1)?.shot.voice_end;
  if (voice && frames.length && voice.seconds > voiceStarts.at(-1) && lastVoiceEnd > voiceStarts.at(-1)
      && lastVoiceEnd <= voice.seconds + 0.05 && voiceStarts.every((start, index) => (
        Number.isFinite(start) && start >= 0 && (!index || start > voiceStarts[index - 1])
      ))) {
    voiceStarts[0] = 0;
    return { starts: voiceStarts, duration: voice.seconds, kind: 'audio', src: voice.url };
  }

  let duration = 0;
  const plannedStarts = frames.map(({ shot, plannedSeconds }) => {
    const start = duration;
    const authored = Number(shot.end) - Number(shot.start);
    duration += Number.isFinite(authored) && authored > 0 ? authored : plannedSeconds > 0 ? plannedSeconds : 3;
    return start;
  });
  return { starts: plannedStarts, duration, kind: 'draft', src: '' };
}

export function shotAtTime(starts, time) {
  const next = starts.findIndex((start) => start > time);
  return Math.max(0, (next === -1 ? starts.length : next) - 1);
}

export function timelineClock(time) {
  const tenths = Math.floor(Math.max(0, time) * 10 + 0.0001);
  return `${String(Math.floor(tenths / 600)).padStart(2, '0')}:${String(Math.floor(tenths / 10) % 60).padStart(2, '0')}.${tenths % 10}`;
}

export default function StoryboardTimeline({
  shots, timing, waveform, position, selectedIndex, playing, onToggle, onSelect, onSeek,
}) {
  const { starts, duration, kind } = timing;
  const last = shots.length - 1;
  const tickSize = Math.max(1, Math.ceil(duration / 8));
  const ticks = duration
    ? [...Array.from({ length: Math.max(1, Math.ceil(duration / tickSize - 0.5)) }, (_, index) => index * tickSize), duration]
    : [];
  const percent = (time) => (duration ? time / duration * 100 : 0) + '%';
  const widths = starts.map((start, index) => percent((starts[index + 1] ?? duration) - start));
  const scope = 'storyboard-editor__';
  const button = scope + 'button ' + scope + 'button--icon';

  return (
    <section className={scope + 'timeline'} data-storyboard-timeline aria-label="Таймлайн">
      <div className={scope + 'transport'}>
        <h2 className={scope + 'timeline-title'}>Таймлайн</h2>
        <div className={scope + 'play-controls'}>
          <button type="button" className={button} aria-label="Предыдущий кадр" disabled={selectedIndex <= 0}
            onClick={() => onSelect(selectedIndex - 1)}><SkipBack size={15} /></button>
          <button type="button" className={button + ' ' + scope + 'play'} aria-label={playing ? 'Пауза' : 'Воспроизвести'}
            disabled={last < 0} onClick={onToggle}>{playing ? <Pause size={16} /> : <Play size={16} />}</button>
          <button type="button" className={button} aria-label="Следующий кадр" disabled={selectedIndex >= last}
            onClick={() => onSelect(selectedIndex + 1)}><SkipForward size={15} /></button>
        </div>
        <div className={scope + 'clock'}><strong>{timelineClock(position)}</strong><span> / {timelineClock(duration)}</span></div>
        <span className={scope + 'timeline-meta'}>{kind === 'draft' ? 'Черновой тайминг' : kind === 'audio' ? 'По озвучке' : 'Готовый ролик'}</span>
      </div>
      <div className={scope + 'timeline-scroll'}>
        <div className={scope + 'track-grid'} style={{ '--timeline-min-width': Math.max(330, shots.length * 54) + 'px' }}>
          <div className={scope + 'track-labels'} aria-hidden="true"><span /><span>Кадры</span><span>Звук</span></div>
          <div className={scope + 'track-area'}>
            <div className={scope + 'ruler'}>
              <div className={scope + 'ruler-ticks'} aria-hidden="true">
                {ticks.map((time) => (
                  <span key={time} style={{ left: percent(time) }}>
                    {Number.isInteger(time) ? timelineClock(time).slice(0, -2) : timelineClock(time)}
                  </span>
                ))}
              </div>
              <input className={scope + 'seek'} type="range" min="0" max={duration} step="any" disabled={last < 0}
                aria-label="Позиция на таймлайне" aria-valuetext={timelineClock(position)} value={position}
                onChange={(event) => onSeek(event.target.valueAsNumber)} />
            </div>
            <div className={scope + 'clips'} style={{ gridTemplateColumns: widths.join(' ') }}>
              {shots.map((frame, index) => (
                <button type="button" key={index} className={scope + 'clip'} data-timeline-clip={index + 1}
                  aria-label={`Кадр ${index + 1}, ${timelineClock(starts[index])}`} aria-pressed={selectedIndex === index}
                  title={frame.shot.speech || frame.shot.scene || `Кадр ${index + 1}`}
                  onClick={() => onSelect(index)}>
                  <span className={scope + 'clip-thumb'}>{frame.imageUrl ? <img src={frame.imageUrl} alt="" /> : <Image size={14} />}</span>
                  <span className={scope + 'clip-label'}>{String(index + 1).padStart(2, '0')}</span>
                </button>
              ))}
            </div>
            <div className={scope + 'audio-track'} data-has-audio={kind !== 'draft'}>
              {kind === 'video' && waveform?.length ? (
                <svg className={scope + 'waveform'} viewBox={`0 0 ${waveform.length} 32`} preserveAspectRatio="none" aria-hidden="true">
                  {waveform.map((peak, index) => {
                    const height = Math.max(1, Math.min(30, Number(peak) * 30 || 0));
                    return <rect key={index} x={index} y={(32 - height) / 2} width="0.65" height={height} />;
                  })}
                </svg>
              ) : <span>{kind === 'draft' ? 'Нет дорожки' : kind === 'audio' ? 'Озвучка' : 'Звук ролика'}</span>}
            </div>
            {shots.length > 0 && <div className={scope + 'playhead'} aria-hidden="true" style={{ left: percent(position) }} />}
          </div>
        </div>
      </div>
    </section>
  );
}

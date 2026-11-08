import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ChevronDown, ChevronUp, Copy, Film, GripVertical, Image, Plus, Settings2, Trash2, Undo2, X } from 'lucide-react';
import MediaPlayer from './MediaPlayer';
import StoryboardTimeline, { shotAtTime, storyboardTiming } from './StoryboardTimeline';
import './StoryboardEditor.css';

const button = 'storyboard-editor__button';
const plain = `${button} ${button}--plain`;
const icon = `${button} ${button}--icon`;
const views = [['script', 'Кадры'], ['preview', 'Превью'], ['inspector', 'Параметры']];

export default function StoryboardEditor({
  title, projectName, shots, sourceVideo, voice, waveform, notice, settings, estimate, renderAction, renderShot, resultLabel,
  onBack, onResult, onAdd, onDuplicate, onRemove, onMove, onReorder, onUndo, onEnlarge,
  settingsBlocked,
}) {
  const id = useId();
  const settingsRef = useRef(null);
  const estimateRef = useRef(null);
  const mediaRef = useRef(null);
  const timeRef = useRef(0);
  const timingKeyRef = useRef('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mobileView, setMobileView] = useState('preview');
  const [leftView, setLeftView] = useState('script');
  const [playingClip, setPlayingClip] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [failedSource, setFailedSource] = useState('');
  const [dragIndex, setDragIndex] = useState(null);
  const [dropIndex, setDropIndex] = useState(null);
  const shotIndex = Math.max(0, Math.min(selectedIndex, shots.length - 1));
  const selected = shots[shotIndex];
  const timing = useMemo(() => storyboardTiming(
    shots, sourceVideo === failedSource ? '' : sourceVideo, voice?.url === failedSource ? null : voice,
  ), [shots, sourceVideo, voice, failedSource]);
  const timingKey = JSON.stringify([timing.src, timing.duration, timing.starts]);
  const shotDuration = (index) => {
    const duration = (timing.starts[index + 1] ?? timing.duration) - timing.starts[index];
    return duration.toLocaleString('ru', { maximumFractionDigits: 1 }) + ' с';
  };

  useEffect(() => {
    if (settingsBlocked) settingsRef.current?.close();
  }, [settingsBlocked]);

  const pauseTimeline = () => {
    mediaRef.current?.pause();
    setPlaying(false);
  };

  const seek = (seconds, index = shotAtTime(timing.starts, seconds)) => {
    const time = Math.max(0, Math.min(timing.duration, seconds));
    timeRef.current = time;
    setPosition(time);
    setSelectedIndex(index);
    setPlayingClip(false);
    if (mediaRef.current?.readyState) mediaRef.current.currentTime = time;
  };

  useEffect(() => {
    if (timingKeyRef.current === timingKey) return;
    if (timingKeyRef.current) {
      pauseTimeline();
      seek(timing.starts[shotIndex] ?? 0, shotIndex);
    }
    timingKeyRef.current = timingKey;
  }, [timingKey, timing, shotIndex]);

  useEffect(() => {
    if (!playing || timing.src) return;
    const initialTime = timeRef.current;
    const initialTick = performance.now();
    let animation;
    const advance = (now) => {
      const time = Math.min(timing.duration, initialTime + (now - initialTick) / 1000);
      timeRef.current = time;
      setPosition(time);
      setSelectedIndex(shotAtTime(timing.starts, time));
      if (time < timing.duration) animation = requestAnimationFrame(advance);
      else setPlaying(false);
    };
    animation = requestAnimationFrame(advance);
    return () => cancelAnimationFrame(animation);
  }, [playing, timing]);

  const selectShot = (index) => {
    pauseTimeline();
    seek(timing.starts[index] ?? timing.duration, index);
  };

  const openShot = (index) => {
    selectShot(index);
    setMobileView('preview');
    requestAnimationFrame(() => {
      const tab = document.getElementById(`${id}-view-preview`);
      if (tab?.offsetParent) tab.focus();
    });
  };

  const mediaFailed = () => {
    setFailedSource(timing.src);
    setPlaying(false);
  };

  const togglePlayback = () => {
    if (playing) {
      pauseTimeline();
      return;
    }
    setPlayingClip(false);
    setMobileView('preview');
    if (timeRef.current >= timing.duration) seek(0);
    const media = mediaRef.current;
    if (media) {
      media.play().catch((error) => {
        if (error.name !== 'AbortError') mediaFailed();
      });
    } else {
      setPlaying(true);
    }
  };

  const mediaEvents = {
    onLoadedMetadata: (event) => { event.currentTarget.currentTime = timeRef.current; },
    onTimeUpdate: (event) => {
      const time = Math.min(event.currentTarget.currentTime, timing.duration);
      timeRef.current = time;
      setPosition(time);
      setSelectedIndex(shotAtTime(timing.starts, time));
    },
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onEnded: () => setPlaying(false),
    onError: mediaFailed,
  };

  const clearDrag = () => {
    setDragIndex(null);
    setDropIndex(null);
  };

  const dropShot = (index) => {
    clearDrag();
    if (dragIndex === null || dragIndex === index) return;
    onReorder(dragIndex, index);
    if (shotIndex === dragIndex) selectShot(index);
    else if (dragIndex < shotIndex && shotIndex <= index) selectShot(shotIndex - 1);
    else if (index <= shotIndex && shotIndex < dragIndex) selectShot(shotIndex + 1);
  };

  const showClip = Boolean(selected?.clipUrl && playingClip);
  const showVideo = timing.kind === 'video' && !showClip
    && (playing || position > 0 || !selected?.imageUrl);

  return (
    <section className="storyboard-editor" data-storyboard-editor aria-label="Редактор раскадровки">
      <header className="storyboard-editor__header">
        <div className="storyboard-editor__header-leading">
          <button type="button" className={plain} onClick={onBack}><ArrowLeft size={16} /> <span>Назад</span></button>
          <button type="button" className={icon} aria-label="Настройки ролика" title="Настройки ролика" aria-haspopup="dialog"
            onClick={() => settingsRef.current.showModal()}><Settings2 size={17} /></button>
          {onResult && <button type="button" className={plain} onClick={onResult}>{resultLabel}</button>}
        </div>
        <div className="storyboard-editor__heading">
          <div className="storyboard-editor__context">
            <span>{projectName || 'Раскадровка'}</span>
          </div>
          <h1 className="storyboard-editor__title">{title}</h1>
        </div>
        <div className="storyboard-editor__header-actions">
          <button type="button" className={button} aria-haspopup="dialog" onClick={() => estimateRef.current.showModal()}>Смета</button>
          {renderAction}
        </div>
      </header>

      <nav className="storyboard-editor__mobile-tabs" aria-label="Панели редактора">
        {views.map(([value, label]) => (
          <button key={value} id={`${id}-view-${value}`} type="button" className="storyboard-editor__tab"
            aria-pressed={(selected ? mobileView : 'script') === value} disabled={!selected && value !== 'script'}
            onClick={() => setMobileView(value)}>{label}</button>
        ))}
      </nav>
      <div className="storyboard-editor__work" data-mobile-view={selected ? mobileView : 'script'}>
        <section className="storyboard-editor__shots" aria-label="Кадры ролика">
          <div className="storyboard-editor__panel-head">
            <div className="storyboard-editor__tabs" role="group" aria-label="Сценарий и материалы">
              {[['script', 'Сценарий'], ['assets', 'Материалы']].map(([value, label]) => (
                <button key={value} type="button" className="storyboard-editor__tab" aria-pressed={leftView === value}
                  onClick={() => setLeftView(value)}>{label}</button>
              ))}
            </div>
            {onUndo && <button type="button" className={icon} onClick={() => { pauseTimeline(); setPlayingClip(false); onUndo(); }}
              title="Отменить последнее действие с кадрами" aria-label="Отменить последнее действие с кадрами"><Undo2 size={16} /></button>}
          </div>
          {leftView === 'script' ? <>
            <ol className="storyboard-editor__shot-list">
            {shots.map((frame, index) => (
              <li key={index} className="storyboard-editor__shot-row" data-dragging={dragIndex === index} data-drop-target={dropIndex === index}
                onDragOver={(event) => {
                  if (dragIndex === null) return;
                  event.preventDefault();
                  setDropIndex(index);
                }}
                onDrop={(event) => { event.preventDefault(); dropShot(index); }}>
                <span className="storyboard-editor__drag" draggable onDragStart={(event) => {
                  event.dataTransfer.setData('text/plain', String(index));
                  event.dataTransfer.effectAllowed = 'move';
                  setDragIndex(index);
                }} onDragEnd={clearDrag} title="Потяни, чтобы поменять порядок" aria-hidden="true"><GripVertical size={15} /></span>
                <button type="button" className="storyboard-editor__shot-select" data-storyboard-shot={index + 1}
                  aria-pressed={index === shotIndex} onClick={() => openShot(index)}>
                  <span className="storyboard-editor__shot-index">{String(index + 1).padStart(2, '0')}</span>
                  <span className="storyboard-editor__thumb">{frame.imageUrl ? <img src={frame.imageUrl} alt="" loading="lazy" /> : <Image size={15} />}</span>
                  <span className="storyboard-editor__shot-text">
                    <span className="storyboard-editor__shot-reply">{frame.shot.speech || frame.shot.scene || 'Пустой кадр'}</span>
                    <span className="storyboard-editor__shot-status" data-status={frame.status}>{frame.statusLabel}</span>
                  </span>
                  <span className="storyboard-editor__shot-time">{shotDuration(index)}</span>
                </button>
              </li>
            ))}
            </ol>
            {!shots.length && <p className="storyboard-editor__notice">Добавь первый кадр и напиши реплику.</p>}
            <button type="button" className={`${plain} storyboard-editor__add`} data-add-shot onClick={() => {
              onAdd();
              openShot(shots.length);
            }}><Plus size={16} /> Добавить кадр</button>
          </> : (
            <div className="storyboard-editor__assets">
              {shots.map((frame, index) => frame.imageUrl || frame.clipUrl ? (
                <button type="button" key={index} className="storyboard-editor__asset" aria-pressed={index === shotIndex}
                  onClick={() => openShot(index)}>
                  <span className="storyboard-editor__thumb">{frame.imageUrl ? <img src={frame.imageUrl} alt="" loading="lazy" /> : <Film size={15} />}</span>
                  <span>Кадр {index + 1}</span>
                </button>
              ) : null)}
              {!shots.some((frame) => frame.imageUrl || frame.clipUrl) && <p className="storyboard-editor__notice">Готовые изображения и клипы появятся здесь.</p>}
            </div>
          )}
        </section>

        <section className="storyboard-editor__preview" aria-label="Предпросмотр">
          <div className="storyboard-editor__panel-head storyboard-editor__preview-head">
            <h2>Предпросмотр</h2><span className="storyboard-editor__ratio">9:16</span>
          </div>
          <div className="storyboard-editor__stage">
            {timing.kind === 'video' && <video key={timing.src} ref={mediaRef} {...mediaEvents} src={timing.src}
              preload="auto" playsInline aria-label="Предпросмотр ролика" className="storyboard-editor__media"
              poster={selected?.imageUrl} style={showVideo ? undefined : { display: 'none' }} />}
            {showClip ? (
              <MediaPlayer key={selected.clipUrl} src={selected.clipUrl} poster={selected.imageUrl} autoPlay playsInline
                label={`Клип ${shotIndex + 1}`} className="storyboard-editor__media" mediaClassName="object-contain" />
            ) : showVideo ? null : selected?.imageUrl ? (
              <button type="button" className="storyboard-editor__media" aria-label={`Открыть кадр ${shotIndex + 1} на весь экран`}
                onClick={() => onEnlarge(selected.imageUrl, shotIndex)}>
                <img src={selected.imageUrl} alt={`Кадр ${shotIndex + 1}`} />
              </button>
            ) : (
              <div className="storyboard-editor__empty"><Image size={24} /><span>{selected ? 'Кадр без изображения' : 'Нет кадров'}</span></div>
            )}
          </div>
          {timing.kind === 'audio' && <audio key={timing.src} ref={mediaRef} {...mediaEvents} src={timing.src} preload="metadata" />}
          {selected && <div className="storyboard-editor__preview-caption">
            <span>Кадр {shotIndex + 1} из {shots.length}</span>
            {selected.clipUrl && (
              <button type="button" className={plain} aria-pressed={showClip}
                onClick={() => { pauseTimeline(); setPlayingClip(!showClip); }}><Film size={15} /> {showClip ? 'К кадру' : 'Смотреть клип'}</button>
            )}
          </div>}
        </section>

        <section className="storyboard-editor__inspector" aria-label="Параметры кадра"
          onFocusCapture={(event) => { if (event.target.matches('input, select, textarea')) pauseTimeline(); }}>
          <div className="storyboard-editor__panel-head">
            <h2>{selected ? `Кадр ${shotIndex + 1}` : 'Кадр'}</h2>
            {selected && <span className="storyboard-editor__shot-time">{shotDuration(shotIndex)}</span>}
          </div>
          {selected && <div className="storyboard-editor__inspector-fields">
            {renderShot(selected, shotIndex)}
            <details className="storyboard-editor__disclosure">
              <summary>Порядок и действия <ChevronDown size={15} /></summary>
              <div className="storyboard-editor__actions">
                <button type="button" className={button} disabled={shotIndex === 0} onClick={() => {
                  onMove(shotIndex, -1);
                  selectShot(shotIndex - 1);
                }}><ChevronUp size={15} /> Выше</button>
                <button type="button" className={button} disabled={shotIndex === shots.length - 1} onClick={() => {
                  onMove(shotIndex, 1);
                  selectShot(shotIndex + 1);
                }}><ChevronDown size={15} /> Ниже</button>
                <button type="button" className={button} onClick={() => {
                  onDuplicate(shotIndex);
                  selectShot(shotIndex + 1);
                }}><Copy size={15} /> Дублировать</button>
                <button type="button" className={button} disabled={shots.length <= 1} onClick={() => {
                  onRemove(shotIndex);
                  selectShot(Math.min(shotIndex, shots.length - 2));
                }}><Trash2 size={15} /> Удалить</button>
              </div>
            </details>
          </div>}
        </section>
      </div>

      {notice}
      <StoryboardTimeline shots={shots} timing={timing} waveform={waveform} position={position} selectedIndex={shotIndex}
        playing={playing} onToggle={togglePlayback} onSelect={selectShot}
        onSeek={(time) => { pauseTimeline(); seek(time); }} />

      <dialog className="storyboard-editor__dialog" ref={settingsRef} aria-labelledby={`${id}-settings`}>
        <div className="storyboard-editor__dialog-head">
          <h2 id={`${id}-settings`}>Настройки ролика</h2>
          <button type="button" className={icon} aria-label="Закрыть настройки" onClick={() => settingsRef.current.close()}><X size={18} /></button>
        </div>
        <div className="storyboard-editor__dialog-body">{settings}</div>
      </dialog>

      <dialog className="storyboard-editor__dialog" ref={estimateRef} aria-labelledby={`${id}-estimate`}>
        <div className="storyboard-editor__dialog-head">
          <h2 id={`${id}-estimate`}>Смета</h2>
          <button type="button" className={icon} aria-label="Закрыть смету" onClick={() => estimateRef.current.close()}><X size={18} /></button>
        </div>
        <div className="storyboard-editor__dialog-body">{estimate}</div>
      </dialog>
    </section>
  );
}

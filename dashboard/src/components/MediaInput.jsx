import React, { useState, useEffect } from 'react';
import { Youtube, Upload, FileVideo, X } from 'lucide-react';
import { getApiUrl } from '../config';

export default function MediaInput({ onProcess, isProcessing }) {
    const [youtubeUrlEnabled, setYoutubeUrlEnabled] = useState(true);
    const [mode, setMode] = useState('url'); // 'url' | 'file'
    const [url, setUrl] = useState('');
    const [file, setFile] = useState(null);
    const [acknowledged, setAcknowledged] = useState(false);

    useEffect(() => {
        fetch(getApiUrl('/api/config'))
            .then((r) => r.ok ? r.json() : null)
            .then((cfg) => {
                if (cfg && cfg.youtubeUrlEnabled === false) {
                    setYoutubeUrlEnabled(false);
                    setMode('file');
                }
            })
            .catch(() => {});
    }, []);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!acknowledged) return;
        if (mode === 'url' && url) {
            onProcess({ type: 'url', payload: url, acknowledged: true });
        } else if (mode === 'file' && file) {
            onProcess({ type: 'file', payload: file, acknowledged: true });
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
            setMode('file');
        }
    };

    return (
        <div className="bg-surface border border-white/5 rounded-2xl p-6 animate-[fadeIn_0.6s_ease-out]">
            {/* Segmented control — same idiom as the rest of the app, and it
                avoids the brittle negative-margin underline this used before. */}
            <div className="mb-6 inline-flex overflow-hidden rounded-xl border border-white/10">
                {youtubeUrlEnabled && (
                    <button
                        type="button"
                        onClick={() => setMode('url')}
                        aria-pressed={mode === 'url'}
                        className={`flex items-center gap-2 px-3.5 py-2 text-sm transition-colors ${mode === 'url'
                            ? 'bg-primary/15 text-violet-200'
                            : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200'
                            }`}
                    >
                        <Youtube size={16} />
                        Ссылка на YouTube
                    </button>
                )}
                <button
                    type="button"
                    onClick={() => setMode('file')}
                    aria-pressed={mode === 'file'}
                    className={`flex items-center gap-2 px-3.5 py-2 text-sm transition-colors ${mode === 'file'
                        ? 'bg-primary/15 text-violet-200'
                        : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200'
                        }`}
                >
                    <Upload size={16} />
                    Загрузить файл
                </button>
            </div>

            <form onSubmit={handleSubmit}>
                {mode === 'url' ? (
                    <div className="space-y-4">
                        <input
                            type="url"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            placeholder="https://www.youtube.com/watch?v=..."
                            className="input-field"
                            required
                        />
                    </div>
                ) : (
                    <div
                        className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${file ? 'border-primary/50 bg-primary/5' : 'border-zinc-700 hover:border-zinc-500 bg-white/5'
                            }`}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={handleDrop}
                    >
                        {file ? (
                            <div className="flex items-center justify-center gap-3 text-white">
                                <FileVideo className="text-primary" />
                                <span className="font-medium">{file.name}</span>
                                <button
                                    type="button"
                                    onClick={() => setFile(null)}
                                    className="p-1 hover:bg-white/10 rounded-full"
                                >
                                    <X size={16} />
                                </button>
                            </div>
                        ) : (
                            <label className="cursor-pointer block">
                                <input
                                    type="file"
                                    accept="video/*"
                                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                                    className="hidden"
                                />
                                <Upload className="mx-auto mb-3 text-zinc-500" size={24} />
                                <p className="text-zinc-400">Нажми, чтобы выбрать файл, или перетащи его сюда</p>
                                <p className="text-xs text-zinc-600 mt-1">MP4 или MOV, до 500 МБ</p>
                            </label>
                        )}
                    </div>
                )}

                <label className="flex items-start gap-2 mt-5 text-xs text-zinc-400 cursor-pointer select-none">
                    <input
                        type="checkbox"
                        checked={acknowledged}
                        onChange={(e) => setAcknowledged(e.target.checked)}
                        className="mt-0.5 accent-primary cursor-pointer"
                    />
                    <span className="leading-relaxed">
                        Подтверждаю, что это моё видео или у меня есть права на его обработку, и я отвечаю за загружаемый контент. См.{' '}
                        <a href="/#legal" target="_blank" rel="noopener noreferrer" className="text-primary underline" onClick={(e) => e.stopPropagation()}>условия и политику конфиденциальности</a>.
                    </span>
                </label>

                <button
                    type="submit"
                    disabled={isProcessing || !acknowledged || (mode === 'url' && !url) || (mode === 'file' && !file)}
                    className="w-full btn-primary mt-4 flex items-center justify-center gap-2"
                >
                    {isProcessing ? (
                        <>
                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            Обрабатываю видео...
                        </>
                    ) : (
                        'Нарезать клипы'
                    )}
                </button>
            </form>
        </div>
    );
}

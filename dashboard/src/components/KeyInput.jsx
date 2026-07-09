import React, { useState, useEffect } from 'react';
import { Key, Eye, EyeOff, Check } from 'lucide-react';

export default function KeyInput({ onKeySet, savedKey, onAccountSave, hasAccountKey }) {
    const [key, setKey] = useState(savedKey || '');
    const [isVisible, setIsVisible] = useState(false);
    const [isSaved, setIsSaved] = useState(!!savedKey);

    useEffect(() => {
        if (savedKey) setKey(savedKey);
    }, [savedKey]);

    const handleSave = () => {
        if (key.trim().length > 0) {
            onKeySet(key);
            if (onAccountSave) onAccountSave(key);
            setIsSaved(true);
        }
    };

    return (
        <div className="bg-surface border border-white/5 rounded-2xl p-6 mb-8 animate-[fadeIn_0.5s_ease-out]">
            <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-accent/20 rounded-lg text-accent">
                    <Key size={20} />
                </div>
                <h2 className="text-lg font-semibold">Gemini API Key</h2>
            </div>

            <div className="flex gap-3">
                <div className="relative flex-1">
                    <input
                        type={isVisible ? "text" : "password"}
                        aria-label="Gemini API key"
                        value={key}
                        onChange={(e) => {
                            setKey(e.target.value);
                            setIsSaved(false);
                        }}
                        placeholder="AIzaSy..."
                        className="input-field pr-12 font-mono"
                    />
                    <button
                        type="button"
                        aria-label={isVisible ? 'Скрыть API-ключ' : 'Показать API-ключ'}
                        onClick={() => setIsVisible(!isVisible)}
                        className="absolute right-1 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-white/5 hover:text-white"
                    >
                        {isVisible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
                    </button>
                </div>
                <button
                    type="button"
                    onClick={handleSave}
                    disabled={!key || isSaved}
                    className={`px-6 rounded-xl font-medium transition-all flex items-center gap-2 ${isSaved
                        ? 'bg-green-500/20 text-green-400 cursor-default'
                        : 'bg-primary hover:bg-blue-600 text-white shadow-lg shadow-primary/20'
                        }`}
                >
                    {isSaved ? <><Check size={18} /> Ready</> : 'Set Key'}
                </button>
            </div>
            <p className="mt-3 text-xs text-zinc-500">
                {hasAccountKey ? 'Gemini key is saved in your account vault.' : 'Your key can be saved to your account vault after login.'}
                <br />
                <a
                    href="https://aistudio.google.com/app/apikey"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-flex py-2 text-primary hover:underline"
                >
                    Get your free Gemini API Key here →
                </a>
            </p>
        </div>
    );
}

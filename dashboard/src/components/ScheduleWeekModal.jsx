import React, { useState, useMemo } from 'react';
import { X, Loader2, Calendar, Clock, CheckCircle, AlertCircle, Video, Instagram, Youtube, ChevronLeft, ChevronRight, Globe, ExternalLink } from 'lucide-react';
import { getApiUrl } from '../config';

const DAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

// Список часовых поясов. Пояса СНГ обязательны: без Europe/Moscow
// detectTimezone() молча падал в UTC, и вся неделя планировалась на 3 часа раньше.
const TIMEZONES = [
    { value: 'Europe/Kaliningrad', label: '(GMT+02:00) Калининград' },
    { value: 'Europe/Kyiv', label: '(GMT+02:00) Киев' },
    { value: 'Europe/Minsk', label: '(GMT+03:00) Минск' },
    { value: 'Europe/Moscow', label: '(GMT+03:00) Москва' },
    { value: 'Europe/Samara', label: '(GMT+04:00) Самара' },
    { value: 'Asia/Tbilisi', label: '(GMT+04:00) Тбилиси' },
    { value: 'Asia/Yerevan', label: '(GMT+04:00) Ереван' },
    { value: 'Asia/Yekaterinburg', label: '(GMT+05:00) Екатеринбург' },
    { value: 'Asia/Tashkent', label: '(GMT+05:00) Ташкент' },
    { value: 'Asia/Almaty', label: '(GMT+05:00) Алматы' },
    { value: 'Asia/Omsk', label: '(GMT+06:00) Омск' },
    { value: 'Asia/Krasnoyarsk', label: '(GMT+07:00) Красноярск' },
    { value: 'Asia/Irkutsk', label: '(GMT+08:00) Иркутск' },
    { value: 'Asia/Yakutsk', label: '(GMT+09:00) Якутск' },
    { value: 'Asia/Vladivostok', label: '(GMT+10:00) Владивосток' },
    { value: 'Asia/Kamchatka', label: '(GMT+12:00) Камчатка' },
    { value: 'UTC', label: '(GMT+00:00) UTC' },
    { value: 'Europe/London', label: '(GMT+00:00) Лондон' },
    { value: 'Europe/Berlin', label: '(GMT+01:00) Берлин' },
    { value: 'Europe/Paris', label: '(GMT+01:00) Париж' },
    { value: 'Europe/Madrid', label: '(GMT+01:00) Мадрид' },
    { value: 'Europe/Rome', label: '(GMT+01:00) Рим' },
    { value: 'Europe/Istanbul', label: '(GMT+03:00) Стамбул' },
    { value: 'Asia/Dubai', label: '(GMT+04:00) Дубай' },
    { value: 'Asia/Kolkata', label: '(GMT+05:30) Индия' },
    { value: 'Asia/Bangkok', label: '(GMT+07:00) Бангкок' },
    { value: 'Asia/Shanghai', label: '(GMT+08:00) Шанхай' },
    { value: 'Asia/Tokyo', label: '(GMT+09:00) Токио' },
    { value: 'Australia/Sydney', label: '(GMT+10:00) Сидней' },
    { value: 'America/New_York', label: '(GMT-05:00) Нью-Йорк' },
    { value: 'America/Chicago', label: '(GMT-06:00) Чикаго' },
    { value: 'America/Denver', label: '(GMT-07:00) Денвер' },
    { value: 'America/Los_Angeles', label: '(GMT-08:00) Лос-Анджелес' },
    { value: 'America/Sao_Paulo', label: '(GMT-03:00) Сан-Паулу' },
];

function getDayLabel(date) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const target = new Date(date);
    target.setHours(0, 0, 0, 0);

    if (target.getTime() === today.getTime()) return 'сегодня';
    if (target.getTime() === tomorrow.getTime()) return 'завтра';
    return DAYS[target.getDay()];
}

// 1 клип, 2 клипа, 5 клипов.
function clipsPlural(n) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'клип';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'клипа';
    return 'клипов';
}

function formatDate(date) {
    return `${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

function detectTimezone() {
    try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (TIMEZONES.find(t => t.value === tz)) return tz;
        return 'UTC';
    } catch {
        return 'UTC';
    }
}

export default function ScheduleWeekModal({ isOpen, onClose, clips, jobId, uploadPostKey, uploadUserId }) {
    const [time, setTime] = useState('12:00');
    const [timezone, setTimezone] = useState(detectTimezone);
    const [platforms, setPlatforms] = useState({
        tiktok: true,
        instagram: true,
        youtube: true
    });
    const [startOffset, setStartOffset] = useState(1);

    const schedule = useMemo(() => {
        if (!clips) return [];
        return clips.map((clip, i) => {
            const date = new Date();
            date.setDate(date.getDate() + startOffset + i);
            date.setHours(0, 0, 0, 0);
            return { clip, index: i, date };
        });
    }, [clips, startOffset]);

    const [scheduling, setScheduling] = useState(false);
    const [progress, setProgress] = useState({ current: 0, total: 0, results: [] });
    const [done, setDone] = useState(false);

    // Reset state when modal reopens
    const prevOpen = React.useRef(false);
    React.useEffect(() => {
        if (isOpen && !prevOpen.current) {
            setScheduling(false);
            setDone(false);
            setProgress({ current: 0, total: 0, results: [] });
        }
        prevOpen.current = isOpen;
    }, [isOpen]);

    if (!isOpen) return null;

    const selectedPlatforms = Object.keys(platforms).filter(k => platforms[k]);

    const handleScheduleAll = async () => {
        if (!uploadPostKey || !uploadUserId) return;
        if (selectedPlatforms.length === 0) return;

        setScheduling(true);
        setDone(false);
        const total = schedule.length;
        setProgress({ current: 0, total, results: [] });

        const results = [];
        for (let i = 0; i < schedule.length; i++) {
            const { clip, index, date } = schedule[i];

            // Build local datetime string: "2026-04-06T12:00:00"
            // Upload-Post accepts this + timezone IANA parameter
            const pad = (n) => String(n).padStart(2, '0');
            const scheduledDate = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${time}:00`;

            const payload = {
                job_id: jobId,
                clip_index: index,
                api_key: uploadPostKey,
                user_id: uploadUserId,
                platforms: selectedPlatforms,
                title: clip.video_title_for_youtube_short || 'Viral Short',
                description: clip.video_description_for_instagram || clip.video_description_for_tiktok || '',
                scheduled_date: scheduledDate,
                timezone
            };

            try {
                const res = await fetch(getApiUrl('/api/social/post'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    const errText = await res.text();
                    throw new Error(errText);
                }

                results.push({ index: i, success: true });
            } catch (e) {
                results.push({ index: i, success: false, error: e.message });
            }

            setProgress({ current: i + 1, total, results: [...results] });
        }

        setDone(true);
        setScheduling(false);
    };

    const successCount = progress.results.filter(r => r.success).length;
    const failCount = progress.results.filter(r => !r.success).length;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-[fadeIn_0.2s_ease-out]">
            <div className="bg-[#121214] border border-white/10 p-6 rounded-2xl w-full max-w-lg shadow-2xl relative max-h-[90vh] overflow-y-auto custom-scrollbar">
                <button
                    onClick={onClose}
                    disabled={scheduling}
                    className="absolute top-4 right-4 text-zinc-500 hover:text-white disabled:opacity-50"
                >
                    <X size={20} />
                </button>

                {/* Header */}
                <div className="flex items-center gap-3 mb-6">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
                        <Calendar size={20} className="text-white" />
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-white">Запланировать неделю</h3>
                        <p className="text-xs text-zinc-500">{clips?.length || 0} {clipsPlural(clips?.length || 0)} &middot; по одному в день</p>
                    </div>
                </div>

                {!uploadPostKey && (
                    <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/20 text-yellow-200 text-xs rounded-lg flex items-start gap-2">
                        <AlertCircle size={14} className="mt-0.5 shrink-0" />
                        <div>Сначала добавь API-ключ Upload-Post в настройках.</div>
                    </div>
                )}

                {/* Time + Timezone */}
                <div className="mb-5 grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-bold text-zinc-400 mb-2 flex items-center gap-2">
                            <Clock size={14} className="text-purple-400" />
                            Время
                        </label>
                        <input
                            type="time"
                            value={time}
                            onChange={(e) => setTime(e.target.value)}
                            disabled={scheduling}
                            className="w-full bg-black/40 border border-white/10 rounded-lg p-3 text-sm text-white focus:outline-none focus:border-purple-500/50 [color-scheme:dark]"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-zinc-400 mb-2 flex items-center gap-2">
                            <Globe size={14} className="text-indigo-400" />
                            Часовой пояс
                        </label>
                        <select
                            value={timezone}
                            onChange={(e) => setTimezone(e.target.value)}
                            disabled={scheduling}
                            className="w-full bg-black/40 border border-white/10 rounded-lg p-3 text-sm text-white focus:outline-none focus:border-indigo-500/50 appearance-none cursor-pointer"
                        >
                            {TIMEZONES.map(tz => (
                                <option key={tz.value} value={tz.value}>{tz.label}</option>
                            ))}
                        </select>
                    </div>
                </div>

                {/* Start day offset */}
                <div className="mb-5 flex items-center justify-between">
                    <span className="text-xs font-bold text-zinc-400">Начать с</span>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setStartOffset(Math.max(1, startOffset - 1))}
                            disabled={startOffset <= 1 || scheduling}
                            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white disabled:opacity-30 transition-colors"
                        >
                            <ChevronLeft size={16} />
                        </button>
                        <span className="text-sm text-white font-medium min-w-[90px] text-center">
                            {(() => {
                                const d = new Date();
                                d.setDate(d.getDate() + startOffset);
                                return `${getDayLabel(d)} ${formatDate(d)}`;
                            })()}
                        </span>
                        <button
                            onClick={() => setStartOffset(startOffset + 1)}
                            disabled={scheduling}
                            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white disabled:opacity-30 transition-colors"
                        >
                            <ChevronRight size={16} />
                        </button>
                    </div>
                </div>

                {/* Calendar grid */}
                <div className="mb-5 space-y-2">
                    {schedule.map(({ clip, index, date }) => (
                        <div key={index} className="flex items-center gap-3 p-3 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors">
                            <div className="w-14 shrink-0 text-center">
                                <div className="text-[10px] font-bold text-purple-400 uppercase">{getDayLabel(date)}</div>
                                <div className="text-lg font-bold text-white leading-tight">{date.getDate()}</div>
                                <div className="text-[10px] text-zinc-500">{MONTHS[date.getMonth()]}</div>
                            </div>

                            <div className="flex-1 min-w-0">
                                <div className="text-xs font-bold text-white truncate">
                                    Клип {index + 1}
                                </div>
                                <div className="text-[10px] text-zinc-500 truncate">
                                    {clip.video_title_for_youtube_short || 'Без названия'}
                                </div>
                                <div className="text-[10px] text-zinc-600 mt-0.5">
                                    {time} &middot; {TIMEZONES.find(t => t.value === timezone)?.label || timezone}
                                </div>
                            </div>

                            <div className="shrink-0">
                                {progress.results[index]?.success === true && (
                                    <CheckCircle size={18} className="text-green-400" />
                                )}
                                {progress.results[index]?.success === false && (
                                    <AlertCircle size={18} className="text-red-400" />
                                )}
                                {scheduling && progress.current === index && (
                                    <Loader2 size={18} className="text-purple-400 animate-spin" />
                                )}
                                {!scheduling && progress.results[index] === undefined && (
                                    <div className="w-4 h-4 rounded-full border-2 border-zinc-700" />
                                )}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Platforms */}
                <div className="mb-5">
                    <label className="block text-xs font-bold text-zinc-400 mb-2">Платформы</label>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setPlatforms(p => ({ ...p, tiktok: !p.tiktok }))}
                            disabled={scheduling}
                            className={`flex-1 flex items-center justify-center gap-2 p-2.5 rounded-lg text-xs font-bold border transition-all ${platforms.tiktok ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400' : 'bg-white/5 border-white/5 text-zinc-500'}`}
                        >
                            <Video size={14} /> TikTok
                        </button>
                        <button
                            onClick={() => setPlatforms(p => ({ ...p, instagram: !p.instagram }))}
                            disabled={scheduling}
                            className={`flex-1 flex items-center justify-center gap-2 p-2.5 rounded-lg text-xs font-bold border transition-all ${platforms.instagram ? 'bg-pink-500/10 border-pink-500/30 text-pink-400' : 'bg-white/5 border-white/5 text-zinc-500'}`}
                        >
                            <Instagram size={14} /> Instagram
                        </button>
                        <button
                            onClick={() => setPlatforms(p => ({ ...p, youtube: !p.youtube }))}
                            disabled={scheduling}
                            className={`flex-1 flex items-center justify-center gap-2 p-2.5 rounded-lg text-xs font-bold border transition-all ${platforms.youtube ? 'bg-red-500/10 border-red-500/30 text-red-400' : 'bg-white/5 border-white/5 text-zinc-500'}`}
                        >
                            <Youtube size={14} /> YouTube
                        </button>
                    </div>
                </div>

                {/* Progress bar */}
                {(scheduling || done) && (
                    <div className="mb-5">
                        <div className="flex items-center justify-between text-xs text-zinc-400 mb-2">
                            <span>{scheduling ? 'Планирую...' : 'Готово'}</span>
                            <span>{progress.current}/{progress.total}</span>
                        </div>
                        <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full transition-all duration-500 ${done && failCount === 0 ? 'bg-green-500' : done && failCount > 0 ? 'bg-yellow-500' : 'bg-purple-500'}`}
                                style={{ width: `${(progress.current / progress.total) * 100}%` }}
                            />
                        </div>
                        {done && (
                            <div className="mt-3 text-xs text-center">
                                {failCount === 0 ? (
                                    <span className="text-green-400">Все клипы успешно запланированы</span>
                                ) : (
                                    <span className="text-yellow-400">Запланировано: {successCount}, с ошибкой: {failCount}</span>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* Actions */}
                <div className="flex gap-3">
                    <button
                        onClick={onClose}
                        disabled={scheduling}
                        className="flex-1 py-3 bg-white/5 hover:bg-white/10 text-zinc-300 rounded-xl font-medium transition-colors disabled:opacity-50"
                    >
                        {done ? 'Закрыть' : 'Отмена'}
                    </button>
                    {!done ? (
                        <button
                            onClick={handleScheduleAll}
                            disabled={scheduling || !uploadPostKey || selectedPlatforms.length === 0}
                            className="flex-1 py-3 bg-gradient-to-r from-purple-500 to-indigo-600 hover:from-purple-400 hover:to-indigo-500 text-white rounded-xl font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        >
                            {scheduling ? (
                                <>
                                    <Loader2 size={16} className="animate-spin" />
                                    Планирую...
                                </>
                            ) : (
                                <>
                                    <Calendar size={16} />
                                    Запланировать {clips?.length || 0} {clipsPlural(clips?.length || 0)}
                                </>
                            )}
                        </button>
                    ) : (
                        <a
                            href="https://app.upload-post.com/calendar"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex-1 py-3 bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-400 hover:to-purple-500 text-white rounded-xl font-bold transition-all flex items-center justify-center gap-2 no-underline"
                        >
                            <ExternalLink size={16} />
                            Открыть календарь
                        </a>
                    )}
                </div>
            </div>
        </div>
    );
}

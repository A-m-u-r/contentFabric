import React from 'react';
import { X, ShieldAlert, Loader2, ImageOff } from 'lucide-react';

// Почему модель не нарисовала кадр — человеческим языком. Дословный ответ fal
// показываем рядом: он есть в логе, но лог читают не все, а деньги списываются
// со всех.
const REASON_TEXT = {
  moderation:
    'Это модерация на стороне вендора: она смотрит и на входное фото, и на результат. '
    + 'Кадр вернулся пустым, но fal тарифицирует его как обычную картинку.',
  blank:
    'Модель вернула пустой кадр без подтверждённого флага модерации. '
    + 'Результат оплачен, но не запомнен; повтор возможен только вручную.',
  known:
    'Эта модель уже отказывала на этом фото с тем же описанием кадра. '
    + 'Поэтому повторный запрос не отправлялся — денег не списано.',
  unavailable:
    'Эндпоинт модели ответил ошибкой — похоже, её сняли или переехала. '
    + 'За несостоявшуюся генерацию fal денег не берёт.',
  unreachable:
    'Запрос не дошёл до fal — оборвалась сеть или не разрешилось имя. Модель '
    + 'фотографию не видела и ничего не отклоняла, денег не списано.',
};

/**
 * Отказ редактора кадра — с выбором, что делать дальше.
 *
 * Раньше пайплайн молча брал следующую модель из списка, и человек узнавал о
 * подмене по счёту. Подменять модель за спиной — это тратить чужие деньги на
 * нашу догадку, поэтому выбор здесь: либо другая модель, либо другое фото.
 */
export default function FrameEditorBlockedModal({
  block,
  models = [],
  spentUsd = '',
  busy = false,
  onPick,
  onClose,
}) {
  if (!block) return null;

  const flags = block.flags && Object.keys(block.flags).length ? block.flags : null;
  // Отказ содержит варианты именно для этого фото и описания кадра. Общий
  // каталог нужен только для ответа старого бэкенда, где alternatives ещё нет.
  const sourceModels = Array.isArray(block.alternatives)
    ? block.alternatives
    : models;
  const options = sourceModels.filter((m) => m.id !== block.model);
  // Сеть не чинится сменой модели. Предлагать здесь перебор — это звать
  // потратить $0.05 на попытку, которая упрётся ровно в то же место.
  const unreachable = block.reason === 'unreachable';

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="bg-[#121214] border border-white/10 p-6 rounded-2xl w-full max-w-lg shadow-2xl relative max-h-[90vh] overflow-y-auto">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-zinc-500 hover:text-white"
          type="button"
        >
          <X size={18} />
        </button>

        <div className="flex items-start gap-3 pr-6">
          <ShieldAlert size={20} className="text-amber-400 shrink-0 mt-0.5" />
          <div>
            <h3 className="text-[15px] font-semibold text-white">
              {block.title} не стал рисовать кадр
            </h3>
            <p className="text-[12px] text-zinc-400 mt-1">
              {REASON_TEXT[block.reason] || REASON_TEXT.moderation}
            </p>
          </div>
        </div>

        {flags && (
          <div className="mt-4">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1.5">
              Что ответила модель
            </p>
            <pre className="text-[11px] text-amber-100/90 bg-black/40 border border-white/5 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(flags, null, 2)}
            </pre>
          </div>
        )}

        <p className="text-[11px] text-zinc-500 mt-3">
          {block.charged
            ? `Пустой кадр стоит столько же, сколько нарисованный${spentUsd ? `: списано ${spentUsd}` : ''}.`
            : 'За эту попытку деньги не списаны.'}
        </p>

        {unreachable ? (
          <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-3 flex gap-2.5">
            <ImageOff size={16} className="text-zinc-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-zinc-300">
              Другая модель не поможет — она живёт по тому же адресу. Проверь сеть
              и нажми «Перегенерить» ещё раз той же моделью.
            </p>
          </div>
        ) : options.length > 0 ? (
          <div className="mt-5">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
              Попробовать другой моделью
            </p>
            <div className="space-y-2">
              {options.map((model) => (
                <button
                  key={model.id}
                  type="button"
                  disabled={busy || model.blocked}
                  onClick={() => onPick(model.id)}
                  className="w-full text-left rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] disabled:opacity-40 disabled:hover:bg-white/[0.03] p-3 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] text-white">{model.title}</span>
                    <span className="text-[10px] text-zinc-500">
                      {model.blocked ? 'уже отказала на этом фото' : model.vendor}
                    </span>
                  </div>
                  {model.note && (
                    <p className="text-[11px] text-zinc-400 mt-0.5">{model.note}</p>
                  )}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-zinc-500 mt-2">
              Одна попытка — один платный запрос (~$0.05). Выбранная модель останется
              и для генерации видео.
            </p>
          </div>
        ) : (
          <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-3 flex gap-2.5">
            <ImageOff size={16} className="text-zinc-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-zinc-300">
              На этом фото отказались все редакторы. Дело в самой фотографии — поставь
              ведущим одиночный вертикальный портрет: это бесплатно и решает такое чаще,
              чем перебор моделей.
            </p>
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          {busy && <Loader2 size={14} className="animate-spin text-zinc-400" />}
          <button
            type="button"
            onClick={onClose}
            className="btn-secondary px-3 py-2 text-[12px]"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}

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
  download:
    'Готовый кадр уже был нарисован, но его файл не скачался из-за сбоя сети или DNS. '
    + 'Приложение повторило скачивание без новых генераций.',
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
  const networkFailure = block.reason === 'unreachable' || block.reason === 'download';
  const downloadFailure = block.reason === 'download';

  return (
    <dialog ref={(dialog) => { if (dialog && !dialog.open) dialog.showModal(); }}
      aria-label="Результат создания кадра" onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="relative m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-md border border-[#dfe1e7] bg-white p-6 text-[#242631] backdrop:bg-black/40">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-[#545967] hover:text-[#242631]"
          type="button"
          aria-label="Закрыть сообщение"
        >
          <X size={18} />
        </button>

        <div className="flex items-start gap-3 pr-6">
          <ShieldAlert size={20} className="text-[#674619] shrink-0 mt-0.5" />
          <div>
            <h3 className="text-[15px] font-semibold">
              {downloadFailure
                ? `${block.title} нарисовал кадр, но файл не скачался`
                : `${block.title} не стал рисовать кадр`}
            </h3>
            <p className="mt-1 text-sm text-[#545967]">
              {REASON_TEXT[block.reason] || REASON_TEXT.moderation}
            </p>
          </div>
        </div>

        {flags && (
          <div className="mt-4">
            <p className="mb-1.5 text-xs text-[#545967]">
              Что ответила модель
            </p>
            <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-md border border-[#dfe1e7] bg-[#f0f1f3] p-3 text-xs">
              {JSON.stringify(flags, null, 2)}
            </pre>
          </div>
        )}

        <p className="mt-3 text-xs text-[#545967]">
          {downloadFailure
            ? `Генерация завершилась и оплачена${spentUsd ? `: списано ${spentUsd}` : ''}. Новый платный запрос автоматически не отправлялся.`
            : block.charged
            ? `Пустой кадр стоит столько же, сколько нарисованный${spentUsd ? `: списано ${spentUsd}` : ''}.`
            : 'За эту попытку деньги не списаны.'}
        </p>

        {networkFailure ? (
          <div className="mt-5 flex gap-2.5 border-t border-[#dfe1e7] pt-3">
            <ImageOff size={16} className="text-[#545967] shrink-0 mt-0.5" />
            <p className="text-sm text-[#545967]">
              {downloadFailure
                ? 'Другая модель не поможет и создаст новый платный запрос. Проверь сеть; повторная генерация возможна только после твоего ручного нажатия.'
                : 'Другая модель не поможет — она живёт по тому же адресу. Проверь сеть и нажми «Перегенерить» ещё раз той же моделью.'}
            </p>
          </div>
        ) : options.length > 0 ? (
          <div className="mt-5">
            <p className="mb-2 text-sm font-medium">
              Попробовать другой моделью
            </p>
            <div className="space-y-2">
              {options.map((model) => (
                <button
                  key={model.id}
                  type="button"
                  disabled={busy || model.blocked}
                  onClick={() => onPick(model.id)}
                  className="w-full rounded-md border border-[#dfe1e7] p-3 text-left transition-colors hover:bg-[#f0f1f3] disabled:opacity-50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm">{model.title}</span>
                    <span className="text-xs text-[#545967]">
                      {model.blocked ? 'уже отказала на этом фото' : model.vendor}
                    </span>
                  </div>
                  {model.note && (
                    <p className="mt-0.5 text-xs text-[#545967]">{model.note}</p>
                  )}
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-[#545967]">
              Одна попытка — один платный запрос (~$0.05). Выбранная модель останется
              и для генерации видео.
            </p>
          </div>
        ) : (
          <div className="mt-5 flex gap-2.5 border-t border-[#dfe1e7] pt-3">
            <ImageOff size={16} className="text-[#545967] shrink-0 mt-0.5" />
            <p className="text-sm text-[#545967]">
              На этом фото отказались все редакторы. Дело в самой фотографии — поставь
              ведущим одиночный вертикальный портрет: это бесплатно и решает такое чаще,
              чем перебор моделей.
            </p>
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          {busy && <Loader2 size={14} className="animate-spin text-[#545967]" />}
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-[#dfe1e7] px-3 py-2 text-sm hover:bg-[#f0f1f3]"
          >
            Закрыть
          </button>
        </div>
    </dialog>
  );
}

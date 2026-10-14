import React from 'react';
import { Receipt } from 'lucide-react';
import { galleryCostSummary } from './galleryCosts';

const COST_KINDS = {
  billed: { label: 'Списано', className: 'text-emerald-300' },
  estimate: { label: 'Оценка', className: 'text-amber-300' },
  reused: { label: 'Повторно использовано', className: 'text-sky-300' },
  local: { label: 'Локально', className: 'text-zinc-400' },
  unknown: { label: 'Неизвестно', className: 'text-amber-300' },
};

export default function VideoCostBreakdown({ video }) {
  const cost = galleryCostSummary(video);
  const detailedItems = cost.items.filter((item) => item.details);

  return (
    <section aria-label="Стоимость генерации" className="space-y-3 border-b border-white/10 pb-5">
      <h4 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
        <Receipt size={16} className="text-zinc-400" /> Стоимость генерации
      </h4>
      {cost.total !== null && (
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <span className="text-sm text-zinc-400">{cost.totalLabel}</span>
          <span className="text-base font-semibold tabular-nums text-zinc-100">{cost.totalText}</span>
        </div>
      )}
      {video.cost_details?.scope === 'current_generation' && (
        <p className="text-xs text-zinc-500">Новые расходы на эту версию</p>
      )}
      {cost.items.length > 0 ? (
        <dl className="divide-y divide-white/5">
          {cost.items.map((item, index) => {
            const status = COST_KINDS[item.kind];
            return (
              <div key={`${item.key}-${index}`} className="grid grid-cols-[minmax(0,1fr),auto] items-start gap-3 py-2.5 first:pt-0">
                <dt className="min-w-0 text-sm text-zinc-300">
                  <span className="block break-words">{item.label}</span>
                  <span className={`mt-0.5 block text-[11px] ${status.className}`}>{status.label}</span>
                </dt>
                <dd className="whitespace-nowrap text-sm font-medium tabular-nums text-zinc-100">
                  {item.amount_usd === null ? 'Неизвестно' : `${item.kind === 'estimate' ? '~' : ''}$${item.amount_usd.toFixed(item.amount_usd > 0 && item.amount_usd < 0.01 ? 3 : 2)}`}
                </dd>
              </div>
            );
          })}
        </dl>
      ) : (
        <p className="text-xs text-zinc-500">
          {cost.total === null ? 'Стоимость не сохранена для этого ролика.' : 'Сохранена только общая оценка, без разбивки.'}
        </p>
      )}
      {cost.estimated && cost.total !== null && (
        <p className="text-xs leading-relaxed text-zinc-500">Оценка не подтверждает фактическое списание у провайдера.</p>
      )}
      {!cost.complete && cost.items.length > 0 && (
        <p className="text-xs leading-relaxed text-amber-300/80">Полная сумма неизвестна: не для всех услуг сохранена цена в USD.</p>
      )}
      {(detailedItems.length > 0 || cost.notes.length > 0) && (
        <details className="text-xs text-zinc-400">
          <summary className="cursor-pointer py-1 hover:text-zinc-200 focus-visible:outline focus-visible:outline-sky-400">Детали расчёта</summary>
          <div className="mt-2 space-y-3 leading-relaxed">
            {detailedItems.map((item, index) => (
              <p key={`${item.key}-${index}`} className="break-words">
                <span className="text-zinc-300">{item.label}: </span>{item.details}
              </p>
            ))}
            {cost.notes.map((note, index) => <p key={`note-${index}`}>{note}</p>)}
          </div>
        </details>
      )}
    </section>
  );
}

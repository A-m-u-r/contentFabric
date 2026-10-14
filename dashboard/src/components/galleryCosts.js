const COST_LABELS = {
  actor_image_flux: 'Изображение ведущего · FLUX',
  actor_image_reused: 'Изображение ведущего · повторное использование',
  reference_frames_flux: 'Референсы кадров · FLUX',
  voiceover_elevenlabs: 'Озвучка · ElevenLabs',
  voiceover_fal_minimax: 'Озвучка · MiniMax',
  talking_head_kling_standard: 'Ведущий · Kling Avatar Standard',
  talking_head_kling_pro: 'Ведущий · Kling Avatar Pro',
  sliced_avatar_kling_standard: 'Говорящие кадры · Kling Avatar Standard',
  sliced_avatar_kling_pro: 'Говорящие кадры · Kling Avatar Pro',
  sliced_broll_kling_v3_standard: 'B-roll · Kling V3 Standard',
  sliced_broll_kling_v3_pro: 'B-roll · Kling V3 Pro',
  talking_head_reuse_lipsync: 'Синхронизация губ · готовый ведущий',
  hailuo_img2video: 'Движение ведущего · Hailuo',
  veed_lipsync: 'Синхронизация губ · VEED',
  broll_flux: 'B-roll · FLUX',
  broll_mockups: 'B-roll · макеты',
  broll_disabled: 'B-roll · отключён',
  ffmpeg_compositing: 'Монтаж и субтитры · локально',
};

function dollarAmount(value) {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  if (typeof value === 'string' && !value.trim()) return null;
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0 ? amount : null;
}

export function galleryCostSummary(video = {}) {
  const details = video.cost_details;
  const detailedItems = Array.isArray(details?.items) && details.items.length > 0;
  const legacy = video.cost_estimate || {};
  const items = detailedItems
    ? details.items.filter((item) => item && typeof item === 'object').map((item, index) => {
      const amount = dollarAmount(item.amount_usd);
      const kind = amount === null ? 'unknown'
        : ['billed', 'reused', 'local'].includes(item.kind) ? item.kind : 'estimate';
      return { ...item, key: item.key || `cost-${index}`, label: item.label || COST_LABELS[item.key] || item.key || 'Генерация', amount_usd: amount, kind };
    })
    : Object.entries(legacy).filter(([key]) => key !== 'total').map(([key, value]) => ({
      key, label: COST_LABELS[key] || key.replaceAll('_', ' '),
      amount_usd: dollarAmount(value), kind: dollarAmount(value) === null ? 'unknown' : 'estimate',
    }));
  const known = items.filter((item) => item.amount_usd !== null);
  const unknown = items.length - known.length;
  const savedTotal = detailedItems ? null : dollarAmount(legacy.total);
  const sum = known.reduce((total, item) => total + item.amount_usd, 0);
  const total = savedTotal !== null && unknown === 0 ? savedTotal : known.length ? sum : null;
  const complete = total !== null && unknown === 0;
  const estimated = !detailedItems || known.some((item) => item.kind === 'estimate');
  const amountText = total === null ? 'Нет данных' : `${estimated ? '~' : ''}$${total.toFixed(2)}`;
  return {
    items, total, complete, estimated,
    totalLabel: total === null ? 'Стоимость' : !complete ? 'Известная часть'
      : estimated ? 'Оценка расходов' : 'Подтверждённые расходы',
    totalText: total !== null && !complete ? `${amountText} + неизвестная часть` : amountText,
    compactText: total !== null && !complete ? `${amountText} + ?` : amountText,
    notes: Array.isArray(details?.notes) ? details.notes.filter((note) => typeof note === 'string') : [],
  };
}

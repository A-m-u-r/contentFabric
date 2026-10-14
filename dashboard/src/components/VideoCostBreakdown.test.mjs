import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server;
let VideoCostBreakdown;

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom', server: { middlewareMode: true },
  });
  try {
    ({ default: VideoCostBreakdown } = await server.ssrLoadModule('/src/components/VideoCostBreakdown.jsx'));
  } catch (error) {
    if (!error.message.includes('Failed to load url')) throw error;
  }
});

after(async () => server?.close());

function render(video) {
  assert.equal(typeof VideoCostBreakdown, 'function', 'Gallery cost breakdown must be implemented');
  return renderToStaticMarkup(React.createElement(VideoCostBreakdown, { video }));
}

test('modal cost section shows each legacy charge, total and estimate notice', () => {
  const html = render({ cost_estimate: { voiceover_elevenlabs: 0.009, talking_head_kling_standard: 1.08, total: 1.09 } });
  assert.ok(html.includes('Стоимость генерации'));
  assert.ok(html.includes('Озвучка · ElevenLabs'));
  assert.ok(html.includes('~$1.09'));
  assert.ok(html.includes('Оценка'));
});

test('partial cost is not presented as the full cost and reused assets are marked', () => {
  const html = render({ cost_details: { items: [
    { key: 'head', label: 'Ведущая', amount_usd: 1.07904, kind: 'estimate' },
    { key: 'voice', label: 'Anna V4', amount_usd: null, kind: 'unknown', details: '269 символов' },
    { key: 'broll', label: 'B-roll', amount_usd: 0, kind: 'reused' },
  ] } });
  assert.ok(html.includes('Известная часть'));
  assert.ok(html.includes('269 символов'));
  assert.ok(html.includes('Неизвестно'));
  assert.ok(html.includes('Повторно использовано'));
  assert.ok(html.includes('~$1.08 + неизвестная часть'));
  assert.ok(!html.includes('Подтверждённые расходы'));
});

test('missing metadata shows a clear unavailable state', () => {
  const html = render({});
  assert.ok(html.includes('Стоимость не сохранена'));
  assert.ok(!html.includes('$0.00'));
});

test('confirmed USD charges remain labelled as billed', () => {
  const html = render({ cost_details: { items: [{ key: 'head', label: 'Kling', amount_usd: 1.08, kind: 'billed' }] } });
  assert.ok(html.includes('Списано'));
  assert.ok(html.includes('Подтверждённые расходы'));
  assert.ok(!html.includes('~$1.08'));
});

test('summary comes before charges and lengthy explanations are collapsed', () => {
  const html = render({ cost_details: { items: [
    { key: 'head', label: 'Генерация ведущего', amount_usd: 1.08, kind: 'estimate', details: '19.2 секунды по тарифу' },
  ], notes: ['Проверка списания недоступна'] } });
  assert.ok(html.indexOf('~$1.08') < html.indexOf('Генерация ведущего'));
  assert.ok(html.includes('Детали расчёта'));
  assert.ok(html.includes('<details'));
  assert.ok(!html.includes('<details open'));
});

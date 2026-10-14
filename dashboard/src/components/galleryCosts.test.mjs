import assert from 'node:assert/strict';
import { test } from 'node:test';

const costs = await import('./galleryCosts.js').catch((error) => {
  if (error.code === 'ERR_MODULE_NOT_FOUND') return {};
  throw error;
});

function summary(video) {
  assert.equal(typeof costs.galleryCostSummary, 'function', 'Gallery cost summary must be implemented');
  return costs.galleryCostSummary(video);
}

test('legacy costs retain their saved total and readable line items', () => {
  const result = summary({ cost_estimate: {
    voiceover_elevenlabs: 0.009, sliced_avatar_kling_standard: 0.67,
    sliced_broll_kling_v3_standard: 0.76, ffmpeg_compositing: 0, total: 1.44,
  } });
  assert.equal(result.total, 1.44);
  assert.equal(result.totalText, '~$1.44');
  assert.equal(result.items.length, 4);
  assert.equal(result.items[0].label, 'Озвучка · ElevenLabs');
  assert.equal(result.items[3].amount_usd, 0);
  assert.ok(result.items.every((item) => item.kind === 'estimate'));
});

test('missing costs are not interpreted as a free generation', () => {
  const result = summary({});
  assert.equal(result.total, null);
  assert.equal(result.totalText, 'Нет данных');
  assert.equal(result.complete, false);
});

test('zero is a valid saved estimate', () => {
  const result = summary({ cost_estimate: { ffmpeg_compositing: 0, total: 0 } });
  assert.equal(result.total, 0);
  assert.equal(result.totalText, '~$0.00');
  assert.equal(result.complete, true);
});

test('confirmed charges are distinct from estimates', () => {
  const result = summary({ cost_details: { items: [
    { key: 'head', label: 'Kling', amount_usd: 1.0772, kind: 'billed' },
    { key: 'voice', label: 'Anna', amount_usd: 0.02, kind: 'billed' },
    { key: 'broll', label: 'B-roll', amount_usd: 0, kind: 'reused' },
  ] } });
  assert.equal(result.totalText, '$1.10');
  assert.equal(result.totalLabel, 'Подтверждённые расходы');
  assert.equal(result.complete, true);
});

test('unknown voice price prevents claiming a full dollar total', () => {
  const result = summary({ cost_details: { items: [
    { key: 'head', label: 'Kling', amount_usd: 1.07904, kind: 'estimate' },
    { key: 'voice', label: 'Anna V4', amount_usd: null, kind: 'unknown', details: '269 символов' },
    { key: 'broll', label: 'B-roll', amount_usd: 0, kind: 'reused' },
  ] }, cost_estimate: { total: 42 } });
  assert.equal(result.totalText, '~$1.08 + неизвестная часть');
  assert.equal(result.compactText, '~$1.08 + ?');
  assert.equal(result.totalLabel, 'Известная часть');
  assert.equal(result.complete, false);
  assert.equal(result.items[1].amount_usd, null);
});

test('invalid, empty and negative values never become dollar charges', () => {
  const result = summary({ cost_estimate: {
    a: null, b: '', c: 'bad', d: Infinity, e: -5, f: false, total: 'bad',
  } });
  assert.equal(result.total, null);
  assert.equal(result.complete, false);
  assert.ok(result.items.every((item) => item.amount_usd === null));
});

test('numeric strings are supported without mutating metadata', () => {
  const video = { cost_estimate: { voiceover_elevenlabs: '0.03', total: '0.03' } };
  assert.equal(summary(video).totalText, '~$0.03');
  assert.equal(video.cost_estimate.voiceover_elevenlabs, '0.03');
});

test('a saved total alone is shown without invented line items', () => {
  const result = summary({ cost_estimate: { total: 2.31 } });
  assert.equal(result.totalText, '~$2.31');
  assert.equal(result.items.length, 0);
  assert.equal(result.complete, true);
});

test('an unclassified amount cannot be labelled as a confirmed payment', () => {
  const result = summary({ cost_details: { items: [
    { key: 'head', label: 'Kling', amount_usd: 1 },
  ] } });
  assert.equal(result.totalText, '~$1.00');
  assert.equal(result.items[0].kind, 'estimate');
});

test('unknown amounts stay unknown even if marked billed or reused', () => {
  const result = summary({ cost_details: { items: [
    { key: 'head', label: 'Kling', kind: 'billed', amount_usd: null },
    { key: 'broll', label: 'B-roll', kind: 'reused' },
  ] } });
  assert.equal(result.total, null);
  assert.equal(result.totalText, 'Нет данных');
  assert.ok(result.items.every((item) => item.kind === 'unknown'));
});

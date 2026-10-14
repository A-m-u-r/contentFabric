import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

let server;
let mergeContentPlans;
let contentPlanItemProgress;

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true },
  });
  ({ mergeContentPlans, contentPlanItemProgress } = await server.ssrLoadModule('/src/components/ContentPlanTab.jsx'));
});

after(async () => server?.close());

test('server plan restores approved scripts and preserves unrelated local items', () => {
  const local = { items: [{ item_id: 'old', title: 'Старый' }], done: { old: true } };
  const remote = { items: [{ item_id: 'reel-1', full_narration: '[curious] Привет.' }], done: { 'reel-1': false } };
  const merged = mergeContentPlans(local, remote);
  assert.deepEqual(merged.items.map((item) => item.item_id), ['reel-1', 'old']);
  assert.equal(merged.items[0].full_narration, '[curious] Привет.');
  assert.deepEqual(merged.done, { old: true, 'reel-1': false });
});

test('server checkbox wins for shared item when loading from account', () => {
  const local = { items: [{ item_id: 'reel-1' }], done: { 'reel-1': false } };
  const remote = { items: [{ item_id: 'reel-1' }], done: { 'reel-1': true } };
  assert.equal(mergeContentPlans(local, remote).done['reel-1'], true);
});

test('legacy numeric checkbox remains attached to its original local item', () => {
  const local = { items: [{ item_id: 'old', title: 'Старый' }], done: { 0: true } };
  const remote = { items: [{ item_id: 'reel-1', title: 'Новый' }], done: {} };
  const merged = mergeContentPlans(local, remote);
  assert.equal(merged.done.old, true);
  assert.equal(merged.done['reel-1'], undefined);
});

test('ready video automatically completes a plan item without manual checkbox', () => {
  assert.equal(typeof contentPlanItemProgress, 'function');
  const remote = { revision: 5, stage: 'video', video: {
    video_url: '/videos/saas_job/latest.mp4', filename: 'latest.mp4', duration: 18.9,
    download_url: '/api/user/content-workspaces/profile/item/video',
  } };
  const progress = contentPlanItemProgress(null, remote, false);
  assert.equal(progress.done, true);
  assert.equal(progress.video.filename, 'latest.mp4');
});

test('server availability and latest gallery edit win over stale local video', () => {
  assert.equal(typeof contentPlanItemProgress, 'function');
  const local = { revision: 6, stage: 'video', result: { video_url: '/videos/saas_job/old.mp4' } };
  const remote = { revision: 5, stage: 'video', video: null };
  const progress = contentPlanItemProgress(local, remote, false);
  assert.equal(progress.done, false);
  assert.equal(progress.video, null);
});

test('manual completion is preserved without inventing a download', () => {
  assert.equal(typeof contentPlanItemProgress, 'function');
  const progress = contentPlanItemProgress(null, { stage: 'script', video: null }, true);
  assert.equal(progress.done, true);
  assert.equal(progress.video, null);
});

test('offline completed local workspace still supplies its saved video', () => {
  assert.equal(typeof contentPlanItemProgress, 'function');
  const progress = contentPlanItemProgress({ genStatus: 'completed', stage: 'video',
    genResult: { video_url: '/videos/saas_job/final.mp4', duration: 19 } }, null, false);
  assert.equal(progress.done, true);
  assert.equal(progress.video.video_url, '/videos/saas_job/final.mp4');
});

test('processing draft with no rendered file is not completed', () => {
  assert.equal(typeof contentPlanItemProgress, 'function');
  assert.equal(contentPlanItemProgress({ stage: 'frames', genStatus: 'processing' }, null, false).done, false);
});

import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { mergeProjectMetadata } from '../lib/businessProfiles.js';

let server;
let ProjectsTab;
let prepareProjectSave;

const presenter = { actor_url: '/videos/actor_uploads/avatar.png', voice_id: 'voice-1', voice_name: 'Виктория' };

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true, hmr: false },
  });
  ({ default: ProjectsTab, prepareProjectSave } = await server.ssrLoadModule('/src/components/ProjectsTab.jsx'));
});

after(async () => server?.close());

test('editing an account project keeps its presenter and scenario settings', () => {
  assert.equal(typeof prepareProjectSave, 'function');
  const existing = {
    id: 'project-1', name: 'Старое название', presenter, created_at: '2026-10-01',
    script_mode: 'custom', text_model: 'pro', style: 'educational', custom_metadata: 'keep',
  };
  const draft = {
    name: ' Новое название ', description: ' Описание ', topic: '', language: 'ru',
    actorGender: 'female', scriptFormat: 'storyboard_v3',
  };

  const { profile, payload } = prepareProjectSave(draft, existing, existing.id);

  assert.equal(profile.name, 'Новое название');
  assert.deepEqual(profile.presenter, presenter);
  assert.equal(profile.custom_metadata, 'keep');
  assert.equal(payload.script_mode, 'custom');
  assert.equal(payload.text_model, 'pro');
  assert.equal(payload.style, 'educational');
  assert.equal(Object.hasOwn(payload, 'presenter'), false, 'account updates leave the server preset authoritative');

  const { payload: initialPayload } = prepareProjectSave(draft, { presenter }, 'local-1');
  assert.deepEqual(initialPayload.presenter, presenter, 'first account save carries a local presenter');
});

test('a project card shows the saved avatar and voice', () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key) => key === 'saasshorts_business_profiles' ? JSON.stringify([{ id: 'project-1', name: 'Проект', presenter }]) : null,
  } });
  let html;
  try {
    html = renderToStaticMarkup(createElement(ProjectsTab));
  } finally {
    if (previous) Object.defineProperty(globalThis, 'localStorage', previous);
    else delete globalThis.localStorage;
  }

  assert.match(html, /avatar\.png/);
  assert.match(html, /Виктория/);
});

test('account refresh retains local metadata while honoring server presenter updates', () => {
  assert.equal(typeof mergeProjectMetadata, 'function');
  const local = [{
    id: 'project-1', name: 'Предыдущее название', presenter, targetDurationSeconds: 30,
    actorGender: 'male', scriptMode: 'custom', scriptFormat: 'ugc', textModel: 'fast',
  }];
  const remote = [{
    id: 'project-1', name: 'Текущее название', presenter: null,
    actor_gender: 'female', script_mode: 'ai', script_format: 'storyboard_v3', text_model: 'pro',
  }];

  assert.deepEqual(mergeProjectMetadata(remote, local), [
    { ...remote[0], targetDurationSeconds: 30 },
  ]);
});

test('account refresh can retain browser-only projects without reviving deleted account projects', () => {
  const browserOnly = { id: 'local-1', name: 'Локальный проект', presenter };
  const deletedAccount = { id: 'server-1', name: 'Удалённый проект', created_at: '2026-10-01' };
  const local = [browserOnly, deletedAccount];

  assert.deepEqual(mergeProjectMetadata([], local, { includeLocalOnly: true }), [browserOnly]);
  assert.deepEqual(mergeProjectMetadata([], local), []);
});

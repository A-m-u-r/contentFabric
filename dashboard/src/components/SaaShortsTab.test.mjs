import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server;
let buildSaaSAnalyzeHeaders;
let isManualStoryboardImport;
let elevenLabsTtsSettings;
let contentPlanScriptDefaults;
let videoPrefsForContentItem;
let initializeGenerationPreferences;
let generationPresetPreferences;
let generationSpeech;
let SaaShortsTab;

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true, hmr: false },
  });
  ({ default: SaaShortsTab, buildSaaSAnalyzeHeaders, isManualStoryboardImport, elevenLabsTtsSettings, contentPlanScriptDefaults, videoPrefsForContentItem, initializeGenerationPreferences, generationPresetPreferences, generationSpeech } = await server.ssrLoadModule('/src/components/SaaShortsTab.jsx'));
});

after(async () => server?.close());

function renderSavedShorts(snapshot, props = {}) {
  const saved = JSON.stringify({ version: 2, timestamp: Date.now(), ...snapshot });
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key) => key === 'saasshorts_cache' ? saved : null,
  } });
  try {
    return renderToStaticMarkup(createElement(SaaShortsTab, props));
  } finally {
    if (previous) Object.defineProperty(globalThis, 'localStorage', previous);
    else delete globalThis.localStorage;
  }
}

test('a saved storyboard shows the ordered shots with one preview and editable reply', () => {
  const html = renderSavedShorts({ step: 2, scripts: [{
    format: 'storyboard_v3', title: 'Ужин', shots: [
      { shot_number: 1, speech: 'Первый кадр', scene: 'Кухня', start: 0, end: 4 },
      { shot_number: 2, speech: 'Второй кадр', scene: 'Тарелка', start: 4, end: 16 },
    ],
  }] }, { falKey: '__saved__' });
  assert.ok(html.includes('data-storyboard-editor'), 'saved storyboard should open the dedicated editor');
  assert.equal((html.match(/data-storyboard-shot=/g) || []).length, 2);
  assert.ok(html.includes('data-storyboard-timeline'));
  assert.equal((html.match(/data-timeline-clip=/g) || []).length, 2);
  assert.match(html, /aria-label="Позиция на таймлайне"/);
  assert.match(html, /grid-template-columns:25% 75%/);
  assert.ok(html.includes('aria-label="Предпросмотр"'));
  assert.match(html, /<textarea[^>]*>Первый кадр<\/textarea>/);
  assert.doesNotMatch(html, /<textarea[^>]*>Второй кадр<\/textarea>/);
});

test('the storyboard uses saved cut times only while the preview matches the current shots', () => {
  const shots = [
    { speech: 'Первый кадр', start: 0, end: 4, timeline_start: 0, timeline_end: 2 },
    { speech: 'Второй кадр', start: 4, end: 8, timeline_start: 2, timeline_end: 8 },
  ];
  const script = { format: 'storyboard_v3', title: 'Ужин', shots,
    _source_video_url: '/preview.mp4', _render_baseline: shots };
  const render = (data) => renderSavedShorts({ step: 2, scripts: [data] }, { falKey: '__saved__' });
  const saved = render(script);
  assert.match(saved, /<video [^>]*src="[^"]*\/preview\.mp4"/);
  assert.match(saved, /grid-template-columns:25% 75%/);
  const edited = render({ ...script, shots: [{ ...shots[0], speech: 'Новая реплика' }, shots[1]] });
  assert.doesNotMatch(edited, /<video [^>]*src="[^"]*\/preview\.mp4"/);
  assert.match(edited, /grid-template-columns:50% 50%/);
});

test('the storyboard warns when spoken length misses the brief target', () => {
  const snapshot = { step: 2, scriptMode: 'ai', targetDurationSeconds: 15, scripts: [{
    format: 'storyboard_v3', title: 'Ужин', shots: [{ speech: 'Короткая реплика', scene: 'Кухня', start: 0, end: 15 }],
  }] };
  const props = { falKey: '__saved__', elevenLabsKey: '__saved__' };
  assert.match(renderSavedShorts(snapshot, props), /Сценарий короче цели на 10 с/);
  assert.doesNotMatch(renderSavedShorts({ ...snapshot, scriptMode: 'custom' }, props), /короче цели/);
});

test('brief displays the current step and explains a missing key beside its action', () => {
  const html = renderSavedShorts({ step: 0 });
  assert.match(html, /data-shorts-workflow="0"/);
  assert.match(html, /data-shorts-studio="true"/);
  assert.match(html, /class="shorts-workflow__next-step".*?Написать сценарии.*?data-shorts-api-note/);
  assert.match(html, /aria-current="step"/);
  assert.match(html, /data-shorts-setup/);
  assert.match(html, /data-shorts-api-note/);
});

test('manual storyboard import keeps the keyless path available', () => {
  const html = renderSavedShorts({ step: 0, scriptMode: 'custom', scriptFormat: 'storyboard_v3',
    customScript: '## КАДР 1 — 0:00–0:04\nОна говорит: Привет',
  });
  assert.match(html, /data-shorts-setup/);
  const importButton = html.match(/<button[^>]*>Импортировать раскадровку<\/button>/)?.[0];
  assert.ok(importButton);
  assert.doesNotMatch(importButton, /\bdisabled\b/);
  assert.doesNotMatch(html, /data-shorts-api-note/);
});

test('the script review exposes its choices separately from the selected scenario', () => {
  const html = renderSavedShorts({ step: 1, analysis: { product_name: 'Ужин' }, selectedScript: 1, scripts: [
    { title: 'Первый вариант', format: 'storyboard_v3', shots: [{ speech: 'Первая реплика' }] },
    { title: 'Второй вариант', format: 'storyboard_v3', shots: [{ speech: 'Вторая реплика' }] },
  ] });
  assert.match(html, /data-shorts-workflow="1"/);
  assert.match(html, /data-shorts-studio="true"/);
  assert.match(html, /<header class="shorts-workflow__studio-header">.*?К раскадровке.*?<\/header>/);
  assert.equal((html.match(/data-shorts-script-option=/g) || []).length, 2);
  assert.match(html, /data-shorts-script-detail/);
  assert.match(html, /Вторая реплика/);
  assert.doesNotMatch(html, /Первая реплика/);
  assert.match(html, /К раскадровке/);
});

test('calm preview comparison uses spoken text, not removed acting tags', () => {
  const tagged = '[whispers] Привет. [curious] Как дела?';
  assert.equal(generationSpeech(tagged, 'calm_ugc'), 'Привет. Как дела?');
  assert.equal(generationSpeech(tagged, 'expressive'), tagged);
  assert.equal(generationSpeech('Артикул [123].', 'calm_ugc'), 'Артикул [123].');
});

test('only authored storyboard headers bypass AI direction', () => {
  assert.equal(isManualStoryboardImport('custom', 'storyboard_v3', '[curious] Твой план работает?'), false);
  assert.equal(isManualStoryboardImport('custom', 'storyboard_v3', '## КАДР 1 — 0:00–0:04\nОна говорит: Привет'), true);
  assert.equal(isManualStoryboardImport('custom', 'storyboard_v3', 'SHOT 1\nSpeech: Hello'), true);
  assert.equal(isManualStoryboardImport('ai', 'storyboard_v3', 'КАДР 1'), false);
  assert.equal(isManualStoryboardImport('custom', 'ugc', 'КАДР 1'), false);
  assert.equal(isManualStoryboardImport('custom', 'storyboard_v3', 'Посмотри на кадр 1, а затем продолжай.'), false);
});

test('analyze headers send user-owned Gemini and fal.ai keys', () => {
  assert.equal(typeof buildSaaSAnalyzeHeaders, 'function');
  assert.deepEqual(
    buildSaaSAnalyzeHeaders({
      baseHeaders: { 'Content-Type': 'application/json', Authorization: 'Bearer auth' },
      geminiApiKey: 'gemini-key',
      falKey: 'fal-key',
      isManagedKey: () => false,
    }),
    {
      'Content-Type': 'application/json',
      Authorization: 'Bearer auth',
      'X-Gemini-Key': 'gemini-key',
      'X-Fal-Key': 'fal-key',
    },
  );
});

test('analyze headers keep saved and platform key markers on the server', () => {
  const headers = buildSaaSAnalyzeHeaders({
    baseHeaders: { 'Content-Type': 'application/json' },
    geminiApiKey: '__saved__',
    falKey: '__platform__',
    isManagedKey: (value) => value === '__saved__' || value === '__platform__',
  });

  assert.deepEqual(headers, { 'Content-Type': 'application/json' });
});

test('v4 settings are sent with all generation requests, v3 remains unchanged', () => {
  assert.deepEqual(elevenLabsTtsSettings('eleven_v4', 0.35, 0.9), {
    elevenlabs_model: 'eleven_v4',
    elevenlabs_stability: 0.35,
    elevenlabs_similarity: 0.9,
  });
  assert.deepEqual(elevenLabsTtsSettings('eleven_v3', 0.35, 0.9), {
    elevenlabs_model: 'eleven_v3',
  });
});

test('content plan narration opens as exact authored text for AI direction', () => {
  const item = { full_narration: '[curious] Привет. [exhales] Продолжение.' };
  assert.deepEqual(contentPlanScriptDefaults(item), {
    scriptMode: 'custom',
    scriptFormat: 'storyboard_v3',
    customScript: item.full_narration,
  });
});

test('new approved voice preset replaces old v3 once but keeps later manual choices', () => {
  const item = {
    voice_id: 'anna', voice_name: 'Anna', elevenlabs_model: 'eleven_v4',
    elevenlabs_stability: 0.5, elevenlabs_similarity: 0.75,
    voice_preset_version: 'anna-v4-base-20260930',
  };
  const old = { selectedVoice: 'victoria', elevenLabsModel: 'eleven_v3' };
  const updated = videoPrefsForContentItem(item, old);
  assert.equal(updated.selectedVoice, 'anna');
  assert.equal(updated.elevenLabsModel, 'eleven_v4');
  assert.equal(updated.elevenLabsStability, 0.5);
  assert.deepEqual(
    videoPrefsForContentItem(item, { ...updated, selectedVoice: 'other' }).selectedVoice,
    'other',
  );
});

test('normal generation initializes the approved calm recipe without replacing voice identity', () => {
  assert.equal(typeof initializeGenerationPreferences, 'function');
  const prefs = initializeGenerationPreferences({ selectedVoice: 'anna', elevenLabsModel: 'eleven_v3' });
  assert.equal(prefs.generationPreset, 'calm_ugc');
  assert.equal(prefs.selectedVoice, 'anna');
  assert.equal(prefs.elevenLabsModel, 'eleven_v4');
  assert.equal(prefs.elevenLabsStability, 0.65);
  assert.equal(prefs.elevenLabsSimilarity, 0.75);
  assert.equal(prefs.backgroundMusic, true);
  assert.equal(prefs.storyboardGenerationMode, 'sliced_avatar');
  assert.equal(prefs.videoMode, 'storyboard_v3_standard');
});

test('calm defaults migrate once, subsequent manual settings survive refresh', () => {
  assert.equal(typeof initializeGenerationPreferences, 'function');
  const prefs = initializeGenerationPreferences({ selectedVoice: 'anna' });
  const manual = { ...prefs, selectedVoice: 'custom', elevenLabsStability: 0.4, backgroundMusic: false };
  assert.deepEqual(initializeGenerationPreferences(manual), manual);
});

test('expressive choice survives reload instead of silently enabling calm mode', () => {
  assert.equal(typeof initializeGenerationPreferences, 'function');
  const prefs = { generationPreset: 'expressive', elevenLabsModel: 'eleven_v3', elevenLabsStability: 0.5 };
  assert.deepEqual(initializeGenerationPreferences(prefs), prefs);
});

test('applying calm preset keeps selected avatar and account-owned voice', () => {
  assert.equal(typeof generationPresetPreferences, 'function');
  const prefs = generationPresetPreferences('calm_ugc', { selectedVoice: 'mine', selectedActor: '/my.png', plateUrls: { front: '/front.png' } });
  assert.equal(prefs.selectedVoice, 'mine');
  assert.equal(prefs.selectedActor, '/my.png');
  assert.deepEqual(prefs.plateUrls, { front: '/front.png' });
  assert.equal(prefs.elevenLabsStability, 0.65);
});

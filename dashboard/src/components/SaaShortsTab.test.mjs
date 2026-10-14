import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
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

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true },
  });
  ({ buildSaaSAnalyzeHeaders, isManualStoryboardImport, elevenLabsTtsSettings, contentPlanScriptDefaults, videoPrefsForContentItem, initializeGenerationPreferences, generationPresetPreferences, generationSpeech } = await server.ssrLoadModule('/src/components/SaaShortsTab.jsx'));
});

after(async () => server?.close());

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

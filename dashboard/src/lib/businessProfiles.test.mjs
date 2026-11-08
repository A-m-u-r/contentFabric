import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as profiles from './businessProfiles.js';

test('project presenter round trip retains avatar angles and an explicitly chosen voice', () => {
  const prefs = { selectedActor: '/gallery/actor.png', selectedFace: '/gallery/face.png',
    plateUrls: { side: '/gallery/side.png' }, selectedVoice: 'custom-voice', selectedVoiceName: 'Мой голос',
    ttsProvider: 'elevenlabs', elevenLabsModel: 'eleven_v4', elevenLabsStability: 0,
    elevenLabsSimilarity: 0.8, minimaxVoice: 'Russian_AmbitiousWoman' };
  const presenter = profiles.presenterFromPreferences(prefs);
  const restored = profiles.preferencesFromPresenter(presenter);
  for (const [key, value] of Object.entries(prefs)) assert.deepEqual(restored[key], value, key);
  assert.equal(restored.voiceSelectionSource, 'manual');
  assert.equal(restored.uploadedActorUrl, '', 'a previous draft upload must not override the saved avatar');
});

test('older projects preserve draft choices while explicit removal clears the presenter', () => {
  assert.deepEqual(profiles.preferencesFromPresenter(undefined), {});
  const cleared = profiles.preferencesFromPresenter(null);
  assert.equal(cleared.selectedActor, '');
  assert.equal(cleared.selectedFace, '');
  assert.deepEqual(cleared.plateUrls, {});
  assert.equal(cleared.voiceSelectionSource, 'default');
});

test('saving without an avatar explicitly clears it and never stores a browser-only image URL', () => {
  const presenter = profiles.presenterFromPreferences({ selectedActor: 'blob:temporary',
    selectedFace: null, plateUrls: { front: 'data:image/png;base64,private', side: '/gallery/saved.png' },
    selectedVoice: 'voice', selectedVoiceName: 'Voice', ttsProvider: 'fal_minimax', minimaxVoice: 'Russian_Voice' });
  assert.equal(presenter.actor_url, null);
  assert.deepEqual(presenter.plate_urls, { side: '/gallery/saved.png' });
  assert.equal(profiles.preferencesFromPresenter(presenter).minimaxVoice, 'Russian_Voice');
});

test('MiniMax display name is not reused as the name of the hidden ElevenLabs voice', () => {
  const prefs = profiles.preferencesFromPresenter({ tts_provider: 'fal_minimax', voice_id: 'eleven-id',
    voice_name: 'MiniMax — Анна', minimax_voice_id: 'Russian_Anna' });
  assert.equal(prefs.selectedVoiceName, '');
  assert.equal(prefs.selectedVoice, 'eleven-id');
});

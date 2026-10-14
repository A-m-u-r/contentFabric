import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

let server;
let musicRequestSettings;
let musicPreferencesFromVideo;

before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom', server: { middlewareMode: true, hmr: false } });
  ({ musicRequestSettings, musicPreferencesFromVideo } = await server.ssrLoadModule('/src/components/MusicPicker.jsx'));
});
after(async () => server?.close());

test('music choices serialize without changing speech or image inputs', () => {
  assert.deepEqual(musicRequestSettings(true, 'warm_groove_104.wav', .8), {
    background_music: true, music_track: 'warm_groove_104.wav', music_volume: .8,
  });
});

test('saved disabled music and zero volume survive reopening', () => {
  assert.deepEqual(musicPreferencesFromVideo({ background_music: false, music_track: 'light_pulse_96.wav', music_volume: 0 }), {
    backgroundMusic: false, musicTrack: 'light_pulse_96.wav', musicVolume: 0,
  });
  assert.deepEqual(musicPreferencesFromVideo({}), { backgroundMusic: true, musicTrack: 'auto', musicVolume: 1 });
});

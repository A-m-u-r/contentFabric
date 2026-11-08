import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { access, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server;
let playerModule;

before(async () => {
  const componentExists = await access(new URL('./MediaPlayer.jsx', import.meta.url)).then(() => true, () => false);
  assert.equal(componentExists, true, 'the shared custom media player is not implemented');
  server = await createServer({ root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom', server: { middlewareMode: true, hmr: false } });
  playerModule = await server.ssrLoadModule('/src/components/MediaPlayer.jsx');
});
after(async () => server?.close());

test('audio renders branded controls, not the browser control bar', () => {
  const html = renderToStaticMarkup(React.createElement(playerModule.default,
    { kind: 'audio', src: '/voice.wav', label: 'Озвучка ролика' }));
  assert.match(html, /<audio/);
  assert.doesNotMatch(html, /\scontrols(?:=|\s|>)/);
  assert.match(html, /data-media-player="audio"/);
  assert.match(html, /aria-label="Воспроизвести озвучку"/);
  assert.match(html, /aria-label="Позиция воспроизведения"/);
  assert.match(html, /aria-label="Выключить звук"/);
});

test('video retains the source and poster and exposes custom fullscreen', () => {
  const html = renderToStaticMarkup(React.createElement(playerModule.default,
    { src: '/result.mp4', poster: '/cover.png', label: 'Готовый ролик', className: 'aspect-video', mediaClassName: 'object-contain' }));
  assert.match(html, /<video[^>]+src="\/result.mp4"/);
  assert.match(html, /poster="\/cover.png"/);
  assert.match(html, /aria-label="Готовый ролик"/);
  assert.match(html, /aria-label="На весь экран"/);
  assert.match(html, /object-contain/);
  assert.doesNotMatch(html, /\scontrols(?:=|\s|>)/);
});

test('missing or disabled media cannot start playback', () => {
  for (const props of [{}, { src: '/voice.wav', disabled: true }]) {
    const html = renderToStaticMarkup(React.createElement(playerModule.default, { kind: 'audio', ...props }));
    assert.match(html, /<button[^>]*disabled=""[^>]*aria-label="Воспроизвести озвучку"/);
    assert.match(html, /aria-disabled="true"/);
  }
});

test('display time is predictable for metadata gaps and hour-long media', () => {
  const { formatMediaTime } = playerModule;
  assert.equal(formatMediaTime(undefined), '0:00');
  assert.equal(formatMediaTime(Infinity), '0:00');
  assert.equal(formatMediaTime(-12), '0:00');
  assert.equal(formatMediaTime(65.9), '1:05');
  assert.equal(formatMediaTime(3723), '1:02:03');
});

test('seek bounds cannot exceed real duration', () => {
  const { clampMediaTime } = playerModule;
  assert.equal(clampMediaTime(-10, 30), 0);
  assert.equal(clampMediaTime(100, 30), 30);
  assert.equal(clampMediaTime(12, 30), 12);
  assert.equal(clampMediaTime(12, NaN), 0);
});

test('keyboard playback and seek shortcuts ignore nested controls', () => {
  const { mediaKeyboardAction } = playerModule;
  assert.deepEqual(mediaKeyboardAction(' ', 'DIV', 12, 30), { type: 'toggle' });
  assert.deepEqual(mediaKeyboardAction('ArrowRight', 'VIDEO', 28, 30), { type: 'seek', time: 30 });
  assert.deepEqual(mediaKeyboardAction('ArrowLeft', 'DIV', 3, 30), { type: 'seek', time: 0 });
  assert.deepEqual(mediaKeyboardAction('m', 'DIV', 3, 30), { type: 'mute' });
  assert.equal(mediaKeyboardAction(' ', 'BUTTON', 12, 30), null);
  assert.equal(mediaKeyboardAction('ArrowRight', 'INPUT', 12, 30), null);
  assert.equal(mediaKeyboardAction('x', 'DIV', 12, 30), null);
});

test('voice, music, result and gallery views use the same custom player', async () => {
  for (const name of ['MusicPicker', 'SaaShortsTab', 'GalleryCard', 'ResultCard', 'UGCGallery', 'TranslateModal']) {
    const source = await readFile(new URL(`./${name}.jsx`, import.meta.url), 'utf8');
    assert.match(source, /import MediaPlayer from ['"]\.\/MediaPlayer['"]/, `${name} must share the player`);
    assert.doesNotMatch(source, /<(?:audio|video)\b[^>]*\bcontrols\b/s, `${name} still exposes a native player`);
  }
});

test('shared base styles do not override compact callers maximum width', async () => {
  const css = await readFile(new URL('./MediaPlayer.css', import.meta.url), 'utf8');
  const base = css.match(/\.cf-media-player\s*\{([^}]+)\}/)?.[1] || '';
  assert.doesNotMatch(base, /max-width\s*:/, 'caller sizing utilities must remain authoritative');
});

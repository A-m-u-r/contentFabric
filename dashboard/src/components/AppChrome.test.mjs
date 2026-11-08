import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server;
let GeminiKeyNotice;

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true, hmr: false },
  });
  ({ GeminiKeyNotice } = await server.ssrLoadModule('/src/App.jsx'));
});

after(async () => server?.close());

test('the Gemini notice leaves AI Shorts clear and offers settings to clip creators', () => {
  assert.equal(typeof GeminiKeyNotice, 'function', 'the shell should render a contextual notice');
  const renderNotice = (activeTab, hasKey = false) => renderToStaticMarkup(
    createElement(GeminiKeyNotice, { activeTab, hasKey, onOpenSettings() {} }),
  );

  assert.equal(renderNotice('saasshorts'), '');
  assert.equal(renderNotice('projects'), '');
  assert.equal(renderNotice('dashboard', true), '');
  assert.match(renderNotice('dashboard'), /API-ключ Gemini.*<button[^>]+>Настройки<\/button>/);
  assert.match(renderNotice('content-plan'), /API-ключ Gemini/);
});

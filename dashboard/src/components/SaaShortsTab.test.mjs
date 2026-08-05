import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

let server;
let buildSaaSAnalyzeHeaders;

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true },
  });
  ({ buildSaaSAnalyzeHeaders } = await server.ssrLoadModule('/src/components/SaaShortsTab.jsx'));
});

after(async () => server?.close());

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

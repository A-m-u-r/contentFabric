import assert from 'node:assert/strict';
import test from 'node:test';

let galleryVideoModeBadge;
let importError;

try {
  ({ galleryVideoModeBadge } = await import('./videoModeBadge.js'));
} catch (error) {
  importError = error;
}

test('storyboard Pro metadata renders a Pro gallery badge', () => {
  assert.equal(
    typeof galleryVideoModeBadge,
    'function',
    `gallery badge mapper is unavailable: ${importError?.message || 'unknown error'}`,
  );
  assert.deepEqual(galleryVideoModeBadge('storyboard_v3_pro'), {
    label: 'PRO',
    className: 'bg-violet-500 text-white',
  });
});

test('storyboard Standard and Veo metadata keep distinct gallery badges', () => {
  assert.equal(typeof galleryVideoModeBadge, 'function');
  assert.deepEqual(galleryVideoModeBadge('storyboard_v3_standard'), {
    label: 'STANDARD',
    className: 'bg-blue-500 text-white',
  });
  assert.deepEqual(galleryVideoModeBadge('storyboard_veo31_quality'), {
    label: 'VEO 3.1',
    className: 'bg-amber-500 text-black',
  });
});

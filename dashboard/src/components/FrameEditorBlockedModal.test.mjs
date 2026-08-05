import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

let server;
let Modal;

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../..', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true },
  });
  ({ default: Modal } = await server.ssrLoadModule('/src/components/FrameEditorBlockedModal.jsx'));
});

after(async () => server?.close());

function elements(node, found = []) {
  if (!node || typeof node !== 'object') return found;
  found.push(node);
  const children = node.props?.children;
  for (const child of (Array.isArray(children) ? children : [children])) {
    elements(child, found);
  }
  return found;
}

test('render and close never select a paid model; enabled click selects exactly once', () => {
  const picked = [];
  let closed = 0;
  const onClose = () => { closed += 1; };
  const tree = Modal({
    block: {
      model: 'current',
      title: 'Current',
      reason: 'blank',
      alternatives: [
        { id: 'next', title: 'Next', vendor: 'Vendor', note: '', blocked: false },
      ],
    },
    models: [
      { id: 'global', title: 'Global', vendor: 'Old catalog', note: '', blocked: false },
    ],
    onPick: (id) => picked.push(id),
    onClose,
  });

  assert.deepEqual(picked, []);
  const buttons = elements(tree).filter((node) => node.type === 'button');
  buttons.find((button) => button.props.onClick === onClose).props.onClick();
  assert.deepEqual(picked, []);
  assert.equal(closed, 1);
  const modelButton = buttons.find((button) => button.key === 'next');
  modelButton.props.onClick();
  assert.deepEqual(picked, ['next']);
});

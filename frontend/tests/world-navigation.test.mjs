import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MantineProvider } from '@mantine/core';
import { createServer } from 'vite';

test('World initially presents Explore before Connections', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  try {
    const { WorldWorkspace } = await server.ssrLoadModule('/src/views/WorldWorkspace.jsx');
    const html = renderToStaticMarkup(React.createElement(MantineProvider, {},
      React.createElement(WorldWorkspace, { active: true, apiGet: async () => ({}), state: { data: null, loading: true } })));
    assert.ok(html.indexOf('>Explore<') < html.indexOf('>Connections<'));
    assert.match(html, /checked="" value="explore"/);
    assert.match(html, /Minimum evidence strength/);
  } finally { await server.close(); }
});

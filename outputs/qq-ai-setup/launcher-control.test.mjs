import test from 'node:test';
import assert from 'node:assert/strict';
import { bridgeStatus } from './launcher-control.mjs';

test('readiness exports no account, settings, or credential fields', async () => {
  let calls = 0;
  const result = await bridgeStatus(async (url, options) => {
    calls++;
    if (url.endsWith('/')) return { ok: true, text: async () => "QQ AI const token='fixture-nonce';" };
    assert.equal(options.headers['x-setup-token'], 'fixture-nonce');
    return { ok: true, json: async () => ({
      session: { status: 'connected', sharing: true, identity: 'private-fixture', token: 'secret-fixture' },
      setup: { botQQ: 'private-fixture' }, modelPause: { paused: false },
    }) };
  });
  assert.equal(calls, 2);
  assert.deepEqual(result, { ready: true, planPaused: false, signInPending: false });
  assert(!JSON.stringify(result).includes('fixture'));
});

test('a different service on the port is not used as the local setup page', async () => {
  let calls = 0;
  const result = await bridgeStatus(async () => {
    calls++;
    return { ok: true, text: async () => 'Another app without the local nonce' };
  });
  assert.equal(calls, 1);
  assert.deepEqual(result, { ready: false });
});

test('login without plan sharing is not ready for startup', async () => {
  const result = await bridgeStatus(async url => url.endsWith('/')
    ? { ok: true, text: async () => "QQ AI const token='fixture';" }
    : { ok: true, json: async () => ({ session: { status: 'connected', sharing: false } }) });
  assert.equal(result.ready, false);
});

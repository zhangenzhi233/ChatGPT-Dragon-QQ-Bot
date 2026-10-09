// Local addition (2026-10-03). Same DevKit Noncommercial License as the repository.
// Synthetic streams and isolated encrypted fixtures only; no account login or network access.
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';
import { createChatGPT } from '../dist/index.js';
import { ConnectionStore } from '../dist/storage.js';
import { streamRawResponse } from '../dist/raw-responses.js';

const token = 'synthetic-raw-access-token';
const body = { model: 'test-model', input: [{ role: 'user', content: [{ type: 'input_image', image_url: 'data:image/png;base64,test' }] }], tools: [{ type: 'namespace', name: 'local', tools: [{ type: 'function', name: 'test', parameters: { type: 'object' } }] }] };
const native = { id: 'resp_test', object: 'response', status: 'completed', output: [{ type: 'function_call', name: 'test', arguments: '{}', call_id: 'call_test' }], usage: { input_tokens: 10, output_tokens: 1 } };
const completed = { type: 'response.completed', response: native };
const encode = (event, ending = '\n') => `data: ${JSON.stringify(event)}${ending}${ending}`;
const invoke = (options = {}) => streamRawResponse(token, { body, ...options }, options.signal ?? new AbortController().signal);
function mockStream(t, chunks, headers = { 'content-type': 'text/event-stream' }) {
  let index = 0;
  const stream = new ReadableStream({ pull(controller) { if (index === chunks.length) controller.close(); else controller.enqueue(new TextEncoder().encode(chunks[index++])); } });
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response(stream, { headers }));
  return mock;
}

test('preserves native images/tools/output, forces stream/store, fixes endpoint and disallows redirects', async (t) => {
  const fetch = mockStream(t, [encode(completed)]);
  assert.deepEqual(await invoke({ body: { ...body, store: true, stream: false, base_url: 'https://example.invalid' } }), native);
  const [url, request] = fetch.mock.calls[0].arguments;
  assert.equal(url, 'https://api.openai.com/v1/responses');
  assert.equal(request.redirect, 'error');
  assert.equal(request.headers.authorization, `Bearer ${token}`);
  const sent = JSON.parse(request.body);
  assert.equal(sent.store, false); assert.equal(sent.stream, true);
  assert.deepEqual(sent.input, body.input); assert.deepEqual(sent.tools, body.tools);
});

test('awaits async event consumers in order; completion callback cannot mutate returned response', async (t) => {
  const delta = { type: 'response.output_text.delta', delta: '你好' };
  mockStream(t, [encode(delta) + encode(completed)]);
  const events = [];
  const result = await invoke({ onEvent: async (event) => { await new Promise(resolve => setTimeout(resolve, 2)); events.push(event.type); if (event.response) event.response.output.length = 0; } });
  assert.deepEqual(events, [delta.type, completed.type]);
  assert.deepEqual(result, native);
});

test('rebuilds an empty completion summary from finished streamed output items', async (t) => {
  const finalItem = { type: 'function_call', name: 'vision_report', namespace: 'maibot', arguments: '{"color":"red"}', call_id: 'synthetic_call' };
  mockStream(t, [
    encode({ type: 'response.output_item.done', output_index: 0, item: finalItem }) +
    encode({ type: 'response.completed', response: { ...native, output: [] } }),
  ]);
  let forwardedCompletion;
  const result = await invoke({ onEvent(event) { if (event.type === 'response.completed') forwardedCompletion = event.response; } });
  assert.deepEqual(result.output, [finalItem]);
  assert.deepEqual(forwardedCompletion.output, [finalItem]);
});

for (const ending of ['\n', '\r\n', '\r']) {
  test(`handles split lines and final unterminated event: ${JSON.stringify(ending)}`, async (t) => {
    const text = `: keepalive${ending}${ending}` + encode(completed, ending).trimEnd();
    mockStream(t, [...text]);
    assert.deepEqual(await invoke(), native);
  });
}

for (const [stream, code] of [
  ['', 'stream_interrupted'],
  ['data: [DONE]\n\n', 'stream_interrupted'],
  ['data: bad-json\n\n', 'invalid_stream'],
  [encode({ type: 'response.completed' }), 'invalid_stream'],
  [encode({ type: 'response.completed', response: { ...native, status: 'in_progress' } }), 'invalid_stream'],
  [encode({ type: 'response.incomplete' }), 'response_incomplete'],
  [encode({ type: 'response.failed', response: { error: { code: 'subscription_sharing_usage_limit_exceeded', message: 'do not expose me' } } }), 'subscription_sharing_usage_limit_exceeded'],
  [encode({ type: 'error', code: 'invalid_request', message: 'do not expose me' }), 'invalid_request'],
  [encode({ type: 'response.output_text.delta', delta: token }), 'invalid_stream'],
]) {
  test(`rejects terminal/invalid stream (${code}, ${stream.length})`, async (t) => {
    mockStream(t, [stream]);
    const events = [];
    await assert.rejects(invoke({ onEvent: event => events.push(event) }), error => error.code === code && !JSON.stringify(error).includes(token) && !error.message.includes('do not expose me'));
    assert.equal(events.length, 0);
  });
}

test('cancels a pending read even when mocked transport does not observe signal', async (t) => {
  const controller = new AbortController();
  let ready;
  const waiting = new Promise(resolve => { ready = resolve; });
  t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({ pull() { ready(); } })));
  const promise = invoke({ signal: controller.signal });
  await waiting;
  controller.abort();
  await assert.rejects(promise, { code: 'cancelled' });
});

test('consumer error cancels transport and returns safe error', async (t) => {
  mockStream(t, [encode({ type: 'response.created' })]);
  await assert.rejects(invoke({ onEvent() { throw new Error('consumer-secret'); } }), error => error.code === 'stream_interrupted' && !error.message.includes('consumer-secret'));
});

test('caller cancellation interrupts a stalled async event consumer', async (t) => {
  const controller = new AbortController();
  let entered;
  const waiting = new Promise(resolve => { entered = resolve; });
  mockStream(t, [encode({ type: 'response.created' })]);
  const request = invoke({ signal: controller.signal, onEvent() { entered(); return new Promise(() => {}); } });
  await waiting;
  controller.abort();
  await assert.rejects(request, { code: 'cancelled' });
});

test('upstream credential reflection in error identifiers is not returned', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ error: { code: token, param: token } }, { status: 403, headers: { 'x-request-id': token } }));
  await assert.rejects(invoke(), error => error.status === 403 && !JSON.stringify(error).includes(token));
});

for (const status of [401, 403, 429, 503]) {
  test(`preserves safe HTTP ${status} diagnostics without forwarding upstream text`, async (t) => {
    t.mock.method(globalThis, 'fetch', async () => Response.json({ error: { message: token } }, { status, headers: { 'x-request-id': 'synthetic-request' } }));
    await assert.rejects(invoke(), error => error.status === status && error.requestId === 'synthetic-request' && !JSON.stringify(error).includes(token));
  });
}

test('rejects non-SSE response and oversized event', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('{}', { headers: { 'content-type': 'application/json' } }));
  await assert.rejects(invoke(), { code: 'invalid_stream' });
  mockStream(t, ['data: ' + 'x'.repeat(16 * 1024 * 1024 + 1)]);
  await assert.rejects(invoke(), { code: 'invalid_stream' });
});

test('invalid bodies fail before transport', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('unexpected network'));
  for (const invalid of [null, [], {}, { model: 'test', input: 'text' }, { model: '', input: [] }]) {
    await assert.rejects(invoke({ body: invalid }), { code: 'invalid_request' });
  }
  assert.equal(fetch.mock.callCount(), 0);
});

test('public client uses authentication gate and keeps credentials out of returned data', async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'siwc-raw-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const key = randomBytes(32);
  const provider = {
    id: 'raw-test-aes-gcm', isAvailable: () => true,
    encrypt(plain) { const iv = randomBytes(12), c = createCipheriv('aes-256-gcm', key, iv); return Buffer.concat([iv, c.update(plain, 'utf8'), c.final(), c.getAuthTag()]); },
    decrypt(value) { const bytes = Buffer.from(value), d = createDecipheriv('aes-256-gcm', key, bytes.subarray(0, 12)); d.setAuthTag(bytes.subarray(-16)); return Buffer.concat([d.update(bytes.subarray(12, -16)), d.final()]).toString('utf8'); },
  };
  const client = createChatGPT({ appName: 'Raw test', appId: 'raw-test', redirectPort: 0, storageDir: directory, credentialEncryption: provider });
  const fetch = mockStream(t, [encode(completed)]);
  await assert.rejects(client.streamRawResponse({ body }), { code: 'sign_in_required' });
  assert.equal(fetch.mock.callCount(), 0);
  const store = new ConnectionStore(directory, provider);
  await store.withLock(() => store.write({ version: 2, activeProfileId: 'test', pendingRegistrations: [], profiles: [{ version: 1, id: 'test', label: 'Test', clientId: 'test', status: 'connected', scopes: ['chatgpt.tokens.use.direct'], savedAt: new Date().toISOString(), credentials: { accessToken: token, expiresAt: Date.now() + 3600000 } }] }));
  const result = await client.streamRawResponse({ body });
  assert.deepEqual(result, native);
  assert.equal(JSON.stringify([result, await client.getSession(), await client.listProfiles()]).includes(token), false);
  assert.equal(Object.keys(client).some(key => /token|credential/i.test(key)), false);
});

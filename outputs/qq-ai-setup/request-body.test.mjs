import assert from 'node:assert/strict';
import test from 'node:test';
import { Readable } from 'node:stream';
import {
  BridgeBodyError,
  readJsonBody,
} from './request-body.mjs';
import { BridgeBodyBudget } from './bridge-limits.mjs';

const stream = chunks => Readable.from(chunks);

test('reads JSON split over transport chunks', async () => {
  const value = await readJsonBody(stream([Buffer.from('{"input":'), Buffer.from('["ok"]}')]), { maximumBytes: 32 });
  assert.deepEqual(value, { input: ['ok'] });
});

test('accepts a payload at the exact byte limit', async () => {
  const payload = Buffer.from('{"ok":true}');
  assert.deepEqual(await readJsonBody(stream([payload]), { maximumBytes: payload.length }), { ok: true });
});

test('counts UTF-8 bytes rather than JavaScript characters', async () => {
  const payload = Buffer.from('{"text":"银白龙😀"}');
  assert.deepEqual(await readJsonBody(stream([payload]), { maximumBytes: payload.length }), { text: '银白龙😀' });
  await assert.rejects(
    readJsonBody(stream([payload]), { maximumBytes: payload.length - 1 }),
    error => error instanceof BridgeBodyError && error.code === 'request_body_too_large' && error.status === 413,
  );
});

test('rejects an over-limit request with a classified 413 error', async () => {
  await assert.rejects(
    readJsonBody(stream([Buffer.from('{"a":1}')]), { maximumBytes: 6 }),
    error => error instanceof BridgeBodyError && error.code === 'request_body_too_large' && error.status === 413,
  );
});

test('rejects malformed JSON with a classified 400 error', async () => {
  await assert.rejects(
    readJsonBody(stream([Buffer.from('{"input":}')]), { maximumBytes: 64 }),
    error => error instanceof BridgeBodyError && error.code === 'invalid_json_body' && error.status === 400,
  );
});

test('accepts an image-history-scale 18.8 MB Responses payload under the configurable bridge limit', async () => {
  const payload = Buffer.from(JSON.stringify({ input_only_wire_bytes: 18_800_000, input: 'x'.repeat(18_800_000) }));
  assert(payload.length > 18_800_000);
  const maximumBytes = 256 * 1024 * 1024;
  assert(payload.length < maximumBytes);
  const midpoint = Math.floor(payload.length / 2);
  const value = await readJsonBody(stream([payload.subarray(0, midpoint), payload.subarray(midpoint)]), {
    maximumBytes,
  });
  assert.equal(value.input_only_wire_bytes, 18_800_000);
  assert.equal(Buffer.byteLength(value.input), 18_800_000);
});

test('shared body budget reports 429 and permits a later request after release', async () => {
  const budget = new BridgeBodyBudget(12);
  const first = budget.createReservation();
  assert.deepEqual(await readJsonBody(stream([Buffer.from('{"a":1}')]), { maximumBytes: 32, reservation: first }), { a: 1 });
  const second = budget.createReservation();
  await assert.rejects(
    readJsonBody(stream([Buffer.from('{"b":2}')]), { maximumBytes: 32, reservation: second }),
    error => error instanceof BridgeBodyError && error.code === 'request_body_budget_exhausted' && error.status === 429,
  );
  first.release();
  second.release();
  const retry = budget.createReservation();
  assert.deepEqual(await readJsonBody(stream([Buffer.from('{"c":3}')]), { maximumBytes: 32, reservation: retry }), { c: 3 });
  retry.release();
  assert.equal(budget.usedBytes, 0);
});

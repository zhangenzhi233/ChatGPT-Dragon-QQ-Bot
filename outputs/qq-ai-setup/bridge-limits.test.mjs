import assert from 'node:assert/strict';
import test from 'node:test';
import {
  BridgeBodyBudget,
  BridgeLimitsError,
  DEFAULT_BRIDGE_LIMITS,
  parseBridgeLimits,
} from './bridge-limits.mjs';

test('accepts the local default bridge limits', () => {
  assert.deepEqual(parseBridgeLimits(DEFAULT_BRIDGE_LIMITS), DEFAULT_BRIDGE_LIMITS);
});

test('rejects non-integer, out-of-range, and inverted bridge limits', () => {
  for (const value of [
    { responses_max_mib: 1.5, inflight_body_max_mib: 2 },
    { responses_max_mib: 512, inflight_body_max_mib: 512 },
    { responses_max_mib: 256, inflight_body_max_mib: 255 },
  ]) {
    assert.throws(() => parseBridgeLimits(value), BridgeLimitsError);
  }
});

test('shared byte budget rejects concurrent over-allocation and releases exactly once', () => {
  const budget = new BridgeBodyBudget(10);
  const first = budget.createReservation();
  const second = budget.createReservation();
  assert.equal(first.reserve(7), true);
  assert.equal(second.reserve(4), false);
  assert.equal(budget.usedBytes, 7);
  first.release();
  first.release();
  assert.equal(budget.usedBytes, 0);
  assert.equal(second.reserve(4), true);
  second.release();
  assert.equal(budget.usedBytes, 0);
});

import { readFile } from 'node:fs/promises';

export const DEFAULT_BRIDGE_LIMITS = Object.freeze({
  responses_max_mib: 256,
  inflight_body_max_mib: 256,
});
export const MIN_LIMIT_MIB = 1;
export const MAX_LIMIT_MIB = 511;

export class BridgeLimitsError extends Error {
  constructor(message) {
    super(message);
    this.name = 'BridgeLimitsError';
    this.code = 'bridge_limits_invalid';
  }
}

export function parseBridgeLimits(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new BridgeLimitsError('桥接限制配置必须是 JSON 对象。');
  }
  const limits = {};
  for (const key of ['responses_max_mib', 'inflight_body_max_mib']) {
    const candidate = value[key];
    if (!Number.isInteger(candidate) || candidate < MIN_LIMIT_MIB || candidate > MAX_LIMIT_MIB) {
      throw new BridgeLimitsError(`桥接限制 ${key} 必须是 ${MIN_LIMIT_MIB} 到 ${MAX_LIMIT_MIB} 的整数 MiB。`);
    }
    limits[key] = candidate;
  }
  if (limits.inflight_body_max_mib < limits.responses_max_mib) {
    throw new BridgeLimitsError('inflight_body_max_mib 不能小于 responses_max_mib。');
  }
  return Object.freeze(limits);
}

export async function loadBridgeLimits(filename) {
  let source;
  try {
    source = await readFile(filename, 'utf8');
  } catch (error) {
    if (error.code === 'ENOENT') return DEFAULT_BRIDGE_LIMITS;
    throw error;
  }
  try {
    return parseBridgeLimits(JSON.parse(source));
  } catch (error) {
    if (error instanceof BridgeLimitsError) throw error;
    throw new BridgeLimitsError('桥接限制配置不是有效的 JSON。');
  }
}

export class BridgeBodyBudget {
  constructor(maximumBytes) {
    if (!Number.isSafeInteger(maximumBytes) || maximumBytes < 1) throw new RangeError('请求体预算必须为正整数。');
    this.maximumBytes = maximumBytes;
    this.usedBytes = 0;
  }

  createReservation() {
    return new BridgeBodyReservation(this);
  }
}

export class BridgeBodyReservation {
  constructor(budget) {
    this.budget = budget;
    this.reservedBytes = 0;
    this.released = false;
  }

  reserve(bytes) {
    if (this.released || !Number.isSafeInteger(bytes) || bytes < 0) return false;
    if (this.budget.usedBytes + bytes > this.budget.maximumBytes) return false;
    this.budget.usedBytes += bytes;
    this.reservedBytes += bytes;
    return true;
  }

  release() {
    if (this.released) return;
    this.released = true;
    this.budget.usedBytes -= this.reservedBytes;
    this.reservedBytes = 0;
  }
}

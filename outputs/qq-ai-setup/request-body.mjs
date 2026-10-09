export const SETTINGS_JSON_MAX_BYTES = 16 * 1024;

export class BridgeBodyError extends Error {
  constructor(code, message, status) {
    super(message);
    this.name = 'BridgeBodyError';
    this.code = code;
    this.status = status;
  }
}

// Count decoded transport chunks as bytes, not JavaScript characters. This keeps
// image-heavy Responses input bounded before JSON parsing allocates more objects.
export async function readJsonBody(req, { maximumBytes = SETTINGS_JSON_MAX_BYTES, reservation } = {}) {
  const parts = [];
  let size = 0;
  for await (const chunk of req) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;
    if (size > maximumBytes) {
      throw new BridgeBodyError('request_body_too_large', '请求正文超过允许大小。', 413);
    }
    if (reservation && !reservation.reserve(bytes.length)) {
      throw new BridgeBodyError('request_body_budget_exhausted', '本机正在接收较大的模型请求，请稍后再试。', 429);
    }
    parts.push(bytes);
  }

  const source = Buffer.concat(parts).toString('utf8');
  if (!source.trim()) return {};
  try {
    return JSON.parse(source);
  } catch {
    throw new BridgeBodyError('invalid_json_body', '请求正文不是有效的 JSON。', 400);
  }
}

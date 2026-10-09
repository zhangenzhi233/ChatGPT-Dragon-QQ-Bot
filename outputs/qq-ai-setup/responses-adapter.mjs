const unsupportedFields = new Set([
  'background', 'conversation', 'max_output_tokens', 'max_tool_calls', 'metadata',
  'moderation', 'multi_agent', 'prompt', 'prompt_cache_retention', 'safety_identifier',
  'temperature', 'top_logprobs', 'top_p', 'truncation', 'user', 'previous_response_id',
]);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
export class BridgeRequestError extends Error {
  constructor(message) { super(message); this.code = 'invalid_bridge_request'; this.status = 400; }
}

// MaiBot uses the public Responses shape. Adapt only the plan-route differences;
// preserve complete text/image history and function outputs for the local agent.
export function normalizePlanRequest(request, selectedModel) {
  if (!object(request) || !Array.isArray(request.input)) throw new BridgeRequestError('Responses 请求必须包含 input 消息数组。');
  if (!selectedModel || request.model !== selectedModel) throw new BridgeRequestError('请使用本机设置中选定的 ChatGPT 模型。');
  const result = structuredClone(request);
  for (const key of unsupportedFields) delete result[key];
  result.store = false;
  result.stream = true;
  for (const item of result.input) {
    if (!object(item)) throw new BridgeRequestError('input 消息格式无效。');
    if (item.role === 'system') item.role = 'developer';
    if (item.type === 'function_call' && !item.namespace) item.namespace = 'maibot';
    if (item.type === 'additional_tools') throw new BridgeRequestError('当前桥接通过统一的本机工具命名空间提供工具。');
  }
  if (result.tools !== undefined) {
    if (!Array.isArray(result.tools)) throw new BridgeRequestError('tools 必须是数组。');
    const functions = [];
    const namespaces = [];
    for (const tool of result.tools) {
      if (!object(tool)) throw new BridgeRequestError('工具定义无效。');
      if (tool.type === 'function' || tool.type === 'custom') functions.push(tool);
      else if (tool.type === 'namespace' && Array.isArray(tool.tools) && tool.tools.every(entry => object(entry) && ['function', 'custom'].includes(entry.type))) namespaces.push(tool);
      else throw new BridgeRequestError('这条 ChatGPT 方案连接只允许本机函数工具。');
    }
    if (functions.length) {
      if (namespaces.some(namespace => namespace.name === 'maibot')) throw new BridgeRequestError('maibot 工具命名空间重复。');
      namespaces.push({ type: 'namespace', name: 'maibot', description: '用户本机 QQ 助手的聊天工具', tools: functions });
    }
    if (namespaces.length) result.tools = namespaces;
    else delete result.tools;
  }
  return result;
}

export function encodeResponseEvent(event) {
  if (!object(event) || typeof event.type !== 'string') throw new BridgeRequestError('上游返回了无效的事件。');
  return `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
}

import { spawn } from 'node:child_process';
import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';
import { access, mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { createChatGPT } from '../../work/official-sdk/sign-in-with-chatgpt-devkit-main/packages/local/dist/index.js';
import { BridgeRequestError, normalizePlanRequest, encodeResponseEvent } from './responses-adapter.mjs';
import { getNapcatStatus, readQrPng, refreshQr, enableVerifiedWs } from './napcat-control.mjs';
import { BridgeBodyError, readJsonBody, SETTINGS_JSON_MAX_BYTES } from './request-body.mjs';
import { BridgeBodyBudget, loadBridgeLimits } from './bridge-limits.mjs';

const port = 8711;
const origin = `http://127.0.0.1:${port}`;
const directory = fileURLToPath(new URL('../../work/qq-ai-local/', import.meta.url));
const setupFile = `${directory}/setup.json`;
const setupToken = randomBytes(32).toString('hex');
await mkdir(directory, { recursive: true });
const bridgeLimits = await loadBridgeLimits(`${directory}/bridge-limits.json`);
const bridgeBodyBudget = new BridgeBodyBudget(bridgeLimits.inflight_body_max_mib * 1024 * 1024);

// Windows DPAPI keeps tokens encrypted for the current Windows user.
// Secret payloads travel only over child-process pipes, never command arguments.
async function dpapi(bytes, decrypt = false) {
  const operation = decrypt ? 'Unprotect' : 'Protect';
  const code = `$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Security; $inputBytes=[Convert]::FromBase64String([Console]::In.ReadToEnd().Trim()); $entropy=[Text.Encoding]::UTF8.GetBytes('qq-ai-local-chatgpt-v1'); $result=[Security.Cryptography.ProtectedData]::${operation}($inputBytes,$entropy,[Security.Cryptography.DataProtectionScope]::CurrentUser); [Console]::Out.Write([Convert]::ToBase64String($result))`;
  return new Promise((resolve, reject) => {
    const child = spawn('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-Command', code], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    const chunks = [];
    const timeout = setTimeout(() => { child.kill(); reject(new Error('Windows 加密服务超时')); }, 15000);
    child.stdout.on('data', chunk => chunks.push(chunk));
    child.stderr.resume();
    child.once('error', () => { clearTimeout(timeout); reject(new Error('无法启动 Windows 加密服务')); });
    child.once('exit', exitCode => {
      clearTimeout(timeout);
      if (exitCode !== 0) return reject(new Error('Windows 加密服务失败，未保存明文凭据'));
      resolve(Buffer.from(Buffer.concat(chunks).toString('utf8').trim(), 'base64'));
    });
    child.stdin.on('error', () => {});
    child.stdin.end(Buffer.from(bytes).toString('base64'));
  });
}
const probe = Buffer.from('qq-ai-encryption-check');
if (!(await dpapi(await dpapi(probe), true)).equals(probe)) throw new Error('Windows 加密验证失败');

const chatgpt = createChatGPT({
  appName: 'ChatGPT 龙娘 QQ 聊天机器人', appId: 'chatgpt-dragon-qq-bot', redirectPort: 0,
  sendHostId: true, storageDir: `${directory}/chatgpt`,
  credentialEncryption: {
    id: 'windows-dpapi-current-user-qq-ai-v1',
    isAvailable: () => process.platform === 'win32',
    encrypt: text => dpapi(Buffer.from(text, 'utf8')),
    decrypt: async bytes => (await dpapi(bytes, true)).toString('utf8'),
  },
});
let signInPending = false;
let lastError = null;
let testing = false;
const bridgeState = { completed: 0, failed: 0, active: 0, lastCompletedAt: null, lastError: null };
let modelPause = null;
try { modelPause = JSON.parse(await readFile(`${directory}/model-paused.json`, 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
const pauseState = () => ({ paused: Boolean(modelPause?.resumeAfter && Date.parse(modelPause.resumeAfter) > Date.now()), resumeAfter: modelPause?.resumeAfter ?? null, reason: modelPause?.reason ?? null });
let setup = {};
try { setup = JSON.parse(await readFile(setupFile, 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }

const translatedErrors = {
  network_error: '程序无法连接 OpenAI，请检查当前网络连接。',
  discovery_failed: '无法验证 OpenAI 的登录配置，授权尚未开始。',
  browser_unavailable: '无法打开默认浏览器，请检查浏览器设置。',
  cancelled: '本次登录或请求已取消。',
  sharing_not_enabled: '账号已登录，但尚未授权本助手使用 ChatGPT 方案额度。',
  sign_in_required: '请先使用 ChatGPT 登录。',
  subscription_sharing_user_not_eligible: '这个账号、工作空间或策略暂不允许本助手使用方案额度。请先确认可用性，勿反复登录。',
  subscription_sharing_usage_limit_exceeded: '本助手的 ChatGPT 方案额度已达到限制，请在 ChatGPT 设置中查看额度。',
};
const safeError = error => ({
  code: typeof error.code === 'string' ? error.code : 'local_error',
  message: translatedErrors[error.code] ?? (error.status === 403 ? 'OpenAI 拒绝了请求（HTTP 403）。需核对网络连接、应用权限或允许的服务地区。' : error.code ? error.message : '本机操作失败，请查看终端状态。'),
  ...(Number.isInteger(error.status) ? { status: error.status } : {}),
  ...(typeof error.requestId === 'string' ? { requestId: error.requestId } : {}),
  ...(typeof error.responseShape === 'string' ? { responseShape: error.responseShape } : {}),
  ...(typeof error.param === 'string' ? { param: error.param } : {}),
});
const send = (res, status, value) => {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(value));
};
const upstreamStatus = error => error.code === 'subscription_sharing_usage_limit_exceeded' ? 429 : Number.isInteger(error.status) && error.status >= 400 && error.status < 600 ? error.status : 502;
const bridgeErrorType = error => error instanceof BridgeBodyError
  ? (error.status === 429 ? 'rate_limit_error' : 'invalid_request_error')
  : error instanceof BridgeRequestError ? 'invalid_request_error' : 'upstream_error';
const bridgeError = error => {
  const safe = safeError(error);
  return { message: safe.message, code: safe.code, param: safe.param, type: bridgeErrorType(error) };
};

async function applySavedModel(full = false) {
  const configUrl = new URL('../../work/compatible-release/MaiBot-1.2.5/config/model_config.toml', import.meta.url);
  // A fresh clone has no private configuration yet: generate the full local config.
  try { await access(configUrl); } catch (error) { if (error.code === 'ENOENT') full = true; else throw error; }
  const pythonPath = fileURLToPath(new URL('../../work/compatible-release/MaiBot-1.2.5/.venv/Scripts/python.exe', import.meta.url));
  const configurePath = fileURLToPath(new URL('./configure-maibot.py', import.meta.url));
  await new Promise((resolve, reject) => {
    const child = spawn(pythonPath, [configurePath, ...(full ? [] : ['--model-only'])], { windowsHide: true, stdio: ['ignore', 'ignore', 'ignore'], env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' } });
    const timeout = setTimeout(() => { child.kill(); reject(Object.assign(new Error('模型配置更新超时，原选择已保留。'), { code: 'model_config_error' })); }, 30000);
    child.once('error', () => { clearTimeout(timeout); reject(Object.assign(new Error('无法运行本机模型配置更新程序。'), { code: 'model_config_error' })); });
    child.once('exit', code => { clearTimeout(timeout); code === 0 ? resolve() : reject(Object.assign(new Error('模型配置更新失败，请检查本机配置。'), { code: 'model_config_error' })); });
  });
  return true;
}

async function handleBridge(req, res, path) {
  let expected;
  try { expected = (await readFile(`${directory}/bridge-key.txt`, 'utf8')).trim(); }
  catch (error) { if (error.code === 'ENOENT') return send(res, 503, { error: { message: '模型桥接正在准备', type: 'service_unavailable' } }); throw error; }
  const supplied = String(req.headers.authorization ?? '');
  const actualBytes = Buffer.from(supplied);
  const expectedBytes = Buffer.from(`Bearer ${expected}`);
  if (!expected || expectedBytes.length !== actualBytes.length || !timingSafeEqual(actualBytes, expectedBytes) || req.headers.origin) return send(res, 401, { error: { message: '本机桥接认证失败', type: 'authentication_error' } });
  if (path === '/v1/models' && req.method === 'GET') {
    const models = await chatgpt.listModels();
    return send(res, 200, { object: 'list', data: models.map(model => ({ id: model.slug, object: 'model', created: 0, owned_by: 'chatgpt-plan' })) });
  }
  if (path !== '/v1/responses' || req.method !== 'POST') return send(res, 404, { error: { message: '桥接仅支持 Responses 和模型列表', type: 'invalid_request_error' } });
  if (pauseState().paused) return send(res, 429, { error: { message: 'ChatGPT 方案额度已达到限制，等待约定时间后再验证。', code: 'subscription_sharing_usage_limit_exceeded', type: 'rate_limit_error' } });
  if (bridgeState.active >= 3) return send(res, 429, { error: { message: '本机模型请求已达到并发上限', type: 'rate_limit_error' } });
  bridgeState.active++;
  const reservation = bridgeBodyBudget.createReservation();
  try {
    const request = await readJsonBody(req, {
      maximumBytes: bridgeLimits.responses_max_mib * 1024 * 1024,
      reservation,
    });
    const currentSetup = JSON.parse(await readFile(setupFile, 'utf8'));
    const nativeBody = normalizePlanRequest(request, currentSetup.selectedModel);
    if (typeof chatgpt.streamRawResponse !== 'function') return send(res, 503, { error: { message: '模型桥接模块尚未构建完成', type: 'service_unavailable' } });
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(240000)]);
    res.on('close', () => { if (!res.writableEnded) controller.abort(); });
    const result = await chatgpt.streamRawResponse({ body: nativeBody, signal, onEvent: async event => {
      if (request.stream !== true) return;
      if (!res.headersSent) res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no' });
      if (!res.destroyed && !res.write(encodeResponseEvent(event))) await once(res, 'drain', { signal });
    } });
    bridgeState.completed++;
    bridgeState.lastCompletedAt = new Date().toISOString();
    bridgeState.lastError = null;
    if (request.stream === true) res.end();
    // A completed raw stream is the success gate even for a non-streaming client.
    else if (!res.headersSent) send(res, 200, result);
    else res.end();
  } catch (error) {
    bridgeState.failed++;
    bridgeState.lastError = safeError(error);
    if (!res.headersSent) send(res, upstreamStatus(error), { error: bridgeError(error) });
    else if (!res.destroyed) { res.write(encodeResponseEvent({ type: 'error', code: safeError(error).code, message: safeError(error).message })); res.end(); }
  } finally {
    reservation.release();
    bridgeState.active--;
  }
}

const server = createServer(async (req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'no-referrer');
  if (req.headers.host !== `127.0.0.1:${port}`) return send(res, 403, { error: '仅接受本机访问' });
  const path = new URL(req.url, origin).pathname;
  try {
    if (path.startsWith('/v1/')) return await handleBridge(req, res, path);
    if (req.method === 'GET' && path === '/') {
      const page = await readFile(new URL('./index.html', import.meta.url), 'utf8');
      const nonce = randomBytes(18).toString('base64');
      res.setHeader('Content-Security-Policy', `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'`);
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      return res.end(page.replaceAll('__NONCE__', nonce).replaceAll('__SETUP_TOKEN__', setupToken));
    }
    if (req.method === 'GET' && ['/eula', '/privacy'].includes(path)) {
      const filename = path === '/eula' ? 'EULA.md' : 'PRIVACY.md';
      const text = await readFile(new URL(`../../work/compatible-release/MaiBot-1.2.5/${filename}`, import.meta.url), 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
      return res.end(text);
    }
    if (req.headers['x-setup-token'] !== setupToken || (req.headers.origin && req.headers.origin !== origin)) return send(res, 403, { error: '请从本机设置页面操作' });
    if (req.method === 'GET' && path === '/api/qq/status') return send(res, 200, await getNapcatStatus());
    if (req.method === 'GET' && path === '/api/qq/qr') {
      const status = await getNapcatStatus();
      if (!status.ready || status.loggedIn) return send(res, 409, { error: '当前没有可用的登录二维码。' });
      let png;
      try { png = await readQrPng(); } catch { return send(res, 404, { error: '二维码正在准备。' }); }
      res.writeHead(200, { 'Content-Type': 'image/png', 'Cache-Control': 'no-store' });
      return res.end(png);
    }
    if (req.method === 'POST' && path === '/api/qq/refresh') {
      const status = await getNapcatStatus();
      if (status.loggedIn) return send(res, 409, { error: 'QQ 已登录，无需刷新二维码。' });
      return send(res, 200, await refreshQr());
    }
    if (req.method === 'POST' && path === '/api/qq/enable') {
      const status = await enableVerifiedWs();
      if (!status.wsEnabled) return send(res, 503, { error: '消息通道尚未准备好，请稍后重试。' });
      await writeFile(`${directory}/qq-ready.json`, JSON.stringify({ checkedAt: new Date().toISOString(), accountVerified: status.accountMatches, wsEnabled: true }, null, 2), 'utf8');
      return send(res, 200, { ...status, modelWaiting: true });
    }
    if (req.method === 'GET' && path === '/api/status') return send(res, 200, {
      session: await chatgpt.getSession(), setup, signInPending, lastError, testing, bridge: bridgeState,
      modelPause: pauseState(), limits: bridgeLimits,
    });
    if (req.method === 'GET' && path === '/api/models') return send(res, 200, { models: await chatgpt.listModels() });
    if (req.method === 'POST' && path === '/api/signin') {
      if (signInPending) return send(res, 409, { error: '登录正在进行' });
      signInPending = true;
      lastError = null;
      // Only this explicit button action launches the official authorization flow.
      chatgpt.signIn().catch(error => { lastError = safeError(error); }).finally(() => { signInPending = false; });
      return send(res, 202, { started: true });
    }
    if (req.method === 'POST' && path === '/api/cancel-signin') { chatgpt.cancelSignIn(); return send(res, 200, { cancelled: true }); }
    if (req.method === 'POST' && path === '/api/disconnect') { await chatgpt.disconnect(); return send(res, 200, { disconnected: true }); }
    if (req.method === 'POST' && path === '/api/setup') {
      const value = await readJsonBody(req, { maximumBytes: SETTINGS_JSON_MAX_BYTES });
      const botQQ = String(value.botQQ ?? '').trim();
      const ownerQQ = String(value.ownerQQ ?? '').trim();
      const groupQQ = String(value.groupQQ ?? '').trim();
      if (!/^[1-9][0-9]{4,11}$/.test(botQQ) || !/^[1-9][0-9]{4,11}$/.test(ownerQQ) || (groupQQ && !/^[1-9][0-9]{4,11}$/.test(groupQQ))) return send(res, 400, { error: '请填写有效的 QQ 号，测试群号可以暂留空' });
      if (botQQ === ownerQQ) return send(res, 400, { error: '机器人小号和你自己的 QQ 号需要不同' });
      if (value.agreementsAccepted !== true) return send(res, 400, { error: 'MaiBot 要求你阅读并同意许可及隐私条款后才能运行' });
      const selectedModel = String(value.selectedModel ?? '').trim() || setup.selectedModel || '';
      if (selectedModel) {
        const models = await chatgpt.listModels();
        if (!models.some(model => model.slug === selectedModel)) return send(res, 400, { error: '所选模型不在当前账号的可用列表中' });
      }
      const agreementHashes = {};
      for (const file of ['EULA.md', 'PRIVACY.md']) agreementHashes[file] = createHash('sha256').update(await readFile(new URL(`../../work/compatible-release/MaiBot-1.2.5/${file}`, import.meta.url))).digest('hex');
      const previousSetup = setup;
      setup = { botQQ, ownerQQ, groupQQ, selectedModel, agreementsAccepted: true, agreementsAcceptedAt: new Date().toISOString(), agreementHashes };
      await writeFile(`${setupFile}.tmp`, JSON.stringify(setup, null, 2), 'utf8');
      await rename(`${setupFile}.tmp`, setupFile);
      let modelApplied = false;
      const qqChanged = ['botQQ', 'ownerQQ', 'groupQQ'].some(key => previousSetup[key] !== setup[key]);
      try { modelApplied = await applySavedModel(qqChanged); }
      catch (error) {
        setup = previousSetup;
        await writeFile(`${setupFile}.tmp`, JSON.stringify(setup, null, 2), 'utf8');
        await rename(`${setupFile}.tmp`, setupFile);
        throw error;
      }
      return send(res, 200, { saved: true, modelApplied });
    }
    if (req.method === 'POST' && path === '/api/test') {
      if (pauseState().paused) return send(res, 429, { error: 'ChatGPT 方案额度已达到限制，已暂停重复测试。请等待约定的重测时间。' });
      if (testing) return send(res, 409, { error: '测试正在进行' });
      const value = await readJsonBody(req, { maximumBytes: SETTINGS_JSON_MAX_BYTES });
      const models = await chatgpt.listModels();
      if (!models.some(model => model.slug === value.model)) return send(res, 400, { error: '请先选择可用模型' });
      testing = true;
      try {
        const result = await chatgpt.streamResponse({ model: value.model, input: '请用中文简短回复：QQ AI 连接测试成功。', signal: AbortSignal.timeout(180000) });
        return send(res, 200, { text: result.text, completed: true });
      } finally { testing = false; }
    }
    return send(res, 404, { error: '没有这个入口' });
  } catch (error) {
    if (path.startsWith('/v1/')) send(res, upstreamStatus(error), { error: bridgeError(error) });
    else send(res, 400, { error: safeError(error).message, code: safeError(error).code });
  }
});
server.on('error', error => { console.error(error.code === 'EADDRINUSE' ? '设置页已运行，或 8711 端口被占用。' : '本机设置服务启动失败。'); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`QQ AI 设置页面：${origin}\nWindows 加密检查通过；尚未连接 QQ。`));
process.on('SIGINT', () => { chatgpt.cancelSignIn(); server.close(); });

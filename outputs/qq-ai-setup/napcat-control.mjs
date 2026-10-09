import { createHash, timingSafeEqual } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const localRoot = fileURLToPath(new URL('../../work/qq-ai-local/', import.meta.url));
const setupPath = `${localRoot}/setup.json`;
const webUiKeyPath = `${localRoot}/napcat-webui-key.txt`;
const oneBotTokenPath = `${localRoot}/napcat-token.txt`;
const webUi = 'http://127.0.0.1:6109/api';
let credential = null;
let credentialExpiresAt = 0;

function safeStatus(value = {}) {
  return {
    ready: Boolean(value.ready),
    loggedIn: Boolean(value.loggedIn),
    accountMatches: Boolean(value.accountMatches),
    coreReady: Boolean(value.coreReady),
    isOffline: Boolean(value.isOffline),
    wsEnabled: Boolean(value.wsEnabled),
    loginPhase: typeof value.loginPhase === 'string' ? value.loginPhase : null,
  };
}

async function jsonFile(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

async function expectedAccount() {
  const setup = await jsonFile(setupPath);
  const account = String(setup.botQQ ?? '').trim();
  if (!/^\d{5,15}$/.test(account)) throw new Error('本机机器人账号配置无效。');
  return account;
}

async function webUiKey() {
  // Test-only process override avoids creating a credential fixture on disk.
  if (process.env.NAPCAT_CONTROL_TEST_WEBUI_KEY) return process.env.NAPCAT_CONTROL_TEST_WEBUI_KEY;
  const key = (await readFile(webUiKeyPath, 'utf8')).trim();
  if (key.length < 24) throw new Error('本机 NapCat WebUI 密钥不可用。');
  return key;
}

async function request(path, body = {}, retry = true) {
  if (!credential || Date.now() >= credentialExpiresAt) await authenticate();
  const response = await fetch(`${webUi}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${credential}` },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  });
  if (response.status === 401 && retry) {
    credential = null;
    credentialExpiresAt = 0;
    await authenticate();
    return request(path, body, false);
  }
  if (!response.ok) throw new Error(`NapCat WebUI 请求失败（HTTP ${response.status}）。`);
  const result = await response.json();
  if (result?.code !== 0) throw new Error('NapCat WebUI 拒绝了本机请求。');
  return result.data;
}

async function authenticate() {
  const token = await webUiKey();
  const hash = createHash('sha256').update(`${token}.napcat`, 'utf8').digest('hex');
  const response = await fetch(`${webUi}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hash }), signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`NapCat WebUI 登录失败（HTTP ${response.status}）。`);
  const result = await response.json();
  const next = result?.data?.Credential;
  if (result?.code !== 0 || typeof next !== 'string' || next.length < 16) throw new Error('NapCat WebUI 本机认证失败。');
  credential = next;
  credentialExpiresAt = Date.now() + 90_000;
}

async function loginState() {
  const state = await request('/QQLogin/CheckLoginStatus');
  const loggedIn = Boolean(state?.isLogin);
  let accountMatches = false;
  let wsEnabled = false;
  if (loggedIn) {
    const info = await request('/QQLogin/GetQQLoginInfo');
    const expected = await expectedAccount();
    const actual = String(info?.uin ?? '');
    accountMatches = actual.length === expected.length && timingSafeEqual(Buffer.from(actual), Buffer.from(expected));
    if (accountMatches) {
      try {
        const [config, token] = await Promise.all([
          request('/OB11Config/GetConfig'),
          readFile(oneBotTokenPath, 'utf8'),
        ]);
        const enabled = (config?.network?.websocketServers ?? []).filter(item => item?.enable === true);
        const server = enabled[0];
        const expectedToken = token.trim();
        const actualToken = String(server?.token ?? '');
        wsEnabled = enabled.length === 1 && server?.host === '127.0.0.1' && Number(server?.port) === 3011 &&
          expectedToken.length > 0 && actualToken.length === expectedToken.length &&
          timingSafeEqual(Buffer.from(actualToken), Buffer.from(expectedToken));
      } catch {
        wsEnabled = false;
      }
    }
  }
  return safeStatus({ ready: true, loggedIn, accountMatches, coreReady: state?.coreReady, isOffline: state?.isOffline, wsEnabled, loginPhase: state?.loginPhase });
}

export async function getNapcatStatus() {
  try { return await loginState(); }
  catch { return safeStatus(); }
}

export async function getSavedLoginStatus() {
  const account = await expectedAccount();
  const accounts = await request('/QQLogin/GetQuickLoginList');
  const autoAccount = await request('/QQLogin/GetQuickLoginQQ');
  return {
    savedQuickLoginAvailable: Array.isArray(accounts) && accounts.some(value => String(value) === account),
    autoLoginConfigured: String(autoAccount ?? '') === account,
  };
}

export async function restoreSavedLogin() {
  const state = await loginState();
  if (state.loggedIn) {
    if (!state.accountMatches) throw new Error('当前账号不是保存的小号，拒绝快速登录。');
    return { attempted: false, alreadyLoggedIn: true };
  }
  const saved = await getSavedLoginStatus();
  const account = await expectedAccount();
  // Persist only the selected dedicated account; no passwords or other accounts.
  await request('/QQLogin/SetQuickLoginQQ', { uin: account });
  if (!saved.savedQuickLoginAvailable) return { attempted: false, needsQr: true, autoLoginConfigured: true };
  try {
    await request('/QQLogin/SetQuickLogin', { uin: account });
    return { attempted: true, accepted: true, autoLoginConfigured: true };
  } catch {
    return { attempted: true, accepted: false, autoLoginConfigured: true };
  }
}

export async function readQrPng() {
  // The file is local binary data. This module deliberately returns no URL or account metadata.
  return readFile(fileURLToPath(new URL('../../work/NapCat/cache/qrcode.png', import.meta.url)));
}

export async function refreshQr() {
  await request('/QQLogin/RefreshQRcode');
  return safeStatus(await loginState());
}

export async function enableVerifiedWs() {
  const state = await loginState();
  if (!state.loggedIn || !state.accountMatches || !state.coreReady || state.isOffline) {
    throw new Error('QQ 小号尚未完成可用登录或账号不匹配，已拒绝开启 OneBot。');
  }
  const current = await request('/OB11Config/GetConfig');
  const token = (await readFile(oneBotTokenPath, 'utf8')).trim();
  if (token.length < 24) throw new Error('本机 OneBot 密钥不可用。');
  const next = {
    ...current,
    network: {
      ...(current?.network ?? {}),
      httpServers: [], httpSseServers: [], httpClients: [], websocketClients: [], plugins: [],
      websocketServers: [{
        name: 'maibot-local-ws', enable: true, host: '127.0.0.1', port: 3011,
        messagePostFormat: 'array', reportSelfMessage: false, enableForcePushEvent: true,
        heartInterval: 30000, token, debug: false,
      }],
    },
  };
  await request('/OB11Config/SetConfig', { config: JSON.stringify(next) });
  return safeStatus(await loginState());
}

// Return only safe local readiness fields; never serialize sessions or credentials.
import { readFile } from 'node:fs/promises';
import { getSavedLoginStatus, restoreSavedLogin } from './napcat-control.mjs';

async function setupRequest(path, method = 'GET') {
  const page = await fetch('http://127.0.0.1:8711/', { signal: AbortSignal.timeout(5000) });
  const html = await page.text();
  const match = html.match(/\bconst\s+token\s*=\s*(['"])([^'"]+)\1/);
  if (!page.ok || !html.includes('QQ AI') || !match) throw new Error('Setup unavailable');
  const response = await fetch(`http://127.0.0.1:8711/api/${path}`, {
    method, headers: { 'x-setup-token': match[2] }, signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error('Local setup request failed');
  return response.json();
}

export async function bridgeStatus(fetchImpl = fetch) {
  const page = await fetchImpl('http://127.0.0.1:8711/', { signal: AbortSignal.timeout(5000) });
  if (!page.ok) return { ready: false };
  const html = await page.text();
  const match = html.match(/\bconst\s+token\s*=\s*(['"])([^'"]+)\1/);
  if (!html.includes('QQ AI') || !match) return { ready: false };
  const response = await fetchImpl('http://127.0.0.1:8711/api/status', {
    headers: { 'x-setup-token': match[2] }, signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) return { ready: false };
  const status = await response.json();
  return {
    ready: status.session?.status === 'connected' && status.session?.sharing === true,
    planPaused: status.modelPause?.paused === true,
    signInPending: status.signInPending === true,
  };
}

export async function runControl(action) {
  if (action === 'bridge') return bridgeStatus();
  // The long-lived setup server caches NapCat authentication. Starting a new
  // auth session on every three-second poll can hit NapCat's login rate limit.
  if (action === 'status') return setupRequest('qq/status');
  if (action === 'enable') {
    const status = await setupRequest('qq/enable', 'POST');
    const { modelWaiting: _unused, ...safeStatus } = status;
    return safeStatus;
  }
  if (action === 'saved-login') return getSavedLoginStatus();
  if (action === 'restore-login') return restoreSavedLogin();
  if (action === 'settings') {
    const setup = JSON.parse(await readFile(new URL('../../work/qq-ai-local/setup.json', import.meta.url), 'utf8'));
    return { saved: Boolean(setup.botQQ && setup.ownerQQ && setup.selectedModel && setup.agreementsAccepted === true) };
  }
  throw new Error('Unknown launcher action');
}

if (process.argv[1] && new URL(import.meta.url).pathname.endsWith('/launcher-control.mjs') &&
    process.argv[1].replaceAll('\\', '/').endsWith('/launcher-control.mjs')) {
  try { console.log(JSON.stringify(await runControl(process.argv[2]))); }
  catch { console.log(JSON.stringify({ ready: false, errorCode: 'local_control_failed' })); process.exitCode = 1; }
}

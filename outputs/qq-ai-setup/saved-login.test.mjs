import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { copyFile, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';

const expected = '100002';
const fixtureRoot = await mkdtemp(path.join(tmpdir(), 'dragon-qq-login-test-'));
const modulePath = path.join(fixtureRoot, 'outputs', 'qq-ai-setup', 'napcat-control.mjs');
await mkdir(path.dirname(modulePath), { recursive: true });
await mkdir(path.join(fixtureRoot, 'work', 'qq-ai-local'), { recursive: true });
await writeFile(path.join(fixtureRoot, 'work', 'qq-ai-local', 'setup.json'), JSON.stringify({ botQQ: expected }));
await copyFile(new URL('./napcat-control.mjs', import.meta.url), modulePath);
after(async () => {
  if (!fixtureRoot.startsWith(path.join(tmpdir(), 'dragon-qq-login-test-'))) throw new Error('Unexpected fixture path');
  await rm(fixtureRoot, { recursive: true, force: true });
});

async function mockLogin(t, kind) {
  const originalFetch = globalThis.fetch;
  const originalKey = process.env.NAPCAT_CONTROL_TEST_WEBUI_KEY;
  process.env.NAPCAT_CONTROL_TEST_WEBUI_KEY = 'offline-fixture-key-never-used-on-network';
  const paths = [];
  let onlySelectedAccount = true;
  globalThis.fetch = async (url, options) => {
    const path = new URL(url).pathname;
    paths.push(path);
    let data = null;
    if (path === '/api/auth/login') data = { Credential: 'offline-fixture-credential' };
    else if (path.endsWith('/CheckLoginStatus')) data = { isLogin: kind === 'wrong-account', coreReady: true, loginPhase: 'ready' };
    else if (path.endsWith('/GetQQLoginInfo')) data = { uin: 'different-fixture-account' };
    else if (path.endsWith('/GetQuickLoginList')) data = kind === 'saved-account' ? [expected] : ['different-fixture-account'];
    else if (path.endsWith('/GetQuickLoginQQ')) data = '';
    else if (path.endsWith('/SetQuickLoginQQ') || path.endsWith('/SetQuickLogin')) {
      onlySelectedAccount &&= JSON.parse(options.body).uin === expected;
    } else throw new Error('Unexpected offline endpoint');
    return { ok: true, status: 200, json: async () => ({ code: 0, data }) };
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
    if (originalKey === undefined) delete process.env.NAPCAT_CONTROL_TEST_WEBUI_KEY;
    else process.env.NAPCAT_CONTROL_TEST_WEBUI_KEY = originalKey;
  });
  const control = await import(`${pathToFileURL(modulePath).href}?fixture=${kind}`);
  return { control, paths, selectedOnly: () => onlySelectedAccount };
}

test('an already logged-in different account is never changed or quick-logged-in', async t => {
  const fixture = await mockLogin(t, 'wrong-account');
  await assert.rejects(fixture.control.restoreSavedLogin());
  assert(!fixture.paths.some(path => path.endsWith('/SetQuickLogin') || path.endsWith('/SetQuickLoginQQ')));
});

test('missing selected history falls back to QR without trying another account', async t => {
  const fixture = await mockLogin(t, 'missing-history');
  const result = await fixture.control.restoreSavedLogin();
  assert.equal(result.needsQr, true);
  assert.equal(result.attempted, false);
  assert(!fixture.paths.some(path => path.endsWith('/SetQuickLogin')));
  assert.equal(fixture.selectedOnly(), true);
});

test('valid selected history triggers exactly one quick-login request', async t => {
  const fixture = await mockLogin(t, 'saved-account');
  const result = await fixture.control.restoreSavedLogin();
  assert.equal(result.accepted, true);
  assert.equal(fixture.paths.filter(path => path.endsWith('/SetQuickLogin')).length, 1);
  assert.equal(fixture.selectedOnly(), true);
});

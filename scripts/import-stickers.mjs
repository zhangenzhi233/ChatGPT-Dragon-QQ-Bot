import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { registerCharacterPack } from './character-catalog.mjs';

const workspace = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const robotRoot = path.join(workspace, 'work', 'compatible-release', 'MaiBot-1.2.5');
const api = 'http://127.0.0.1:8011/api/webui/emoji';
const packs = ['银白龙_原图24', '银白龙_补充4', '银白龙_我喜欢你'];

async function main() {
  let headers;
  async function request(endpoint, options = {}) {
    const response = await fetch(`${api}${endpoint}`, {
      ...options,
      headers: { ...headers, ...options.headers },
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error(`表情库 API 返回 HTTP ${response.status}。`);
    const data = await response.json();
    if (data.success !== true) throw new Error('表情库 API 未确认操作成功。');
    return data;
  }
  async function listAll() {
    const data = [];
    for (let page = 1; ; page++) {
      const result = await request(`/list?page=${page}&page_size=100`);
      data.push(...result.data);
      if (data.length >= result.total || result.data.length === 0) break;
    }
    return { data };
  }

  // 先校验本次全部素材，再修改机器人表情库，避免因材料缺失只导入一部分。
  const assets = [];
  for (const pack of packs) {
    const root = path.join(workspace, 'assets', 'stickers', pack);
    const manifest = JSON.parse(await readFile(path.join(root, 'manifest.json'), 'utf8'));
    if (manifest.count !== manifest.stickers.length) throw new Error(`${pack} 的素材数量不一致。`);
    for (const sticker of manifest.stickers) {
      const filePath = path.resolve(root, sticker.file);
      if (!filePath.startsWith(`${root}${path.sep}`)) throw new Error('素材路径越出表情包目录。');
      const bytes = await readFile(filePath);
      const sha256 = createHash('sha256').update(bytes).digest('hex');
      if (sha256 !== sticker.sha256 || bytes.length > 5 * 1024 * 1024) {
        throw new Error(`${sticker.name} 的文件校验失败或超出大小限制。`);
      }
      if (bytes.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') {
        throw new Error(`${sticker.name} 不是 PNG 文件。`);
      }
      if (manifest.mode === 'high_resolution_redraw' && Math.min(bytes.readUInt32BE(16), bytes.readUInt32BE(20)) < 1024) {
        throw new Error(`${sticker.name} 的高清文件像素不足。`);
      }
      assets.push({ ...sticker, pack, filePath, bytes, sha256, description: sticker.tags.join(',') });
    }
  }
  if (assets.length !== 29 || new Set(assets.map((asset) => asset.sha256)).size !== 29) {
    throw new Error('应有 29 个不同的素材文件。');
  }

  if (process.argv.includes('--check-only')) { console.log(JSON.stringify({ assets: assets.length, valid: true, sent: false })); return; }
  const webui = JSON.parse(await readFile(path.join(robotRoot, 'data', 'webui.json'), 'utf8'));
  if (typeof webui.access_token !== 'string' || !webui.access_token) {
    throw new Error('机器人本机管理凭据不存在。');
  }
  headers = { Cookie: `maibot_session=${webui.access_token}` };
  const before = (await request('/stats/summary')).data;
  const listing = await listAll();
  const known = new Map(listing.data.map((entry) => [entry.emoji_hash, entry]));
  const imported = [];
  for (const asset of assets) {
    let record = known.get(asset.sha256);
    const existed = Boolean(record);
    if (!record || !record.is_registered || record.is_banned || record.description !== asset.description) {
      const form = new FormData();
      form.append('file', new Blob([asset.bytes], { type: 'image/png' }), path.basename(asset.filePath));
      form.append('description', asset.description);
      form.append('emotion', asset.description);
      form.append('is_registered', 'true');
      record = (await request('/upload', { method: 'POST', body: form })).data;
    }
    if (record.emoji_hash !== asset.sha256 || !record.is_registered || record.is_banned) {
      throw new Error(`${asset.name} 未正确注册。`);
    }
    const storedPath = path.resolve(robotRoot, record.full_path);
    if (!storedPath.startsWith(`${path.join(robotRoot, 'data', 'emoji')}${path.sep}`)) {
      throw new Error('机器人返回的图片路径不在表情库内。');
    }
    const stored = await readFile(storedPath);
    if (createHash('sha256').update(stored).digest('hex') !== asset.sha256) {
      throw new Error(`${asset.name} 的入库副本与素材不一致。`);
    }
    imported.push({
      id: asset.id, name: asset.name, pack: asset.pack, database_id: record.id,
      sha256: asset.sha256, registered: true, stored_path: storedPath, existed,
    });
  }
  const after = (await request('/stats/summary')).data;
  const finalListing = await listAll();
  const finalByHash = new Map(finalListing.data.map((entry) => [entry.emoji_hash, entry]));
  if (assets.some((asset) => {
    const entry = finalByHash.get(asset.sha256);
    return !entry || !entry.is_registered || entry.is_banned || entry.description !== asset.description;
  })) throw new Error('导入后的总核验未通过。');
  const report = {
    checked_at: new Date().toISOString(),
    count: imported.length,
    original_count: assets.filter((asset) => asset.pack === '银白龙_原图24' && !asset.original_sha256).length,
    redrawn_count: assets.filter((asset) => Boolean(asset.original_sha256)).length,
    supplemental_count: 4,
    generated_count: assets.filter((asset) => asset.original_sha256 || asset.pack === '银白龙_补充4').length,
    before: { total: before.total, registered: before.registered },
    after: { total: after.total, registered: after.registered },
    all_files_match: true,
    all_registered: true,
    runtime_pool_checked: false,
    qq_delivery_tested: false,
    stickers: imported,
  };
  for (const pack of packs) {
    const root = path.join(workspace, 'assets', 'stickers', pack);
    const manifest = JSON.parse(await readFile(path.join(root, 'manifest.json'), 'utf8'));
    await registerCharacterPack(robotRoot, root, manifest);
  }
  await writeFile(path.join(workspace, 'work', 'qq-ai-local', 'sticker-import.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({
    imported: imported.length, new: imported.filter((entry) => !entry.existed).length,
    total: after.total, registered: after.registered, allFilesMatch: true,
  }));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : '导入失败。');
  process.exitCode = 1;
});

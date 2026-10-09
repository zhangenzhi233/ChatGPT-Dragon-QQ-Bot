// 角色归属只来自经用户确认并校验哈希的素材清单，不靠情绪标签或相似白发推断。
import { createHash } from 'node:crypto';
import { readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';

export async function registerCharacterPack(robotRoot, packRoot, manifest) {
  if (!manifest.character?.name) return 0;
  const catalogPath = path.join(robotRoot, 'data', 'emoji', 'character_catalog.json');
  let catalog;
  try {
    catalog = JSON.parse(await readFile(catalogPath, 'utf8'));
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    catalog = { version: 1, characters: {} };
  }
  if (catalog.version !== 1 || !catalog.characters || typeof catalog.characters !== 'object') {
    throw new Error('角色表情索引格式错误。');
  }
  const name = manifest.character.name;
  const info = catalog.characters[name] ?? { aliases: [], stickers: {} };
  info.aliases = [...new Set([...info.aliases, ...(manifest.character.aliases ?? [])])];
  let updated = 0;
  for (const sticker of manifest.stickers) {
    const file = path.resolve(packRoot, sticker.file);
    if (!file.startsWith(path.resolve(packRoot) + path.sep)) throw new Error('角色素材路径越界。');
    const bytes = await readFile(file);
    const hash = createHash('sha256').update(bytes).digest('hex');
    if (hash !== sticker.sha256 || !sticker.visual_description) throw new Error('角色素材哈希或可见内容未核实。');
    info.stickers[hash] = {
      name: sticker.name,
      description: sticker.visual_description,
      tags: sticker.tags,
      source_pack: path.basename(packRoot),
    };
    updated++;
  }
  catalog.characters[name] = info;
  catalog.updated_at = new Date().toISOString();
  const tempPath = catalogPath + '.tmp';
  await writeFile(tempPath, JSON.stringify(catalog, null, 2) + '\n', 'utf8');
  await rename(tempPath, catalogPath);
  return updated;
}

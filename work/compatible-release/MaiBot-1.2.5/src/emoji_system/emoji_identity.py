"""经过人工核对的角色表情索引与离线匹配，不从模型描述猜测角色。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import json
import re


CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "emoji" / "character_catalog.json"


@dataclass(frozen=True)
class CharacterEmoji:
    character_name: str
    name: str
    description: str
    tags: Tuple[str, ...]


@dataclass(frozen=True)
class _Catalog:
    aliases: Dict[str, str]
    stickers: Dict[str, CharacterEmoji]


_catalog_cache: Optional[Tuple[Path, int, int, _Catalog]] = None
_STYLE_TAGS = frozenset(("可爱", "萌", "萌萌", "q版", "二次元", "少女", "银白", "白发", "蓝眼", "龙娘", "猫娘"))
_ACTIONS = frozenset((
    "跳舞", "跳芭蕾", "游泳", "潜水", "飞翔", "飞行", "挥手", "招手", "抱抱", "拥抱", "亲亲", "亲吻",
    "鞠躬", "睡觉", "吃饭", "喝水", "摸头", "打滚", "捂脸", "鼓掌", "点赞", "哭泣", "道歉", "敬礼", "打招呼",
))
_NEGATION = re.compile(r"(?:明确)?(?:不是|不要|不想要|不能是|别用|排除|非(?!常))([^，,。；;！!？?\n]*)")


def _normalize(text: str) -> str:
    return str(text).strip().lower()


def _load_catalog() -> _Catalog:
    """按文件时间缓存；缺少可选索引视为空，损坏索引明确报错。"""
    global _catalog_cache
    try:
        stat = CATALOG_PATH.stat()
    except FileNotFoundError:
        _catalog_cache = None
        return _Catalog({}, {})
    key = (CATALOG_PATH, stat.st_mtime_ns, stat.st_size)
    if _catalog_cache is not None and _catalog_cache[:3] == key:
        return _catalog_cache[3]
    try:
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("characters"), dict):
            raise ValueError("必须包含 version=1 和 characters 对象")
        aliases: Dict[str, str] = {}
        stickers: Dict[str, CharacterEmoji] = {}
        for owner, character in raw["characters"].items():
            if not isinstance(owner, str) or not owner.strip() or not isinstance(character, dict):
                raise ValueError("角色名称或角色条目无效")
            names = character.get("aliases", [])
            if not isinstance(names, list) or any(not isinstance(v, str) or not v.strip() for v in names):
                raise ValueError(f"{owner} 的 aliases 必须是非空字符串列表")
            for name in [owner, *names]:
                alias = _normalize(name)
                if alias in aliases and aliases[alias] != owner:
                    raise ValueError(f"角色别名重复: {name}")
                aliases[alias] = owner
            items = character.get("stickers")
            if not isinstance(items, dict):
                raise ValueError(f"{owner} 的 stickers 必须是对象")
            for file_hash, item in items.items():
                if not re.fullmatch(r"[0-9a-f]{64}", file_hash) or not isinstance(item, dict):
                    raise ValueError(f"{owner} 的表情 SHA256 或条目无效")
                if file_hash in stickers:
                    raise ValueError(f"同一表情不能登记给多个角色: {file_hash}")
                if any(not isinstance(item.get(k), str) or not item[k].strip() for k in ("name", "description")):
                    raise ValueError(f"{owner} 的表情缺少 name/description")
                tags = item.get("tags")
                if not isinstance(tags, list) or any(not isinstance(v, str) or not v.strip() for v in tags):
                    raise ValueError(f"{owner} 的表情 tags 无效")
                stickers[file_hash] = CharacterEmoji(owner, item["name"], item["description"], tuple(tags))
        catalog = _Catalog(aliases, stickers)
    except (ValueError, TypeError, OSError) as exc:
        raise ValueError(f"角色表情索引读取失败 {CATALOG_PATH}: {exc}") from exc
    _catalog_cache = (*key, catalog)
    return catalog


def lookup_character_emoji(file_hash: str, character_name: Optional[str] = None) -> Optional[CharacterEmoji]:
    """只返回人工登记、哈希精确一致的实际外观和文案。"""
    catalog = _load_catalog()
    sticker = catalog.stickers.get(file_hash)
    if sticker is None:
        return None
    if character_name is not None and sticker.character_name != catalog.aliases.get(_normalize(character_name)):
        return None
    return sticker


def _split_request(request: str) -> Tuple[str, str]:
    text = _normalize(request)
    negatives = "，".join(match.group(1) for match in _NEGATION.finditer(text))
    return _NEGATION.sub("，", text), negatives


def requests_animated_emoji(request: str) -> bool:
    """明确要求动图时由发送池按原始格式过滤，不能拿静图替代。"""
    positive, _ = _split_request(request)
    return bool(re.search(r"gif|动图|动画表情", positive))


def resolve_character_request(
    request: str, current_character_name: str, character_name: Optional[str] = None
) -> Optional[str]:
    """解析硬性角色约束；未登记的显式角色仍保留约束，防止退回全库。"""
    catalog = _load_catalog()
    if character_name is not None:
        return catalog.aliases.get(_normalize(character_name), character_name.strip())
    positive, _ = _split_request(request)
    owners = {owner for alias, owner in catalog.aliases.items() if alias in positive}
    current_name = _normalize(current_character_name)
    if current_name and current_name in positive:
        owners.add(catalog.aliases.get(current_name, current_character_name.strip()))
    if len(owners) > 1:
        raise ValueError("表情请求同时指定多个角色，无法确定要发送的角色")
    if owners:
        return next(iter(owners))
    if any(word in positive for word in ("本人", "自己", "专属", "你的表情", "你的图")):
        return catalog.aliases.get(_normalize(current_character_name), current_character_name.strip())
    return None


def _caption_terms(caption: str) -> Sequence[str]:
    normalized = _normalize(caption)
    terms = [normalized]
    # “来了”可以命中图中文字“来了来了”，但不做任意编辑距离猜测。
    midpoint = len(normalized) // 2
    if midpoint >= 2 and normalized[:midpoint] == normalized[midpoint:]:
        terms.append(normalized[:midpoint])
    return terms


def _generic_character_request(positive: str, catalog: _Catalog, scope: str) -> bool:
    """只允许没有具体动作要求的自身表情请求在角色内自由选图。"""
    residual = positive
    words = [alias for alias, owner in catalog.aliases.items() if owner == scope]
    words += [
        scope.lower(), "表情包", "表情", "本人", "自己", "专属", "看看", "看一下", "我想看", "想看", "看", "给我",
        "发一张", "发个", "发一个", "来一张", "来个", "一张", "一个", "这次", "真正", "明确", "就是", "形象", "角色",
        "q版", "二次元", "银白色", "银白", "白色", "白发", "长发", "蓝眼", "蓝瞳", "龙角", "龙尾", "龙娘",
        "少女", "可爱", "萌萌", "可爱的", "动画表情", "动图", "gif", "你", "我", "的", "是", "要", "请", "~", "～",
    ]
    for word in sorted(set(words), key=len, reverse=True):
        residual = residual.replace(word, "")
    return not re.search(r"[\w\u4e00-\u9fff]", residual)


def score_emoji_candidates(
    request: str,
    candidates: Sequence[Tuple[str, Sequence[str]]],
    *,
    current_character_name: str,
    character_name: Optional[str] = None,
) -> List[Tuple[str, float]]:
    """从可发送池评分；角色素材只使用人工标签，使用次数不参与语义排序。"""
    catalog = _load_catalog()
    scope = resolve_character_request(request, current_character_name, character_name)
    positive, negative = _split_request(request)
    if not positive.strip(" ，,。"):
        return []
    alternatives = re.split(r"或者|或是|或(?!许|然)", positive)
    if len(alternatives) > 1:
        # “晚安或捂脸”是备选方案；每个分支独立满足动作/文案要求，仍共享角色和否定约束。
        scores: Dict[str, float] = {}
        exclusions = "".join(f"，不要{term}" for term in negative.split("，") if term)
        for alternative in alternatives:
            if not alternative.strip():
                continue
            for file_hash, score in score_emoji_candidates(
                alternative + exclusions, candidates,
                current_character_name=current_character_name, character_name=scope,
            ):
                scores[file_hash] = max(scores.get(file_hash, 0.0), score)
        return list(scores.items())
    pool: List[Tuple[str, Sequence[str], Sequence[str]]] = []
    requested_actions = {action for action in _ACTIONS if action in positive}
    explicit_caption = re.search(
        r"(?:文案|文字|写着|说)(?:是|为|一句|声)?[：:\s]*[“「\"]([^”」\"，,。；;]+)[”」\"]", positive
    )
    for file_hash, database_tags in candidates:
        sticker = catalog.stickers.get(file_hash)
        if scope is not None and (sticker is None or sticker.character_name != scope):
            continue
        tags = sticker.tags if sticker else database_tags
        if sticker:
            # 动作可以来自人工核对的可见外观描述，绝不从数据库旧描述猜角色。
            tags = (*tags, *(action for action in _ACTIONS if action in sticker.description))
        captions = _caption_terms(sticker.name) if sticker else ()
        pool.append((file_hash, tuple(_normalize(t) for t in tags if t), captions))

    # 词汇来自完整索引（包括暂时禁用的素材），避免请求的动作不在池时被“可爱”等词替代。
    known_tags = {t for _, tags, _ in pool for t in tags}
    for sticker in catalog.stickers.values():
        known_tags.update(_normalize(t) for t in sticker.tags)
        known_tags.update(_caption_terms(sticker.name))
    identity_terms = set(catalog.aliases) | _STYLE_TAGS
    requested = {tag for tag in known_tags if tag and tag in positive and tag not in identity_terms}
    # 只保留更完整的词，避免“晚安”同时命中被拆出来的“安”。
    requested = {tag for tag in requested if not any(tag != other and tag in other for other in requested)}
    animated = requests_animated_emoji(request)
    requested_styles = {tag for tag in known_tags & _STYLE_TAGS if tag in positive}
    generic = (scope is not None or animated) and not requested and _generic_character_request(positive, catalog, scope or "")
    scored: List[Tuple[str, float]] = []
    for file_hash, tags, captions in pool:
        terms = set(tags) | set(captions)
        if negative and any(term in negative for term in terms if term):
            continue
        if requested_actions and not requested_actions.issubset(terms):
            continue
        if explicit_caption and not any(explicit_caption.group(1) in caption for caption in captions):
            continue
        caption_hits = [caption for caption in captions if caption and caption in positive]
        tag_hits = requested & terms
        if requested and not tag_hits and not caption_hits:
            continue
        if caption_hits:
            score = 10000.0 + max(len(caption) for caption in caption_hits)
        elif tag_hits:
            score = float(sum(len(tag) for tag in tag_hits))
        elif generic:
            score = 1.0 if not animated or not requested_styles or requested_styles.issubset(terms) else 0.0
        elif scope is None and not requested:
            style_hits = {tag for tag in tags if tag in positive and tag in _STYLE_TAGS}
            # 一般情绪的单独“可爱”可匹配；“可爱地飞翔”等未知动作不能被它遮蔽。
            score = 1.0 if positive.strip() in style_hits else 0.0
        else:
            score = 0.0
        if score > 0:
            scored.append((file_hash, score))
    return scored

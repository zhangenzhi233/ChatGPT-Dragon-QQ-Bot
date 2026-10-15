"""有来源的待跟进事项与主动联系门控；不承担长期画像或发送。"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
import json
import re

from .policy import parse_iso

FOLLOWUP_STATUSES = {"pending", "resolved", "cancelled", "expired"}
MAX_FOLLOWUPS = 24
MAX_PENDING = 8


def reference_id(kind: str, value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return kind + "_" + sha256(payload.encode("utf-8")).hexdigest()[:16]


def topic_key(topic: str) -> str:
    return sha256(re.sub(r"\W", "", topic.lower()).encode("utf-8")).hexdigest()[:16]


def validate_followups(raw: Any) -> bool:
    if not isinstance(raw, dict) or len(raw) > MAX_FOLLOWUPS:
        return False
    for key, item in raw.items():
        if not isinstance(key, str) or not isinstance(item, dict) or item.get("item_id") != key:
            return False
        if item.get("status") not in FOLLOWUP_STATUSES or item.get("kind") not in {"user_issue", "bot_promise"}:
            return False
        for field in ("title", "source_message_id", "source_quote", "source_time"):
            if not isinstance(item.get(field), str) or not item[field] or len(item[field]) > 500:
                return False
        for field in ("source_time", "created_at", "not_before", "expires_at"):
            if parse_iso(item.get(field)) is None:
                return False
        if parse_iso(item["expires_at"]) <= parse_iso(item["not_before"]):
            return False
    return True


def expire_items(items: dict[str, Any], now: datetime) -> None:
    for item in items.values():
        if item["status"] == "pending" and parse_iso(item["expires_at"]) <= now:
            item["status"] = "expired"


def apply_updates(items: dict[str, Any], updates: list[Any], messages: list[dict[str, Any]], now: datetime) -> None:
    """模型只能以可核对的消息 ID + 原文片段提议变更；时间不会证明完成。"""
    expire_items(items, now)
    sources = {m["message_id"]: m for m in messages if m.get("message_id")}
    for update in updates[:8]:
        if not isinstance(update, dict):
            continue
        source_id = update.get("source_message_id")
        quote = update.get("source_quote")
        source = sources.get(source_id) if isinstance(source_id, str) else None
        if source is None or not isinstance(quote, str) or not 2 <= len(quote) <= 160 or quote not in source.get("text", ""):
            continue
        source_time = parse_iso(source.get("time"))
        if source_time is None or source_time > now or now - source_time > timedelta(days=7):
            continue
        operation = update.get("operation")
        item_id = update.get("item_id")
        if operation in {"resolve", "cancel"}:
            item = items.get(item_id) if isinstance(item_id, str) else None
            if item and item["status"] == "pending" and source.get("role") == "user" and source_time > parse_iso(item["source_time"]):
                item.update(status="resolved" if operation == "resolve" else "cancelled",
                            resolution_message_id=source_id, resolution_quote=quote, updated_at=now.isoformat())
            continue
        if operation != "add":
            continue
        if len(quote) < 4:
            continue
        kind = update.get("kind")
        if (kind, source.get("role")) not in {("user_issue", "user"), ("bot_promise", "bot")}:
            continue
        title = update.get("title")
        if not isinstance(title, str) or not 2 <= len(title.strip()) <= 80:
            continue
        # 同一来源片段只能生成一条；终态记录在保留期内也不能被重新打开。
        new_id = reference_id("fu", [source_id, quote])
        if new_id in items or sum(i["status"] == "pending" for i in items.values()) >= MAX_PENDING:
            continue
        if any(i["source_message_id"] == source_id for i in items.values()):
            continue
        delay = update.get("followup_after_minutes", 240)
        lifetime = update.get("expires_after_hours", 72)
        if type(delay) is not int or type(lifetime) is not int:
            continue
        # 以原消息时间为准，反复评估不会替旧事项续命；至少一小时后才适合跟进。
        not_before = source_time + timedelta(minutes=max(60, min(delay, 6 * 24 * 60)))
        expires = source_time + timedelta(hours=max(2, min(lifetime, 7 * 24)))
        if expires <= now or not_before >= expires:
            continue
        items[new_id] = {
            "item_id": new_id, "title": title.strip(), "kind": kind, "status": "pending",
            "source_message_id": source_id, "source_quote": quote, "source_time": source_time.isoformat(),
            "created_at": now.isoformat(), "not_before": not_before.isoformat(), "expires_at": expires.isoformat(),
        }
    # 先保留所有 pending，再保留最近终态；最多八条待办，避免上下文膨胀。
    if len(items) > MAX_FOLLOWUPS:
        terminal = [key for key, item in items.items() if item["status"] != "pending"]
        for key in terminal[:len(items) - MAX_FOLLOWUPS]:
            del items[key]


def gate_decision(decision: Any, context: dict[str, Any], state: Any, now: datetime) -> tuple[bool, str]:
    """核实联系依据、待办有效期及近期重复；不放宽既有次数和静默限制。"""
    kind, ref = decision.basis_kind, decision.basis_id
    followup_id = ""
    if kind == "followup":
        item = state.followups.get(ref)
        if not item or item["status"] != "pending" or not (parse_iso(item["not_before"]) <= now < parse_iso(item["expires_at"])):
            return False, "待跟进事项尚未到时、已结束或已过期"
        followup_id = ref
    elif kind == "chat":
        if not any(m.get("message_id") == ref and m.get("role") == "user" for m in context["chat"].messages):
            return False, "聊天来源无法核实"
        followup_id = next((key for key, item in state.followups.items()
                            if item["source_message_id"] == ref and item["status"] == "pending"), "")
        if any(item["source_message_id"] == ref and item["status"] != "pending" for item in state.followups.values()):
            return False, "来源事项已经结束"
        if followup_id and not (parse_iso(state.followups[followup_id]["not_before"]) <= now
                                < parse_iso(state.followups[followup_id]["expires_at"])):
            return False, "来源事项尚未到跟进时间"
    elif kind == "feed":
        if not any(reference_id("feed", feed) == ref for feed in context.get("feeds") or []):
            return False, "空间来源无法核实"
    elif kind == "news":
        news = context.get("news")
        if news is None or not any(reference_id("news", item.link) == ref for item in news.items):
            return False, "新闻来源无法核实"
    elif kind != "natural" or ref:
        return False, "缺少有效联系依据"
    key = topic_key(decision.topic or decision.intent)
    for record in state.attempts.values():
        if followup_id and record.followup_id == followup_id and record.status != "skipped":
            last_user = parse_iso(context["chat"].last_user_at)
            if last_user is None or last_user <= parse_iso(record.decided_at):
                return False, "上次跟进后没有新的用户反馈"
        age = now - parse_iso(record.decided_at)
        if not timedelta(0) <= age < timedelta(hours=72):
            continue
        if record.status == "skipped":
            continue
        if record.topic_key and record.topic_key == key:
            return False, "近期已经尝试过同一话题"
        if ref and record.basis_kind == kind and record.basis_id == ref:
            return False, "同一来源近期已联系或结果不明"
        if followup_id and record.followup_id == followup_id:
            return False, "同一事项近期已尝试跟进"
        if kind == "natural" and record.basis_kind == "natural" and age < timedelta(hours=24):
            return False, "自然问候每日最多一次"
    decision.followup_id = followup_id
    return True, ""


def context_projection(state: Any) -> dict[str, Any]:
    return {
        "followups": list(state.followups.values()),
        "recent_contacts": [
            {"topic": record.intent, "basis_kind": record.basis_kind, "basis_id": record.basis_id,
             "at": record.decided_at, "delivery_status": record.delivery_status}
            for record in list(state.attempts.values())[-12:] if record.status != "skipped"
        ],
    }

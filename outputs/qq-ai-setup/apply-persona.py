#!/usr/bin/env python3
"""同步昵称、人设和图文回复开关，保留其他 MaiBot 配置。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import argparse
import subprocess
import sys
import tomllib

import tomlkit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).with_name("人设设置.toml")
CONFIG_PATH = PROJECT_ROOT / "work/compatible-release/MaiBot-1.2.5/config/bot_config.toml"
BACKUP_DIR = PROJECT_ROOT / "work/qq-ai-local/persona-backups"
FIELDS = {
    "bot": ("nickname",),
    "personality": ("personality", "behavior_style", "reply_style"),
    "experimental": ("enable_rich_reply",),
}
# 用户要求停用旧人设，同时清空默认备用语气，防止以后随机切回。
LEGACY_STYLE_RESET = {"multiple_reply_style": [], "multiple_probability": 0.0}


class PersonaError(ValueError):
    """可在不输出配置内容的情况下向用户说明的人设错误。"""


def parse_toml(data: bytes, label: str) -> dict[str, Any]:
    try:
        return tomllib.loads(data.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise PersonaError(f"{label}格式无效，请检查引号和字段名；尚未应用。") from exc


def persona_values(document: dict[str, Any], *, strict: bool) -> dict[str, dict[str, Any]]:
    if strict and set(document) != set(FIELDS):
        raise PersonaError("人设设置只允许 [bot]、[personality] 和 [experimental] 三个分组。")
    values: dict[str, dict[str, Any]] = {}
    for section, fields in FIELDS.items():
        table = document.get(section)
        if not isinstance(table, dict) or (strict and set(table) != set(fields)):
            raise PersonaError(f"[{section}] 字段不完整或包含额外字段，请参照编辑说明。")
        values[section] = {}
        for field in fields:
            value = table.get(field)
            if section == "experimental":
                if type(value) is not bool:
                    raise PersonaError("enable_rich_reply 必须填写 true 或 false，不加引号。")
                values[section][field] = value
                continue
            if not isinstance(value, str) or not value.strip():
                raise PersonaError(f"{section}.{field} 必须是非空文字。")
            value = value.strip()
            if len(value) > 24000:
                raise PersonaError(f"{section}.{field} 超过 24000 字，请适当缩短。")
            if field == "nickname" and (len(value) > 80 or "\n" in value or "\r" in value):
                raise PersonaError("昵称必须是一行文字，长度不超过 80 字。")
            values[section][field] = value
    return values


def apply_values(
    config_path: Path,
    values: dict[str, dict[str, Any]],
    backup_dir: Path,
) -> dict[str, Any]:
    original_bytes = config_path.read_bytes()
    original = parse_toml(original_bytes, "MaiBot 运行配置")
    expected = deepcopy(original)
    for section, fields in FIELDS.items():
        if not isinstance(expected.get(section), dict) or not all(field in expected[section] for field in fields):
            raise PersonaError(f"运行配置缺少 [{section}] 必要字段，尚未应用。")
        for field in fields:
            expected[section][field] = values[section][field]
    expected["personality"].update(deepcopy(LEGACY_STYLE_RESET))
    if expected == original:
        return {"changed": False, "backup": None}

    document = tomlkit.parse(original_bytes.decode("utf-8-sig"))
    for section, fields in FIELDS.items():
        for field in fields:
            value = values[section][field]
            document[section][field] = tomlkit.string(value, multiline=field != "nickname") if isinstance(value, str) else value
    for field, value in LEGACY_STYLE_RESET.items():
        document["personality"][field] = value
    updated_bytes = tomlkit.dumps(document).encode("utf-8")
    if parse_toml(updated_bytes, "拟应用配置") != expected:
        raise PersonaError("校验发现人设之外的配置变化，已停止，原配置未修改。")
    if config_path.read_bytes() != original_bytes:
        raise PersonaError("运行配置刚被其他程序修改，请核对后重新应用。")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S-%f")
    backup_path = backup_dir / f"bot_config-{timestamp}-before-persona.toml"
    with backup_path.open("xb") as backup_file:
        backup_file.write(original_bytes)

    temporary_path = config_path.with_name(f".bot_config-persona-{uuid4().hex}.tmp")
    try:
        with temporary_path.open("xb") as temporary_file:
            temporary_file.write(updated_bytes)
        if config_path.read_bytes() != original_bytes:
            raise PersonaError("运行配置刚被其他程序修改，已停止同步。")
        temporary_path.replace(config_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    if parse_toml(config_path.read_bytes(), "保存后的运行配置") != expected:
        raise PersonaError("保存后配置发生变化，请核对运行配置和备份。")
    return {"changed": True, "backup": str(backup_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="应用 ChatGPT 的昵称和人设，自动备份旧配置")
    parser.add_argument("--check", action="store_true", help="只检查人设文件，不修改运行配置")
    parser.add_argument("--edit", action="store_true", help="用记事本打开可编辑的人设文件")
    parser.add_argument("--restore", type=Path, metavar="BACKUP_FILE", help="仅从指定备份恢复昵称和人设")
    arguments = parser.parse_args()
    if arguments.edit:
        subprocess.Popen(["notepad.exe", str(SOURCE_PATH)])
        return 0
    if arguments.restore is not None:
        backup_path = arguments.restore.resolve()
        if not backup_path.is_relative_to(BACKUP_DIR.resolve()):
            raise PersonaError("只能从本项目 persona-backups 目录中的备份恢复人设。")
        values = persona_values(parse_toml(backup_path.read_bytes(), "人设备份"), strict=False)
    else:
        values = persona_values(parse_toml(SOURCE_PATH.read_bytes(), "人设设置文件"), strict=True)

    if arguments.check:
        print("人设文件校验通过；运行配置未修改。")
        return 0
    result = apply_values(CONFIG_PATH, values, BACKUP_DIR)
    if not result["changed"]:
        print("人设与当前运行配置一致，无需重复应用。")
        return 0
    print(f"人设已写入配置，昵称：{values['bot']['nickname']}")
    print("回复附带表情包：" + ("已开启" if values["experimental"]["enable_rich_reply"] else "已关闭"))
    print(f"原配置备份：{result['backup']}")
    print("运行中的 MaiBot 会尝试热加载。请用新的私聊观察人设表现。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PersonaError as exc:
        print(f"人设未完成应用：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except (OSError, ValueError, tomlkit.exceptions.ParseError) as exc:
        print(f"人设未完成应用：文件读写或格式错误（{type(exc).__name__}），请核对文件与备份。", file=sys.stderr)
        raise SystemExit(2) from exc

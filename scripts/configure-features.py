"""Configure optional features for this installation without sending messages."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import tomlkit

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "work/compatible-release/MaiBot-1.2.5/plugins"


def configure(name: str, enabled: bool, setup: dict[str, object]) -> None:
    folder = PLUGINS / name
    destination = folder / "config.toml"
    source = destination if destination.exists() else folder / "config.example.toml"
    document = tomlkit.parse(source.read_text(encoding="utf-8"))
    document["plugin"]["enabled"] = enabled
    owner = str(setup.get("ownerQQ", ""))
    bot = str(setup.get("botQQ", ""))
    if enabled and (not re.fullmatch(r"[1-9][0-9]{4,11}", owner) or not re.fullmatch(r"[1-9][0-9]{4,11}", bot) or owner == bot):
        raise ValueError("请先在本机设置页保存有效且不同的主 QQ 与机器人小号。")
    if name == "SilverDragonVoice":
        document["access"]["allowed_user_ids"] = [owner] if enabled else []
    else:
        document["target"]["main_qq"] = owner if enabled else ""
        document["target"]["bot_qq"] = bot if enabled else ""
    temporary = destination.with_suffix(".toml.tmp")
    temporary.write_text(tomlkit.dumps(document), encoding="utf-8")
    temporary.replace(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="设置私聊语音和主动聊天；不会直接发送消息。")
    parser.add_argument("--voice", choices=("on", "off"))
    parser.add_argument("--companion", choices=("on", "off"))
    args = parser.parse_args()
    if args.voice is None and args.companion is None:
        parser.error("请指定 --voice on/off 或 --companion on/off")
    setup_file = ROOT / "work/qq-ai-local/setup.json"
    setup = json.loads(setup_file.read_text(encoding="utf-8")) if setup_file.exists() else {}
    for name, setting in (("SilverDragonVoice", args.voice), ("SilverDragonCompanion", args.companion)):
        if setting is not None:
            configure(name, setting == "on", setup)
            print(f"{name}: {'启用' if setting == 'on' else '禁用'}。请在 MaiBot 插件管理中加载或重载插件。")


if __name__ == "__main__":
    main()

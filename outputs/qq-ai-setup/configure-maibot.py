#!/usr/bin/env python3
"""为本机 QQ AI 生成并更新 MaiBot 1.2.5 配置。

此工具只读取本机设置页保存的 QQ 号码和模型选择。不会启动 QQ、NapCat
或 MaiBot，也不会读取 ChatGPT 授权凭据。
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomlkit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAIBOT_ROOT = PROJECT_ROOT / "work" / "compatible-release" / "MaiBot-1.2.5"
LOCAL_ROOT = PROJECT_ROOT / "work" / "qq-ai-local"
SETUP_PATH = LOCAL_ROOT / "setup.json"
BRIDGE_KEY_PATH = LOCAL_ROOT / "bridge-key.txt"
NAPCAT_TOKEN_PATH = LOCAL_ROOT / "napcat-token.txt"
AGREEMENT_RECORD_PATH = LOCAL_ROOT / "maibot-1.2.5-agreement-confirmed.json"
CONFIG_DIR = MAIBOT_ROOT / "config"
BOT_CONFIG_PATH = CONFIG_DIR / "bot_config.toml"
MODEL_CONFIG_PATH = CONFIG_DIR / "model_config.toml"
POLICY_PATH = CONFIG_DIR / "adapter_policy.toml"
NAPCAT_CONFIG_PATH = MAIBOT_ROOT / "plugins" / "Napcat_Adapter" / "config.toml"
HELLO_CONFIG_PATH = MAIBOT_ROOT / "plugins" / "hello_world_plugin" / "config.toml"
QQ_ID_RE = re.compile(r"^[1-9][0-9]{4,11}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
NAPCAT_PLUGIN_ID = "maibot-team.napcat-adapter"


class ConfigurationError(RuntimeError):
    """用户可修正的本机配置问题。"""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError("尚未完成本机设置页保存") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError("本机设置文件格式无效") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("本机设置文件必须是对象")
    return value


def required_qq(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not QQ_ID_RE.fullmatch(normalized):
        raise ConfigurationError(f"本机设置中的 {field_name} 无效")
    return normalized


def optional_qq(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if not QQ_ID_RE.fullmatch(normalized):
        raise ConfigurationError(f"本机设置中的 {field_name} 无效")
    return normalized


def selected_model(value: Any) -> str:
    normalized = str(value or "").strip()
    if not MODEL_RE.fullmatch(normalized):
        raise ConfigurationError("尚未从已授权的 ChatGPT 模型列表选择有效模型")
    return normalized


def secret_file(path: Path) -> str:
    """首次生成仅供本机回环进程使用的随机密钥。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
        raise ConfigurationError(f"本机密钥文件无效: {path.name}")
    value = secrets.token_urlsafe(36)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(value + "\n", encoding="utf-8")
    temporary.replace(path)
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_and_record_agreement(setup: dict[str, Any]) -> None:
    if setup.get("agreementsAccepted") is not True:
        raise ConfigurationError("本机设置页尚未确认 MaiBot 许可协议和隐私条款")

    accepted_at = str(setup.get("agreementsAcceptedAt") or "").strip()
    try:
        datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigurationError("本机设置页缺少有效的协议确认时间") from exc

    expected = {
        "EULA.md": sha256(MAIBOT_ROOT / "EULA.md"),
        "PRIVACY.md": sha256(MAIBOT_ROOT / "PRIVACY.md"),
    }
    saved_hashes = setup.get("agreementHashes")
    if not isinstance(saved_hashes, dict) or not saved_hashes:
        raise ConfigurationError("请在本机设置页阅读并确认当前 MaiBot 协议，缺少协议哈希记录。")
    if isinstance(saved_hashes, dict) and saved_hashes:
        actual = {name: str(saved_hashes.get(name) or "").lower() for name in expected}
        if actual != expected:
            raise ConfigurationError("已确认的协议文件与当前 MaiBot 1.2.5 协议不一致；请重新在设置页阅读并确认")

    # Earlier local setup pages stored the acceptance timestamp before adding
    # agreementHashes. The page served the 1.2.5 files directly, so retain a
    # local evidence record instead of silently accepting a different license.
    record = {
        "format": "qq-ai-local-maibot-agreement-v1",
        "maibotVersion": "1.2.5",
        "acceptedAt": accepted_at,
        "acceptedVia": "local-setup-page",
        "agreementHashes": expected,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    temporary = AGREEMENT_RECORD_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(AGREEMENT_RECORD_PATH)


def load_maibot_config(path: Path, config_class: Any, version: str, *, override_repr: bool) -> Any:
    sys.path.insert(0, str(MAIBOT_ROOT))
    from src.config.config import load_config_from_file  # noqa: PLC0415

    config, _ = load_config_from_file(config_class, path, version, override_repr)
    return config


def write_maibot_config(config: Any, path: Path, version: str, *, override_repr: bool) -> None:
    from src.config.config import write_config_to_file  # noqa: PLC0415

    write_config_to_file(config, path, version, override_repr)


def update_model_config(model_name: str, bridge_key: str, reasoning_effort: str | None = None) -> None:
    sys.path.insert(0, str(MAIBOT_ROOT))
    from src.config.config import MODEL_CONFIG_VERSION, ModelConfig  # noqa: PLC0415
    from src.config.model_configs import APIProvider, ModelInfo  # noqa: PLC0415

    config = load_maibot_config(MODEL_CONFIG_PATH, ModelConfig, MODEL_CONFIG_VERSION, override_repr=True)
    provider_name = "ChatGPTPlusLocal"
    existing_provider = next((item for item in config.api_providers if item.name == provider_name), None)
    provider_values = {
        "name": provider_name,
        "base_url": "http://127.0.0.1:8711/v1",
        "api_key": bridge_key,
        "client_type": "openai_responses",
        "auth_type": "bearer",
        "max_retry": 0,
        "timeout": 180,
        "retry_interval": 5,
    }
    if existing_provider is None:
        config.api_providers.append(APIProvider(**provider_values))
    else:
        for key, value in provider_values.items():
            setattr(existing_provider, key, value)

    existing_model = next((item for item in config.models if item.name == model_name), None)
    # Saving the model in the setup page must retain an applied speed/quality
    # setting rather than silently returning to the provider's default effort.
    extra_params = deepcopy(existing_model.extra_params) if existing_model is not None else {}
    if reasoning_effort is not None:
        reasoning = extra_params.setdefault("reasoning", {})
        if not isinstance(reasoning, dict):
            raise ConfigurationError("现有 reasoning 参数格式无效，尚未更新模型配置")
        reasoning["effort"] = reasoning_effort
    model_values = {
        "model_identifier": model_name,
        "name": model_name,
        "api_provider": provider_name,
        "price_in": 0.0,
        "price_out": 0.0,
        "send_temperature": False,
        "force_stream_mode": True,
        "visual": True,
        "extra_params": extra_params,
    }
    if existing_model is None:
        config.models.append(ModelInfo(**model_values))
    else:
        for key, value in model_values.items():
            setattr(existing_model, key, value)

    # All LLM, vision and emoji decisions use the one model selected in the
    # local page. Embedding remains disabled: bge-m3 can be added later only
    # after the local bridge exposes /v1/embeddings.
    for task_name in type(config.model_task_config).model_fields:
        task = getattr(config.model_task_config, task_name)
        if not hasattr(task, "model_list"):
            continue
        if task_name == "embedding":
            task.model_list = []
        else:
            task.model_list = [model_name]
    write_maibot_config(config, MODEL_CONFIG_PATH, MODEL_CONFIG_VERSION, override_repr=True)


def update_bot_config(bot_qq: str) -> None:
    sys.path.insert(0, str(MAIBOT_ROOT))
    from src.config.config import CONFIG_VERSION, Config  # noqa: PLC0415

    config = load_maibot_config(BOT_CONFIG_PATH, Config, CONFIG_VERSION, override_repr=False)
    config.bot.platform = "qq"
    config.bot.qq_account = bot_qq
    config.telemetry.enable = False
    config.webui.host = ["127.0.0.1"]
    config.webui.port = 8011
    config.chat.reply_style.enable_reply_quote = False
    config.chinese_typo.enable_correction_quote = False
    config.debug.enable_console_input = False
    config.plugin.permission = []
    write_maibot_config(config, BOT_CONFIG_PATH, CONFIG_VERSION, override_repr=False)


def write_toml(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(tomlkit.dumps(document), encoding="utf-8")
    temporary.replace(path)


def update_napcat_plugin(owner_qq: str, group_qq: str, token: str) -> None:
    document = tomlkit.parse(NAPCAT_CONFIG_PATH.read_text(encoding="utf-8")) if NAPCAT_CONFIG_PATH.exists() else tomlkit.document()
    document["plugin"] = {"enabled": True, "enable_private_chat_tool": False, "config_version": "0.1.0"}
    document["napcat_server"] = {
        "host": "127.0.0.1",
        "port": 3011,
        "token": token,
        "heartbeat_interval": 30,
        "reconnect_delay_sec": 5,
        "action_timeout_sec": 15,
        "connection_id": "",
    }
    document["chat"] = {
        "enable_chat_list_filter": True,
        "show_dropped_chat_list_messages": False,
        "group_list_type": "whitelist",
        "group_list": [group_qq] if group_qq else [],
        "private_list_type": "whitelist",
        "private_list": [owner_qq],
        "ban_user_id": [],
        "ban_qq_bot": True,
    }
    document["notice"] = {"enabled": False}
    document["filters"] = {"ignore_self_message": True, "regex_filter_enabled": False, "regex_filter_patterns": []}
    write_toml(NAPCAT_CONFIG_PATH, document)


def update_adapter_policy(bot_qq: str, owner_qq: str, group_qq: str) -> None:
    document = tomlkit.document()
    document["defaults"] = {
        "private": {"default_action": "block", "allow_ids": []},
        "group": {"default_action": "block", "allow_ids": []},
    }
    adapters = tomlkit.aot()
    adapter = tomlkit.table()
    adapter["plugin_id"] = NAPCAT_PLUGIN_ID
    adapter["platform"] = "qq"
    adapter["account_id"] = bot_qq
    adapter["private"] = {"default_action": "block", "allow_ids": [owner_qq]}
    adapter["group"] = {"default_action": "block", "allow_ids": [group_qq] if group_qq else []}
    adapters.append(adapter)
    document["adapters"] = adapters
    write_toml(POLICY_PATH, document)


def disable_hello_world_plugin() -> None:
    document = tomlkit.parse(HELLO_CONFIG_PATH.read_text(encoding="utf-8")) if HELLO_CONFIG_PATH.exists() else tomlkit.document()
    document["plugin"] = {"enabled": False, "config_version": "2.0.0"}
    document["print_message"] = {"enabled": False}
    write_toml(HELLO_CONFIG_PATH, document)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 MaiBot 的本机 QQ AI 配置")
    parser.add_argument("--model-only", action="store_true", help="只更新模型提供商和任务模型映射")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh", "max"), help="设置当前 ChatGPT 模型的思考强度；未指定时保留已保存参数")
    arguments = parser.parse_args()
    if not MAIBOT_ROOT.is_dir():
        raise ConfigurationError("未找到兼容的 MaiBot 1.2.5 目录")

    setup = read_json(SETUP_PATH)
    model_name = selected_model(setup.get("selectedModel"))
    bridge_key = secret_file(BRIDGE_KEY_PATH)

    if arguments.model_only:
        update_model_config(model_name, bridge_key, arguments.reasoning_effort)
        print("模型配置已更新；运行中的 MaiBot 会通过配置文件监视器热重载模型配置。")
        return 0

    bot_qq = required_qq(setup.get("botQQ"), "机器人 QQ")
    owner_qq = required_qq(setup.get("ownerQQ"), "主 QQ")
    group_qq = optional_qq(setup.get("groupQQ"), "测试群号")
    if bot_qq == owner_qq:
        raise ConfigurationError("机器人 QQ 与主 QQ 不能相同")
    verify_and_record_agreement(setup)
    napcat_token = secret_file(NAPCAT_TOKEN_PATH)
    update_bot_config(bot_qq)
    update_model_config(model_name, bridge_key, arguments.reasoning_effort)
    update_napcat_plugin(owner_qq, group_qq, napcat_token)
    update_adapter_policy(bot_qq, owner_qq, group_qq)
    disable_hello_world_plugin()
    persona_spec = importlib.util.spec_from_file_location("public_apply_persona", Path(__file__).with_name("apply-persona.py"))
    persona_module = importlib.util.module_from_spec(persona_spec)
    persona_spec.loader.exec_module(persona_module)
    persona_source = Path(__file__).with_name("人设设置.toml")
    if not persona_source.exists():
        persona_source = Path(__file__).with_name("人设设置.example.toml")
    persona_module.apply_values(BOT_CONFIG_PATH, persona_module.persona_values(persona_module.parse_toml(persona_source.read_bytes(), "人设设置"), strict=True), LOCAL_ROOT / "persona-backups")
    print("MaiBot 本机配置已生成；尚未启动 QQ、NapCat 或 MaiBot。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigurationError as exc:
        print(f"配置未生成: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

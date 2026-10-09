from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest
import tomllib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_features", ROOT / "scripts/configure-features.py")
features = importlib.util.module_from_spec(spec)
spec.loader.exec_module(features)


@pytest.fixture
def plugin_root(tmp_path, monkeypatch):
    for name in ("SilverDragonVoice", "SilverDragonCompanion"):
        directory = tmp_path / name
        directory.mkdir()
        source = ROOT / "work/compatible-release/MaiBot-1.2.5/plugins" / name / "config.example.toml"
        (directory / "config.example.toml").write_bytes(source.read_bytes())
    monkeypatch.setattr(features, "PLUGINS", tmp_path)
    return tmp_path


@pytest.mark.parametrize("setup", ({}, {"ownerQQ": "1", "botQQ": "100002"}, {"ownerQQ": "100001", "botQQ": "100001"}))
def test_enable_rejects_missing_invalid_or_same_accounts(plugin_root, setup):
    with pytest.raises(ValueError):
        features.configure("SilverDragonVoice", True, setup)
    assert not (plugin_root / "SilverDragonVoice/config.toml").exists()


def test_voice_only_authorizes_this_installation_owner(plugin_root):
    features.configure("SilverDragonVoice", True, {"ownerQQ": "100001", "botQQ": "100002"})
    config = tomllib.loads((plugin_root / "SilverDragonVoice/config.toml").read_text(encoding="utf-8"))
    assert config["plugin"]["enabled"] is True
    assert config["access"]["allowed_user_ids"] == ["100001"]
    assert config["voice"]["voice"] == "zh-CN-XiaoxiaoNeural"


def test_disable_removes_proactive_target(plugin_root):
    features.configure("SilverDragonCompanion", True, {"ownerQQ": "100001", "botQQ": "100002"})
    features.configure("SilverDragonCompanion", False, {})
    config = tomllib.loads((plugin_root / "SilverDragonCompanion/config.toml").read_text(encoding="utf-8"))
    assert config["plugin"]["enabled"] is False
    assert config["target"]["main_qq"] == ""
    assert config["target"]["bot_qq"] == ""


def test_fresh_install_generates_complete_config_in_isolated_directory(tmp_path, monkeypatch):
    setup_dir = ROOT / "outputs/qq-ai-setup"
    monkeypatch.syspath_prepend(str(setup_dir))
    spec = importlib.util.spec_from_file_location("public_bot_configuration", setup_dir / "configure-maibot.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    private = tmp_path / "private"
    private.mkdir()
    config = tmp_path / "config"
    config.mkdir()
    filenames = {
        "SETUP_PATH": private / "setup.json",
        "BRIDGE_KEY_PATH": private / "bridge-key.txt",
        "NAPCAT_TOKEN_PATH": private / "napcat-token.txt",
        "AGREEMENT_RECORD_PATH": private / "agreement.json",
        "BOT_CONFIG_PATH": config / "bot_config.toml",
        "MODEL_CONFIG_PATH": config / "model_config.toml",
        "POLICY_PATH": config / "adapter_policy.toml",
        "NAPCAT_CONFIG_PATH": private / "napcat-config.toml",
        "HELLO_CONFIG_PATH": private / "hello-config.toml",
    }
    for name, path in filenames.items():
        monkeypatch.setattr(builder, name, path)
    monkeypatch.setattr(builder, "LOCAL_ROOT", private)
    monkeypatch.setattr(builder, "CONFIG_DIR", config)
    hashes = {name: hashlib.sha256((builder.MAIBOT_ROOT / name).read_bytes()).hexdigest() for name in ("EULA.md", "PRIVACY.md")}
    builder.SETUP_PATH.write_text(json.dumps({"botQQ": "100002", "ownerQQ": "100001", "groupQQ": "", "selectedModel": "fixture-model", "agreementsAccepted": True, "agreementsAcceptedAt": "2026-10-09T00:00:00Z", "agreementHashes": hashes}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["configure-maibot.py"])
    monkeypatch.chdir(tmp_path)
    assert builder.main() == 0
    bot_config = tomllib.loads(builder.BOT_CONFIG_PATH.read_text(encoding="utf-8"))
    model_config = tomllib.loads(builder.MODEL_CONFIG_PATH.read_text(encoding="utf-8"))
    adapter = tomllib.loads(builder.NAPCAT_CONFIG_PATH.read_text(encoding="utf-8"))
    assert bot_config["bot"]["nickname"] == "银白龙"
    assert bot_config["webui"]["port"] == 8011
    assert adapter["chat"]["private_list"] == ["100001"]
    assert adapter["chat"]["group_list"] == []
    assert any(provider["base_url"] == "http://127.0.0.1:8711/v1" for provider in model_config["api_providers"])

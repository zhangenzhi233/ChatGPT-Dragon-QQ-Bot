"""Read-only validation of Git publication candidates and selected assets."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"}
REQUIRED = (
    "README.md", ".gitignore", "LICENSE", "THIRD_PARTY_NOTICES.md", "Start.cmd", "Setup.cmd",
    "setup/install.ps1", "outputs/qq-ai-setup/server.mjs", "scripts/stop.ps1",
    "outputs/qq-ai-setup/人设设置.example.toml", "scripts/configure-features.py",
    "work/compatible-release/MaiBot-1.2.5/bot.py", "work/compatible-release/MaiBot-1.2.5/uv.lock",
    "work/compatible-release/MaiBot-1.2.5/src/common/personality_prompt.py",
    "work/compatible-release/MaiBot-1.2.5/src/emoji_system/emoji_identity.py",
    "work/official-sdk/sign-in-with-chatgpt-devkit-main/packages/local/src/raw-responses.ts",
    "work/official-sdk/sign-in-with-chatgpt-devkit-main/LICENSE",
    "work/compatible-release/MaiBot-1.2.5/plugins/Napcat_Adapter/plugin.py",
    "work/compatible-release/MaiBot-1.2.5/plugins/Napcat_Adapter/runtime/builder.py",
    "work/compatible-release/MaiBot-1.2.5/src/A_memorix/core/runtime/runtime_facade.py",
    "work/compatible-release/MaiBot-1.2.5/plugins/Maizone/plugin.py",
    "work/compatible-release/MaiBot-1.2.5/plugins/SilverDragonVoice/plugin.py",
    "work/compatible-release/MaiBot-1.2.5/plugins/SilverDragonVoice/config.example.toml",
    "work/compatible-release/MaiBot-1.2.5/plugins/SilverDragonCompanion/plugin.py",
    "work/compatible-release/MaiBot-1.2.5/plugins/SilverDragonCompanion/config.example.toml",
)


def publication_files() -> list[Path]:
    if (ROOT / ".git").exists():
        result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, check=True)
        return [ROOT / name for name in sorted(set(result.stdout.decode("utf-8").split("\0"))) if name]
    # Downloaded source ZIP has no .git: apply the same runtime exclusions.
    files = []
    for file in ROOT.rglob("*"):
        if not file.is_file() or any(part in IGNORED_PARTS or part.endswith(".egg-info") for part in file.relative_to(ROOT).parts):
            continue
        relative = file.relative_to(ROOT)
        if relative.as_posix().startswith(("runtime/", "work/qq-ai-local/", "work/compatible-release/MaiBot-1.2.5/config/old/")) or file.name in {"config.toml", "bot_config.toml", "model_config.toml", "adapter_policy.toml", "人设设置.toml", "eula.confirmed", "privacy.confirmed"}:
            continue
        # Upstream benchmark fixtures are source data; local account databases are not.
        fixture_data = relative.as_posix().startswith("work/compatible-release/MaiBot-1.2.5/pytests/A_memorix_test/data/")
        if any(part in {"data", "logs", "temp"} for part in relative.parts) and not fixture_data:
            continue
        if file.suffix in {".pyc", ".log", ".pid", ".db", ".jsonl", ".tmp"}:
            continue
        files.append(file)
    return files


def verify() -> dict[str, object]:
    issues = []
    files = publication_files()
    included = {file.relative_to(ROOT).as_posix() for file in files}
    for required in REQUIRED:
        if not (ROOT / required).is_file():
            issues.append({"file": required, "reason": "required-source-missing"})
        elif required not in included:
            issues.append({"file": required, "reason": "required-source-excluded-from-publication"})
    size = 0
    for file in files:
        relative = file.relative_to(ROOT).as_posix()
        if file.is_symlink() or not file.resolve().is_relative_to(ROOT.resolve()):
            issues.append({"file": relative, "reason": "external-symlink"})
            continue
        content = file.read_bytes()
        size += len(content)
        if len(content) > 100 * 1024 * 1024:
            issues.append({"file": relative, "reason": "github-file-too-large"})
        text = content.decode("utf-8-sig", errors="ignore")
        # Do not print the matching text, even when it looks like a credential.
        if re.search(r"[CD]:[/\\]+Users[/\\]+[^\s'\"]+[/\\]+Documents[/\\]+(?:Codex|ChatGPT)", text):
            issues.append({"file": relative, "reason": "fixed-private-workspace-path"})
        if re.search(r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}", text):
            issues.append({"file": relative, "reason": "possible-secret"})
        if file.suffix == ".py":
            try:
                ast.parse(text, filename=relative)
            except SyntaxError:
                issues.append({"file": relative, "reason": "python-syntax"})
    assets = []
    for manifest_file in (ROOT / "assets/stickers").glob("*/manifest.json"):
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest["count"] != len(manifest["stickers"]):
            issues.append({"file": manifest_file.relative_to(ROOT).as_posix(), "reason": "manifest-count"})
        for sticker in manifest["stickers"]:
            file = (manifest_file.parent / sticker["file"]).resolve()
            if not file.is_relative_to(manifest_file.parent.resolve()):
                issues.append({"file": manifest_file.relative_to(ROOT).as_posix(), "reason": "asset-path-escape"})
                continue
            data = file.read_bytes()
            if hashlib.sha256(data).hexdigest() != sticker["sha256"] or data[:8] != b"\x89PNG\r\n\x1a\n":
                issues.append({"file": file.relative_to(ROOT).as_posix(), "reason": "asset-hash-or-format"})
            assets.append(sticker["sha256"])
    if len(assets) != 29 or len(set(assets)) != 29:
        issues.append({"file": "assets/stickers", "reason": "expected-29-distinct-assets"})
    plugins = ROOT / "work/compatible-release/MaiBot-1.2.5/plugins"
    for name in ("SilverDragonVoice", "SilverDragonCompanion"):
        example = tomllib.loads((plugins / name / "config.example.toml").read_text(encoding="utf-8"))
        if example["plugin"]["enabled"] is not False:
            issues.append({"file": name, "reason": "optional-feature-enabled-by-default"})
    return {"passed": not issues, "files": len(files), "bytes": size, "stickers": len(assets), "issues": issues}


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path

import json

import pytest

from src.common.i18n.manager import I18nManager
from src.common.i18n.loaders import DuplicateTranslationKeyError, load_locale_catalog


def write_locale_file(locales_root: Path, locale: str, file_name: str, payload: dict[str, object]) -> None:
    locale_dir = locales_root / locale
    locale_dir.mkdir(parents=True, exist_ok=True)
    file_path = locale_dir / file_name
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_t_falls_back_to_default_locale(tmp_path: Path) -> None:
    locales_root = tmp_path / "locales"
    write_locale_file(locales_root, "zh-CN", "core.json", {"greeting": "你好，{name}"})
    write_locale_file(locales_root, "en-US", "core.json", {})

    manager = I18nManager(locales_root=locales_root)

    assert manager.t("greeting", locale="en-US", name="Mai") == "你好，Mai"


def test_t_returns_key_when_missing_everywhere(tmp_path: Path) -> None:
    locales_root = tmp_path / "locales"
    write_locale_file(locales_root, "zh-CN", "core.json", {})
    write_locale_file(locales_root, "en-US", "core.json", {})

    manager = I18nManager(locales_root=locales_root)

    assert manager.t("missing.key", locale="en-US") == "missing.key"


def test_tn_uses_plural_rules(tmp_path: Path) -> None:
    locales_root = tmp_path / "locales"
    write_locale_file(
        locales_root,
        "en-US",
        "core.json",
        {
            "tasks.cancelled": {
                "one": "Cancelled {count} task",
                "other": "Cancelled {count} tasks",
            }
        },
    )

    manager = I18nManager(default_locale="en-US", locales_root=locales_root)

    assert manager.tn("tasks.cancelled", 1) == "Cancelled 1 task"
    assert manager.tn("tasks.cancelled", 2) == "Cancelled 2 tasks"


def test_load_locale_catalog_rejects_duplicate_keys(tmp_path: Path) -> None:
    locales_root = tmp_path / "locales"
    write_locale_file(locales_root, "zh-CN", "a.json", {"duplicate.key": "A"})
    write_locale_file(locales_root, "zh-CN", "b.json", {"duplicate.key": "B"})

    with pytest.raises(DuplicateTranslationKeyError):
        load_locale_catalog("zh-CN", locales_root)

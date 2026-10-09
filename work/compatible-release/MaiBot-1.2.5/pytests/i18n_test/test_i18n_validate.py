from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import json

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "i18n_validate.py"
MODULE_SPEC = spec_from_file_location("i18n_validate_script", SCRIPT_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
I18N_VALIDATE = module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(I18N_VALIDATE)


def write_locale_file(locales_root: Path, locale: str, file_name: str, payload: dict[str, object]) -> None:
    locale_dir = locales_root / locale
    locale_dir.mkdir(parents=True, exist_ok=True)
    (locale_dir / file_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_dashboard_locale_file(locales_root: Path, locale: str, payload: dict[str, object]) -> None:
    locales_root.mkdir(parents=True, exist_ok=True)
    (locales_root / f"{locale}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_validate_json_locales_rejects_han_characters_in_english_locale(tmp_path: Path) -> None:
    locales_root = tmp_path / "locales"
    write_locale_file(locales_root, "zh-CN", "core.json", {"consent.prompt": '输入"同意"继续'})
    write_locale_file(locales_root, "en-US", "core.json", {"consent.prompt": 'Type "confirmed" or "同意" to continue'})

    errors = I18N_VALIDATE.validate_json_locales(locales_root)

    assert any("consent.prompt" in error and "仍包含中文字符" in error for error in errors)


def test_validate_json_locales_rejects_untranslated_han_source_in_other_target_locales(tmp_path: Path) -> None:
    locales_root = tmp_path / "locales"
    write_locale_file(locales_root, "zh-CN", "core.json", {"greeting": "你好，世界"})
    write_locale_file(locales_root, "ja", "core.json", {"greeting": "你好，世界"})

    errors = I18N_VALIDATE.validate_json_locales(locales_root)

    assert any("greeting" in error and "直接保留了包含中文字符的 source 文案" in error for error in errors)


def test_validate_json_locales_avoids_false_positive_when_plural_categories_do_not_align(tmp_path: Path) -> None:
    locales_root = tmp_path / "locales"
    write_locale_file(
        locales_root,
        "zh-CN",
        "core.json",
        {
            "tasks.cancelled": {
                "one": "中文单数",
                "other": "中文复数",
            }
        },
    )
    write_locale_file(
        locales_root,
        "ja",
        "core.json",
        {
            "tasks.cancelled": {
                "many": "中文单数",
                "other": "已翻译",
            }
        },
    )

    errors = I18N_VALIDATE.validate_json_locales(locales_root)

    assert any("tasks.cancelled" in error and "plural category 不一致" in error for error in errors)
    assert not any("tasks.cancelled" in error and "直接保留了包含中文字符的 source 文案" in error for error in errors)


def test_validate_dashboard_json_locales_rejects_han_characters_in_english_locale(tmp_path: Path) -> None:
    locales_root = tmp_path / "dashboard-locales"
    write_dashboard_locale_file(locales_root, "zh", {"common": {"greeting": "你好，世界"}})
    write_dashboard_locale_file(locales_root, "en", {"common": {"greeting": "Hello 同意"}})

    errors = I18N_VALIDATE.validate_dashboard_json_locales(locales_root)

    assert any("dashboard:en" in error and "common.greeting" in error and "仍包含中文字符" in error for error in errors)


def test_validate_dashboard_json_locales_rejects_untranslated_han_source_in_other_target_locales(
    tmp_path: Path,
) -> None:
    locales_root = tmp_path / "dashboard-locales"
    write_dashboard_locale_file(locales_root, "zh", {"common": {"greeting": "你好，世界"}})
    write_dashboard_locale_file(locales_root, "ja", {"common": {"greeting": "你好，世界"}})

    errors = I18N_VALIDATE.validate_dashboard_json_locales(locales_root)

    assert any(
        "dashboard:ja" in error and "common.greeting" in error and "直接保留了包含中文字符的 source 文案" in error
        for error in errors
    )


def test_validate_dashboard_json_locales_rejects_i18next_placeholder_drift(tmp_path: Path) -> None:
    locales_root = tmp_path / "dashboard-locales"
    write_dashboard_locale_file(locales_root, "zh", {"status": {"checkingDesc": "等待服务恢复... ({{current}}/{{max}})"}})
    write_dashboard_locale_file(locales_root, "ko", {"status": {"checkingDesc": "서비스 복구 대기 중... ({{current}}/{{limit}})"}})

    errors = I18N_VALIDATE.validate_dashboard_json_locales(locales_root)

    assert any("dashboard:ko" in error and "status.checkingDesc" in error and "占位符集合与 source 不一致" in error for error in errors)

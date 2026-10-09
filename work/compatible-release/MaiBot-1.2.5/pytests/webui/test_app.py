from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from src.webui import app as webui_app


def test_ensure_static_path_ready_uses_existing_static_path(tmp_path) -> None:
    static_path = tmp_path / "dist"
    static_path.mkdir()
    (static_path / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch.object(webui_app, "_resolve_static_path", return_value=static_path):
        result = webui_app._ensure_static_path_ready()

    assert result == static_path


def test_ensure_static_path_ready_logs_install_hint_when_static_assets_are_missing() -> None:
    with (
        patch.object(webui_app, "_resolve_static_path", return_value=None),
        patch.object(webui_app.logger, "warning") as warning_mock,
    ):
        result = webui_app._ensure_static_path_ready()

    assert result is None
    warning_mock.assert_any_call(webui_app.t("startup.webui_static_assets_unavailable"))
    warning_mock.assert_any_call(
        webui_app.t("startup.webui_dashboard_package_hint", command=webui_app._MANUAL_INSTALL_COMMAND)
    )


def test_ensure_static_path_ready_logs_index_error_when_static_path_is_invalid(tmp_path) -> None:
    static_path = tmp_path / "dist"
    static_path.mkdir()

    with (
        patch.object(webui_app, "_resolve_static_path", return_value=static_path),
        patch.object(webui_app.logger, "warning") as warning_mock,
    ):
        result = webui_app._ensure_static_path_ready()

    assert result is None
    warning_mock.assert_any_call(
        webui_app.t("startup.webui_index_missing", index_path=static_path / "index.html")
    )
    warning_mock.assert_any_call(
        webui_app.t("startup.webui_dashboard_package_hint", command=webui_app._MANUAL_INSTALL_COMMAND)
    )


def test_setup_static_files_does_not_duplicate_warning_when_static_path_is_unavailable() -> None:
    app = webui_app.FastAPI()

    with (
        patch.object(webui_app, "_ensure_static_path_ready", return_value=None),
        patch.object(webui_app.logger, "warning") as warning_mock,
    ):
        webui_app._setup_static_files(app)

    warning_mock.assert_not_called()


def test_statistics_report_route_requires_auth(monkeypatch, tmp_path) -> None:
    static_path = tmp_path / "dist"
    static_path.mkdir()
    (static_path / "index.html").write_text("<html></html>", encoding="utf-8")

    report_path = tmp_path / "maibot_statistics.html"
    report_path.write_text("<html>statistics</html>", encoding="utf-8")
    monkeypatch.setenv(webui_app._STATISTICS_REPORT_PATH_ENV, str(report_path))

    app = webui_app.FastAPI()
    with patch.object(webui_app, "_ensure_static_path_ready", return_value=static_path):
        webui_app._setup_static_files(app)

    client = TestClient(app)
    assert client.get("/maibot_statistics.html").status_code == 401

    app.dependency_overrides[webui_app.require_auth] = lambda: "test-token"
    authenticated_response = client.get("/maibot_statistics.html")

    assert authenticated_response.status_code == 200
    assert authenticated_response.text == "<html>statistics</html>"


def test_resolve_static_path_prefers_installed_dashboard_package(monkeypatch, tmp_path) -> None:
    package_dist = tmp_path / "site-packages" / "maibot_dashboard" / "dist"
    package_dist.mkdir(parents=True)

    class _DashboardModule:
        @staticmethod
        def get_dist_path() -> Path:
            return package_dist

    monkeypatch.setattr(webui_app, "_get_project_root", lambda: tmp_path)

    with patch.object(webui_app, "import_module", return_value=_DashboardModule()):
        resolved_path = webui_app._resolve_static_path()

    assert resolved_path == package_dist


def test_resolve_static_path_ignores_dashboard_dist_when_package_is_unavailable(monkeypatch, tmp_path) -> None:
    dashboard_dist = tmp_path / "dashboard" / "dist"
    dashboard_dist.mkdir(parents=True)
    (dashboard_dist / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(webui_app, "_get_project_root", lambda: tmp_path)

    with patch.object(webui_app, "import_module", side_effect=ImportError):
        resolved_path = webui_app._resolve_static_path()

    assert resolved_path is None


def test_resolve_static_path_uses_package_even_when_dashboard_dist_exists(monkeypatch, tmp_path) -> None:
    dashboard_dist = tmp_path / "dashboard" / "dist"
    dashboard_dist.mkdir(parents=True)

    package_dist = tmp_path / "site-packages" / "maibot_dashboard" / "dist"
    package_dist.mkdir(parents=True)

    class _DashboardModule:
        @staticmethod
        def get_dist_path() -> Path:
            return package_dist

    monkeypatch.setattr(webui_app, "_get_project_root", lambda: tmp_path)

    with patch.object(webui_app, "import_module", return_value=_DashboardModule()):
        resolved_path = webui_app._resolve_static_path()

    assert resolved_path == package_dist


def test_resolve_safe_static_file_path_allows_regular_static_file(tmp_path) -> None:
    static_path = tmp_path / "dist"
    asset_path = static_path / "assets" / "app.js"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text("console.log('ok')", encoding="utf-8")

    resolved_path = webui_app._resolve_safe_static_file_path(static_path, "assets/app.js")

    assert resolved_path == asset_path.resolve()


def test_resolve_safe_static_file_path_rejects_relative_path_traversal(tmp_path) -> None:
    static_path = tmp_path / "dist"
    static_path.mkdir()

    resolved_path = webui_app._resolve_safe_static_file_path(static_path, "../secret.txt")

    assert resolved_path is None


def test_resolve_safe_static_file_path_rejects_absolute_path_traversal(tmp_path) -> None:
    static_path = tmp_path / "dist"
    static_path.mkdir()

    resolved_path = webui_app._resolve_safe_static_file_path(static_path, "/etc/passwd")

    assert resolved_path is None


def test_resolve_safe_static_file_path_rejects_symlink_escape(tmp_path) -> None:
    static_path = tmp_path / "dist"
    static_path.mkdir()

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")

    link_path = static_path / "escape"
    try:
        link_path.symlink_to(outside_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink is not supported in this environment: {exc}")

    resolved_path = webui_app._resolve_safe_static_file_path(static_path, "escape/secret.txt")

    assert resolved_path is None

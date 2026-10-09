"""pytest 引导：把插件目录加入导入路径，并提供沙箱安全的 tmp_path。

Windows 沙箱会把 ``mkdir(mode=0o700)`` 创建的目录做成不可枚举（pytest 自带的
tmp_path 就因此失败），所以这里用一个默认权限的目录替代内置 tmp_path。
"""

from __future__ import annotations

from pathlib import Path

from uuid import uuid4
import os
import shutil
import sys

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PLUGINS_DIR = PLUGIN_DIR.parent
if str(PLUGINS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGINS_DIR))

_TMP_ROOT = Path(os.environ.get("COMPANION_TEST_DIR", str(PLUGIN_DIR / ".pytest_tmp")))


@pytest.fixture
def tmp_path() -> Path:
    """在插件目录内创建一个可枚举的临时目录（默认权限，非 0o700）。"""
    os.makedirs(_TMP_ROOT, exist_ok=True)
    path = _TMP_ROOT / f"case-{uuid4().hex}"
    os.makedirs(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

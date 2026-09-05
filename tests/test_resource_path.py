"""
Unit tests for utils/resource_path.py.
"""
import os
import sys
from utils.resource_path import get_app_root, get_bin_path, get_asset_path, get_config_path


def test_get_app_root_source_mode():
    root = get_app_root()
    assert os.path.exists(root)
    assert os.path.isdir(root)
    assert os.path.exists(os.path.join(root, "main.py"))


def test_get_bin_path():
    bin_dir = get_bin_path()
    assert os.path.exists(bin_dir)
    fcp_path = get_bin_path("fcp.exe")
    assert os.path.basename(fcp_path) == "fcp.exe"
    assert os.path.exists(fcp_path)


def test_get_asset_path():
    asset_dir = get_asset_path()
    assert os.path.exists(asset_dir)
    qss_path = get_asset_path("dark_style.qss")
    assert os.path.basename(qss_path) == "dark_style.qss"
    assert os.path.exists(qss_path)


def test_get_config_path():
    cfg_path = get_config_path()
    assert os.path.basename(cfg_path) == "config.json"


def test_frozen_mode_mock(monkeypatch, tmp_path):
    """Mocks sys.frozen and verifies path resolution relative to sys.executable."""
    fake_exe = str(tmp_path / "app" / "SD-FastBackup.exe")
    os.makedirs(os.path.dirname(fake_exe), exist_ok=True)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", fake_exe)

    assert get_app_root() == os.path.normpath(os.path.dirname(fake_exe))
    assert get_bin_path("fcp.exe") == os.path.normpath(os.path.join(os.path.dirname(fake_exe), "bin", "fcp.exe"))
    assert get_asset_path("dark_style.qss") == os.path.normpath(os.path.join(os.path.dirname(fake_exe), "assets", "dark_style.qss"))
    assert get_config_path() == os.path.normpath(os.path.join(os.path.dirname(fake_exe), "config.json"))

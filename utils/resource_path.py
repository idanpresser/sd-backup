"""
Resource & Path Resolution Utility for SD-FastBackup.
Provides consistent absolute paths to application root, bundled binaries, assets, and config
across both normal Python source execution and PyInstaller frozen distributions.
"""
import os
import sys


def get_app_root() -> str:
    """
    Returns the root directory of the application.
    In PyInstaller onedir frozen mode: returns the directory containing the executable.
    In source execution mode: returns the repository root directory.
    """
    if getattr(sys, "frozen", False):
        return os.path.normpath(os.path.dirname(sys.executable))
    # In source mode, this file is in utils/ -> parent is repository root
    return os.path.normpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_bundle_dir() -> str:
    """
    Returns the directory where bundled data files live.
    In PyInstaller frozen mode with _MEIPASS (e.g. _internal folder): returns _MEIPASS.
    Otherwise returns get_app_root().
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.normpath(sys._MEIPASS)
    return get_app_root()


def get_bin_path(subpath: str = "") -> str:
    """Returns absolute path to bin/ directory or a specific bundled binary inside bin/."""
    # 1. Check in bundle dir (_MEIPASS / _internal / root)
    bundle_bin = os.path.join(get_bundle_dir(), "bin")
    if os.path.exists(bundle_bin):
        return os.path.normpath(os.path.join(bundle_bin, subpath)) if subpath else os.path.normpath(bundle_bin)

    # 2. Check directly in app root (e.g. next to .exe)
    app_bin = os.path.join(get_app_root(), "bin")
    return os.path.normpath(os.path.join(app_bin, subpath)) if subpath else os.path.normpath(app_bin)


def get_asset_path(filename: str = "") -> str:
    """Returns absolute path to assets/ directory or a specific asset file (e.g. dark_style.qss)."""
    # 1. Check in bundle dir (_MEIPASS / _internal / root)
    bundle_assets = os.path.join(get_bundle_dir(), "assets")
    if os.path.exists(bundle_assets):
        return os.path.normpath(os.path.join(bundle_assets, filename)) if filename else os.path.normpath(bundle_assets)

    # 2. Check directly in app root (e.g. next to .exe)
    app_assets = os.path.join(get_app_root(), "assets")
    return os.path.normpath(os.path.join(app_assets, filename)) if filename else os.path.normpath(app_assets)


def get_config_path(default_name: str = "config.json") -> str:
    """
    Returns absolute path to config.json.
    Prioritizes user config next to executable, then bundled template, then user writable path next to executable.
    """
    exe_dir_cfg = os.path.join(get_app_root(), default_name)
    if os.path.exists(exe_dir_cfg):
        return os.path.normpath(exe_dir_cfg)

    bundle_cfg = os.path.join(get_bundle_dir(), default_name)
    if os.path.exists(bundle_cfg):
        return os.path.normpath(bundle_cfg)

    return os.path.normpath(exe_dir_cfg)

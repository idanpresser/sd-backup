# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for SD-FastBackup onedir distribution.
Bundles Python runtimes, PySide6 GUI, dependencies, assets, and vendored binaries (fcp.exe, exiftool, FSViewer85).
"""
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect all dynamic libraries and binaries for metadata packages
pymediainfo_datas, pymediainfo_binaries, pymediainfo_hiddenimports = collect_all('pymediainfo')
exifread_datas, exifread_binaries, exifread_hiddenimports = collect_all('exifread')

datas = [
    ('assets', 'assets'),
    ('bin', 'bin'),
]
if os.path.exists('config.json'):
    datas.append(('config.json', '.'))

datas += pymediainfo_datas + exifread_datas
binaries = pymediainfo_binaries + exifread_binaries

hiddenimports = [
    # Windows COM / MTP engine support
    'win32com',
    'win32com.client',
    'pythoncom',
    'pywintypes',
    'win32api',
    'win32con',
    # PySide6 Qt Modules
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'shiboken6',
    # Metadata & Media parsing
    'exifread',
    'pymediainfo',
    # Core app submodules
    'core',
    'core.db',
    'core.fastcopy',
    'core.logger',
    'core.metadata',
    'core.mtp_engine',
    'core.sync_engine',
    'core.indexer',
    'core.worker',
    'app',
    'app.main_window',
    'app.components',
    'app.components.alert_banner',
    'app.components.db_viewer',
    'app.components.drive_selector',
    'app.components.extension_filter_dialog',
    'app.components.index_folder_dialog',
    'app.components.log_console',
    'app.components.progress_panel',
    'utils',
    'utils.maintenance',
    'utils.media_filter',
    'utils.path_formatter',
    'utils.resource_path',
] + pymediainfo_hiddenimports + exifread_hiddenimports

# Exclude heavy unused Qt submodules to ensure fast build and compact package
excludes = [
    'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras', 'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic', 'PySide6.Qt3DRender', 'PySide6.QtBluetooth', 'PySide6.QtCharts',
    'PySide6.QtDataVisualization', 'PySide6.QtGraphs', 'PySide6.QtHttpServer',
    'PySide6.QtLocation', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtNfc', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtPositioning',
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickControls2',
    'PySide6.QtQuickWidgets', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtSensors',
    'PySide6.QtSerialBus', 'PySide6.QtSerialPort', 'PySide6.QtSpatialAudio', 'PySide6.QtStateMachine',
    'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.QtTest', 'PySide6.QtTextToSpeech',
    'PySide6.QtVirtualKeyboard', 'PySide6.QtWebChannel', 'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineQuick', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebSockets',
    'tkinter', 'matplotlib', 'scipy', 'torch', 'transformers'
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SD-FastBackup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SD-FastBackup',
)

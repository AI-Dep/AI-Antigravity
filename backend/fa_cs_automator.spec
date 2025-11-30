# -*- mode: python ; coding: utf-8 -*-
# ==============================================================================
# PyInstaller Spec File for FA CS Automator Backend
# ==============================================================================
# This compiles the Python backend to a standalone executable.
# Run with: pyinstaller fa_cs_automator.spec
# ==============================================================================

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all submodules
hidden_imports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    'pydantic',
    'pandas',
    'openpyxl',
    'numpy',
    'dotenv',
    'psutil',
]

# Add all backend.logic submodules
hidden_imports += collect_submodules('backend.logic')
hidden_imports += collect_submodules('backend.services')
hidden_imports += collect_submodules('backend.models')

a = Analysis(
    ['api.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('logic', 'logic'),
        ('config', 'config'),
        ('models', 'models'),
        ('services', 'services'),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='fa_cs_automator_api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../icon.ico' if os.path.exists('../icon.ico') else None,
)

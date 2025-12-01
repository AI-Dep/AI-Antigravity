# -*- mode: python ; coding: utf-8 -*-
# ==============================================================================
# PyInstaller Spec File for FA CS Automator Backend
# ==============================================================================
# This compiles the Python backend to a standalone executable.
# Run with: pyinstaller fa_cs_automator.spec
# ==============================================================================

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Get the absolute path to the backend directory
BACKEND_DIR = os.path.dirname(os.path.abspath(SPEC))

# ------------------------------------------------------------------------------
# Hidden Imports - modules that PyInstaller can't detect automatically
# ------------------------------------------------------------------------------
hidden_imports = [
    # Uvicorn and ASGI
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',

    # FastAPI and Starlette
    'fastapi',
    'fastapi.middleware',
    'fastapi.middleware.cors',
    'fastapi.responses',
    'starlette',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    'starlette.middleware.errors',
    'starlette.responses',
    'starlette.requests',
    'starlette.websockets',

    # Pydantic
    'pydantic',
    'pydantic.fields',
    'pydantic_core',
    'annotated_types',

    # Data processing
    'pandas',
    'pandas.io.formats.style',
    'openpyxl',
    'openpyxl.styles',
    'openpyxl.utils',
    'openpyxl.workbook',
    'openpyxl.worksheet',
    'numpy',
    'numpy.core',

    # Standard library (sometimes missed)
    'asyncio',
    'threading',
    'io',
    'traceback',
    'logging',
    'logging.handlers',
    'datetime',
    'shutil',
    'contextlib',
    'json',
    'typing',
    'typing_extensions',
    'email_validator',

    # ASGI/HTTP dependencies
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'sniffio',
    'httptools',
    'h11',
    'websockets',
    'watchfiles',
    'multipart',
    'python_multipart',

    # Environment and system
    'dotenv',
    'psutil',

    # Crypto (if using encryption module)
    'cryptography',
    'cryptography.fernet',
]

# Collect all backend submodules dynamically
hidden_imports += collect_submodules('backend.logic')
hidden_imports += collect_submodules('backend.services')
hidden_imports += collect_submodules('backend.models')
hidden_imports += collect_submodules('backend.middleware')
hidden_imports += collect_submodules('backend.rpa')
hidden_imports += collect_submodules('backend.ui')

# ------------------------------------------------------------------------------
# Data Files - non-Python files that must be included
# ------------------------------------------------------------------------------
datas = [
    # Logic module and all subfolders
    ('logic', 'logic'),
    ('logic/config', 'logic/config'),

    # Models
    ('models', 'models'),

    # Services
    ('services', 'services'),

    # Middleware
    ('middleware', 'middleware'),

    # RPA module including config and UiPath templates
    ('rpa', 'rpa'),
    ('rpa/uipath', 'rpa/uipath'),

    # UI module (if needed for management interface)
    ('ui', 'ui'),
]

# Collect data files from third-party packages that need them
datas += collect_data_files('pydantic')
datas += collect_data_files('email_validator', include_py_files=False)

# ------------------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------------------
a = Analysis(
    ['api.py'],
    pathex=[BACKEND_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

# ------------------------------------------------------------------------------
# Remove duplicate data files and binaries
# ------------------------------------------------------------------------------
def unique_datas(datas):
    seen = set()
    result = []
    for dest, src, kind in datas:
        if dest not in seen:
            seen.add(dest)
            result.append((dest, src, kind))
    return result

a.datas = unique_datas(a.datas)

# ------------------------------------------------------------------------------
# PYZ Archive
# ------------------------------------------------------------------------------
pyz = PYZ(a.pure, a.zipped_data)

# ------------------------------------------------------------------------------
# Executable
# ------------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Disabled - can cause issues with some DLLs
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for logging output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(BACKEND_DIR, '..', 'icon.ico') if os.path.exists(os.path.join(BACKEND_DIR, '..', 'icon.ico')) else None,
)

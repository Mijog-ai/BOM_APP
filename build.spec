# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for BOM Explorer
# Build with:  pyinstaller build.spec
# Output:      dist/BOM_Explorer/BOM_Explorer.exe  (entire folder must be distributed)

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# pyodbc ships a compiled .pyd; collect_all pulls the binary + any submodules
pyodbc_datas, pyodbc_binaries, pyodbc_hidden = collect_all('pyodbc')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=pyodbc_binaries,
    datas=pyodbc_datas,
    hiddenimports=[
        *pyodbc_hidden,
        'PyQt6.QtPrintSupport',
        'PyQt6.sip',
        'openpyxl',
        'openpyxl.cell._writer',
        *collect_submodules('reportlab'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy ML packages not needed in the app EXE
        'transformers',
        'accelerate',
        'bitsandbytes',
        'huggingface_hub',
        'sentencepiece',
        'safetensors',
        'tokenizers',
        'torch',
        'tensorflow',
        'keras',
        'sklearn',
        'scipy',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --onefile: binaries/datas passed directly into EXE — single .exe output
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='BOM_Explorer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # replace with 'icon.ico' if you have one
)

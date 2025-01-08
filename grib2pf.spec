# -*- mode: python ; coding: utf-8 -*-
import sys
EXCLUDE = {
        "MSVCP140.dll",
        "ucrtbase.dll",
}

BINARIES = None
if sys.platform.lower().startswith('win'):
    BINARIES = [
        ('build\\grib2pf.dll', '.'),
        ('build\\bin\\eccodes.dll', '.'),
        ('build\\bin\\eccodes_memfs.dll', '.')
    ]
else:
    BINARIES = [
        ('build/libgrib2pf.so', '.'),
        ('build/lib/libeccodes.so', '.'),
        ('build/lib/libeccodes_memfs.so', '.')
    ]

grib2pf_a = Analysis(
    ['grib2pf.py'],
    pathex=[],
    binaries=BINARIES,
    datas=[
        ( "README.md", '.' ),
        ( "ACKNOWLEDGMENTS.md", "." ),
    ],
    hiddenimports=['packaging', 'pyproj'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# exclude binaries
toKeep = []

for (dest, source, kind) in grib2pf_a.binaries:
    filename = os.path.split(dest)[1]
    if filename.startswith("api-ms-win-")  or \
       filename.startswith("VCRUNTIME140") or \
       filename in EXCLUDE                    :
        continue

    toKeep.append((dest, source, kind))

grib2pf_a.binaries = toKeep

grib2pf_pyz = PYZ(grib2pf_a.pure)

grib2pf_exe = EXE(
    grib2pf_pyz,
    grib2pf_a.scripts,
    [],
    exclude_binaries=True,
    name='grib2pf',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[
        "icon\\icon16.ico",
        "icon\\icon32.ico",
        "icon\\icon512.ico"
        ],
)


grib2pf_ui_a = Analysis(
    ['grib2pf-ui.py'],
    pathex=[],
    binaries=[
    ],
    datas=[
        ( "README.md", '.' ),
        ( "ACKNOWLEDGMENTS.md", "." ),
    ],
    hiddenimports=['packaging', 'pyproj'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

toKeep = []

for (dest, source, kind) in grib2pf_ui_a.binaries:
    filename = os.path.split(dest)[1]
    if filename.startswith("api-ms-win-")  or \
       filename.startswith("VCRUNTIME140") or \
       filename in EXCLUDE                    :
        continue

    toKeep.append((dest, source, kind))

grib2pf_ui_a.binaries = toKeep

grib2pf_ui_pyz = PYZ(grib2pf_ui_a.pure)

grib2pf_ui_exe = EXE(
    grib2pf_ui_pyz,
    grib2pf_ui_a.scripts,
    [],
    exclude_binaries=True,
    name='grib2pf-ui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[
        "icon\\icon16.ico",
        "icon\\icon32.ico",
        "icon\\icon512.ico"
        ],
)

coll = COLLECT(
    grib2pf_exe,
    grib2pf_a.binaries,
    grib2pf_a.datas,
    grib2pf_ui_exe,
    grib2pf_ui_a.binaries,
    grib2pf_ui_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='grib2pf',
)

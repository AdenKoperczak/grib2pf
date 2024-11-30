# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['grib2pf.py'],
    pathex=[],
    binaries=[
        ('D:\\a\\grib2pf\\grib2pf\\eccodes-install\\bin\\eccodes.dll', '.'),
        ('D:\\a\\grib2pf\\grib2pf\\eccodes-install\\bin\\eccodes_memfs.dll', '.')
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

# exclude binaries
toKeep = []

EXCLUDE = {
        "MSVCP140.dll",
        "ucrtbase.dll",
}
for (dest, source, kind) in a.binaries:
    filename = os.path.split(dest)[1]
    if filename.startswith("api-ms-win-")  or \
       filename.startswith("VCRUNTIME140") or \
       filename in EXCLUDE                    :
        continue

    toKeep.append((dest, source, kind))

a.binaries = toKeep

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='grib2pf',
)

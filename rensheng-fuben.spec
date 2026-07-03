# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


root = Path.cwd()

datas = []


def add_file(src: Path, dest: Path | str) -> None:
    if src.exists() and src.is_file():
        datas.append((str(src), str(dest)))


def add_tree(src_dir: Path, dest_dir: Path | str) -> None:
    if not src_dir.exists():
        return
    dest_root = Path(dest_dir)
    for path in src_dir.rglob("*"):
        if path.is_file():
            datas.append((str(path), str(dest_root / path.relative_to(src_dir).parent)))


for file_name in ("prompt.txt", ".env.example", "README.md", "LICENSE"):
    add_file(root / file_name, ".")

for folder_name in ("static", "prompts", "examples", "assets"):
    add_tree(root / folder_name, folder_name)

hiddenimports = []
for package_name in ("uvicorn", "edge_tts"):
    hiddenimports += collect_submodules(package_name)


a = Analysis(
    ["desktop_launcher.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="rensheng-fuben",
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
    name="rensheng-fuben",
)

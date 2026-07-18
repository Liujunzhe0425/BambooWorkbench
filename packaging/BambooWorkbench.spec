from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
DATAS = [
    (str(ROOT / "contracts"), "contracts"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "logo"), "logo"),
    (str(ROOT / "resources"), "resources"),
    (str(ROOT / "mock_modules"), "mock_modules"),
]
HIDDEN = collect_submodules("keyring.backends")
APP_ICON = str(ROOT / "logo" / "BambooWorkbench.ico")

main_analysis = Analysis(
    [str(ROOT / "app" / "__main__.py")],
    pathex=[str(ROOT)],
    datas=DATAS,
    hiddenimports=HIDDEN,
    excludes=[],
    noarchive=False,
)
main_pyz = PYZ(main_analysis.pure)
main_exe = EXE(
    main_pyz,
    main_analysis.scripts,
    [],
    exclude_binaries=True,
    name="BambooWorkbench",
    console=False,
    icon=APP_ICON,
    contents_directory=".",
)

host_analysis = Analysis(
    [str(ROOT / "app" / "module_host_entry.py")],
    pathex=[str(ROOT)],
    datas=[],
    hiddenimports=[],
    excludes=[],
    noarchive=False,
)
host_pyz = PYZ(host_analysis.pure)
host_exe = EXE(
    host_pyz,
    host_analysis.scripts,
    [],
    exclude_binaries=True,
    name="BambooModuleHost",
    console=True,
    icon=APP_ICON,
    contents_directory=".",
)

coll = COLLECT(
    main_exe,
    host_exe,
    main_analysis.binaries,
    main_analysis.datas,
    host_analysis.binaries,
    host_analysis.datas,
    name="BambooWorkbench",
)

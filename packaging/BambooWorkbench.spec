from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
MOISTURE_ROOT = ROOT / "modules" / "moisture"


def data_tree(source, destination):
    return [
        (
            str(path),
            str(Path(destination) / path.parent.relative_to(source)).replace("\\", "/"),
        )
        for path in source.rglob("*")
        if path.is_file()
        and path.suffix != ".pyc"
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
    ]


MOISTURE_DATAS = [
    (str(MOISTURE_ROOT / name), "modules/moisture")
    for name in (
        "module.json",
        "run_module.bat",
        "README.md",
        "CHANGELOG.md",
        "requirements.txt",
        "pyproject.toml",
    )
] + [
    (str(MOISTURE_ROOT / name), f"modules/moisture/{name}")
    for name in ("rules", "experience", "schemas", "templates", "docs")
] + [
    (str(MOISTURE_ROOT / "samples" / "README.md"), "modules/moisture/samples"),
]
MOISTURE_DATAS += data_tree(MOISTURE_ROOT / "src", "modules/moisture/src")
MOISTURE_DATAS += data_tree(MOISTURE_ROOT / "tests", "modules/moisture/tests")
DATAS = [
    (str(ROOT / "contracts"), "contracts"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "logo"), "logo"),
    (str(ROOT / "resources"), "resources"),
    (str(ROOT / "mock_modules"), "mock_modules"),
] + MOISTURE_DATAS
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

moisture_analysis = Analysis(
    [str(MOISTURE_ROOT / "src" / "moisture" / "cli.py")],
    pathex=[str(MOISTURE_ROOT / "src"), str(ROOT)],
    datas=MOISTURE_DATAS,
    hiddenimports=[],
    excludes=["PySide6"],
    noarchive=False,
)
moisture_pyz = PYZ(moisture_analysis.pure)
moisture_exe = EXE(
    moisture_pyz,
    moisture_analysis.scripts,
    [],
    exclude_binaries=True,
    name="BambooMoistureModule",
    console=True,
    icon=APP_ICON,
    contents_directory=".",
)

coll = COLLECT(
    main_exe,
    host_exe,
    moisture_exe,
    main_analysis.binaries,
    main_analysis.datas,
    host_analysis.binaries,
    host_analysis.datas,
    moisture_analysis.binaries,
    moisture_analysis.datas,
    name="BambooWorkbench",
)

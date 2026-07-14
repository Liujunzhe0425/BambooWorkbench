from pathlib import Path

from PySide6.QtGui import QIcon, QImage, QPixmap

ROOT = Path(__file__).parents[2]


def test_user_provided_team_logo_is_the_canonical_ui_asset(qapp) -> None:
    logo_path = ROOT / "logo" / "team-logo.png"
    image = QImage(str(logo_path))

    assert logo_path.is_file()
    assert image.isNull() is False
    assert image.width() == 81
    assert image.height() == 81
    assert image.hasAlphaChannel()
    assert QPixmap(str(logo_path)).isNull() is False


def test_windows_icon_contains_multiple_shortcut_sizes(qapp) -> None:
    icon_path = ROOT / "logo" / "BambooWorkbench.ico"
    icon = QIcon(str(icon_path))
    sizes = {(size.width(), size.height()) for size in icon.availableSizes()}

    assert icon_path.is_file()
    assert icon.isNull() is False
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes

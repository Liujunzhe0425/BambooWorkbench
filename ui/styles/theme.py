from pathlib import Path

from PySide6.QtWidgets import QApplication


def load_stylesheet(resource_root: Path) -> str:
    theme_path = resource_root / "resources" / "themes" / "bamboo.qss"
    return theme_path.read_text(encoding="utf-8")


def apply_theme(application: QApplication, resource_root: Path) -> str:
    stylesheet = load_stylesheet(resource_root)
    application.setStyleSheet(stylesheet)
    return stylesheet

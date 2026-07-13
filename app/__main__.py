from collections.abc import Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.bootstrap import AppContext, build_context, create_application
from ui.main_window import MainWindow


def compose_application(application: QApplication, context: AppContext) -> MainWindow:
    application.setStyleSheet(context.stylesheet)
    application.aboutToQuit.connect(context.close)
    window = MainWindow(context)
    window.show()
    return window


def main(
    argv: Sequence[str] | None = None,
    data_root: Path | None = None,
    *,
    use_mocks: bool = True,
) -> int:
    application = create_application(list(argv) if argv is not None else None)
    context = build_context(data_root, use_mocks=use_mocks)
    window = compose_application(application, context)
    try:
        return application.exec()
    finally:
        window.close()
        context.close()


if __name__ == "__main__":
    raise SystemExit(main())

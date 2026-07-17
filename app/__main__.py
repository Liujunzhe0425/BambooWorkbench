import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from app.bootstrap import AppContext, build_context, create_application
from ui.main_window import MainWindow


def compose_application(application: QApplication, context: AppContext) -> MainWindow:
    application.setStyleSheet(context.stylesheet)
    window = MainWindow(context)
    window.show()
    return window


def main(
    argv: Sequence[str] | None = None,
    data_root: Path | None = None,
    *,
    use_mocks: bool | None = None,
) -> int:
    command_arguments = list(sys.argv[1:] if argv is None else argv)
    if "--smoke-test" in command_arguments:
        return smoke_test(use_mocks=True)
    if "--real-smoke-test" in command_arguments:
        return smoke_test(use_mocks=False)
    requested_modes = {
        argument
        for argument in command_arguments
        if argument in {"--mock-modules", "--real-modules"}
    }
    if len(requested_modes) > 1:
        raise ValueError("--mock-modules and --real-modules are mutually exclusive")
    if use_mocks is None:
        use_mocks = "--mock-modules" in requested_modes
    application_arguments = (
        [argument for argument in argv if argument not in requested_modes]
        if argv is not None
        else [
            sys.argv[0],
            *(argument for argument in sys.argv[1:] if argument not in requested_modes),
        ]
    )
    application = create_application(application_arguments)
    context = build_context(data_root, use_mocks=use_mocks)
    window: MainWindow | None = None
    close_context = context.close
    connected = False
    try:
        application.aboutToQuit.connect(close_context)
        connected = True
        window = compose_application(application, context)
        return application.exec()
    finally:
        try:
            if connected:
                application.aboutToQuit.disconnect(close_context)
        finally:
            try:
                if window is not None:
                    window.close()
            finally:
                context.close()


def smoke_test(*, use_mocks: bool = True) -> int:
    application = create_application(["BambooWorkbench", "--smoke-test"])
    del application
    with TemporaryDirectory(prefix="BambooWorkbench-smoke-") as directory:
        context = build_context(Path(directory), use_mocks=use_mocks)
        try:
            modules = tuple(context.registry.all())
            expected_count = 3 if use_mocks else 1
            if len(modules) != expected_count or any(
                module.health != "healthy" for module in modules
            ):
                return 2
            if not context.stylesheet.strip():
                return 3
            if context.database.scalar("SELECT COUNT(*) FROM knowledge_records") < 4:
                return 4
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

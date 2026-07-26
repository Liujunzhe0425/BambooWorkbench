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
    schedule_update = getattr(window, "schedule_automatic_update_check", None)
    if callable(schedule_update):
        schedule_update()
    return window


def main(
    argv: Sequence[str] | None = None,
    data_root: Path | None = None,
    *,
    use_mocks: bool | None = None,
) -> int:
    command_arguments = list(sys.argv[1:] if argv is None else argv)
    if command_arguments == ["--smoke-test"]:
        return smoke_test(use_mocks=False)
    if command_arguments == ["--demo-smoke-test"]:
        return smoke_test(use_mocks=True)
    if command_arguments == ["--initialize-install"]:
        context = build_context(None, use_mocks=False)
        context.close()
        return 0
    application_arguments = list(sys.argv if argv is None else argv)
    demo_requested = "--demo" in command_arguments
    application_arguments = [
        argument for argument in application_arguments if argument != "--demo"
    ]
    selected_use_mocks = demo_requested if use_mocks is None else use_mocks
    application = create_application(application_arguments)
    context = build_context(data_root, use_mocks=selected_use_mocks)
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


def smoke_test(*, use_mocks: bool = False) -> int:
    application = create_application(["BambooWorkbench", "--smoke-test"])
    del application
    with TemporaryDirectory(prefix="BambooWorkbench-smoke-") as directory:
        context = build_context(Path(directory), use_mocks=use_mocks)
        try:
            modules = tuple(context.registry.all())
            if len(modules) != 3 or any(module.health != "healthy" for module in modules):
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

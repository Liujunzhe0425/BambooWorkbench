"""Capture deterministic UI previews for visual acceptance checks."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bootstrap import build_context, create_application  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.page_ids import PageId  # noqa: E402


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "ui-preview").resolve()
    output.mkdir(parents=True, exist_ok=True)
    application = create_application(["capture-ui-previews"])
    with tempfile.TemporaryDirectory(prefix="bamboo-ui-") as data_root:
        context = build_context(Path(data_root), use_mocks=True)
        try:
            application.setStyleSheet(context.stylesheet)
            window = MainWindow(context)
            window.resize(1180, 760)
            window.show()
            application.processEvents()
            for page_id, filename in (
                (PageId.WORKBENCH, "01-workbench.png"),
                (PageId.HISTORY, "02-history.png"),
                (PageId.KNOWLEDGE, "03-knowledge.png"),
                (PageId.SETTINGS, "04-settings.png"),
            ):
                window.navigate(page_id)
                application.processEvents()
                if not window.grab().save(str(output / filename), "PNG"):
                    raise RuntimeError(f"failed to save {filename}")
            window.close()
        finally:
            context.close()
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

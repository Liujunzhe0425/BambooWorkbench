from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from ui.navigation import Navigation
from ui.page_ids import PageId


class MainWindow(QMainWindow):
    def __init__(self, context: object) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("竹简工作台")
        self.resize(1180, 760)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        resource_root = context.resource_root
        self.navigation = Navigation(resource_root / "assets" / "brand" / "team-logo.svg")
        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        self.pages: dict[PageId, QWidget] = {
            page_id: self._placeholder(page_id) for page_id in PageId
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.navigation.page_selected.connect(self.navigate)
        self.navigate(PageId.WORKBENCH)

    @staticmethod
    def _placeholder(page_id: PageId) -> QWidget:
        page = QWidget()
        page.setObjectName(f"page-{page_id.value}")
        return page

    def navigate(self, page_id: PageId) -> None:
        self.stack.setCurrentWidget(self.pages[page_id])
        self.navigation.set_current_page(page_id)

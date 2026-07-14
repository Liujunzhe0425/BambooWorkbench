from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class WindowTitleBar(QWidget):
    """Lightweight in-app title bar for the frameless desktop shell."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._drag_offset: QPoint | None = None
        self.setObjectName("windowTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(6)

        self.title_label = QLabel("竹简工作台")
        self.title_label.setObjectName("windowTitle")
        self.version_label = QLabel("BambooWorkbench v0.1.0")
        self.version_label.setObjectName("windowVersion")
        layout.addWidget(self.title_label)
        layout.addWidget(self.version_label)
        layout.addStretch()

        self.minimize_button = self._button("—", "windowMinimize", "最小化窗口")
        self.maximize_button = self._button("□", "windowMaximize", "最大化窗口")
        self.close_button = self._button("×", "windowClose", "关闭窗口")
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

    @staticmethod
    def _button(text: str, name: str, accessible_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(name)
        button.setAccessibleName(accessible_name)
        button.setFixedSize(38, 30)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
            self.maximize_button.setText("□")
            self.maximize_button.setAccessibleName("最大化窗口")
        else:
            self._window.showMaximized()
            self.maximize_button.setText("❐")
            self.maximize_button.setAccessibleName("还原窗口")

    def update_window_state(self) -> None:
        maximized = self._window.isMaximized()
        self.maximize_button.setText("❐" if maximized else "□")
        self.maximize_button.setAccessibleName("还原窗口" if maximized else "最大化窗口")

    def mousePressEvent(self, event: object) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self._window.isMaximized()
        ):
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: object) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

from PySide6.QtCore import QLineF, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class WindowControlButton(QPushButton):
    """Uniform vector-drawn window control with no font-glyph alignment drift."""

    def __init__(self, control_kind: str) -> None:
        super().__init__()
        self.control_kind = control_kind

    def set_control_kind(self, control_kind: str) -> None:
        self.control_kind = control_kind
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        icon_color = (
            QColor("#FFFDF8")
            if self.control_kind == "close" and self.underMouse()
            else QColor("#365B49")
        )
        pen = QPen(icon_color, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        center = self.rect().center()
        x = float(center.x())
        y = float(center.y())

        if self.control_kind == "minimize":
            painter.drawLine(QLineF(x - 6, y + 3, x + 6, y + 3))
        elif self.control_kind == "maximize":
            painter.drawRect(QRectF(x - 6, y - 6, 12, 12))
        elif self.control_kind == "restore":
            painter.drawRect(QRectF(x - 3.5, y - 6, 9.5, 9.5))
            painter.fillRect(QRectF(x - 7, y - 3, 10.5, 10.5), QColor("#F5F7F2"))
            painter.drawRect(QRectF(x - 6, y - 3, 10, 10))
        else:
            painter.drawLine(QLineF(x - 5, y - 5, x + 5, y + 5))
            painter.drawLine(QLineF(x + 5, y - 5, x - 5, y + 5))


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
        layout.setContentsMargins(16, 0, 2, 0)
        layout.setSpacing(0)

        self.title_label = QLabel("竹简工作台")
        self.title_label.setObjectName("windowTitle")
        self.version_label = QLabel("BambooWorkbench v0.1.0")
        self.version_label.setObjectName("windowVersion")
        layout.addWidget(self.title_label)
        layout.addWidget(self.version_label)
        layout.addStretch()

        self.minimize_button = self._button(
            "minimize",
            "windowMinimize",
            "最小化窗口",
        )
        self.maximize_button = self._button(
            "maximize",
            "windowMaximize",
            "最大化窗口",
        )
        self.close_button = self._button(
            "close",
            "windowClose",
            "关闭窗口",
        )
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

    def _button(
        self,
        control_kind: str,
        name: str,
        accessible_name: str,
    ) -> QPushButton:
        button = WindowControlButton(control_kind)
        button.setObjectName(name)
        button.setAccessibleName(accessible_name)
        button.setFixedSize(40, 40)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self.update_window_state()

    def update_window_state(self) -> None:
        maximized = self._window.isMaximized()
        self.maximize_button.set_control_kind("restore" if maximized else "maximize")
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

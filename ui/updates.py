from __future__ import annotations

import logging
import os
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

from app import __version__
from core.updates.installer import launch_installer_after_exit
from core.updates.models import ReleaseUpdate
from core.updates.service import GitHubReleaseUpdateService, UpdateError

_LOG = logging.getLogger("bamboo_workbench")


class UpdateController(QObject):
    status_changed = Signal(str)
    _available = Signal(object)
    _current = Signal()
    _check_error = Signal(str)
    _download_ready = Signal(object)
    _download_error = Signal(str)
    _download_progress = Signal(int, int)

    def __init__(
        self,
        parent: QWidget,
        context: object,
        service: GitHubReleaseUpdateService | None = None,
    ) -> None:
        super().__init__(parent)
        self.parent_window = parent
        self.context = context
        self.service = service or GitHubReleaseUpdateService()
        self._threads: set[threading.Thread] = set()
        self._busy = False
        self._manual = False
        self._pending_release: ReleaseUpdate | None = None
        self._progress_dialog: QProgressDialog | None = None
        self._installer_helper: object | None = None
        self._available.connect(self._update_available)
        self._current.connect(self._already_current)
        self._check_error.connect(self._check_failed)
        self._download_ready.connect(self._downloaded)
        self._download_error.connect(self._download_failed)
        self._download_progress.connect(self._download_progressed)

    @property
    def busy(self) -> bool:
        return self._busy

    def check_automatically(self) -> None:
        if self.context.settings.get("update_auto_check", "true") != "true":
            return
        if not getattr(sys, "frozen", False) and os.environ.get(
            "BAMBOO_ENABLE_SOURCE_UPDATE_CHECK"
        ) != "1":
            return
        self.check(manual=False)

    @Slot()
    def check_manually(self) -> None:
        self.check(manual=True)

    def check(self, *, manual: bool) -> None:
        if self._busy:
            if manual:
                self._show_information("检查更新", "更新检查正在进行，请稍候。")
            return
        self._busy = True
        self._manual = manual
        self.status_changed.emit("正在检查更新…")
        self._start_thread(self._check_in_background)

    def _start_thread(self, target: Callable[[], None]) -> None:
        thread: threading.Thread

        def run() -> None:
            try:
                target()
            finally:
                self._threads.discard(thread)

        thread = threading.Thread(target=run, daemon=True, name="BambooWorkbenchUpdater")
        self._threads.add(thread)
        thread.start()

    def _check_in_background(self) -> None:
        try:
            release = self.service.check(__version__)
        except (UpdateError, ValueError) as error:
            self._check_error.emit(str(error))
        else:
            if release is None:
                self._current.emit()
            else:
                self._available.emit(release)

    @Slot(object)
    def _update_available(self, release: ReleaseUpdate) -> None:
        self._busy = False
        self.status_changed.emit(f"发现新版本 {release.version}")
        answer = QMessageBox.question(
            self.parent_window,
            "发现竹简工作台更新",
            f"当前版本：{__version__}\n最新版本：{release.version}\n\n"
            "是否现在下载？下载完成后软件将退出、安装并自动重新启动。\n"
            "本地任务、设置和历史数据会保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status_changed.emit(f"已暂缓更新至 {release.version}")
            return
        if not getattr(sys, "frozen", False):
            self._show_information(
                "源码运行模式",
                "已检测到新版本，但源码运行模式不会覆盖安装程序。"
                "请从 Release 下载，或使用已安装版本测试自动更新。",
            )
            return
        self._busy = True
        self._pending_release = release
        self.status_changed.emit(f"正在下载 {release.version}…")
        self._show_download_progress(release)
        self._start_thread(lambda: self._download_in_background(release))

    def _download_in_background(self, release: ReleaseUpdate) -> None:
        destination = self.context.paths.cache / "updates" / release.tag_name
        try:
            installer = self.service.download(
                release,
                destination,
                progress=lambda received, total: self._download_progress.emit(
                    received, total
                ),
            )
        except UpdateError as error:
            self._download_error.emit(str(error))
        else:
            self._download_ready.emit(installer)

    @Slot()
    def _already_current(self) -> None:
        self._busy = False
        self.status_changed.emit(f"当前已是最新版本 {__version__}")
        if self._manual:
            self._show_information("检查更新", f"当前已是最新版本 {__version__}。")

    @Slot(str)
    def _check_failed(self, message: str) -> None:
        self._busy = False
        self.status_changed.emit("更新检查暂不可用")
        _LOG.warning("update check failed: %s", message)
        if self._manual:
            self._show_warning("检查更新失败", message)

    @Slot(object)
    def _downloaded(self, installer: Path) -> None:
        release = self._pending_release
        if release is None:
            self._download_failed("更新状态已失效，请重新检查更新")
            return
        self._finish_download_progress()
        install_directory = Path(sys.executable).resolve().parent
        helper_directory = (
            Path(tempfile.gettempdir())
            / "BambooWorkbench-updater"
            / release.tag_name
        )
        try:
            self._installer_helper = launch_installer_after_exit(
                installer,
                helper_directory,
                application_path=Path(sys.executable),
                install_directory=install_directory,
                expected_version=release.version,
            )
        except UpdateError as error:
            self._download_failed(str(error))
            return
        helper_pid = getattr(self._installer_helper, "pid", "unknown")
        _LOG.info(
            "update helper launched version=%s helper_pid=%s",
            release.version,
            helper_pid,
        )
        self._busy = False
        self._pending_release = None
        self.status_changed.emit("更新已下载，正在重启安装…")
        application = QApplication.instance()
        if application is not None:
            application.quit()

    @Slot(str)
    def _download_failed(self, message: str) -> None:
        self._close_download_progress()
        self._busy = False
        self._pending_release = None
        self.status_changed.emit("更新下载或安装失败")
        _LOG.warning("update download failed: %s", message)
        self._show_warning("更新失败", message)

    @Slot(int, int)
    def _download_progressed(self, received: int, total: int) -> None:
        if total <= 0:
            return
        percent = min(100.0, max(0.0, received * 100.0 / total))
        received_mb = received / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        self.status_changed.emit(
            f"正在下载更新：{percent:.1f}%（{received_mb:.1f}/{total_mb:.1f} MB）"
        )
        dialog = self._progress_dialog
        if dialog is not None:
            dialog.setMaximum(total)
            dialog.setValue(min(received, total))
            dialog.setLabelText(
                f"正在下载竹简工作台更新…\n"
                f"{percent:.1f}%（{received_mb:.1f}/{total_mb:.1f} MB）"
            )

    def _show_download_progress(self, release: ReleaseUpdate) -> None:
        self._close_download_progress()
        dialog = QProgressDialog(
            f"正在下载竹简工作台 {release.version}…",
            "",
            0,
            release.asset_size,
            self.parent_window,
        )
        dialog.setWindowTitle("下载软件更新")
        dialog.setCancelButton(None)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setMinimumDuration(0)
        dialog.setValue(0)
        dialog.show()
        self._progress_dialog = dialog

    def _finish_download_progress(self) -> None:
        dialog = self._progress_dialog
        if dialog is not None:
            dialog.setLabelText("下载完成，SHA-256 校验通过，正在准备安装…")
            dialog.setValue(dialog.maximum())
        self._close_download_progress()

    def _close_download_progress(self) -> None:
        dialog = self._progress_dialog
        self._progress_dialog = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()

    def _show_information(self, title: str, message: str) -> None:
        QMessageBox.information(self.parent_window, title, message)

    def _show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self.parent_window, title, message)

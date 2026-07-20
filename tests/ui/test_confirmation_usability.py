from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QLabel, QPlainTextEdit

from core.contracts.result import ConfirmationPrompt, OutputArtifact, SourceRef
from ui.pages.confirmations_page import ConfirmationsPage
from ui.widgets.output_files import OutputFilesWidget


def _prompt(
    confirmation_id: str,
    field: str,
    reason: str,
    *,
    source_file: str = "20260135.xlsx",
    cell: str | None = None,
    batch_applicable: bool = False,
    rememberable: bool = False,
    blocking: bool = False,
    options: list[object] | None = None,
) -> ConfirmationPrompt:
    return ConfirmationPrompt(
        confirmation_id=confirmation_id,
        field=field,
        reason=reason,
        suggested_value=None,
        options=options or [1.1, 1.2],
        confidence=0.5,
        blocking=blocking,
        batch_applicable=batch_applicable,
        rememberable=rememberable,
        source=SourceRef(
            source_file=source_file,
            sheet="板 1",
            cell_or_range=cell,
        ),
    )


def test_confirmation_page_explains_batch_scope_and_disambiguates_repeated_fields(
    qtbot,
) -> None:
    page = ConfirmationsPage()
    qtbot.addWidget(page)
    prompts = [
        _prompt(
            "usage",
            "product_usage",
            "本批输入文件未提供产品用途。",
            batch_applicable=True,
            rememberable=True,
            blocking=True,
            options=["地板", "家具", "墙板"],
        ),
        _prompt("density-one", "密度", "20260115 原表与规则结论冲突。"),
        _prompt("density-two", "密度", "20260121 原表与规则结论冲突。"),
        _prompt(
            "expansion-one",
            "expansion_ratio",
            "中1 原表值与复算值冲突。",
            cell="H22",
        ),
        _prompt(
            "expansion-two",
            "expansion_ratio",
            "端2-2 原表值与复算值冲突。",
            cell="H36",
        ),
    ]

    page.load("boiling-ui", prompts)

    assert isinstance(page.answer_inputs["usage"], QComboBox)
    assert page.answer_inputs["usage"].currentText() == "地板"
    assert "只有确认本批数据应使用同一答案时才勾选" in page.batch_checks[
        "usage"
    ].toolTip()
    assert page.batch_help_labels["usage"].text() == "!"
    assert page.batch_help_labels["usage"].toolTip() == page.batch_checks["usage"].toolTip()
    assert page.reason_labels["expansion-one"].text().startswith("中1")
    assert "20260135.xlsx" in page.source_labels["expansion-one"].text()
    assert "H22" in page.source_labels["expansion-one"].text()

    visible_labels = {label.text() for label in page.findChildren(QLabel)}
    assert "密度结论复核 1/2（可选）" in visible_labels
    assert "密度结论复核 2/2（可选）" in visible_labels
    assert "膨胀率数值冲突 1/2（可选）" in visible_labels
    assert "膨胀率数值冲突 2/2（可选）" in visible_labels


def test_confirmation_page_scrolls_instead_of_compressing_many_prompts(qtbot, qapp) -> None:
    page = ConfirmationsPage()
    qtbot.addWidget(page)
    page.resize(900, 520)
    prompts = [
        _prompt(
            f"conflict-{index}",
            "expansion_ratio",
            f"样{index + 1} 原表值与复算值冲突。",
            cell=f"H{index + 1}",
        )
        for index in range(18)
    ]

    page.load("overflow", prompts)
    page.show()
    qapp.processEvents()

    assert page.scroll_area.verticalScrollBar().maximum() > 0
    assert all(editor.height() > 20 for editor in page.answer_inputs.values())


def test_text_output_uses_built_in_viewer_when_windows_has_no_file_association(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "analysis_report.md"
    report.write_text("# 分析报告\n\n本地内容", encoding="utf-8")
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda _url: False)
    failures: list[str] = []
    widget = OutputFilesWidget()
    qtbot.addWidget(widget)
    widget.open_failed.connect(failures.append)
    widget.set_outputs(
        [
            OutputArtifact(
                type="analysis_report",
                path=str(report),
                label="竹丝水分分析报告",
                mime_type="text/markdown",
            )
        ]
    )

    qtbot.mouseClick(widget.buttons[0], Qt.MouseButton.LeftButton)

    assert failures == []
    assert len(widget.text_viewers) == 1
    editor = widget.text_viewers[0].findChild(QPlainTextEdit)
    assert editor is not None
    assert "本地内容" in editor.toPlainText()


def test_json_output_is_pretty_printed_in_built_in_viewer(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = tmp_path / "boiling_records.json"
    records.write_text('{"records":[{"product":"竹板"}]}', encoding="utf-8")
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda _url: False)
    widget = OutputFilesWidget()
    qtbot.addWidget(widget)
    widget.set_outputs(
        [
            OutputArtifact(
                type="business_records",
                path=str(records),
                label="水煮实验结构化业务记录",
                mime_type="application/json",
            )
        ]
    )

    qtbot.mouseClick(widget.buttons[0], Qt.MouseButton.LeftButton)

    editor = widget.text_viewers[0].findChild(QPlainTextEdit)
    assert editor is not None
    assert '\n  "records": [' in editor.toPlainText()


def test_theme_gives_unchecked_confirmations_a_visible_border(app_context) -> None:
    stylesheet = app_context.stylesheet
    indicator_rule = stylesheet.split("QCheckBox::indicator, QRadioButton::indicator", 1)[
        1
    ].split("}", 1)[0]

    assert "border: 2px solid #5B9B7D" in indicator_rule
    assert "background: #FFFDF8" in indicator_rule
    assert 'QLabel[helpBadge="true"]' in stylesheet

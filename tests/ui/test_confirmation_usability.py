from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QDesktopServices, QEnterEvent
from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QPlainTextEdit, QToolTip

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

    assert page.job_selector.currentText() == "任务 1"
    assert "boiling-ui" not in page.status_label.text()
    assert isinstance(page.answer_inputs["usage"], QComboBox)
    assert page.answer_inputs["usage"].currentText() == "地板"
    assert "只有确认本批数据应使用同一答案时才勾选" in page.batch_checks[
        "usage"
    ].toolTip()
    assert page.batch_help_labels["usage"].text() == "!"
    assert page.batch_help_labels["usage"].toolTip() == page.batch_checks["usage"].toolTip()
    assert page.remember_help_labels["usage"].text() == "!"
    assert "后续相同字段自动匹配" in page.remember_help_labels["usage"].help_text
    options_view = page.answer_inputs["usage"].view()
    assert options_view.objectName() == "confirmationOptions"
    assert options_view.frameShape() == QFrame.Shape.NoFrame
    assert page.reason_labels["expansion-one"].text().startswith("中1")
    assert page.file_group_titles["20260135.xlsx"].text() == "20260135.xlsx"
    assert "H22" in page.source_labels["expansion-one"].text()

    visible_labels = {label.text() for label in page.findChildren(QLabel)}
    assert "密度结论复核 1/2（可选）" in visible_labels
    assert "密度结论复核 2/2（可选）" in visible_labels
    assert "膨胀率数值冲突 1/2（可选）" in visible_labels
    assert "膨胀率数值冲突 2/2（可选）" in visible_labels


def test_after_sales_protocol_fields_are_localized(qtbot) -> None:
    page = ConfirmationsPage()
    qtbot.addWidget(page)
    prompts = [
        _prompt(f"field-{field}", field, "需要人工确认。")
        for field in (
            "complaint_date",
            "enterprise_cost_amount",
            "internal_accountability_amount",
            "external_borne_amount",
            "issue_types",
            "template",
        )
    ]

    page.load("after-sales-fields", prompts)

    labels = {label.text() for label in page.findChildren(QLabel)}
    assert {
        "投诉日期（可选）",
        "企业承担售后费用（可选）",
        "内部责任费用（可选）",
        "外部承担费用（可选）",
        "质量问题类型（可选）",
        "表格模板识别（可选）",
    }.issubset(labels)
    assert not any("_" in label for label in labels if "（可选）" in label)


def test_confirmation_popup_and_help_badges_have_immediate_light_ui(
    qtbot, qapp, monkeypatch
) -> None:
    page = ConfirmationsPage()
    qtbot.addWidget(page)
    page.load(
        "visual-confirmation",
        [
            _prompt(
                "visual-field",
                "product_usage",
                "请选择产品用途。",
                batch_applicable=True,
                rememberable=True,
                options=["地板", "家具"],
            )
        ],
    )
    page.resize(900, 520)
    page.show()
    qapp.processEvents()
    editor = page.answer_inputs["visual-field"]
    assert isinstance(editor, QComboBox)
    editor.showPopup()
    qapp.processEvents()
    popup_image = editor.view().window().grab().toImage()
    assert QColor(popup_image.pixelColor(popup_image.width() // 2, 0)) != QColor("#000000")
    assert QColor(
        popup_image.pixelColor(popup_image.width() // 2, popup_image.height() - 1)
    ) != QColor("#000000")
    editor.hidePopup()

    shown: list[str] = []
    monkeypatch.setattr(
        QToolTip,
        "showText",
        lambda _position, text, _widget: shown.append(text),
    )
    enter = QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
    qapp.sendEvent(page.batch_help_labels["visual-field"], enter)
    qapp.processEvents()
    assert shown and "应用到当前任务" in shown[-1]
    qapp.sendEvent(page.remember_help_labels["visual-field"], enter)
    qapp.processEvents()
    assert "后续相同字段自动匹配" in shown[-1]


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


def test_confirmation_page_groups_fields_by_source_file_and_preserves_answers(
    qtbot,
) -> None:
    page = ConfirmationsPage()
    qtbot.addWidget(page)
    prompts = [
        _prompt(
            f"file-{file_index}-{field}",
            field,
            f"第 {file_index} 份文件的{field}需要复核。",
            source_file=f"售后记录-{file_index}.xlsx",
            blocking=True,
            options=["建议值", "人工值"],
        )
        for file_index in range(1, 6)
        for field in ("售后费用", "责任工厂", "投诉类型")
    ]

    page.load("after-sales-review", prompts)

    assert len(page.file_group_frames) == 5
    assert [label.text() for label in page.file_group_titles.values()] == [
        f"售后记录-{index}.xlsx" for index in range(1, 6)
    ]
    for file_index in range(1, 6):
        group_key = f"售后记录-{file_index}.xlsx"
        confirmation_ids = {
            f"file-{file_index}-{field}"
            for field in ("售后费用", "责任工厂", "投诉类型")
        }
        assert {
            confirmation_id
            for confirmation_id, prompt_group in page.prompt_group_keys.items()
            if prompt_group == group_key
        } == confirmation_ids

    page.answer_inputs["file-1-售后费用"].setCurrentIndex(1)
    page.answer_inputs["file-4-投诉类型"].setCurrentIndex(1)
    submitted: list[tuple[str, list[object]]] = []
    page.submitted.connect(lambda job_id, answers: submitted.append((job_id, answers)))

    qtbot.mouseClick(page.submit_button, Qt.MouseButton.LeftButton)

    assert submitted[0][0] == "after-sales-review"
    values = {
        answer.confirmation_id: answer.value for answer in submitted[0][1]
    }
    assert values["file-1-售后费用"] == "人工值"
    assert values["file-4-投诉类型"] == "人工值"
    assert values["file-2-责任工厂"] == "建议值"


def test_confirmation_page_keeps_missing_source_prompts_in_other_group(qtbot) -> None:
    page = ConfirmationsPage()
    qtbot.addWidget(page)
    prompt = _prompt(
        "legacy-confirmation",
        "legacy_field",
        "旧任务没有提供来源文件。",
        source_file="",
    )

    page.load("legacy-task", [prompt])

    assert "" in page.file_group_frames
    assert page.file_group_titles[""].text() == "其他确认事项"
    assert page.prompt_group_keys["legacy-confirmation"] == ""
    assert "legacy-confirmation" in page.answer_inputs


def test_confirmation_page_scrolls_across_one_hundred_file_groups(qtbot, qapp) -> None:
    page = ConfirmationsPage()
    qtbot.addWidget(page)
    page.resize(1050, 620)
    prompts = [
        _prompt(
            f"review-{index}",
            "责任工厂",
            "请逐文件确认责任工厂。",
            source_file=f"售后-{index:03d}.xlsx",
            blocking=True,
            options=["一厂", "二厂"],
        )
        for index in range(100)
    ]

    page.load("hundred-files", prompts)
    page.show()
    qapp.processEvents()

    assert len(page.file_group_frames) == 100
    assert page.file_group_titles["售后-099.xlsx"].text() == "售后-099.xlsx"
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

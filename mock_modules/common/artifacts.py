from pathlib import Path

from openpyxl import Workbook


def create_artifacts(output_dir: Path, module_id: str) -> list[dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = output_dir / f"{module_id}-summary.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Summary"
    sheet.append(["Module", "Status"])
    sheet.append([module_id, "Mock success"])
    workbook.save(workbook_path)

    report_path = output_dir / f"{module_id}-report.md"
    report_path.write_text(f"# {module_id}\n\nMock analysis result.\n", encoding="utf-8")

    chart_path = output_dir / f"{module_id}-chart.svg"
    chart_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="240">'
        '<rect width="600" height="240" fill="#fbfaf4"/>'
        '<rect x="50" y="80" width="120" height="110" fill="#2fa47d"/>'
        '<rect x="210" y="40" width="120" height="150" fill="#294d3c"/>'
        '<rect x="370" y="110" width="120" height="80" fill="#f1b232"/>'
        "</svg>",
        encoding="utf-8",
    )
    return [
        {
            "type": "summary_excel",
            "path": str(workbook_path.resolve()),
            "label": "模拟汇总",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        {
            "type": "report",
            "path": str(report_path.resolve()),
            "label": "模拟报告",
            "mime_type": "text/markdown",
        },
        {
            "type": "chart",
            "path": str(chart_path.resolve()),
            "label": "模拟图表",
            "mime_type": "image/svg+xml",
        },
    ]

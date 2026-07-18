import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path

try:
    import openpyxl
    import yaml
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
except ImportError as exc:  # pragma: no cover - exercised in a clean environment
    print(json.dumps({"type": "error", "message": str(exc)}), file=sys.stderr)
    raise SystemExit(4) from exc


MODULE_ID = "boiling"
MODULE_VERSION = "0.1.0"
MODULE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES_FILE = MODULE_ROOT / "rules" / "default_rules.yaml"
ALLOWED_JOB_FIELDS = {
    "schema_version",
    "job_id",
    "module_id",
    "phase",
    "run_mode",
    "input_files",
    "output_dir",
    "module_config_file",
    "ai_enabled",
    "allowed_knowledge_scopes",
    "parent_job_id",
    "confirmation_file",
    "service_response_file",
}
FIELD_LABELS = {
    "batch_no": ("批号", "批次号", "批次"),
    "product": ("产品名称", "产品名", "品名"),
    "specification": ("规格型号", "产品规格", "规格"),
    "pressing_date": ("压制日期", "压制时间"),
    "team_leader": ("班组长", "班长"),
    "test_date": ("检测日期", "检验日期", "试验日期", "实验日期"),
    "impregnation_date": ("浸胶日期", "浸渍日期", "浸胶时间"),
    "order_info": ("订单信息", "订单编号", "订单号", "订单"),
    "product_usage": ("产品用途", "用途"),
}
FIXED_FALLBACKS = {
    "batch_no": (2, 1),
    "product": (3, 3),
    "specification": (3, 7),
    "test_date": (5, 3),
}
REQUIRED_FOR_NORMAL_STATS = (
    "product",
    "specification",
    "pressing_date",
    "team_leader",
    "test_date",
    "impregnation_date",
    "order_info",
    "samples",
)
SAMPLE_PATTERN = re.compile(
    r"^(?:样(?:品|件)?|试件|复测)\s*[#№]?[A-Za-z0-9一二三四五六七八九十_-]+$",
    re.I,
)


def emit(message, percent=0, event_type="progress"):
    print(
        json.dumps(
            {"type": event_type, "percent": percent, "message": message},
            ensure_ascii=False,
        ),
        flush=True,
    )


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_number(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def as_text(value):
    return "" if value is None else str(value).strip()


def as_date_text(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%Y-%m-%d")
    text = as_text(value)
    if not text:
        return ""
    for pattern in (r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})",):
        match = re.search(pattern, text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            try:
                return dt.date(year, month, day).isoformat()
            except ValueError:
                return text
    return text.replace("年", "-").replace("月", "-").replace("日", "")


def mean(values):
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def normalize_label(value):
    return re.sub(r"[\s:：()（）【】\[\]]", "", as_text(value)).lower()


def normalize_ratio(value):
    number = as_number(value)
    if number is None:
        return None
    return number / 100 if abs(number) > 1 else number


def display_cell_value(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%Y-%m-%d")
    return as_text(value)


def plausible_fixed_fallback(field, value):
    if value in (None, ""):
        return False
    if field.endswith("_date"):
        if isinstance(value, (dt.date, dt.datetime)):
            return True
        return bool(re.search(r"20\d{2}[./年-]\d{1,2}[./月-]\d{1,2}", as_text(value)))
    normalized = normalize_label(value)
    known_labels = {
        normalize_label(label)
        for labels in FIELD_LABELS.values()
        for label in labels
    }
    header_words = ("试件", "长度", "宽度", "重量", "密度", "膨胀率", "记录状态", "检测员")
    return normalized not in known_labels and not any(word in normalized for word in header_words)


def find_labeled_value(sheet, labels, max_rows=30, max_columns=12):
    normalized_labels = sorted(
        ((normalize_label(label), label) for label in labels),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for row in range(1, min(sheet.max_row, max_rows) + 1):
        for column in range(1, min(sheet.max_column, max_columns) + 1):
            raw = sheet.cell(row, column).value
            text = as_text(raw)
            normalized = normalize_label(text)
            if not normalized:
                continue
            for normalized_label, original_label in normalized_labels:
                if normalized == normalized_label:
                    candidate_column = column + 1
                    if candidate_column <= sheet.max_column:
                        candidate = sheet.cell(row, candidate_column).value
                        if candidate not in (None, ""):
                            return candidate, sheet.cell(row, candidate_column).coordinate
                for separator in ("：", ":"):
                    prefix = original_label + separator
                    if text.replace(" ", "").startswith(prefix):
                        remainder = text.replace(" ", "")[len(prefix) :].strip()
                        if remainder:
                            return remainder, sheet.cell(row, column).coordinate
    return None, None


def find_sample_markers(sheet):
    markers = []
    for row in range(1, sheet.max_row + 1):
        for column in range(1, min(sheet.max_column, 3) + 1):
            label = as_text(sheet.cell(row=row, column=column).value)
            if label and SAMPLE_PATTERN.fullmatch(label):
                markers.append({"row": row, "column": column, "label": label})
                break
    return markers


def find_sample_rows(sheet):
    return [marker["row"] for marker in find_sample_markers(sheet)]


def worksheet_score(sheet):
    score = len(find_sample_markers(sheet)) * 100
    for labels in FIELD_LABELS.values():
        value, _ = find_labeled_value(sheet, labels)
        if value not in (None, ""):
            score += 2
    for row in range(1, min(sheet.max_row, 80) + 1):
        joined = " ".join(
            as_text(sheet.cell(row, column).value)
            for column in range(1, min(sheet.max_column, 12) + 1)
        )
        if "检测结论" in joined or "检验结论" in joined:
            score += 10
            break
    return score


def select_data_sheet(workbook):
    return max(workbook.worksheets, key=worksheet_score)


def first_numeric(value_getter, rows, column):
    for row in rows:
        number = as_number(value_getter(row, column))
        if number is not None:
            return number
    return None


def find_conclusion_row(sheet, start_row):
    for row in range(start_row, sheet.max_row + 1):
        joined = " ".join(
            as_text(sheet.cell(row, column).value)
            for column in range(1, min(sheet.max_column, 12) + 1)
        )
        if "检测结论" in joined or "检验结论" in joined:
            return row
    return None


def source_ref(path, sheet, cell_or_range=None):
    return {
        "source_file": str(Path(path).resolve()),
        "sheet": sheet,
        "cell_or_range": cell_or_range,
    }


def extract_file(path):
    formula_book = openpyxl.load_workbook(path, data_only=False, read_only=False)
    value_book = openpyxl.load_workbook(path, data_only=True, read_only=False)
    try:
        sheet = select_data_sheet(formula_book)
        value_sheet = value_book[sheet.title]

        def value(row, column):
            calculated = value_sheet.cell(row=row, column=column).value
            if calculated is not None:
                return calculated
            return sheet.cell(row=row, column=column).value

        record = {
            "source_file": str(Path(path).resolve()),
            "source_sheet": sheet.title,
            "batch_no": "",
            "product": "",
            "specification": "",
            "pressing_date": "",
            "team_leader": "",
            "test_date": "",
            "impregnation_date": "",
            "order_info": "",
            "product_usage": "",
            "field_sources": {},
            "samples": [],
            "source_conclusion": "",
            "tester": "",
            "missing_fields": [],
            "conflicts": [],
            "conclusion_rule_conflicts": [],
            "rule_observations": {},
            "business_status": "信息不足",
        }
        for field, labels in FIELD_LABELS.items():
            raw, coordinate = find_labeled_value(sheet, labels)
            if raw in (None, "") and field in FIXED_FALLBACKS:
                row, column = FIXED_FALLBACKS[field]
                candidate = sheet.cell(row, column).value
                if plausible_fixed_fallback(field, candidate):
                    raw = candidate
                    coordinate = sheet.cell(row, column).coordinate
            if field.endswith("_date"):
                record[field] = as_date_text(raw)
            else:
                record[field] = display_cell_value(raw)
            if coordinate:
                record["field_sources"][field] = coordinate

        markers = find_sample_markers(sheet)
        conclusion_row = find_conclusion_row(sheet, 1)
        for sample_index, marker in enumerate(markers):
            start = marker["row"]
            base_column = marker["column"]
            next_start = markers[sample_index + 1]["row"] if sample_index + 1 < len(markers) else None
            block_end = next_start - 1 if next_start is not None else sheet.max_row
            if conclusion_row is not None and conclusion_row > start:
                block_end = min(block_end, conclusion_row - 1)
            block_end = min(block_end, start + 20)
            block_rows = range(start, block_end + 1)
            density_column = base_column + 5
            expansion_column = base_column + 7
            summary_candidates = [
                row
                for row in block_rows
                if as_number(value(row, density_column)) is not None
                or normalize_ratio(value(row, expansion_column)) is not None
            ]
            summary_row = summary_candidates[-1] if summary_candidates else block_end
            before_column = base_column + 3
            after_column = base_column + 6
            measurement_stop = summary_row if summary_candidates else summary_row + 1
            measurement_rows = [
                row
                for row in range(start, measurement_stop)
                if as_number(value(row, before_column)) is not None
                or as_number(value(row, after_column)) is not None
            ]
            before = [as_number(value(row, before_column)) for row in measurement_rows]
            after = [as_number(value(row, after_column)) for row in measurement_rows]
            avg_before = mean(before)
            avg_after = mean(after)
            length = first_numeric(value, range(start, min(block_end, start + 3) + 1), base_column + 1)
            width = first_numeric(value, range(start, min(block_end, start + 3) + 1), base_column + 2)
            weight = first_numeric(value, range(start, summary_row + 1), base_column + 4)
            source_density = as_number(value(summary_row, density_column)) if summary_row <= sheet.max_row else None
            source_expansion = normalize_ratio(value(summary_row, expansion_column)) if summary_row <= sheet.max_row else None
            volume_cm3 = None
            calculated_density = None
            calculated_expansion = None
            if length and width and avg_before:
                volume_cm3 = length * width * avg_before / 1000
                if weight is not None and volume_cm3:
                    calculated_density = weight / volume_cm3
            if avg_before not in (None, 0) and avg_after is not None:
                calculated_expansion = (avg_after - avg_before) / avg_before
            density = calculated_density if calculated_density is not None else source_density
            expansion = calculated_expansion if calculated_expansion is not None else source_expansion
            label = marker["label"]
            sample = {
                "label": label,
                "sample_type": "retest" if "复测" in label else "normal",
                "length_mm": length,
                "width_mm": width,
                "weight_g": weight,
                "average_thickness_before_mm": avg_before,
                "average_thickness_after_mm": avg_after,
                "volume_cm3": volume_cm3,
                "source_density_g_cm3": source_density,
                "calculated_density_g_cm3": calculated_density,
                "density_g_cm3": density,
                "source_expansion_ratio": source_expansion,
                "calculated_expansion_ratio": calculated_expansion,
                "expansion_ratio": expansion,
                "source_range": (
                    f"{sheet.cell(start, base_column).coordinate}:"
                    f"{sheet.cell(summary_row, min(base_column + 7, sheet.max_column)).coordinate}"
                ),
            }
            if source_density is not None and calculated_density is not None:
                difference = abs(source_density - calculated_density)
                if difference > 0.01:
                    record["conflicts"].append(
                        {
                            "field": "density_g_cm3",
                            "sample": label,
                            "source_value": source_density,
                            "calculated_value": calculated_density,
                            "difference": difference,
                            "cell_or_range": sheet.cell(summary_row, density_column).coordinate,
                        }
                    )
            if source_expansion is not None and calculated_expansion is not None:
                difference = abs(source_expansion - calculated_expansion)
                if difference > 0.001:
                    record["conflicts"].append(
                        {
                            "field": "expansion_ratio",
                            "sample": label,
                            "source_value": source_expansion,
                            "calculated_value": calculated_expansion,
                            "difference": difference,
                            "cell_or_range": sheet.cell(summary_row, expansion_column).coordinate,
                        }
                    )
            record["samples"].append(sample)

        for row in range(1, sheet.max_row + 1):
            cells = [as_text(sheet.cell(row, column).value) for column in range(1, min(sheet.max_column, 12) + 1)]
            joined = " ".join(item for item in cells if item)
            if "检测结论" in joined or "检验结论" in joined:
                record["source_conclusion"] = re.sub(r"^.*?(?:检测|检验)结论\s*[：:]?", "", joined).strip()
                tester_value, tester_coordinate = find_labeled_value(sheet, ("检测员", "检验员", "测试员"), max_rows=sheet.max_row)
                record["tester"] = as_text(tester_value) or as_text(sheet.cell(row, 8).value)
                if tester_coordinate:
                    record["field_sources"]["tester"] = tester_coordinate
                break

        densities = [sample["density_g_cm3"] for sample in record["samples"] if sample["density_g_cm3"] is not None]
        expansions = [sample["expansion_ratio"] for sample in record["samples"] if sample["expansion_ratio"] is not None]
        record["average_density_g_cm3"] = mean(densities)
        record["density_range_g_cm3"] = max(densities) - min(densities) if densities else None
        record["average_expansion_ratio"] = mean(expansions)
        conclusion = record["source_conclusion"]
        if re.search(r"浸渍剥离.{0,8}不合格", conclusion):
            record["immersion_peel_result"] = "不合格"
        elif re.search(r"浸渍剥离.{0,8}合格", conclusion):
            record["immersion_peel_result"] = "合格"
        else:
            record["immersion_peel_result"] = ""
        for field in (
            "product",
            "specification",
            "pressing_date",
            "team_leader",
            "test_date",
            "impregnation_date",
            "order_info",
        ):
            if not record[field]:
                record["missing_fields"].append(field)
        if not record["samples"]:
            record["missing_fields"].append("samples")
        return record
    finally:
        formula_book.close()
        value_book.close()


def load_rules(config_file=None):
    rules_path = DEFAULT_RULES_FILE
    if config_file:
        config_path = Path(config_file)
        data = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}
        candidate = data.get("rules_file") if isinstance(data, dict) else None
        if candidate:
            candidate_path = Path(candidate)
            rules_path = candidate_path if candidate_path.is_absolute() else config_path.parent / candidate_path
        elif isinstance(data, dict) and ("density" in data or "expansion" in data):
            return data
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(data, dict):
        raise ValueError("规则文件根节点必须是对象")
    return data


def make_anomaly(record, fingerprint, suffix, severity, field, value, rule_id, message, suggestion, cell_or_range=None):
    return {
        "anomaly_id": f"A-{suffix}-{fingerprint[:12]}",
        "severity": severity,
        "field": field,
        "value": value,
        "rule_id": rule_id,
        "message": message,
        "suggestion": suggestion,
        "source": source_ref(record["source_file"], record["source_sheet"], cell_or_range),
    }


def conclusion_pass_claim(conclusion, keywords):
    for keyword in keywords:
        match = re.search(rf"{keyword}.{{0,16}}?(不合格|合格)", conclusion)
        if match:
            return match.group(1) == "合格"
    return None


def add_conclusion_rule_conflict(
    record,
    anomalies,
    confirmations,
    fingerprint,
    field,
    rule_id,
    source_claim,
    observed_outside,
    observed_value,
):
    if source_claim is None or observed_outside is None or source_claim == (not observed_outside):
        return
    source_text = "合格" if source_claim else "不合格"
    rule_text = "超出暂存阈值" if observed_outside else "未超出暂存阈值"
    conflict = {
        "field": field,
        "source_conclusion": source_text,
        "rule_observation": rule_text,
        "observed_value": observed_value,
        "rule_id": rule_id,
    }
    record["conclusion_rule_conflicts"].append(conflict)
    conflict_index = len(record["conclusion_rule_conflicts"])
    anomalies.append(
        make_anomaly(
            record,
            fingerprint,
            f"CONCLUSION-RULE-{conflict_index}",
            "warning",
            field,
            {"source_conclusion": source_text, "rule_observation": rule_text, "value": observed_value},
            "BOILING-CONCLUSION-CONFLICT-001",
            f"原表{field}结论为{source_text}，但当前规则观察为{rule_text}；两者均已保留。",
            "复核原表签字结论、测量数据和规则版本；暂存规则未经确认，不得自动覆盖原表。",
        )
    )
    confirmations.append(
        {
            "confirmation_id": f"C-CONCLUSION-RULE-{field}-{fingerprint[:12]}",
            "field": field,
            "reason": f"原表结论“{source_text}”与规则观察“{rule_text}”不一致，需要人工复核。",
            "suggested_value": None,
            "options": [source_text, rule_text],
            "confidence": 0.0,
            "blocking": False,
            "batch_applicable": False,
            "rememberable": False,
            "source": source_ref(record["source_file"], record["source_sheet"]),
        }
    )


def evaluate_record(record, rules, fingerprint):
    anomalies = []
    confirmations = []
    density_rule = rules.get("density") or {}
    minimum = as_number(density_rule.get("minimum_g_cm3"))
    maximum = as_number(density_rule.get("maximum_g_cm3"))
    density_value = record.get("average_density_g_cm3")
    density_outside = density_value is not None and (
        (minimum is not None and density_value < minimum) or (maximum is not None and density_value > maximum)
    )
    record["rule_observations"]["density"] = (
        "超出暂存阈值" if density_outside else "未超出暂存阈值"
    ) if density_value is not None and (minimum is not None or maximum is not None) else "信息不足"
    if density_outside:
        anomalies.append(
            make_anomaly(
                record,
                fingerprint,
                "DENSITY",
                "warning",
                "average_density_g_cm3",
                density_value,
                density_rule.get("rule_id"),
                "平均密度超出当前暂存阈值；该规则尚未获客户确认，不能作为正式合格判定。",
                "复核原始测量值，并由有权限人员确认密度阈值后再作正式判断。",
            )
        )

    expansion_rule = rules.get("expansion") or {}
    thresholds = expansion_rule.get("thresholds") or {}
    usage = record.get("product_usage")
    threshold = thresholds.get(usage) if usage else None
    if isinstance(threshold, dict):
        maximum_ratio = normalize_ratio(threshold.get("maximum_ratio"))
    else:
        maximum_ratio = normalize_ratio(threshold)
    expansion_value = record.get("average_expansion_ratio")
    expansion_outside = (
        expansion_value > maximum_ratio
        if maximum_ratio is not None and expansion_value is not None
        else None
    )
    record["rule_observations"]["expansion"] = (
        "超出暂存阈值" if expansion_outside else "未超出暂存阈值"
    ) if expansion_outside is not None else "待确认产品用途或规则"
    if expansion_outside:
        anomalies.append(
            make_anomaly(
                record,
                fingerprint,
                "EXPANSION",
                "warning",
                "average_expansion_ratio",
                expansion_value,
                expansion_rule.get("rule_id"),
                "平均膨胀率超出当前产品用途对应的暂存阈值；规则尚未获客户确认。",
                "复核产品用途及测量值，并由有权限人员确认正式阈值。",
            )
        )
    conclusion = record.get("source_conclusion", "")
    add_conclusion_rule_conflict(
        record,
        anomalies,
        confirmations,
        fingerprint,
        "密度",
        density_rule.get("rule_id"),
        conclusion_pass_claim(conclusion, ("密度",)),
        density_outside if density_value is not None and (minimum is not None or maximum is not None) else None,
        density_value,
    )
    add_conclusion_rule_conflict(
        record,
        anomalies,
        confirmations,
        fingerprint,
        "膨胀率",
        expansion_rule.get("rule_id"),
        conclusion_pass_claim(conclusion, ("膨胀率", "膨胀")),
        expansion_outside,
        expansion_value,
    )
    if record.get("immersion_peel_result") == "不合格":
        anomalies.append(
            make_anomaly(
                record,
                fingerprint,
                "PEEL",
                "warning",
                "immersion_peel_result",
                "不合格",
                "BOILING-PEEL-SOURCE-001",
                "原表记录浸渍剥离检测不合格。",
                "保留原表结论并转人工复核；本模块不替代检测人员作正式判定。",
            )
        )
    for index, conflict in enumerate(record.get("conflicts", []), 1):
        anomalies.append(
            make_anomaly(
                record,
                fingerprint,
                f"CONFLICT-{index}",
                "warning",
                conflict["field"],
                {"source": conflict["source_value"], "calculated": conflict["calculated_value"]},
                "BOILING-CALC-CONFLICT-001",
                f"{conflict['sample']} 的原表值与模块复算值不一致。",
                "核对公式、单位和原始测量记录；在确认前同时保留两个值。",
                conflict.get("cell_or_range"),
            )
        )
        confirmations.append(
            {
                "confirmation_id": f"C-CONFLICT-{index}-{fingerprint[:12]}",
                "field": conflict["field"],
                "reason": f"{conflict['sample']} 原表值与复算值冲突，需要人工选择可信来源。",
                "suggested_value": conflict["calculated_value"],
                "options": [conflict["source_value"], conflict["calculated_value"]],
                "confidence": 0.5,
                "blocking": False,
                "batch_applicable": False,
                "rememberable": False,
                "source": source_ref(record["source_file"], record["source_sheet"], conflict.get("cell_or_range")),
            }
        )
    return anomalies, confirmations


def style_header(cells):
    fill = PatternFill("solid", fgColor="1F4E78")
    for cell in cells:
        cell.font = Font(name="微软雅黑", bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def write_summary(records, output_path, rules, excluded_records=None):
    excluded_records = excluded_records or []
    workbook = openpyxl.Workbook()
    summary = workbook.active
    summary.title = "水煮检测汇总"
    headers = [
        "来源文件", "批号", "产品", "规格", "压制日期", "班长", "检测日期", "浸胶日期",
        "订单信息", "产品用途", "试件数", "复测试件数", "平均密度(g/cm³)", "密度差(g/cm³)",
        "平均膨胀率", "浸渍剥离", "原表结论", "规则观察", "业务状态", "缺失字段",
        "复算冲突数", "结论/规则冲突数",
    ]
    summary.append(headers)
    style_header(summary[1])
    for record in records:
        summary.append(
            [
                Path(record["source_file"]).name,
                record["batch_no"], record["product"], record["specification"], record["pressing_date"],
                record["team_leader"], record["test_date"], record["impregnation_date"], record["order_info"],
                record["product_usage"], len(record["samples"]),
                sum(1 for sample in record["samples"] if sample["sample_type"] == "retest"),
                record["average_density_g_cm3"], record["density_range_g_cm3"],
                record["average_expansion_ratio"], record["immersion_peel_result"], record["source_conclusion"],
                "；".join(f"{key}:{value}" for key, value in record["rule_observations"].items()),
                record["business_status"], ", ".join(record["missing_fields"]), len(record["conflicts"]),
                len(record["conclusion_rule_conflicts"]),
            ]
        )
    summary.freeze_panes = "A2"
    summary.auto_filter.ref = summary.dimensions
    summary.sheet_view.showGridLines = False
    for column in ("M", "N"):
        for cell in summary[column][1:]:
            cell.number_format = "0.000"
    for cell in summary["O"][1:]:
        cell.number_format = "0.00%"
    widths = {"A": 24, "B": 16, "C": 18, "D": 16, "E": 12, "F": 12, "G": 12, "H": 12,
              "I": 18, "J": 12, "K": 10, "L": 10, "M": 16, "N": 16, "O": 14, "P": 12,
              "Q": 44, "R": 34, "S": 12, "T": 28, "U": 12, "V": 16}
    for column, width in widths.items():
        summary.column_dimensions[column].width = width

    excluded_sheet = workbook.create_sheet("未纳入正常统计")
    excluded_sheet.append([
        "来源文件", "批号", "产品", "规格", "业务状态", "缺失字段", "处理说明",
    ])
    style_header(excluded_sheet[1])
    for record in excluded_records:
        excluded_sheet.append([
            Path(record["source_file"]).name,
            record["batch_no"],
            record["product"],
            record["specification"],
            "信息不足",
            ", ".join(record["missing_fields"]),
            "空表、未完成表或关键信息不足；未进入正常汇总和图表统计。",
        ])
    excluded_sheet.auto_filter.ref = excluded_sheet.dimensions
    excluded_sheet.sheet_view.showGridLines = False
    for column, width in {"A": 26, "B": 16, "C": 18, "D": 18, "E": 14, "F": 34, "G": 54}.items():
        excluded_sheet.column_dimensions[column].width = width

    details = workbook.create_sheet("试件明细")
    detail_headers = [
        "来源文件", "批号", "试件", "类型", "长(mm)", "宽(mm)", "重量(g)", "煮前平均厚度(mm)",
        "煮后平均厚度(mm)", "体积(cm³)", "原表密度", "复算密度", "采用密度", "原表膨胀率",
        "复算膨胀率", "采用膨胀率", "来源区域",
    ]
    details.append(detail_headers)
    style_header(details[1])
    for record in records:
        for sample in record["samples"]:
            details.append(
                [
                    Path(record["source_file"]).name, record["batch_no"], sample["label"], sample["sample_type"],
                    sample["length_mm"], sample["width_mm"], sample["weight_g"],
                    sample["average_thickness_before_mm"], sample["average_thickness_after_mm"], sample["volume_cm3"],
                    sample["source_density_g_cm3"], sample["calculated_density_g_cm3"], sample["density_g_cm3"],
                    sample["source_expansion_ratio"], sample["calculated_expansion_ratio"], sample["expansion_ratio"],
                    sample["source_range"],
                ]
            )
    details.freeze_panes = "A2"
    details.auto_filter.ref = details.dimensions
    details.sheet_view.showGridLines = False
    for column in ("N", "O", "P"):
        for cell in details[column][1:]:
            cell.number_format = "0.00%"
    for column in range(5, 14):
        for cell in details.iter_cols(min_col=column, max_col=column, min_row=2):
            for item in cell:
                item.number_format = "0.000"
    for column, width in {"A": 24, "B": 15, "C": 10, "D": 10, "H": 18, "I": 18, "J": 14,
                          "K": 14, "L": 14, "M": 14, "N": 14, "O": 14, "P": 14, "Q": 14}.items():
        details.column_dimensions[column].width = width

    rule_sheet = workbook.create_sheet("规则说明")
    rule_sheet.append(["规则版本", rules.get("rule_version", "")])
    rule_sheet.append(["规则状态", rules.get("status", "")])
    rule_sheet.append(["重要说明", "客户未确认的阈值仅用于异常观察，不生成正式合格/不合格结论。"])
    rule_sheet.append(["密度暂存范围", f"{(rules.get('density') or {}).get('minimum_g_cm3', '')} ~ {(rules.get('density') or {}).get('maximum_g_cm3', '')} g/cm³"])
    rule_sheet.append(["膨胀率规则", "必须先确定产品用途，再按用途选择阈值；未知用途转人工确认。"])
    rule_sheet.column_dimensions["A"].width = 20
    rule_sheet.column_dimensions["B"].width = 80
    rule_sheet.sheet_view.showGridLines = False
    style_header(rule_sheet[1])

    if records:
        chart_sheet = workbook.create_sheet("分析图表")
        chart_sheet.append(["批号/文件", "平均密度(g/cm³)", "平均膨胀率"])
        for record in records:
            chart_sheet.append([
                record["batch_no"] or Path(record["source_file"]).stem,
                record["average_density_g_cm3"],
                record["average_expansion_ratio"],
            ])
        style_header(chart_sheet[1])
        chart_sheet.column_dimensions["A"].width = 24
        chart_sheet.column_dimensions["B"].width = 18
        chart_sheet.column_dimensions["C"].width = 18
        for cell in chart_sheet["C"][1:]:
            cell.number_format = "0.00%"
        categories = Reference(chart_sheet, min_col=1, min_row=2, max_row=len(records) + 1)
        density_chart = BarChart()
        density_chart.type = "col"
        density_chart.title = "各批次平均密度对比"
        density_chart.y_axis.title = "g/cm³"
        density_chart.y_axis.numFmt = "0.0"
        density_chart.legend = None
        density_chart.add_data(Reference(chart_sheet, min_col=2, min_row=1, max_row=len(records) + 1), titles_from_data=True)
        density_chart.set_categories(categories)
        density_chart.height = 8
        density_chart.width = 15
        chart_sheet.add_chart(density_chart, "E2")
        expansion_chart = BarChart()
        expansion_chart.type = "col"
        expansion_chart.title = "各批次平均膨胀率对比"
        expansion_chart.y_axis.title = "比例"
        expansion_chart.y_axis.numFmt = "0.0%"
        expansion_chart.legend = None
        expansion_chart.add_data(Reference(chart_sheet, min_col=3, min_row=1, max_row=len(records) + 1), titles_from_data=True)
        expansion_chart.set_categories(categories)
        expansion_chart.height = 8
        expansion_chart.width = 15
        chart_sheet.add_chart(expansion_chart, "E18")
        chart_sheet.sheet_view.showGridLines = False

    thin_gray = Side(style="thin", color="D9E2F3")
    border = Border(bottom=thin_gray)
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if cell.row > 1:
                    cell.border = border
        sheet.freeze_panes = sheet.freeze_panes or "A2"
    workbook.save(output_path)


def write_analysis_report(records, anomalies, confirmations, output_path, rules, excluded_records=None):
    excluded_records = excluded_records or []
    lines = [
        "# 水煮实验分析报告",
        "",
        f"- 规则版本：`{rules.get('rule_version', '')}`",
        f"- 纳入正常汇总的文件：{len(records)}",
        f"- 因信息不足未纳入正常统计的文件：{len(excluded_records)}",
        f"- 异常/观察项：{len(anomalies)}",
        f"- 待确认项：{len(confirmations)}",
        "",
        "> 客户未确认的阈值仅用于观察和复核，不构成正式合格/不合格结论。",
        "",
        "## 文件摘要",
        "",
        "| 文件 | 批号 | 产品 | 业务状态 | 试件数 | 平均密度 | 平均膨胀率 | 剥离结果 |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for record in records:
        density = "" if record["average_density_g_cm3"] is None else f"{record['average_density_g_cm3']:.3f}"
        expansion = "" if record["average_expansion_ratio"] is None else f"{record['average_expansion_ratio']:.2%}"
        lines.append(
            f"| {Path(record['source_file']).name} | {record['batch_no']} | {record['product']} | {record['business_status']} | "
            f"{len(record['samples'])} | {density} | {expansion} | {record['immersion_peel_result']} |"
        )
    lines.extend(["", "## 未纳入正常统计", ""])
    if excluded_records:
        for record in excluded_records:
            lines.append(
                f"- `{Path(record['source_file']).name}`：信息不足（缺少 {', '.join(record['missing_fields'])}）。"
            )
    else:
        lines.append("- 无。")
    lines.extend(["", "## 异常与复核", ""])
    if anomalies:
        for item in anomalies:
            lines.append(f"- **{item['severity']} / {item['field']}**：{item['message']}")
    else:
        lines.append("- 无异常或观察项。")
    lines.extend(["", "## 人工确认", ""])
    if confirmations:
        for item in confirmations:
            lines.append(f"- `{item['confirmation_id']}`：{item['reason']}")
    else:
        lines.append("- 无待确认项。")
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_business_records(records, excluded_records, output_path, rules):
    payload = {
        "schema_version": "1.0",
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "rule_version": rules.get("rule_version"),
        "status_definitions": {
            "正常": "关键信息完整，未发现异常或待确认项。",
            "异常": "发现测量、剥离或规则观察异常，需要业务复核。",
            "信息不足": "关键字段缺失，未纳入正常统计。",
            "待确认": "产品用途或数据/结论冲突需要人工确认。",
        },
        "records": records,
        "excluded_records": excluded_records,
    }
    Path(output_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取{label}: {exc}") from exc


def validate_job(job):
    errors = []
    if not isinstance(job, dict):
        return ["任务JSON根节点必须是对象"]
    unknown = set(job) - ALLOWED_JOB_FIELDS
    if unknown:
        errors.append("任务包含未知字段: " + ", ".join(sorted(unknown)))
    required = {"schema_version", "job_id", "module_id", "phase", "run_mode", "input_files", "output_dir"}
    missing = sorted(required - set(job))
    if missing:
        errors.append("任务缺少字段: " + ", ".join(missing))
    if job.get("schema_version") != "1.0":
        errors.append("schema_version 必须为 1.0")
    if job.get("module_id") != MODULE_ID:
        errors.append("module_id 必须为 boiling")
    if not re.fullmatch(r"[A-Za-z0-9-]{6,64}", str(job.get("job_id", ""))):
        errors.append("job_id 格式不合法")
    if job.get("phase") not in {"draft", "finalize"}:
        errors.append("phase 必须为 draft 或 finalize")
    if job.get("run_mode") not in {"single", "batch"}:
        errors.append("本模块只支持 single 或 batch")
    files = job.get("input_files")
    if not isinstance(files, list) or not files or not all(isinstance(item, str) and item for item in files):
        errors.append("input_files 必须是非空字符串数组")
    if job.get("run_mode") == "single" and isinstance(files, list) and len(files) != 1:
        errors.append("single 模式必须且只能提供一个文件")
    if not isinstance(job.get("output_dir"), str) or not job.get("output_dir"):
        errors.append("output_dir 必须是非空路径")
    if job.get("phase") == "finalize":
        if not job.get("parent_job_id"):
            errors.append("finalize 阶段缺少 parent_job_id")
        if not job.get("confirmation_file"):
            errors.append("finalize 阶段缺少 confirmation_file")
    for key in ("module_config_file", "confirmation_file"):
        path_value = job.get(key)
        if path_value is not None and not isinstance(path_value, str):
            errors.append(f"{key} 必须是字符串或 null")
    return errors


def confirmation_answers(job):
    if job["phase"] != "finalize":
        return {}
    data = load_json(job["confirmation_file"], "人工确认文件")
    answers = data.get("answers")
    if not isinstance(answers, list):
        raise ValueError("人工确认文件缺少 answers 数组")
    return {
        item.get("confirmation_id"): item.get("value")
        for item in answers
        if isinstance(item, dict) and item.get("confirmation_id")
    }


def result_template(job, started, rule_version):
    return {
        "schema_version": "1.0",
        "job_id": job["job_id"],
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "status": "failed",
        "summary": {
            "input_count": len(job["input_files"]),
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "anomaly_count": 0,
            "confirmation_count": 0,
        },
        "anomalies": [],
        "confirmations": [],
        "outputs": [],
        "file_results": [],
        "errors": [],
        "service_requests": [],
        "rule_version": rule_version,
        "analysis_summary": None,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": started.isoformat(timespec="seconds"),
    }


def product_usage_confirmation(record, fingerprint):
    return {
        "confirmation_id": f"C-PRODUCT-USAGE-{fingerprint[:12]}",
        "field": "product_usage",
        "reason": "原文件未提供产品用途，无法选择膨胀率标准。",
        "suggested_value": None,
        "options": ["地板", "家具", "墙板", "栏杆", "其他"],
        "confidence": 0.0,
        "blocking": True,
        "batch_applicable": True,
        "rememberable": True,
        "source": source_ref(record["source_file"], record["source_sheet"]),
    }


def run_job(job_path):
    try:
        job = load_json(job_path, "任务JSON")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    validation_errors = validate_job(job)
    if validation_errors:
        print("; ".join(validation_errors), file=sys.stderr)
        return 2
    try:
        answers = confirmation_answers(job)
        rules = load_rules(job.get("module_config_file"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    started = dt.datetime.now().astimezone()
    result = result_template(job, started, rules.get("rule_version"))
    output_dir = Path(job["output_dir"]).resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"无法创建输出目录: {exc}", file=sys.stderr)
        return 3
    result_path = output_dir / "result.json"
    records = []
    excluded_records = []
    seen = set()
    emit("任务开始", 0)
    for index, raw_path in enumerate(job["input_files"], 1):
        source = Path(raw_path).resolve()
        fingerprint = "unavailable"
        status = "failed"
        extracted_records = 0
        missing_fields = []
        error = None
        anomaly_count = 0
        try:
            if source.suffix.lower() != ".xlsx" or source.name.startswith("~$"):
                raise ValueError("不支持的文件或 Excel 临时文件")
            if not source.is_file():
                raise ValueError("输入文件不存在")
            fingerprint = sha256_file(source)
            if fingerprint in seen:
                status = "partial_success"
                result["summary"]["skipped_count"] += 1
                error = "重复文件，已跳过"
            else:
                seen.add(fingerprint)
                record = extract_file(source)
                missing_fields = record["missing_fields"]
                blocking_missing = [field for field in REQUIRED_FOR_NORMAL_STATS if field in missing_fields]
                if blocking_missing:
                    status = "needs_confirmation"
                    record["business_status"] = "信息不足"
                    anomalies = [
                        make_anomaly(
                            record,
                            fingerprint,
                            f"MISSING-{field.upper()}",
                            "critical",
                            field,
                            None,
                            None,
                            f"缺少关键字段 {field}，该文件未进入正常汇总统计。",
                            "复核空表、未完成表或模板结构变化，并补齐原始记录。",
                            record["field_sources"].get(field),
                        )
                        for field in blocking_missing
                    ]
                    result["anomalies"].extend(anomalies)
                    anomaly_count += len(anomalies)
                    excluded_records.append(record)
                else:
                    confirmation_id = f"C-PRODUCT-USAGE-{fingerprint[:12]}"
                    usage_answer = answers.get(confirmation_id)
                    usage_confirmation_pending = False
                    if usage_answer:
                        record["product_usage"] = as_text(usage_answer)
                    elif not record["product_usage"] and job["phase"] == "draft":
                        result["confirmations"].append(product_usage_confirmation(record, fingerprint))
                        usage_confirmation_pending = True
                    elif not record["product_usage"] and job["phase"] == "finalize":
                        raise ValueError("正式阶段缺少产品用途确认答案")
                    anomalies, confirmations = evaluate_record(record, rules, fingerprint)
                    result["anomalies"].extend(anomalies)
                    anomaly_count += len(anomalies)
                    if job["phase"] == "draft":
                        result["confirmations"].extend(confirmations)
                    if usage_confirmation_pending or confirmations:
                        record["business_status"] = "待确认"
                    elif anomalies:
                        record["business_status"] = "异常"
                    else:
                        record["business_status"] = "正常"
                    records.append(record)
                    extracted_records = 1
                    result["summary"]["processed_count"] += 1
                    status = "needs_confirmation" if anomalies or confirmations or (not record["product_usage"]) else "success"
        except Exception as exc:  # isolate a bad workbook from the remaining batch
            error = str(exc)
            result["summary"]["failed_count"] += 1
            result["errors"].append(f"{source}: {exc}")
        result["file_results"].append(
            {
                "source_file": str(source),
                "fingerprint": fingerprint,
                "status": status,
                "extracted_records": extracted_records,
                "anomaly_count": anomaly_count,
                "missing_fields": missing_fields,
                "error": error,
            }
        )
        emit(f"已处理 {index}/{len(job['input_files'])}: {source.name}", round(index / len(job["input_files"]) * 80))

    if records or excluded_records:
        summary_path = output_dir / "boiling_summary.xlsx"
        report_path = output_dir / "boiling_analysis.md"
        records_path = output_dir / "boiling_records.json"
        try:
            write_summary(records, summary_path, rules, excluded_records)
            write_analysis_report(
                records,
                result["anomalies"],
                result["confirmations"],
                report_path,
                rules,
                excluded_records,
            )
            write_business_records(records, excluded_records, records_path, rules)
            result["outputs"].extend(
                [
                    {
                        "type": "summary_excel",
                        "path": str(summary_path),
                        "label": "水煮实验汇总",
                        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    },
                    {
                        "type": "analysis_report",
                        "path": str(report_path),
                        "label": "水煮实验分析报告",
                        "mime_type": "text/markdown",
                    },
                    {
                        "type": "business_records",
                        "path": str(records_path),
                        "label": "水煮实验结构化业务记录",
                        "mime_type": "application/json",
                    },
                ]
            )
        except (OSError, ValueError) as exc:
            result["errors"].append(f"生成汇总文件失败: {exc}")
            result["summary"]["failed_count"] += 1

    result["summary"]["anomaly_count"] = len(result["anomalies"])
    result["summary"]["confirmation_count"] = len(result["confirmations"])
    if result["confirmations"] or result["anomalies"]:
        result["status"] = "needs_confirmation"
    elif result["summary"]["failed_count"] or result["summary"]["skipped_count"]:
        result["status"] = "partial_success" if records else "failed"
    else:
        result["status"] = "success"
    result["analysis_summary"] = (
        f"处理{result['summary']['processed_count']}个文件，失败{result['summary']['failed_count']}个，"
        f"异常/观察{result['summary']['anomaly_count']}项，待确认{result['summary']['confirmation_count']}项。"
    )
    result["finished_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"无法写入 result.json: {exc}", file=sys.stderr)
        return 3
    emit(f"任务完成: {result['status']}", 100, "complete")
    return 3 if result["status"] == "failed" else 0


def self_check():
    with tempfile.TemporaryDirectory() as folder:
        sample_path = Path(folder) / "self-check.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "水煮实验"
        sheet.append(["批号", "TEST-001", "产品名称", "脱敏测试产品", "规格", "100*100*10"])
        sheet.append(["压制日期", dt.date(2026, 7, 15), "班长", "脱敏班长", "产品用途", "家具"])
        sheet.append(["检测日期", dt.date(2026, 7, 16), "浸胶日期", dt.date(2026, 7, 14), "订单号", "ORDER-001"])
        sheet.cell(8, 1, "样1")
        sheet.cell(8, 2, 100)
        sheet.cell(8, 3, 100)
        sheet.cell(9, 5, 120)
        for row in range(8, 14):
            sheet.cell(row, 4, 10.0)
            sheet.cell(row, 7, 10.5)
        sheet.cell(14, 6, 1.2)
        sheet.cell(14, 8, 0.05)
        sheet.cell(17, 1, "检测结论：密度检测合格，2h膨胀率检测合格，浸渍剥离检测合格")
        workbook.save(sample_path)
        record = extract_file(sample_path)
        if record["product"] != "脱敏测试产品" or len(record["samples"]) != 1:
            print("self-check failed", file=sys.stderr)
            return 4
    emit("self-check passed", 100, "self-check")
    return 0


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version")
    subparsers.add_parser("self-check")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--job", required=True)
    args = parser.parse_args()
    if args.command == "version":
        emit(f"{MODULE_ID} {MODULE_VERSION}", 100, "version")
        return 0
    if args.command == "self-check":
        return self_check()
    return run_job(args.job)


if __name__ == "__main__":
    raise SystemExit(main())

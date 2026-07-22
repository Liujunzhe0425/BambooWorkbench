import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path


def configure_protocol_streams():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


configure_protocol_streams()

try:
    import openpyxl
    import yaml
    from openpyxl.chart import BarChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
except ImportError as exc:  # pragma: no cover - exercised in a clean environment
    print(json.dumps({"type": "error", "message": str(exc)}), file=sys.stderr)
    raise SystemExit(4) from exc


MODULE_ID = "boiling"
MODULE_VERSION = "0.2.2"


def resolve_module_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[1]


MODULE_ROOT = resolve_module_root()
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
    "specification": ("规格型号", "型号规格", "产品规格", "规格"),
    "pressing_date": ("压制日期", "压制时间"),
    "team_leader": ("压机班长", "班组长", "班长"),
    "test_date": ("检测日期", "检验日期", "试验日期", "实验日期"),
    "impregnation_date": ("浸胶日期", "浸渍日期", "浸胶时间"),
    "order_info": ("订单信息", "订单编号", "订单号", "订单"),
    "product_usage": ("产品用途", "用途"),
    "record_status": ("记录状态", "完成状态", "表单状态"),
}
FIXED_FALLBACKS = {
    "batch_no": (2, 1),
    "product": (3, 3),
    "specification": (3, 7),
    "test_date": (5, 3),
}
NON_BLOCKING_METADATA_FIELDS = (
    "product",
    "specification",
    "pressing_date",
    "team_leader",
    "test_date",
    "impregnation_date",
    "order_info",
)
SAMPLE_PATTERN = re.compile(
    r"^(?:端\d+(?:-\d+)?|中\d+(?:-\d+)?|\d+|"
    r"(?:样(?:品|件)?|试件|复测)\s*[#№]?[A-Za-z0-9一二三四五六七八九十_-]+)$",
    re.I,
)
MISSING_PLACEHOLDERS = {"", "/", "／", "-", "—"}


def emit(message, percent=0):
    print(
        json.dumps(
            {"type": "progress", "percent": percent, "message": message},
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


def stable_input_scope(input_files):
    """Return a path-independent identifier shared by draft and finalize snapshots."""
    fingerprints = []
    for raw_path in input_files:
        path = Path(raw_path)
        try:
            token = sha256_file(path) if path.is_file() else f"missing:{path.name}"
        except OSError:
            token = f"unreadable:{path.name}"
        fingerprints.append(token)
    material = "\n".join(sorted(fingerprints)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def sanitize_business_value(value, key=None):
    """Remove machine-local paths from formal business deliverables."""
    if isinstance(value, dict):
        return {
            item_key: sanitize_business_value(item, item_key) for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_business_value(item, key) for item in value]
    if key == "source_file" and isinstance(value, str):
        return Path(value).name
    return value


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


def is_missing_value(value):
    return as_text(value) in MISSING_PLACEHOLDERS


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


def number_format_precision(number_format, percentage=False):
    format_text = as_text(number_format).split(";")[0]
    match = re.search(r"0(?:\.(0+))?%?", format_text)
    if not match:
        return None
    precision = len(match.group(1) or "")
    return precision if not percentage else precision


def formatted_number(value, number_format, percentage=False):
    number = as_number(value)
    if number is None:
        return ""
    precision = number_format_precision(number_format, percentage)
    if precision is None:
        precision = 3 if not percentage else 2
    if percentage:
        return f"{number:.{precision}%}"
    return f"{number:.{precision}f}"


def compact_number(value, precision=4):
    number = as_number(value)
    return f"{number:.{precision}f}" if number is not None else "缺失"


def values_conflict(source_value, calculated_value, number_format, percentage=False):
    source_number = as_number(source_value)
    calculated_number = as_number(calculated_value)
    if source_number is None or calculated_number is None:
        return False
    precision = number_format_precision(number_format, percentage)
    if precision is None:
        tolerance = 0.0005 if not percentage else 0.00005
    else:
        scale = 100 if percentage else 1
        tolerance = 0.5 * (10 ** (-precision)) / scale
    return abs(source_number - calculated_number) > tolerance + 1e-12


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
    known_labels = {normalize_label(label) for labels in FIELD_LABELS.values() for label in labels}
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
                    for candidate_column in range(
                        column + 1,
                        min(sheet.max_column, column + 3) + 1,
                    ):
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


def find_measurement_header(sheet):
    for row in range(1, min(sheet.max_row, 80) + 1):
        headers = {
            column: normalize_label(sheet.cell(row=row, column=column).value)
            for column in range(1, min(sheet.max_column, 20) + 1)
        }
        values = list(headers.values())
        if not any(value in {"序号", "试件", "样件", "样品"} for value in values):
            continue
        if not any("长度" in value for value in values) or not any(
            "密度" in value for value in values
        ):
            continue
        label_column = next(
            column for column, value in headers.items() if value in {"序号", "试件", "样件", "样品"}
        )
        density_column = next(column for column, value in headers.items() if "密度" in value)
        expansion_column = next(
            (column for column, value in headers.items() if "膨胀率" in value),
            None,
        )
        thickness_columns = [column for column, value in headers.items() if "厚度" in value]
        before_column = next(
            (column for column in thickness_columns if column < density_column),
            None,
        )
        after_column = next(
            (column for column in thickness_columns if column > density_column),
            None,
        )
        return {
            "row": row,
            "label": label_column,
            "length": next(
                (column for column, value in headers.items() if "长度" in value),
                None,
            ),
            "width": next(
                (column for column, value in headers.items() if "宽度" in value),
                None,
            ),
            "before": before_column,
            "weight": next(
                (column for column, value in headers.items() if "重量" in value or "质量" in value),
                None,
            ),
            "density": density_column,
            "after": after_column,
            "expansion": expansion_column,
        }
    return None


def is_sample_label(value):
    text = as_text(value)
    return bool(text and SAMPLE_PATTERN.fullmatch(text))


def find_sample_markers(sheet, header=None):
    header = header or find_measurement_header(sheet)
    if not header:
        return []
    markers = []
    column = header["label"]
    for row in range(header["row"] + 1, sheet.max_row + 1):
        label = as_text(sheet.cell(row=row, column=column).value)
        if not is_sample_label(label):
            continue
        structural_values = [
            as_number(sheet.cell(row=row, column=header[key]).value)
            for key in ("length", "width", "density")
            if header.get(key)
        ]
        if any(value is not None for value in structural_values):
            markers.append({"row": row, "column": column, "label": label})
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
            return (
                calculated if calculated is not None else sheet.cell(row=row, column=column).value
            )

        record = {
            "source_file": str(Path(path).resolve()),
            "source_sheet": sheet.title,
            "source_used_range": sheet.calculate_dimension(),
            "batch_no": "",
            "product": "",
            "specification": "",
            "pressing_date": "",
            "team_leader": "",
            "test_date": "",
            "impregnation_date": "",
            "order_info": "",
            "product_usage": "",
            "record_status": "",
            "field_sources": {},
            "samples": [],
            "source_conclusion": "",
            "tester": "",
            "missing_fields": [],
            "blocking_reasons": [],
            "conflicts": [],
            "conclusion_rule_conflicts": [],
            "rule_observations": {},
            "business_status": "信息不足",
        }
        for field, labels in FIELD_LABELS.items():
            raw, coordinate = find_labeled_value(sheet, labels)
            if raw in (None, "") and field in FIXED_FALLBACKS:
                row, column = FIXED_FALLBACKS[field]
                candidate = value(row, column)
                if plausible_fixed_fallback(field, candidate):
                    raw = candidate
                    coordinate = sheet.cell(row, column).coordinate
            record[field] = (
                as_date_text(raw) if field.endswith("_date") else display_cell_value(raw)
            )
            if coordinate:
                record["field_sources"][field] = coordinate
        record["batch_no"] = re.sub(r"^\s*(?:NO\.?|编号)\s*", "", record["batch_no"], flags=re.I)

        header = find_measurement_header(sheet)
        markers = find_sample_markers(sheet, header)
        conclusion_row = find_conclusion_row(sheet, 1)
        for sample_index, marker in enumerate(markers):
            start = marker["row"]
            next_start = (
                markers[sample_index + 1]["row"] if sample_index + 1 < len(markers) else None
            )
            block_end = next_start - 1 if next_start is not None else sheet.max_row
            if conclusion_row is not None and conclusion_row > start:
                block_end = min(block_end, conclusion_row - 1)
            block_end = min(block_end, start + 20)
            rows = list(range(start, block_end + 1))
            label_column = header["label"]
            measurement_rows = [
                row
                for row in rows
                if normalize_label(value(row, label_column)) not in {"平均值", "平均"}
                and any(
                    as_number(value(row, header[key])) is not None
                    for key in ("before", "after")
                    if header.get(key)
                )
            ]
            before_values = [
                as_number(value(row, header["before"]))
                for row in measurement_rows
                if header.get("before") and as_number(value(row, header["before"])) is not None
            ]
            after_values = [
                as_number(value(row, header["after"]))
                for row in measurement_rows
                if header.get("after") and as_number(value(row, header["after"])) is not None
            ]
            avg_before = mean(before_values)
            avg_after = mean(after_values)
            length = first_numeric(value, rows, header["length"]) if header.get("length") else None
            width = first_numeric(value, rows, header["width"]) if header.get("width") else None
            weight = first_numeric(value, rows, header["weight"]) if header.get("weight") else None
            density_rows = [
                row for row in rows if as_number(value(row, header["density"])) is not None
            ]
            expansion_rows = [
                row
                for row in rows
                if header.get("expansion")
                and normalize_ratio(value(row, header["expansion"])) is not None
            ]
            density_row = density_rows[0] if density_rows else None
            expansion_row = expansion_rows[0] if expansion_rows else None
            source_density = (
                as_number(value(density_row, header["density"])) if density_row else None
            )
            source_expansion = (
                normalize_ratio(value(expansion_row, header["expansion"]))
                if expansion_row and header.get("expansion")
                else None
            )
            density_cell = sheet.cell(density_row, header["density"]) if density_row else None
            expansion_cell = (
                sheet.cell(expansion_row, header["expansion"])
                if expansion_row and header.get("expansion")
                else None
            )
            volume_cm3 = (
                length * width * avg_before / 1000 if length and width and avg_before else None
            )
            calculated_density = weight / volume_cm3 if weight is not None and volume_cm3 else None
            calculated_expansion = (
                (avg_after - avg_before) / avg_before
                if avg_before not in (None, 0) and avg_after is not None
                else None
            )
            density = calculated_density if calculated_density is not None else source_density
            expansion = (
                calculated_expansion if calculated_expansion is not None else source_expansion
            )
            label = marker["label"]
            source_end_column = header.get("expansion") or header["density"]
            sample = {
                "label": label,
                "sample_type": "retest"
                if "复测" in label or "复测" in Path(path).stem
                else "normal",
                "length_mm": length,
                "width_mm": width,
                "weight_g": weight,
                "thickness_before_values_mm": before_values,
                "thickness_after_values_mm": after_values,
                "average_thickness_before_mm": avg_before,
                "average_thickness_after_mm": avg_after,
                "volume_cm3": volume_cm3,
                "source_density_g_cm3": source_density,
                "source_density_display": formatted_number(
                    source_density,
                    density_cell.number_format if density_cell else "",
                ),
                "source_density_formula": density_cell.value
                if density_cell and density_cell.data_type == "f"
                else None,
                "calculated_density_g_cm3": calculated_density,
                "density_g_cm3": density,
                "density_source_cell": density_cell.coordinate if density_cell else None,
                "source_expansion_ratio": source_expansion,
                "source_expansion_display": formatted_number(
                    source_expansion,
                    expansion_cell.number_format if expansion_cell else "",
                    percentage=True,
                ),
                "source_expansion_formula": (
                    expansion_cell.value
                    if expansion_cell and expansion_cell.data_type == "f"
                    else None
                ),
                "calculated_expansion_ratio": calculated_expansion,
                "expansion_ratio": expansion,
                "expansion_source_cell": expansion_cell.coordinate if expansion_cell else None,
                "source_range": (
                    f"{sheet.cell(start, label_column).coordinate}:"
                    f"{sheet.cell(block_end, source_end_column).coordinate}"
                ),
                "density_rule_result": "信息不足",
            }
            if values_conflict(
                source_density,
                calculated_density,
                density_cell.number_format if density_cell else "",
            ):
                record["conflicts"].append(
                    {
                        "field": "density_g_cm3",
                        "sample": label,
                        "source_value": source_density,
                        "source_display": sample["source_density_display"],
                        "calculated_value": calculated_density,
                        "difference": abs(source_density - calculated_density),
                        "cell_or_range": density_cell.coordinate,
                    }
                )
            if values_conflict(
                source_expansion,
                calculated_expansion,
                expansion_cell.number_format if expansion_cell else "",
                percentage=True,
            ):
                record["conflicts"].append(
                    {
                        "field": "expansion_ratio",
                        "sample": label,
                        "source_value": source_expansion,
                        "source_display": sample["source_expansion_display"],
                        "calculated_value": calculated_expansion,
                        "difference": abs(source_expansion - calculated_expansion),
                        "cell_or_range": expansion_cell.coordinate,
                    }
                )
            record["samples"].append(sample)

        for row in range(1, sheet.max_row + 1):
            for column in range(1, min(sheet.max_column, 20) + 1):
                text = as_text(sheet.cell(row, column).value)
                if "检测结论" not in text and "检验结论" not in text:
                    continue
                remainder = re.sub(r"^.*?(?:检测|检验)结论\s*[：:]?", "", text).strip()
                if remainder:
                    record["source_conclusion"] = remainder
                else:
                    for candidate_column in range(
                        column + 1, min(sheet.max_column, column + 4) + 1
                    ):
                        candidate = as_text(value(row, candidate_column))
                        if candidate and "检测员" not in candidate and "检验员" not in candidate:
                            record["source_conclusion"] = candidate
                            break
                record["field_sources"]["source_conclusion"] = sheet.cell(row, column).coordinate
                break
            if "source_conclusion" in record["field_sources"]:
                break
        tester_value, tester_coordinate = find_labeled_value(
            sheet,
            ("检测员", "检验员", "测试员"),
            max_rows=sheet.max_row,
        )
        record["tester"] = as_text(tester_value)
        if tester_coordinate:
            record["field_sources"]["tester"] = tester_coordinate

        densities = [
            sample["density_g_cm3"]
            for sample in record["samples"]
            if sample["density_g_cm3"] is not None
        ]
        expansions = [
            sample["expansion_ratio"]
            for sample in record["samples"]
            if sample["expansion_ratio"] is not None
        ]
        record["average_density_g_cm3"] = mean(densities)
        record["density_min_g_cm3"] = min(densities) if densities else None
        record["density_max_g_cm3"] = max(densities) if densities else None
        record["density_range_g_cm3"] = (
            record["density_max_g_cm3"] - record["density_min_g_cm3"] if densities else None
        )
        record["average_expansion_ratio"] = mean(expansions)
        conclusion = record["source_conclusion"]
        if re.search(r"浸渍剥离.{0,8}不合格", conclusion):
            record["immersion_peel_result"] = "不合格"
        elif re.search(r"浸渍剥离.{0,8}合格", conclusion):
            record["immersion_peel_result"] = "合格"
        else:
            record["immersion_peel_result"] = ""
        for field in NON_BLOCKING_METADATA_FIELDS:
            if is_missing_value(record[field]):
                record["missing_fields"].append(field)
        if is_missing_value(record["product_usage"]):
            record["missing_fields"].append("product_usage")
        if not record["source_conclusion"]:
            record["missing_fields"].append("source_conclusion")
        computable_samples = [
            sample
            for sample in record["samples"]
            if sample["density_g_cm3"] is not None and sample["expansion_ratio"] is not None
        ]
        record["computable_sample_count"] = len(computable_samples)
        if not record["samples"]:
            record["blocking_reasons"].append("未识别到测量试件")
        elif not computable_samples:
            record["blocking_reasons"].append("无可同时复算密度和膨胀率的试件")
        status_text = normalize_label(record["record_status"])
        if "未完成" in status_text or "空表" in status_text:
            record["blocking_reasons"].append("原表标记为未完成")
        if not record["source_conclusion"] and is_missing_value(record["test_date"]):
            record["blocking_reasons"].append("检测日期和检测结论均缺失，判定为未完成表")
        record["is_incomplete"] = bool(record["blocking_reasons"])
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
            rules_path = (
                candidate_path
                if candidate_path.is_absolute()
                else config_path.parent / candidate_path
            )
        elif isinstance(data, dict) and ("density" in data or "expansion" in data):
            return data
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(data, dict):
        raise ValueError("规则文件根节点必须是对象")
    return data


def make_anomaly(
    record,
    fingerprint,
    suffix,
    severity,
    field,
    value,
    rule_id,
    message,
    suggestion,
    cell_or_range=None,
):
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
    conclusion_cell=None,
):
    if source_claim is None or observed_outside is None or source_claim == (not observed_outside):
        return
    source_text = "合格" if source_claim else "不合格"
    rule_text = "不合格" if observed_outside else "合格"
    source_name = Path(record["source_file"]).name
    display_field = f"{field}｜{source_name}｜原表{source_text}→规则{rule_text}（建议按规则）"
    if isinstance(observed_value, dict):
        observed_detail = (
            f"最小值 {compact_number(observed_value.get('minimum'))}、"
            f"最大值 {compact_number(observed_value.get('maximum'))}、"
            f"密度差 {compact_number(observed_value.get('difference'))}"
        )
    elif observed_value is not None:
        observed_detail = f"规则复核值 {observed_value:.2%}"
    else:
        observed_detail = "规则复核值缺失"
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
            {
                "source_conclusion": source_text,
                "rule_observation": rule_text,
                "value": observed_value,
            },
            "BOILING-CONCLUSION-CONFLICT-001",
            f"原表{field}结论为{source_text}，但按本版规则复核为{rule_text}；两者均已保留。",
            "复核原表签字结论、测量数据和规则版本；人工确认前不得覆盖原表结论。",
        )
    )
    confirmations.append(
        {
            "confirmation_id": f"C-CONCLUSION-RULE-{field}-{fingerprint[:12]}",
            "field": display_field,
            "reason": (
                f"{source_name}：原表结论“{source_text}”与规则观察“{rule_text}”不一致；"
                f"{observed_detail}。建议按现行规则选择“{rule_text}”，原表结论仍会保留。"
            ),
            "suggested_value": rule_text,
            "options": [source_text, rule_text],
            "confidence": 0.0,
            "blocking": False,
            "batch_applicable": False,
            "rememberable": False,
            "source": source_ref(record["source_file"], record["source_sheet"], conclusion_cell),
        }
    )


def evaluate_record(record, rules, fingerprint):
    anomalies = []
    confirmations = []
    rule_hits = []
    density_rule = rules.get("density") or {}
    density_rule_id = density_rule.get("rule_id")
    minimum = as_number(density_rule.get("minimum_g_cm3"))
    maximum = as_number(density_rule.get("maximum_g_cm3"))
    maximum_difference = as_number(density_rule.get("maximum_difference_g_cm3"))
    density_samples = [
        sample for sample in record["samples"] if sample["density_g_cm3"] is not None
    ]
    outside_samples = []
    for sample in density_samples:
        value = sample["density_g_cm3"]
        outside = (minimum is not None and value < minimum - 1e-12) or (
            maximum is not None and value > maximum + 1e-12
        )
        sample["density_rule_result"] = "不合格" if outside else "合格"
        if outside:
            outside_samples.append(sample["label"])
    density_difference = record.get("density_range_g_cm3")
    difference_outside = (
        density_difference is not None
        and maximum_difference is not None
        and density_difference > maximum_difference + 1e-12
    )
    density_pass = bool(density_samples) and not outside_samples and not difference_outside
    record["density_rule_pass"] = density_pass if density_samples else None
    record["density_outside_samples"] = outside_samples
    record["rule_observations"]["density"] = (
        "合格" if density_pass else ("不合格" if density_samples else "信息不足")
    )
    rule_hits.append(
        {
            "rule_id": density_rule_id,
            "field": "density",
            "result": record["rule_observations"]["density"],
            "minimum_g_cm3": record.get("density_min_g_cm3"),
            "maximum_g_cm3": record.get("density_max_g_cm3"),
            "difference_g_cm3": density_difference,
            "outside_samples": outside_samples,
            "source_cells": [
                sample["density_source_cell"]
                for sample in density_samples
                if sample.get("density_source_cell")
            ],
        }
    )
    if density_samples and not density_pass:
        reasons = []
        if outside_samples:
            reasons.append("超出 1.1～1.3 g/cm³ 的试件：" + "、".join(outside_samples))
        if difference_outside:
            reasons.append(f"密度差 {density_difference:.6f} g/cm³ 大于 0.1 g/cm³")
        anomalies.append(
            make_anomaly(
                record,
                fingerprint,
                "DENSITY",
                "warning",
                "density",
                {
                    "minimum": record.get("density_min_g_cm3"),
                    "maximum": record.get("density_max_g_cm3"),
                    "difference": density_difference,
                    "outside_samples": outside_samples,
                },
                density_rule_id,
                "；".join(reasons),
                "核对各试件密度、来源单元格和密度差；边界 1.1、1.3、0.1 均按合格处理。",
            )
        )

    expansion_rule = rules.get("expansion") or {}
    expansion_rule_id = expansion_rule.get("rule_id")
    expansion_value = record.get("average_expansion_ratio")
    usage = as_text(record.get("product_usage"))
    excellent_max = normalize_ratio(expansion_rule.get("excellent_max_ratio"))
    numeric_pass = None
    expansion_grade = ""
    human_review = False
    rule_detail = ""
    if expansion_value is None:
        rule_detail = "信息不足"
    elif not usage:
        rule_detail = "待确认产品用途"
    elif usage in {"地板", "家具"}:
        pass_max = normalize_ratio(
            (expansion_rule.get("floor_furniture") or {}).get("pass_max_ratio")
        )
        if excellent_max is not None and expansion_value <= excellent_max + 1e-12:
            numeric_pass = True
            expansion_grade = "绿色优等候选"
            human_review = True
            rule_detail = "膨胀率≤6.5%，需结合开裂观察确认绿色优等"
        elif pass_max is not None and expansion_value <= pass_max + 1e-12:
            numeric_pass = True
            expansion_grade = "蓝色合格"
            human_review = True
            rule_detail = "6.5%＜膨胀率≤8%，膨胀率维度蓝色合格，仍需核对开裂观察"
        else:
            numeric_pass = False
            expansion_grade = "红色不合格"
            rule_detail = "膨胀率＞8%，红色不合格"
    elif usage in {"墙板", "栏杆"}:
        blue_min = normalize_ratio((expansion_rule.get("wall_railing") or {}).get("blue_min_ratio"))
        pass_max = normalize_ratio((expansion_rule.get("wall_railing") or {}).get("pass_max_ratio"))
        if excellent_max is not None and expansion_value <= excellent_max + 1e-12:
            numeric_pass = True
            expansion_grade = "绿色优等候选"
            human_review = True
            rule_detail = "膨胀率≤6.5%，需结合开裂观察确认绿色优等"
        elif blue_min is not None and expansion_value < blue_min - 1e-12:
            human_review = True
            rule_detail = "墙板/栏杆膨胀率＞6.5%且＜8%，v0.1 规则缺口转人工复核"
        elif pass_max is not None and expansion_value <= pass_max + 1e-12:
            numeric_pass = True
            expansion_grade = "蓝色合格"
            human_review = True
            rule_detail = "8%≤膨胀率≤12%，膨胀率维度蓝色合格，仍需核对开裂观察"
        else:
            numeric_pass = False
            expansion_grade = "红色不合格"
            rule_detail = "膨胀率＞12%，红色不合格"
    else:
        human_review = True
        rule_detail = f"产品用途“{usage}”没有自动判定规则"

    record["expansion_numeric_pass"] = numeric_pass
    record["expansion_grade"] = expansion_grade
    record["expansion_human_review_required"] = human_review
    record["rule_observations"]["expansion"] = rule_detail
    rule_hits.append(
        {
            "rule_id": expansion_rule_id,
            "field": "expansion",
            "result": rule_detail,
            "product_usage": usage,
            "average_expansion_ratio": expansion_value,
            "human_review_required": human_review,
            "source_cells": [
                sample["expansion_source_cell"]
                for sample in record["samples"]
                if sample.get("expansion_source_cell")
            ],
        }
    )
    if numeric_pass is False:
        anomalies.append(
            make_anomaly(
                record,
                fingerprint,
                "EXPANSION",
                "warning",
                "average_expansion_ratio",
                expansion_value,
                expansion_rule_id,
                rule_detail,
                "复核产品用途、平均膨胀率和来源单元格，并保留原表结论供人工复核。",
            )
        )
    if human_review and usage and numeric_pass is None:
        reason = rule_detail
        confirmations.append(
            {
                "confirmation_id": f"C-EXPANSION-REVIEW-{fingerprint[:12]}",
                "field": "expansion_review",
                "reason": reason,
                "suggested_value": None,
                "options": ["开裂观察符合对应等级", "开裂观察不符合对应等级", "继续待复核"],
                "confidence": 0.0,
                "blocking": False,
                "batch_applicable": False,
                "rememberable": False,
                "source": source_ref(record["source_file"], record["source_sheet"]),
            }
        )
    record["rule_hits"] = rule_hits
    conclusion = record.get("source_conclusion", "")
    add_conclusion_rule_conflict(
        record,
        anomalies,
        confirmations,
        fingerprint,
        "密度",
        density_rule.get("rule_id"),
        conclusion_pass_claim(conclusion, ("密度",)),
        (not density_pass) if density_samples else None,
        {
            "minimum": record.get("density_min_g_cm3"),
            "maximum": record.get("density_max_g_cm3"),
            "difference": density_difference,
        },
        conclusion_cell=None,
    )
    add_conclusion_rule_conflict(
        record,
        anomalies,
        confirmations,
        fingerprint,
        "膨胀率",
        expansion_rule.get("rule_id"),
        conclusion_pass_claim(conclusion, ("膨胀率", "膨胀")),
        (not numeric_pass) if numeric_pass is not None else None,
        expansion_value,
        conclusion_cell=None,
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
        source_name = Path(record["source_file"]).name
        source_display = conflict.get("source_display") or compact_number(
            conflict["source_value"]
        )
        if conflict["field"] == "expansion_ratio":
            field_name = "膨胀率"
            calculated_display = f"{conflict['calculated_value']:.2%}"
        else:
            field_name = "密度"
            calculated_display = f"{conflict['calculated_value']:.3f}"
        display_field = (
            f"{field_name}｜{source_name}｜{conflict['sample']}"
            f"（{conflict.get('cell_or_range') or '来源位置未知'}）｜"
            f"原表{source_display}→复算{calculated_display}（建议复算值）"
        )
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
                "field": display_field,
                "reason": (
                    f"{source_name} 的 {conflict['sample']}："
                    f"原表值 {source_display} 与复算值 {calculated_display} 冲突；"
                    "建议采用复算值，"
                    "两者仍会在报告中保留。"
                ),
                "suggested_value": conflict["calculated_value"],
                "options": [conflict["source_value"], conflict["calculated_value"]],
                "confidence": 0.5,
                "blocking": False,
                "batch_applicable": False,
                "rememberable": False,
                "source": source_ref(
                    record["source_file"], record["source_sheet"], conflict.get("cell_or_range")
                ),
            }
        )
    return anomalies, confirmations


def style_header(cells):
    fill = PatternFill("solid", fgColor="1F4E78")
    for cell in cells:
        cell.font = Font(name="微软雅黑", bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def style_result_cell(cell, value):
    """Apply the delivery-standard color while keeping the text conclusion visible."""
    text = str(value or "")
    if "红色" in text or text in {"异常", "不合格"}:
        color = "F4CCCC"
    elif "蓝色" in text:
        color = "CFE2F3"
    elif "绿色" in text or text in {"正常", "合格"}:
        color = "D9EAD3"
    elif text in {"待确认", "是"} or "待确认" in text or "人工复核" in text:
        color = "FFF2CC"
    elif text == "信息不足":
        color = "D9D9D9"
    else:
        return
    cell.fill = PatternFill("solid", fgColor=color)
    cell.font = Font(name="微软雅黑", color="000000")


def write_summary(records, output_path, rules, excluded_records=None):
    excluded_records = excluded_records or []
    workbook = openpyxl.Workbook()
    summary = workbook.active
    summary.title = "水煮检测汇总"
    headers = [
        "来源文件",
        "批号",
        "产品",
        "规格",
        "压制日期",
        "班长",
        "检测日期",
        "浸胶日期",
        "订单信息",
        "产品用途",
        "试件数",
        "复测试件数",
        "端1-1密度(g/cm³)",
        "端1-1膨胀率",
        "端1-2密度(g/cm³)",
        "端1-2膨胀率",
        "中1密度(g/cm³)",
        "中1膨胀率",
        "端2-1密度(g/cm³)",
        "端2-1膨胀率",
        "端2-2密度(g/cm³)",
        "端2-2膨胀率",
        "平均密度(g/cm³)",
        "最小密度(g/cm³)",
        "最大密度(g/cm³)",
        "密度差(g/cm³)",
        "密度规则",
        "平均膨胀率",
        "膨胀率规则",
        "自动等级",
        "需人工复核",
        "浸渍剥离",
        "原表结论",
        "业务状态",
        "复算冲突数",
        "结论/规则冲突数",
    ]
    summary.append(headers)
    style_header(summary[1])
    for record in records:
        samples_by_label = {}
        for sample in record["samples"]:
            samples_by_label.setdefault(str(sample.get("label") or "").strip(), sample)
        position_values = []
        for label in ("端1-1", "端1-2", "中1", "端2-1", "端2-2"):
            sample = samples_by_label.get(label, {})
            position_values.extend(
                [
                    sample.get("density_g_cm3") or 0,
                    sample.get("expansion_ratio") or 0,
                ]
            )
        summary.append(
            [
                Path(record["source_file"]).name,
                record["batch_no"],
                record["product"],
                record["specification"],
                record["pressing_date"],
                record["team_leader"],
                record["test_date"],
                record["impregnation_date"],
                record["order_info"],
                record["product_usage"],
                len(record["samples"]),
                sum(1 for sample in record["samples"] if sample["sample_type"] == "retest"),
                *position_values,
                record["average_density_g_cm3"],
                record["density_min_g_cm3"],
                record["density_max_g_cm3"],
                record["density_range_g_cm3"],
                record["rule_observations"].get("density", ""),
                record["average_expansion_ratio"],
                record["rule_observations"].get("expansion", ""),
                record.get("expansion_grade", ""),
                "是" if record.get("expansion_human_review_required") else "否",
                record["immersion_peel_result"],
                record["source_conclusion"],
                record["business_status"],
                len(record["conflicts"]),
                len(record["conclusion_rule_conflicts"]),
            ]
        )
    summary.freeze_panes = "A2"
    summary.auto_filter.ref = summary.dimensions
    summary.sheet_view.showGridLines = False
    for column in ("M", "O", "Q", "S", "U", "W", "X", "Y", "Z"):
        for cell in summary[column][1:]:
            cell.number_format = "0.000"
    for column in ("N", "P", "R", "T", "V", "AB"):
        for cell in summary[column][1:]:
            cell.number_format = "0.00%"
    for row in range(2, summary.max_row + 1):
        style_result_cell(summary[f"AA{row}"], summary[f"AA{row}"].value)
        style_result_cell(summary[f"AD{row}"], summary[f"AD{row}"].value)
        style_result_cell(summary[f"AE{row}"], summary[f"AE{row}"].value)
        style_result_cell(summary[f"AH{row}"], summary[f"AH{row}"].value)
    widths = {
        "A": 24,
        "B": 16,
        "C": 18,
        "D": 16,
        "E": 12,
        "F": 14,
        "G": 12,
        "H": 12,
        "I": 18,
        "J": 12,
        "K": 10,
        "L": 10,
        "M": 17,
        "N": 14,
        "O": 17,
        "P": 14,
        "Q": 17,
        "R": 14,
        "S": 17,
        "T": 14,
        "U": 17,
        "V": 14,
        "W": 15,
        "X": 15,
        "Y": 15,
        "Z": 15,
        "AA": 12,
        "AB": 14,
        "AC": 50,
        "AD": 16,
        "AE": 12,
        "AF": 12,
        "AG": 48,
        "AH": 12,
        "AI": 12,
        "AJ": 16,
    }
    for column, width in widths.items():
        summary.column_dimensions[column].width = width

    excluded_sheet = workbook.create_sheet("未纳入正常统计")
    excluded_sheet.append(
        [
            "来源文件",
            "批号",
            "产品",
            "规格",
            "业务状态",
            "缺失字段",
            "阻断原因",
            "处理说明",
        ]
    )
    style_header(excluded_sheet[1])
    for record in excluded_records:
        excluded_sheet.append(
            [
                Path(record["source_file"]).name,
                record["batch_no"],
                record["product"],
                record["specification"],
                "信息不足",
                ", ".join(record["missing_fields"]),
                "；".join(record.get("blocking_reasons", [])),
                "空表、未完成表或无可计算试件；未进入正常汇总和图表统计。",
            ]
        )
    excluded_sheet.auto_filter.ref = excluded_sheet.dimensions
    excluded_sheet.sheet_view.showGridLines = False
    for row in range(2, excluded_sheet.max_row + 1):
        style_result_cell(excluded_sheet[f"E{row}"], excluded_sheet[f"E{row}"].value)
    for column, width in {
        "A": 26,
        "B": 16,
        "C": 18,
        "D": 18,
        "E": 14,
        "F": 34,
        "G": 48,
        "H": 54,
    }.items():
        excluded_sheet.column_dimensions[column].width = width

    details = workbook.create_sheet("试件明细")
    detail_headers = [
        "来源文件",
        "批号",
        "试件",
        "类型",
        "长(mm)",
        "宽(mm)",
        "重量(g)",
        "煮前平均厚度(mm)",
        "煮后平均厚度(mm)",
        "体积(cm³)",
        "原表密度",
        "原表显示密度",
        "复算密度",
        "采用密度",
        "密度规则",
        "密度来源单元格",
        "原表膨胀率",
        "原表显示膨胀率",
        "复算膨胀率",
        "采用膨胀率",
        "膨胀率来源单元格",
        "来源区域",
    ]
    details.append(detail_headers)
    style_header(details[1])
    for record in records:
        for sample in record["samples"]:
            details.append(
                [
                    Path(record["source_file"]).name,
                    record["batch_no"],
                    sample["label"],
                    sample["sample_type"],
                    sample["length_mm"],
                    sample["width_mm"],
                    sample["weight_g"],
                    sample["average_thickness_before_mm"],
                    sample["average_thickness_after_mm"],
                    sample["volume_cm3"],
                    sample["source_density_g_cm3"],
                    sample["source_density_display"],
                    sample["calculated_density_g_cm3"],
                    sample["density_g_cm3"],
                    sample["density_rule_result"],
                    sample["density_source_cell"],
                    sample["source_expansion_ratio"],
                    sample["source_expansion_display"],
                    sample["calculated_expansion_ratio"],
                    sample["expansion_ratio"],
                    sample["expansion_source_cell"],
                    sample["source_range"],
                ]
            )
    details.freeze_panes = "A2"
    details.auto_filter.ref = details.dimensions
    details.sheet_view.showGridLines = False
    for column in ("Q", "S", "T"):
        for cell in details[column][1:]:
            cell.number_format = "0.00%"
    for column in (5, 6, 7, 8, 9, 10, 11, 13, 14):
        for cell in details.iter_cols(min_col=column, max_col=column, min_row=2):
            for item in cell:
                item.number_format = "0.000"
    for row in range(2, details.max_row + 1):
        style_result_cell(details[f"O{row}"], details[f"O{row}"].value)
    for column, width in {
        "A": 24,
        "B": 15,
        "C": 10,
        "D": 10,
        "H": 18,
        "I": 18,
        "J": 14,
        "K": 14,
        "L": 16,
        "M": 14,
        "N": 14,
        "O": 12,
        "P": 18,
        "Q": 14,
        "R": 18,
        "S": 14,
        "T": 14,
        "U": 20,
        "V": 16,
    }.items():
        details.column_dimensions[column].width = width

    rule_sheet = workbook.create_sheet("规则说明")
    rule_sheet.append(["规则版本", rules.get("rule_version", "")])
    rule_sheet.append(["规则状态", rules.get("status", "")])
    rule_sheet.append(
        [
            "密度正式规则",
            "每个有效试件 1.1～1.3 g/cm³（含边界），且最大值-最小值≤0.1 g/cm³（含边界）。",
        ]
    )
    rule_sheet.append(["绿色优等", "平均膨胀率≤6.5%，并须结合表面、侧面和端头开裂观察人工确认。"])
    rule_sheet.append(["地板/家具", "6.5%＜平均膨胀率≤8% 为蓝色合格；＞8% 为红色不合格。"])
    rule_sheet.append(["墙板/栏杆", "8%≤平均膨胀率≤12% 为蓝色合格；＞12% 为红色不合格。"])
    rule_sheet.append(["v0.1 人工边界", "墙板/栏杆平均膨胀率＞6.5%且＜8% 不自动标色，转人工复核。"])
    rule_sheet.append(["用途缺失", "不得猜测产品用途；生成一次可批量应用的确认项。"])
    rule_sheet.column_dimensions["A"].width = 20
    rule_sheet.column_dimensions["B"].width = 80
    rule_sheet.sheet_view.showGridLines = False
    style_header(rule_sheet[1])

    if records:
        chart_sheet = workbook.create_sheet("分析图表")
        chart_sheet.append(["批号/文件", "平均密度(g/cm³)", "平均膨胀率"])
        for record in records:
            chart_sheet.append(
                [
                    record["batch_no"] or Path(record["source_file"]).stem,
                    record["average_density_g_cm3"],
                    record["average_expansion_ratio"],
                ]
            )
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
        density_chart.add_data(
            Reference(chart_sheet, min_col=2, min_row=1, max_row=len(records) + 1),
            titles_from_data=True,
        )
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
        expansion_chart.add_data(
            Reference(chart_sheet, min_col=3, min_row=1, max_row=len(records) + 1),
            titles_from_data=True,
        )
        expansion_chart.set_categories(categories)
        expansion_chart.height = 8
        expansion_chart.width = 15
        chart_sheet.add_chart(expansion_chart, "E18")

        result_counts = {"合格": 0, "不合格": 0}
        for record in records:
            source_conclusion = str(record.get("source_conclusion") or "")
            if "不合格" in source_conclusion:
                result_counts["不合格"] += 1
            elif "合格" in source_conclusion:
                result_counts["合格"] += 1
        result_table_row = len(records) + 4
        chart_sheet.cell(result_table_row, 1, "原表综合结论")
        chart_sheet.cell(result_table_row, 2, "文件数")
        chart_sheet.cell(result_table_row + 1, 1, "合格")
        chart_sheet.cell(result_table_row + 1, 2, result_counts["合格"])
        chart_sheet.cell(result_table_row + 2, 1, "不合格")
        chart_sheet.cell(result_table_row + 2, 2, result_counts["不合格"])
        style_header(chart_sheet[result_table_row])

        result_chart = PieChart()
        result_chart.title = "原表综合结论：合格与不合格"
        result_chart.add_data(
            Reference(
                chart_sheet,
                min_col=2,
                min_row=result_table_row,
                max_row=result_table_row + 2,
            ),
            titles_from_data=True,
        )
        result_chart.set_categories(
            Reference(
                chart_sheet,
                min_col=1,
                min_row=result_table_row + 1,
                max_row=result_table_row + 2,
            )
        )
        result_chart.dataLabels = DataLabelList()
        result_chart.dataLabels.showPercent = True
        result_chart.dataLabels.showLeaderLines = True
        result_chart.height = 8
        result_chart.width = 15
        chart_sheet.add_chart(result_chart, "E34")
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


def write_analysis_report(
    records, anomalies, confirmations, output_path, rules, excluded_records=None
):
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
        "> 本报告按 2026-07-18 确认的 v0.1 规则复核。产品用途缺失、开裂观察缺失以及"
        "墙板/栏杆 6.5%～8% 规则缺口均转人工确认。",
        "",
        "## 文件摘要",
        "",
        "| 文件 | 批号 | 产品 | 业务状态 | 试件数 | 密度最小值 | 密度最大值 | 密度差 | "
        "平均膨胀率 | 剥离结果 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for record in records:
        density_min = (
            "" if record["density_min_g_cm3"] is None else f"{record['density_min_g_cm3']:.3f}"
        )
        density_max = (
            "" if record["density_max_g_cm3"] is None else f"{record['density_max_g_cm3']:.3f}"
        )
        density_diff = (
            "" if record["density_range_g_cm3"] is None else f"{record['density_range_g_cm3']:.3f}"
        )
        expansion = (
            ""
            if record["average_expansion_ratio"] is None
            else f"{record['average_expansion_ratio']:.2%}"
        )
        lines.append(
            f"| {Path(record['source_file']).name} | {record['batch_no']} | "
            f"{record['product']} | {record['business_status']} | {len(record['samples'])} | "
            f"{density_min} | {density_max} | {density_diff} | {expansion} | "
            f"{record['immersion_peel_result']} |"
        )
    lines.extend(["", "## 未纳入正常统计", ""])
    if excluded_records:
        for record in excluded_records:
            blocking_reasons = "；".join(record.get("blocking_reasons", []))
            lines.append(
                f"- `{Path(record['source_file']).name}`：信息不足（{blocking_reasons}）。"
            )
    else:
        lines.append("- 无。")
    lines.extend(["", "## 异常与复核", ""])
    if anomalies:
        for item in anomalies:
            sf = Path(item.get('source', {}).get('source_file', '')).name or '?'
            sh = item.get('source', {}).get('sheet', '?')
            lines.append(
                f"- **{item['severity']} / {item['field']}**"
                f"（来源：{sf} / {sh}）：{item['message']}"
            )
        lines.append("- 无异常或观察项。")
    lines.extend(["", "## 人工确认", ""])
    if confirmations:
        for item in confirmations:
            sf = Path(item.get('source', {}).get('source_file', '')).name or '?'
            sh = item.get('source', {}).get('sheet', '?')
            lines.append(f"- `{item['confirmation_id']}`（来源：{sf} / {sh}）：{item['reason']}")
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_business_records(records, excluded_records, output_path, rules):
    payload = {
        "schema_version": "1.0",
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "rule_version": rules.get("rule_version"),
        "status_definitions": {
            "正常": "可计算且未发现异常或待确认项。",
            "异常": "发现测量、剥离或规则观察异常，需要业务复核。",
            "信息不足": "空表、未完成表或无可计算试件，未纳入正常统计。",
            "待确认": "产品用途或数据/结论冲突需要人工确认。",
        },
        "records": sanitize_business_value(records),
        "excluded_records": sanitize_business_value(excluded_records),
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
    required = {
        "schema_version",
        "job_id",
        "module_id",
        "phase",
        "run_mode",
        "input_files",
        "output_dir",
    }
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
    if (
        not isinstance(files, list)
        or not files
        or not all(isinstance(item, str) and item for item in files)
    ):
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
        return {"by_id": {}, "batch_usage": ""}
    data = load_json(job["confirmation_file"], "人工确认文件")
    answers = data.get("answers")
    if not isinstance(answers, list):
        raise ValueError("人工确认文件缺少 answers 数组")
    by_id = {
        item.get("confirmation_id"): item.get("value")
        for item in answers
        if isinstance(item, dict) and item.get("confirmation_id")
    }
    batch_usage = ""
    for item in answers:
        if not isinstance(item, dict):
            continue
        confirmation_id = as_text(item.get("confirmation_id"))
        if confirmation_id.startswith("C-PRODUCT-USAGE-BATCH-") and item.get("value"):
            batch_usage = as_text(item.get("value"))
            break
        if (
            confirmation_id.startswith("C-PRODUCT-USAGE-")
            and item.get("apply_to_batch")
            and item.get("value")
        ):
            batch_usage = as_text(item.get("value"))
            break
    return {"by_id": by_id, "batch_usage": batch_usage}


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


def product_usage_confirmation(record, scope_id):
    return {
        "confirmation_id": f"C-PRODUCT-USAGE-BATCH-{scope_id}",
        "field": "product_usage",
        "reason": (
            "本批部分或全部输入文件未提供产品用途；"
            "请确认一次并批量应用（地板/家具/墙板/栏杆/其他），"
            "模块不得自行猜测膨胀率标准。"
        ),
        "suggested_value": None,
        "options": ["地板", "家具", "墙板", "栏杆", "其他"],
        "confidence": 0.0,
        "blocking": True,
        "batch_applicable": True,
        "rememberable": True,
        "source": source_ref(record["source_file"], record["source_sheet"]),
    }


def unresolved_finalize_anomaly(record, fingerprint, confirmation):
    confirmation_id = confirmation["confirmation_id"]
    stable_suffix = hashlib.sha256(confirmation_id.encode("utf-8")).hexdigest()[:12]
    return {
        "anomaly_id": f"A-FINALIZE-{stable_suffix}",
        "severity": "warning",
        "field": confirmation.get("field", "manual_review"),
        "value": confirmation.get("suggested_value"),
        "rule_id": "BOILING-FINALIZE-NONBLOCKING-001",
        "message": confirmation.get("reason", "最终阶段出现需要人工复核的观察项。"),
        "suggestion": "本次结果已保留为非阻断观察项；如需调整业务结论，请在业务复核流程中处理。",
        "source": confirmation.get("source")
        or source_ref(record["source_file"], record["source_sheet"]),
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
    usage_prompt_added = False
    is_finalize = job["phase"] == "finalize"
    scope_id = stable_input_scope(job["input_files"])
    answer_map = answers["by_id"]
    batch_usage = answers["batch_usage"]
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
                if record["is_incomplete"]:
                    status = "partial_success"
                    record["business_status"] = "信息不足"
                    anomalies = [
                        make_anomaly(
                            record,
                            fingerprint,
                            "INCOMPLETE",
                            "critical",
                            "workbook_completion",
                            record["blocking_reasons"],
                            "BOILING-INPUT-COMPLETENESS-001",
                            "；".join(record["blocking_reasons"]),
                            "复核空表、未完成表或模板结构变化；补齐后重新运行。",
                        )
                    ]
                    result["anomalies"].extend(anomalies)
                    anomaly_count += len(anomalies)
                    excluded_records.append(record)
                    extracted_records = 1
                    result["summary"]["processed_count"] += 1
                else:
                    finalize_anomalies = []
                    if is_missing_value(record["product_usage"]):
                        record["product_usage"] = ""
                    batch_confirmation_id = f"C-PRODUCT-USAGE-BATCH-{scope_id}"
                    # Individual product_usage confirmations not generated - batch-level is used.
                    usage_answer = (
                        batch_usage
                        or answer_map.get(batch_confirmation_id)
                    )
                    usage_confirmation_pending = False
                    if usage_answer:
                        record["product_usage"] = as_text(usage_answer)
                        record["missing_fields"] = [
                            field for field in record["missing_fields"] if field != "product_usage"
                        ]
                    elif is_missing_value(record["product_usage"]):
                        if not is_finalize and not usage_prompt_added:
                            result["confirmations"].append(
                                product_usage_confirmation(record, scope_id)
                            )
                            usage_prompt_added = True
                        if is_finalize:
                            missing_usage = product_usage_confirmation(record, scope_id)
                            finalize_anomalies.append(
                                unresolved_finalize_anomaly(record, fingerprint, missing_usage)
                            )
                        else:
                            usage_confirmation_pending = True
                    anomalies, confirmations = evaluate_record(record, rules, fingerprint)
                    pending_confirmations = [
                        item for item in confirmations if item["confirmation_id"] not in answer_map
                    ]
                    if is_finalize:
                        finalize_anomalies.extend(
                            unresolved_finalize_anomaly(record, fingerprint, item)
                            for item in pending_confirmations
                        )
                        pending_confirmations = []
                    else:
                        result["confirmations"].extend(pending_confirmations)
                    anomalies.extend(finalize_anomalies)
                    result["anomalies"].extend(anomalies)
                    anomaly_count += len(anomalies)
                    if usage_confirmation_pending or pending_confirmations:
                        record["business_status"] = "待确认"
                    elif anomalies:
                        record["business_status"] = "异常"
                    else:
                        record["business_status"] = "正常"
                    records.append(record)
                    extracted_records = 1
                    result["summary"]["processed_count"] += 1
                    if usage_confirmation_pending or pending_confirmations:
                        status = "needs_confirmation"
                    elif anomalies:
                        status = "partial_success"
                    else:
                        status = "success"
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
        emit(
            f"已处理 {index}/{len(job['input_files'])}: {source.name}",
            round(index / len(job["input_files"]) * 80),
        )

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
                        "mime_type": (
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        ),
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

    result["summary"]["anomaly_count"] = len(result["anomalies"])
    result["summary"]["confirmation_count"] = len(result["confirmations"])
    if result["confirmations"]:
        result["status"] = "needs_confirmation"
    elif result["summary"]["processed_count"] == 0 and result["summary"]["failed_count"]:
        result["status"] = "failed"
    elif (
        result["anomalies"]
        or excluded_records
        or result["summary"]["failed_count"]
        or result["summary"]["skipped_count"]
        or result["errors"]
    ):
        result["status"] = "partial_success"
    else:
        result["status"] = "success"
    result["analysis_summary"] = (
        f"处理{result['summary']['processed_count']}个文件，失败{result['summary']['failed_count']}个，"
        f"未纳入正常统计{len(excluded_records)}个，异常/观察{result['summary']['anomaly_count']}项，"
        f"待确认{result['summary']['confirmation_count']}项。"
    )
    result["finished_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"无法写入 result.json: {exc}", file=sys.stderr)
        return 3
    emit(f"任务完成: {result['status']}", 100)
    return 3 if result["status"] == "failed" else 0


def self_check():
    with tempfile.TemporaryDirectory() as folder:
        sample_path = Path(folder) / "self-check.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "水煮实验"
        sheet.append(["水煮实验检测记录（自检）"])
        sheet.append(["批号", "TEST-001", "产品名称", "脱敏测试产品", "规格", "100*100*10"])
        sheet.append(["压制日期", dt.date(2026, 7, 15), "班长", "脱敏班长", "产品用途", "家具"])
        sheet.append(
            [
                "检测日期",
                dt.date(2026, 7, 16),
                "浸胶日期",
                dt.date(2026, 7, 14),
                "订单号",
                "ORDER-001",
            ]
        )
        sheet.append(
            [
                "试件",
                "长度(mm)",
                "宽度(mm)",
                "煮前厚度(mm)",
                "重量(g)",
                "密度(g/cm³)",
                "煮后厚度(mm)",
                "膨胀率",
            ]
        )
        sheet.cell(6, 1, "样1")
        sheet.cell(6, 2, 100)
        sheet.cell(6, 3, 100)
        sheet.cell(7, 5, 120)
        for row in range(6, 12):
            sheet.cell(row, 4, 10.0)
            sheet.cell(row, 7, 10.5)
        sheet.cell(12, 6, 1.2)
        sheet.cell(12, 8, 0.05)
        sheet.cell(14, 1, "检测结论：密度检测合格，2h膨胀率检测合格，浸渍剥离检测合格")
        workbook.save(sample_path)
        record = extract_file(sample_path)
        if record["product"] != "脱敏测试产品" or len(record["samples"]) != 1:
            print("self-check failed", file=sys.stderr)
            return 4
    emit("self-check passed", 100)
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
        emit(f"{MODULE_ID} {MODULE_VERSION}", 100)
        return 0
    if args.command == "self-check":
        return self_check()
    return run_job(args.job)


if __name__ == "__main__":
    raise SystemExit(main())

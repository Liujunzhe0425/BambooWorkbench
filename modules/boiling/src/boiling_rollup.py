import hashlib
import json
import re
from pathlib import Path

MODULE_ID = "boiling"
MODULE_VERSION = "1.3.1"
SNAPSHOT_FORMAT = "module-owned-v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")


class RollupContractError(ValueError):
    """Raised when a monthly snapshot or rollup request violates the module contract."""


def canonical_json_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(target)


def read_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RollupContractError(f"无法读取{label}: {exc}") from exc


def validate_year_month(year, month, *, label):
    if not isinstance(year, int) or not 2000 <= year <= 9999:
        raise RollupContractError(f"{label} year 必须为 2000～9999 的整数")
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise RollupContractError(f"{label} month 必须为 1～12 的整数")


def contains_absolute_path(value):
    if isinstance(value, dict):
        return any(contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_absolute_path(item) for item in value)
    if not isinstance(value, str):
        return False
    text = value.strip()
    if text == "/":
        return False
    return bool(WINDOWS_ABSOLUTE_PATTERN.match(text)) or text.startswith(("/", "\\\\"))


def validate_snapshot(snapshot, *, expected_year=None, expected_month=None):
    if not isinstance(snapshot, dict):
        raise RollupContractError("月度快照根节点必须是对象")
    required = {
        "schema_version",
        "module_id",
        "module_version",
        "year",
        "month",
        "snapshot_format",
        "payload",
    }
    unknown = set(snapshot) - required
    missing = required - set(snapshot)
    if missing:
        raise RollupContractError("月度快照缺少字段: " + ", ".join(sorted(missing)))
    if unknown:
        raise RollupContractError("月度快照包含未知字段: " + ", ".join(sorted(unknown)))
    if snapshot["schema_version"] != "1.0":
        raise RollupContractError("月度快照 schema_version 必须为 1.0")
    if snapshot["module_id"] != MODULE_ID:
        raise RollupContractError("月度快照 module_id 必须为 boiling")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(snapshot["module_version"])):
        raise RollupContractError("月度快照 module_version 不合法")
    validate_year_month(snapshot["year"], snapshot["month"], label="月度快照")
    if expected_year is not None and snapshot["year"] != expected_year:
        raise RollupContractError("月度快照年份与累计请求不一致")
    if expected_month is not None and snapshot["month"] != expected_month:
        raise RollupContractError("月度快照月份与清单声明不一致")
    if snapshot["snapshot_format"] != SNAPSHOT_FORMAT:
        raise RollupContractError("月度快照格式不受支持")
    payload = snapshot["payload"]
    if not isinstance(payload, dict):
        raise RollupContractError("月度快照 payload 必须是对象")
    for key in (
        "rule_version",
        "records",
        "excluded_records",
        "anomalies",
        "confirmation_answers",
        "learning_descriptions",
        "ai_review",
        "knowledge_review",
    ):
        if key not in payload:
            raise RollupContractError(f"月度快照 payload 缺少字段: {key}")
    if not isinstance(payload["records"], list):
        raise RollupContractError("月度快照 records 必须是数组")
    if not isinstance(payload["excluded_records"], list):
        raise RollupContractError("月度快照 excluded_records 必须是数组")
    if not isinstance(payload["anomalies"], list):
        raise RollupContractError("月度快照 anomalies 必须是数组")
    if not isinstance(payload["confirmation_answers"], list):
        raise RollupContractError("月度快照 confirmation_answers 必须是数组")
    if not isinstance(payload["learning_descriptions"], list):
        raise RollupContractError("月度快照 learning_descriptions 必须是数组")
    if contains_absolute_path(payload):
        raise RollupContractError("月度快照 payload 不得包含绝对路径")
    return snapshot


def build_snapshot(*, module_version, year, month, payload):
    snapshot = {
        "schema_version": "1.0",
        "module_id": MODULE_ID,
        "module_version": module_version,
        "year": year,
        "month": month,
        "snapshot_format": SNAPSHOT_FORMAT,
        "payload": payload,
    }
    return validate_snapshot(snapshot)


def ensure_within(path, root, *, label):
    resolved = Path(path).resolve()
    resolved_root = Path(root).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise RollupContractError(f"{label}超出授权目录") from exc
    return resolved


def validate_snapshot_ref(item, *, label):
    if not isinstance(item, dict):
        raise RollupContractError(f"{label}必须是对象")
    required = {
        "snapshot_id",
        "job_id",
        "module_id",
        "year",
        "month",
        "path",
        "size",
        "sha256",
    }
    if set(item) != required:
        raise RollupContractError(f"{label}字段不符合中央快照引用合同")
    for field in ("snapshot_id", "job_id"):
        if not isinstance(item[field], str) or not re.fullmatch(
            r"[A-Za-z0-9-]{6,64}", item[field]
        ):
            raise RollupContractError(f"{label} {field} 格式不合法")
    if item["module_id"] != MODULE_ID:
        raise RollupContractError(f"{label} module_id 必须为 boiling")
    if not isinstance(item["year"], int) or not 2000 <= item["year"] <= 9999:
        raise RollupContractError(f"{label} year 必须为 2000～9999")
    if not isinstance(item["month"], int) or not 1 <= item["month"] <= 12:
        raise RollupContractError(f"{label} month 必须为 1～12")
    if not isinstance(item["path"], str) or not item["path"]:
        raise RollupContractError(f"{label} path 必须是非空字符串")
    if not isinstance(item["size"], int) or item["size"] < 0:
        raise RollupContractError(f"{label} size 必须是非负整数")
    if not isinstance(item["sha256"], str) or not SHA256_PATTERN.fullmatch(item["sha256"]):
        raise RollupContractError(f"{label} sha256 必须是 64 位小写十六进制")


def validate_rollup_request(request):
    if not isinstance(request, dict):
        raise RollupContractError("累计请求根节点必须是对象")
    required = {
        "schema_version",
        "transaction_id",
        "module_id",
        "module_version",
        "year",
        "target_month",
        "snapshot_root",
        "output_dir",
        "snapshots",
    }
    optional = {"configuration_identity", "offline_required"}
    missing = required - set(request)
    unknown = set(request) - required - optional
    if missing:
        raise RollupContractError("累计请求缺少字段: " + ", ".join(sorted(missing)))
    if unknown:
        raise RollupContractError("累计请求包含未知字段: " + ", ".join(sorted(unknown)))
    if request["schema_version"] != "1.0":
        raise RollupContractError("累计请求 schema_version 必须为 1.0")
    if request["module_id"] != MODULE_ID:
        raise RollupContractError("累计请求 module_id 必须为 boiling")
    if request["module_version"] != MODULE_VERSION:
        raise RollupContractError("累计请求 module_version 与当前模块版本不一致")
    if not re.fullmatch(r"[A-Za-z0-9-]{6,64}", str(request["transaction_id"])):
        raise RollupContractError("累计请求 transaction_id 格式不合法")
    validate_year_month(request["year"], request["target_month"], label="累计请求")
    if not isinstance(request["snapshot_root"], str) or not request["snapshot_root"]:
        raise RollupContractError("累计请求 snapshot_root 必须是非空路径")
    if not isinstance(request["output_dir"], str) or not request["output_dir"]:
        raise RollupContractError("累计请求 output_dir 必须是非空路径")
    if request.get("offline_required", True) is not True:
        raise RollupContractError("累计请求 offline_required 必须为 true")
    configuration_identity = request.get("configuration_identity")
    if configuration_identity is not None:
        if not isinstance(configuration_identity, dict) or set(
            configuration_identity
        ) != {"version", "sha256"}:
            raise RollupContractError("累计请求 configuration_identity 格式不合法")
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
            str(configuration_identity["version"]),
        ):
            raise RollupContractError("累计请求 configuration_identity.version 格式不合法")
        if not isinstance(
            configuration_identity["sha256"], str
        ) or not SHA256_PATTERN.fullmatch(configuration_identity["sha256"]):
            raise RollupContractError("累计请求 configuration_identity.sha256 格式不合法")
    if not isinstance(request["snapshots"], list) or not request["snapshots"]:
        raise RollupContractError("累计请求 snapshots 必须是非空数组")
    if len(request["snapshots"]) > 12:
        raise RollupContractError("累计请求 snapshots 最多包含 12 个月")
    previous = 0
    for index, item in enumerate(request["snapshots"]):
        validate_snapshot_ref(item, label=f"snapshots[{index}]")
        if item["year"] != request["year"]:
            raise RollupContractError("累计请求包含跨年快照")
        month = item["month"]
        if month <= previous:
            reason = "重复月份" if month == previous else "月份乱序"
            raise RollupContractError(f"累计请求 snapshots 存在{reason}")
        if month > request["target_month"]:
            raise RollupContractError("累计请求包含晚于目标月份的快照")
        previous = month
    return request


def load_verified_snapshot(reference, *, snapshot_root, year):
    path = ensure_within(reference["path"], snapshot_root, label="快照路径")
    if not path.is_file():
        raise RollupContractError(f"快照文件不存在: {path.name}")
    if path.stat().st_size != reference["size"]:
        raise RollupContractError(f"快照大小不一致: {path.name}")
    actual_hash = sha256_file(path)
    if actual_hash != reference["sha256"]:
        raise RollupContractError(f"快照哈希不一致: {path.name}")
    snapshot = read_json(path, f"月度快照 {path.name}")
    validate_snapshot(
        snapshot,
        expected_year=year,
        expected_month=reference["month"],
    )
    return {
        "snapshot_id": reference["snapshot_id"],
        "job_id": reference["job_id"],
        "month": reference["month"],
        "path": path,
        "sha256": actual_hash,
        "snapshot": snapshot,
    }


def resolve_rollup_snapshots(request):
    validate_rollup_request(request)
    snapshot_root = Path(request["snapshot_root"]).resolve()
    if not snapshot_root.is_dir():
        raise RollupContractError("累计请求 snapshot_root 不存在或不是目录")
    return [
        load_verified_snapshot(
            item,
            snapshot_root=snapshot_root,
            year=request["year"],
        )
        for item in request["snapshots"]
    ]


def response_template(
    request,
    *,
    status,
    outputs=None,
    used=None,
    record_count=0,
    error=None,
):
    used = used or []
    return {
        "schema_version": "1.0",
        "transaction_id": request.get("transaction_id", "invalid"),
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "status": status,
        "year": request.get("year", 2000),
        "target_month": request.get("target_month", 1),
        "used_months": [item["month"] for item in used],
        "snapshot_hashes": [
            {
                "snapshot_id": item["snapshot_id"],
                "month": item["month"],
                "sha256": item["sha256"],
            }
            for item in used
        ],
        "outputs": outputs or [],
        "record_count": record_count,
        "error": error,
        "network_call_count": 0,
    }

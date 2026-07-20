from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_RULES: dict[str, Any] = {
    "rule_version": "2026.07",
    "brand_order": ["桃花江", "竹语堂", "海外"],
    "brand_priority": ["海外", "竹语堂", "桃花江"],
    "fallback_brand": "未知",
    "brand_keywords": {
        "海外": ["海外", "香港", "澳门", "澳門", "台湾", "Taiwan", "Hong Kong"],
        "竹语堂": ["竹语堂", "竹雨堂", "竹語堂"],
        "桃花江": ["桃花江", "常规浅炭", "浅炭", "浅碳", "深炭", "光量子"],
    },
    "issue_order": ["性能", "外观", "加工", "其他"],
    "issue_keywords": {
        "性能": [
            "开裂",
            "裂纹",
            "断裂",
            "分层",
            "剥离",
            "发霉",
            "霉变",
            "腐烂",
            "膨胀",
            "胀裂",
            "收缩",
            "变形",
            "松动",
            "破裂",
            "功能性",
            "安全隐患",
        ],
        "外观": [
            "颜色",
            "色差",
            "法国色",
            "柚木色",
            "表面",
            "划伤",
            "脏污",
            "污渍",
            "掉漆",
            "漆面",
            "美观",
            "发白",
            "变色",
            "崩边",
        ],
        "加工": [
            "尺寸",
            "规格",
            "宽度",
            "厚度",
            "长度",
            "斜边",
            "图纸",
            "拆解",
            "沟通不到位",
            "开片",
            "指令",
            "加工",
            "返工",
            "漏",
            "补数",
            "不能安装",
            "尺寸不符",
            "切",
            "指令错误",
            "设计遗漏",
            "图纸拆解",
            "沟通时存在遗漏",
        ],
        "其他": [],
    },
    "field_aliases": {
        "customer": ["客户/项目", "客户", "项目"],
        "location": ["地点", "地址"],
        "salesperson": ["销售/代表", "销售", "代表"],
        "complaint_date": ["提出质量问题日期", "报修日期", "投诉日期", "日期"],
        "product": ["产品名称", "产品"],
        "spec": ["规格/mm", "规格"],
        "order_no": ["订单编号", "订单号", "订单"],
        "delivery_date": ["交货日期", "交货"],
        "feedback": ["反馈内容", "客户反馈", "问题反馈"],
        "application": ["方案申请明细", "售后申请方案", "申请方案"],
        "investigation": ["售后负责人调查情况", "调查情况", "原因调查"],
        "solution": ["售后解决方案", "售后/解决方案", "售后方案", "解决方案"],
        "responsibility": ["责任落实与处理", "责任落实"],
    },
    "cost_keywords": [
        "费用",
        "损失",
        "工费",
        "运费",
        "材料",
        "赔偿",
        "补偿",
        "承担",
        "总计",
        "合计",
        "共计",
    ],
    "cost_total_keywords": ["总计", "合计", "共计", "总费用", "费用计算"],
    "excluded_cost_keywords": ["转嫁给", "供应商", "合作方", "不纳入统计", "不在统计"],
    "closed_keywords": [
        "结案",
        "关闭",
        "完成",
        "已前往",
        "最终确认",
        "达成一致",
        "重新生产",
        "补偿",
        "更换",
        "返工",
        "处理",
        "修复",
    ],
}


def deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_rules(module_root: Path, config_file: str | None = None) -> dict[str, Any]:
    rules = deepcopy(DEFAULT_RULES)
    default_rules = module_root / "rules" / "default_rules.yaml"
    for candidate in [default_rules, Path(config_file) if config_file else None]:
        if candidate and candidate.exists():
            loaded = _load_yaml(candidate)
            if loaded:
                rules = deep_merge(rules, loaded)
    return rules


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return data

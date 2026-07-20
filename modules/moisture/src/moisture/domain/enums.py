"""Moisture-domain states retained from the verified legacy implementation."""

from enum import StrEnum


class ScreenStatus(StrEnum):
    NORMAL = "normal"
    HIGH = "high"
    LOW = "low"
    DATA_QUALITY = "data_quality"


class ReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    REVIEW_HIGH = "review_high"
    REVIEW_LOW = "review_low"
    REVIEW_NORMAL = "review_normal"
    NOT_COMPLETED = "not_completed"


class DisplayColor(StrEnum):
    NONE = "none"
    ORANGE = "orange"
    GREEN = "green"
    RED = "red"
    BLUE = "blue"


class ConfirmationState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING_HUMAN_REVIEW = "pending_human_review"
    CONFIRMED_NORMAL = "confirmed_normal"
    CONFIRMED_ANOMALY = "confirmed_anomaly"

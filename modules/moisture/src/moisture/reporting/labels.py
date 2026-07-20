"""Chinese presentation labels for human-facing report artifacts only."""

from moisture.domain.enums import (
    ConfirmationState,
    DisplayColor,
    ReviewStatus,
    ScreenStatus,
)

SCREEN_LABELS = {
    ScreenStatus.NORMAL: "正常",
    ScreenStatus.HIGH: "偏高疑似",
    ScreenStatus.LOW: "偏低疑似",
    ScreenStatus.DATA_QUALITY: "数据质量疑点",
}
REVIEW_LABELS = {
    ReviewStatus.NOT_REQUIRED: "无需辅助复判",
    ReviewStatus.REVIEW_HIGH: "辅助证据支持偏高疑似",
    ReviewStatus.REVIEW_LOW: "辅助证据支持偏低疑似",
    ReviewStatus.REVIEW_NORMAL: "辅助复判未支持异常",
    ReviewStatus.NOT_COMPLETED: "辅助复判未完成",
}
COLOR_LABELS = {
    DisplayColor.NONE: "无颜色",
    DisplayColor.ORANGE: "橙色",
    DisplayColor.GREEN: "绿色",
    DisplayColor.RED: "红色",
    DisplayColor.BLUE: "蓝色",
}
CONFIRMATION_LABELS = {
    ConfirmationState.NOT_REQUIRED: "无需人工确认",
    ConfirmationState.PENDING_HUMAN_REVIEW: "待人工复核",
    ConfirmationState.CONFIRMED_NORMAL: "已确认正常",
    ConfirmationState.CONFIRMED_ANOMALY: "已确认疑点",
}


def screen_label(value: ScreenStatus) -> str:
    return SCREEN_LABELS[value]


def review_label(value: ReviewStatus) -> str:
    return REVIEW_LABELS[value]


def color_label(value: DisplayColor) -> str:
    return COLOR_LABELS[value]


def confirmation_label(value: ConfirmationState) -> str:
    return CONFIRMATION_LABELS[value]

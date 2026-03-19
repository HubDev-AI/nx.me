from enum import StrEnum


class LimitType(StrEnum):
    TOTAL = "total"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    PERIOD = "period"
    CREDITS = "credits"
    UNLIMITED = "unlimited"

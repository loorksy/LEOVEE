from enum import StrEnum


class WorkspaceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class Timeframe(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


class RecommendationDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"


class RecommendationStatus(StrEnum):
    DETECTED = "DETECTED"
    ANALYZING = "ANALYZING"
    FORMING = "FORMING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    READY = "READY"
    ACTIVE = "ACTIVE"
    STRENGTHENING = "STRENGTHENING"
    WEAKENING = "WEAKENING"
    TARGET_REACHED = "TARGET_REACHED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class ThesisStatus(StrEnum):
    ACTIVE = "ACTIVE"
    STRENGTHENING = "STRENGTHENING"
    WEAKENING = "WEAKENING"
    INVALIDATED = "INVALIDATED"
    TARGET_REACHED = "TARGET_REACHED"
    EXPIRED = "EXPIRED"


class TradeStatus(StrEnum):
    IDEA = "IDEA"
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    INVALIDATED = "INVALIDATED"


class PlanCode(StrEnum):
    FREE = "FREE"
    PRO = "PRO"
    PRO_PLUS = "PRO_PLUS"
    ENTERPRISE = "ENTERPRISE"

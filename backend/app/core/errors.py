"""Application-wide exceptions."""


class LeoveeError(Exception):
    """Base error."""


class DataUnavailableError(LeoveeError):
    """Live market or required data cannot be loaded."""


class ProviderConfigurationError(LeoveeError):
    """External provider is not configured."""


class InsufficientEvidenceError(LeoveeError):
    """Analysis cannot proceed with available evidence."""

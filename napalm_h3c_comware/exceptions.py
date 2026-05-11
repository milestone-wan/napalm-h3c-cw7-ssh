"""Project-specific exceptions for the H3C Comware NAPALM driver."""


class ComwareDriverError(Exception):
    """Base exception for driver-specific errors."""


class UnsupportedProfileError(ComwareDriverError):
    """Raised when a discovered device profile is outside the supported scope."""


class UnsupportedCommandError(ComwareDriverError):
    """Raised when no command specification supports the requested profile."""


class ComwareParserError(ComwareDriverError):
    """Raised when raw command output cannot be parsed safely."""


# Backward-compatible alias; will be removed in a future version.
ParserError = ComwareParserError


class ConfigManagementError(ComwareDriverError):
    """Raised for configuration workflow failures."""

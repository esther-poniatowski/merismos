"""
Exceptions raised by Merismos.

Every exception derives from `MerismosError`, so that a consumer catches the failures of the
library with one clause and lets its own errors pass.

Classes
-------
MerismosError
    Base of every exception raised by Merismos.
SyntaxFileError
    A syntax file is missing, malformed, or declares an unknown key or value.
UnknownSourceTypeError
    No segmenter is registered for the requested source type.
DecodingError
    A prose string could not be decoded with an exact map to its source.
SourceSyntaxError
    A structured source does not parse in its format.
ConformanceFileError
    A conformance file is malformed or names another contract.
"""


class MerismosError(Exception):
    """Base of every exception raised by Merismos."""


class SyntaxFileError(MerismosError):
    """A syntax file is missing, malformed, or declares an unknown key or value."""


class UnknownSourceTypeError(MerismosError, KeyError):
    """No segmenter is registered for the requested source type."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else "unknown source type"


class DecodingError(MerismosError):
    """A prose string could not be decoded with an exact map to its source."""


class SourceSyntaxError(MerismosError):
    """A structured source does not parse in its format, so that no region can be located."""


class ConformanceFileError(MerismosError):
    """A conformance file is malformed or names another contract than the one checked."""

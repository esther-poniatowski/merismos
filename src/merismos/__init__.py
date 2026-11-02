"""
Segmentation of documents into typed regions with exact offsets, for the tools that check texts.

Merismos returns the regions of a source and applies no policy to them: each consumer selects
the kinds that it masks, scans or reads. The grammar of each source type comes from a syntax file,
so that a dialect changes without code.

Variables
---------
__version__ : str, default "0.0.0+unknown"
    Version of the package. If the package metadata is unavailable (e.g. in editable or source-only
    environments), a fallback value is provided (PEP 440 compliant).
__all__ : list
    Public objects exposed by this package.

Functions
---------
segment(source, source_type, syntax) -> Segmentation
    Segment one source with the default registry.
info() -> str
    Format diagnostic information about the package and platform.

Examples
--------
>>> segmentation = segment("Let $x_i$ vary.", "markdown")
>>> [(region.kind, segmentation.text(region.content)) for region in segmentation]
[('inline-math', 'x_i')]
"""

from functools import lru_cache
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import platform

from .errors import DecodingError, MerismosError, SyntaxFileError, UnknownSourceTypeError
from .model import AttributeValue, DecodedString, Piece, Region, Segmentation, Span
from .registry import Registry, Segmenter, SourceType, default_registry
from .text import ContentView, content_view, mask

try:
    if __package__ is None:  # erroneous script execution
        raise PackageNotFoundError
    __version__ = version(__package__)
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "AttributeValue",
    "ContentView",
    "DecodedString",
    "DecodingError",
    "MerismosError",
    "Piece",
    "Region",
    "Registry",
    "Segmentation",
    "Segmenter",
    "SourceType",
    "Span",
    "SyntaxFileError",
    "UnknownSourceTypeError",
    "content_view",
    "default_registry",
    "info",
    "mask",
    "segment",
    "__version__",
]


@lru_cache(maxsize=None)
def _segmenter(source_type: str, syntax: Path | None) -> Segmenter:
    """Build the segmenter of a source type once; it is immutable, so every call shares it."""
    return default_registry().segmenter(source_type, syntax)


def segment(source: str, source_type: str, syntax: Path | None = None) -> Segmentation:
    """
    Segment one source with the source types shipped with Merismos.

    Parameters
    ----------
    source : str
        Text to segment.
    source_type : str
        Name of its source type, such as `markdown`.
    syntax : Path | None
        Syntax file to read, or None for the default syntax of the type.

    Returns
    -------
    Segmentation
        Regions of the source.

    Raises
    ------
    UnknownSourceTypeError
        If the source type is not shipped with Merismos.
    SyntaxFileError
        If the syntax file is invalid.
    """
    return _segmenter(source_type, None if syntax is None else syntax.resolve()).segment(source)


def info() -> str:
    """Format diagnostic information on package and platform."""
    platform_name = f"{platform.system()} Python {platform.python_version()}"
    return f"{__package__} {__version__} | Platform: {platform_name}"

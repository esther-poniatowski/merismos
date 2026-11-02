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
inline_regions(source, segments, syntax) -> Segmentation
    Scan the inline constructs of one Markdown paragraph, given the spans of its lines.
info() -> str
    Format diagnostic information about the package and platform.

Examples
--------
>>> segmentation = segment("Let $x_i$ vary.", "markdown")
>>> [(region.kind, segmentation.text(region.content)) for region in segmentation]
[('inline-math', 'x_i')]
"""

from functools import cache
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import platform
from typing import Sequence

from .errors import (
    DecodingError,
    MerismosError,
    SourceSyntaxError,
    SyntaxFileError,
    UnknownSourceTypeError,
)
from .markdown.segmenter import MarkdownSegmenter
from .model import AttributeValue, DecodedString, Piece, Region, Segmentation, Span
from .registry import (
    PackagedSyntax,
    Registry,
    Segmenter,
    SegmenterBuilder,
    SourceType,
    SyntaxReference,
    default_registry,
)
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
    "MarkdownSegmenter",
    "MerismosError",
    "PackagedSyntax",
    "Piece",
    "Region",
    "Registry",
    "Segmentation",
    "Segmenter",
    "SegmenterBuilder",
    "SourceSyntaxError",
    "SourceType",
    "Span",
    "SyntaxFileError",
    "SyntaxReference",
    "UnknownSourceTypeError",
    "content_view",
    "default_registry",
    "info",
    "inline_regions",
    "mask",
    "segment",
    "__version__",
]


@cache
def _default_segmenter(source_type: str) -> Segmenter:
    """
    Build the segmenter of a source type under its packaged syntax, once.

    A packaged syntax cannot change while the process runs, so its segmenter is shared. A syntax
    file of the consumer is read again at each call, so that an edited file takes effect.
    """
    return default_registry().segmenter(source_type)


def _segmenter(source_type: str, syntax: Path | None) -> Segmenter:
    """Return the segmenter of a source type, under its packaged syntax or a consumer file."""
    if syntax is None:
        return _default_segmenter(source_type)
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
    SourceSyntaxError
        If a structured source does not parse in its format.
    DecodingError
        If a prose string of a structured source decodes to another value than its parser reads.
    """
    return _segmenter(source_type, syntax).segment(source)


def inline_regions(
    source: str, segments: Sequence[Span], syntax: Path | None = None
) -> Segmentation:
    """
    Scan the inline constructs of one Markdown paragraph, given the spans of its lines.

    A consumer keeping a block parser of its own passes the text of each line of a paragraph,
    without its container prefixes, and receives the inline regions with source offsets.

    Raises
    ------
    SyntaxFileError
        If the syntax file is invalid, or describes no Markdown dialect.
    """
    segmenter = _segmenter("markdown", syntax)
    if not isinstance(segmenter, MarkdownSegmenter):
        raise SyntaxFileError("the markdown source type is not served by the Markdown segmenter")
    return segmenter.inline_regions(source, segments)


def info() -> str:
    """Format diagnostic information on package and platform."""
    platform_name = f"{platform.system()} Python {platform.python_version()}"
    return f"{__package__} {__version__} | Platform: {platform_name}"

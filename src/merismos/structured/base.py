"""
Base of the segmenters of structured sources, each configured by one typed syntax.

Classes
-------
StructuredSegmenter
    Segmenter holding its syntax and the name of its source type.
"""

from typing import Generic, Iterable, TypeVar

from ..model import Region, Segmentation

SyntaxT = TypeVar("SyntaxT")
"""Type of the syntax read by a segmenter."""


class StructuredSegmenter(Generic[SyntaxT]):
    """
    Segmenter holding its syntax and the name of its source type.

    The regions of a structured source never nest, so the order of the contract reduces to the
    order of their starts.

    Parameters
    ----------
    syntax : SyntaxT
        Syntax of the source type.
    source_type : str
        Name of the source type reported in each segmentation.
    """

    def __init__(self, syntax: SyntaxT, source_type: str) -> None:
        self._syntax = syntax
        self._source_type = source_type

    kinds: frozenset[str] = frozenset()
    """Kinds of the regions that the segmenter returns, declared by each subclass."""

    def _segmentation(self, source: str, regions: Iterable[Region]) -> Segmentation:
        """Build the segmentation of a source, its regions sorted by start."""
        ordered = sorted(regions, key=lambda region: region.range.start)
        return Segmentation(source, self._source_type, tuple(ordered), self.kinds)

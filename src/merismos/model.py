"""
Value types of a segmentation: spans, regions, decoded strings, and the segmentation itself.

Every offset counts Unicode code points from the start of the source, beginning at 0, and every
span is half-open. The types are immutable, so a segmentation can be shared between consumers.

Classes
-------
Span
    Half-open range of code points in a source.
Piece
    Run of a decoded string copied verbatim from its source.
DecodedString
    Prose string decoded from a structured source, with its map to the source.
Region
    Typed part of a source.
Segmentation
    Source with its regions, in the order fixed by the contract.

Examples
--------
>>> region = Region("inline-math", Span(4, 9), content=Span(5, 8))
>>> Segmentation("Let $x_i$ vary.", "markdown", (region,)).text(region.content)
'x_i'
"""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Iterator, Mapping

AttributeValue = str | int | bool | None
"""Type of the value of a region attribute."""


@dataclass(frozen=True, order=True)
class Span:
    """
    Half-open range of code points in a source.

    Attributes
    ----------
    start : int
        Offset of the first code point of the span.
    end : int
        Offset after the last code point of the span, equal to `start` for an empty span.

    Raises
    ------
    ValueError
        If an offset is negative or `end` precedes `start`.

    Examples
    --------
    >>> Span(2, 5).contains(Span(3, 5))
    True
    >>> len(Span(2, 5))
    3
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid span [{self.start}, {self.end})")

    def __len__(self) -> int:
        return self.end - self.start

    def contains(self, other: "Span") -> bool:
        """Whether `other` lies inside this span, its bounds included."""
        return self.start <= other.start and other.end <= self.end

    def overlaps(self, other: "Span") -> bool:
        """Whether the two spans share at least one code point."""
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Piece:
    """
    Run of a decoded string copied verbatim from its source.

    Attributes
    ----------
    value_start : int
        Offset of the run in the decoded string.
    source_start : int
        Offset of the run in the source.
    length : int
        Number of code points of the run.
    """

    value_start: int
    source_start: int
    length: int


@dataclass(frozen=True)
class DecodedString:
    """
    Prose string decoded from a structured source, with its map to the source.

    A code point of `value` outside every piece was produced by decoding, such as a folded line
    break or an escape. It originates from the source text between the two pieces around it.

    Attributes
    ----------
    value : str
        Decoded string.
    pieces : tuple[Piece, ...]
        Runs of `value` copied verbatim from the source, in increasing order of both offsets.

    Examples
    --------
    >>> decoded = DecodedString("a b", (Piece(0, 10, 1), Piece(2, 14, 1)))
    >>> decoded.to_source(2), decoded.to_source(1)
    (14, 11)
    """

    value: str
    pieces: tuple[Piece, ...] = ()

    def to_source(self, offset: int) -> int:
        """
        Map an offset of the value to an offset of the source.

        An offset inside a piece maps exactly. An offset produced by decoding maps to the end of
        the preceding piece, the first source position from which the code point originates, or to
        the start of the first piece when no piece precedes it.

        Raises
        ------
        ValueError
            If the offset lies outside the value, or the string has no piece.
        """
        if not 0 <= offset <= len(self.value):
            raise ValueError(f"offset {offset} outside a value of length {len(self.value)}")
        if not self.pieces:
            raise ValueError("a decoded string without pieces maps no offset")
        previous: Piece | None = None
        for piece in self.pieces:
            if offset < piece.value_start:
                break
            if offset < piece.value_start + piece.length:
                return piece.source_start + offset - piece.value_start
            previous = piece
        if previous is None:
            return self.pieces[0].source_start
        return previous.source_start + previous.length


@dataclass(frozen=True)
class Region:
    """
    Typed part of a source.

    Attributes
    ----------
    kind : str
        Span kind of the region, one of the kinds of its source type.
    range : Span
        Whole construct, delimiters included.
    content : Span | None
        Part between the delimiters, or None for a kind whose parts are child regions or whose
        string is decoded.
    gaps : tuple[Span, ...]
        Container prefixes inside the content, in source order.
    attributes : Mapping[str, AttributeValue]
        Attributes of the kind.
    string : DecodedString | None
        Decoded prose string of a region of a structured source.
    """

    kind: str
    range: Span
    content: Span | None = None
    gaps: tuple[Span, ...] = ()
    attributes: Mapping[str, AttributeValue] = field(default_factory=dict)
    string: DecodedString | None = None

    def __post_init__(self) -> None:
        if self.content is not None and not self.range.contains(self.content):
            raise ValueError(
                f"content {self.content} of {self.kind} outside its range {self.range}"
            )
        for gap in self.gaps:
            if self.content is None or not self.content.contains(gap):
                raise ValueError(f"gap {gap} of {self.kind} outside its content")
        # A frozen dataclass keeps a reference to the caller's mapping, so a read-only copy keeps
        # the region immutable after construction.
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))

    def __hash__(self) -> int:
        return hash((self.kind, self.range, self.content, self.gaps, self.string))


@dataclass(frozen=True)
class Segmentation:
    """
    Source with its regions, in the order fixed by the contract.

    The regions are sorted by start, then by end in decreasing order, and an enclosing region
    precedes a region sharing its range.

    Attributes
    ----------
    source : str
        Segmented text.
    source_type : str
        Name of the source type under which the text was segmented.
    regions : tuple[Region, ...]
        Regions of the source.
    """

    source: str
    source_type: str
    regions: tuple[Region, ...]

    def __iter__(self) -> Iterator[Region]:
        return iter(self.regions)

    def __len__(self) -> int:
        return len(self.regions)

    def select(self, kinds: Iterable[str]) -> tuple[Region, ...]:
        """Return the regions of the given kinds, in the order of the segmentation."""
        wanted = frozenset(kinds)
        return tuple(region for region in self.regions if region.kind in wanted)

    def text(self, span: Span) -> str:
        """Return the text of the source covered by a span."""
        return self.source[span.start : span.end]

"""
Operations on the text of regions, free of any policy on which kinds to apply them to.

A consumer decides which kinds it masks or reads; these functions apply that decision with exact
offsets, so that no consumer reimplements the handling of gaps and line breaks.

Classes
-------
ContentView
    Content of a region without its gaps, with the source offset of each position.

Functions
---------
mask(source, regions, fill) -> str
    Replace the ranges of regions by a fill character, keeping every line break.
content_view(source, region) -> ContentView
    Read the content of a region without its gaps.
"""

from dataclasses import dataclass
from typing import Iterable

from .model import Region

LINE_BREAK_CHARACTERS = frozenset("\r\n")
"""Characters kept by masking, so that line numbers and offsets survive it."""


def mask(source: str, regions: Iterable[Region], fill: str = " ") -> str:
    """
    Replace the ranges of regions by a fill character, keeping every line break.

    The masked text keeps the length of the source, so every offset stays valid.

    Parameters
    ----------
    source : str
        Text that the regions segment.
    regions : Iterable[Region]
        Regions to mask, typically those of the kinds that a consumer ignores.
    fill : str
        Single character replacing each masked code point.

    Raises
    ------
    ValueError
        If `fill` is not a single character, or is a line break.

    Examples
    --------
    >>> from merismos.model import Span
    >>> mask("a $b$\\nc", [Region("inline-math", Span(2, 5))])
    'a    \\nc'
    """
    if len(fill) != 1 or fill in LINE_BREAK_CHARACTERS:
        raise ValueError("the fill is one character other than a line break")
    characters = list(source)
    for region in regions:
        for index in range(region.range.start, region.range.end):
            if characters[index] not in LINE_BREAK_CHARACTERS:
                characters[index] = fill
    return "".join(characters)


@dataclass(frozen=True)
class ContentView:
    """
    Content of a region without its gaps, with the source offset of each position.

    Attributes
    ----------
    text : str
        Content of the region, its gaps removed.
    offsets : tuple[int, ...]
        Source offset of each position of `text`, followed by the end of the content.
    """

    text: str
    offsets: tuple[int, ...]

    def to_source(self, position: int) -> int:
        """Map a position of the view, its end included, to an offset of the source."""
        return self.offsets[position]


def content_view(source: str, region: Region) -> ContentView:
    """
    Read the content of a region without its gaps.

    Raises
    ------
    ValueError
        If the region has no content.

    Examples
    --------
    >>> from merismos.model import Span
    >>> region = Region("display-math", Span(0, 8), Span(2, 6), gaps=(Span(3, 4),))
    >>> view = content_view("$$a> b$$", region)
    >>> view.text, view.to_source(1)
    ('a b', 4)
    """
    if region.content is None:
        raise ValueError(f"a region of kind {region.kind} has no content")
    parts: list[str] = []
    offsets: list[int] = []
    position = region.content.start
    for gap in (*region.gaps, None):
        stop = region.content.end if gap is None else gap.start
        parts.append(source[position:stop])
        offsets.extend(range(position, stop))
        if gap is not None:
            position = gap.end
    offsets.append(region.content.end)
    return ContentView("".join(parts), tuple(offsets))

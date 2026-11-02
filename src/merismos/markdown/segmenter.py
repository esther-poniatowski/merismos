"""
Segmenter of a Markdown source: the block scan, then the inline scan of each run of text.

The text of a run joins its lines with a line break, and every offset of the run maps back to
the source through the start of its line. Each region then receives as gaps the container
prefixes that its content crosses, among the prefixes of its own containers.

A consumer keeping a block parser of its own, such as Hermeneia, passes the spans of the lines
of one paragraph to `MarkdownSegmenter.inline_regions`, and receives the inline regions of that
paragraph with source offsets. The text between two consecutive spans, after the line ending,
then stands for the container prefixes.

Classes
-------
MarkdownSegmenter
    Segmenter of Markdown sources under one syntax.
"""

from bisect import bisect_left
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..lines import ending_width
from ..model import AttributeValue, Region, Segmentation, Span
from .blocks import BlockScanner, InlineRun, Prefix
from .inline import RUN_LINE_BREAK, InlineNode, InlineScanner
from .kinds import MARKDOWN_KINDS
from .syntax import MarkdownSyntax

SPANS_OWNER = 0
"""Owner of the prefixes between the spans passed to `inline_regions`."""


@dataclass(frozen=True)
class _Found:
    """Region found by either scanner, before its gaps are computed."""

    kind: str
    range: Span
    content: Span | None
    owners: tuple[int, ...]
    attributes: dict[str, AttributeValue]


class _RunText:
    """Text of a run, with the source offset of each of its positions."""

    def __init__(self, source: str, segments: Sequence[Span]) -> None:
        parts: list[str] = []
        offsets: list[int] = []
        for index, segment in enumerate(segments):
            if index:
                parts.append(RUN_LINE_BREAK)
                offsets.append(segments[index - 1].end)
            parts.append(source[segment.start : segment.end])
            offsets.extend(range(segment.start, segment.end))
        offsets.append(segments[-1].end if segments else 0)
        self.text = "".join(parts)
        self._offsets = offsets

    def span(self, span: Span) -> Span:
        """Map a span of the run to the source."""
        return Span(self._offsets[span.start], self._offsets[span.end])


class _Prefixes:
    """Container prefixes sorted by start, searched by bisection."""

    def __init__(self, prefixes: Sequence[Prefix]) -> None:
        self._prefixes = sorted(prefixes, key=lambda prefix: prefix.span.start)
        self._starts = [prefix.span.start for prefix in self._prefixes]

    def gaps(self, content: Span, owners: frozenset[int]) -> tuple[Span, ...]:
        """The prefixes of the given owners lying inside a content, in source order."""
        gaps: list[Span] = []
        index = bisect_left(self._starts, content.start)
        while index < len(self._prefixes) and self._starts[index] < content.end:
            prefix = self._prefixes[index]
            if prefix.owner in owners and content.contains(prefix.span):
                gaps.append(prefix.span)
            index += 1
        return tuple(gaps)


class MarkdownSegmenter:
    """
    Segmenter of Markdown sources under one syntax.

    Parameters
    ----------
    syntax : MarkdownSyntax
        Syntax of the dialect.
    source_type : str
        Name of the source type reported in each segmentation.
    """

    kinds = frozenset(MARKDOWN_KINDS)
    """Kinds of the regions that the segmenter returns."""

    def __init__(self, syntax: MarkdownSyntax, source_type: str) -> None:
        self._blocks = BlockScanner(syntax)
        self._inline = InlineScanner(syntax)
        self._source_type = source_type

    def segment(self, source: str) -> Segmentation:
        """
        Segment a Markdown source.

        Returns
        -------
        Segmentation
            Regions of the source, in the order fixed by the contract.
        """
        scan = self._blocks.scan(source)
        found = [
            _Found(
                region.kind,
                Span(region.start, region.end),
                (
                    Span(region.content_start, region.content_end)
                    if region.content_start is not None and region.content_end is not None
                    else None
                ),
                region.owners,
                region.attributes,
            )
            for region in scan.regions
        ]
        for run in scan.runs:
            found.extend(self._run_regions(source, run))
        return self._segmentation(source, found, _Prefixes(scan.prefixes))

    def inline_regions(self, source: str, segments: Sequence[Span]) -> Segmentation:
        """
        Scan the inline constructs of one paragraph, given the spans of its lines.

        Parameters
        ----------
        source : str
            Source holding the paragraph.
        segments : Sequence[Span]
            Text of each line of the paragraph, without its container prefixes, in order.

        Returns
        -------
        Segmentation
            Inline regions of the paragraph, the text between two lines after the line ending of
            the first standing for container prefixes.
        """
        prefixes = []
        for previous, following in zip(segments, segments[1:]):
            start = previous.end + ending_width(source, previous.end)
            if start < following.start:
                prefixes.append(Prefix(Span(start, following.start), SPANS_OWNER))
        found = self._run_regions(source, InlineRun(tuple(segments), (SPANS_OWNER,)))
        return self._segmentation(source, found, _Prefixes(prefixes))

    def _run_regions(self, source: str, run: InlineRun) -> list[_Found]:
        """Scan one run, mapping its regions to the source, each parent before its children."""
        text = _RunText(source, run.segments)
        return [
            _Found(
                node.kind,
                text.span(node.range),
                text.span(node.content) if node.content is not None else None,
                run.owners,
                node.attributes,
            )
            for node in _flatten(self._inline.scan(text.text))
        ]

    def _segmentation(self, source: str, found: list[_Found], prefixes: _Prefixes) -> Segmentation:
        """Order the found regions as the contract fixes, and give each its gaps."""
        # Two regions share a range only when one nests in the other, and the list holds each
        # parent before the regions nested in it, so its index breaks every tie.
        ranked = sorted(
            enumerate(found), key=lambda pair: (pair[1].range.start, -pair[1].range.end, pair[0])
        )
        regions = tuple(
            Region(
                item.kind,
                item.range,
                item.content,
                (
                    prefixes.gaps(item.content, frozenset(item.owners))
                    if item.content is not None
                    else ()
                ),
                item.attributes,
            )
            for _, item in ranked
        )
        return Segmentation(source, self._source_type, regions, self.kinds)


def _flatten(nodes: Iterable[InlineNode]) -> list[InlineNode]:
    """List the nodes in preorder, each parent before the nodes nested in it."""
    flat: list[InlineNode] = []
    for node in nodes:
        flat.append(node)
        flat.extend(_flatten(node.children))
    return flat

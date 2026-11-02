"""
Segmenter of a Markdown source: the block scan, then the inline scan of each run of text.

The text of a run joins its lines with a line break, and every offset of the run maps back to
the source through the start of its line. Each region then receives as gaps the container
prefixes that its content crosses, among the prefixes of its own containers.

Classes
-------
MarkdownSegmenter
    Segmenter of Markdown sources under one syntax.
"""

from dataclasses import dataclass
from typing import Iterable

from ..model import AttributeValue, Region, Segmentation, Span
from .blocks import BlockScanner, InlineRun, Prefix
from .inline import InlineNode, InlineScanner
from .syntax import MarkdownSyntax

RUN_LINE_BREAK = "\n"
"""Character joining the lines of a run, whatever the line ending of the source."""


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

    def __init__(self, source: str, run: InlineRun) -> None:
        parts: list[str] = []
        offsets: list[int] = []
        for index, segment in enumerate(run.segments):
            if index:
                parts.append(RUN_LINE_BREAK)
                offsets.append(run.segments[index - 1].end)
            parts.append(source[segment.start : segment.end])
            offsets.extend(range(segment.start, segment.end))
        offsets.append(run.segments[-1].end if run.segments else 0)
        self.text = "".join(parts)
        self._offsets = offsets

    def span(self, span: Span) -> Span:
        """Map a span of the run to the source."""
        return Span(self._offsets[span.start], self._offsets[span.end])


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
            text = _RunText(source, run)
            for node in _flatten(self._inline.scan(text.text)):
                found.append(
                    _Found(
                        node.kind,
                        text.span(node.range),
                        text.span(node.content) if node.content is not None else None,
                        run.owners,
                        node.attributes,
                    )
                )
        # Two regions share a range only when one nests in the other, and the list holds each
        # parent before the regions nested in it, so its index breaks every tie.
        ranked = sorted(
            enumerate(found), key=lambda pair: (pair[1].range.start, -pair[1].range.end, pair[0])
        )
        regions = tuple(_region(item, scan.prefixes) for _, item in ranked)
        return Segmentation(source, self._source_type, regions)


def _flatten(nodes: Iterable[InlineNode]) -> list[InlineNode]:
    """List the nodes in preorder, each parent before the nodes nested in it."""
    flat: list[InlineNode] = []
    for node in nodes:
        flat.append(node)
        flat.extend(_flatten(node.children))
    return flat


def _region(item: _Found, prefixes: tuple[Prefix, ...]) -> Region:
    """Build a region, with the prefixes of its containers that its content crosses as gaps."""
    gaps: tuple[Span, ...] = ()
    if item.content is not None:
        owners = frozenset(item.owners)
        content = item.content
        gaps = tuple(
            prefix.span
            for prefix in prefixes
            if prefix.owner in owners and content.contains(prefix.span)
        )
    return Region(item.kind, item.range, item.content, gaps, item.attributes)

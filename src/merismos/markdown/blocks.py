"""
Block scanner of a Markdown source: containers, leaf blocks, and the runs of inline text.

The scanner reads the source line by line. Each line first passes the prefixes of the open
containers (quotations and list items), then may open new containers, then holds one leaf block:
frontmatter, fenced or indented code, a heading, a thematic break, or a line of paragraph. The
scanner records every container prefix that it consumes, with the identifier of the container
owning it, so that the segmenter can give each region the gaps of its own containers only.

Classes
-------
Prefix
    Container prefix consumed on a line, with the identifier of its container.
BlockRegion
    Region found by the scanner, with the containers enclosing it.
InlineRun
    Text of one paragraph or heading, scanned later for inline constructs.
BlockScan
    Result of scanning one source.
BlockScanner
    Scanner of the blocks of a source under one Markdown syntax.
"""

from dataclasses import dataclass, field
from itertools import count
from typing import Iterator

from ..model import AttributeValue, Span
from . import kinds
from .lines import Cursor, Line, is_blank, split_lines
from .syntax import MarkdownSyntax

QUOTATION_SPACING = 1
"""Columns of space after a quotation marker that belong to the marker rather than the content."""


@dataclass(frozen=True)
class Prefix:
    """
    Container prefix consumed on a line, with the identifier of its container.

    Attributes
    ----------
    span : Span
        Code points of the prefix.
    owner : int
        Identifier of the container, or of the indented code block, owning the prefix.
    """

    span: Span
    owner: int


@dataclass
# Each attribute is one field of a region, filled while the region stays open.
class BlockRegion:  # pylint: disable=too-many-instance-attributes
    """
    Region found by the scanner, with the containers enclosing it.

    Attributes
    ----------
    identifier : int
        Identifier of the region, increasing in the order of creation.
    kind : str
        Span kind of the region.
    start : int
        Start of the range.
    content_start : int | None
        Start of the content, None until the scanner reaches it.
    owners : tuple[int, ...]
        Identifiers of the containers whose prefixes may be gaps of the region, its own included.
    attributes : dict[str, AttributeValue]
        Attributes of the region.
    end : int
        End of the range, set when the region closes.
    content_end : int | None
        End of the content, set when the region closes.
    """

    identifier: int
    kind: str
    start: int
    content_start: int | None
    owners: tuple[int, ...]
    attributes: dict[str, AttributeValue] = field(default_factory=dict)
    end: int = -1
    content_end: int | None = None


@dataclass(frozen=True)
class InlineRun:
    """
    Text of one paragraph or heading, scanned later for inline constructs.

    Attributes
    ----------
    identifier : int
        Identifier of the run, in the sequence of the region identifiers.
    segments : tuple[Span, ...]
        Text of each line of the run, without its container prefixes.
    owners : tuple[int, ...]
        Identifiers of the containers enclosing the run.
    """

    identifier: int
    segments: tuple[Span, ...]
    owners: tuple[int, ...]


@dataclass(frozen=True)
class BlockScan:
    """
    Result of scanning one source.

    Attributes
    ----------
    regions : tuple[BlockRegion, ...]
        Block regions, closed.
    runs : tuple[InlineRun, ...]
        Runs of inline text.
    prefixes : tuple[Prefix, ...]
        Container prefixes of every line.
    next_identifier : int
        First identifier left free for the regions found inside the runs.
    """

    regions: tuple[BlockRegion, ...]
    runs: tuple[InlineRun, ...]
    prefixes: tuple[Prefix, ...]
    next_identifier: int


@dataclass
class _Container:
    """Open container: a quotation, with its region, or a list item, with its content column."""

    identifier: int
    region: BlockRegion | None
    content_column: int
    last_end: int


@dataclass
class _Paragraph:
    """Open paragraph, collecting the text of its lines."""

    identifier: int
    segments: list[Span]
    owners: tuple[int, ...]


@dataclass
class _Fence:
    """Open fenced code block."""

    region: BlockRegion
    character: str
    length: int
    last_end: int


@dataclass
class _IndentedCode:
    """Open indented code block."""

    region: BlockRegion
    last_text_end: int


class BlockScanner:
    """
    Scanner of the blocks of a source under one Markdown syntax.

    Parameters
    ----------
    syntax : MarkdownSyntax
        Syntax of the dialect.
    """

    def __init__(self, syntax: MarkdownSyntax) -> None:
        self._syntax = syntax

    def scan(self, source: str) -> BlockScan:
        """
        Scan the blocks of a source.

        Returns
        -------
        BlockScan
            Block regions, inline runs and container prefixes of the source.
        """
        return _Scan(self._syntax, source).run()


# Each attribute is part of the state of one scan, discarded at its end.
class _Scan:  # pylint: disable=too-many-instance-attributes
    """State of one scan, discarded once the source is read."""

    def __init__(self, syntax: MarkdownSyntax, source: str) -> None:
        self.syntax = syntax
        self.source = source
        self.lines = split_lines(source)
        self.identifiers: Iterator[int] = count()
        self.regions: list[BlockRegion] = []
        self.runs: list[InlineRun] = []
        self.prefixes: list[Prefix] = []
        self.stack: list[_Container] = []
        self.leaf: _Paragraph | _Fence | _IndentedCode | None = None

    # --- driver ---------------------------------------------------------------------------------

    def run(self) -> BlockScan:
        """Scan every line, then close the blocks left open."""
        first = self._frontmatter()
        for line in self.lines[first:]:
            self._line(line)
        self._close_leaf()
        self._close_containers(0)
        return BlockScan(
            tuple(self.regions), tuple(self.runs), tuple(self.prefixes), next(self.identifiers)
        )

    def _region(
        self,
        kind: str,
        start: int,
        content_start: int | None,
        own: bool,
        **attributes: AttributeValue
    ) -> BlockRegion:
        """Create a block region enclosed by the open containers, optionally owning its prefixes."""
        identifier = next(self.identifiers)
        owners = tuple(container.identifier for container in self.stack)
        if own:
            owners += (identifier,)
        region = BlockRegion(identifier, kind, start, content_start, owners, dict(attributes))
        self.regions.append(region)
        return region

    # --- frontmatter ----------------------------------------------------------------------------

    def _frontmatter(self) -> int:
        """Record the frontmatter opening the source, returning the index of the next line."""
        syntax = self.syntax.frontmatter
        if syntax is None or not self.lines or self._text(self.lines[0]) != syntax.fence:
            return 0
        for index, line in enumerate(self.lines[1:], start=1):
            if self._text(line) == syntax.fence:
                region = self._region(kinds.FRONTMATTER, 0, self.lines[1].start, own=False)
                region.end, region.content_end = line.end, line.start
                return index + 1
        return 0

    def _text(self, line: Line) -> str:
        """Return the text of a line, without its ending."""
        return self.source[line.start : line.end]

    # --- one line -------------------------------------------------------------------------------

    def _line(self, line: Line) -> None:
        """Read one line: its container prefixes, an open block it continues, then new blocks."""
        cursor, matched, line_prefixes = self._match_containers(line)
        all_matched = matched == len(self.stack)
        if isinstance(self.leaf, _Fence):
            if all_matched and self._fence_line(self.leaf, line, cursor, line_prefixes):
                return
            if not all_matched:
                self._close_leaf()
        if isinstance(self.leaf, _IndentedCode):
            if all_matched and self._indented_line(self.leaf, line, cursor, line_prefixes):
                return
            self._close_leaf()
        if (
            not all_matched
            and isinstance(self.leaf, _Paragraph)
            and not is_blank(self.source, cursor.position, line.end)
            and not self._opens_block(cursor, line)
        ):
            # A lazy continuation line keeps every container open without its prefix.
            self.leaf.segments.append(Span(cursor.position, line.end))
            self._keep(line_prefixes, line, self.stack)
            return
        if not all_matched:
            self._close_leaf()
            self._close_containers(matched)
        self._keep(line_prefixes, line, self.stack)
        cursor = self._open_containers(cursor, line)
        self._leaf_line(cursor, line)

    def _keep(self, line_prefixes: list[Prefix], line: Line, containers: list[_Container]) -> None:
        """Record the prefixes of a line, and extend the containers that hold it."""
        self.prefixes.extend(
            prefix for prefix in line_prefixes if prefix.span.end > prefix.span.start
        )
        for container in containers:
            container.last_end = line.end

    def _match_containers(self, line: Line) -> tuple[Cursor, int, list[Prefix]]:
        """Consume the prefixes of the open containers, as far as the line holds them."""
        cursor = Cursor(line.start, 0)
        line_prefixes: list[Prefix] = []
        matched = 0
        for container in self.stack:
            if container.region is not None:
                after = self._quotation_marker(cursor, line)
                if after is None:
                    break
            elif is_blank(self.source, cursor.position, line.end):
                after = cursor
            else:
                after = cursor.consume_columns(
                    self.source,
                    line.end,
                    container.content_column - cursor.column,
                    self.syntax.tab_width,
                )
                if after is None:
                    break
            line_prefixes.append(
                Prefix(Span(cursor.position, after.position), container.identifier)
            )
            cursor = after
            matched += 1
        return cursor, matched, line_prefixes

    # --- containers -----------------------------------------------------------------------------

    def _block_start(self, cursor: Cursor, line: Line) -> Cursor | None:
        """Skip the indentation admitted before a block marker, or None when it is too deep."""
        columns, after = cursor.indentation(self.source, line.end, self.syntax.tab_width)
        return after if columns <= self.syntax.block_indent else None

    def _quotation_marker(self, cursor: Cursor, line: Line) -> Cursor | None:
        """Consume a quotation marker and the space following it, or return None."""
        syntax = self.syntax.quotations
        start = self._block_start(cursor, line)
        if (
            syntax is None
            or start is None
            or not self.source.startswith(syntax.marker, start.position)
        ):
            return None
        after = Cursor(start.position + len(syntax.marker), start.column + len(syntax.marker))
        spaced = after.consume_columns(
            self.source, line.end, QUOTATION_SPACING, self.syntax.tab_width
        )
        return spaced if spaced is not None else after

    def _list_marker(self, cursor: Cursor, line: Line) -> tuple[Cursor, int] | None:
        """Recognize a list marker, returning the cursor after it and the column of its content."""
        syntax = self.syntax.lists
        start = self._block_start(cursor, line)
        if syntax is None or start is None:
            return None
        position = start.position
        end = position
        if position < line.end and self.source[position] in syntax.bullets:
            end = position + 1
        else:
            while (
                end < line.end
                and end - position < syntax.maximum_digits
                and self.source[end].isdigit()
            ):
                end += 1
            if (
                end == position
                or end >= line.end
                or self.source[end] not in syntax.ordered_delimiters
            ):
                return None
            end += 1
        if end < line.end and self.source[end] not in " \t":
            return None
        marker = Cursor(end, start.column + end - position)
        spacing, after = marker.indentation(self.source, line.end, self.syntax.tab_width)
        if after.position >= line.end or spacing > syntax.maximum_spacing:
            # An empty item or a wide spacing sets the content one column after the marker.
            spacing = 1
            after = (
                marker.consume_columns(self.source, line.end, 1, self.syntax.tab_width) or marker
            )
        return after, marker.column + spacing

    def _open_containers(self, cursor: Cursor, line: Line) -> Cursor:
        """Open the quotations and list items starting on a line."""
        while True:
            after = self._quotation_marker(cursor, line)
            if after is not None:
                self._close_leaf()
                marker = self._block_start(cursor, line)
                assert marker is not None
                callout = self._callout(after, line)
                region = self._region(
                    kinds.QUOTATION, marker.position, after.position, own=True, callout=callout
                )
                self.stack.append(_Container(region.identifier, region, 0, line.end))
                cursor = after
                continue
            if self._thematic_break(cursor, line):
                return cursor
            item = self._list_marker(cursor, line)
            if item is not None:
                self._close_leaf()
                after, column = item
                identifier = next(self.identifiers)
                self.stack.append(_Container(identifier, None, column, line.end))
                cursor = after
                continue
            return cursor

    def _callout(self, cursor: Cursor, line: Line) -> str | None:
        """Return the type of the callout opened by the first line of a quotation, if any."""
        quotations = self.syntax.quotations
        syntax = quotations.callout if quotations is not None else None
        if syntax is None or not self.source.startswith(syntax.opening, cursor.position):
            return None
        start = cursor.position + len(syntax.opening)
        match = syntax.type_pattern.match(self.source, start, line.end)
        if match is None or not self.source.startswith(syntax.closing, match.end()):
            return None
        return match.group(0)

    def _close_containers(self, keep: int) -> None:
        """Close the containers above the first `keep` ones."""
        while len(self.stack) > keep:
            container = self.stack.pop()
            if container.region is not None:
                container.region.end = container.last_end
                container.region.content_end = container.last_end
                assert container.region.content_start is not None
                container.region.content_start = min(
                    container.region.content_start, container.last_end
                )

    # --- leaf blocks ----------------------------------------------------------------------------

    def _opens_block(self, cursor: Cursor, line: Line) -> bool:
        """Whether a line opens a block, which ends a paragraph instead of continuing it lazily."""
        return (
            self._quotation_marker(cursor, line) is not None
            or self._thematic_break(cursor, line)
            or self._list_marker(cursor, line) is not None
            or self._heading(cursor, line) is not None
            or self._fence_opening(cursor, line) is not None
        )

    def _leaf_line(self, cursor: Cursor, line: Line) -> None:
        """Read the leaf part of a line: the first handler accepting it decides its block."""
        handlers = (
            self._closing_line,
            self._heading_line,
            self._fence_opening_line,
            self._indented_code_opening,
        )
        if not any(handler(cursor, line) for handler in handlers):
            self._paragraph_line(cursor, line)

    def _closing_line(self, cursor: Cursor, line: Line) -> bool:
        """Close the open leaf on a blank line, a setext underline or a thematic break."""
        closes = (
            is_blank(self.source, cursor.position, line.end)
            or (isinstance(self.leaf, _Paragraph) and self._setext_underline(cursor, line))
            or self._thematic_break(cursor, line)
        )
        if closes:
            self._close_leaf()
        return closes

    def _heading_line(self, cursor: Cursor, line: Line) -> bool:
        """Record a heading and its run of inline text, returning whether the line holds one."""
        heading = self._heading(cursor, line)
        if heading is None:
            return False
        self._close_leaf()
        start, level, content = heading
        region = self._region(kinds.HEADING, start, content.start, own=False, level=level)
        region.end, region.content_end = line.end, content.end
        owners = tuple(container.identifier for container in self.stack)
        self.runs.append(InlineRun(next(self.identifiers), (content,), owners))
        return True

    def _fence_opening_line(self, cursor: Cursor, line: Line) -> bool:
        """Open a fenced code block, returning whether the line opens one."""
        fence = self._fence_opening(cursor, line)
        if fence is None:
            return False
        self._close_leaf()
        start, character, length, info = fence
        region = self._region(kinds.FENCED_CODE, start, None, own=False, info=info)
        self.leaf = _Fence(region, character, length, line.end)
        return True

    def _paragraph_line(self, cursor: Cursor, line: Line) -> None:
        """Add a line to the open paragraph, or open a paragraph with it."""
        if isinstance(self.leaf, _Paragraph):
            self.leaf.segments.append(Span(cursor.position, line.end))
            return
        owners = tuple(container.identifier for container in self.stack)
        self.leaf = _Paragraph(next(self.identifiers), [Span(cursor.position, line.end)], owners)

    def _close_leaf(self) -> None:
        """Close the open leaf block, recording its run or the end of its region."""
        leaf = self.leaf
        self.leaf = None
        if isinstance(leaf, _Paragraph):
            self.runs.append(InlineRun(leaf.identifier, tuple(leaf.segments), leaf.owners))
        elif isinstance(leaf, _Fence):
            # A fence never closed runs to the end of its last line.
            leaf.region.end = leaf.last_end
            if leaf.region.content_start is None:
                leaf.region.content_start = leaf.last_end
            leaf.region.content_end = leaf.last_end
        elif isinstance(leaf, _IndentedCode):
            leaf.region.end = leaf.last_text_end
            leaf.region.content_end = leaf.last_text_end

    def _thematic_break(self, cursor: Cursor, line: Line) -> bool:
        """Whether a line is a thematic break."""
        syntax = self.syntax.thematic_breaks
        start = self._block_start(cursor, line)
        if syntax is None or start is None:
            return False
        text = self.source[start.position : line.end]
        marks = [character for character in text if character not in " \t"]
        return (
            len(marks) >= syntax.minimum_count
            and marks[0] in syntax.characters
            and all(mark == marks[0] for mark in marks)
        )

    def _setext_underline(self, cursor: Cursor, line: Line) -> bool:
        """Whether a line underlines the open paragraph as a heading of another style."""
        start = self._block_start(cursor, line)
        if start is None:
            return False
        text = self.source[start.position : line.end].rstrip(" \t")
        return bool(text) and text[0] in self.syntax.setext_underlines and set(text) == {text[0]}

    def _heading(self, cursor: Cursor, line: Line) -> tuple[int, int, Span] | None:
        """Recognize a heading, returning its start, its level and its content."""
        syntax = self.syntax.headings
        start = self._block_start(cursor, line)
        if syntax is None or start is None:
            return None
        position = start.position
        end = position
        while end < line.end and self.source[end] == syntax.marker:
            end += 1
        level = end - position
        if not 1 <= level <= syntax.maximum_level or (
            end < line.end and self.source[end] not in " \t"
        ):
            return None
        content_start = end
        while content_start < line.end and self.source[content_start] in " \t":
            content_start += 1
        content_end = line.end
        while content_end > content_start and self.source[content_end - 1] in " \t":
            content_end -= 1
        closing = content_end
        while closing > content_start and self.source[closing - 1] == syntax.marker:
            closing -= 1
        if closing < content_end and (
            closing == content_start or self.source[closing - 1] in " \t"
        ):
            # An optional closing run of markers, preceded by a space, belongs to no content.
            content_end = closing
            while content_end > content_start and self.source[content_end - 1] in " \t":
                content_end -= 1
        return position, level, Span(content_start, content_end)

    def _fence_opening(self, cursor: Cursor, line: Line) -> tuple[int, str, int, str] | None:
        """Recognize a fence opening, returning its start, character, length and info string."""
        syntax = self.syntax.fences
        start = self._block_start(cursor, line)
        if syntax is None or start is None or start.position >= line.end:
            return None
        position = start.position
        character = self.source[position]
        if character not in syntax.characters:
            return None
        end = position
        while end < line.end and self.source[end] == character:
            end += 1
        length = end - position
        info = self.source[end : line.end].strip(" \t")
        if length < syntax.minimum_length or (
            character == self.syntax.code_span and character in info
        ):
            return None
        return position, character, length, info

    def _fence_line(
        self, fence: _Fence, line: Line, cursor: Cursor, line_prefixes: list[Prefix]
    ) -> bool:
        """Read one line inside an open fence, returning False when the line falls outside it."""
        self._keep(line_prefixes, line, self.stack)
        start = self._block_start(cursor, line)
        if start is not None:
            end = start.position
            while end < line.end and self.source[end] == fence.character:
                end += 1
            if end - start.position >= fence.length and is_blank(self.source, end, line.end):
                if fence.region.content_start is None:
                    fence.region.content_start = line.start
                fence.region.end, fence.region.content_end = line.end, line.start
                self.leaf = None
                return True
        if fence.region.content_start is None:
            fence.region.content_start = line.start
        fence.last_end = line.end
        return True

    def _indented_code_opening(self, cursor: Cursor, line: Line) -> bool:
        """Open an indented code block on a line, returning whether one opens."""
        syntax = self.syntax.indented_code
        # Indented code never interrupts a paragraph: an indented line continues it instead.
        if syntax is None or isinstance(self.leaf, _Paragraph):
            return False
        after = cursor.consume_columns(self.source, line.end, syntax.indent, self.syntax.tab_width)
        if after is None:
            return False
        region = self._region(kinds.INDENTED_CODE, cursor.position, after.position, own=True)
        self.leaf = _IndentedCode(region, line.end)
        return True

    def _indented_line(
        self, code: _IndentedCode, line: Line, cursor: Cursor, line_prefixes: list[Prefix]
    ) -> bool:
        """Read one line after an indented code block, returning False when the block ends."""
        syntax = self.syntax.indented_code
        assert syntax is not None
        if is_blank(self.source, cursor.position, line.end):
            self._keep(line_prefixes, line, self.stack)
            return True
        after = cursor.consume_columns(self.source, line.end, syntax.indent, self.syntax.tab_width)
        if after is None:
            return False
        self._keep(
            line_prefixes + [Prefix(Span(cursor.position, after.position), code.region.identifier)],
            line,
            self.stack,
        )
        code.last_text_end = line.end
        return True

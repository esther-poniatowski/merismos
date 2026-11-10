"""
Inline scanner: code spans, mathematics and links inside the text of a paragraph or heading.

The scanner reads one run of text, its container prefixes removed, from left to right. A
construct opened first takes precedence over the constructs opening inside it, and no construct
opens inside an opaque one. A closing bracket inside a code span closes no link text, as in
CommonMark. A syntax may let a link prevail over a code span crossing its text, as Obsidian does:
when the brackets matched around the code spans form no link, the brackets matched without them
are tried.

A code span closes at the next run of its delimiter as wide as its opening run. A syntax may also
let the first narrower run close it when no run as wide follows, the excess delimiters of the
opening run then staying literal.

Before scanning, one pass over the run builds an index of its escapes, its backtick runs, its
matched brackets and the positions of each delimiter. Every search for a closing delimiter is
then a lookup in that index, so the scan stays linear in the length of the run, up to a
logarithmic factor, whatever the number of unmatched delimiters.

Classes
-------
InlineNode
    Inline construct found in a run, with its nested constructs.
RunIndex
    Positions of the delimiters of one run, computed in one pass.
InlineScanner
    Scanner of the inline constructs of a run under one Markdown syntax.
"""

from bisect import bisect_left
from dataclasses import dataclass, field
from enum import Enum

from ..model import AttributeValue, Span
from . import kinds
from .syntax import LinkSyntax, MarkdownLinkSyntax, MarkdownSyntax

RUN_LINE_BREAK = "\n"
"""Character joining the lines of a run, whatever the line ending of the source."""


class LinkMode(Enum):
    """Links admitted in a scan: every link, embeds only (inside link text), or none."""

    ALL = "all"
    EMBEDS = "embeds"
    NONE = "none"


@dataclass
class InlineNode:
    """
    Inline construct found in a run, with its nested constructs.

    Offsets are positions in the text of the run, not in the source.

    Attributes
    ----------
    kind : str
        Span kind of the construct.
    range : Span
        Whole construct.
    content : Span | None
        Part between the delimiters, None for a link.
    attributes : dict[str, AttributeValue]
        Attributes of the kind.
    children : list[InlineNode]
        Constructs nested in this one, in order.
    """

    kind: str
    range: Span
    content: Span | None
    attributes: dict[str, AttributeValue] = field(default_factory=dict)
    children: list["InlineNode"] = field(default_factory=list)


def _first_at_or_after(positions: list[int], position: int) -> int | None:
    """Return the first position of a sorted list at or after `position`, or None."""
    index = bisect_left(positions, position)
    return positions[index] if index < len(positions) else None


def run_length(text: str, position: int, end: int, character: str) -> int:
    """Length of the run of `character` starting at `position`."""
    stop = position
    while stop < end and text[stop] == character:
        stop += 1
    return stop - position


# One attribute per delimiter indexed, each a list of positions read by the scan.
class RunIndex:  # pylint: disable=too-many-instance-attributes
    """
    Positions of the delimiters of one run, computed in one pass.

    Parameters
    ----------
    text : str
        Text of the run.
    syntax : MarkdownSyntax
        Syntax of the dialect.
    """

    def __init__(self, text: str, syntax: MarkdownSyntax) -> None:
        self.text = text
        self.escaped = _escaped_positions(text, syntax)
        self.line_breaks = [
            index for index, character in enumerate(text) if character == RUN_LINE_BREAK
        ]
        self._runs_by_width: dict[int, list[int]] = {}
        if syntax.code_span is not None:
            self._index_runs(syntax.code_span)
        math = syntax.math
        self.display = self._occurrences(math.display) if math is not None and math.display else []
        self.inline_closings = (
            self._inline_closings(math.inline) if math is not None and math.inline else []
        )
        links = syntax.links
        wikilink = links.wikilink if links is not None else None
        self.wiki_closings = self._occurrences(wikilink.closing) if wikilink is not None else []
        self.wiki_separators = (
            self._occurrences(wikilink.alias_separator, wikilink.escaped_separator)
            if wikilink is not None
            else []
        )
        self._shorter_closing = syntax.code_span_shorter_closing
        markdown = links.markdown if links is not None else None
        self.brackets = (
            self._match_brackets(markdown, syntax.code_span) if markdown is not None else {}
        )
        #: Brackets matched through the code spans, tried when a link prevails over a code span
        #: crossing its text.
        self.crossing_brackets = (
            self._match_brackets(markdown, None)
            if markdown is not None and not syntax.code_span_over_links
            else {}
        )

    def _index_runs(self, delimiter: str) -> None:
        """Record the start of each maximal run of the code-span delimiter, by width."""
        position = 0
        while position < len(self.text):
            if self.text[position] == delimiter:
                width = run_length(self.text, position, len(self.text), delimiter)
                self._runs_by_width.setdefault(width, []).append(position)
                position += width
            else:
                position += 1

    def _occurrences(self, delimiter: str, escaped: bool = False) -> list[int]:
        """Non-overlapping occurrences of a delimiter, from left to right, the escaped ones only
        when `escaped` admits them."""
        found: list[int] = []
        position = self.text.find(delimiter)
        while position != -1:
            if position in self.escaped and not escaped:
                position = self.text.find(delimiter, position + 1)
                continue
            found.append(position)
            position = self.text.find(delimiter, position + len(delimiter))
        return found

    def _inline_closings(self, delimiter: str) -> list[int]:
        """Occurrences of the inline delimiter that may close mathematics: after a non-space."""
        return [
            position
            for position in self._occurrences(delimiter)
            if position > 0 and not self.text[position - 1].isspace()
        ]

    def _match_brackets(self, syntax: MarkdownLinkSyntax, code_span: str | None) -> dict[int, int]:
        """Match the brackets of link texts, skipping escapes and code spans, which prevail."""
        matches: dict[int, int] = {}
        stack: list[int] = []
        position = 0
        text = self.text
        while position < len(text):
            character = text[position]
            if position in self.escaped:
                position += 1
            elif code_span is not None and character == code_span:
                width = run_length(text, position, len(text), code_span)
                closing = self.code_span_closing(position, width, len(text))
                position = position + width if closing is None else closing[0] + closing[1]
            else:
                if character == syntax.text_opening:
                    stack.append(position)
                elif character == syntax.text_closing and stack:
                    matches[stack.pop()] = position
                position += 1
        return matches

    def code_span_closing(self, position: int, width: int, end: int) -> tuple[int, int] | None:
        """
        Start and width of the run closing a code span opened by the run at `position`: the first
        maximal run of `width` delimiters after it, or, when none follows and the syntax admits
        narrower closings, the first maximal run of fewer delimiters.
        """
        same = _first_at_or_after(self._runs_by_width.get(width, []), position + width)
        if same is not None and same + width <= end:
            return same, width
        if not self._shorter_closing:
            return None
        found = [
            (closing, candidate)
            for candidate in range(1, width)
            if (
                closing := _first_at_or_after(
                    self._runs_by_width.get(candidate, []), position + width
                )
            )
            is not None
            and closing + candidate <= end
        ]
        return min(found) if found else None

    def next_line_break(self, position: int) -> int:
        """Position of the first line break at or after `position`, or the length of the run."""
        found = _first_at_or_after(self.line_breaks, position)
        return len(self.text) if found is None else found


def next_occurrence(positions: list[int], position: int, end: int, width: int) -> int | None:
    """First occurrence of a sorted list at or after `position`, ending before `end`, or None."""
    found = _first_at_or_after(positions, position)
    return found if found is not None and found + width <= end else None


def _escaped_positions(text: str, syntax: MarkdownSyntax) -> frozenset[int]:
    """Positions of the characters escaped by an escape character."""
    escape = syntax.escape
    if escape is None:
        return frozenset()
    escaped: set[int] = set()
    position = 0
    while position < len(text):
        if (
            text[position] == escape.character
            and position + 1 < len(text)
            and text[position + 1] in escape.escapable
        ):
            escaped.add(position + 1)
            position += 2
        else:
            position += 1
    return frozenset(escaped)


class InlineScanner:
    """
    Scanner of the inline constructs of a run under one Markdown syntax.

    Parameters
    ----------
    syntax : MarkdownSyntax
        Syntax of the dialect.

    Examples
    --------
    >>> from merismos.syntax import packaged_syntax_document
    >>> from merismos.markdown.syntax import parse_markdown_syntax
    >>> document = packaged_syntax_document("markdown-obsidian")
    >>> scanner = InlineScanner(parse_markdown_syntax(document.name, document.body))
    >>> [(node.kind, node.range.start, node.range.end) for node in scanner.scan("a `b` $c$")]
    [('inline-code', 2, 5), ('inline-math', 6, 9)]
    """

    def __init__(self, syntax: MarkdownSyntax) -> None:
        self._syntax = syntax

    def scan(self, text: str) -> list[InlineNode]:
        """Return the inline constructs of a run, in order of their start."""
        return _Scan(self._syntax, RunIndex(text, self._syntax)).scan(0, len(text), LinkMode.ALL)

    def display_closing(self, text: str) -> int | None:
        """Position after the first unescaped display delimiter of a text, or None."""
        math = self._syntax.math
        if math is None or math.display is None:
            return None
        occurrences = RunIndex(text, self._syntax).display
        return occurrences[0] + len(math.display) if occurrences else None

    def opens_display_math(self, text: str) -> bool:
        """Whether a run leaves a display delimiter open, so that the next lines continue it."""
        math = self._syntax.math
        if math is None or math.display is None:
            return False
        scan = _Scan(self._syntax, RunIndex(text, self._syntax))
        scan.scan(0, len(text), LinkMode.ALL)
        return scan.unclosed_display


class _Scan:
    """Scan of one run, reading the delimiters from its index."""

    def __init__(self, syntax: MarkdownSyntax, index: RunIndex) -> None:
        self._syntax = syntax
        self._index = index
        self._text = index.text
        #: Whether the scan met a display delimiter that no later delimiter of the run closes.
        self.unclosed_display = False

    def scan(self, start: int, end: int, links: LinkMode) -> list[InlineNode]:
        """Scan the text between two positions, admitting the links of the given mode."""
        nodes: list[InlineNode] = []
        position = start
        while position < end:
            if position + 1 < end and position + 1 in self._index.escaped:
                position += 2
                continue
            node = (
                self._code_span(position, end)
                or self._display_math(position, end)
                or self._inline_math(position, end)
                or self._wikilink(position, end, links)
                or self._markdown_link(position, end, links)
            )
            if node is not None:
                nodes.append(node)
                position = node.range.end
            else:
                position += self._literal_width(position, end)
        return nodes

    def _literal_width(self, position: int, end: int) -> int:
        """Width of the literal text at `position`: a whole backtick run, or one character."""
        delimiter = self._syntax.code_span
        if delimiter is not None and self._text[position] == delimiter:
            # A backtick run without its closing run is literal as a whole, as in CommonMark.
            return run_length(self._text, position, end, delimiter)
        math = self._syntax.math
        if (
            math is not None
            and math.display is not None
            and self._text.startswith(math.display, position)
        ):
            self.unclosed_display = True
            return len(math.display)
        return 1

    # --- code and mathematics -------------------------------------------------------------------

    def _code_span(self, position: int, end: int) -> InlineNode | None:
        """Recognize a code span opening at `position`."""
        delimiter = self._syntax.code_span
        if delimiter is None or self._text[position] != delimiter:
            return None
        width = run_length(self._text, position, end, delimiter)
        found = self._index.code_span_closing(position, width, end)
        if found is None:
            return None
        closing, closing_width = found
        # The opening keeps as many delimiters as the closing run holds, the others staying literal.
        return InlineNode(
            kinds.INLINE_CODE,
            Span(position + width - closing_width, closing + closing_width),
            Span(position + width, closing),
        )

    def _display_math(self, position: int, end: int) -> InlineNode | None:
        """Recognize display mathematics opening at `position`."""
        math = self._syntax.math
        if (
            math is None
            or math.display is None
            or not self._text.startswith(math.display, position)
        ):
            return None
        width = len(math.display)
        closing = next_occurrence(self._index.display, position + width, end, width)
        if closing is None:
            if not math.display_unclosed_runs_to_end:
                return None
            # An unclosed formula runs to the end of the run, whose paragraph it keeps open.
            self.unclosed_display = True
            return InlineNode(kinds.DISPLAY_MATH, Span(position, end), Span(position + width, end))
        return InlineNode(
            kinds.DISPLAY_MATH, Span(position, closing + width), Span(position + width, closing)
        )

    def _inline_math(self, position: int, end: int) -> InlineNode | None:
        """Recognize inline mathematics opening at `position`."""
        math = self._syntax.math
        if math is None or math.inline is None or not self._text.startswith(math.inline, position):
            return None
        width = len(math.inline)
        opening_end = position + width
        if (
            opening_end >= end
            or self._text[opening_end].isspace()
            or self._text.startswith(math.inline, opening_end)
        ):
            return None
        limit = (
            end if math.inline_spans_lines else min(end, self._index.next_line_break(opening_end))
        )
        closing = next_occurrence(self._index.inline_closings, opening_end + 1, limit, width)
        if closing is None:
            return None
        return InlineNode(
            kinds.INLINE_MATH, Span(position, closing + width), Span(opening_end, closing)
        )

    # --- links ----------------------------------------------------------------------------------

    def _opening(self, position: int, opening: str, links: LinkSyntax) -> int | None:
        """Return the start of a link opening at `position`, after an optional embed prefix."""
        prefix = links.embed_prefix
        if prefix is not None and self._text.startswith(prefix + opening, position):
            return position + len(prefix)
        if self._text.startswith(opening, position):
            return position
        return None

    @staticmethod
    def _admitted(mode: LinkMode, embed: bool) -> bool:
        """Whether a scan in `mode` admits a link, given whether the link is an embed."""
        return mode is LinkMode.ALL or (mode is LinkMode.EMBEDS and embed)

    def _text_mode(self) -> LinkMode:
        """Links admitted inside the text of a Markdown link."""
        links = self._syntax.links
        return LinkMode.EMBEDS if links is not None and links.embeds_in_text else LinkMode.NONE

    def _wikilink(self, position: int, end: int, mode: LinkMode) -> InlineNode | None:
        """Recognize a wikilink, possibly an embed, opening at `position`."""
        links = self._syntax.links
        syntax = links.wikilink if links is not None else None
        if links is None or syntax is None:
            return None
        opening = self._opening(position, syntax.opening, links)
        if opening is None or not self._admitted(mode, opening != position):
            return None
        inner = opening + len(syntax.opening)
        limit = min(end, self._index.next_line_break(inner))
        closing = next_occurrence(self._index.wiki_closings, inner, limit, len(syntax.closing))
        if closing is None:
            return None
        separator = next_occurrence(
            self._index.wiki_separators, inner, closing, len(syntax.alias_separator)
        )
        destination = self._wiki_destination(inner, closing, separator)
        if syntax.excluded and any(
            character in syntax.excluded
            for character in self._text[destination.start : destination.end]
        ):
            return None
        node = InlineNode(
            kinds.LINK,
            Span(position, closing + len(syntax.closing)),
            None,
            {"syntax": "wiki", "embed": opening != position},
        )
        node.children.append(InlineNode(kinds.LINK_DESTINATION, destination, destination))
        if separator is not None:
            alias = Span(separator + len(syntax.alias_separator), closing)
            children = self.scan(alias.start, alias.end, LinkMode.NONE)
            node.children.append(InlineNode(kinds.LINK_TEXT, alias, alias, children=children))
        return node

    def _wiki_destination(self, inner: int, closing: int, separator: int | None) -> Span:
        """Return the destination of a wikilink, up to its separator or its closing; an escaped
        separator separates too, its escape character left out of the destination."""
        if separator is None:
            return Span(inner, closing)
        return Span(inner, separator - 1 if separator in self._index.escaped else separator)

    def _markdown_link(self, position: int, end: int, mode: LinkMode) -> InlineNode | None:
        """Recognize a Markdown link, possibly an embed, opening at `position`."""
        links = self._syntax.links
        syntax = links.markdown if links is not None else None
        if links is None or syntax is None:
            return None
        opening = self._opening(position, syntax.text_opening, links)
        if opening is None or not self._admitted(mode, opening != position):
            return None
        for brackets in (self._index.brackets, self._index.crossing_brackets):
            node = self._link_text_at(position, opening, brackets.get(opening), end)
            if node is not None:
                return node
        return None

    def _link_text_at(
        self, position: int, opening: int, bracket: int | None, end: int
    ) -> InlineNode | None:
        """Recognize a Markdown link whose text closes at `bracket`, None when none closes there."""
        links = self._syntax.links
        syntax = links.markdown if links is not None else None
        if (
            syntax is None
            or bracket is None
            or bracket + 1 >= end
            or self._text[bracket + 1] != syntax.destination_opening
        ):
            return None
        parsed = self._destination(syntax, bracket + 2, end)
        if parsed is None:
            return None
        destination, content, link_end = parsed
        node = InlineNode(
            kinds.LINK,
            Span(position, link_end),
            None,
            {"syntax": "markdown", "embed": opening != position},
        )
        label = Span(opening + 1, bracket)
        children = self.scan(label.start, label.end, self._text_mode())
        node.children.append(InlineNode(kinds.LINK_TEXT, label, label, children=children))
        node.children.append(InlineNode(kinds.LINK_DESTINATION, destination, content))
        return node

    def _until(self, start: int, end: int, stops: tuple[str, ...]) -> int:
        """First position from `start` holding an unescaped stop character, or `end`."""
        position = start
        while position < end and (
            self._text[position] not in stops or position in self._index.escaped
        ):
            position += 1
        return position

    def _destination(
        self, syntax: MarkdownLinkSyntax, start: int, end: int
    ) -> tuple[Span, Span, int] | None:
        """Parse the destination and the title of a Markdown link, up to its closing character."""
        text = self._text
        position = _skip_space(text, start, end)
        opening, closing = syntax.destination_brackets
        if position < end and text[position] == opening:
            stop = self._until(position + 1, end, (closing, opening, RUN_LINE_BREAK))
            if stop >= end or text[stop] != closing:
                return None
            destination, content = Span(position, stop + 1), Span(position + 1, stop)
            position = stop + 1
        else:
            stop = self._bare_destination_end(syntax, position, end)
            destination = content = Span(position, stop)
            position = stop
        position = _skip_space(text, position, end)
        if (
            position < end
            and text[position] in syntax.title_delimiters
            and position > destination.end
        ):
            title_end = self._until(position + 1, end, (syntax.title_delimiters[text[position]],))
            if title_end >= end:
                return None
            position = _skip_space(text, title_end + 1, end)
        if position >= end or text[position] != syntax.destination_closing:
            return None
        return destination, content, position + 1

    def _bare_destination_end(self, syntax: MarkdownLinkSyntax, position: int, end: int) -> int:
        """End of a destination without brackets: a space, or an unbalanced closing character."""
        depth = 0
        stop = position
        while stop < end and not self._text[stop].isspace():
            if stop not in self._index.escaped:
                if self._text[stop] == syntax.destination_opening:
                    depth += 1
                elif self._text[stop] == syntax.destination_closing:
                    if not depth:
                        break
                    depth -= 1
            stop += 1
        return stop


def _skip_space(text: str, position: int, end: int) -> int:
    """Skip spaces and tabs, and at most one line break."""
    seen_break = False
    while position < end and text[position] in " \t" + RUN_LINE_BREAK:
        if text[position] == RUN_LINE_BREAK:
            if seen_break:
                break
            seen_break = True
        position += 1
    return position

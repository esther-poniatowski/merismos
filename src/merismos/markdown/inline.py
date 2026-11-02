"""
Inline scanner: code spans, mathematics and links inside the text of a paragraph or heading.

The scanner reads one run of text, its container prefixes removed, from left to right. A
construct opened first takes precedence over the constructs opening inside it, and no construct
opens inside an opaque one. One exception holds, as in CommonMark: a code span takes precedence
over a link, so a closing bracket inside a code span closes no link text.

Classes
-------
InlineNode
    Inline construct found in a run, with its nested constructs.
InlineScanner
    Scanner of the inline constructs of a run under one Markdown syntax.
"""

from dataclasses import dataclass, field

from ..model import AttributeValue, Span
from . import kinds
from .syntax import LinkSyntax, MarkdownSyntax

TITLE_CLOSERS = {'"': '"', "'": "'", "(": ")"}
"""Delimiters of the title of a Markdown link, each opening character with its closing one."""

DESTINATION_BRACKETS = ("<", ">")
"""Brackets around a destination that holds spaces."""


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
        return self._scan(text, 0, len(text), links=self._syntax.links)

    # --- driver ---------------------------------------------------------------------------------

    def _scan(self, text: str, start: int, end: int, links: LinkSyntax | None) -> list[InlineNode]:
        """Scan the text between two offsets, with or without links."""
        nodes: list[InlineNode] = []
        position = start
        while position < end:
            if self._escapes(text, position, end):
                position += 2
                continue
            node = (
                self._code_span(text, position, end)
                or self._display_math(text, position, end)
                or self._inline_math(text, position, end)
                or self._wikilink(text, position, end, links)
                or self._markdown_link(text, position, end, links)
            )
            if node is None:
                position += 1
                continue
            nodes.append(node)
            position = node.range.end
        return nodes

    def _escapes(self, text: str, position: int, end: int) -> bool:
        """Whether an escape character at `position` escapes the character after it."""
        syntax = self._syntax.escape
        return (
            syntax is not None
            and text[position] == syntax.character
            and position + 1 < end
            and text[position + 1] in syntax.escapable
        )

    def _escaped(self, text: str, position: int, start: int) -> bool:
        """Whether the character at `position` follows an odd run of escape characters."""
        syntax = self._syntax.escape
        if syntax is None:
            return False
        run = 0
        while position - run - 1 >= start and text[position - run - 1] == syntax.character:
            run += 1
        return run % 2 == 1

    # --- code and mathematics -------------------------------------------------------------------

    def _code_span(self, text: str, position: int, end: int) -> InlineNode | None:
        """Recognize a code span opening at `position`."""
        delimiter = self._syntax.code_span
        if delimiter is None or text[position] != delimiter:
            return None
        width = _run_length(text, position, end, delimiter)
        search = position + width
        while search < end:
            if text[search] == delimiter:
                closing = _run_length(text, search, end, delimiter)
                if closing == width:
                    return InlineNode(
                        kinds.INLINE_CODE,
                        Span(position, search + width),
                        Span(position + width, search),
                    )
                search += closing
            else:
                search += 1
        return None

    def _display_math(self, text: str, position: int, end: int) -> InlineNode | None:
        """Recognize display mathematics opening at `position`."""
        math = self._syntax.math
        if math is None or math.display is None or not text.startswith(math.display, position):
            return None
        delimiter = math.display
        search = position + len(delimiter)
        while (closing := text.find(delimiter, search, end)) != -1:
            if not self._escaped(text, closing, position):
                return InlineNode(
                    kinds.DISPLAY_MATH,
                    Span(position, closing + len(delimiter)),
                    Span(position + len(delimiter), closing),
                )
            search = closing + 1
        return None

    def _inline_math(self, text: str, position: int, end: int) -> InlineNode | None:
        """Recognize inline mathematics opening at `position`."""
        math = self._syntax.math
        if math is None or math.inline is None or not text.startswith(math.inline, position):
            return None
        delimiter = math.inline
        opening_end = position + len(delimiter)
        if (
            opening_end >= end
            or text[opening_end].isspace()
            or text.startswith(delimiter, opening_end)
        ):
            return None
        search = opening_end + 1
        while search < end:
            character = text[search]
            if character == "\n" and not math.inline_spans_lines:
                return None
            if (
                text.startswith(delimiter, search)
                and not text[search - 1].isspace()
                and not self._escaped(text, search, position)
            ):
                return InlineNode(
                    kinds.INLINE_MATH,
                    Span(position, search + len(delimiter)),
                    Span(opening_end, search),
                )
            search += 1
        return None

    # --- links ----------------------------------------------------------------------------------

    def _embed(self, text: str, position: int, opening: str, links: LinkSyntax) -> int | None:
        """Return the start of the link opening at `position`, after an optional embed prefix."""
        prefix = links.embed_prefix
        if prefix is not None and text.startswith(prefix + opening, position):
            return position + len(prefix)
        if text.startswith(opening, position):
            return position
        return None

    def _wikilink(
        self, text: str, position: int, end: int, links: LinkSyntax | None
    ) -> InlineNode | None:
        """Recognize a wikilink, possibly an embed, opening at `position`."""
        syntax = links.wikilink if links is not None else None
        if links is None or syntax is None:
            return None
        opening = self._embed(text, position, syntax.opening, links)
        if opening is None:
            return None
        inner_start = opening + len(syntax.opening)
        closing = text.find(syntax.closing, inner_start, end)
        if closing == -1 or "\n" in text[inner_start:closing]:
            return None
        separator = text.find(syntax.alias_separator, inner_start, closing)
        destination_end = closing if separator == -1 else separator
        node = InlineNode(
            kinds.LINK,
            Span(position, closing + len(syntax.closing)),
            None,
            {"syntax": "wiki", "embed": opening != position},
        )
        destination = Span(inner_start, destination_end)
        node.children.append(InlineNode(kinds.LINK_DESTINATION, destination, destination))
        if separator != -1:
            alias = Span(separator + len(syntax.alias_separator), closing)
            node.children.append(
                InlineNode(
                    kinds.LINK_TEXT,
                    alias,
                    alias,
                    children=self._scan(text, alias.start, alias.end, None),
                )
            )
        return node

    def _markdown_link(
        self, text: str, position: int, end: int, links: LinkSyntax | None
    ) -> InlineNode | None:
        """Recognize a Markdown link, possibly an embed, opening at `position`."""
        if links is None or not links.markdown:
            return None
        opening = self._embed(text, position, "[", links)
        if opening is None:
            return None
        bracket = self._closing_bracket(text, opening, end)
        if bracket is None or bracket + 1 >= end or text[bracket + 1] != "(":
            return None
        parsed = self._destination(text, bracket + 2, end)
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
        node.children.append(
            InlineNode(
                kinds.LINK_TEXT,
                label,
                label,
                children=self._scan(text, label.start, label.end, None),
            )
        )
        node.children.append(InlineNode(kinds.LINK_DESTINATION, destination, content))
        return node

    def _closing_bracket(self, text: str, opening: int, end: int) -> int | None:
        """Find the bracket closing a link text, skipping escapes and code spans."""
        depth = 0
        position = opening
        while position < end:
            if self._escapes(text, position, end):
                position += 2
                continue
            code = self._code_span(text, position, end)
            if code is not None:
                position = code.range.end
                continue
            character = text[position]
            if character == "[":
                depth += 1
            elif character == "]":
                depth -= 1
                if not depth:
                    return position
            position += 1
        return None

    def _destination(self, text: str, start: int, end: int) -> tuple[Span, Span, int] | None:
        """Parse the destination and the title of a Markdown link, up to its closing parenthesis."""
        position = _skip_space(text, start, end)
        opening, closing = DESTINATION_BRACKETS
        if position < end and text[position] == opening:
            stop = position + 1
            while stop < end and text[stop] not in (closing, opening, "\n"):
                stop += 1
            if stop >= end or text[stop] != closing:
                return None
            destination = Span(position, stop + 1)
            content = Span(position + 1, stop)
            position = stop + 1
        else:
            stop = position
            depth = 0
            while stop < end and not text[stop].isspace():
                if text[stop] == "(":
                    depth += 1
                elif text[stop] == ")":
                    if not depth:
                        break
                    depth -= 1
                stop += 1
            destination = content = Span(position, stop)
            position = stop
        position = _skip_space(text, position, end)
        if position < end and text[position] in TITLE_CLOSERS and position > destination.end:
            title_end = text.find(TITLE_CLOSERS[text[position]], position + 1, end)
            if title_end == -1:
                return None
            position = _skip_space(text, title_end + 1, end)
        if position >= end or text[position] != ")":
            return None
        return destination, content, position + 1


def _run_length(text: str, position: int, end: int, character: str) -> int:
    """Length of the run of `character` starting at `position`."""
    stop = position
    while stop < end and text[stop] == character:
        stop += 1
    return stop - position


def _skip_space(text: str, position: int, end: int) -> int:
    """Skip spaces and tabs, and at most one line break."""
    seen_break = False
    while position < end and text[position] in " \t\n":
        if text[position] == "\n":
            if seen_break:
                break
            seen_break = True
        position += 1
    return position

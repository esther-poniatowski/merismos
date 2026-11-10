"""
Typed syntax of a Markdown dialect, parsed from the body of a syntax file.

Each construct of the dialect takes one section of the file. A section set to null disables its
construct, so a dialect without wikilinks or without mathematics needs no code. The algorithms
of the segmenter stay fixed, and every delimiter, marker and limit that they read comes from
this syntax.

Classes
-------
MarkdownSyntax
    Complete syntax of a Markdown dialect.

Functions
---------
parse_markdown_syntax(name, fields) -> MarkdownSyntax
    Parse the body of a Markdown syntax file.
"""

from dataclasses import dataclass
import re

from ..errors import SyntaxFileError
from ..syntax import Fields


@dataclass(frozen=True)
class FrontmatterSyntax:
    """Frontmatter opening the source: a fence line, the body, and the same fence line."""

    fence: str


@dataclass(frozen=True)
class FenceSyntax:
    """
    Fenced code: a run of one fence character, at least `minimum_length` long.

    The info string of a fence made of a character of `info_excludes_fence` may not contain
    that character, so that a run of them in a paragraph reads as a code span instead.
    """

    characters: tuple[str, ...]
    minimum_length: int
    info_excludes_fence: frozenset[str]


@dataclass(frozen=True)
class IndentedCodeSyntax:
    """Indented code: lines indented by at least `indent` columns outside a paragraph."""

    indent: int


@dataclass(frozen=True)
class HeadingSyntax:
    """Heading opened by a run of `marker`, at most `maximum_level` long."""

    marker: str
    maximum_level: int


@dataclass(frozen=True)
class CalloutSyntax:
    """Callout: a quotation whose first line opens with `opening`, a type and `closing`."""

    opening: str
    closing: str
    type_pattern: re.Pattern[str]
    fold_signs: tuple[str, ...]


@dataclass(frozen=True)
class QuotationSyntax:
    """Quotation opened by `marker`, followed by at most `spacing` columns, on each line."""

    marker: str
    spacing: int
    callout: CalloutSyntax | None


@dataclass(frozen=True)
class ListSyntax:
    """List items: bullet markers, or ordinals followed by a delimiter."""

    bullets: tuple[str, ...]
    ordered_delimiters: tuple[str, ...]
    maximum_digits: int
    maximum_spacing: int


@dataclass(frozen=True)
class ThematicBreakSyntax:
    """Thematic break: a line holding at least `minimum_count` of one character."""

    characters: tuple[str, ...]
    minimum_count: int


@dataclass(frozen=True)
class MathSyntax:
    """Mathematics delimited by `display` or `inline`, either possibly disabled."""

    display: str | None
    inline: str | None
    inline_spans_lines: bool
    display_spans_blank_lines: bool
    display_unclosed_runs_to_end: bool


@dataclass(frozen=True)
class WikilinkSyntax:
    """
    Wikilink: `opening`, a destination, an optional alias after `alias_separator`, `closing`.

    Attributes
    ----------
    excluded : str
        Characters that a destination cannot hold, so that an opening followed by one of them
        before its closing opens no wikilink.
    escaped_separator : bool
        Whether an escaped alias separator still separates the alias, its escape character left
        out of the destination, as a table cell requires the escape.
    """

    opening: str
    closing: str
    alias_separator: str
    excluded: str = ""
    escaped_separator: bool = False


@dataclass(frozen=True)
class MarkdownLinkSyntax:
    """
    Markdown link: its text between brackets, then its destination and title between parentheses.

    Attributes
    ----------
    text_opening, text_closing : str
        Characters around the text.
    destination_opening, destination_closing : str
        Characters around the destination and the title.
    destination_brackets : tuple[str, str]
        Characters around a destination that holds spaces.
    title_delimiters : dict[str, str]
        Closing character of a title, by its opening character.
    """

    text_opening: str
    text_closing: str
    destination_opening: str
    destination_closing: str
    destination_brackets: tuple[str, str]
    title_delimiters: dict[str, str]


@dataclass(frozen=True)
class LinkSyntax:
    """Links: Markdown links, wikilinks, and the prefix that turns either into an embed."""

    markdown: MarkdownLinkSyntax | None
    wikilink: WikilinkSyntax | None
    embed_prefix: str | None
    embeds_in_text: bool


@dataclass(frozen=True)
class EscapeSyntax:
    """Escape: `character` followed by one of the `escapable` characters."""

    character: str
    escapable: frozenset[str]


# One attribute per construct of the dialect, each None when the dialect disables it.
@dataclass(frozen=True)
class MarkdownSyntax:  # pylint: disable=too-many-instance-attributes
    """
    Complete syntax of a Markdown dialect.

    Attributes
    ----------
    name : str
        Name of the dialect.
    tab_width : int
        Columns between two tab stops, for the indentation of blocks.
    block_indent : int
        Columns of indentation admitted before the marker of a block.
    frontmatter, fences, indented_code, headings, quotations, lists, thematic_breaks, math, links,
    escape : section or None
        Syntax of each construct, None when the dialect disables it.
    code_span : str | None
        Character whose runs delimit a code span.
    code_span_shorter_closing : bool
        Whether, when no run of the width of the opening run follows it, the first narrower run
        closes a code span, the excess characters of the opening run staying literal.
    code_span_over_links : bool
        Whether a code span crossing the text of a link prevails over the link, as in CommonMark;
        otherwise the link prevails. A code span inside the text holds its brackets either way.
    setext_underlines : tuple[str, ...]
        Characters whose run under a paragraph closes it as a heading of another style.
    """

    name: str
    tab_width: int
    block_indent: int
    frontmatter: FrontmatterSyntax | None
    fences: FenceSyntax | None
    indented_code: IndentedCodeSyntax | None
    headings: HeadingSyntax | None
    quotations: QuotationSyntax | None
    lists: ListSyntax | None
    thematic_breaks: ThematicBreakSyntax | None
    setext_underlines: tuple[str, ...]
    code_span: str | None
    code_span_shorter_closing: bool
    code_span_over_links: bool
    math: MathSyntax | None
    links: LinkSyntax | None
    escape: EscapeSyntax | None


def _required_character(fields: Fields, key: str, name: str) -> str:
    """Read a single character that the section requires."""
    character = fields.character(key)
    if character is None:
        raise SyntaxFileError(f"{name}: {key}: expected a single character")
    return character


def _pair(fields: Fields, key: str, name: str) -> tuple[str, str]:
    """Read a list of exactly two single characters: an opening and a closing one."""
    pair = fields.characters(key)
    if len(pair) != 2:
        raise SyntaxFileError(f"{name}: {key}: expected an opening and a closing character")
    return pair[0], pair[1]


def _callout(fields: Fields | None, name: str) -> CalloutSyntax | None:
    """Parse the callout section of a quotation, or None when it is disabled."""
    if fields is None:
        return None
    pattern = fields.string("type_pattern")
    try:
        compiled = re.compile(pattern)
    except re.error as error:
        raise SyntaxFileError(
            f"{name}: invalid callout type_pattern {pattern!r}: {error}"
        ) from error
    callout = CalloutSyntax(
        opening=fields.string("opening"),
        closing=fields.string("closing"),
        type_pattern=compiled,
        fold_signs=fields.characters("fold_signs"),
    )
    fields.finish()
    return callout


def _math(fields: Fields | None) -> MathSyntax | None:
    """Parse the math section, or None when mathematics is disabled."""
    if fields is None:
        return None
    math = MathSyntax(
        display=fields.optional_string("display"),
        inline=fields.optional_string("inline"),
        inline_spans_lines=fields.boolean("inline_spans_lines"),
        display_spans_blank_lines=fields.boolean("display_spans_blank_lines"),
        display_unclosed_runs_to_end=fields.boolean("display_unclosed_runs_to_end"),
    )
    fields.finish()
    return math


def _markdown_links(fields: Fields | None, name: str) -> MarkdownLinkSyntax | None:
    """Parse the Markdown-link section, or None when Markdown links are disabled."""
    if fields is None:
        return None
    titles = dict(_split_title(pair, name) for pair in fields.strings("title_delimiters"))
    links = MarkdownLinkSyntax(
        text_opening=_required_character(fields, "text_opening", name),
        text_closing=_required_character(fields, "text_closing", name),
        destination_opening=_required_character(fields, "destination_opening", name),
        destination_closing=_required_character(fields, "destination_closing", name),
        destination_brackets=_pair(fields, "destination_brackets", name),
        title_delimiters=titles,
    )
    fields.finish()
    return links


def _split_title(pair: str, name: str) -> tuple[str, str]:
    """Split a title delimiter written as two characters, its opening and its closing one."""
    if len(pair) != 2:
        raise SyntaxFileError(f"{name}: title_delimiters: expected pairs of two characters")
    return pair[0], pair[1]


def _links(fields: Fields | None, name: str) -> LinkSyntax | None:
    """Parse the links section, or None when links are disabled."""
    if fields is None:
        return None
    wiki_fields = fields.section("wikilink")
    wikilink = None
    if wiki_fields is not None:
        wikilink = WikilinkSyntax(
            opening=wiki_fields.string("opening"),
            closing=wiki_fields.string("closing"),
            alias_separator=wiki_fields.string("alias_separator"),
            excluded=wiki_fields.optional_string("excluded") or "",
            escaped_separator=wiki_fields.boolean("escaped_separator"),
        )
        wiki_fields.finish()
    links = LinkSyntax(
        markdown=_markdown_links(fields.section("markdown"), name),
        wikilink=wikilink,
        embed_prefix=fields.optional_string("embed_prefix"),
        embeds_in_text=fields.boolean("embeds_in_text"),
    )
    fields.finish()
    return links


def _frontmatter(section: Fields | None) -> FrontmatterSyntax | None:
    """Parse the frontmatter section, or None when frontmatter is disabled."""
    if section is None:
        return None
    parsed = FrontmatterSyntax(fence=section.string("fence"))
    section.finish()
    return parsed


def _fences(section: Fields | None) -> FenceSyntax | None:
    """Parse the fences section, or None when fenced code is disabled."""
    if section is None:
        return None
    parsed = FenceSyntax(
        characters=section.characters("characters"),
        minimum_length=section.integer("minimum_length", minimum=1),
        info_excludes_fence=frozenset(section.characters("info_excludes_fence")),
    )
    section.finish()
    return parsed


def _indented_code(section: Fields | None) -> IndentedCodeSyntax | None:
    """Parse the indented-code section, or None when indented code is disabled."""
    if section is None:
        return None
    parsed = IndentedCodeSyntax(indent=section.integer("indent", minimum=1))
    section.finish()
    return parsed


def _headings(section: Fields | None, name: str) -> HeadingSyntax | None:
    """Parse the headings section, or None when headings are disabled."""
    if section is None:
        return None
    parsed = HeadingSyntax(
        marker=_required_character(section, "marker", name),
        maximum_level=section.integer("maximum_level", minimum=1),
    )
    section.finish()
    return parsed


def _quotations(section: Fields | None, name: str) -> QuotationSyntax | None:
    """Parse the quotations section, or None when quotations are disabled."""
    if section is None:
        return None
    parsed = QuotationSyntax(
        marker=_required_character(section, "marker", name),
        spacing=section.integer("spacing"),
        callout=_callout(section.section("callout"), name),
    )
    section.finish()
    return parsed


def _lists(section: Fields | None) -> ListSyntax | None:
    """Parse the lists section, or None when lists are disabled."""
    if section is None:
        return None
    parsed = ListSyntax(
        bullets=section.characters("bullets"),
        ordered_delimiters=section.characters("ordered_delimiters"),
        maximum_digits=section.integer("maximum_digits"),
        maximum_spacing=section.integer("maximum_spacing", minimum=1),
    )
    section.finish()
    return parsed


def _thematic_breaks(section: Fields | None) -> ThematicBreakSyntax | None:
    """Parse the thematic-breaks section, or None when thematic breaks are disabled."""
    if section is None:
        return None
    parsed = ThematicBreakSyntax(
        characters=section.characters("characters"),
        minimum_count=section.integer("minimum_count", minimum=1),
    )
    section.finish()
    return parsed


def _escape(section: Fields | None, name: str) -> EscapeSyntax | None:
    """Parse the escape section, or None when escapes are disabled."""
    if section is None:
        return None
    parsed = EscapeSyntax(
        character=_required_character(section, "character", name),
        escapable=frozenset(section.string("escapable")),
    )
    section.finish()
    return parsed


def parse_markdown_syntax(name: str, fields: Fields) -> MarkdownSyntax:
    """
    Parse the body of a Markdown syntax file.

    Parameters
    ----------
    name : str
        Name of the syntax, from the header of its file.
    fields : Fields
        Reader of the body of the file.

    Returns
    -------
    MarkdownSyntax
        Typed syntax of the dialect.

    Raises
    ------
    SyntaxFileError
        If a key is missing, unknown, or holds a value of the wrong type.
    """
    syntax = MarkdownSyntax(
        name=name,
        tab_width=fields.integer("tab_width", minimum=1),
        block_indent=fields.integer("block_indent"),
        frontmatter=_frontmatter(fields.section("frontmatter")),
        fences=_fences(fields.section("fences")),
        indented_code=_indented_code(fields.section("indented_code")),
        headings=_headings(fields.section("headings"), name),
        quotations=_quotations(fields.section("quotations"), name),
        lists=_lists(fields.section("lists")),
        thematic_breaks=_thematic_breaks(fields.section("thematic_breaks")),
        setext_underlines=fields.characters("setext_underlines"),
        code_span=fields.character("code_span"),
        code_span_shorter_closing=fields.boolean("code_span_shorter_closing"),
        code_span_over_links=fields.boolean("code_span_over_links"),
        math=_math(fields.section("math")),
        links=_links(fields.section("links"), name),
        escape=_escape(fields.section("escape"), name),
    )
    fields.finish()
    return syntax

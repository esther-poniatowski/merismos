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
    """Fenced code: a run of one fence character, at least `minimum_length` long."""

    characters: tuple[str, ...]
    minimum_length: int


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
    """Quotation opened by `marker` on each line, possibly a callout."""

    marker: str
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


@dataclass(frozen=True)
class WikilinkSyntax:
    """Wikilink: `opening`, a destination, an optional alias after `alias_separator`, `closing`."""

    opening: str
    closing: str
    alias_separator: str


@dataclass(frozen=True)
class LinkSyntax:
    """Links: Markdown links, wikilinks, and the prefix that turns either into an embed."""

    markdown: bool
    wikilink: WikilinkSyntax | None
    embed_prefix: str | None


@dataclass(frozen=True)
class EscapeSyntax:
    """Escape: `character` followed by one of the `escapable` characters."""

    character: str
    escapable: frozenset[str]


@dataclass(frozen=True)
# One attribute per construct of the dialect, each None when the dialect disables it.
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
    math: MathSyntax | None
    links: LinkSyntax | None
    escape: EscapeSyntax | None


def _callout(fields: Fields | None) -> CalloutSyntax | None:
    """Parse the callout section of a quotation, or None when it is disabled."""
    if fields is None:
        return None
    pattern = fields.string("type_pattern")
    try:
        compiled = re.compile(pattern)
    except re.error as error:
        raise SyntaxFileError(f"invalid callout type_pattern {pattern!r}: {error}") from error
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
    )
    fields.finish()
    return math


def _links(fields: Fields | None) -> LinkSyntax | None:
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
        )
        wiki_fields.finish()
    links = LinkSyntax(
        markdown=fields.boolean("markdown"),
        wikilink=wikilink,
        embed_prefix=fields.optional_string("embed_prefix"),
    )
    fields.finish()
    return links


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
    sections = {
        key: fields.section(key)
        for key in (
            "frontmatter",
            "fences",
            "indented_code",
            "headings",
            "quotations",
            "lists",
            "thematic_breaks",
            "math",
            "links",
            "escape",
        )
    }
    frontmatter = fences = indented = headings = quotations = lists = breaks = escape = None
    if (section := sections["frontmatter"]) is not None:
        frontmatter = FrontmatterSyntax(fence=section.string("fence"))
        section.finish()
    if (section := sections["fences"]) is not None:
        fences = FenceSyntax(
            characters=section.characters("characters"),
            minimum_length=section.integer("minimum_length", minimum=1),
        )
        section.finish()
    if (section := sections["indented_code"]) is not None:
        indented = IndentedCodeSyntax(indent=section.integer("indent", minimum=1))
        section.finish()
    if (section := sections["headings"]) is not None:
        headings = HeadingSyntax(
            marker=section.character("marker") or "",
            maximum_level=section.integer("maximum_level", minimum=1),
        )
        section.finish()
        if not headings.marker:
            raise SyntaxFileError(f"{name}: headings.marker: expected a single character")
    if (section := sections["quotations"]) is not None:
        quotations = QuotationSyntax(
            marker=section.character("marker") or "",
            callout=_callout(section.section("callout")),
        )
        section.finish()
        if not quotations.marker:
            raise SyntaxFileError(f"{name}: quotations.marker: expected a single character")
    if (section := sections["lists"]) is not None:
        lists = ListSyntax(
            bullets=section.characters("bullets"),
            ordered_delimiters=section.characters("ordered_delimiters"),
            maximum_digits=section.integer("maximum_digits"),
            maximum_spacing=section.integer("maximum_spacing", minimum=1),
        )
        section.finish()
    if (section := sections["thematic_breaks"]) is not None:
        breaks = ThematicBreakSyntax(
            characters=section.characters("characters"),
            minimum_count=section.integer("minimum_count", minimum=1),
        )
        section.finish()
    if (section := sections["escape"]) is not None:
        escape_character = section.character("character")
        if escape_character is None:
            raise SyntaxFileError(f"{name}: escape.character: expected a single character")
        escape = EscapeSyntax(
            character=escape_character,
            escapable=frozenset(section.string("escapable")),
        )
        section.finish()
    syntax = MarkdownSyntax(
        name=name,
        tab_width=fields.integer("tab_width", minimum=1),
        block_indent=fields.integer("block_indent"),
        frontmatter=frontmatter,
        fences=fences,
        indented_code=indented,
        headings=headings,
        quotations=quotations,
        lists=lists,
        thematic_breaks=breaks,
        setext_underlines=fields.characters("setext_underlines"),
        code_span=fields.character("code_span"),
        math=_math(sections["math"]),
        links=_links(sections["links"]),
        escape=escape,
    )
    fields.finish()
    return syntax

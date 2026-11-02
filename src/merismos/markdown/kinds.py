"""
Span kinds of a Markdown source, as the contract `merismos:span-kinds` names them.

Every other module refers to a kind through these constants, so that the names of the contract
are written once.
"""

FRONTMATTER = "frontmatter"
"""YAML block opening the source."""

FENCED_CODE = "fenced-code"
"""Fenced code block."""

INDENTED_CODE = "indented-code"
"""Code block written by indentation."""

INLINE_CODE = "inline-code"
"""Code span."""

DISPLAY_MATH = "display-math"
"""Mathematics delimited by the display delimiter."""

INLINE_MATH = "inline-math"
"""Mathematics delimited by the inline delimiter."""

HEADING = "heading"
"""Heading opened by a run of markers."""

QUOTATION = "quotation"
"""Block quote, a callout included."""

LINK = "link"
"""Markdown link or wikilink, an embed included."""

LINK_TEXT = "link-text"
"""Text displayed by a link."""

LINK_DESTINATION = "link-destination"
"""Destination of a link."""

MARKDOWN_KINDS = (
    FRONTMATTER,
    FENCED_CODE,
    INDENTED_CODE,
    INLINE_CODE,
    DISPLAY_MATH,
    INLINE_MATH,
    HEADING,
    QUOTATION,
    LINK,
    LINK_TEXT,
    LINK_DESTINATION,
)
"""Every kind of a Markdown source."""

OPAQUE_KINDS = frozenset(
    {
        FRONTMATTER,
        FENCED_CODE,
        INDENTED_CODE,
        INLINE_CODE,
        DISPLAY_MATH,
        INLINE_MATH,
        LINK_DESTINATION,
    }
)
"""Kinds whose content is never parsed, so that their regions are always leaves."""

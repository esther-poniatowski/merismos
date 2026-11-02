"""
Decoder of Python string literals, and the dedent of docstrings, keeping the source offset of
every decoded code point.

The literal decoder follows the escape rules of Python for text literals; the dedent follows
`inspect.cleandoc`. Both build traced texts, and the segmenter compares each result with the
value computed by Python itself.

Functions
---------
decode_literal(token, start) -> TracedText
    Decode one text literal, given its token and the offset of the token.
cleandoc(text, tab_size) -> TracedText
    Dedent a traced docstring as `inspect.cleandoc` dedents its value.
"""

import unicodedata

from ..errors import DecodingError
from .traced import TracedText

SIMPLE_ESCAPES = {
    "\\": "\\",
    "'": "'",
    '"': '"',
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}
"""Escapes of one character, each with the code point it produces."""

CODE_ESCAPES = {"x": 2, "u": 4, "U": 8}
"""Escapes followed by a hexadecimal code, with the number of digits."""

OCTAL_DIGITS = "01234567"
"""Digits of an octal escape, which takes at most three."""

QUOTES = "'\""
"""Characters opening a string literal after its prefix."""


def decode_literal(token: str, start: int) -> TracedText:
    """
    Decode one text literal, given its token and the offset of the token.

    A line ending of the source decodes to one line feed, as the tokenizer of Python reads it.

    Raises
    ------
    DecodingError
        If the token is not a text literal, or holds an invalid escape.

    Examples
    --------
    >>> decode_literal('"a\\\\tb"', 0).value
    'a\\tb'
    """
    quote_index = next(
        (index for index, character in enumerate(token) if character in QUOTES), None
    )
    if quote_index is None:
        raise DecodingError(f"not a string literal: {token!r}")
    prefix = token[:quote_index].lower()
    if "b" in prefix or "f" in prefix:
        raise DecodingError(f"not a plain text literal: {token!r}")
    quote = token[quote_index]
    width = 3 if token.startswith(quote * 3, quote_index) else 1
    body_start = quote_index + width
    body_end = len(token) - width
    return _decode_body(token, body_start, body_end, start, raw="r" in prefix)


def _decode_body(token: str, position: int, end: int, start: int, raw: bool) -> TracedText:
    """Decode the body of a literal between two positions of its token."""
    text = TracedText()
    while position < end:
        character = token[position]
        if character == "\r":
            # The tokenizer reads a carriage return, alone or before a line feed, as a line feed.
            text.produce("\n", start + position)
            position += 2 if token.startswith("\r\n", position) else 1
        elif character == "\\" and not raw:
            position = _escape(token, position, end, start, text)
        elif character == "\\" and raw and position + 1 < end:
            # A raw literal keeps a backslash and the character it protects.
            text.copy(token[position : position + 2], start + position)
            position += 2
        else:
            text.copy(character, start + position)
            position += 1
    return text


def _escape(token: str, position: int, end: int, start: int, text: TracedText) -> int:
    """Decode the escape at `position`, at its backslash, returning the position after it."""
    if position + 1 >= end:
        raise DecodingError(f"dangling backslash at offset {start + position}")
    character = token[position + 1]
    origin = start + position
    if character in "\r\n":
        # A backslash before a line ending continues the literal on the next line.
        return position + (3 if token.startswith("\r\n", position + 1) else 2)
    if character in SIMPLE_ESCAPES:
        text.produce(SIMPLE_ESCAPES[character], origin)
        return position + 2
    if character in OCTAL_DIGITS:
        stop = position + 1
        while stop < min(end, position + 4) and token[stop] in OCTAL_DIGITS:
            stop += 1
        text.produce(chr(int(token[position + 1 : stop], 8)), origin)
        return stop
    if character in CODE_ESCAPES:
        stop = position + 2 + CODE_ESCAPES[character]
        try:
            text.produce(chr(int(token[position + 2 : stop], 16)), origin)
        except ValueError as error:
            raise DecodingError(f"invalid escape at offset {origin}") from error
        return stop
    if character == "N" and position + 2 < end and token[position + 2] == "{":
        close = token.find("}", position + 3, end)
        if close == -1:
            raise DecodingError(f"unclosed named escape at offset {origin}")
        try:
            text.produce(unicodedata.lookup(token[position + 3 : close]), origin)
        except KeyError as error:
            raise DecodingError(f"unknown character name at offset {origin}") from error
        return close + 1
    # An unknown escape keeps its backslash, as Python does with a warning.
    text.copy(token[position : position + 2], origin)
    return position + 2


def _split_lines(text: TracedText) -> list[TracedText]:
    """Split a traced text at its line feeds, the line feeds left out."""
    lines: list[TracedText] = []
    start = 0
    for index, character in enumerate(text.characters):
        if character == "\n":
            lines.append(text.slice(start, index))
            start = index + 1
    lines.append(text.slice(start, len(text)))
    return lines


def _expand_tabs(text: TracedText, tab_size: int) -> TracedText:
    """Expand the tabs of a traced text as `str.expandtabs` does, each space traced to its tab."""
    expanded = TracedText()
    column = 0
    for character, origin in zip(text.characters, text.origins):
        if character == "\t":
            width = tab_size - column % tab_size
            expanded.produce(" " * width, origin)
            column += width
        else:
            expanded.characters.append(character)
            expanded.origins.append(origin)
            column = 0 if character in "\n\r" else column + 1
    return expanded


def cleandoc(text: TracedText, tab_size: int) -> TracedText:
    """
    Dedent a traced docstring as `inspect.cleandoc` dedents its value.

    The first line loses its leading whitespace, every later line loses the common margin of the
    later lines holding text, and the empty lines opening or closing the docstring are removed.
    """
    lines = _split_lines(_expand_tabs(text, tab_size))
    margins = [
        len(line.value) - len(line.value.lstrip()) for line in lines[1:] if line.value.lstrip()
    ]
    margin = min(margins) if margins else 0
    first = lines[0]
    lines[0] = first.slice(len(first.value) - len(first.value.lstrip()), len(first))
    lines[1:] = [line.slice(margin, len(line)) for line in lines[1:]]
    while lines and not lines[-1].value:
        lines.pop()
    while lines and not lines[0].value:
        lines.pop(0)
    joined = TracedText()
    for index, line in enumerate(lines):
        if index:
            joined.produce("\n")
        joined.extend(line)
    return joined

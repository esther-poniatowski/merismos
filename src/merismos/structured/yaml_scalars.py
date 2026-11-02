"""
Decoder of YAML scalars that keeps the source offset of every decoded code point.

The decoder follows the scalar rules of the PyYAML scanner for the five styles: plain, single
quoted, double quoted, literal and folded. It reads the source from the start of a scalar and
records, for each decoded code point, the offset it was copied from, or the offset of the
construct that produced it, such as a folded line break or an escape. The segmenter compares
the result with the value read by PyYAML, so that a disagreement fails instead of yielding wrong
offsets.

Classes
-------
ScalarDecoder
    Decoder of the scalars of one YAML source.
"""

from ..errors import DecodingError
from .traced import TracedText

LINE_BREAKS = "\r\n\x85  "
"""Characters that break a line in YAML."""

END = "\0"
"""Character read past the end of the source."""

ESCAPE_REPLACEMENTS = {
    "0": "\0",
    "a": "\x07",
    "b": "\x08",
    "t": "\x09",
    "\t": "\x09",
    "n": "\x0a",
    "v": "\x0b",
    "f": "\x0c",
    "r": "\x0d",
    "e": "\x1b",
    " ": " ",
    '"': '"',
    "/": "/",
    "\\": "\\",
    "N": "\x85",
    "_": "\xa0",
    "L": " ",
    "P": " ",
}
"""Single-character escapes of a double-quoted scalar, each with the code point it produces."""

ESCAPE_CODES = {"x": 2, "u": 4, "U": 8}
"""Escapes of a double-quoted scalar followed by a hexadecimal code, with the number of digits."""

CHOMPING_INDICATORS = {"+": True, "-": False}
"""Chomping indicators of a block scalar: keep every final line break, or strip them all."""


class ScalarDecoder:
    """
    Decoder of the scalars of one YAML source.

    Parameters
    ----------
    source : str
        YAML source.
    """

    def __init__(self, source: str) -> None:
        self._source = source
        self._limit = len(source)
        self._line_starts = [0] + [
            index + 1 for index, character in enumerate(source) if character == "\n"
        ]

    # --- reading ------------------------------------------------------------------------------

    def _peek(self, position: int) -> str:
        """Return the character at `position`, or the end character past the scalar."""
        return self._source[position] if position < self._limit else END

    def _column(self, position: int) -> int:
        """Return the column of an offset, counted from the start of its line."""
        low, high = 0, len(self._line_starts) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if self._line_starts[middle] <= position:
                low = middle
            else:
                high = middle - 1
        return position - self._line_starts[low]

    def _line_break(self, position: int) -> tuple[str, int]:
        """Read a line break, returning its normalized form and the offset after it."""
        character = self._peek(position)
        if character in "\r\n\x85":
            width = 2 if self._source.startswith("\r\n", position) else 1
            return "\n", position + width
        if character in "  ":
            return character, position + 1
        return "", position

    # --- styles -------------------------------------------------------------------------------

    def decode(self, style: str | None, start: int, end: int, parent_indent: int) -> TracedText:
        """
        Decode the scalar starting at `start`.

        Parameters
        ----------
        style : str | None
            Style of the scalar as PyYAML reports it: None for plain, `'`, `"`, `|` or `>`.
        start : int
            Offset of the scalar, at its quote or its indicator for the quoted and block styles.
        end : int
            Offset after the scalar, as PyYAML reports it; the decoder reads nothing beyond it.
        parent_indent : int
            Column of the block collection holding the scalar, or -1 at the document level.

        Raises
        ------
        DecodingError
            If the style is unknown.
        """
        self._limit = min(end, len(self._source))
        if style is None:
            return self._plain(start)
        if style in ("'", '"'):
            return self._flow(start, double=style == '"')
        if style in ("|", ">"):
            return self._block(start, folded=style == ">", parent_indent=parent_indent)
        raise DecodingError(f"unknown scalar style {style!r}")

    def _plain(self, start: int) -> TracedText:
        """Decode a plain scalar: words, single spaces kept, line breaks folded."""
        text = TracedText()
        position = start
        while True:
            end = position
            while self._peek(end) not in END + " \t" + LINE_BREAKS:
                end += 1
            if end == position:
                return text
            text.copy(self._source[position:end], position)
            position = end
            spaces = self._plain_spaces(position)
            if spaces is None:
                return text
            produced, position = spaces
            if self._peek(position) in END + " \t#" + LINE_BREAKS:
                return text
            text.extend(produced)

    def _plain_spaces(self, position: int) -> tuple[TracedText, int] | None:
        """Read the spaces between two words of a plain scalar, folding its line breaks."""
        produced = TracedText()
        end = position
        while self._peek(end) == " ":
            end += 1
        if self._peek(end) not in LINE_BREAKS:
            if end == position:
                return None
            produced.copy(self._source[position:end], position)
            return produced, end
        break_position = end
        line_break, end = self._line_break(end)
        breaks: list[tuple[str, int]] = []
        while self._peek(end) in " " + LINE_BREAKS:
            if self._peek(end) == " ":
                end += 1
            else:
                breaks.append((self._line_break(end)[0], end))
                end = self._line_break(end)[1]
        if line_break != "\n":
            produced.produce(line_break, break_position)
        elif not breaks:
            produced.produce(" ", break_position)
        for character, origin in breaks:
            produced.produce(character, origin)
        return produced, end

    def _flow(self, start: int, double: bool) -> TracedText:
        """Decode a quoted scalar: escapes, doubled quotes, and folded line breaks."""
        quote = self._peek(start)
        text = TracedText()
        position = self._flow_non_spaces(start + 1, double, text)
        while self._peek(position) != quote:
            if self._peek(position) == END:
                raise DecodingError(f"unclosed quoted scalar at offset {start}")
            position = self._flow_spaces(position, text)
            position = self._flow_non_spaces(position, double, text)
        return text

    def _flow_non_spaces(self, position: int, double: bool, text: TracedText) -> int:
        """Read the characters of a quoted scalar up to its next space or quote."""
        while True:
            end = position
            while self._peek(end) not in "'\"\\" + END + " \t" + LINE_BREAKS:
                end += 1
            if end > position:
                text.copy(self._source[position:end], position)
                position = end
            character = self._peek(position)
            if not double and character == "'" and self._peek(position + 1) == "'":
                text.copy("'", position)
                position += 2
            elif (double and character == "'") or (not double and character in '"\\'):
                text.copy(character, position)
                position += 1
            elif double and character == "\\":
                position = self._escape(position, text)
            else:
                return position

    def _escape(self, position: int, text: TracedText) -> int:
        """Decode the escape of a double-quoted scalar at `position`, at its backslash."""
        character = self._peek(position + 1)
        if character in ESCAPE_REPLACEMENTS:
            text.produce(ESCAPE_REPLACEMENTS[character], position)
            return position + 2
        if character in ESCAPE_CODES:
            digits = self._source[position + 2 : position + 2 + ESCAPE_CODES[character]]
            try:
                text.produce(chr(int(digits, 16)), position)
            except ValueError as error:
                raise DecodingError(f"invalid escape at offset {position}") from error
            return position + 2 + ESCAPE_CODES[character]
        if character in LINE_BREAKS:
            # An escaped line break joins the lines without a space.
            return self._flow_breaks(self._line_break(position + 1)[1], text)
        raise DecodingError(f"unknown escape at offset {position}")

    def _flow_spaces(self, position: int, text: TracedText) -> int:
        """Read the spaces of a quoted scalar, folding its line breaks."""
        end = position
        while self._peek(end) in " \t":
            end += 1
        if self._peek(end) not in LINE_BREAKS:
            text.copy(self._source[position:end], position)
            return end
        break_position = end
        line_break, end = self._line_break(end)
        folded = TracedText()
        end = self._flow_breaks(end, folded)
        if line_break != "\n":
            text.produce(line_break, break_position)
        elif not folded:
            text.produce(" ", break_position)
        text.extend(folded)
        return end

    def _flow_breaks(self, position: int, text: TracedText) -> int:
        """Read the empty lines of a quoted scalar, each producing one line break."""
        while True:
            while self._peek(position) in " \t":
                position += 1
            if self._peek(position) not in LINE_BREAKS:
                return position
            line_break, after = self._line_break(position)
            text.produce(line_break, position)
            position = after

    def _block_layout(
        self, start: int, parent_indent: int
    ) -> tuple[int, bool | None, int, TracedText]:
        """
        Read the header and the leading empty lines of a block scalar.

        Returns
        -------
        tuple[int, bool | None, int, TracedText]
            Offset of the first content line, chomping, indentation of the content, and the line
            breaks of the leading empty lines.
        """
        position, chomping, increment = self._block_header(start + 1)
        minimum = max(parent_indent + 1, 1)
        breaks = TracedText()
        if increment is None:
            position, maximum = self._block_indentation(position, breaks)
            indent = max(minimum, maximum)
        else:
            indent = minimum + increment - 1
            position = self._block_breaks(position, indent, breaks)
        return position, chomping, indent, breaks

    def _block(self, start: int, folded: bool, parent_indent: int) -> TracedText:
        """Decode a literal or folded block scalar, with its chomping."""
        position, chomping, indent, breaks = self._block_layout(start, parent_indent)
        text = TracedText()
        line_break = ""
        break_position = position
        while self._column(position) == indent and self._peek(position) != END:
            text.extend(breaks)
            leading_non_space = self._peek(position) not in " \t"
            end = position
            while self._peek(end) not in END + LINE_BREAKS:
                end += 1
            text.copy(self._source[position:end], position)
            break_position = end
            line_break, position = self._line_break(end)
            breaks = TracedText()
            position = self._block_breaks(position, indent, breaks)
            if not (self._column(position) == indent and self._peek(position) != END):
                break
            if (
                folded
                and line_break == "\n"
                and leading_non_space
                and self._peek(position) not in " \t"
            ):
                if not breaks:
                    text.produce(" ", break_position)
            else:
                text.produce(line_break, break_position)
        if chomping is not False:
            text.produce(line_break, break_position)
        if chomping is True:
            text.extend(breaks)
        return text

    def _block_header(self, position: int) -> tuple[int, bool | None, int | None]:
        """Read the indicators of a block scalar and the rest of its first line."""
        chomping: bool | None = None
        increment: int | None = None
        for _ in range(2):
            character = self._peek(position)
            if character in CHOMPING_INDICATORS and chomping is None:
                chomping = CHOMPING_INDICATORS[character]
                position += 1
            elif character.isdigit() and increment is None:
                increment = int(character)
                position += 1
        while self._peek(position) == " ":
            position += 1
        if self._peek(position) == "#":
            while self._peek(position) not in END + LINE_BREAKS:
                position += 1
        return self._line_break(position)[1], chomping, increment

    def _block_indentation(self, position: int, breaks: TracedText) -> tuple[int, int]:
        """Read the leading empty lines of a block scalar, measuring its deepest indentation."""
        maximum = 0
        while self._peek(position) in " " + LINE_BREAKS:
            if self._peek(position) != " ":
                line_break, after = self._line_break(position)
                breaks.produce(line_break, position)
                position = after
            else:
                position += 1
                maximum = max(maximum, self._column(position))
        return position, maximum

    def _block_breaks(self, position: int, indent: int, breaks: TracedText) -> int:
        """Read the empty lines inside a block scalar, each producing one line break."""
        while self._column(position) < indent and self._peek(position) == " ":
            position += 1
        while self._peek(position) in LINE_BREAKS:
            line_break, after = self._line_break(position)
            breaks.produce(line_break, position)
            position = after
            while self._column(position) < indent and self._peek(position) == " ":
                position += 1
        return position

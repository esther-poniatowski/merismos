"""
Lines of a source and the indentation of their content, measured in columns.

Classes
-------
Line
    Offsets of one line of a source.
Cursor
    Position in a line, with the column that it reaches.

Functions
---------
split_lines(source) -> tuple[Line, ...]
    Split a source into lines, keeping the offsets of their endings.
"""

from dataclasses import dataclass

LINE_ENDINGS = ("\r\n", "\n", "\r")
"""Line endings recognized in a source, the two-character ending first so that it wins."""

INDENT_CHARACTERS = frozenset(" \t")
"""Characters that indent the content of a line."""


@dataclass(frozen=True)
class Line:
    """
    Offsets of one line of a source.

    Attributes
    ----------
    start : int
        Offset of the first code point of the line.
    end : int
        Offset of the line ending, or of the end of the source for a last line without ending.
    next : int
        Offset of the line that follows, after the line ending.
    """

    start: int
    end: int
    next: int


def split_lines(source: str) -> tuple[Line, ...]:
    """
    Split a source into lines, keeping the offsets of their endings.

    A source ending with a line ending holds no empty last line.

    Examples
    --------
    >>> [(line.start, line.end, line.next) for line in split_lines("a\\r\\nbc\\nd")]
    [(0, 1, 3), (3, 5, 6), (6, 7, 7)]
    """
    lines: list[Line] = []
    start = 0
    position = 0
    length = len(source)
    while position < length:
        character = source[position]
        if character in "\r\n":
            width = 2 if source.startswith("\r\n", position) else 1
            lines.append(Line(start, position, position + width))
            position += width
            start = position
        else:
            position += 1
    if start < length:
        lines.append(Line(start, length, length))
    return tuple(lines)


@dataclass(frozen=True)
class Cursor:
    """
    Position in a line, with the column that it reaches.

    Columns count from the start of the line, a tab advancing to the next tab stop, so that the
    indentation of a line is measured independently of the prefixes already consumed.

    Attributes
    ----------
    position : int
        Offset in the source.
    column : int
        Column reached at that offset.
    """

    position: int
    column: int

    def indentation(self, source: str, end: int, tab_width: int) -> tuple[int, "Cursor"]:
        """
        Measure the indentation that follows the cursor.

        Returns
        -------
        tuple[int, Cursor]
            Columns of indentation, and the cursor on the first character after it.
        """
        cursor = self
        while cursor.position < end and source[cursor.position] in INDENT_CHARACTERS:
            cursor = cursor.advance(source, tab_width)
        return cursor.column - self.column, cursor

    def advance(self, source: str, tab_width: int) -> "Cursor":
        """Move past one character, a tab reaching the next tab stop."""
        if source[self.position] == "\t":
            column = (self.column // tab_width + 1) * tab_width
        else:
            column = self.column + 1
        return Cursor(self.position + 1, column)

    def consume_columns(
        self, source: str, end: int, columns: int, tab_width: int
    ) -> "Cursor | None":
        """
        Consume indentation until the cursor reaches `columns` more columns.

        A tab crossing the target column is consumed whole.

        Returns
        -------
        Cursor | None
            Cursor after the consumed indentation, or None when the line holds less indentation.
        """
        target = self.column + columns
        cursor = self
        while cursor.column < target:
            if cursor.position >= end or source[cursor.position] not in INDENT_CHARACTERS:
                return None
            cursor = cursor.advance(source, tab_width)
        return cursor


def is_blank(source: str, start: int, end: int) -> bool:
    """Whether the text between two offsets holds only indentation."""
    return all(character in INDENT_CHARACTERS for character in source[start:end])

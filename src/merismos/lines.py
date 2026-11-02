"""
Lines of a source and the indentation of their content, measured in columns.

Each format breaks its lines at its own set of endings: Markdown, Python and commit messages at
a line feed, a carriage return or both, YAML also at the Unicode line and paragraph separators.
The functions of this module take that set from their caller.

Classes
-------
Line
    Offsets of one line of a source.
Cursor
    Position in a line, with the column that it reaches.

Functions
---------
split_lines(source, endings) -> tuple[Line, ...]
    Split a source into lines, keeping the offsets of their endings.
line_starts(source, endings) -> list[int]
    Offsets of the first code point of each line.
ending_width(source, position, endings) -> int
    Width of the line ending at an offset, or 0.
is_blank(source, start, end) -> bool
    Whether the text between two offsets holds only indentation.
"""

from dataclasses import dataclass

LINE_ENDINGS = ("\r\n", "\n", "\r")
"""Line endings of Markdown, Python and commit messages, the two-character ending first."""

YAML_LINE_ENDINGS = LINE_ENDINGS + ("\x85", "\u2028", "\u2029")
"""Line endings of YAML, which also breaks at the next-line and the Unicode separators."""

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


def ending_width(source: str, position: int, endings: tuple[str, ...] = LINE_ENDINGS) -> int:
    """Width of the line ending starting at `position`, or 0 when none starts there."""
    for ending in endings:
        if source.startswith(ending, position):
            return len(ending)
    return 0


def split_lines(source: str, endings: tuple[str, ...] = LINE_ENDINGS) -> tuple[Line, ...]:
    """
    Split a source into lines, keeping the offsets of their endings.

    A source ending with a line ending holds no empty last line. The endings are tried in order,
    so a longer ending sharing its first character with a shorter one comes first.

    Examples
    --------
    >>> [(line.start, line.end, line.next) for line in split_lines("a\\r\\nbc\\rd")]
    [(0, 1, 3), (3, 5, 6), (6, 7, 7)]
    """
    first_characters = frozenset(ending[0] for ending in endings)
    lines: list[Line] = []
    start = 0
    position = 0
    length = len(source)
    while position < length:
        width = (
            ending_width(source, position, endings) if source[position] in first_characters else 0
        )
        if width:
            lines.append(Line(start, position, position + width))
            position += width
            start = position
        else:
            position += 1
    if start < length:
        lines.append(Line(start, length, length))
    return tuple(lines)


def line_starts(source: str, endings: tuple[str, ...] = LINE_ENDINGS) -> list[int]:
    """
    Offsets of the first code point of each line, a final line after a last ending included.

    Examples
    --------
    >>> line_starts("a\\rb\\n")
    [0, 2, 4]
    """
    starts = [0]
    for line in split_lines(source, endings):
        if line.next > line.end:
            starts.append(line.next)
    return starts


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

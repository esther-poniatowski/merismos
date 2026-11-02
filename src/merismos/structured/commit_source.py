"""
Segmenter of commit messages: the subject and the body, without comment lines and trailers.

The syntax fixes the cleanup that the message undergoes before it is read, as the cleanup mode
of Git does: the character opening a comment line, whether trailing whitespace is removed, and
whether runs of blank lines collapse into one. It also fixes the extent of the subject and the
form of a trailer line.

Classes
-------
CommitSyntax
    Cleanup, subject and trailers of a commit message.
CommitSegmenter
    Segmenter of commit messages under one syntax.

Functions
---------
parse_commit_syntax(name, fields) -> CommitSyntax
    Parse the body of a commit syntax file.
"""

from dataclasses import dataclass
from enum import Enum
import re

from ..errors import SyntaxFileError
from ..lines import Line, split_lines
from ..model import Region, Segmentation, Span
from ..syntax import Fields
from . import kinds
from .base import StructuredSegmenter
from .traced import TracedText


class SubjectExtent(Enum):
    """Extent of a subject: the first paragraph, as Git reads it, or the first line only."""

    FIRST_PARAGRAPH = "first-paragraph"
    FIRST_LINE = "first-line"


@dataclass(frozen=True)
class CommitSyntax:
    """
    Cleanup, subject and trailers of a commit message.

    Attributes
    ----------
    comment_character : str | None
        Character opening a comment line, or None when no line is a comment.
    strip_trailing_whitespace : bool
        Whether the whitespace ending a line is left out of the values.
    collapse_blank_lines : bool
        Whether a run of blank lines reads as one blank line.
    subject : SubjectExtent
        Extent of the subject.
    trailer : re.Pattern[str] | None
        Form of a trailer line, or None when no final paragraph is a block of trailers.
    scissors : re.Pattern[str] | None
        Form of the line cutting the message, as `git commit --verbose` writes it before the diff;
        the line and everything after it are left out. None when no line cuts the message.
    """

    comment_character: str | None
    strip_trailing_whitespace: bool
    collapse_blank_lines: bool
    subject: SubjectExtent
    trailer: re.Pattern[str] | None
    scissors: re.Pattern[str] | None


def parse_commit_syntax(name: str, fields: Fields) -> CommitSyntax:
    """Parse the body of a commit syntax file, rejecting unknown keys and values."""
    try:
        subject = SubjectExtent(fields.string("subject"))
    except ValueError as error:
        choices = ", ".join(member.value for member in SubjectExtent)
        raise SyntaxFileError(f"{name}: subject: expected one of {choices}") from error
    syntax = CommitSyntax(
        comment_character=fields.character("comment_character"),
        strip_trailing_whitespace=fields.boolean("strip_trailing_whitespace"),
        collapse_blank_lines=fields.boolean("collapse_blank_lines"),
        subject=subject,
        trailer=fields.pattern("trailer_pattern"),
        scissors=fields.pattern("scissors_pattern"),
    )
    fields.finish()
    return syntax


class CommitSegmenter(StructuredSegmenter[CommitSyntax]):
    """
    Segmenter of commit messages under one syntax.

    Parameters
    ----------
    syntax : CommitSyntax
        Cleanup, subject and trailers of a message.
    source_type : str
        Name of the source type reported in each segmentation.
    """

    kinds = frozenset(kinds.COMMIT_KINDS)
    """Kinds of the regions that the segmenter returns."""

    def segment(self, source: str) -> Segmentation:
        """Segment a commit message into its subject and its body."""
        lines = [line for line in self._uncut_lines(source) if not self._is_comment(source, line)]
        paragraphs = self._paragraphs(source, lines)
        regions: list[Region] = []
        if paragraphs:
            first, _ = paragraphs[0]
            subject = first if self._syntax.subject is SubjectExtent.FIRST_PARAGRAPH else first[:1]
            body = paragraphs[1:]
            if len(subject) < len(first):
                body = [(first[len(subject) :], 0)] + body
            if body and self._is_trailer_block(source, body[-1][0]):
                body = body[:-1]
            regions.append(self._region(kinds.COMMIT_SUBJECT, source, [(subject, 0)]))
            if body:
                regions.append(self._region(kinds.COMMIT_BODY, source, body))
        return self._segmentation(source, regions)

    def _uncut_lines(self, source: str) -> list[Line]:
        """The lines of a message before its scissors line, when the syntax declares one."""
        lines = list(split_lines(source))
        pattern = self._syntax.scissors
        if pattern is None:
            return lines
        for index, line in enumerate(lines):
            if pattern.fullmatch(source, line.start, line.end):
                return lines[:index]
        return lines

    def _is_comment(self, source: str, line: Line) -> bool:
        """Whether a line is a comment line, left out of every value."""
        character = self._syntax.comment_character
        return character is not None and source.startswith(character, line.start)

    def _text_end(self, source: str, line: Line) -> int:
        """End of the text of a line, its trailing whitespace left out when the syntax says so."""
        end = line.end
        if self._syntax.strip_trailing_whitespace:
            while end > line.start and source[end - 1] in " \t":
                end -= 1
        return end

    def _paragraphs(self, source: str, lines: list[Line]) -> list[tuple[list[Line], int]]:
        """Group the lines into paragraphs, each with the number of blank lines preceding it."""
        paragraphs: list[tuple[list[Line], int]] = []
        current: list[Line] = []
        blanks = 0
        for line in lines:
            if not source[line.start : line.end].strip(" \t"):
                if current:
                    paragraphs.append((current, blanks))
                    current, blanks = [], 0
                blanks += 1
            else:
                current.append(line)
        if current:
            paragraphs.append((current, blanks))
        return paragraphs

    def _is_trailer_block(self, source: str, paragraph: list[Line]) -> bool:
        """Whether a paragraph holds trailers only, a continuation line opening with a space."""
        pattern = self._syntax.trailer
        if pattern is None or pattern.match(source, paragraph[0].start, paragraph[0].end) is None:
            return False
        return all(
            pattern.match(source, line.start, line.end) is not None or source[line.start] in " \t"
            for line in paragraph
        )

    def _region(self, kind: str, source: str, paragraphs: list[tuple[list[Line], int]]) -> Region:
        """Build the region of paragraphs, joined by line breaks and their blank lines."""
        traced = TracedText()
        for index, (paragraph, blanks) in enumerate(paragraphs):
            if index:
                previous_end = paragraphs[index - 1][0][-1].end
                kept = 1 if self._syntax.collapse_blank_lines else max(blanks, 1)
                traced.produce("\n" * (1 + kept), previous_end)
            for line_index, line in enumerate(paragraph):
                if line_index:
                    traced.produce("\n", paragraph[line_index - 1].end)
                traced.copy(source[line.start : self._text_end(source, line)], line.start)
        last = paragraphs[-1][0][-1]
        span = Span(paragraphs[0][0][0].start, self._text_end(source, last))
        return Region(kind, span, string=traced.decoded(source))

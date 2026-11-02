"""
Traced text: a decoded string in which each code point records the source offset it came from.

Decoders build a traced text one part at a time, either copying source text or producing code
points of their own, such as a folded line break. The pieces of the contract are then derived
once: the maximal runs of code points copied verbatim from consecutive source offsets. Traced
texts compose, so a transformation applied after decoding, such as the dedent of a docstring,
keeps the map to the source.

Classes
-------
TracedText
    Decoded string with the source offset of each of its code points.
"""

from dataclasses import dataclass, field

from ..errors import DecodingError
from ..model import DecodedString, Piece


@dataclass
class TracedText:
    """
    Decoded string with the source offset of each of its code points.

    Attributes
    ----------
    characters : list[str]
        Code points of the decoded string.
    origins : list[int | None]
        Source offset of each code point, or None for a code point produced by decoding.

    Examples
    --------
    >>> text = TracedText()
    >>> text.copy("ab", 10)
    >>> text.produce(" ")
    >>> text.copy("c", 14)
    >>> [(piece.value_start, piece.source_start, piece.length)
    ...  for piece in text.decoded("..........ab..c").pieces]
    [(0, 10, 2), (3, 14, 1)]
    """

    characters: list[str] = field(default_factory=list)
    origins: list[int | None] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.characters)

    @property
    def value(self) -> str:
        """Decoded string."""
        return "".join(self.characters)

    def copy(self, text: str, source_start: int) -> None:
        """Append source text copied from `source_start`."""
        self.characters.extend(text)
        self.origins.extend(range(source_start, source_start + len(text)))

    def produce(self, text: str, origin: int | None = None) -> None:
        """Append code points produced by decoding, optionally attributed to one source offset."""
        self.characters.extend(text)
        self.origins.extend([origin] * len(text))

    def extend(self, other: "TracedText") -> None:
        """Append another traced text."""
        self.characters.extend(other.characters)
        self.origins.extend(other.origins)

    def slice(self, start: int, end: int) -> "TracedText":
        """Return the traced text of a range of positions."""
        return TracedText(self.characters[start:end], self.origins[start:end])

    def decoded(self, source: str, expected: str | None = None) -> DecodedString:
        """
        Derive the decoded string and its pieces, the runs copied verbatim from the source.

        Parameters
        ----------
        source : str
            Source the origins refer to.
        expected : str | None
            Value returned by the parser of the source format, compared with the decoded string.

        Raises
        ------
        DecodingError
            If the decoded string differs from the value of the parser.
        """
        value = self.value
        if expected is not None and value != expected:
            raise DecodingError(f"decoded {value!r}, while the parser reads {expected!r}")
        pieces: list[Piece] = []
        run_start: int | None = None
        for index, (character, origin) in enumerate(zip(self.characters, self.origins)):
            verbatim = origin is not None and origin < len(source) and source[origin] == character
            previous = self.origins[index - 1] if index else None
            continues = (
                verbatim
                and run_start is not None
                and previous is not None
                and origin == previous + 1
            )
            if continues:
                continue
            if run_start is not None:
                pieces.append(self._piece(run_start, index))
                run_start = None
            if verbatim:
                run_start = index
        if run_start is not None:
            pieces.append(self._piece(run_start, len(self.characters)))
        return DecodedString(value, tuple(pieces))

    def _piece(self, start: int, end: int) -> Piece:
        """Build the piece of a verbatim run between two positions."""
        origin = self.origins[start]
        assert origin is not None
        return Piece(start, origin, end - start)

"""
Observation vault: the conformance cases written as notes, for a reader to compare in Obsidian.

Obsidian documents its syntax by examples, so a case is settled by observing how Obsidian renders
its text. The vault holds one note per case, whose content is exactly the text of the case, and a
checklist stating the expected reading of each case: the kind of each region and the text of its
content. A reader opens each note in the reading view, compares it with its line of the checklist,
and records the version of Obsidian in the field `observed` of each case found to conform.

Functions
---------
expected_reading(case) -> list[str]
    State the expected regions of a case in words, one line per region.
export_vault(cases, folder, force) -> Path
    Write the notes of the cases and their checklist into a folder.
"""

from pathlib import Path
from typing import Sequence

from .conformance import Case
from .errors import MerismosError
from .serialization import region_from_data
from .text import content_view

CHECKLIST = "_checklist.md"
"""Name of the checklist note, sorted before the notes of the cases."""

NOTES = "cases"
"""Folder of the vault holding one note per case."""

EMPTY_VALUE = ""
"""Attribute value shown by `EMPTY`, such as the info string of a bare fence."""

EMPTY = '""'
"""Display of an empty attribute value, visible in the checklist."""


def expected_reading(case: Case) -> list[str]:
    """
    State the expected regions of a case in words, one line per region.

    Each line names the kind of a region, its attributes, and the text of its content, its gaps
    removed, or the text of its whole range for a kind without content.

    Examples
    --------
    >>> region = {"kind": "inline-math", "range": [4, 7], "content": [5, 6]}
    >>> case = Case("x", "markdown", None, None, "Let $x$.", (region,))
    >>> expected_reading(case)
    ['inline-math: `x`']
    """
    lines: list[str] = []
    for data in case.regions:
        region = region_from_data(data)
        if region.content is not None:
            text = content_view(case.text, region).text
        else:
            text = case.text[region.range.start : region.range.end]
        attributes = ", ".join(
            f"{name} {EMPTY if value == EMPTY_VALUE else value}"
            for name, value in region.attributes.items()
        )
        label = f"{region.kind} ({attributes})" if attributes else region.kind
        lines.append(f"{label}: `{_inline(text)}`")
    return lines


def _inline(text: str) -> str:
    """Show line breaks and backticks of a text visibly, so that it fits one line of a list."""
    return text.replace("\r", "\\r").replace("\n", "\\n").replace("`", "ˋ")


def export_vault(cases: Sequence[Case], folder: Path, force: bool = False) -> Path:
    """
    Write the notes of the cases and their checklist into a folder.

    The notes are derived from the cases and are replaced freely. The checklist is ticked by the
    reader, so an existing checklist is replaced only when `force` is set.

    Parameters
    ----------
    cases : Sequence[Case]
        Cases to observe, those of one source type read by Obsidian.
    folder : Path
        Folder of the vault, created when absent; existing notes of the same names are replaced.
    force : bool, default False
        Whether to replace an existing checklist.

    Returns
    -------
    Path
        Path of the checklist.

    Raises
    ------
    MerismosError
        If a case is not a Markdown case, which Obsidian cannot render, or if the checklist exists
        and `force` is not set; nothing is written in either case.
    """
    for case in cases:
        if case.source_type != "markdown":
            raise MerismosError(f"case {case.identifier}: only Markdown cases render in Obsidian")
    checklist = folder / CHECKLIST
    if checklist.exists() and not force:
        raise MerismosError(
            f"{checklist} exists and may hold ticked cases; replace it with --force"
        )
    notes = folder / NOTES
    notes.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    for case in cases:
        # The note holds the text alone, written without newline translation, so that its
        # frontmatter, its line endings and its first line are those of the case.
        with (notes / f"{case.identifier}.md").open("w", encoding="utf-8", newline="") as handle:
            handle.write(case.text)
        reading = expected_reading(case) or ["no region: the text renders as plain prose"]
        observed = f" — observed in {case.observed}" if case.observed else ""
        entries.append(f"- [ ] [[{NOTES}/{case.identifier}|{case.identifier}]]{observed}")
        if case.note:
            entries.append(f"    - {case.note}")
        entries.extend(f"    - {line}" for line in reading)
    checklist.write_text(
        "# Conformance cases to observe\n\n"
        "Open each case in the reading view, and tick it when Obsidian renders every region listed "
        "under it, and nothing else as code, mathematics, a heading, a quotation or a link. "
        "Record the version of Obsidian in the field `observed` of each ticked case.\n\n"
        + "\n".join(entries)
        + "\n",
        encoding="utf-8",
    )
    return checklist

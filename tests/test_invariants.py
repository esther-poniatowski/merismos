"""
Invariants of the contract on generated Markdown documents.

Each document joins fragments drawn with a fixed seed, so that a failure reproduces. The fragments
combine every construct with the containers and the delimiters that interact with it.
"""

import random

import pytest

from merismos import segment

FRAGMENTS = (
    "text",
    "$x$",
    "$$a+b$$",
    "`code $x$`",
    "``a`b``",
    "[t $y$](d.md)",
    "[[n|a $z$]]",
    "![[f.png]]",
    "\\$5",
    "$ 5",
    "# H $h$",
    "> ",
    "> > ",
    "- ",
    "1. ",
    "    ",
    "```\n",
    "~~~py\n",
    "---\n",
    "\n",
    "> [!tip] T\n",
    "[a`](b)`",
    "  ",
    "\t",
    "$$\n+ b\n> c\n$$",
    "\\`x`",
)
"""Fragments joined into documents, chosen to cross every construct with every container."""


def _document(seed: int) -> str:
    generator = random.Random(seed)
    lines = []
    for _ in range(generator.randint(1, 12)):
        line = "".join(generator.choice(FRAGMENTS) for _ in range(generator.randint(1, 5)))
        lines.append(line)
    return generator.choice(("\n", "\r\n", "\r")).join(lines)


@pytest.mark.parametrize("seed", range(400))
def test_generated_documents_form_a_forest(seed: int, assert_forest) -> None:
    """Every generated document segments into sorted, nested or disjoint regions."""
    assert_forest(segment(_document(seed), "markdown"))


@pytest.mark.parametrize("seed", range(50))
def test_segmentation_is_deterministic(seed: int) -> None:
    """Segmenting a source twice returns the same regions."""
    document = _document(seed)
    assert segment(document, "markdown") == segment(document, "markdown")


DELIMITED_KINDS = {"inline-math": "$", "inline-code": "`"}
"""Kinds whose content never holds an unescaped delimiter of their own width at its edges."""


@pytest.mark.parametrize("seed", range(200))
def test_contents_exclude_their_delimiters(seed: int) -> None:
    """The content of a delimited region starts and ends inside its delimiters."""
    document = _document(seed)
    segmentation = segment(document, "markdown")
    for region in segmentation.select(DELIMITED_KINDS):
        assert region.content is not None
        delimiter = DELIMITED_KINDS[region.kind]
        assert (
            document[region.range.start] == delimiter
            and document[region.range.end - 1] == delimiter
        )
        assert region.range.start < region.content.start <= region.content.end < region.range.end

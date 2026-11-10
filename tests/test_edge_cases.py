"""
Tests of the edge cases of each source type, of the extension points and of the bounds on cost.

The Markdown edge cases live in the conformance file, which every consumer reads; this module
holds the cases of the structured sources, of the API and of the command line.
"""

from pathlib import Path
import time

import pytest
from typer.testing import CliRunner

from merismos import (
    PackagedSyntax,
    Registry,
    Segmentation,
    SourceType,
    Span,
    default_registry,
    inline_regions,
    segment,
)
from merismos.cli import app
from merismos.conformance import load_cases
from merismos.errors import ConformanceFileError

# --- YAML ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value", "start"),
    [("b: &x hi\nc: *x\n", "hi", 6), ("a: !!str 3\n", "3", 9)],
    ids=["anchor", "tag"],
)
def test_yaml_properties_precede_the_scalar(text: str, value: str, start: int) -> None:
    """An anchor or a tag belongs to no value, and an alias adds no second region."""
    (region,) = segment(text, "yaml").regions
    assert region.string is not None and region.string.value == value
    assert region.range.start == start


def test_yaml_comment_on_a_block_header_is_kept() -> None:
    text = "a: | # header comment\n  text\n"
    comments = segment(text, "yaml").select(["yaml-comment"])
    assert [(region.range.start, region.range.end) for region in comments] == [(5, 21)]


def test_yaml_carriage_returns_break_lines() -> None:
    text = "a: x\rb: >\r  folded\r  line\r"
    values = [
        region.string.value
        for region in segment(text, "yaml").select(["yaml-value"])
        if region.string
    ]
    assert values == ["x", "folded line\n"]


def test_yaml_directive_comments_are_excluded() -> None:
    text = "# yaml-language-server: $schema=x\na: 1 # real\n"
    comments = segment(text, "yaml").select(["yaml-comment"])
    assert [region.string.value for region in comments if region.string] == [" real"]


# --- Python -------------------------------------------------------------------------------------


def test_python_carriage_returns_break_lines() -> None:
    text = 'def f():\r    """Doc\r    more."""\r    # c\r'
    regions = segment(text, "python").regions
    assert [region.string.value for region in regions if region.string] == ["Doc\nmore.", " c"]
    for region in regions:
        assert region.string is not None
        for piece in region.string.pieces:
            run = region.string.value[piece.value_start : piece.value_start + piece.length]
            assert run == text[piece.source_start : piece.source_start + piece.length]


def test_python_directive_comments_are_excluded() -> None:
    text = "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\nx = 1  # type: ignore\n# real\n"
    comments = segment(text, "python").select(["python-comment"])
    assert [region.string.value for region in comments if region.string] == [" real"]


def test_python_names_follow_qualname() -> None:
    text = 'def f():\n    def g():\n        """G."""\n    class C:\n        """C."""\n'
    names = [region.attributes["name"] for region in segment(text, "python").regions]
    assert names == ["f.<locals>.g", "f.<locals>.C"]


# --- commit messages ----------------------------------------------------------------------------


def test_commit_scissors_line_cuts_the_message() -> None:
    text = (
        "Subject\n\nBody\n# ------------------------ >8 ------------------------\ndiff --git a b\n"
    )
    body = segment(text, "commit").select(["commit-body"])
    assert [region.string.value for region in body if region.string] == ["Body"]


# --- API ----------------------------------------------------------------------------------------


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="inline-maht"):
        segment("$x$", "markdown").select(["inline-maht"])


def test_inline_regions_map_spans_of_a_foreign_parser() -> None:
    """A construct crossing two spans receives the text between them, after the ending, as a gap."""
    text = "> $$a\n> b$$ [c](d)\n"
    segmentation = inline_regions(text, [Span(2, 5), Span(8, 18)])
    math, link = segmentation.select(["display-math"])[0], segmentation.select(["link"])[0]
    assert (math.range, math.content, math.gaps) == (Span(2, 11), Span(4, 9), (Span(6, 8),))
    assert link.range == Span(12, 18)


def test_registered_default_syntax_may_have_any_suffix(tmp_path: Path) -> None:
    syntax = tmp_path / "plain.syntax"
    syntax.write_text("syntax_version: 1\nsource_type: plain\nname: plain\n", encoding="utf-8")

    class Whole:
        kinds = frozenset({"text"})

        def segment(self, source: str) -> Segmentation:
            return Segmentation(source, "plain", (), self.kinds)

    registry = Registry((), {})
    registry.register(SourceType("plain", lambda document, name: Whole()), default_syntax=syntax)
    assert isinstance(registry.segmenter("plain"), Whole)


def test_packaged_reference_is_typed() -> None:
    registry = Registry((), {"markdown": PackagedSyntax("markdown-obsidian")})
    assert registry.names() == ()


def test_edited_consumer_syntax_takes_effect(tmp_path: Path) -> None:
    """A syntax file of the consumer is read at each call, so an edit is never served stale."""
    packaged = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "merismos"
        / "syntaxes"
        / "markdown-obsidian.yml"
    )
    path = tmp_path / "syntax.yml"
    path.write_text(packaged.read_text(encoding="utf-8"), encoding="utf-8")
    assert len(segment("$x$", "markdown", syntax=path)) == 1
    path.write_text(
        packaged.read_text(encoding="utf-8").replace('inline: "$"', "inline: null"),
        encoding="utf-8",
    )
    assert len(segment("$x$", "markdown", syntax=path)) == 0


def test_shipped_types_agree_with_the_packaged_defaults() -> None:
    assert default_registry().names() == ("commit", "markdown", "python", "yaml")


# --- conformance files and command line ---------------------------------------------------------


def test_conformance_file_of_another_contract_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cases.yml"
    path.write_text("contract: other:kinds@1\ncases: []\n", encoding="utf-8")
    with pytest.raises(ConformanceFileError, match="other:kinds@1"):
        load_cases(path)


def test_cli_reports_an_invalid_source_without_traceback(tmp_path: Path) -> None:
    source = tmp_path / "bad.yml"
    source.write_text("a: [unclosed\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["segment", str(source), "--type", "yaml"])
    assert result.exit_code == 2
    assert "Traceback" not in result.output


# --- bounds on cost -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["[" * 20000, "`" * 2 + "x`" * 5000, "> " + "\n> ".join("`a` $b$" for _ in range(8000))],
    ids=["unmatched-brackets", "unmatched-backticks", "long-quotation"],
)
def test_pathological_sources_segment_quickly(text: str) -> None:
    """The scan stays near linear whatever the number of unmatched delimiters."""
    started = time.perf_counter()
    segment(text, "markdown")
    assert time.perf_counter() - started < 2.0


# --- observation in Obsidian --------------------------------------------------------------------


def test_observation_vault_holds_each_case_text_verbatim(tmp_path: Path) -> None:
    cases_file = Path(__file__).resolve().parent.parent / "specs" / "conformance" / "markdown.yml"
    vault = ["observe", str(cases_file), "--output-dir", str(tmp_path / "vault")]
    result = CliRunner().invoke(app, vault)
    assert result.exit_code == 0
    for case in load_cases(cases_file):
        note = tmp_path / "vault" / "cases" / f"{case.identifier}.md"
        assert note.read_bytes().decode("utf-8") == case.text
    checklist = (tmp_path / "vault" / "_checklist.md").read_text(encoding="utf-8")
    assert "- [ ] [[cases/inline-math-basic|inline-math-basic]]" in checklist
    assert "inline-math: `x_i`" in checklist


def test_observation_keeps_a_ticked_checklist_without_force(tmp_path: Path) -> None:
    """The checklist is ticked by the reader: replacing it needs --force; the notes are derived."""
    cases_file = Path(__file__).resolve().parent.parent / "specs" / "conformance" / "markdown.yml"
    vault = ["observe", str(cases_file), "--output-dir", str(tmp_path / "vault")]
    runner = CliRunner()
    assert runner.invoke(app, vault).exit_code == 0
    checklist = tmp_path / "vault" / "_checklist.md"
    checklist.write_text("- [x] ticked\n", encoding="utf-8")
    refused = runner.invoke(app, vault)
    assert refused.exit_code == 2
    assert str(checklist) in refused.output.replace("\n", "")
    assert checklist.read_text(encoding="utf-8") == "- [x] ticked\n"
    assert runner.invoke(app, [*vault, "--force"]).exit_code == 0
    assert "- [ ] [[cases/inline-math-basic|inline-math-basic]]" in checklist.read_text(
        encoding="utf-8"
    )


def test_observation_folder_is_no_longer_positional(tmp_path: Path) -> None:
    """The folder of the vault is named by --output-dir, without a positional alias."""
    cases_file = Path(__file__).resolve().parent.parent / "specs" / "conformance" / "markdown.yml"
    result = CliRunner().invoke(app, ["observe", str(cases_file), str(tmp_path / "vault")])
    assert result.exit_code == 2
    assert not (tmp_path / "vault").exists()

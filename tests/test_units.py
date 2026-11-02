"""Unit tests of the model, the syntax files, the registry, the text operations and the CLI."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from merismos import Region, Segmentation, Span, content_view, mask, segment
from merismos.cli import app
from merismos.errors import SyntaxFileError, UnknownSourceTypeError
from merismos.model import DecodedString, Piece
from merismos.registry import Registry, SourceType, default_registry
from merismos.serialization import region_from_data, region_to_data
from merismos.syntax import packaged_syntax_document, read_syntax_document

OBSIDIAN = packaged_syntax_document("markdown-obsidian")


def _syntax_file(tmp_path: Path, edit: dict[str, object]) -> Path:
    """Write the packaged Obsidian syntax with some top-level keys replaced."""
    import yaml

    resource = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "merismos"
        / "syntaxes"
        / "markdown-obsidian.yml"
    )
    data = yaml.safe_load(resource.read_text(encoding="utf-8"))
    data.update(edit)
    path = tmp_path / "syntax.yml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# --- model --------------------------------------------------------------------------------------


def test_span_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError):
        Span(3, 2)


def test_region_rejects_content_outside_range() -> None:
    with pytest.raises(ValueError):
        Region("inline-math", Span(0, 3), content=Span(1, 4))


def test_region_rejects_gap_outside_content() -> None:
    with pytest.raises(ValueError):
        Region("quotation", Span(0, 9), content=Span(2, 9), gaps=(Span(0, 2),))


def test_region_attributes_are_read_only() -> None:
    attributes = {"level": 1}
    region = Region("heading", Span(0, 3), Span(2, 3), attributes=attributes)
    attributes["level"] = 2
    assert region.attributes["level"] == 1
    with pytest.raises(TypeError):
        region.attributes["level"] = 3  # type: ignore[index]


def test_decoded_string_maps_synthesized_points_to_the_preceding_piece() -> None:
    decoded = DecodedString("ab\ncd", (Piece(0, 10, 2), Piece(3, 20, 2)))
    assert [decoded.to_source(offset) for offset in range(6)] == [10, 11, 12, 20, 21, 22]


# --- syntax files -------------------------------------------------------------------------------


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    path = _syntax_file(tmp_path, {"inline_mathematics": True})
    with pytest.raises(SyntaxFileError, match="inline_mathematics: unknown key"):
        default_registry().segmenter("markdown", path)


def test_wrong_type_names_its_key_path(tmp_path: Path) -> None:
    path = _syntax_file(
        tmp_path, {"math": {"display": "$$", "inline": "$", "inline_spans_lines": "no"}}
    )
    with pytest.raises(SyntaxFileError, match="math.inline_spans_lines"):
        default_registry().segmenter("markdown", path)


def test_wrong_version_is_rejected() -> None:
    with pytest.raises(SyntaxFileError, match="syntax_version"):
        read_syntax_document("syntax_version: 2\nsource_type: markdown\nname: x\n", "inline")


def test_null_section_disables_its_construct(tmp_path: Path) -> None:
    path = _syntax_file(tmp_path, {"math": None})
    regions = default_registry().segmenter("markdown", path).segment("Let $x$ vary.")
    assert len(regions) == 0


def test_custom_delimiter_needs_no_code(tmp_path: Path) -> None:
    path = _syntax_file(
        tmp_path, {"math": {"display": None, "inline": "%%", "inline_spans_lines": False}}
    )
    regions = default_registry().segmenter("markdown", path).segment("a %%x%% b")
    assert [(region.kind, region.range) for region in regions] == [("inline-math", Span(2, 7))]


def test_inline_math_may_span_lines_when_the_syntax_says_so(tmp_path: Path) -> None:
    math = {"display": "$$", "inline": "$", "inline_spans_lines": True}
    path = _syntax_file(tmp_path, {"math": math})
    regions = default_registry().segmenter("markdown", path).segment("$a\nb$")
    assert [region.kind for region in regions] == ["inline-math"]


# --- registry -----------------------------------------------------------------------------------


def test_unknown_source_type_names_the_known_ones() -> None:
    with pytest.raises(UnknownSourceTypeError, match="markdown"):
        default_registry().segmenter("latex")


def test_syntax_of_another_source_type_is_rejected(tmp_path: Path) -> None:
    path = _syntax_file(tmp_path, {"source_type": "commit"})
    with pytest.raises(SyntaxFileError, match="describes source type 'commit'"):
        default_registry().segmenter("markdown", path)


def test_a_consumer_registers_its_own_source_type(tmp_path: Path) -> None:
    class WholeText:
        def segment(self, source: str) -> Segmentation:
            return Segmentation(
                source, "plain", (Region("text", Span(0, len(source)), Span(0, len(source))),)
            )

    syntax = tmp_path / "plain.yml"
    syntax.write_text("syntax_version: 1\nsource_type: plain\nname: plain\n", encoding="utf-8")
    registry = Registry((), {})
    registry.register(
        SourceType("plain", lambda document, name: WholeText()), default_syntax=syntax
    )
    assert registry.names() == ("plain",)
    assert registry.segmenter("plain").segment("abc").regions[0].range == Span(0, 3)


# --- text operations ----------------------------------------------------------------------------


def test_mask_keeps_length_and_line_breaks() -> None:
    source = "> $$\r\n> a\r\n> $$"
    segmentation = segment(source, "markdown")
    masked = mask(source, segmentation.select(["display-math"]), fill="#")
    assert len(masked) == len(source)
    assert masked.count("\r\n") == source.count("\r\n")
    assert "$" not in masked


def test_mask_rejects_a_line_break_fill() -> None:
    with pytest.raises(ValueError):
        mask("abc", [], fill="\n")


def test_content_view_removes_the_gaps_of_a_callout() -> None:
    source = "> [!NOTE] Title\n> $$\n> a\n> $$\n"
    (math,) = segment(source, "markdown").select(["display-math"])
    view = content_view(source, math)
    assert view.text == "\na\n"
    assert [source[view.to_source(index)] for index in range(len(view.text))] == ["\n", "a", "\n"]


# --- serialization ------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["> [!tip] T\n> $a$ [[n|b]]\n", "- x\n  ```\n  y\n  ```\n"])
def test_regions_survive_a_round_trip(text: str) -> None:
    for region in segment(text, "markdown"):
        assert region_from_data(region_to_data(region)) == region


# --- command line -------------------------------------------------------------------------------


def test_cli_segment_prints_one_region_per_line(tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text("Let $x$ and `y`.\n", encoding="utf-8")
    result = CliRunner().invoke(
        app, ["segment", str(source), "--type", "markdown", "--kind", "inline-math"]
    )
    assert result.exit_code == 0
    assert result.output.strip() == '{"kind": "inline-math", "range": [4, 7], "content": [5, 6]}'


def test_cli_conform_fails_on_a_planted_mismatch(tmp_path: Path) -> None:
    cases = tmp_path / "cases.yml"
    cases.write_text(
        "cases:\n- id: wrong\n  source: markdown\n  observed: null\n  text: '$x$'\n  regions: []\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["conform", str(cases)])
    assert result.exit_code == 1
    assert "0 of 1 cases conform" in result.output


def test_cli_reports_an_unknown_source_type(tmp_path: Path) -> None:
    source = tmp_path / "note.tex"
    source.write_text("x", encoding="utf-8")
    result = CliRunner().invoke(app, ["segment", str(source), "--type", "latex"])
    assert result.exit_code == 2


def test_forest_checker_detects_overlap(assert_forest) -> None:
    """The invariant checker of the other tests fails on overlapping regions."""
    overlapping = Segmentation(
        "abcdef", "markdown", (Region("a", Span(0, 4)), Region("b", Span(2, 6)))
    )
    with pytest.raises(AssertionError):
        assert_forest(overlapping)


def test_obsidian_syntax_is_packaged() -> None:
    assert OBSIDIAN.source_type == "markdown" and OBSIDIAN.name == "obsidian"

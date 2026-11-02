"""
Command-line interface for the `merismos` package.

Defines commands available via `python -m merismos` or `merismos` if installed as a script.

Commands
--------
info : Display diagnostic information.
segment : Print the regions of a source as JSON.
conform : Check a segmenter against a conformance file.

See Also
--------
typer.Typer
    Library for building CLI applications: https://typer.tiangolo.com/
"""

import json
from pathlib import Path
from typing import Optional

import typer

from . import info, __version__
from .conformance import check_case, load_cases
from .errors import MerismosError
from .registry import default_registry
from .serialization import region_to_data

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("info")
def cli_info() -> None:
    """Display version and platform diagnostics."""
    typer.echo(info())


@app.command("segment")
def cli_segment(
    path: Path = typer.Argument(..., help="Source file to segment."),
    source_type: str = typer.Option(
        ..., "--type", "-t", help="Source type of the file, such as markdown."
    ),
    syntax: Optional[Path] = typer.Option(
        None, "--syntax", help="Syntax file replacing the default one."
    ),
    kinds: Optional[list[str]] = typer.Option(
        None, "--kind", "-k", help="Kind to print; repeat for several."
    ),
) -> None:
    """Print the regions of a source as JSON, one region per line."""
    try:
        segmenter = default_registry().segmenter(source_type, syntax)
        segmentation = segmenter.segment(path.read_text(encoding="utf-8"))
        regions = segmentation.select(kinds) if kinds else segmentation.regions
    except (MerismosError, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(2) from error
    for region in regions:
        typer.echo(json.dumps(region_to_data(region), ensure_ascii=False))


@app.command("conform")
def cli_conform(
    cases_path: Path = typer.Argument(..., help="Conformance file to check."),
    syntax: Optional[Path] = typer.Option(
        None, "--syntax", help="Syntax file replacing the default one."
    ),
) -> None:
    """Check the segmenter of each case against its expected regions; exit 1 on any mismatch."""
    registry = default_registry()
    try:
        cases = load_cases(cases_path)
        segmenters = {
            case.source_type: registry.segmenter(case.source_type, syntax) for case in cases
        }
        mismatches = [
            mismatch
            for case in cases
            if (mismatch := check_case(case, segmenters[case.source_type])) is not None
        ]
    except MerismosError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(2) from error
    for mismatch in mismatches:
        typer.echo(mismatch.describe())
    typer.echo(f"{len(cases) - len(mismatches)} of {len(cases)} cases conform")
    if mismatches:
        raise typer.Exit(1)


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show the package version and exit."
    )
) -> None:
    """Root command for the package command-line interface."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()

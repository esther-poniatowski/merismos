# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- The packaged Obsidian syntax follows the reading observed in Obsidian 1.15.0, and every
  Markdown case records that observation. Six readings change:
  - a wikilink runs to its first closing, its destination possibly holding brackets;
  - an escaped alias separator still separates the alias of a wikilink;
  - a narrower run closes a code span when no run of the opening width follows;
  - a link prevails over a code span crossing its text;
  - a code span inside the text of a link holds its brackets;
  - a blank line keeps display mathematics open, and an unclosed display delimiter opening a
    line opens a formula running to the end of its container.

### Added

- The syntax keys `code_span_shorter_closing`, `code_span_over_links`,
  `math.display_unclosed_runs_to_end` and `links.wikilink.escaped_separator`, which keep the
  CommonMark readings available.
- Fourteen Markdown cases, one of them awaiting observation.

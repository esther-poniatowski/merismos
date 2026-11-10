# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- The packaged Obsidian syntax follows the reading observed in Obsidian 1.15.0, and every
  Markdown case records that observation. Five readings change:
  - a wikilink runs to its first closing, its destination possibly holding brackets;
  - an escaped alias separator still separates the alias of a wikilink;
  - a narrower run closes a code span when no run of the opening width follows;
  - a link prevails over a code span crossing its text;
  - a blank line keeps display mathematics open, when a later delimiter may close it.

### Added

- The syntax keys `code_span_shorter_closing`, `code_span_over_links` and
  `links.wikilink.escaped_separator`, which keep the CommonMark readings available.
- Twelve Markdown cases, five of them awaiting observation.

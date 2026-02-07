# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- Cloud mode implementation: MCP-first with SonarCloud REST API fallback
- `--mode`, `--organization`, `--branch` flags for `collect_changed_issues.py`
- Bearer token authentication for SonarCloud
- MCP detection guidance in SKILL.md for cloud mode
- Output schema documentation in SKILL.md

### Changed

- Repository restructured: single canonical source in `skill/` replaces duplicate `.agents/` and `.codex/` directories
- Bash 3.2+ compatibility (macOS default `/bin/bash`); removed incorrect bash 4+ requirement

### Fixed

- Severity counts in `findings.json` now sorted by severity rank (BLOCKER first), not alphabetically
- Docker port mapping extracted from `SONAR_HOST_URL` instead of hardcoded 9000
- Docker container creation race condition between concurrent invocations
- Filenames containing commas now skipped from scanner inclusions with a warning
- Install script uses atomic copy to prevent partial installs on failure

## [1.0.0] - 2026-02-07

### Added

- Initial standalone `sonarqube` skill repository
- Codex skill and `/sonarqube` prompt command
- Claude skill package
- Installer script for Codex/Claude skill locations
- Documentation for install, configuration, troubleshooting, and release

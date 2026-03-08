# Changelog

All notable changes to this project are documented in this file.

## [1.2.0] - 2026-03-08

### Added

- Repo-local Python tooling with `uv` for optional skill validation helpers
- `validate:skill` workflow for running `skill-creator` validation with repo-local dependencies
- Automatic local SonarQube project bootstrap, token persistence to `.env`, richer `sonar-project.properties` detection, and Rust clippy report generation
- Regression tests covering SonarQube bootstrap, `.env` fallback, property parsing, and report generation

### Changed

- SonarQube skill trigger text and prompt descriptions now better match quality-gate, findings-summary, and autofix intents
- New-code-period verification guidance now calls out branch-scoped API checks

## [1.1.1] - 2026-02-13

### Added

- `CLAUDE.md` project guidance file for Claude Code

### Fixed

- Docker container image changed from `sonarqube:lts-community` to `sonarqube:community`
- Docker container now uses persistent named volumes for data and extensions directories

## [1.1.0] - 2026-02-07

### Added

- New-issues-only scope (`--scope new`): filters findings to changed lines via git diff hunk detection (default); `--scope changed` preserves file-level filtering
- Repo config file `.sonarqube-skill.yaml` with precedence: CLI > env > config > defaults
- Fix-plan generation: agent writes `fix-plan.md` and `fix-plan.json` before autofix loop
- Blocked-finding classification with structured `blocked.json` output and classification codes
- `changed-lines.json` output for debugging hunk-level filtering
- Cloud mode implementation: MCP-first with SonarCloud REST API fallback
- Bearer token authentication for SonarCloud
- MCP detection guidance in SKILL.md for cloud mode
- Output schema documentation in SKILL.md
- GitHub Actions release workflow for automated validation, changelog-based release notes, and npm publish to GitHub Packages
- npm package support (`package.json`) for distribution via npm, OpenSkills, and skills.sh
- Root-level `SKILL.md` symlink for marketplace auto-discovery
- Multi-platform install instructions in README (OpenSkills, skills.sh, npm)

### Changed

- Cloud mode autofix runs single-pass without re-scan verification (cloud API cannot reflect local fixes); agent advises user to verify via CI/CD after push
- Consolidated `run_changed_scan.sh` and `collect_changed_issues.py` into single `sonarqube.py` script with `scan` and `fetch` subcommands
- Repository restructured: single canonical source in `skill/` replaces duplicate `.agents/` and `.codex/` directories
- `bash` is no longer a prerequisite; the skill is now pure Python

### Fixed

- Severity counts in `findings.json` now sorted by severity rank (BLOCKER first), not alphabetically
- Docker port mapping extracted from `SONAR_HOST_URL` instead of hardcoded 9000
- Docker container creation race condition between concurrent invocations
- Filenames containing commas now skipped from scanner inclusions with a warning
- Install script uses atomic copy to prevent partial installs on failure

## [1.0.0] - 2026-02-05

### Added

- Initial standalone `sonarqube` skill repository
- Codex skill and `/sonarqube` prompt command
- Claude skill package
- Installer script for Codex/Claude skill locations
- Documentation for install, configuration, troubleshooting, and release

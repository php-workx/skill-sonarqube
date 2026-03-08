# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A SonarQube/SonarCloud skill package for AI coding agents (Claude, Codex, Cursor). It scans files changed on the current branch and either lists findings by severity or autonomously fixes them. Distributed via npm (GitHub Packages), OpenSkills, and skills.sh.

## Commands

```bash
# Validate (compile-checks Python + bash syntax)
npm run validate

# Set up repo-local Python tooling for optional validator helpers
uv sync --dev

# Run skill-creator quick validation through the repo venv
npm run validate:skill

# Preview package contents before publish
npm pack --dry-run

# Local smoke-test install
bash scripts/install-sonarqube-skill.sh
```

There are no test suites or linters configured beyond `npm run validate`.

## Repository Layout

```
skills/
  sonarqube/              # Canonical skill source (installed to agent skill dirs)
    SKILL.md              # Skill definition with frontmatter (name, description, full workflow)
    scripts/sonarqube.py  # Single Python script: scan + fetch subcommands
    agents/openai.yaml    # OpenAI agent metadata
prompts/sonarqube.md      # Codex /sonarqube slash command dispatcher
scripts/install-sonarqube-skill.sh  # Copies skill to ~/.claude/skills/ and ~/.codex/skills/
docs/                     # CONFIGURATION.md, TROUBLESHOOTING.md, RELEASE.md
```

## Architecture

**Single-script design**: `skills/sonarqube/scripts/sonarqube.py` is a zero-dependency Python 3 script (stdlib only, optional PyYAML) that handles both local SonarQube and SonarCloud workflows. It has two subcommands:
- `scan`: full pipeline — detect base ref, compute changed files/lines, ensure server (local), run scanner (local), fetch issues, filter, output findings
- `fetch`: backward-compatible issue fetch from an existing scan

**Skill definition**: `skills/sonarqube/SKILL.md` contains the complete autonomous workflow that agents follow. It defines the input resolution steps, severity mapping, scan/fix loop, stop conditions, and output schema. Changes to agent behavior start here.

**Dual-mode operation**:
- **Local mode**: manages a Docker SonarQube container, runs `sonar-scanner`, fetches results via local API. Iterative fix loop with re-scan verification.
- **Cloud mode**: MCP-first (checks for SonarQube MCP tools), REST API fallback via `SONAR_TOKEN`. Single-pass fixes only (cloud can't verify local changes).

**Exit codes from sonarqube.py**: `0` = no findings, `3` = actionable findings exist, `1` = blocked/error.

**Config precedence**: CLI flags > environment variables > `.sonarqube-skill.yaml` > hardcoded defaults.

## Key Conventions

- The Python script uses only stdlib (`urllib.request`, `subprocess`, `argparse`, `json`, `pathlib`). Do not add external dependencies.
- PyYAML is optional — the script includes a minimal YAML parser fallback (`_parse_simple_yaml`).
- Path normalization (`normalize_path`) strips `./` prefix and uses forward slashes. This is critical for matching Sonar component paths to git diff paths.
- Auth: local mode uses Basic auth (`token:` or `user:password`); cloud mode uses Bearer token. Local mode defaults to `admin/admin` for localhost.
- Outputs go to `.sonarqube/` directory (gitignored).
- Severity uses two models: software-quality (`blocker/high/medium/low/info`) and API/legacy (`blocker/critical/major/minor/info`). Both are accepted as input; internal mapping normalizes to API labels.

## Release Process

1. Update `CHANGELOG.md` (move Unreleased to versioned section)
2. Bump `version` in `package.json`
3. Commit, push, then `git tag vX.Y.Z && git push origin vX.Y.Z`
4. GitHub Actions handles validation, npm publish to GitHub Packages, and GitHub Release creation with changelog extraction

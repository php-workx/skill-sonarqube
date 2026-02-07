# skill-sonarqube

SonarQube/SonarCloud skill package for Codex and Claude.

This repository provides:

- `sonarqube` skill definitions for Codex and Claude
- `/sonarqube` prompt command for Codex
- installer script to copy skill files into user skill directories

## Features

- Scan only files changed on the current branch (vs base ref)
- Two actions:
  - `list`: aggregated findings by severity
  - `autofix`: iteratively fix findings at/above threshold
- Two scan modes:
  - `local`: local SonarQube instance/container
  - `cloud`: SonarCloud/SonarQube cloud APIs or MCP
- Supports both severity models (`high/medium/...` and `critical/major/...`)

## Prerequisites

- `python3`
- `sonar-scanner` (local mode only)
- `docker` (local mode only, for SonarQube container workflows)

Cloud mode only requires `python3`, `git`, and a `SONAR_TOKEN`.

## Install

### Via OpenSkills

```bash
# project-local install
npx openskills install php-workx/skill-sonarqube

# global install
npx openskills install -g php-workx/skill-sonarqube
```

### Via skills.sh

```bash
# project-local install
npx skills add php-workx/skill-sonarqube

# global install
npx skills add -g php-workx/skill-sonarqube
```

### Via npm (GitHub Packages)

```bash
npm install @php-workx/skill-sonarqube --registry=https://npm.pkg.github.com
```

### Via installer script

```bash
git clone --depth 1 --branch v1.1.0 https://github.com/php-workx/skill-sonarqube.git
cd skill-sonarqube
bash scripts/install-sonarqube-skill.sh
```

After install, restart Codex/Claude so new skills and slash commands are loaded.

## Usage

Codex slash command:

```text
/sonarqube list
/sonarqube autofix local high
/sonarqube autofix cloud medium
```

Natural language usage also works when `sonarqube` skill is selected by intent.

## Configuration

Runtime environment variables:

- `SONAR_TOKEN` (preferred)
- `SONAR_USER`, `SONAR_PASSWORD` (fallback)
- `SONAR_HOST_URL` (default `http://localhost:9000`)

Installer destination overrides:

- `CLAUDE_SKILLS_DIR`
- `CODEX_SKILLS_DIR`
- `CODEX_PROMPTS_DIR`

See `docs/CONFIGURATION.md` for details.

## Repository Layout

- `skill/` — single canonical skill source (SKILL.md, scripts, agents config)
- `prompts/sonarqube.md` — Codex slash command dispatcher
- `scripts/install-sonarqube-skill.sh` — copies skill to both Claude and Codex directories

## Troubleshooting

See `docs/TROUBLESHOOTING.md`.

## Release Process

See `docs/RELEASE.md`.

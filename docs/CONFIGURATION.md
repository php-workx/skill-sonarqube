# Configuration

## Runtime Variables

### Both Modes

- `SONAR_TOKEN`: preferred auth token. Used as Basic auth for local mode, Bearer auth for cloud mode.
- `SONAR_PROJECT_KEY`: Sonar project key. Auto-detected from `sonar-project.properties` or repository name if omitted.

### Local Mode

- `SONAR_HOST_URL`: SonarQube URL. Default: `http://localhost:9000`.
- `SONAR_USER`: username fallback when token is not set.
- `SONAR_PASSWORD`: password fallback when token is not set.

### Cloud Mode

- `SONAR_ORGANIZATION`: SonarCloud organization key.
- Cloud mode connects to `https://sonarcloud.io` and requires `SONAR_TOKEN` (Bearer auth).
- Cloud mode fetches existing findings from SonarCloud (no local `sonar-scanner` or `docker` needed).

## Severity Inputs

Preferred labels:

- `blocker`
- `high`
- `medium`
- `low`
- `info`

Accepted aliases:

- `critical` (alias of `high`)
- `major` (alias of `medium`)
- `minor` (alias of `low`)

Effective mapping used by scanner/API filters:

- `blocker -> BLOCKER`
- `high|critical -> CRITICAL`
- `medium|major -> MAJOR`
- `low|minor -> MINOR`
- `info -> INFO`

## Repo Config File (`.sonarqube-skill.yaml`)

Optional config file at the repo root. Provides defaults that can be overridden by environment variables or CLI flags.

Precedence: CLI flags > environment variables > config file > hardcoded defaults.

```yaml
version: 1
defaults:
  mode: local          # local|cloud
  severity: high       # blocker|high|medium|low|info
  scope: new           # new|changed
  max_passes: 8
scan:
  base_ref: origin/main
  exclude_paths:
    - vendor/**
    - dist/**
```

- `version`: must be `1`. Unknown versions produce a warning and fall back to defaults.
- `defaults.scope`: `new` filters to changed lines only; `changed` filters to changed files (previous behavior).
- `scan.exclude_paths`: glob patterns excluded from scanner inclusions.
- If the file is missing, all values use hardcoded defaults.
- If the file is malformed, a warning is printed and defaults are used.
- Uses PyYAML if available; falls back to a built-in parser for this schema.

## Installer Destination Overrides

- `CLAUDE_SKILLS_DIR`: override destination base for Claude skill install.
- `CODEX_SKILLS_DIR`: override destination base for Codex skill install.
- `CODEX_PROMPTS_DIR`: override destination base for Codex prompt command install.

Example:

```bash
CLAUDE_SKILLS_DIR="$HOME/.claude/skills" \
CODEX_SKILLS_DIR="$HOME/.codex/skills" \
CODEX_PROMPTS_DIR="$HOME/.codex/prompts" \
bash scripts/install-sonarqube-skill.sh
```

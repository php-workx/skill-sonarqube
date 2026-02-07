# Configuration

## Runtime Variables

- `SONAR_HOST_URL`: SonarQube URL. Default: `http://localhost:9000`.
- `SONAR_TOKEN`: preferred auth token.
- `SONAR_USER`: username fallback when token is not set.
- `SONAR_PASSWORD`: password fallback when token is not set.

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

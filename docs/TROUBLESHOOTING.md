# Troubleshooting

## `/sonarqube` is unrecognized

Cause: Codex prompt file not loaded.

Fix:

1. Re-run installer: `bash scripts/install-sonarqube-skill.sh`
2. Confirm file exists: `~/.codex/prompts/sonarqube.md`
3. Restart Codex.

## `required command not found: sonar-scanner`

Install scanner CLI and retry:

```bash
brew install sonar-scanner
```

## `mapfile: command not found`

Cause: old bash (macOS `/bin/bash` 3.2).

Fix:

```bash
brew install bash
/opt/homebrew/bin/bash scripts/install-sonarqube-skill.sh
```

And run skill scripts with newer bash.

## Local scan cannot connect to SonarQube

1. Verify Docker is running.
2. Verify `SONAR_HOST_URL`.
3. Confirm local SonarQube is reachable.

## Cloud mode cannot fetch results

1. Verify auth (`SONAR_TOKEN` preferred).
2. Verify MCP availability (if using MCP path).
3. Check project key and permissions.

## Scan exits with blocked findings

This indicates findings that cannot be auto-fixed safely (false positives, external constraints, or unsupported transformations). Use `list` to aggregate and then address manually.

# Troubleshooting

## `/sonarqube` is unrecognized

Cause: Codex prompt file not loaded.

Fix:

1. Re-run installer: `bash scripts/install-sonarqube-skill.sh`
2. Confirm file exists: `~/.codex/prompts/sonarqube.md`
3. Restart Codex.

## `required command not found: sonar-scanner`

Only needed for local mode. Install scanner CLI and retry:

```bash
brew install sonar-scanner
```

## Local scan cannot connect to SonarQube

1. Verify Docker is running.
2. Verify `SONAR_HOST_URL`.
3. Confirm local SonarQube is reachable.
4. If using a non-default port, ensure `SONAR_HOST_URL` includes the correct port (e.g. `http://localhost:9010`). The skill extracts the port and maps it automatically.

## Local mode keeps asking for credentials

1. Check whether repo-local `.env` already contains `SONAR_TOKEN`.
2. If not, make sure the local server is reachable at `SONAR_HOST_URL` or `sonar.host.url`.
3. For `localhost`, the skill falls back to `admin/admin`, generates a token, and stores it in `.env`.
4. If token generation fails, inspect `.sonarqube/sonar-scanner.log` and the script stderr for the underlying SonarQube API error.

## Quality gate passes but new-code findings look wrong

1. Verify the project has a configured new code period in SonarQube.
2. The skill now sets `REFERENCE_BRANCH` automatically during local bootstrap.
3. If your repo uses a non-`main` base branch, run the scan with `--base-ref` so the reference branch is derived correctly.

## Rust findings are missing from local scans

1. Confirm `Cargo.toml` exists at the repo root.
2. Verify `cargo` is installed and `cargo clippy` succeeds locally.
3. The skill writes the clippy JSON report into `.sonarqube/rust-clippy.json` before scanning.

## Cloud mode cannot fetch results

### MCP path

1. Verify a SonarQube/SonarCloud MCP server is connected.
2. Check that the MCP server exposes issue search tools.
3. The skill will fall back to the REST API if MCP is unavailable.

### REST API path

1. Verify `SONAR_TOKEN` is set. Cloud mode requires a Bearer token.
2. Verify the token has permissions for the target project.
3. If the project belongs to an organization, set `SONAR_ORGANIZATION`.
4. Check project key matches SonarCloud (case-sensitive).

## Scan exits with blocked findings

This indicates findings that cannot be auto-fixed safely (false positives, external constraints, or unsupported transformations). Use `list` to aggregate and then address manually.

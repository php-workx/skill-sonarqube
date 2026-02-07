---
name: sonarqube
description: Use when you need a coding agent to run SonarQube/SonarCloud checks on current-branch changes, either list aggregated findings by severity or autonomously fix findings at/above a chosen severity threshold.
---

# SonarQube

**YOU MUST EXECUTE THIS WORKFLOW. Do not just describe it.**

Runs SonarQube/SonarCloud against files changed on the current branch, then iteratively fixes findings at/above a target severity (`high` by default) until clean or blocked.

## Inputs

- `action`: `autofix|list` (resolved from user intent)
- `mode`: `local|cloud` (default `local`)
- `severity`: `blocker|high|medium|low|info` (default `high`)
- `base_ref`: branch to diff against (default auto-detect: `origin/main`, `main`, `origin/master`, `master`)
- `host_url`: SonarQube URL (default `http://localhost:9000`; ignored in cloud mode)
- `auth`: prefer `SONAR_TOKEN`; fallback `SONAR_USER` + `SONAR_PASSWORD`
- `organization`: SonarCloud organization key (cloud mode only)

## Severity Models

This skill understands both Sonar severity models and maps them consistently:

- Software-quality labels: `blocker|high|medium|low|info` (preferred input)
- API/legacy labels: `blocker|critical|major|minor|info`
- Mapping used by this skill:
  - `blocker` -> `BLOCKER`
  - `high`/`critical` -> `CRITICAL`
  - `medium`/`major` -> `MAJOR`
  - `low`/`minor` -> `MINOR`
  - `info` -> `INFO`

## Bundled Scripts

- `scripts/run_changed_scan.sh`: starts local SonarQube container if needed, scans changed files, writes findings (local mode only)
- `scripts/collect_changed_issues.py`: queries SonarQube/SonarCloud API and filters findings to changed files at/above threshold (both modes via `--mode local|cloud`)

Outputs (default directory `.sonarqube/`):
- `changed-files.txt`
- `sonar-scanner.log` (local mode only)
- `findings.json`
- `findings.md`

## Autonomous Workflow

1. Resolve action from intent.
- If invoked as `/sonarqube` with no explicit action, first show supported actions and ask once:
  - `autofix`: apply fixes for findings at/above threshold
  - `list`: show aggregated findings by severity (no code changes)
- `autofix` keywords: `autofix`, `fix`, `address`, `resolve`, `complete`, `remediate`.
- `list` keywords: `list`, `show`, `find`, `report`, `summary`, `aggregate`, `count`.
- If ambiguous, ask once: `Do you want autofix or list? (autofix/list)`.
- If unanswered/ambiguous, default to `autofix`.

2. Resolve mode.
- If user/context explicitly says `local` or `cloud`, use it.
- If not explicit, ask once: `Do you want a local scan or SonarCloud results? (local/cloud)`.
- If unanswered/ambiguous, default to `local`.

3. Resolve severity threshold.
- If user/context explicitly provides severity, use it.
- If missing, ask once: `Which severity threshold? (blocker/high/medium/low/info)`.
- If unanswered/ambiguous, default to `high`.
- Accept both models on input (`medium` or `major`, `high` or `critical`, etc.) and apply the mapping above.

4. Compute changed files (both modes).
```bash
BASE_REF="${BASE_REF:-origin/main}"
BASE_COMMIT="$(git merge-base HEAD "$BASE_REF")"
OUTPUT_DIR=".sonarqube"
mkdir -p "$OUTPUT_DIR"
git diff --name-only --diff-filter=ACMRTUXB "$BASE_COMMIT..HEAD" | while IFS= read -r f; do
  [ -f "$f" ] && printf '%s\n' "$f"
done > "$OUTPUT_DIR/changed-files.txt"
```

5. For `local` mode, run scanner and collect findings.
- If `action=list`, pass `--list-only`:
```bash
bash "<path-to-skill>/scripts/run_changed_scan.sh" \
  --severity "${SEVERITY:-high}" --base-ref "${BASE_REF:-origin/main}" --list-only
```
- Otherwise (autofix):
```bash
bash "<path-to-skill>/scripts/run_changed_scan.sh" \
  --severity "${SEVERITY:-high}" --base-ref "${BASE_REF:-origin/main}"
```
- Skip to step 7 (interpret exit code).

6. For `cloud` mode, fetch existing findings (no local scanner needed).
   Cloud mode retrieves findings already in SonarCloud from CI/CD scans. It does not run `sonar-scanner` locally.

   a. **MCP-first**: Check if a SonarQube/SonarCloud MCP server is connected.
      - Look for MCP tools containing `sonar` in the name (e.g. `sonarqube_issues_search`, `search_issues`, or similar).
      - If available, use the MCP tool to search issues for the project key with relevant severity/status filters.
      - Parse the MCP response and filter results to files in `.sonarqube/changed-files.txt`.
      - Write results to `.sonarqube/findings.json` and `.sonarqube/findings.md` using the standard schema (see Output Schema below).

   b. **REST API fallback**: If no SonarCloud MCP server is available, run:
      ```bash
      python3 "<path-to-skill>/scripts/collect_changed_issues.py" \
        --mode cloud \
        --project-key "$PROJECT_KEY" \
        --changed-files ".sonarqube/changed-files.txt" \
        --severity-threshold "${SEVERITY:-high}" \
        --token "$SONAR_TOKEN" \
        --organization "${SONAR_ORGANIZATION:-}" \
        --branch "$(git rev-parse --abbrev-ref HEAD)" \
        --output-json ".sonarqube/findings.json" \
        --output-md ".sonarqube/findings.md"
      ```

   c. If neither MCP nor `SONAR_TOKEN` is available, report blocked with the exact missing dependency and stop.

   d. If `action=list`, print aggregated findings from `.sonarqube/findings.json` and stop (no code edits).

7. Interpret exit code (both modes).
- `0`: no actionable findings; stop.
- `3`: actionable findings exist; continue fix loop.
- `1`: blocked (scanner/auth/infrastructure); surface blocker and stop.

8. Fix loop (no user checkpoints).
- Set `MAX_PASSES=8` unless user specified another limit.
- On each pass with exit code `3`, read `.sonarqube/findings.json` and fix highest-severity findings first.
- Keep changes minimal and local to files in `changed-files.txt`.
- After each pass run relevant verification (`make test` preferred; if too slow, run targeted tests for touched packages/files).
- Re-run the scan/fetch for the current mode after fixes.

9. Stop conditions.
- Stop successfully when scan exits `0`.
- Stop as blocked if findings are non-actionable in-code constraints (rule false positive, external dependency, or unsupported auto-fix) and report exact finding keys.
- Stop as failed if `MAX_PASSES` is reached and findings remain; report remaining findings by severity.

10. Completion behavior.
- Summarize files changed and remaining findings count (should be zero on success).
- Commit with a conventional commit message if repository policy expects autonomous commits.
- Never push automatically.

## Output Schema

Both local and cloud modes produce the same output format so the fix loop works identically regardless of mode.

**findings.json:**
```json
{
  "summary": {
    "project_key": "...",
    "severity_threshold": "...",
    "changed_files": 5,
    "findings": 3,
    "severity_counts": {"BLOCKER": 0, "CRITICAL": 2, "MAJOR": 1}
  },
  "findings": [
    {
      "key": "issue-key",
      "rule": "rule-id",
      "type": "BUG|VULNERABILITY|CODE_SMELL|SECURITY_HOTSPOT",
      "severity": "BLOCKER|CRITICAL|MAJOR|MINOR|INFO",
      "message": "description",
      "file": "path/to/file",
      "line": 42,
      "status": "OPEN|CONFIRMED|REOPENED",
      "effort": "estimation",
      "tags": ["tag1"]
    }
  ]
}
```

**findings.md:** Markdown table with columns: Severity | File | Line | Rule | Message.

## MCP Detection (Cloud Mode)

When in cloud mode, before falling back to the REST API script:

1. Check your available MCP tools for names containing `sonar` (e.g. `sonarqube_issues_search`, `search_issues`).
2. If available, call with the project key and relevant filters (severities, statuses).
3. The MCP tool returns issues with fields like: key, rule, severity, message, component, line, status.
4. Filter results to files listed in `.sonarqube/changed-files.txt` using the same path normalization as `collect_changed_issues.py`.
5. Write `findings.json` and `findings.md` using the Output Schema above.
6. Use exit code `0` if no findings match, `3` if findings exist.

## Execution Rules

- Do not ask the user to review each finding during this workflow.
- Do not claim success without a fresh final scan (`exit 0`) and test evidence.
- Prioritize vulnerabilities and bugs over code smells when severities tie.
- If SonarQube is local and no credentials are provided, `run_changed_scan.sh` defaults to `admin/admin`.
- Cloud mode does not require `sonar-scanner` or `docker`.

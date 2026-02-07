# Release

## Pre-release Checklist

1. Validate scripts syntax:

```bash
bash -n scripts/install-sonarqube-skill.sh
bash -n .codex/skills/sonarqube/scripts/run_changed_scan.sh
bash -n .agents/skills/sonarqube/scripts/run_changed_scan.sh
python3 -m py_compile .codex/skills/sonarqube/scripts/collect_changed_issues.py
python3 -m py_compile .agents/skills/sonarqube/scripts/collect_changed_issues.py
```

2. Smoke-install locally:

```bash
bash scripts/install-sonarqube-skill.sh
```

3. Restart Codex/Claude.
4. Verify `/sonarqube list` resolves.
5. Update `CHANGELOG.md`.

## Versioning

Use semantic versioning:

- `v1.0.0`: first stable release
- `v1.0.1`: patch fix
- `v1.1.0`: new backward-compatible feature
- `v2.0.0`: breaking behavior change

## Tag and publish

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin codex/bootstrap-sonarqube-skill
git push origin v1.0.0
```

## Post-release

1. Add release notes on GitHub.
2. Include install command pinned to tag.
3. Mention restart requirement for Codex/Claude.

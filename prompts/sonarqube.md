---
description: Run the SonarQube skill to list findings, check quality gates, or autofix SonarQube/SonarCloud issues on current-branch changes.
---

## User Input

```text
$ARGUMENTS
```

Use the `sonarqube` skill for this request.

Interpret `$ARGUMENTS` as follows:
- If it includes `list`, run action=`list`.
- If it includes `autofix`, run action=`autofix`.
- If it includes neither, ask once: `Do you want autofix or list? (autofix/list)`.
- Parse optional mode (`local` or `cloud`), severity (`blocker|high|medium|low|info`, plus aliases `critical|major|minor`), and scope (`new` or `changed`).

Note: cloud mode autofix applies fixes in a single pass without re-scan verification (cloud API cannot reflect local fixes). Include this in the output summary and advise the user to verify via CI/CD after push.

Then execute the workflow exactly as defined by the `sonarqube` skill.

# Release

## Pre-release Checklist

1. Validate scripts:

```bash
npm run validate
```

2. Preview npm package contents:

```bash
npm pack --dry-run
```

3. Smoke-install locally:

```bash
bash scripts/install-sonarqube-skill.sh
```

4. Restart Codex/Claude.
5. Verify `/sonarqube list` resolves.

## Versioning

Use semantic versioning:

- `v1.0.0`: first stable release
- `v1.0.1`: patch fix
- `v1.1.0`: new backward-compatible feature
- `v2.0.0`: breaking behavior change

## Release Flow

1. Move "Unreleased" items in `CHANGELOG.md` under `## [x.y.z] - YYYY-MM-DD`.
2. Bump `version` in `package.json` to `x.y.z`.
3. Commit and push:

```bash
git add CHANGELOG.md package.json
git commit -m "release: vx.y.z"
git push origin main
```

4. Tag and push (triggers the GitHub Action):

```bash
git tag vx.y.z
git push origin vx.y.z
```

5. The GitHub Action automatically:
   - Validates scripts (`npm run validate`)
   - Publishes to npmjs via trusted publishing (OIDC)
   - Publishes to GitHub Packages
   - Creates a GitHub Release with notes extracted from `CHANGELOG.md`

## Required Secrets

- `GITHUB_TOKEN`: provided automatically by GitHub Actions for GitHub Packages and release creation

## Trusted Publishing Setup

The npmjs publish job uses npm trusted publishing with GitHub Actions OIDC. After configuring the trusted publisher on npmjs for this repository and workflow file:

- no `NPM_TOKEN` secret is required for the npmjs publish job
- the workflow must have `id-token: write`
- GitHub-hosted runners must use a recent Node/npm toolchain; this repo uses Node 24 in the release workflow

You can keep a local npm token for manual fallback publishes, but CI no longer needs one for npmjs.

## Manual Fallback

If the GitHub Action fails or you need to publish manually to npmjs:

```bash
npm publish --access public
```

`prepublishOnly` runs `npm run validate` automatically before publishing.

To publish manually to GitHub Packages:

```bash
npm publish --registry=https://npm.pkg.github.com
```

## Post-release

1. Verify the GitHub Release appears with correct changelog notes.
2. Verify the package is visible on npmjs.
3. Verify the package is listed in the repo's Packages tab.
4. Mention restart requirement for Codex/Claude in release notes.

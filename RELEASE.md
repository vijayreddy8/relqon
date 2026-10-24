# Release Checklist

Use this checklist when preparing a Relqon release.

## Before tagging

- [ ] Confirm the intended version in `pyproject.toml` matches `CHANGELOG.md`.
- [ ] Review the release notes and document any known limitations.
- [ ] Confirm the working tree is clean and the release commit is on `master`.
- [ ] Confirm all required GitHub Actions workflows pass for the exact release commit:
  - Relqon CI
  - Relqon tests
  - Relqon package smoke test
- [ ] Verify package installation and the installed console command:
  `python -m pip install -e ".[test]"`, `relqon --help`, and `relqon run --help`.
- [ ] Confirm the CLI writes the expected JSON validation report and uses documented exit codes.

## Publish

- [ ] Create an annotated Git tag matching the package version (for example, `v0.1.0`).
- [ ] Create a GitHub Release from that tag and use the matching `CHANGELOG.md` section as the release notes.
- [ ] If distributing built packages, build and inspect the wheel and source distribution before attaching or publishing them.

## After publishing

- [ ] Install the published artifact in a clean environment and run the CLI smoke checks.
- [ ] Verify the GitHub Release page, tag, and installation instructions.
- [ ] Record any follow-up fixes for the next release.

## Release caution

A green CI run confirms the checks implemented in this repository passed; it does not guarantee every external environment or optional validator is available. Review the generated report and any skipped checks before relying on a result.

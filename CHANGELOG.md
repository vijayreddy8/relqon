# Relqon v0.1.0

This release establishes the initial installable CLI package and CI validation pipeline.

## Highlights

- Installable Python package with the `relqon` console command.
- Change-impact analysis for Python, Docker, Kubernetes, and Terraform files.
- Structured JSON validation report with summary, statuses, durations, and recovery guidance.
- Git path handling for quoted filenames, UTF-8 octal escapes, and escaped backslashes.
- Automated unit tests, Terraform fixture validation, and package-install smoke test.

## Installation

```bash
python -m pip install -e ".[test]"
```

## Quick start

```bash
relqon run .
relqon run . --changed-file src/relqon/cli.py
```

The JSON report is written to `reports/validation-report.json`.

## Verification

GitHub Actions checks for this release include the Relqon CI workflow, unit tests, and package smoke test.

## Notes

This is an initial development release. Validators can report `SKIPPED` when optional external tools are not installed. Review validation output before using it to approve deployments.

# Relqon

**Relqon** is a Python-based DevOps change-impact and validation CLI. It detects changed files, selects relevant checks, runs supported validations, displays diagnostics, and writes a JSON report.

> **Important:** Relqon helps find certain code and build problems before deployment. A passing build does not guarantee that every browser, API, database, configuration, infrastructure, or production runtime issue has been detected. Use application tests, staging, health checks, and monitoring too.

## Contents

- [What Relqon checks](#what-relqon-checks)
- [Install Relqon](#install-relqon)
- [Everyday workflow for an application](#everyday-workflow-for-an-application)
- [What to do when Relqon passes](#what-to-do-when-relqon-passes)
- [What to do when Relqon fails](#what-to-do-when-relqon-fails)
- [TypeScript and Vite troubleshooting example](#typescript-and-vite-troubleshooting-example)
- [Skipped checks and no changed files](#skipped-checks-and-no-changed-files)
- [JSON report and exit codes](#json-report-and-exit-codes)
- [Run Relqon's own tests](#run-relqons-own-tests)
- [Limitations and deployment safety](#limitations-and-deployment-safety)

## What Relqon checks

- **Python** — syntax validation for changed production Python files.
- **Node.js / TypeScript** — runs a package build when relevant files changed, a build script exists, and dependencies are installed.
- **Docker** — build validation when Docker configuration changes and Docker is available.
- **Kubernetes** — supported validation for changed Kubernetes manifests and Helm metadata when relevant tools are available.
- **Terraform** — formatting and configuration validation for changed Terraform files when Terraform is available.
- **Relqon self-tests** — optional `--full` mode runs Relqon's own test suite and failure-detection self-tests. It does not automatically run every test suite in the target application.

A check may be marked `SKIPPED` if a required tool, dependency, or supported project script is unavailable. A skipped check is **not** a pass.

## Install Relqon

Relqon supports Python 3.10+ on Windows, Linux, and macOS.

### Windows (PowerShell)

```powershell
git clone https://github.com/vijayreddy8/relqon.git
Set-Location relqon
.\scripts\setup.ps1
.\.venv\Scripts\relqon.exe run .
```

If PowerShell blocks the setup script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

### Linux / macOS

```bash
git clone https://github.com/vijayreddy8/relqon.git
cd relqon
sh scripts/setup.sh
./.venv/bin/relqon run .
```

The default command is a lightweight scan. To run Relqon's own slower self-tests:

```powershell
# Windows PowerShell, from the Relqon repository
.\.venv\Scripts\relqon.exe run . --full
```

```bash
# Linux/macOS, from the Relqon repository
./.venv/bin/relqon run . --full
```

## Everyday workflow for an application

Run these commands from the **application repository root** — the directory containing the app's frontend/backend folders or package manifests. If Relqon is installed in a different folder, invoke its executable by full path.

### 1. Check what changed

Windows PowerShell:

```powershell
git status --short
git diff --stat
git diff
```

Linux/macOS:

```bash
git status --short
git diff --stat
git diff
```

Review the changes. Do not commit credentials, `.env` files, personal uploads, generated build output, or intentional test errors.

### 2. Run Relqon

Windows PowerShell example — replace the executable path with your actual Relqon installation path:

```powershell
& "C:\Users\<your-user>\relqon\.venv\Scripts\relqon.exe" run .
```

Linux/macOS example:

```bash
/path/to/relqon/.venv/bin/relqon run .
```

To explicitly include a file if automatic Git detection did not include it:

```powershell
& "C:\Users\<your-user>\relqon\.venv\Scripts\relqon.exe" run . --changed-file frontend/src/App.tsx
```

You can repeat `--changed-file` for multiple paths. This asks Relqon to consider those files; checks still depend on available validators, dependencies, and project scripts.

### 3. Know where the report is saved

Relqon writes:

```text
reports/validation-report.json
```

The path is inside the **target application root**, not necessarily the Relqon repository. In PowerShell, inspect it with:

```powershell
Get-Content reports\validation-report.json
```

For formatted JSON:

```powershell
Get-Content reports\validation-report.json | ConvertFrom-Json | ConvertTo-Json -Depth 20
```

## What to do when Relqon passes

A `PASS` means the checks that actually ran passed. Continue with the app's own build, tests, and deployment gates.

For a React/Vite frontend and Express/TypeScript backend, from the application root:

```powershell
npm --prefix frontend run build
npm --prefix backend run build
```

These commands assume each package has a `build` script. Run the tests defined by the application too. Example commands (only if these scripts exist):

```powershell
npm --prefix frontend test
npm --prefix backend test
```

Check each package's `package.json` to confirm its scripts:

```powershell
Get-Content frontend\package.json
Get-Content backend\package.json
```

Before deploying, follow the project's normal process for API/database integration tests, browser or end-to-end tests, secret/configuration checks, staging deployment, health checks, and monitoring. Do not deploy based only on a single passing build.

## What to do when Relqon fails

**Do not ignore the first error or blindly reinstall everything.** Use this order to find and fix the root cause.

### Step 1 — Read the complete failure

Look at the `[FAIL]` section in the terminal. Note the failed check, package, file path, line/column, and first useful diagnostic. Then inspect the report:

```powershell
Get-Content reports\validation-report.json | ConvertFrom-Json | ConvertTo-Json -Depth 20
```

### Step 2 — Confirm the application root and changed files

```powershell
Get-Location
git status --short
git diff --stat
git diff
```

Make sure you ran Relqon from the application root and that the intended files are in the Git change list. If needed, rerun Relqon with an explicit `--changed-file` path as shown above.

### Step 3 — Re-run the failing package build directly

For a React/Vite frontend and an Express/TypeScript backend:

```powershell
npm --prefix frontend run build
npm --prefix backend run build
```

Running the build directly often provides the clearest compiler output. Fix the **first real diagnostic**, then rerun the build. More errors may appear after the first one is resolved.

### Step 4 — Inspect the exact code around the reported line

Example for a frontend TypeScript error:

```powershell
Get-Content frontend\src\App.tsx | Select-Object -Skip 890 -First 25
```

Example for a Vite environment-type error:

```powershell
Get-Content frontend\src\App.tsx | Select-Object -Skip 25 -First 20
Get-Content frontend\src\components\ProfileEditor.tsx | Select-Object -First 20
Get-Content frontend\tsconfig.json
Get-ChildItem frontend\src -Filter "vite-env.d.ts" -Recurse | Select-Object FullName
```

Adjust the `-Skip` number to inspect the lines around the diagnostic. Do not replace or delete application code without understanding why the type or value is wrong.

### Step 5 — Apply the fix that matches the diagnostic

- **TypeScript type mismatch** (for example, a string passed where a number is required): inspect the variable, function/prop type, and expected data format. Correct the source value or type based on the intended behavior; do not silence the error with an unsafe cast just to get a green build.
- **Missing Vite types** (`import.meta.env` is not recognized): in a Vite project, check that Vite is installed and that a declaration file such as `src/vite-env.d.ts` contains `/// <reference types="vite/client" />` and is included by the active TypeScript configuration. Check `frontend/package.json` and `frontend/tsconfig.json` before changing config.
- **Missing package or dependency**: confirm the correct package directory and lockfile. Restore dependencies only if they are missing or out of sync.
- **Script not found**: inspect the relevant `package.json` and use a script that actually exists.
- **Docker/Kubernetes/Terraform failure**: read the tool's specific diagnostic and validate the configuration with the corresponding installed tool. Do not deploy until the failure is understood.

### Step 6 — Reinstall dependencies only when justified

If dependencies are missing or the lockfile has changed and needs syncing, run `npm ci` inside the affected package. Note that `npm ci` removes and recreates that package's `node_modules`, and requires a valid lockfile.

```powershell
npm --prefix frontend ci
# Run only if the backend dependencies need restoring too:
npm --prefix backend ci
```

Do not run these commands as a reflex for every TypeScript error. If a lockfile is not present, check the project's package manager and documented setup instead.

### Step 7 — Rebuild after the fix

```powershell
npm --prefix frontend run build
npm --prefix backend run build
```

Run only the packages relevant to your changes, but validate both for changes that affect both sides.

### Step 8 — Run Relqon again

Use the same command you used for the initial scan:

```powershell
& "C:\Users\<your-user>\relqon\.venv\Scripts\relqon.exe" run .
```

Replace the example path with your actual Relqon executable. Check that all relevant checks are `PASS`, not `SKIPPED`. Review the new JSON report. Repeat the inspect → fix → build → Relqon cycle if a new failure appears.

### Step 9 — Review and commit only the intended fix

```powershell
git diff --check
git status --short
git diff
```

After reviewing the changes, commit only the intended application files. Avoid committing reports, uploads, secrets, generated `dist` files, or deliberate failure-test code unless the project explicitly requires them.

## TypeScript and Vite troubleshooting example

During a Relqon test against a React/Vite application, these diagnostics appeared:

```text
src/App.tsx(35,15): error TS2339: Property 'env' does not exist on type 'ImportMeta'.
src/App.tsx(901,7): error TS2322: Type 'string' is not assignable to type 'number'.
src/components/ProfileEditor.tsx(4,25): error TS2339: Property 'env' does not exist on type 'ImportMeta'.
```

The investigation found two distinct issues:

1. The app needed Vite client type declarations for `import.meta.env`. A declaration file was added at `frontend/src/vite-env.d.ts` with:
   ```typescript
   /// <reference types="vite/client" />
   ```
2. The `TS2322` diagnostic came from an intentional test line:
   ```typescript
   const relqonTest: number = "intentional-error";
   ```
   That test-only line was removed from the application source.

After those changes, the following command completed successfully, including TypeScript compilation and the Vite production build:

```powershell
npm --prefix frontend run build
```

This is a troubleshooting example, not a promise that the same changes fix every project. Confirm the current source and diagnostic before applying a fix.

## Skipped checks and no changed files

- **SKIPPED:** a required tool, dependency, or expected build script may be missing. Read the skip reason, check whether the tool is installed, and verify the package's scripts. A skipped check is not a pass.
- **No changed files detected:** run `git status --short`, verify the current directory, and check whether the file is untracked or ignored. Use `--changed-file` if appropriate.
- **A check passes but the application still fails:** build validation does not exercise every runtime path. Reproduce the issue with the app's own tests, browser, API, database, container, or staging environment and inspect relevant logs.

## JSON report and exit codes

The report at `reports/validation-report.json` records changed files, impact-analysis reasons, individual check results, durations, recovery guidance, and overall status.

- `0` — no checks failed or were skipped.
- `1` — a validation failed or the project path is invalid.
- `2` — at least one check was skipped and no check failed.

Always read the displayed results and report. Do not interpret an exit code in isolation from the checks that actually ran.

## Run Relqon's own tests

From the Relqon repository root, install test dependencies if needed, then run:

```powershell
python -m pip install -e ".[test]"
python -m pytest tests/ -v --ignore=tests/python_validation/broken_test.py
```

The intentionally broken Python fixture is excluded from the ordinary test run because it is used by the failure-detection self-test. Alternatively, use Relqon's `--full` mode as documented above.

## Deployment safety and limitations

A reliable pre-deployment workflow may include:

1. Relqon change-impact validation.
2. Frontend and backend production builds.
3. Unit and integration tests.
4. Browser/e2e tests for important user journeys.
5. API, database connectivity, and migration checks.
6. Environment/secret validation without printing secret values.
7. Container image build and vulnerability checks where applicable.
8. Staging deployment, HTTP/API health checks, and runtime monitoring.

Relqon does not guarantee production readiness. Static/build checks cannot detect every runtime, browser, API, database, network, or infrastructure failure. Review diagnostics and reports before using results as a deployment decision.

## CI and workflow

GitHub Actions runs Relqon's CI and tests on repository changes. Inspect the [Relqon Actions page](https://github.com/vijayreddy8/relqon/actions) for workflow results and available validation-report artifacts.

## License and contribution

Open an issue or pull request in the [Relqon repository](https://github.com/vijayreddy8/relqon) to report a bug or propose an improvement.

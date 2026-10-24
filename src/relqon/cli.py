
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path


def get_changed_files(project_path: Path) -> list[str]:
    """Get changed, staged, and untracked files from Git."""

    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=project_path,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print("Warning: Could not read Git status.")
        return []

    changed_files = []

    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue

        filename = line[3:].strip()

        # Handle Git rename output.
        if " -> " in filename:
            filename = filename.split(" -> ")[-1]

        filename = filename.replace("\\", "/")

        if filename:
            changed_files.append(filename)

    return sorted(set(changed_files))


def detect_changes(project_path: Path) -> tuple[int, list[str]]:
    """Detect project changes."""

    print("\nRelqon - Change Intelligence")
    changed_files = get_changed_files(project_path)

    if not changed_files:
        print("No changed files detected.")
        return 0, []

    print(f"Detected {len(changed_files)} changed file(s):")

    for filename in changed_files:
        print(f"  File: {filename}")

    return len(changed_files), changed_files


def analyse_impact(changed_files: list[str]) -> dict:
    """Identify which validation checks are relevant."""

    checks = set()
    reasons = []

    for filename in changed_files:
        path = Path(filename)
        name = path.name.lower()
        parts = {part.lower() for part in path.parts}

        # Test fixtures are handled by dedicated self-tests.
        is_test_file = "tests" in parts or "test" in parts

        if (
            name == "dockerfile"
            or name in {"docker-compose.yml", "docker-compose.yaml"}
        ):
            checks.add("docker_build")
            reasons.append(
                f"{filename}: Docker configuration changed."
            )

        if not is_test_file and (
            path.suffix.lower() == ".py"
            or name in {"requirements.txt", "pyproject.toml"}
        ):
            checks.add("python_check")
            reasons.append(
                f"{filename}: Python code or dependencies changed."
            )

        if (
            "k8s" in parts
            or "kubernetes" in parts
            or "helm" in parts
            or name == "chart.yaml"
        ):
            checks.add("kubernetes_check")
            reasons.append(
                f"{filename}: Kubernetes or Helm configuration changed."
            )

        if path.suffix.lower() in {".tf", ".tfvars"}:
            checks.add("terraform_check")
            reasons.append(
                f"{filename}: Terraform configuration changed."
            )

    return {
        "checks": sorted(checks),
        "reasons": reasons,
    }


def validate_python(
    project_path: Path,
    changed_files: list[str],
) -> dict:
    """Compile changed production Python files."""

    started = time.perf_counter()

    python_files = [
        filename
        for filename in changed_files
        if Path(filename).suffix.lower() == ".py"
        and not ({"tests", "test"} & {
            part.lower() for part in Path(filename).parts
        })
    ]

    if not python_files:
        return {
            "name": "Python syntax validation",
            "status": "SKIPPED",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": "No changed production Python files to validate.",
            "files_checked": [],
        }

    errors = []
    checked_files = []

    for filename in python_files:
        file_path = (project_path / filename).resolve()

        try:
            file_path.relative_to(project_path.resolve())
        except ValueError:
            errors.append(
                f"{filename}: file is outside the project directory."
            )
            continue

        if not file_path.is_file():
            errors.append(f"{filename}: file not found.")
            continue

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "py_compile",
                    str(file_path),
                ],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

            checked_files.append(filename)

            if result.returncode != 0:
                message = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Python syntax check failed."
                )
                errors.append(f"{filename}: {message}")

        except subprocess.TimeoutExpired:
            errors.append(f"{filename}: syntax check timed out.")
        except OSError as exc:
            errors.append(f"{filename}: {exc}")

    return {
        "name": "Python syntax validation",
        "status": "FAIL" if errors else "PASS",
        "duration_seconds": round(
            time.perf_counter() - started, 3
        ),
        "error": "\n".join(errors)[:4000] if errors else None,
        "files_checked": checked_files,
    }


def validate_docker(project_path: Path) -> dict:
    """Build the project's Docker image to validate its Dockerfile."""

    started = time.perf_counter()
    dockerfile = project_path / "Dockerfile"

    if not dockerfile.is_file():
        return {
            "name": "Docker build validation",
            "status": "SKIPPED",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": "No root Dockerfile found.",
        }

    if shutil.which("docker") is None:
        return {
            "name": "Docker build validation",
            "status": "SKIPPED",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": "Docker CLI is not installed or not in PATH.",
        }

    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "-t",
                "relqon-validation:local",
                "-f",
                str(dockerfile),
                str(project_path),
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

        error = None

        if result.returncode != 0:
            error = (
                result.stderr.strip()
                or result.stdout.strip()
                or "Docker build failed."
            )[-4000:]

        return {
            "name": "Docker build validation",
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": error,
        }

    except subprocess.TimeoutExpired:
        return {
            "name": "Docker build validation",
            "status": "FAIL",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": "Docker build timed out after 300 seconds.",
        }
    except OSError as exc:
        return {
            "name": "Docker build validation",
            "status": "FAIL",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": str(exc),
        }


def test_python_failure_detection() -> dict:
    """Confirm that Relqon's Python syntax check catches broken code."""

    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="relqon-python-test-") as temp:
        test_file = Path(temp) / "broken_test.py"
        test_file.write_text(
            "def broken_function(:\n",
            encoding="utf-8",
        )

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "py_compile",
                    str(test_file),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

            detected = (
                result.returncode != 0
                and "SyntaxError" in result.stderr
            )

            return {
                "name": "Python failure detection test",
                "status": "PASS" if detected else "FAIL",
                "duration_seconds": round(
                    time.perf_counter() - started, 3
                ),
                "error": (
                    None
                    if detected
                    else "The intentional Python syntax error was not detected."
                ),
            }

        except (subprocess.TimeoutExpired, OSError) as exc:
            return {
                "name": "Python failure detection test",
                "status": "FAIL",
                "duration_seconds": round(
                    time.perf_counter() - started, 3
                ),
                "error": str(exc),
            }


def test_failure_detection(project_path: Path) -> dict:
    """Confirm that Docker failure detection works."""

    started = time.perf_counter()
    test_dockerfile = (
        project_path / "tests" / "docker_failure" / "Dockerfile"
    )
    invalid_image = "this-image-does-not-exist-relqon:999"

    if not test_dockerfile.is_file():
        return {
            "name": "Docker failure detection test",
            "status": "SKIPPED",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": "Docker failure-test Dockerfile not found.",
        }

    if shutil.which("docker") is None:
        return {
            "name": "Docker failure detection test",
            "status": "SKIPPED",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": "Docker CLI is not installed or not in PATH.",
        }

    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--pull",
                "-f",
                str(test_dockerfile),
                "-t",
                "relqon-intentional-failure-test:local",
                str(test_dockerfile.parent),
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )

        output = result.stdout + "\n" + result.stderr

        detected = (
            result.returncode != 0
            and invalid_image in output
        )

        return {
            "name": "Docker failure detection test",
            "status": "PASS" if detected else "FAIL",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": (
                None
                if detected
                else (
                    "Expected Docker failure was not confirmed. "
                    "Check Docker output and the test Dockerfile."
                )
            ),
        }

    except subprocess.TimeoutExpired:
        return {
            "name": "Docker failure detection test",
            "status": "FAIL",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": "Docker failure test timed out.",
        }
    except OSError as exc:
        return {
            "name": "Docker failure detection test",
            "status": "FAIL",
            "duration_seconds": round(
                time.perf_counter() - started, 3
            ),
            "error": str(exc),
        }


def generate_report(
    project_path: Path,
    changed_files: list[str],
    impact: dict,
    checks: list[dict],
    started_at: str,
    total_duration: float,
) -> Path:
    """Write validation results to a JSON report."""

    statuses = [check["status"] for check in checks]

    if "FAIL" in statuses:
        overall_status = "FAIL"
    elif "SKIPPED" in statuses:
        overall_status = "SKIPPED"
    else:
        overall_status = "PASS"

    report = {
        "project": project_path.name,
        "timestamp": started_at,
        "duration_seconds": round(total_duration, 3),
        "changed_files": changed_files,
        "impact_analysis": impact,
        "checks": checks,
        "summary": {
            "passed": statuses.count("PASS"),
            "failed": statuses.count("FAIL"),
            "skipped": statuses.count("SKIPPED"),
        },
        "overall_status": overall_status,
    }

    reports_dir = project_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_path = reports_dir / "validation-report.json"
    report_path.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    return report_path


def run_pytest(project_path: Path) -> dict:
    """Run unit tests and return a structured result for the JSON report."""

    started = time.perf_counter()

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-v",
                "--ignore=tests/python_validation/broken_test.py",
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        output = (result.stdout + "\n" + result.stderr).strip()

        return {
            "name": "Pytest unit tests",
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": None if result.returncode == 0 else output[-4000:],
            "output": output[-4000:],
        }

    except subprocess.TimeoutExpired:
        return {
            "name": "Pytest unit tests",
            "status": "FAIL",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": "Pytest timed out after 120 seconds.",
        }

    except OSError as exc:
        return {
            "name": "Pytest unit tests",
            "status": "FAIL",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Relqon - Automated DevOps Change Impact & Recovery Platform"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Detect changes and run relevant validations.",
    )
    run_parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Path to the project directory (default: current directory).",
    )

    args = parser.parse_args()
    project_path = Path(args.project_path).resolve()

    if not project_path.is_dir():
        print(f"Error: Project directory not found: {project_path}")
        return 1

    started_clock = datetime.now().astimezone().isoformat()
    started = time.perf_counter()

    _, changed_files = detect_changes(project_path)
    impact = analyse_impact(changed_files)

    print("\nRelqon - Change Impact Analysis")

    if impact["checks"]:
        print("Relevant checks identified:")
        for check in impact["checks"]:
            print(f"  - {check}")
    else:
        print("No production validation checks required.")

    for reason in impact["reasons"]:
        print(f"  Reason: {reason}")

    checks = []
    checks.append(run_pytest(project_path))

    if "python_check" in impact["checks"]:
        checks.append(validate_python(project_path, changed_files))

    if "docker_build" in impact["checks"]:
        checks.append(validate_docker(project_path))

    if "kubernetes_check" in impact["checks"]:
        checks.append({
            "name": "Kubernetes validation",
            "status": "SKIPPED",
            "duration_seconds": 0,
            "error": "Kubernetes validation is not implemented yet.",
        })

    if "terraform_check" in impact["checks"]:
        checks.append({
            "name": "Terraform validation",
            "status": "SKIPPED",
            "duration_seconds": 0,
            "error": "Terraform validation is not implemented yet.",
        })

    # Self-tests run independently of the changed files.
    checks.append(test_python_failure_detection())
    checks.append(test_failure_detection(project_path))

    print("\nRelqon - Validation Summary")

    for check in checks:
        duration = check.get("duration_seconds", 0)
        print(
            f'{check["name"]}: {check["status"]} '
            f'({duration:.3f} seconds)'
        )

        if check.get("error"):
            print(f'  Details: {check["error"]}')

    total_duration = time.perf_counter() - started

    report_path = generate_report(
        project_path,
        changed_files,
        impact,
        checks,
        started_clock,
        total_duration,
    )

    print(f"\nJSON report saved: {report_path}")

    statuses = [check["status"] for check in checks]

    if "FAIL" in statuses:
        return 1

    if "SKIPPED" in statuses:
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

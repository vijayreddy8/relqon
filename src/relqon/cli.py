
import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path


FILE_TYPES = {
    ".py": "Python Code",
    ".js": "JavaScript Code",
    ".ts": "TypeScript Code",
    ".java": "Java Code",
    ".go": "Go Code",
    ".yaml": "YAML Configuration",
    ".yml": "YAML Configuration",
    ".json": "JSON Configuration",
    ".tf": "Terraform",
    ".sh": "Shell Script",
    ".ps1": "PowerShell Script",
    ".sql": "Database Script",
    ".toml": "Project Configuration",
}

SPECIAL_FILES = {
    "Dockerfile": "Docker Configuration",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    "Makefile": "Build Automation",
}


def classify_file(filename: str) -> str:
    """Classify a changed file by name or extension."""

    name = Path(filename).name

    if name in SPECIAL_FILES:
        return SPECIAL_FILES[name]
    if name == "Jenkinsfile":
        return "Jenkins Pipeline"
    if name == ".gitignore":
        return "Git Configuration"
    if name == "requirements.txt":
        return "Python Dependencies"
    if name == "package.json":
        return "Node.js Dependencies"
    if name == "Chart.yaml":
        return "Helm Chart"
    if name.endswith(".tfvars"):
        return "Terraform Variables"

    if name.endswith((".yaml", ".yml")):
        if "k8s" in filename.lower() or "kubernetes" in filename.lower():
            return "Kubernetes Configuration"

    return FILE_TYPES.get(Path(name).suffix.lower(), "Other File")


def get_changed_files(project_path: Path) -> list[str] | None:
    """Return changed file paths, or None on Git error."""

    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=project_path,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print("ERROR: Unable to read Git status.")
        if result.stderr.strip():
            print(result.stderr.strip())
        return None

    return [
        line[3:].strip()
        for line in result.stdout.splitlines()
        if len(line) >= 4
    ]


def detect_changes(project_path: Path) -> tuple[int, list[str]]:
    """Detect and classify changed files."""

    if not (project_path / ".git").exists():
        print("ERROR: This folder is not a Git repository.")
        return 1, []

    changed_files = get_changed_files(project_path)

    if changed_files is None:
        return 1, []

    print("\nRelqon - Change Intelligence")
    print("----------------------------")

    if not changed_files:
        print("Working tree is clean. No changes detected.")
        return 0, []

    print(f"Detected {len(changed_files)} changed file(s):\n")

    for filename in changed_files:
        print(f"  File: {filename}")
        print(f"  Type: {classify_file(filename)}\n")

    print("Change classification complete.")
    return 0, changed_files


def validate_docker(project_path: Path) -> dict:
    """Build the project's Docker image and capture evidence."""

    started = time.perf_counter()
    dockerfile = project_path / "Dockerfile"

    if not dockerfile.is_file():
        return {
            "name": "Docker build",
            "status": "SKIPPED",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": "No Dockerfile found.",
        }

    if shutil.which("docker") is None:
        return {
            "name": "Docker build",
            "status": "FAIL",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": "Docker CLI not found on PATH.",
        }

    try:
        result = subprocess.run(
            [
                "docker", "build",
                "--tag", "relqon-validation",
                str(project_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

        if result.returncode == 0:
            return {
                "name": "Docker build",
                "status": "PASS",
                "duration_seconds": round(time.perf_counter() - started, 3),
                "error": None,
            }

        error = result.stderr.strip() or "Docker build failed."
        return {
            "name": "Docker build",
            "status": "FAIL",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": error[-4000:],
        }

    except subprocess.TimeoutExpired:
        error = "Docker build timed out after 300 seconds."
    except OSError as exc:
        error = str(exc)

    return {
        "name": "Docker build",
        "status": "FAIL",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "error": error,
    }


def test_failure_detection(project_path: Path) -> dict:
    """Verify that an intentionally invalid Dockerfile fails to build."""

    started = time.perf_counter()
    test_dockerfile = (
        project_path / "tests" / "docker_failure" / "Dockerfile"
    )

    if not test_dockerfile.is_file():
        return {
            "name": "Failure detection test",
            "status": "SKIPPED",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": "Failure-test Dockerfile not found.",
        }

    if shutil.which("docker") is None:
        return {
            "name": "Failure detection test",
            "status": "SKIPPED",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": "Docker CLI not found on PATH.",
        }

    try:
        result = subprocess.run(
            [
                "docker", "build",
                "--tag", "relqon-failure-validation",
                "--file", str(test_dockerfile),
                str(test_dockerfile.parent),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        # A failed build is only a valid test result if it failed
        # for the expected missing-image reason.
        output = (result.stdout + "\n" + result.stderr).lower()
        expected_failure = (
            result.returncode != 0
            and "this-image-does-not-exist-relqon" in output
        )

        if expected_failure:
            status = "PASS"
            error = None
        elif result.returncode == 0:
            status = "FAIL"
            error = "The invalid Dockerfile unexpectedly built successfully."
        else:
            status = "FAIL"
            error = (
                "Docker failed, but the expected missing-image reason "
                "was not found in the output."
            )

        return {
            "name": "Failure detection test",
            "status": status,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": error,
        }

    except subprocess.TimeoutExpired:
        error = "Failure-detection test timed out after 120 seconds."
    except OSError as exc:
        error = str(exc)

    return {
        "name": "Failure detection test",
        "status": "FAIL",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "error": error,
    }


def generate_report(
    project_path: Path,
    changed_files: list[str],
    checks: list[dict],
    started_at: str,
    total_duration: float,
) -> Path:
    """Write detailed validation results to a JSON report."""

    reports_dir = project_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    statuses = [check["status"] for check in checks]

    if "FAIL" in statuses:
        overall_status = "FAIL"
    elif "SKIPPED" in statuses:
        overall_status = "WARNING"
    else:
        overall_status = "PASS"

    report = {
        "project": "Relqon",
        "timestamp": started_at,
        "duration_seconds": round(total_duration, 3),
        "changed_files": [
            {
                "path": filename,
                "type": classify_file(filename),
            }
            for filename in changed_files
        ],
        "checks": checks,
        "summary": {
            "passed": statuses.count("PASS"),
            "failed": statuses.count("FAIL"),
            "skipped": statuses.count("SKIPPED"),
        },
        "overall_status": overall_status,
    }

    report_path = reports_dir / "validation-report.json"
    report_path.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="relqon",
        description="Automated DevOps change detection and Docker validation",
    )
    parser.add_argument(
        "command",
        choices=["run"],
        help="Analyse project changes and validate Docker",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the Git project",
    )

    args = parser.parse_args()
    project_path = Path(args.path).resolve()
    started_at = datetime.now().astimezone().isoformat()
    run_started = time.perf_counter()

    detection_code, changed_files = detect_changes(project_path)

    if detection_code != 0:
        return detection_code

    checks = [
        validate_docker(project_path),
        test_failure_detection(project_path),
    ]

    print("\nRelqon - Validation Summary")
    print("---------------------------")

    for check in checks:
        print(
            f"{check['name']}: {check['status']} "
            f"({check['duration_seconds']} seconds)"
        )
        if check["error"]:
            print(f"  Details: {check['error']}")

    total_duration = time.perf_counter() - run_started

    try:
        report_path = generate_report(
            project_path,
            changed_files,
            checks,
            started_at,
            total_duration,
        )
        print(f"\nJSON report saved: {report_path}")
    except (OSError, TypeError, ValueError) as exc:
        print(f"\nERROR: Could not save JSON report: {exc}")
        return 1

    if any(check["status"] == "FAIL" for check in checks):
        return 1

    if any(check["status"] == "SKIPPED" for check in checks):
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

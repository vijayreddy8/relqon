
import argparse
import json
import shutil
import subprocess
import sys
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
    """Return changed paths reported by Git."""

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


def analyse_impact(changed_files: list[str]) -> dict:
    """Select checks based on changed-file patterns."""

    checks = set()
    reasons = []

    for filename in changed_files:
        name = Path(filename).name.lower()
        suffix = Path(filename).suffix.lower()

        if name == "dockerfile" or name in {
            "docker-compose.yml",
            "docker-compose.yaml",
        }:
            checks.add("docker_build")
            reasons.append(f"{filename}: Docker configuration changed.")

        if suffix == ".py" or name in {
            "requirements.txt",
            "pyproject.toml",
        }:
            checks.add("python_check")
            reasons.append(f"{filename}: Python code or dependencies changed.")

        if suffix in {".yaml", ".yml"} and (
            "k8s" in filename.lower()
            or "kubernetes" in filename.lower()
            or "helm" in filename.lower()
            or name == "chart.yaml"
        ):
            checks.add("kubernetes_check")
            reasons.append(
                f"{filename}: Kubernetes or Helm configuration changed."
            )

        if suffix in {".tf", ".tfvars"}:
            checks.add("terraform_check")
            reasons.append(f"{filename}: Terraform configuration changed.")

    return {"checks": sorted(checks), "reasons": reasons}


def validate_python(project_path: Path, changed_files: list[str]) -> dict:
    """Compile changed Python files to detect syntax errors."""

    started = time.perf_counter()

    python_files = [
        filename for filename in changed_files
        if Path(filename).suffix.lower() == ".py"
    ]

    if not python_files:
        return {
            "name": "Python syntax validation",
            "status": "SKIPPED",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": (
                "Python dependency changes were detected, but no changed "
                "Python source file was available to compile."
            ),
        }

    errors = []

    for filename in python_files:
        file_path = (project_path / filename).resolve()

        # Do not compile files outside the selected project.
        if not file_path.is_relative_to(project_path.resolve()):
            errors.append(f"{filename}: path is outside the project.")
            continue

        if not file_path.is_file():
            errors.append(f"{filename}: file not found.")
            continue

        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(file_path)],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

            if result.returncode != 0:
                message = result.stderr.strip() or "Python compilation failed."
                errors.append(f"{filename}: {message}")

        except subprocess.TimeoutExpired:
            errors.append(f"{filename}: compilation timed out.")
        except OSError as exc:
            errors.append(f"{filename}: {exc}")

    if errors:
        status = "FAIL"
        error = "\n".join(errors)[:4000]
    else:
        status = "PASS"
        error = None

    return {
        "name": "Python syntax validation",
        "status": status,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "error": error,
        "files_checked": python_files,
    }


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
                "docker", "build", "--tag", "relqon-validation",
                str(project_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

        if result.returncode == 0:
            status, error = "PASS", None
        else:
            status = "FAIL"
            error = (
                result.stderr.strip() or "Docker build failed."
            )[-4000:]

    except subprocess.TimeoutExpired:
        status, error = "FAIL", "Docker build timed out after 300 seconds."
    except OSError as exc:
        status, error = "FAIL", str(exc)

    return {
        "name": "Docker build",
        "status": status,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "error": error,
    }


def test_failure_detection(project_path: Path) -> dict:
    """Check the known invalid Dockerfile fails for the expected reason."""

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

        output = (result.stdout + "\n" + result.stderr).lower()
        expected_failure = (
            result.returncode != 0
            and "this-image-does-not-exist-relqon" in output
        )

        if expected_failure:
            status, error = "PASS", None
        elif result.returncode == 0:
            status = "FAIL"
            error = "The invalid Dockerfile unexpectedly built."
        else:
            status = "FAIL"
            error = "Docker failed for an unexpected reason."

    except subprocess.TimeoutExpired:
        status, error = "FAIL", "Failure-detection test timed out."
    except OSError as exc:
        status, error = "FAIL", str(exc)

    return {
        "name": "Failure detection test",
        "status": status,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "error": error,
    }


def generate_report(
    project_path: Path,
    changed_files: list[str],
    impact: dict,
    checks: list[dict],
    started_at: str,
    total_duration: float,
) -> Path:
    """Write change-impact and validation results to JSON."""

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
            {"path": filename, "type": classify_file(filename)}
            for filename in changed_files
        ],
        "impact_analysis": impact,
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
        description="DevOps change impact analysis and validation",
    )
    parser.add_argument("command", choices=["run"])
    parser.add_argument("path", nargs="?", default=".")

    args = parser.parse_args()
    project_path = Path(args.path).resolve()
    started_at = datetime.now().astimezone().isoformat()
    run_started = time.perf_counter()

    detection_code, changed_files = detect_changes(project_path)

    if detection_code != 0:
        return detection_code

    impact = analyse_impact(changed_files)

    print("\nRelqon - Change Impact Analysis")
    print("------------------------------")

    if impact["checks"]:
        print("Relevant checks identified:")
        for check_name in impact["checks"]:
            print(f"  - {check_name}")
        for reason in impact["reasons"]:
            print(f"  Reason: {reason}")
    else:
        print("No supported validation checks matched these changes.")

    checks = []

    if "python_check" in impact["checks"]:
        checks.append(validate_python(project_path, changed_files))

    if "docker_build" in impact["checks"]:
        checks.append(validate_docker(project_path))

    for check_name, display_name in [
        ("kubernetes_check", "Kubernetes checks"),
        ("terraform_check", "Terraform checks"),
    ]:
        if check_name in impact["checks"]:
            checks.append({
                "name": display_name,
                "status": "SKIPPED",
                "duration_seconds": 0,
                "error": "Impact rule exists; validator is not implemented yet.",
            })

    checks.append(test_failure_detection(project_path))

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
            project_path, changed_files, impact, checks,
            started_at, total_duration,
        )
        print(f"\nJSON report saved: {report_path}")
    except (OSError, TypeError, ValueError) as exc:
        print(f"ERROR: Could not save JSON report: {exc}")
        return 1

    if any(check["status"] == "FAIL" for check in checks):
        return 1
    if any(check["status"] == "SKIPPED" for check in checks):
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


import argparse
import json
import shutil
import subprocess
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
    """Classify a changed file by its name or extension."""

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
    """Return changed files, or None if Git reports an error."""

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


def detect_changes(project_path: Path) -> int:
    """Detect and classify changed files."""

    if not (project_path / ".git").exists():
        print("ERROR: This folder is not a Git repository.")
        return 1

    changed_files = get_changed_files(project_path)

    if changed_files is None:
        return 1

    print("\nRelqon - Change Intelligence")
    print("----------------------------")

    if not changed_files:
        print("Working tree is clean. No changes detected.")
        return 0

    print(f"Detected {len(changed_files)} changed file(s):\n")

    for filename in changed_files:
        category = classify_file(filename)
        print(f"  File: {filename}")
        print(f"  Type: {category}\n")

    print("Change classification complete.")
    return 0


def validate_docker(project_path: Path) -> bool:
    """Build the project's Docker image."""

    dockerfile = project_path / "Dockerfile"

    if not dockerfile.is_file():
        print("SKIPPED: No Dockerfile found.")
        return True

    if shutil.which("docker") is None:
        print("FAIL: Docker CLI is not installed or not on PATH.")
        return False

    print("\nRelqon - Docker Validation")
    print("--------------------------")

    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--tag",
                "relqon-validation",
                str(project_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("FAIL: Docker build timed out after 300 seconds.")
        return False

    if result.returncode == 0:
        print("PASS: Docker image built successfully.")
        return True

    print("FAIL: Docker image build failed.")

    if result.stderr.strip():
        print(result.stderr.strip())

    return False


def test_failure_detection(project_path: Path) -> bool:
    """Verify that an intentionally invalid Dockerfile fails to build."""

    test_dockerfile = (
        project_path / "tests" / "docker_failure" / "Dockerfile"
    )

    if not test_dockerfile.is_file():
        print("SKIPPED: Docker failure-test Dockerfile not found.")
        return False

    if shutil.which("docker") is None:
        print("FAIL: Docker CLI is not installed or not on PATH.")
        return False

    print("\nRelqon - Failure Detection Test")
    print("--------------------------------")

    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--tag",
                "relqon-failure-validation",
                "--file",
                str(test_dockerfile),
                str(test_dockerfile.parent),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("FAIL: Failure-detection test timed out.")
        return False

    if result.returncode != 0:
        print("PASS: Expected Docker build failure detected.")
        return True

    print("FAIL: Invalid Dockerfile unexpectedly built successfully.")
    return False


def generate_report(
    project_path: Path,
    docker_passed: bool,
    failure_test_passed: bool,
) -> Path:
    """Save validation results to a JSON report."""

    reports_dir = project_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "project": "Relqon",
        "timestamp": datetime.now().astimezone().isoformat(),
        "results": {
            "docker_build": "PASS" if docker_passed else "FAIL",
            "failure_detection_test": (
                "PASS" if failure_test_passed else "FAIL"
            ),
        },
        "overall_status": (
            "PASS"
            if docker_passed and failure_test_passed
            else "FAIL"
        ),
    }

    report_path = reports_dir / "validation-report.json"

    report_path.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    print(f"\nJSON report saved: {report_path}")

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

    if detect_changes(project_path) != 0:
        return 1

    docker_passed = validate_docker(project_path)
    failure_test_passed = test_failure_detection(project_path)

    print("\nRelqon - Validation Summary")
    print("---------------------------")
    print(f"Docker build: {'PASS' if docker_passed else 'FAIL'}")
    print(
        "Failure detection test: "
        f"{'PASS' if failure_test_passed else 'FAIL'}"
    )

    try:
        generate_report(
            project_path,
            docker_passed,
            failure_test_passed,
        )
    except OSError as error:
        print(f"ERROR: Could not save JSON report: {error}")
        return 1

    return 0 if docker_passed and failure_test_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

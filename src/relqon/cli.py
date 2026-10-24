
import argparse
import shutil
import subprocess
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
    """Return changed file paths, or None if Git reports an error."""

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

    files = []

    for line in result.stdout.splitlines():
        if len(line) >= 4:
            files.append(line[3:].strip())

    return files


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
    """Build the project's Docker image to validate its Dockerfile."""

    dockerfile = project_path / "Dockerfile"

    if not dockerfile.is_file():
        print("SKIPPED: No Dockerfile found.")
        return True

    if shutil.which("docker") is None:
        print("FAIL: Docker CLI is not installed or not on PATH.")
        return False

    print("\nRelqon - Docker Validation")
    print("--------------------------")

    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            "relqon-validation",
            str(project_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0:
        print("PASS: Docker image built successfully.")
        return True

    print("FAIL: Docker image build failed.")

    if result.stdout.strip():
        print(result.stdout.strip())

    if result.stderr.strip():
        print(result.stderr.strip())

    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="relqon",
        description="Automated DevOps change detection and validation",
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

    print("\nRelqon - Validation Summary")
    print("---------------------------")
    print(f"Docker validation: {'PASS' if docker_passed else 'FAIL'}")

    return 0 if docker_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

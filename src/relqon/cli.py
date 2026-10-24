import argparse
import subprocess
from pathlib import Path


def detect_changes(project_path: Path) -> int:
    """Detect changed files in a Git repository."""

    if not (project_path / ".git").exists():
        print("ERROR: This folder is not a Git repository.")
        return 1

    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=project_path,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print("ERROR: Unable to read Git status.")
        return 1

    print("\nRelqon - Change Detection")
    print("-------------------------")

    changes = result.stdout.strip()

    if not changes:
        print("Working tree is clean. No changes detected.")
        return 0

    print("Changes detected:\n")

    for line in changes.splitlines():
        print(f"  {line}")

    print(f"\nTotal changed entries: {len(changes.splitlines())}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="relqon",
        description="Automated DevOps change detection",
    )
    parser.add_argument(
        "command",
        choices=["run"],
        help="Run change detection",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the Git project (default: current directory)",
    )

    args = parser.parse_args()
    return detect_changes(Path(args.path).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
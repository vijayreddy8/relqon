
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


def _validate_kubernetes_document(document: dict, filename: str, index: int) -> None:
    """Validate common Kubernetes fields and Deployment/Service semantics."""

    context = f"{filename}: document {index}"
    missing = [
        field for field in ("apiVersion", "kind", "metadata")
        if field not in document
    ]
    if missing:
        raise ValueError(
            f"{context} is missing required field(s): " + ", ".join(missing)
        )

    if not isinstance(document["apiVersion"], str) or not document["apiVersion"].strip():
        raise ValueError(f"{context} apiVersion must be a non-empty string.")
    if not isinstance(document["kind"], str) or not document["kind"].strip():
        raise ValueError(f"{context} kind must be a non-empty string.")
    if not isinstance(document["metadata"], dict):
        raise ValueError(f"{context} metadata must be a YAML mapping/object.")
    if not isinstance(document["metadata"].get("name"), str) or not document["metadata"]["name"].strip():
        raise ValueError(f"{context} metadata.name is required.")

    kind = document["kind"]
    spec = document.get("spec")

    if kind in {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet"}:
        if not isinstance(spec, dict):
            raise ValueError(f"{context} {kind} spec must be a YAML mapping/object.")

        selector = spec.get("selector")
        if not isinstance(selector, dict) or not isinstance(selector.get("matchLabels"), dict) or not selector["matchLabels"]:
            raise ValueError(f"{context} {kind} spec.selector.matchLabels must be a non-empty mapping.")

        template = spec.get("template")
        if not isinstance(template, dict):
            raise ValueError(f"{context} {kind} spec.template must be a YAML mapping/object.")
        template_metadata = template.get("metadata")
        labels = template_metadata.get("labels") if isinstance(template_metadata, dict) else None
        if not isinstance(labels, dict) or not labels:
            raise ValueError(f"{context} {kind} spec.template.metadata.labels must be a non-empty mapping.")
        mismatched = [
            key for key, value in selector["matchLabels"].items()
            if labels.get(key) != value
        ]
        if mismatched:
            raise ValueError(
                f"{context} {kind} selector labels do not match pod-template labels: "
                + ", ".join(str(key) for key in mismatched)
            )

        pod_spec = template.get("spec")
        containers = pod_spec.get("containers") if isinstance(pod_spec, dict) else None
        if not isinstance(containers, list) or not containers:
            raise ValueError(f"{context} {kind} spec.template.spec.containers must be a non-empty list.")
        for container_index, container in enumerate(containers, start=1):
            if not isinstance(container, dict):
                raise ValueError(f"{context} container {container_index} must be a mapping.")
            if not isinstance(container.get("name"), str) or not container["name"].strip():
                raise ValueError(f"{context} container {container_index} requires a name.")
            if not isinstance(container.get("image"), str) or not container["image"].strip():
                raise ValueError(f"{context} container {container_index} requires an image.")

        replicas = spec.get("replicas")
        if replicas is not None and (
            isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0
        ):
            raise ValueError(f"{context} {kind} spec.replicas must be a non-negative integer.")

    elif kind == "Service":
        if not isinstance(spec, dict):
            raise ValueError(f"{context} Service spec must be a YAML mapping/object.")
        if spec.get("type", "ClusterIP") != "ExternalName":
            ports = spec.get("ports")
            if not isinstance(ports, list) or not ports:
                raise ValueError(f"{context} Service spec.ports must be a non-empty list.")
            for port_index, port in enumerate(ports, start=1):
                if not isinstance(port, dict):
                    raise ValueError(f"{context} Service port {port_index} must be a mapping.")
                number = port.get("port")
                if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 65535:
                    raise ValueError(f"{context} Service port {port_index}.port must be an integer from 1 to 65535.")
                target = port.get("targetPort")
                if target is not None and (
                    isinstance(target, bool)
                    or not (isinstance(target, int) and 1 <= target <= 65535)
                    and not (isinstance(target, str) and target.strip())
                ):
                    raise ValueError(f"{context} Service port {port_index}.targetPort must be a valid port number or name.")
                protocol = port.get("protocol", "TCP")
                if protocol not in {"TCP", "UDP", "SCTP"}:
                    raise ValueError(f"{context} Service port {port_index}.protocol must be TCP, UDP, or SCTP.")
        selector = spec.get("selector")
        if selector is not None and not isinstance(selector, dict):
            raise ValueError(f"{context} Service spec.selector must be a mapping when provided.")

    elif kind == "Pod":
        spec = document.get("spec")
        containers = spec.get("containers") if isinstance(spec, dict) else None
        if not isinstance(containers, list) or not containers:
            raise ValueError(f"{context} Pod spec.containers must be a non-empty list.")
        for container_index, container in enumerate(containers, start=1):
            if not isinstance(container, dict) or not isinstance(container.get("image"), str) or not container["image"].strip():
                raise ValueError(f"{context} Pod container {container_index} requires an image.")


def validate_kubernetes(
    project_path: Path,
    changed_files: list[str],
) -> dict:
    """Validate changed Kubernetes YAML manifests and Helm chart metadata."""

    started = time.perf_counter()
    candidates = []

    for filename in changed_files:
        path = Path(filename)
        parts = {part.lower() for part in path.parts}
        name = path.name.lower()
        is_kubernetes_path = bool(
            {"k8s", "kubernetes", "helm"} & parts
        ) or name == "chart.yaml"

        if not is_kubernetes_path:
            continue

        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue

        # Helm templates contain Go-template expressions and need helm lint.
        if "templates" in parts:
            continue

        candidates.append(filename)

    if not candidates:
        return {
            "name": "Kubernetes YAML validation",
            "status": "SKIPPED",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": "No changed Kubernetes YAML manifests or Chart.yaml files to validate.",
            "files_checked": [],
            "kubectl_validation": {
                "status": "SKIPPED",
                "details": "No manifest files were selected.",
            },
        }

    try:
        import yaml
    except ImportError:
        return {
            "name": "Kubernetes YAML validation",
            "status": "FAIL",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": "PyYAML is required. Install it with: python -m pip install pyyaml",
            "files_checked": [],
        }

    errors = []
    checked_files = []
    manifest_files = []

    for filename in candidates:
        file_path = (project_path / filename).resolve()

        try:
            file_path.relative_to(project_path.resolve())
        except ValueError:
            errors.append(f"{filename}: file is outside the project directory.")
            continue

        # A deleted manifest is a valid change; there is nothing left to parse.
        if not file_path.exists():
            continue

        try:
            with file_path.open("r", encoding="utf-8") as stream:
                documents = list(yaml.safe_load_all(stream))

            if not documents or all(document is None for document in documents):
                raise ValueError("YAML file is empty.")

            if file_path.name.lower() == "chart.yaml":
                chart = documents[0]
                if not isinstance(chart, dict):
                    raise ValueError("Chart.yaml must contain a YAML mapping/object.")
                for field in ("apiVersion", "name", "version"):
                    if not isinstance(chart.get(field), str) or not chart[field].strip():
                        raise ValueError(f"Chart.yaml requires a non-empty '{field}' field.")
                if chart["apiVersion"] not in {"v1", "v2"}:
                    raise ValueError("Chart.yaml apiVersion must be 'v1' or 'v2'.")
            else:
                for index, document in enumerate(documents, start=1):
                    if document is None:
                        continue
                    if not isinstance(document, dict):
                        raise ValueError(
                            f"Document {index} must be a YAML mapping/object."
                        )
                    _validate_kubernetes_document(document, filename, index)

            checked_files.append(filename)
            if file_path.name.lower() != "chart.yaml":
                manifest_files.append(filename)

        except (yaml.YAMLError, OSError, ValueError) as exc:
            errors.append(f"{filename}: {exc}")

    kubectl_result = {
        "status": "SKIPPED",
        "details": "kubectl is not installed; YAML syntax and basic manifest structure were checked.",
    }

    kubectl = shutil.which("kubectl")
    if kubectl and manifest_files and not errors:
        kubectl_errors = []
        kubectl_checked = []
        for filename in manifest_files:
            try:
                result = subprocess.run(
                    [
                        kubectl,
                        "apply",
                        "--dry-run=client",
                        "--validate=false",
                        "-f",
                        str((project_path / filename).resolve()),
                    ],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=60,
                )
                output = (result.stdout + "\\n" + result.stderr).strip()[-2000:]
                kubectl_checked.append({
                    "file": filename,
                    "status": "PASS" if result.returncode == 0 else "FAIL",
                    "output": output,
                })
                if result.returncode != 0:
                    kubectl_errors.append(
                        f"{filename}: {output or 'kubectl dry-run failed'}"
                    )
            except subprocess.TimeoutExpired:
                kubectl_errors.append(f"{filename}: kubectl dry-run timed out after 60 seconds.")
                kubectl_checked.append({"file": filename, "status": "FAIL", "output": "Timed out after 60 seconds."})
            except OSError as exc:
                kubectl_errors.append(f"{filename}: {exc}")
                kubectl_checked.append({"file": filename, "status": "FAIL", "output": str(exc)})

        kubectl_result = {
            "status": "PASS" if not kubectl_errors else "FAIL",
            "details": (
                "kubectl client dry-run passed for all selected manifests."
                if not kubectl_errors
                else "\\n".join(kubectl_errors)[:4000]
            ),
            "command": "kubectl apply --dry-run=client --validate=false -f <manifest>",
            "files_checked": kubectl_checked,
        }
        if kubectl_errors:
            errors.extend(kubectl_errors)

    return {
        "name": "Kubernetes YAML validation",
        "status": "FAIL" if errors else "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "error": "\n".join(errors)[:4000] if errors else None,
        "files_checked": checked_files,
        "kubectl_validation": kubectl_result,
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
        checks.append(validate_kubernetes(project_path, changed_files))

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

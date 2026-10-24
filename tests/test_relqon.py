
import sys
from pathlib import Path

# Make the project's src directory importable.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from relqon.cli import analyse_impact


def test_python_file_triggers_python_check():
    result = analyse_impact(["src/relqon/example.py"])

    assert "python_check" in result["checks"]


def test_dockerfile_triggers_docker_build():
    result = analyse_impact(["Dockerfile"])

    assert "docker_build" in result["checks"]


def test_terraform_file_triggers_terraform_check():
    result = analyse_impact(["infra/main.tf"])

    assert "terraform_check" in result["checks"]


def test_kubernetes_file_triggers_kubernetes_check():
    result = analyse_impact(["k8s/deployment.yaml"])

    assert "kubernetes_check" in result["checks"]


def test_markdown_file_triggers_no_validation():
    result = analyse_impact(["README.md"])

    assert result["checks"] == []


def test_multiple_changes_trigger_multiple_checks():
    result = analyse_impact([
        "src/relqon/example.py",
        "Dockerfile",
        "infra/main.tf",
    ])

    assert "python_check" in result["checks"]
    assert "docker_build" in result["checks"]
    assert "terraform_check" in result["checks"]



def test_kubernetes_yaml_validates_manifest_structure(tmp_path):
    from relqon.cli import validate_kubernetes

    manifest = tmp_path / "k8s" / "deployment.yaml"
    manifest.parent.mkdir()
    manifest.write_text(
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        "  name: sample-app\n",
        encoding="utf-8",
    )

    result = validate_kubernetes(tmp_path, ["k8s/deployment.yaml"])
    assert result["status"] == "PASS"
    assert result["files_checked"] == ["k8s/deployment.yaml"]


def test_kubernetes_yaml_rejects_missing_manifest_fields(tmp_path):
    from relqon.cli import validate_kubernetes

    manifest = tmp_path / "k8s" / "deployment.yaml"
    manifest.parent.mkdir()
    manifest.write_text(
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        "  labels:\n"
        "    app: sample\n",
        encoding="utf-8",
    )

    result = validate_kubernetes(tmp_path, ["k8s/deployment.yaml"])
    assert result["status"] == "FAIL"
    assert "metadata.name is required" in result["error"]


def test_chart_yaml_triggers_kubernetes_check():
    result = analyse_impact(["helm/Chart.yaml"])
    assert "kubernetes_check" in result["checks"]

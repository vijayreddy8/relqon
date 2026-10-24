
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


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



def test_kubernetes_yaml_validates_manifest_structure(tmp_path, monkeypatch):
    import relqon.cli as cli
    validate_kubernetes = cli.validate_kubernetes
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    manifest = tmp_path / "k8s" / "deployment.yaml"
    manifest.parent.mkdir()
    manifest.write_text(
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        "  name: sample-app\n"
        "spec:\n"
        "  selector:\n"
        "    matchLabels:\n"
        "      app: sample\n"
        "  template:\n"
        "    metadata:\n"
        "      labels:\n"
        "        app: sample\n"
        "    spec:\n"
        "      containers:\n"
        "        - name: app\n"
        "          image: nginx:stable\n",
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

def test_deployment_rejects_selector_mismatch(tmp_path):
    from relqon.cli import validate_kubernetes

    manifest = tmp_path / "k8s" / "deployment.yaml"
    manifest.parent.mkdir()
    manifest.write_text(
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        "  name: sample-app\n"
        "spec:\n"
        "  selector:\n"
        "    matchLabels:\n"
        "      app: expected\n"
        "  template:\n"
        "    metadata:\n"
        "      labels:\n"
        "        app: actual\n"
        "    spec:\n"
        "      containers:\n"
        "        - name: app\n"
        "          image: nginx:stable\n",
        encoding="utf-8",
    )

    result = validate_kubernetes(tmp_path, ["k8s/deployment.yaml"])
    assert result["status"] == "FAIL"
    assert "selector labels do not match" in result["error"]


def test_deployment_requires_container_image(tmp_path):
    from relqon.cli import validate_kubernetes

    manifest = tmp_path / "k8s" / "deployment.yaml"
    manifest.parent.mkdir()
    manifest.write_text(
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        "  name: sample-app\n"
        "spec:\n"
        "  selector:\n"
        "    matchLabels:\n"
        "      app: sample\n"
        "  template:\n"
        "    metadata:\n"
        "      labels:\n"
        "        app: sample\n"
        "    spec:\n"
        "      containers:\n"
        "        - name: app\n",
        encoding="utf-8",
    )

    result = validate_kubernetes(tmp_path, ["k8s/deployment.yaml"])
    assert result["status"] == "FAIL"
    assert "requires an image" in result["error"]


def test_service_rejects_invalid_port(tmp_path):
    from relqon.cli import validate_kubernetes

    manifest = tmp_path / "k8s" / "service.yaml"
    manifest.parent.mkdir()
    manifest.write_text(
        "apiVersion: v1\n"
        "kind: Service\n"
        "metadata:\n"
        "  name: sample-service\n"
        "spec:\n"
        "  ports:\n"
        "    - port: 70000\n",
        encoding="utf-8",
    )

    result = validate_kubernetes(tmp_path, ["k8s/service.yaml"])
    assert result["status"] == "FAIL"
    assert "must be an integer from 1 to 65535" in result["error"]


def test_chart_yaml_requires_name_and_version(tmp_path):
    from relqon.cli import validate_kubernetes

    chart = tmp_path / "helm" / "Chart.yaml"
    chart.parent.mkdir()
    chart.write_text(
        "apiVersion: v2\n"
        "name: sample-chart\n",
        encoding="utf-8",
    )

    result = validate_kubernetes(tmp_path, ["helm/Chart.yaml"])
    assert result["status"] == "FAIL"
    assert "version" in result["error"]


def test_kubernetes_validation_reports_kubectl_evidence_when_available(tmp_path, monkeypatch):
    import relqon.cli as cli

    manifest = tmp_path / "k8s" / "service.yaml"
    manifest.parent.mkdir()
    manifest.write_text(
        "apiVersion: v1\n"
        "kind: Service\n"
        "metadata:\n"
        "  name: sample-service\n"
        "spec:\n"
        "  ports:\n"
        "    - port: 80\n",
        encoding="utf-8",
    )

    class FakeResult:
        returncode = 0
        stdout = "dry-run ok"
        stderr = ""

    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/kubectl" if name == "kubectl" else None)
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: FakeResult())

    result = cli.validate_kubernetes(tmp_path, ["k8s/service.yaml"])
    assert result["status"] == "PASS"
    assert result["kubectl_validation"]["status"] == "PASS"
    assert result["kubectl_validation"]["files_checked"][0]["file"] == "k8s/service.yaml"

def test_terraform_validation_runs_fmt_init_and_validate(tmp_path, monkeypatch):
    import relqon.cli as cli

    terraform_file = tmp_path / "infra" / "main.tf"
    terraform_file.parent.mkdir()
    terraform_file.write_text(
        'terraform { required_version = ">= 1.0.0" }\\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/terraform" if name == "terraform" else None)

    calls = []

    class FakeResult:
        returncode = 0
        stdout = "Success"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        return FakeResult()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    result = cli.validate_terraform(tmp_path, ["infra/main.tf"])

    assert result["status"] == "PASS"
    assert result["files_checked"] == ["infra/main.tf"]
    assert [command[1] for command in calls] == ["fmt", "init", "validate"]
    assert result["steps"][-1]["name"] == "terraform validate"


def test_terraform_validation_fails_when_format_check_fails(tmp_path, monkeypatch):
    import relqon.cli as cli

    terraform_file = tmp_path / "infra" / "main.tf"
    terraform_file.parent.mkdir()
    terraform_file.write_text('terraform {}\\n', encoding="utf-8")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/terraform" if name == "terraform" else None)

    class FakeResult:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return FakeResult(1, stdout="main.tf")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    result = cli.validate_terraform(tmp_path, ["infra/main.tf"])

    assert result["status"] == "FAIL"
    assert "formatting check failed" in result["error"]
    assert len(calls) == 1


def test_terraform_validation_skips_when_cli_missing(tmp_path, monkeypatch):
    import relqon.cli as cli

    terraform_file = tmp_path / "infra" / "main.tf"
    terraform_file.parent.mkdir()
    terraform_file.write_text("terraform {}\\n", encoding="utf-8")
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    result = cli.validate_terraform(tmp_path, ["infra/main.tf"])

    assert result["status"] == "SKIPPED"
    assert "not installed" in result["error"]



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

def test_recovery_guidance_for_terraform_format_failure():
    from relqon.cli import add_recovery_guidance

    result = add_recovery_guidance({
        "name": "Terraform validation",
        "status": "FAIL",
        "error": "Terraform formatting check failed.",
    })

    assert result["status"] == "FAIL"
    assert any("terraform fmt" in item for item in result["recovery_guidance"])


def test_recovery_guidance_for_missing_terraform_cli():
    from relqon.cli import add_recovery_guidance

    result = add_recovery_guidance({
        "name": "Terraform validation",
        "status": "SKIPPED",
        "error": "Terraform CLI is not installed or not in PATH.",
    })

    assert any("Install Terraform CLI" in item for item in result["recovery_guidance"])


def test_recovery_guidance_does_not_change_successful_checks():
    from relqon.cli import add_recovery_guidance

    result = add_recovery_guidance({
        "name": "Terraform validation",
        "status": "PASS",
        "error": None,
    })

    assert "recovery_guidance" not in result

def test_recovery_guidance_for_kubernetes_manifest_failure():
    from relqon.cli import add_recovery_guidance

    result = add_recovery_guidance({
        "name": "Kubernetes validation",
        "status": "FAIL",
        "error": "Manifest selector does not match pod template labels.",
    })

    assert len(result["recovery_guidance"]) >= 1
    assert any("manifest" in item.lower() or "kubectl" in item.lower() for item in result["recovery_guidance"])


def test_recovery_guidance_for_docker_build_failure():
    from relqon.cli import add_recovery_guidance

    result = add_recovery_guidance({
        "name": "Docker build",
        "status": "FAIL",
        "error": "Docker build failed.",
    })

    assert any("docker build" in item.lower() for item in result["recovery_guidance"])


def test_recovery_guidance_for_python_test_failure():
    from relqon.cli import add_recovery_guidance

    result = add_recovery_guidance({
        "name": "Pytest unit tests",
        "status": "FAIL",
        "error": "AssertionError in test example.",
    })

    assert any("traceback" in item.lower() or "python" in item.lower() for item in result["recovery_guidance"])

def test_python_validation_detects_invalid_syntax(tmp_path):
    from relqon.cli import validate_python

    broken = tmp_path / "src" / "broken.py"
    broken.parent.mkdir()
    broken.write_text("def broken_function(:\\n", encoding="utf-8")

    result = validate_python(tmp_path, ["src/broken.py"])

    assert result["status"] == "FAIL"
    assert "SyntaxError" in result["error"]


def test_docker_validation_detects_build_failure(tmp_path, monkeypatch):
    import relqon.cli as cli

    (tmp_path / "Dockerfile").write_text("FROM scratch\\n", encoding="utf-8")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "intentional build failure"

    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: FakeResult())

    result = cli.validate_docker(tmp_path)

    assert result["status"] == "FAIL"
    assert "intentional build failure" in result["error"]


def test_docker_validation_reports_missing_cli_as_skipped(tmp_path, monkeypatch):
    import relqon.cli as cli

    (tmp_path / "Dockerfile").write_text("FROM scratch\\n", encoding="utf-8")
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    result = cli.validate_docker(tmp_path)

    assert result["status"] == "SKIPPED"
    assert "not installed" in result["error"]


def test_failure_recovery_guidance_is_added_to_failed_report_check():
    from relqon.cli import add_recovery_guidance

    check = {
        "name": "Docker build validation",
        "status": "FAIL",
        "error": "Docker build failed.",
    }
    result = add_recovery_guidance(check)

    assert result["recovery_guidance"]
    assert any("docker build" in item.lower() for item in result["recovery_guidance"])



def test_generate_report_serializes_summary_and_overall_status(tmp_path):
    import json
    from relqon.cli import generate_report

    checks = [
        {"name": "Python syntax validation", "status": "PASS", "duration_seconds": 0.01},
        {
            "name": "Docker build validation",
            "status": "FAIL",
            "duration_seconds": 0.02,
            "error": "Docker build failed.",
            "recovery_guidance": ["Review the Dockerfile and build context."],
        },
        {
            "name": "Terraform validation",
            "status": "SKIPPED",
            "duration_seconds": 0.0,
            "error": "Terraform CLI is not installed.",
            "recovery_guidance": ["Install Terraform CLI."],
        },
    ]
    impact = {
        "checks": ["docker_build", "python_check", "terraform_check"],
        "reasons": ["A representative end-to-end report test."],
    }

    report_path = generate_report(
        tmp_path,
        ["Dockerfile", "src/app.py", "infra/main.tf"],
        impact,
        checks,
        "2026-10-24T10:00:00+05:30",
        0.5,
    )

    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["project"] == tmp_path.name
    assert report["changed_files"] == ["Dockerfile", "src/app.py", "infra/main.tf"]
    assert report["impact_analysis"] == impact
    assert report["summary"] == {"passed": 1, "failed": 1, "skipped": 1}
    assert report["overall_status"] == "FAIL"

    docker_check = next(
        check for check in report["checks"]
        if check["name"] == "Docker build validation"
    )
    assert docker_check["recovery_guidance"] == [
        "Review the Dockerfile and build context."
    ]


def test_generate_report_marks_skipped_when_no_checks_fail(tmp_path):
    import json
    from relqon.cli import generate_report

    report_path = generate_report(
        tmp_path,
        [],
        {"checks": [], "reasons": []},
        [
            {"name": "Terraform validation", "status": "SKIPPED", "duration_seconds": 0.0},
            {"name": "Python syntax validation", "status": "PASS", "duration_seconds": 0.01},
        ],
        "2026-10-24T10:00:00+05:30",
        0.1,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"] == {"passed": 1, "failed": 0, "skipped": 1}
    assert report["overall_status"] == "SKIPPED"


def test_generate_report_marks_pass_when_all_checks_pass(tmp_path):
    import json
    from relqon.cli import generate_report

    report_path = generate_report(
        tmp_path,
        ["src/app.py"],
        {"checks": ["python_check"], "reasons": ["Python changed."]},
        [{"name": "Python syntax validation", "status": "PASS", "duration_seconds": 0.01}],
        "2026-10-24T10:00:00+05:30",
        0.1,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"] == {"passed": 1, "failed": 0, "skipped": 0}
    assert report["overall_status"] == "PASS"


def test_cli_run_creates_end_to_end_json_report(tmp_path, monkeypatch):
    import json
    import relqon.cli as cli

    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("VALUE = 42\n", encoding="utf-8")

    monkeypatch.setattr(cli, "detect_changes", lambda project_path: (0, []))
    monkeypatch.setattr(
        cli,
        "run_pytest",
        lambda project_path: {
            "name": "Pytest unit tests",
            "status": "PASS",
            "duration_seconds": 0.01,
            "error": None,
            "output": "1 passed",
        },
    )
    monkeypatch.setattr(
        cli,
        "test_python_failure_detection",
        lambda: {
            "name": "Python failure detection test",
            "status": "PASS",
            "duration_seconds": 0.01,
            "error": None,
        },
    )
    monkeypatch.setattr(
        cli,
        "test_failure_detection",
        lambda project_path: {
            "name": "Docker failure detection test",
            "status": "PASS",
            "duration_seconds": 0.01,
            "error": None,
        },
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["relqon", "run", str(tmp_path), "--changed-file", "src/app.py"],
    )

    exit_code = cli.main()

    report_path = tmp_path / "reports" / "validation-report.json"
    assert exit_code == 0
    assert report_path.is_file()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["changed_files"] == ["src/app.py"]
    assert "python_check" in report["impact_analysis"]["checks"]
    python_check = next(
        check for check in report["checks"]
        if check["name"] == "Python syntax validation"
    )
    assert python_check["status"] == "PASS"
    assert python_check["files_checked"] == ["src/app.py"]
    assert report["overall_status"] == "PASS"
    assert report["summary"]["failed"] == 0



def test_cli_failure_writes_recovery_guidance_and_returns_one(tmp_path, monkeypatch):
    import json
    import relqon.cli as cli

    source = tmp_path / "src" / "broken.py"
    source.parent.mkdir()
    source.write_text("def broken(:\n", encoding="utf-8")

    monkeypatch.setattr(cli, "detect_changes", lambda project_path: (0, []))
    monkeypatch.setattr(
        cli,
        "run_pytest",
        lambda project_path: {
            "name": "Pytest unit tests",
            "status": "PASS",
            "duration_seconds": 0.01,
            "error": None,
            "output": "tests passed",
        },
    )
    monkeypatch.setattr(
        cli,
        "validate_python",
        lambda project_path, changed_files: {
            "name": "Python syntax validation",
            "status": "FAIL",
            "duration_seconds": 0.01,
            "error": "src/broken.py: SyntaxError: invalid syntax",
            "files_checked": ["src/broken.py"],
        },
    )
    monkeypatch.setattr(
        cli,
        "test_python_failure_detection",
        lambda: {"name": "Python failure detection test", "status": "PASS", "duration_seconds": 0.01},
    )
    monkeypatch.setattr(
        cli,
        "test_failure_detection",
        lambda project_path: {"name": "Docker failure detection test", "status": "PASS", "duration_seconds": 0.01},
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["relqon", "run", str(tmp_path), "--changed-file", "src/broken.py"],
    )

    exit_code = cli.main()

    report = json.loads(
        (tmp_path / "reports" / "validation-report.json").read_text(encoding="utf-8")
    )
    python_check = next(
        check for check in report["checks"]
        if check["name"] == "Python syntax validation"
    )
    assert exit_code == 1
    assert report["overall_status"] == "FAIL"
    assert report["summary"]["failed"] == 1
    assert python_check["recovery_guidance"]
    assert any("syntax error" in item.lower() or "traceback" in item.lower()
               for item in python_check["recovery_guidance"])


def test_cli_skipped_validation_returns_two_and_reports_skip_guidance(tmp_path, monkeypatch):
    import json
    import relqon.cli as cli

    terraform = tmp_path / "infra" / "main.tf"
    terraform.parent.mkdir()
    terraform.write_text('terraform {}\n', encoding="utf-8")

    monkeypatch.setattr(cli, "detect_changes", lambda project_path: (0, []))
    monkeypatch.setattr(
        cli,
        "run_pytest",
        lambda project_path: {
            "name": "Pytest unit tests",
            "status": "PASS",
            "duration_seconds": 0.01,
            "error": None,
            "output": "tests passed",
        },
    )
    monkeypatch.setattr(
        cli,
        "validate_terraform",
        lambda project_path, changed_files: {
            "name": "Terraform validation",
            "status": "SKIPPED",
            "duration_seconds": 0.0,
            "error": "Terraform CLI is not installed or not in PATH.",
            "files_checked": [],
            "steps": [],
        },
    )
    monkeypatch.setattr(
        cli,
        "test_python_failure_detection",
        lambda: {"name": "Python failure detection test", "status": "PASS", "duration_seconds": 0.01},
    )
    monkeypatch.setattr(
        cli,
        "test_failure_detection",
        lambda project_path: {"name": "Docker failure detection test", "status": "PASS", "duration_seconds": 0.01},
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["relqon", "run", str(tmp_path), "--changed-file", "infra/main.tf"],
    )

    exit_code = cli.main()

    report = json.loads(
        (tmp_path / "reports" / "validation-report.json").read_text(encoding="utf-8")
    )
    terraform_check = next(
        check for check in report["checks"]
        if check["name"] == "Terraform validation"
    )
    assert exit_code == 2
    assert report["overall_status"] == "SKIPPED"
    assert report["summary"]["skipped"] == 1
    assert terraform_check["recovery_guidance"]
    assert any("install terraform" in item.lower()
               for item in terraform_check["recovery_guidance"])

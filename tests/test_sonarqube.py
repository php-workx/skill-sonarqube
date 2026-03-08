import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def load_module():
    module_path = Path(__file__).resolve().parents[1] / "skills" / "sonarqube" / "scripts" / "sonarqube.py"
    spec = importlib.util.spec_from_file_location("skill_sonarqube", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sonarqube = load_module()


class SonarQubeScriptTests(unittest.TestCase):
    def test_repo_uses_index_friendly_skill_layout(self):
        repo_root = Path(__file__).resolve().parents[1]
        self.assertTrue((repo_root / "skills" / "sonarqube" / "SKILL.md").exists())
        self.assertEqual((repo_root / "SKILL.md").resolve(), (repo_root / "skills" / "sonarqube" / "SKILL.md").resolve())

    def test_read_sonar_properties_returns_project_host_sources_and_tests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "sonar-project.properties").write_text(
                "\n".join(
                    [
                        "sonar.projectKey=demo-key",
                        "sonar.host.url=http://localhost:9010",
                        "sonar.sources=src,lib",
                        "sonar.tests=tests",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            props = sonarqube.read_sonar_properties(str(repo_root))

            self.assertEqual(props["sonar.projectKey"], "demo-key")
            self.assertEqual(props["sonar.host.url"], "http://localhost:9010")
            self.assertEqual(props["sonar.sources"], "src,lib")
            self.assertEqual(props["sonar.tests"], "tests")

    def test_resolve_uses_dotenv_when_process_env_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("SONAR_TOKEN=from-dotenv\n", encoding="utf-8")
            dotenv = sonarqube.load_dotenv_file(str(env_path))

            with mock.patch.dict(sonarqube.os.environ, {}, clear=True):
                value = sonarqube.resolve_setting("", "SONAR_TOKEN", dotenv, "", "")

            self.assertEqual(value, "from-dotenv")

    def test_bootstrap_local_project_generates_token_persists_env_and_sets_new_code_period(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            api_calls = []

            def fake_api(host_url, path, headers, data):
                api_calls.append((path, dict(data)))
                if path == "/api/user_tokens/generate":
                    return {"token": "generated-token"}
                return {}

            with mock.patch.object(sonarqube, "post_api_form", side_effect=fake_api):
                token, user, password = sonarqube.bootstrap_local_project(
                    host_url="http://localhost:9000",
                    project_key="demo-key",
                    project_name="demo-key",
                    token="",
                    user="admin",
                    password="admin",
                    env_path=str(env_path),
                    reference_branch="main",
                )

            self.assertEqual(token, "generated-token")
            self.assertEqual(user, "")
            self.assertEqual(password, "")
            self.assertIn("SONAR_TOKEN=generated-token", env_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [path for path, _ in api_calls],
                [
                    "/api/projects/create",
                    "/api/user_tokens/generate",
                    "/api/new_code_periods/set",
                ],
            )
            self.assertEqual(api_calls[2][1]["type"], "REFERENCE_BRANCH")
            self.assertEqual(api_calls[2][1]["value"], "main")

    def test_validate_sonar_properties_suggests_separating_test_paths(self):
        warnings = sonarqube.validate_sonar_properties(
            {
                "sonar.sources": "src,tests",
                "sonar.tests": "",
            }
        )

        self.assertTrue(any("sonar.tests" in warning for warning in warnings))

    def test_prepare_language_reports_adds_rust_clippy_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            output_dir = repo_root / ".sonarqube"
            output_dir.mkdir()
            (repo_root / "Cargo.toml").write_text("[package]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")

            with mock.patch.object(sonarqube.shutil, "which", return_value="/usr/bin/cargo"):
                with mock.patch.object(sonarqube.subprocess, "run") as run_mock:
                    run_mock.return_value = mock.Mock(returncode=0)
                    scanner_props = sonarqube.prepare_language_reports(str(repo_root), str(output_dir))

            report_path = output_dir / "rust-clippy.json"
            self.assertEqual(scanner_props["sonar.rust.clippy.reportPaths"], str(report_path))
            self.assertEqual(run_mock.call_args.args[0][:3], ["cargo", "clippy", "--message-format=json"])
            self.assertEqual(run_mock.call_args.kwargs["cwd"], str(repo_root))


if __name__ == "__main__":
    unittest.main()

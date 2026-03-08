#!/usr/bin/env python3
"""SonarQube/SonarCloud skill script for AI coding agents.

Subcommands:
  scan   Full pipeline: detect base ref, compute changed files, ensure server,
         run scanner (local), fetch issues, output findings.
  fetch  Fetch issues from an existing scan and filter to changed files
         (backward-compatible with the original collect_changed_issues.py).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SEVERITY_ORDER = {
    "INFO": 1,
    "MINOR": 2,
    "MAJOR": 3,
    "CRITICAL": 4,
    "BLOCKER": 5,
}

THRESHOLD_TO_SEVERITY = {
    "info": "INFO",
    "low": "MINOR",
    "medium": "MAJOR",
    "high": "CRITICAL",
    "blocker": "BLOCKER",
    "minor": "MINOR",
    "major": "MAJOR",
    "critical": "CRITICAL",
    "all": "INFO",
}

SONARCLOUD_URL = "https://sonarcloud.io"

DEFAULT_CONTAINER_NAME = "clai-sonarqube"
DEFAULT_CONTAINER_IMAGE = "sonarqube:community"
DEFAULT_WAIT_SECONDS = 300

BLOCKER_CODES = (
    "false_positive_candidate",
    "external_dependency",
    "unsupported_auto_fix",
    "needs_behavioral_change",
    "infrastructure_failure",
)

CONFIG_DEFAULTS = {
    "mode": "local",
    "severity": "high",
    "scope": "new",
    "max_passes": 8,
    "base_ref": "",
    "exclude_paths": [],
}

COMMON_TEST_PATH_PARTS = {
    "test",
    "tests",
    "__tests__",
    "spec",
    "specs",
    "integration-tests",
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[sonarqube] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"[sonarqube] error: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def git_repo_root() -> str:
    r = _run(["git", "rev-parse", "--show-toplevel"])
    if r.returncode != 0:
        fail("not inside a git repository")
    return r.stdout.strip()


def ref_exists(ref: str) -> bool:
    r = _run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    return r.returncode == 0


def detect_base_ref() -> Optional[str]:
    for candidate in ("origin/main", "main", "origin/master", "master"):
        if ref_exists(candidate):
            return candidate
    return None


def compute_changed_files(repo_root: str, base_ref: str, output_dir: str) -> Tuple[List[str], str]:
    """Compute files changed between base_ref and HEAD, write list, return (files, list_path)."""
    r = _run(["git", "merge-base", "HEAD", base_ref], cwd=repo_root)
    if r.returncode != 0:
        fail(f"cannot compute merge-base between HEAD and {base_ref}")
    base_commit = r.stdout.strip()

    r = _run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base_commit}..HEAD"],
        cwd=repo_root,
    )
    diff_files = [f for f in r.stdout.strip().splitlines() if f]

    changed = [f for f in diff_files if os.path.isfile(os.path.join(repo_root, f))]

    list_path = os.path.join(output_dir, "changed-files.txt")
    with open(list_path, "w", encoding="utf-8") as fh:
        for f in changed:
            fh.write(f + "\n")

    return changed, list_path


def compute_changed_lines(
    repo_root: str, base_ref: str, output_dir: str,
) -> Dict[str, List[Tuple[int, int]]]:
    """Parse git diff hunk headers to get changed line ranges per file.

    Returns {normalized_path: [(start_line, end_line), ...]}.
    """
    r = _run(["git", "merge-base", "HEAD", base_ref], cwd=repo_root)
    if r.returncode != 0:
        return {}
    base_commit = r.stdout.strip()

    r = _run(
        ["git", "diff", "--unified=0", "--diff-filter=ACMRTUXB", f"{base_commit}..HEAD"],
        cwd=repo_root,
    )
    if r.returncode != 0:
        return {}

    changed_lines: Dict[str, List[Tuple[int, int]]] = {}
    current_file: Optional[str] = None

    for raw_line in r.stdout.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = normalize_path(raw_line[6:])
        elif raw_line.startswith("@@ ") and current_file is not None:
            # Parse @@ -old +new @@ format.  We care about the + (new) side.
            m = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                if count > 0:
                    end = start + count - 1
                    changed_lines.setdefault(current_file, []).append((start, end))

    # Write for transparency / debugging.
    lines_path = os.path.join(output_dir, "changed-lines.json")
    serializable = {k: v for k, v in changed_lines.items()}
    with open(lines_path, "w", encoding="utf-8") as fh:
        json.dump(serializable, fh, indent=2)
        fh.write("\n")

    return changed_lines


# ---------------------------------------------------------------------------
# Config file loader
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> Dict[str, Any]:
    """Load .sonarqube-skill.yaml, returning a flat dict of resolved values.

    Uses PyYAML if available, otherwise a minimal line parser for the supported schema.
    Returns CONFIG_DEFAULTS if file is missing or malformed.
    """
    if not os.path.isfile(config_path):
        return dict(CONFIG_DEFAULTS)

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError:
        return dict(CONFIG_DEFAULTS)

    parsed: Optional[Dict[str, Any]] = None

    # Try PyYAML first.
    try:
        import yaml  # type: ignore[import-untyped]
        parsed = yaml.safe_load(raw)
    except ImportError:
        pass
    except Exception:
        log(f"warning: failed to parse {config_path} with PyYAML, trying fallback")

    # Fallback: minimal line parser.
    if parsed is None:
        parsed = _parse_simple_yaml(raw)

    if not isinstance(parsed, dict):
        log(f"warning: {config_path} is not a valid config, using defaults")
        return dict(CONFIG_DEFAULTS)

    result = dict(CONFIG_DEFAULTS)
    defaults = parsed.get("defaults", {})
    if isinstance(defaults, dict):
        for key in ("mode", "severity", "scope"):
            if key in defaults and isinstance(defaults[key], str):
                result[key] = defaults[key]
        if "max_passes" in defaults:
            try:
                result["max_passes"] = int(defaults["max_passes"])
            except (ValueError, TypeError):
                pass

    scan = parsed.get("scan", {})
    if isinstance(scan, dict):
        if "base_ref" in scan and isinstance(scan["base_ref"], str):
            result["base_ref"] = scan["base_ref"]
        if "exclude_paths" in scan and isinstance(scan["exclude_paths"], list):
            result["exclude_paths"] = [str(p) for p in scan["exclude_paths"]]

    return result


def _parse_simple_yaml(raw: str) -> Optional[Dict[str, Any]]:
    """Minimal YAML-subset parser for the config schema (no PyYAML dependency)."""
    result: Dict[str, Any] = {}
    current_section: Optional[str] = None
    current_list_key: Optional[str] = None

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # Top-level key.
        if indent == 0 and ":" in stripped:
            key, _, val = stripped.partition(":")
            val = val.strip()
            if val:
                result[key.strip()] = val
            else:
                current_section = key.strip()
                result.setdefault(current_section, {})
            current_list_key = None
            continue

        # Section-level key.
        if indent > 0 and current_section and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                result[current_section][key] = val
                current_list_key = None
            else:
                result[current_section][key] = []
                current_list_key = key
            continue

        # List item.
        if stripped.startswith("- ") and current_section and current_list_key:
            item = stripped[2:].strip()
            result[current_section][current_list_key].append(item)

    return result if result else None


# ---------------------------------------------------------------------------
# Sonar project property helpers
# ---------------------------------------------------------------------------

def read_sonar_properties(repo_root: str) -> Dict[str, str]:
    props_path = os.path.join(repo_root, "sonar-project.properties")
    if not os.path.isfile(props_path):
        return {}

    props: Dict[str, str] = {}
    with open(props_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("!"):
                continue

            separator = "=" if "=" in line else ":" if ":" in line else ""
            if not separator:
                continue

            key, value = line.split(separator, 1)
            props[key.strip()] = value.strip()
    return props


def detect_project_key(repo_root: str) -> str:
    props = read_sonar_properties(repo_root)
    return props.get("sonar.projectKey", "").strip() or os.path.basename(repo_root)


def detect_project_settings(repo_root: str) -> Dict[str, str]:
    props = read_sonar_properties(repo_root)
    return {
        "project_key": props.get("sonar.projectKey", "").strip() or os.path.basename(repo_root),
        "host_url": props.get("sonar.host.url", "").strip(),
        "sources": props.get("sonar.sources", "").strip(),
        "tests": props.get("sonar.tests", "").strip(),
    }


def _split_csv_paths(value: str) -> List[str]:
    return [normalize_path(part) for part in value.split(",") if part.strip()]


def validate_sonar_properties(props: Dict[str, str]) -> List[str]:
    warnings: List[str] = []
    source_paths = _split_csv_paths(props.get("sonar.sources", ""))
    test_paths = _split_csv_paths(props.get("sonar.tests", ""))

    source_test_paths = [
        path
        for path in source_paths
        if any(part in COMMON_TEST_PATH_PARTS for part in Path(path).parts)
    ]
    if source_test_paths and not test_paths:
        warnings.append(
            "sonar.sources includes likely test paths; set sonar.tests separately for more accurate SonarQube analysis."
        )

    return warnings


# ---------------------------------------------------------------------------
# URL / port helpers
# ---------------------------------------------------------------------------

def extract_port(url: str) -> int:
    """Extract port from a URL, defaulting to 9000."""
    m = re.match(r"https?://[^/:]+:(\d+)", url)
    return int(m.group(1)) if m else 9000


# ---------------------------------------------------------------------------
# Docker / server management
# ---------------------------------------------------------------------------

def read_system_status(host_url: str) -> Optional[str]:
    api = f"{host_url.rstrip('/')}/api/system/status"
    try:
        req = urllib.request.Request(api, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status")
    except Exception:
        return None


def ensure_server(
    host_url: str,
    autostart: bool = True,
    container_name: str = DEFAULT_CONTAINER_NAME,
    image: str = DEFAULT_CONTAINER_IMAGE,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
) -> None:
    status = read_system_status(host_url)
    if status == "UP":
        return

    if not autostart:
        fail(f"SonarQube is not reachable at {host_url} and autostart is disabled")

    if not shutil.which("docker"):
        fail("required command not found: docker")

    host_port = extract_port(host_url)

    # Try start first (avoids race condition with concurrent invocations).
    r = _run(["docker", "start", container_name])
    if r.returncode != 0:
        log(f"creating container {container_name} from {image}")
        r = _run([
            "docker", "run", "-d",
            "--name", container_name,
            "-p", f"{host_port}:9000",
            "-v", f"{container_name}-data:/opt/sonarqube/data",
            "-v", f"{container_name}-extensions:/opt/sonarqube/extensions",
            image,
        ])
        if r.returncode != 0:
            # Another process may have created it between our check and run.
            log("container creation failed, attempting start in case of race")
            r2 = _run(["docker", "start", container_name])
            if r2.returncode != 0:
                fail(f"cannot start or create container {container_name}")
    else:
        log(f"started existing container {container_name}")

    log(f"waiting for SonarQube to become ready at {host_url}")
    waited = 0
    while waited < wait_seconds:
        status = read_system_status(host_url)
        if status == "UP":
            log("SonarQube is ready")
            return
        time.sleep(5)
        waited += 5

    fail("timed out waiting for SonarQube to become ready")


def post_api_form(
    host_url: str,
    path: str,
    headers: Dict[str, str],
    data: Dict[str, str],
) -> Dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request_headers = dict(headers)
    request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    api = f"{host_url.rstrip('/')}{path}"
    req = urllib.request.Request(api, data=encoded, headers=request_headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        lowered = body.lower()
        if path == "/api/projects/create" and "already exists" in lowered:
            return {"status": "already_exists"}
        raise RuntimeError(f"SonarQube API error {exc.code} at {path}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach SonarQube at {api}: {exc}") from exc

    if not body:
        return {}
    return json.loads(body)


def load_dotenv_file(path: str) -> Dict[str, str]:
    if not os.path.isfile(path):
        return {}

    env_vars: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip().strip("'\"")
    return env_vars


def _write_dotenv_value(path: str, key: str, value: str) -> None:
    env_path = Path(path)
    existing = []
    if env_path.is_file():
        existing = env_path.read_text(encoding="utf-8").splitlines()

    updated = False
    new_lines: List[str] = []
    for line in existing:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def resolve_setting(
    cli_val: str,
    env_key: str,
    dotenv: Dict[str, str],
    config_val: str,
    default: str,
) -> str:
    if cli_val:
        return cli_val
    env_val = os.environ.get(env_key, "")
    if env_val:
        return env_val
    dotenv_val = dotenv.get(env_key, "")
    if dotenv_val:
        return dotenv_val
    if config_val:
        return config_val
    return default


def bootstrap_local_project(
    host_url: str,
    project_key: str,
    project_name: str,
    token: str,
    user: str,
    password: str,
    env_path: str,
    reference_branch: str = "main",
) -> Tuple[str, str, str]:
    headers = build_headers(token, user, password)
    post_api_form(
        host_url,
        "/api/projects/create",
        headers,
        {"project": project_key, "name": project_name},
    )

    resolved_token = token
    resolved_user = user
    resolved_password = password

    if not resolved_token:
        token_name = f"sonarqube-skill-{project_key}-{int(time.time())}"
        token_payload = post_api_form(
            host_url,
            "/api/user_tokens/generate",
            headers,
            {"name": token_name},
        )
        resolved_token = str(token_payload.get("token", "")).strip()
        if not resolved_token:
            raise RuntimeError("SonarQube token generation returned no token")
        _write_dotenv_value(env_path, "SONAR_TOKEN", resolved_token)
        resolved_user = ""
        resolved_password = ""
        headers = build_headers(resolved_token, resolved_user, resolved_password)

    post_api_form(
        host_url,
        "/api/new_code_periods/set",
        headers,
        {
            "project": project_key,
            "type": "REFERENCE_BRANCH",
            "value": reference_branch or "main",
        },
    )

    return resolved_token, resolved_user, resolved_password


# ---------------------------------------------------------------------------
# Scanner invocation
# ---------------------------------------------------------------------------

def run_scanner(
    repo_root: str,
    host_url: str,
    project_key: str,
    inclusions_csv: str,
    token: str,
    user: str,
    password: str,
    output_dir: str,
    sources: str = "",
    tests: str = "",
    extra_properties: Optional[Dict[str, str]] = None,
) -> None:
    if not shutil.which("sonar-scanner"):
        fail("required command not found: sonar-scanner")

    log_path = os.path.join(output_dir, "sonar-scanner.log")
    cmd = [
        "sonar-scanner",
        f"-Dsonar.host.url={host_url}",
        f"-Dsonar.projectKey={project_key}",
        f"-Dsonar.inclusions={inclusions_csv}",
        "-Dsonar.qualitygate.wait=true",
        "-Dsonar.qualitygate.timeout=300",
    ]
    if sources:
        cmd.append(f"-Dsonar.sources={sources}")
    if tests:
        cmd.append(f"-Dsonar.tests={tests}")
    if extra_properties:
        for key, value in sorted(extra_properties.items()):
            cmd.append(f"-D{key}={value}")
    if token:
        cmd.append(f"-Dsonar.token={token}")
    else:
        cmd.append(f"-Dsonar.login={user}")
        cmd.append(f"-Dsonar.password={password}")

    log(f"running sonar-scanner for project {project_key}")
    with open(log_path, "w", encoding="utf-8") as lf:
        r = subprocess.run(cmd, cwd=repo_root, stdout=lf, stderr=subprocess.STDOUT)

    if r.returncode != 0:
        log("scanner output (last 100 lines):")
        try:
            with open(log_path, "r", encoding="utf-8") as lf:
                lines = lf.readlines()
                for line in lines[-100:]:
                    print(line, end="", file=sys.stderr)
        except Exception:
            pass
        fail("sonar-scanner failed")


# ---------------------------------------------------------------------------
# Path / file helpers
# ---------------------------------------------------------------------------

def normalize_path(path: str) -> str:
    path = path.strip()
    if path.startswith("./"):
        path = path[2:]
    return os.path.normpath(path).replace("\\", "/")


def load_changed_files(path: str) -> set[str]:
    files: set[str] = set()
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                files.add(normalize_path(line))
    return files


def prepare_language_reports(repo_root: str, output_dir: str) -> Dict[str, str]:
    scanner_properties: Dict[str, str] = {}
    cargo_toml = os.path.join(repo_root, "Cargo.toml")
    if os.path.isfile(cargo_toml):
        scanner_properties.update(_prepare_rust_clippy_report(repo_root, output_dir))
    return scanner_properties


def _prepare_rust_clippy_report(repo_root: str, output_dir: str) -> Dict[str, str]:
    if not shutil.which("cargo"):
        log("warning: Cargo.toml detected but cargo is not installed; skipping clippy report generation")
        return {}

    report_path = os.path.join(output_dir, "rust-clippy.json")
    cmd = ["cargo", "clippy", "--message-format=json", "--all-targets", "--all-features"]
    log("running cargo clippy to generate SonarQube Rust report")
    with open(report_path, "w", encoding="utf-8") as report_file:
        result = subprocess.run(cmd, cwd=repo_root, stdout=report_file, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        log("warning: cargo clippy failed; continuing without sonar.rust.clippy.reportPaths")
        if os.path.isfile(report_path):
            os.remove(report_path)
        return {}

    return {"sonar.rust.clippy.reportPaths": report_path}


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def build_headers(token: str, user: str, password: str) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        auth = f"{token}:"
    elif user or password:
        auth = f"{user}:{password}"
    else:
        auth = ""
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(auth.encode("utf-8")).decode("ascii")
    return headers


def build_cloud_headers(token: str) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Issue fetching
# ---------------------------------------------------------------------------

def _paginated_fetch(url_base: str, params: Dict[str, str], headers: Dict[str, str], label: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    page = 1
    while True:
        params["p"] = str(page)
        query = urllib.parse.urlencode(params)
        url = f"{url_base}?{query}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{label} API error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach {label} at {url_base}: {exc}") from exc

        page_issues = payload.get("issues", [])
        issues.extend(page_issues)

        paging = payload.get("paging", {})
        total = int(paging.get("total", len(issues)))
        page_size = int(paging.get("pageSize", 500))
        if page * page_size >= total:
            break
        page += 1
    return issues


def fetch_issues(host_url: str, project_key: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    params = {
        "projectKeys": project_key,
        "statuses": "OPEN,CONFIRMED,REOPENED",
        "ps": "500",
    }
    url_base = f"{host_url.rstrip('/')}/api/issues/search"
    return _paginated_fetch(url_base, params, headers, "SonarQube")


def fetch_cloud_issues(
    project_key: str,
    token: str,
    organization: str = "",
    branch: str = "",
) -> List[Dict[str, Any]]:
    headers = build_cloud_headers(token)
    params: Dict[str, str] = {
        "componentKeys": project_key,
        "statuses": "OPEN,CONFIRMED,REOPENED",
        "ps": "500",
    }
    if organization:
        params["organization"] = organization
    if branch:
        params["branch"] = branch
    url_base = f"{SONARCLOUD_URL}/api/issues/search"
    return _paginated_fetch(url_base, params, headers, "SonarCloud")


# ---------------------------------------------------------------------------
# Issue filtering and output
# ---------------------------------------------------------------------------

def issue_file_path(issue: Dict[str, Any]) -> str:
    component = issue.get("component", "")
    if ":" in component:
        component = component.split(":", 1)[1]
    return normalize_path(component)


def issue_line(issue: Dict[str, Any]) -> int:
    line = issue.get("line")
    if isinstance(line, int) and line > 0:
        return line
    text_range = issue.get("textRange", {})
    start_line = text_range.get("startLine")
    if isinstance(start_line, int) and start_line > 0:
        return start_line
    return 0


def _line_in_changed_ranges(line: int, ranges: List[Tuple[int, int]]) -> bool:
    """Check if a line number falls within any of the changed hunk ranges."""
    for start, end in ranges:
        if start <= line <= end:
            return True
    return False


# Security issue types that should be included even without a precise line.
_SECURITY_TYPES = {"VULNERABILITY", "SECURITY_HOTSPOT"}


def filter_issues(
    raw_issues: List[Dict[str, Any]],
    changed_files: set[str],
    threshold: str,
    scope: str = "changed",
    changed_lines: Optional[Dict[str, List[Tuple[int, int]]]] = None,
) -> List[Dict[str, Any]]:
    threshold_sev = THRESHOLD_TO_SEVERITY[threshold]
    threshold_rank = SEVERITY_ORDER[threshold_sev]
    findings: List[Dict[str, Any]] = []
    for issue in raw_issues:
        severity = issue.get("severity", "INFO")
        rank = SEVERITY_ORDER.get(severity, 0)
        file_path = issue_file_path(issue)
        if rank < threshold_rank:
            continue
        if file_path not in changed_files:
            continue

        line_num = issue_line(issue)

        # scope=new: require finding on a changed line range.
        if scope == "new" and changed_lines is not None:
            file_ranges = changed_lines.get(file_path, [])
            if line_num > 0:
                if not _line_in_changed_ranges(line_num, file_ranges):
                    continue
            else:
                # No line number: include only security-relevant types.
                issue_type = issue.get("type", "")
                if issue_type not in _SECURITY_TYPES:
                    continue

        findings.append({
            "key": issue.get("key", ""),
            "rule": issue.get("rule", ""),
            "type": issue.get("type", ""),
            "severity": severity,
            "message": issue.get("message", ""),
            "file": file_path,
            "line": line_num,
            "status": issue.get("status", ""),
            "effort": issue.get("effort", ""),
            "tags": issue.get("tags", []),
        })
    findings.sort(key=lambda f: (
        -SEVERITY_ORDER.get(f["severity"], 0),
        f["file"],
        f["line"],
        f["key"],
    ))
    return findings


def write_json(
    path: str, project_key: str, threshold: str, changed_count: int,
    findings: List[Dict[str, Any]], scope: str = "changed",
) -> None:
    severity_counts = Counter(item["severity"] for item in findings)
    output = {
        "summary": {
            "project_key": project_key,
            "severity_threshold": threshold,
            "scope": scope,
            "changed_files": changed_count,
            "findings": len(findings),
            "severity_counts": {
                k: v
                for k, v in sorted(
                    severity_counts.items(),
                    key=lambda item: -SEVERITY_ORDER.get(item[0], 0),
                )
            },
        },
        "findings": findings,
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)
        fh.write("\n")


def write_markdown(path: str, project_key: str, threshold: str, changed_count: int, findings: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# SonarQube Findings (Changed Files)\n\n")
        fh.write(f"- Project: `{project_key}`\n")
        fh.write(f"- Severity threshold: `{threshold}`\n")
        fh.write(f"- Changed files scanned: `{changed_count}`\n")
        fh.write(f"- Findings: `{len(findings)}`\n\n")
        if not findings:
            fh.write("No findings at or above the selected threshold on changed files.\n")
            return
        fh.write("| Severity | File | Line | Rule | Message |\n")
        fh.write("|---|---|---:|---|---|\n")
        for item in findings:
            message = item["message"].replace("|", "\\|").replace("\n", " ")
            fh.write(
                f"| {item['severity']} | `{item['file']}` | {item['line'] or ''} | `{item['rule']}` | {message} |\n"
            )


def print_summary(json_path: str) -> None:
    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    summary = data.get("summary", {})
    counts = summary.get("severity_counts", {})
    order = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")
    print("SonarQube Aggregated Findings")
    print(f"- Project: {summary.get('project_key', 'unknown')}")
    print(f"- Threshold: {summary.get('severity_threshold', 'unknown')}")
    print(f"- Changed files: {summary.get('changed_files', 0)}")
    print(f"- Findings: {summary.get('findings', 0)}")
    print("- Severity counts:")
    for sev in order:
        print(f"  - {sev}: {counts.get(sev, 0)}")


def write_blocked_json(path: str, blocked: List[Dict[str, str]]) -> None:
    """Write blocked findings with classification codes.

    Each entry: {key, rule, file, line, classification, reason}.
    Classification must be one of BLOCKER_CODES.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    output = {"blocked_findings": blocked, "total": len(blocked)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Subcommand: scan (replaces run_changed_scan.sh)
# ---------------------------------------------------------------------------

def _resolve(cli_val: str, env_key: str, dotenv: Dict[str, str], config_val: str, default: str) -> str:
    """Resolve a value by precedence: CLI > env > .env > config > default."""
    return resolve_setting(cli_val, env_key, dotenv, config_val, default)


def cmd_scan(args: argparse.Namespace) -> int:
    repo_root = git_repo_root()
    env_path = os.path.join(repo_root, ".env")
    dotenv = load_dotenv_file(env_path)
    project_settings = detect_project_settings(repo_root)

    # Load config file.
    config_path = args.config
    if not config_path:
        config_path = os.path.join(repo_root, ".sonarqube-skill.yaml")
    cfg = load_config(config_path)

    # Resolve values: CLI > env > config > default.
    mode = args.mode or cfg.get("mode", "local")
    severity = _resolve(args.severity, "", dotenv, cfg.get("severity", ""), "high").lower().strip()
    scope = args.scope or cfg.get("scope", "new")
    if severity not in THRESHOLD_TO_SEVERITY:
        fail(f"invalid severity '{args.severity}' (expected blocker|high|medium|low|info)")

    output_dir = args.output_dir
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(repo_root, output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Resolve base ref.
    base_ref = _resolve(args.base_ref, "", dotenv, cfg.get("base_ref", ""), "")
    if not base_ref:
        base_ref = detect_base_ref()
    if not base_ref:
        fail("unable to detect base ref; pass --base-ref <ref>")
    if not ref_exists(base_ref):
        fail(f"base ref does not exist: {base_ref}")

    # Compute changed files.
    changed_files, changed_list_path = compute_changed_files(repo_root, base_ref, output_dir)
    if not changed_files:
        log(f"no changed files between {base_ref} and HEAD")
        write_json(
            os.path.join(output_dir, "findings.json"),
            args.project_key or project_settings["project_key"],
            severity, 0, [], scope=scope,
        )
        write_markdown(
            os.path.join(output_dir, "findings.md"),
            args.project_key or project_settings["project_key"],
            severity, 0, [],
        )
        return 0

    # Compute changed lines for scope=new.
    changed_lines: Optional[Dict[str, List[Tuple[int, int]]]] = None
    if scope == "new":
        changed_lines = compute_changed_lines(repo_root, base_ref, output_dir)

    # Resolve project key.
    project_key = args.project_key or project_settings["project_key"]
    sources = project_settings["sources"]
    tests = project_settings["tests"]
    for warning in validate_sonar_properties(
        {
            "sonar.sources": sources,
            "sonar.tests": tests,
        }
    ):
        log(f"warning: {warning}")

    # Resolve auth.
    token = _resolve(args.token, "SONAR_TOKEN", dotenv, "", "")
    user = _resolve(args.user, "SONAR_USER", dotenv, "", "")
    password = _resolve(args.password, "SONAR_PASSWORD", dotenv, "", "")
    host_url = args.host_url or os.environ.get("SONAR_HOST_URL") or dotenv.get("SONAR_HOST_URL", "") or project_settings["host_url"] or "http://localhost:9000"
    organization = _resolve(args.organization, "SONAR_ORGANIZATION", dotenv, "", "")

    json_path = os.path.join(output_dir, "findings.json")
    md_path = os.path.join(output_dir, "findings.md")

    if mode == "cloud":
        if not token:
            fail("cloud mode requires --token or SONAR_TOKEN")
        branch = args.branch
        if not branch:
            r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
            branch = r.stdout.strip() if r.returncode == 0 else ""
        raw_issues = fetch_cloud_issues(project_key, token, organization, branch)
    else:
        # Local mode: default credentials for localhost.
        if not token and not user and not password:
            if re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?/?$", host_url):
                user = "admin"
                password = "admin"
                log("using default local SonarQube credentials admin/admin")
            else:
                fail("provide SONAR_TOKEN or --user/--password for SonarQube authentication")

        # Ensure server is running.
        ensure_server(
            host_url,
            autostart=not args.no_autostart,
            container_name=os.environ.get("SONARQUBE_CONTAINER_NAME", DEFAULT_CONTAINER_NAME),
            image=os.environ.get("SONARQUBE_IMAGE", DEFAULT_CONTAINER_IMAGE),
            wait_seconds=int(os.environ.get("SONARQUBE_WAIT_SECONDS", str(DEFAULT_WAIT_SECONDS))),
        )

        reference_branch = base_ref.split("/", 1)[1] if "/" in base_ref else base_ref
        token, user, password = bootstrap_local_project(
            host_url=host_url,
            project_key=project_key,
            project_name=project_key,
            token=token,
            user=user,
            password=password,
            env_path=env_path,
            reference_branch=reference_branch or "main",
        )

        # Filter comma files for sonar.inclusions.
        inclusion_files = []
        for f in changed_files:
            if "," in f:
                log(f"warning: skipping file with comma in name (unsupported by sonar.inclusions): {f}")
            else:
                inclusion_files.append(f)

        if not inclusion_files:
            log("no scannable files remain after filtering")
            write_json(json_path, project_key, severity, len(changed_files), [])
            write_markdown(md_path, project_key, severity, len(changed_files), [])
            return 0

        inclusions_csv = ",".join(inclusion_files)
        extra_properties = prepare_language_reports(repo_root, output_dir)

        # Run scanner.
        run_scanner(
            repo_root,
            host_url,
            project_key,
            inclusions_csv,
            token,
            user,
            password,
            output_dir,
            sources=sources,
            tests=tests,
            extra_properties=extra_properties,
        )

        # Fetch issues from local API.
        headers = build_headers(token, user, password)
        raw_issues = fetch_issues(host_url, project_key, headers)

    # Filter and output.
    changed_set = load_changed_files(changed_list_path)
    findings = filter_issues(raw_issues, changed_set, severity, scope=scope, changed_lines=changed_lines)
    write_json(json_path, project_key, severity, len(changed_set), findings, scope=scope)
    write_markdown(md_path, project_key, severity, len(changed_set), findings)

    log(f"findings json: {json_path}")
    log(f"findings markdown: {md_path}")
    log(f"changed files: {changed_list_path}")

    if args.list_only:
        print_summary(json_path)
        return 0

    if findings:
        log(f"findings found at/above '{severity}' on changed files")
        return 3
    else:
        log(f"no findings at/above '{severity}' on changed files")
        return 0


# ---------------------------------------------------------------------------
# Subcommand: fetch (backward-compatible with collect_changed_issues.py)
# ---------------------------------------------------------------------------

def cmd_fetch(args: argparse.Namespace) -> int:
    threshold = args.severity_threshold.lower().strip()
    if threshold not in THRESHOLD_TO_SEVERITY:
        fail(
            f"invalid severity threshold '{args.severity_threshold}' "
            "(expected blocker|high|medium|low|info; aliases: critical|major|minor|all)"
        )

    changed_files = load_changed_files(args.changed_files)

    if args.mode == "cloud":
        if not args.token:
            fail("cloud mode requires --token (SONAR_TOKEN)")
        raw_issues = fetch_cloud_issues(
            project_key=args.project_key,
            token=args.token,
            organization=args.organization,
            branch=args.branch,
        )
    else:
        host_url = args.host_url
        if not host_url:
            fail("local mode requires --host-url")
        headers = build_headers(args.token, args.user, args.password)
        raw_issues = fetch_issues(host_url, args.project_key, headers)

    findings = filter_issues(raw_issues, changed_files, threshold)
    write_json(args.output_json, args.project_key, threshold, len(changed_files), findings)
    write_markdown(args.output_md, args.project_key, threshold, len(changed_files), findings)

    return 3 if findings else 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sonarqube",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # -- scan ---
    scan_p = subparsers.add_parser(
        "scan",
        help="Full pipeline: detect refs, compute changed files, scan, fetch issues, output findings.",
    )
    scan_p.add_argument("--mode", choices=["local", "cloud"], default="local")
    scan_p.add_argument("--severity", default="high", help="blocker|high|medium|low|info (aliases: critical|major|minor|all)")
    scan_p.add_argument("--scope", choices=["new", "changed"], default="new",
                         help="new = only findings on changed lines; changed = all findings on changed files (default: new)")
    scan_p.add_argument("--base-ref", default="", help="Git ref to diff against (auto-detected if omitted)")
    scan_p.add_argument("--project-key", default="", help="Sonar project key (auto-detected if omitted)")
    scan_p.add_argument("--host-url", default="", help="SonarQube URL (default: SONAR_HOST_URL or http://localhost:9000)")
    scan_p.add_argument("--output-dir", default=".sonarqube", help="Output directory (default: .sonarqube)")
    scan_p.add_argument("--config", default="", help="Path to .sonarqube-skill.yaml (default: <repo-root>/.sonarqube-skill.yaml)")
    scan_p.add_argument("--token", default="", help="Sonar token")
    scan_p.add_argument("--user", default="", help="Sonar username")
    scan_p.add_argument("--password", default="", help="Sonar password")
    scan_p.add_argument("--organization", default="", help="SonarCloud organization key (cloud mode)")
    scan_p.add_argument("--branch", default="", help="Branch name (cloud mode; auto-detected if omitted)")
    scan_p.add_argument("--no-autostart", action="store_true", help="Do not start Docker container automatically")
    scan_p.add_argument("--list-only", action="store_true", help="Print aggregated findings and exit 0")

    # -- fetch ---
    fetch_p = subparsers.add_parser(
        "fetch",
        help="Fetch issues from existing scan and filter to changed files (backward-compatible).",
    )
    fetch_p.add_argument("--host-url", default="")
    fetch_p.add_argument("--project-key", required=True)
    fetch_p.add_argument("--changed-files", required=True)
    fetch_p.add_argument("--severity-threshold", default="high",
                         help="blocker|high|medium|low|info (aliases: critical|major|minor|all)")
    fetch_p.add_argument("--output-json", required=True)
    fetch_p.add_argument("--output-md", required=True)
    fetch_p.add_argument("--token", default="")
    fetch_p.add_argument("--user", default="")
    fetch_p.add_argument("--password", default="")
    fetch_p.add_argument("--mode", choices=["local", "cloud"], default="local")
    fetch_p.add_argument("--organization", default="")
    fetch_p.add_argument("--branch", default="")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scan":
        return cmd_scan(args)
    elif args.command == "fetch":
        return cmd_fetch(args)
    else:
        # No subcommand: if legacy flags are present, run fetch for backward compatibility.
        # Re-parse with fetch defaults.
        if any(a.startswith("--changed-files") or a.startswith("--output-json") for a in sys.argv[1:]):
            fetch_p = build_parser()
            args = fetch_p.parse_args(["fetch"] + sys.argv[1:])
            return cmd_fetch(args)
        parser.print_help()
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)

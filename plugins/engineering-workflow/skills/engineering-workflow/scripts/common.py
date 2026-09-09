#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

PLAN_SCHEMA_VERSION = 2
PLAN_ORIGINS = {
    "plan_mode_approved",
    "direct_execution",
    "resumed",
    "backlog_promotion",
    "external_handoff",
}
REQUIRED_PLAN_SECTIONS = (
    "Goal",
    "Plan Origin",
    "Requested Scope",
    "Requirement Traceability",
    "Explicit Non-Goals",
    "Constraints",
    "Inputs And Sources",
    "User Decisions And Answers",
    "Completed Baseline State",
    "Current Work Queue",
    "Locked Decisions",
    "Verification",
    "Latest Validation Results",
    "Risks And Recovery",
    "Resume Point",
    "Plan Fidelity Check",
    "Reconciliation Check",
    "Closure Gate",
    "Post-Close Delivery",
    "Handoff Notes",
)

CANONICAL_FILES = {
    "agents": "AGENTS.md",
    "plans": "PLANS.md",
    "principles": "docs/engineering/project_principles.md",
    "backlog": "docs/codex/TASKS_BACKLOG.md",
    "pitfalls": "docs/codex/AGENT_EXECUTION_PITFALLS.md",
}
STATE_MANIFEST_PATH = "docs/codex/ENGINEERING_WORKFLOW_STATE.yaml"
OPTIONAL_FILES = {
    "adoption_note": "docs/codex/agent_practices_adoption.md",
    "migration_note": "docs/codex/exec_plan_migration_note.md",
}
LEGACY_COMPAT_FILES = (
    "CLAUDE.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
)
SUPPORTED_ARCHIVE_PREFIXES = (
    "docs/archive/plans/",
    "docs/archive/backlog/",
    "docs/exec-plans/",
)
MANAGED_MARKER_START = "<!-- engineering-workflow:managed:start -->"
MANAGED_MARKER_END = "<!-- engineering-workflow:managed:end -->"
INDEX_MARKER_START = "<!-- engineering-workflow:index:start -->"
INDEX_MARKER_END = "<!-- engineering-workflow:index:end -->"

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "node_modules",
    "vendor",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "tmp",
    "dist",
    "build",
    ".idea",
    ".vscode",
}
DOC_SUFFIXES = {".md", ".rst", ".txt"}
TEXT_LIKE_SUFFIXES = DOC_SUFFIXES | {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".php",
    ".rb",
    ".cs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".swift",
    ".scala",
    ".sh",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".tmpl",
}
TEXT_LIKE_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "Jenkinsfile",
    "go.mod",
    "Gemfile",
    "Procfile",
    "Justfile",
    ".gitlab-ci.yml",
    ".gitignore",
}

PROMPT_INJECTION_PATTERNS = (
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget)\b.{0,80}\b(previous|prior|above)\b.{0,80}\binstructions?\b",
            re.IGNORECASE,
        ),
        "repo content tries to override higher-priority instructions",
    ),
    (
        "secrets_request",
        re.compile(
            r"\b(send|print|reveal|exfiltrate|upload|expose)\b.{0,80}\b(secret|token|credential|api key|password)\b",
            re.IGNORECASE,
        ),
        "repo content asks for secrets or credentials",
    ),
    (
        "remote_execution",
        re.compile(r"\b(curl|wget)\b.{0,40}\|\s*(sh|bash)\b", re.IGNORECASE),
        "repo content suggests piping remote content directly into a shell",
    ),
    (
        "data_exfiltration",
        re.compile(
            r"\b(upload|post|send)\b.{0,80}\b(to|into)\b.{0,80}\b(external|remote|server|webhook)\b",
            re.IGNORECASE,
        ),
        "repo content suggests exfiltrating data to an external destination",
    ),
)

PRIVACY_PATTERNS = {
    "macos_user_path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "linux_user_path": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "windows_user_path": re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._ -]+\\"),
    "file_url": re.compile(r"\bfile:" + r"//", re.IGNORECASE),
    "private_ssh_key_path": re.compile(
        r"(?:~|/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|[A-Za-z]:\\Users\\[^\\]+)[/\\]\.ssh[/\\](?:id_rsa|id_ed25519|id_ecdsa|id_dsa)",
        re.IGNORECASE,
    ),
    "private_key_material": re.compile(
        r"BEGIN (?:RSA |OPENSSH |EC )?" + r"PRIVATE KEY",
        re.IGNORECASE,
    ),
    "internal_hostname": re.compile(r"\b[a-zA-Z0-9.-]+\.(?:internal|corp|local)\b"),
    "credential_like_assignment": re.compile(
        r"\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|passwd)\b\s*[:=]\s*['\"]?[^\s'\";,]{8,}",
        re.IGNORECASE,
    ),
    "environment_secret_assignment": re.compile(
        r"\b(?:[A-Z][A-Z0-9]*_)*(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE_KEY|SECRET_ACCESS_KEY)\b"
        r"\s*[:=]\s*['\"]?[^\s'\";,]{8,}",
        re.IGNORECASE,
    ),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "known_token_prefix": re.compile(
        r"(?:ghp" + r"_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk" + r"-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})"
    ),
    "ssh_repository_url": re.compile(
        r"(?:ssh:" + r"//[^\s]+|git" + r"@[^\s:]+:[^\s]+)",
        re.IGNORECASE,
    ),
    "url_with_credentials": re.compile(r"https?://[^\s/@:]+:[^\s/@]+@[^\s/]+", re.IGNORECASE),
}

PRIVACY_REVIEW_CONTRACT_VERSION = 1
PRIVACY_REVIEW_ELIGIBLE_TYPES = frozenset(
    {
        "credential_like_assignment",
        "environment_secret_assignment",
        "bearer_token",
        "email",
        "internal_hostname",
    }
)


def _iter_relevant_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if path.is_symlink():
            yield path
            continue
        if path.is_file():
            yield path


def _read_text(path: Path) -> str:
    if path.is_symlink():
        try:
            return os.readlink(path)
        except OSError:
            return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if b"\x00" in data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _is_text_like(path: Path) -> bool:
    if path.suffix.lower() in TEXT_LIKE_SUFFIXES or path.name in TEXT_LIKE_FILENAMES:
        return True
    return bool(_read_text(path))


def iter_public_text_files(root: Path) -> Iterable[Path]:
    """Yield tracked public text files, or all non-ignored text files without Git."""
    candidates: list[tuple[Path, bool]] = []
    git_inventory_succeeded = False
    if (root / ".git").exists():
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "-z"],
            check=False,
            capture_output=True,
        )
        untracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"],
            check=False,
            capture_output=True,
        )
        if tracked.returncode == 0 and untracked.returncode == 0:
            git_inventory_succeeded = True
            candidates.extend((root / os.fsdecode(item), True) for item in tracked.stdout.split(b"\0") if item)
            candidates.extend((root / os.fsdecode(item), False) for item in untracked.stdout.split(b"\0") if item)
    if not git_inventory_succeeded:
        candidates = [(path, False) for path in _iter_relevant_files(root)]

    seen: set[str] = set()
    for path, tracked_path in candidates:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        relative_name = rel.as_posix()
        if relative_name in seen:
            continue
        seen.add(relative_name)
        if not tracked_path and any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if (path.is_symlink() or path.is_file()) and _is_text_like(path):
            yield path


def scan_privacy_text_with_fingerprints(text: str) -> list[dict[str, int | str]]:
    """Return private fingerprints for internal comparison without matched values."""
    issues: list[dict[str, int | str]] = []
    lines = text.splitlines(keepends=True) or [""]
    for name, pattern in PRIVACY_PATTERNS.items():
        for line_number, line in enumerate(lines, start=1):
            for _match in pattern.finditer(line):
                issues.append(
                    {
                        "type": name,
                        "line": line_number,
                        "line_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest(),
                    }
                )
    return issues


def scan_privacy_text(text: str) -> list[dict[str, int | str]]:
    """Return categories and line numbers without echoing values or fingerprints."""
    return [{"type": issue["type"], "line": issue["line"]} for issue in scan_privacy_text_with_fingerprints(text)]


def scan_public_tree_with_fingerprints(root: Path) -> list[dict[str, int | str]]:
    """Return internal finding fingerprints for exact snapshot comparison."""
    issues: list[dict[str, int | str]] = []
    for path in iter_public_text_files(root):
        text = _read_text(path)
        if not text:
            continue
        rel = path.relative_to(root).as_posix()
        for issue in scan_privacy_text_with_fingerprints(text):
            issues.append({"path": rel, **issue})
    return issues


def scan_public_tree(root: Path) -> list[dict[str, int | str]]:
    """Return public finding coordinates without echoing values or fingerprints."""
    return [
        {"type": issue["type"], "path": issue["path"], "line": issue["line"]}
        for issue in scan_public_tree_with_fingerprints(root)
    ]


def _classify_text_language(text: str) -> str:
    latin = 0
    cyrillic = 0
    for ch in text:
        if "A" <= ch <= "Z" or "a" <= ch <= "z":
            latin += 1
        elif "\u0400" <= ch <= "\u04ff":
            cyrillic += 1
    if latin == 0 and cyrillic == 0:
        return "unknown"
    bigger = max(latin, cyrillic)
    smaller = min(latin, cyrillic)
    if latin and cyrillic and smaller >= bigger * 0.35:
        return "mixed"
    return "cyrillic_dominant" if cyrillic > latin else "latin_dominant"


def _detect_language(texts: list[str]) -> str:
    per_text = {_classify_text_language(text) for text in texts if text.strip()}
    per_text.discard("unknown")
    if not per_text:
        return "unknown"
    if "mixed" in per_text or len(per_text) > 1:
        return "mixed"
    return per_text.pop()


def _normalize_managed_path(raw: str) -> str | None:
    value = raw.strip().strip("\"'").replace("\\", "/")
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        return None
    parts = Path(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return Path(*parts).as_posix()


def _parse_manifest_atom(raw: str, *, allow_null: bool = False) -> str | None:
    value = raw.strip()
    if allow_null and value.lower() in {"null", "~"}:
        return None
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid quoted manifest value") from exc
        if not isinstance(parsed, str):
            raise ValueError("manifest path value must be a string")
        return parsed
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1].replace("''", "'")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError("unsupported manifest path value")
    return value


def parse_manifest_path_scalar(text: str, key: str, *, allow_null: bool = False) -> tuple[bool, str | None]:
    matches = list(re.finditer(rf"(?m)^{re.escape(key)}:[ \t]*(?P<value>[^#\n]*?)[ \t]*(?:#.*)?$", text))
    if not matches:
        return False, None
    if len(matches) != 1:
        raise ValueError(f"{key} must be declared exactly once")
    match = matches[0]
    raw = match.group("value").strip()
    if not raw:
        raise ValueError(f"{key} must be a scalar path")
    parsed = _parse_manifest_atom(raw, allow_null=allow_null)
    if parsed is None:
        return True, None
    normalized = _normalize_managed_path(parsed)
    if normalized is None:
        raise ValueError(f"{key} must be a safe repository-relative path")
    return True, normalized


def parse_manifest_path_list(text: str, key: str) -> tuple[bool, list[str]]:
    matches = list(re.finditer(rf"(?m)^{re.escape(key)}:[ \t]*(?P<inline>[^#\n]*?)[ \t]*(?:#.*)?$", text))
    if not matches:
        return False, []
    if len(matches) != 1:
        raise ValueError(f"{key} must be declared exactly once")
    match = matches[0]
    inline = match.group("inline").strip()
    if inline:
        if inline == "[]":
            return True, []
        raise ValueError(f"{key} must use a block list")
    values: list[str] = []
    start = match.end()
    for raw_line in text[start:].splitlines():
        if raw_line and not raw_line.startswith((" ", "\t")):
            break
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.startswith("-"):
            raise ValueError(f"{key} contains a non-list value")
        parsed = _parse_manifest_atom(stripped[1:].strip())
        if parsed is None:
            raise ValueError(f"{key} entries must be paths")
        normalized = _normalize_managed_path(parsed)
        if normalized is None:
            raise ValueError(f"{key} entries must be safe repository-relative paths")
        values.append(normalized)
    return True, values


def load_managed_paths(root: Path) -> set[str]:
    manifest = root / STATE_MANIFEST_PATH
    if not manifest.exists():
        return set()
    text = _read_text(manifest)
    managed: set[str] = set()
    active = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not raw_line.startswith((" ", "\t")):
            active = stripped.startswith("managed_paths:")
            continue
        if active and stripped.startswith("-"):
            normalized = _normalize_managed_path(stripped[1:].strip())
            if normalized:
                managed.add(normalized)
        elif active and stripped and not stripped.startswith("#"):
            active = False
    return managed


def _contains_managed_section(path: Path) -> bool:
    text = _read_text(path)
    return bool(
        (MANAGED_MARKER_START in text and MANAGED_MARKER_END in text)
        or (INDEX_MARKER_START in text and INDEX_MARKER_END in text)
    )


def classify_workflow_artifact(root: Path, path: Path, managed_paths: set[str] | None = None) -> str:
    rel = path.relative_to(root).as_posix()
    lower = rel.lower()
    managed_paths = managed_paths if managed_paths is not None else load_managed_paths(root)

    if rel == STATE_MANIFEST_PATH or rel in managed_paths or _contains_managed_section(path):
        return "managed"
    if any(lower.startswith(prefix) for prefix in SUPPORTED_ARCHIVE_PREFIXES):
        return "historical"
    if rel in CANONICAL_FILES.values() or rel in OPTIONAL_FILES.values() or rel in LEGACY_COMPAT_FILES:
        return "shared"
    if lower == "readme.md" or lower.endswith("/readme.md"):
        return "external_source_of_truth"
    if path.suffix.lower() in DOC_SUFFIXES:
        protected_words = (
            "architecture",
            "product",
            "security",
            "policy",
            "runbook",
            "release",
            "operations",
            "benchmark",
            "test-strategy",
            "qa/",
        )
        if any(word in lower for word in protected_words):
            return "protected"
        return "unknown"
    if lower in {".codex/config.toml"} or lower.startswith(".codex/agents/"):
        return "shared"
    return "unknown"


def _context_doc_reason(classification: str) -> str:
    reasons = {
        "managed": "path is declared by the workflow state manifest or explicit managed-section markers",
        "shared": "canonical workflow or compatibility path may contain repository-owned content and requires a narrow merge",
        "protected": "domain, product, architecture, QA, security, or operational documentation remains repository-owned",
        "external_source_of_truth": "repository overview or external-owner documentation should be indexed rather than absorbed",
        "historical": "supported historical path remains non-canonical retained context",
        "unknown": "ownership is not proven; keep protected until repository evidence or user direction resolves it",
    }
    return reasons[classification]


def discover_workflow_artifacts(root: Path, relevant_files: list[Path] | None = None) -> list[dict[str, str]]:
    files = relevant_files if relevant_files is not None else list(_iter_relevant_files(root))
    managed_paths = load_managed_paths(root)
    artifacts: list[dict[str, str]] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if (
            path.suffix.lower() not in DOC_SUFFIXES
            and rel
            not in {
                STATE_MANIFEST_PATH,
                ".codex/config.toml",
            }
            and not rel.startswith(".codex/agents/")
        ):
            continue
        classification = classify_workflow_artifact(root, path, managed_paths)
        artifacts.append(
            {
                "path": rel,
                "classification": classification,
                "reason": _context_doc_reason(classification),
            }
        )
    return sorted(artifacts, key=lambda item: item["path"])


def _discover_context_docs(root: Path, relevant_files: list[Path]) -> list[dict[str, str]]:
    results = []
    for item in discover_workflow_artifacts(root, relevant_files):
        if item["classification"] in {"managed", "shared", "historical"}:
            continue
        action = "leave_untouched"
        results.append(
            {
                "path": item["path"],
                "role": item["classification"],
                "action": action,
                "reason": item["reason"],
            }
        )
    return results


def _scan_prompt_injection_risks(root: Path, relevant_files: list[Path]) -> list[dict[str, str]]:
    findings = []
    for path in relevant_files:
        if not _is_text_like(path):
            continue
        text = _read_text(path)
        if not text.strip():
            continue
        rel_path = path.relative_to(root).as_posix()
        for name, pattern, reason in PROMPT_INJECTION_PATTERNS:
            if pattern.search(text):
                findings.append({"path": rel_path, "type": name, "reason": reason})
                break
    return sorted(findings, key=lambda item: item["path"])


def classify_repo_maturity(
    root: Path,
    relevant_files: list[Path],
    doc_count: int,
    canonical_count: int,
    context_doc_count: int = 0,
    compatibility_count: int = 0,
) -> str:
    del root
    if not relevant_files:
        return "empty_directory"
    if (
        canonical_count >= 3
        or doc_count >= 5
        or len(relevant_files) >= 25
        or context_doc_count >= 2
        or compatibility_count > 0
    ):
        return "mature_repo"
    return "minimal_repo"


_SHELL_CONTROL = re.compile(r"(?:&&|\|\||[;\n\r]|(?<!\\)\||[<>`]|\$\(|\$\{|\$[A-Za-z_(])")
_DESTRUCTIVE_EXECUTABLES = {
    "rm",
    "mv",
    "cp",
    "touch",
    "mkdir",
    "rmdir",
    "chmod",
    "chown",
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
}
_COPY_ONLY_EXECUTABLES = {
    "make",
    "pytest",
    "ruff",
    "black",
    "prettier",
    "eslint",
    "mypy",
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "bun",
    "pip",
    "pip3",
    "poetry",
    "uv",
    "cargo",
    "go",
    "mvn",
    "gradle",
    "gradlew",
    "bundle",
    "rake",
    "cmake",
    "ninja",
    "bash",
    "sh",
    "zsh",
}
_SAFE_GIT_SUBCOMMANDS = {"status", "diff", "ls-files", "log", "show", "rev-parse", "grep"}
_MUTATING_GIT_SUBCOMMANDS = {
    "add",
    "am",
    "apply",
    "branch",
    "checkout",
    "cherry-pick",
    "clean",
    "commit",
    "fetch",
    "merge",
    "pull",
    "push",
    "rebase",
    "reset",
    "restore",
    "revert",
    "rm",
    "switch",
    "tag",
    "worktree",
}
_SENSITIVE_PATH_RE = re.compile(
    r"(?:^|[/\\])(?:\.env(?:\.[^/\\]+)?|credentials?(?:\.[^/\\]+)?|secrets?(?:\.[^/\\]+)?|"
    r"id_(?:rsa|ed25519|ecdsa|dsa)|\.npmrc|\.pypirc|netrc|keychain)(?:$|[/\\])",
    re.IGNORECASE,
)
_CONTENT_READING_EXECUTABLES = {"cat", "head", "tail", "rg", "grep", "sed"}


def _has_unsafe_find_action(tokens: list[str]) -> bool:
    unsafe = {
        "-delete",
        "-exec",
        "-execdir",
        "-ok",
        "-okdir",
        "-fprint",
        "-fprint0",
        "-fprintf",
        "-fls",
    }
    return any(token in unsafe for token in tokens[1:])


def _sed_writes_or_executes(tokens: list[str]) -> bool:
    if any(
        token == "--in-place" or token.startswith("--in-place=") or re.fullmatch(r"-i.*", token) for token in tokens[1:]
    ):
        return True
    scripts: list[str] = []
    skip_next = False
    for index, token in enumerate(tokens[1:], start=1):
        if skip_next:
            skip_next = False
            continue
        if token in {"-e", "--expression", "-f", "--file"}:
            if token in {"-f", "--file"}:
                return True
            if index + 1 < len(tokens):
                scripts.append(tokens[index + 1])
                skip_next = True
            continue
        if token.startswith("-"):
            continue
        scripts.append(token)
        break
    script = ";".join(scripts)
    return bool(
        re.search(r"(?:^|[;{}\s])w(?:[;\s]|$)", script)
        or re.search(r"(?:^|[;{}\s])e(?:[;\s]|$)", script)
        or re.search(r"s(?:[^\\\n]|\\.)+[/|#]w(?:[;\s]|$)", script)
    )


def _sed_is_bounded_read(tokens: list[str]) -> bool:
    if "-n" not in tokens and "--quiet" not in tokens and "--silent" not in tokens:
        return False
    if _sed_writes_or_executes(tokens):
        return False
    programs: list[str] = []
    index = 1
    while index < len(tokens):
        argument = tokens[index]
        if argument in {"-f", "--file"} or argument.startswith("--file="):
            return False
        if argument in {"-e", "--expression"}:
            index += 1
            if index >= len(tokens):
                return False
            programs.append(tokens[index])
        elif argument.startswith("--expression="):
            programs.append(argument.split("=", 1)[1])
        elif argument.startswith("-"):
            pass
        elif not programs:
            programs.append(argument)
        else:
            break
        index += 1
    safe_program = re.compile(r"\s*(?:(?:\d+|\$)(?:\s*,\s*(?:\d+|\$))?)?\s*p\s*")
    return bool(programs) and all(safe_program.fullmatch(program) for program in programs)


def _names_or_presence_only(executable: str, tokens: list[str]) -> bool:
    if executable in {"ls", "stat", "readlink", "test", "wc"}:
        return True
    if executable == "rg":
        return any(
            token in {"--files", "-l", "--files-with-matches", "-L", "--files-without-match"} for token in tokens[1:]
        )
    if executable == "grep":
        return any(
            token in {"-l", "--files-with-matches", "-L", "--files-without-match", "-q", "--quiet", "--silent"}
            for token in tokens[1:]
        )
    return False


def classify_command_risks(command: str) -> dict[str, object]:
    """Return orthogonal command risks plus the compatible execution class."""
    stripped = command.strip()
    result: dict[str, object] = {
        "writes": False,
        "repo_code_execution": False,
        "network": False,
        "sensitive_output": False,
        "reasons": [],
        "classification": "live_only",
    }
    if not stripped or _SHELL_CONTROL.search(stripped):
        result["writes"] = bool(stripped)
        result["reasons"] = ["empty_or_shell_control"]
        return result
    try:
        tokens = shlex.split(stripped, posix=True)
    except ValueError:
        result["reasons"] = ["unparseable_shell"]
        return result
    if not tokens:
        result["reasons"] = ["empty_command"]
        return result

    executable = Path(tokens[0]).name.lower()
    sensitive_path = any(_SENSITIVE_PATH_RE.search(token) for token in tokens[1:])
    if (
        sensitive_path
        and executable in _CONTENT_READING_EXECUTABLES
        and not _names_or_presence_only(executable, tokens)
    ):
        result["sensitive_output"] = True
        result["reasons"] = ["sensitive_path_content"]
        return result
    if executable in _DESTRUCTIVE_EXECUTABLES:
        result["writes"] = executable not in {"curl", "wget", "ssh"}
        result["network"] = executable in {"curl", "wget", "ssh", "scp", "rsync"}
        result["reasons"] = ["mutation_or_network_tool"]
        return result
    if executable == "git":
        if len(tokens) < 2 or tokens[1].startswith("-"):
            result["reasons"] = ["ambiguous_git_invocation"]
            return result
        subcommand = tokens[1].lower()
        if subcommand in _MUTATING_GIT_SUBCOMMANDS:
            result["writes"] = True
            result["network"] = subcommand in {"fetch", "pull", "push"}
            result["reasons"] = ["mutating_git_subcommand"]
            return result
        if subcommand not in _SAFE_GIT_SUBCOMMANDS:
            result["reasons"] = ["unsupported_git_subcommand"]
            return result
        unsafe_git_options = ("--output", "--exec-path", "--open-files-in-pager")
        if any(
            token in {"--ext-diff", "--textconv", "--paginate", "-p"}
            or token.startswith("-O")
            or token.startswith(unsafe_git_options)
            for token in tokens[2:]
        ):
            result["writes"] = True
            result["reasons"] = ["unsafe_git_option"]
            return result
        result["classification"] = "read_only_safe"
        return result

    if executable in {"ls", "cat", "head", "tail", "wc", "pwd", "stat", "readlink", "test"}:
        result["classification"] = "read_only_safe"
        return result
    if executable in {"rg", "grep"}:
        if any(token in {"--pre", "--pre-glob"} or token.startswith("--pre=") for token in tokens[1:]):
            result["repo_code_execution"] = True
            result["reasons"] = ["search_preprocessor"]
            return result
        result["classification"] = "read_only_safe"
        return result
    if executable == "sed":
        if not _sed_is_bounded_read(tokens):
            result["writes"] = True
            result["reasons"] = ["sed_mode_not_proven_bounded_read"]
            return result
        result["classification"] = "read_only_safe"
        return result
    if executable == "find":
        if _has_unsafe_find_action(tokens):
            result["writes"] = True
            result["repo_code_execution"] = any(token in {"-exec", "-execdir", "-ok", "-okdir"} for token in tokens)
            result["reasons"] = ["unsafe_find_action"]
            return result
        result["classification"] = "read_only_safe"
        return result

    if executable in {"python", "python3"}:
        result["repo_code_execution"] = True
        if "-c" in tokens or "-" in tokens[1:2]:
            result["reasons"] = ["inline_python"]
            return result
        result["classification"] = "copy_only_safe"
        return result
    if executable in _COPY_ONLY_EXECUTABLES:
        result["repo_code_execution"] = True
        result["network"] = executable in {
            "npm",
            "npx",
            "pnpm",
            "yarn",
            "bun",
            "pip",
            "pip3",
            "poetry",
            "uv",
            "cargo",
            "go",
        }
        result["classification"] = "copy_only_safe"
        return result
    result["reasons"] = ["unsupported_command"]
    return result


def classify_command_safety(command: str) -> str:
    """Return the legacy string class derived from structured risk analysis."""
    return str(classify_command_risks(command)["classification"])


def recommended_checks(root: Path) -> dict[str, list[str]]:
    relevant_files = list(_iter_relevant_files(root))
    read_only = ["git status --short", "git diff --check", "git ls-files"]
    copy_only: list[str] = []
    if (root / "Makefile").exists():
        copy_only.append("make help")
    if any(path.suffix == ".py" for path in relevant_files) or any(
        (root / name).exists() for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt")
    ):
        copy_only.append("python -m compileall .")
    if (root / "package.json").exists():
        copy_only.append("npm test")
    return {"read_only_safe": read_only, "copy_only_safe": copy_only, "live_only": []}


def _minimal_disposable_env(temp_root: Path) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(temp_root / "home"),
        "TMPDIR": str(temp_root / "tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PIP_NO_INDEX": "1",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "",
        "no_proxy": "",
    }
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    return env


def _external_symlinks(root: Path) -> list[str]:
    external = []
    resolved_root = root.resolve()
    for path in root.rglob("*"):
        if not path.is_symlink():
            continue
        try:
            resolved = path.resolve(strict=False)
        except (OSError, RuntimeError):
            external.append(path.relative_to(root).as_posix())
            continue
        if not resolved.is_relative_to(resolved_root):
            external.append(path.relative_to(root).as_posix())
    return sorted(external)


def _network_guard_prefix(temp_root: Path) -> list[str] | None:
    sandbox_exec = Path("/usr/bin/sandbox-exec")
    if sys.platform == "darwin" and sandbox_exec.exists():
        allowed_root = str(temp_root.resolve()).replace("\\", "\\\\").replace('"', '\\"')
        real_home = str(Path.home()).replace("\\", "\\\\").replace('"', '\\"')
        profile = (
            "(version 1) "
            "(allow default) "
            "(deny network*) "
            f'(deny file-write* (require-not (subpath "{allowed_root}"))) '
            f'(deny file-read* (require-all (subpath "{real_home}") (require-not (subpath "{allowed_root}"))))'
        )
        return [str(sandbox_exec), "-p", profile]
    return None


def _intrinsically_offline(tokens: list[str]) -> bool:
    return tokens in (["python", "-m", "compileall", "."], ["python3", "-m", "compileall", "."])


def public_command_descriptor(command: str, index: int) -> dict[str, int | str]:
    """Return a stable opaque command identity without exposing command text."""
    fingerprint = hashlib.sha256(command.encode("utf-8", errors="surrogatepass")).hexdigest()
    return {
        "command": f"validation-command-{index:03d}",
        "command_index": index,
        "command_fingerprint": f"sha256:{fingerprint}",
    }


def run_in_disposable_copy(repo: Path, commands: list[str], timeout_seconds: int = 300) -> list[dict]:
    """Run copy-only commands in an isolated copy with a minimal credential-free env."""
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="engineering-workflow-verify-") as temp_name:
        temp_root = Path(temp_name)
        copy_root = temp_root / "repo"
        try:
            shutil.copytree(
                repo,
                copy_root,
                ignore=shutil.ignore_patterns(*IGNORED_DIRS),
                symlinks=True,
            )
        except OSError:
            return [
                {
                    **public_command_descriptor(command, index),
                    "status": "rejected",
                    "reason": "repository could not be copied safely",
                }
                for index, command in enumerate(commands, start=1)
            ]
        env = _minimal_disposable_env(temp_root)
        unsafe_links = _external_symlinks(copy_root)
        if unsafe_links:
            for index, command in enumerate(commands, start=1):
                results.append(
                    {
                        **public_command_descriptor(command, index),
                        "status": "rejected",
                        "reason": f"disposable copy contains {len(unsafe_links)} external symlink(s)",
                    }
                )
            return results
        network_guard = _network_guard_prefix(temp_root)
        for index, command in enumerate(commands, start=1):
            descriptor = public_command_descriptor(command, index)
            safety = classify_command_safety(command)
            if safety != "copy_only_safe":
                results.append({**descriptor, "status": "rejected", "reason": f"expected copy_only_safe, got {safety}"})
                continue
            tokens = shlex.split(command)
            executable = Path(tokens[0]).name.lower()
            if executable in {"pip", "pip3", "npm", "npx", "pnpm", "yarn", "bun", "cargo", "go"}:
                results.append(
                    {
                        **descriptor,
                        "status": "rejected",
                        "reason": "network-capable package command requires an explicit offline wrapper",
                    }
                )
                continue
            isolated_compileall = _intrinsically_offline(tokens)
            if network_guard is None and not isolated_compileall:
                results.append(
                    {
                        **descriptor,
                        "status": "rejected",
                        "reason": "command requires OS network isolation or an explicit offline wrapper",
                    }
                )
                continue
            if executable in {"python", "python3"}:
                tokens = (
                    [sys.executable, "-I", "-m", "compileall", "."]
                    if isolated_compileall
                    else [sys.executable, *tokens[1:]]
                )
            execution_tokens = [*network_guard, *tokens] if network_guard else tokens
            try:
                completed = subprocess.run(
                    execution_tokens,
                    cwd=copy_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                results.append({**descriptor, "status": "timeout", "timeout_seconds": timeout_seconds})
                continue
            results.append(
                {
                    **descriptor,
                    "status": "passed" if completed.returncode == 0 else "failed",
                    "returncode": completed.returncode,
                    "network_policy": "os_sandbox_deny" if network_guard else "intrinsic_offline",
                }
            )
    return results


def audit_repo(root: Path) -> dict:
    from instruction_contract import check_instruction_contract
    from plan_lifecycle import check_archive_indexes

    relevant_files = list(_iter_relevant_files(root))
    docs = [path for path in relevant_files if path.suffix.lower() in DOC_SUFFIXES]
    canonical_presence = {key: (root / rel_path).exists() for key, rel_path in CANONICAL_FILES.items()}
    optional_presence = {key: (root / rel_path).exists() for key, rel_path in OPTIONAL_FILES.items()}
    compat_presence = [rel for rel in LEGACY_COMPAT_FILES if (root / rel).exists()]
    workflow_artifacts = discover_workflow_artifacts(root, relevant_files)
    context_docs = _discover_context_docs(root, relevant_files)
    prompt_injection_risks = _scan_prompt_injection_risks(root, relevant_files)

    language_sources = []
    for rel in list(CANONICAL_FILES.values()) + compat_presence:
        path = root / rel
        if path.exists():
            language_sources.append(_read_text(path))
    if not language_sources:
        language_sources = [_read_text(path) for path in docs[:5]]

    retained_history = any((root / rel).exists() for rel in ("docs/exec-plans", "docs/archive"))
    repo_maturity = classify_repo_maturity(
        root,
        relevant_files,
        len(docs),
        sum(1 for value in canonical_presence.values() if value),
        context_doc_count=len(context_docs),
        compatibility_count=len(compat_presence),
    )
    classified_paths = {
        name: [item["path"] for item in workflow_artifacts if item["classification"] == name]
        for name in ("managed", "shared", "protected", "external_source_of_truth", "historical", "unknown")
    }
    instruction_contract = check_instruction_contract(root)
    archive_indexes = check_archive_indexes(root)

    return {
        "root": str(root.resolve()),
        "repo_maturity": repo_maturity,
        "file_count": len(relevant_files),
        "doc_count": len(docs),
        "canonical_files": canonical_presence,
        "optional_files": optional_presence,
        "state_manifest": (root / STATE_MANIFEST_PATH).exists(),
        "compatibility_docs": compat_presence,
        "workflow_artifacts": workflow_artifacts,
        "ownership": classified_paths,
        "context_docs": context_docs,
        "prompt_injection_risks": prompt_injection_risks,
        "retained_history": retained_history,
        "dominant_language": _detect_language(language_sources),
        "recommended_validation": recommended_checks(root),
        "instruction_contract": instruction_contract,
        "archive_indexes": archive_indexes,
    }


def _section_text(text: str, heading: str) -> str:
    match = re.search(
        rf"^### {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^### |^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group("body").strip() if match else ""


def validate_plan_schema(
    text: str,
    declared_external_sources: bool = False,
    require_fidelity_passed: bool = False,
) -> list[str]:
    issues: list[str] = []
    if not re.search(rf"(?mi)^(?:plan_schema_version|Plan Schema Version)\s*:\s*`?{PLAN_SCHEMA_VERSION}`?\s*$", text):
        issues.append("missing or unsupported plan_schema_version")
    for section in REQUIRED_PLAN_SECTIONS:
        if not re.search(rf"(?m)^### {re.escape(section)}\s*$", text):
            issues.append(f"missing plan section: {section}")

    origin_body = _section_text(text, "Plan Origin")
    origin_lines = [line.strip().strip("`") for line in origin_body.splitlines() if line.strip()]
    origin_text = origin_lines[0] if origin_lines else ""
    if not origin_text:
        issues.append("Plan Origin is empty")
    elif origin_text not in PLAN_ORIGINS:
        issues.append(f"invalid Plan Origin: {origin_text}")

    traceability = _section_text(text, "Requirement Traceability")
    queue = _section_text(text, "Current Work Queue")
    requirement_ids = set(re.findall(r"\bREQ-\d{3}\b", traceability))
    if not requirement_ids:
        issues.append("Requirement Traceability has no stable requirement IDs")
    for requirement_id in sorted(requirement_ids):
        if requirement_id not in queue:
            issues.append(f"work queue does not cover {requirement_id}")

    sources = _section_text(text, "Inputs And Sources")
    if not sources:
        issues.append("Inputs And Sources is empty")
    if declared_external_sources and not re.search(r"https?://", sources):
        issues.append("declared external sources are missing from Inputs And Sources")

    decisions = _section_text(text, "User Decisions And Answers")
    if not decisions:
        issues.append("User Decisions And Answers is empty")

    fidelity = _section_text(text, "Plan Fidelity Check")
    if not fidelity:
        issues.append("Plan Fidelity Check is empty")
    elif require_fidelity_passed and re.search(r"(?m)^\s*-\s*\[ \]", fidelity):
        issues.append("Plan Fidelity Check has unchecked conditions")

    first_open = None
    for line in queue.splitlines():
        if re.search(r"(?:\[ \]|`(?:pending|in_progress|blocked)`)", line):
            match = re.search(r"\bWQ-\d{2}\b", line)
            if match:
                first_open = match.group(0)
                break
    resume = _section_text(text, "Resume Point")
    if first_open and first_open not in resume:
        issues.append(f"Resume Point does not identify first unfinished queue item {first_open}")
    if requirement_ids and len(queue.strip().splitlines()) < 1:
        issues.append("Current Work Queue is compressed or empty")
    return issues


def find_stale_completed_state(text: str) -> list[str]:
    stale = []
    patterns = {
        "next_work": r"\bnext work\b",
        "resume_instruction": r"\bresume (?:point|by|with|from)\b",
        "current_milestone": r"\bcurrent milestone\b",
        "active_blocker": r"\bactive blocker\b",
    }
    for match in re.finditer(
        r"(?ms)^## Recently Completed\s*$\n(?P<body>.*?)(?=^## |\Z)",
        text,
    ):
        for line_number, line in enumerate(match.group("body").splitlines(), start=1):
            if "explicit follow-up" in line.lower() or "do not leave" in line.lower():
                continue
            for name, pattern in patterns.items():
                if re.search(pattern, line, re.IGNORECASE):
                    stale.append(f"{name} in Recently Completed line {line_number}")
    return stale


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def find_placeholder_issues(text: str) -> list[str]:
    patterns = (
        r"\[TODO[:\]]",
        r"\{\{[^}]+\}\}",
        r"<(?!/?(?:details|summary|br|code|kbd|sub|sup)\b|!--|https?://)[A-Za-z][^>\n]{0,100}>",
    )
    return [pattern for pattern in patterns if re.search(pattern, text)]

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

sys.dont_write_bytecode = True

CANONICAL_UPSTREAM = "https://github.com/xeonvs/codex-engineering-workflow"
CANONICAL_SOURCE_PATH = "skill/engineering-workflow"
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
INSTRUCTION_FILES = {"SKILL.md", "agents/openai.yaml"}
INSTRUCTION_PREFIXES = ("references/",)
FULL_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
MARKETPLACE_NAME = "xeonvs-engineering"
PLUGIN_NAME = "engineering-workflow"
CANONICAL_MARKETPLACE = "https://github.com/xeonvs/xeonvs-engineering"
STABLE_TAG_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CLAUDE_PLUGIN_SCOPES = {"user", "project", "local"}


class UpdateConflict(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        recovery_path: Path | None = None,
        backup_path: Path | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.recovery_path = recovery_path
        self.backup_path = backup_path


def _run_git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="surrogateescape",
            check=False,
        )
    except OSError as exc:
        raise UpdateConflict("git_unavailable", "Git operation is unavailable") from exc
    if check and completed.returncode != 0:
        raise UpdateConflict("git_error", "Git operation failed")
    return completed


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    section = ""
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0 and raw.rstrip().endswith(":"):
            section = raw.rstrip()[:-1].strip()
            continue
        if ":" not in raw:
            continue
        key, value = raw.strip().split(":", 1)
        full_key = f"{section}.{key}" if indent and section else key
        values[full_key] = value.strip().strip("\"'")
    return values


def read_skill_identity(skill_dir: Path) -> dict[str, str]:
    skill_file = skill_dir / "SKILL.md"
    if skill_file.is_symlink() or not skill_file.is_file():
        raise UpdateConflict("missing_skill_file", "Candidate or installation is missing SKILL.md")
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UpdateConflict("invalid_skill_file", "SKILL.md must be a readable UTF-8 regular file") from exc
    metadata = _frontmatter(text)
    name = metadata.get("name", "")
    version = metadata.get("metadata.version", "")
    if not name:
        raise UpdateConflict("invalid_frontmatter", "SKILL.md frontmatter is missing name")
    if not SEMVER_RE.fullmatch(version):
        raise UpdateConflict("invalid_version", "SKILL.md metadata.version is not valid SemVer")
    return {"name": name, "version": version}


def _semver_key(version: str) -> tuple[int, int, int, tuple[tuple[int, str], ...]]:
    match = SEMVER_RE.fullmatch(version)
    if not match:
        raise UpdateConflict("invalid_version", f"Invalid SemVer: {version}")
    prerelease = match.group(4)
    if prerelease is None:
        pre_key = ((2, ""),)
    else:
        parts = []
        for part in prerelease.split("."):
            parts.append((0, f"{int(part):020d}") if part.isdigit() else (1, part))
        pre_key = tuple(parts)
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), pre_key


def _normalized_repo(value: str) -> str:
    stripped = value.strip().rstrip("/")
    github_patterns = (
        re.compile(r"^https://github\.com/(?P<path>[^/]+/[^/]+?)(?:\.git)?$", re.IGNORECASE),
        re.compile("^ssh" + r"://" + "git" + r"@github\.com/(?P<path>[^/]+/[^/]+?)(?:\.git)?$", re.IGNORECASE),
        re.compile("^git" + r"@github\.com:(?P<path>[^/]+/[^/]+?)(?:\.git)?$", re.IGNORECASE),
    )
    for pattern in github_patterns:
        match = pattern.fullmatch(stripped)
        if match:
            return "github.com/" + match.group("path").lower()
    if "://" not in stripped and not stripped.startswith("git@"):
        return str(Path(stripped).expanduser().resolve())
    return stripped.removesuffix(".git")


def _public_source_label(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "invalid-source-url"
    if not parsed.netloc:
        if parsed.query or parsed.fragment:
            return urlunsplit((parsed.scheme, "", parsed.path, "", ""))
        return value
    host = parsed.hostname or "redacted-source"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        return "invalid-source-url"
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _reject_source_credentials(value: str) -> None:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise UpdateConflict("invalid_source_url", "Source repository URL is malformed") from exc
    try:
        parsed.port
    except ValueError as exc:
        raise UpdateConflict("invalid_source_url", "Source repository URL is malformed") from exc
    http_userinfo = parsed.scheme.lower() in {"http", "https"} and parsed.username is not None
    if http_userinfo or parsed.password is not None or parsed.query or parsed.fragment:
        raise UpdateConflict(
            "source_credentials_refused", "Source repository URL must not contain embedded credentials"
        )


def _validated_expected_commit(value: str | None) -> str | None:
    if value is None:
        return None
    if not FULL_COMMIT_RE.fullmatch(value):
        raise UpdateConflict("invalid_expected_commit", "Expected commit must be a full 40-character Git object ID")
    return value.lower()


def is_canonical_upstream(source_repo: str) -> bool:
    return _normalized_repo(source_repo) == _normalized_repo(CANONICAL_UPSTREAM)


def _safe_source_path(value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise UpdateConflict("unsafe_source_path", "source path must be a normalized relative path")
    return path


def _validate_symlinks(candidate: Path) -> None:
    root = candidate.resolve()
    for path in candidate.rglob("*"):
        if not path.is_symlink():
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise UpdateConflict("invalid_candidate_symlink", "Candidate contains a broken symlink") from exc
        if not resolved.is_relative_to(root):
            raise UpdateConflict("escaping_candidate_symlink", "Candidate contains a symlink outside its tree")


def _reject_executable_cache(root: Path, code: str = "executable_cache_refused") -> None:
    if any("__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"} for path in root.rglob("*")):
        raise UpdateConflict(code, "Executable Python cache artifacts are not accepted as skill content")


def validate_candidate(candidate: Path) -> dict[str, Any]:
    if not candidate.is_dir():
        raise UpdateConflict("missing_source_path", "Source path is not a directory in the selected ref")
    _reject_executable_cache(candidate, "invalid_candidate_executable_cache")
    _validate_symlinks(candidate)
    required_files = ("SKILL.md", "agents/openai.yaml")
    required_directories = ("references", "scripts")
    if any((candidate / relative).is_symlink() or not (candidate / relative).is_file() for relative in required_files):
        raise UpdateConflict("invalid_candidate", "Candidate is missing a required regular file")
    if any(
        (candidate / relative).is_symlink() or not (candidate / relative).is_dir() for relative in required_directories
    ):
        raise UpdateConflict("invalid_candidate", "Candidate is missing a required directory")
    identity = read_skill_identity(candidate)
    if identity["name"] != "engineering-workflow":
        raise UpdateConflict("wrong_skill_name", "Candidate SKILL.md has the wrong skill name")
    if _semver_key(identity["version"]) >= _semver_key("0.10.0"):
        required_release_files = (
            "assets/release_adoption.json",
            "references/documentation_navigation.md",
            "scripts/documentation_navigation.py",
            "scripts/documentation_restructure.py",
            "scripts/release_adoption.py",
            "scripts/workflow_updates.py",
        )
        if any((candidate / path).is_symlink() or not (candidate / path).is_file() for path in required_release_files):
            raise UpdateConflict("invalid_candidate", "Candidate is missing a required release capability file")
        _candidate_descriptor(candidate)
    return {"success": True, "name": identity["name"], "version": identity["version"]}


def _candidate_descriptor(candidate: Path) -> dict[str, Any] | None:
    path = candidate / "assets" / "release_adoption.json"
    if not path.exists():
        return None
    from release_adoption import load_descriptor

    try:
        data = load_descriptor(json.loads(path.read_text(encoding="utf-8")))
        if data["skill_version"] != read_skill_identity(candidate)["version"]:
            raise ValueError
        local = load_descriptor()
        required_ids = {
            change["id"]
            for change in local["changes"]
            if _semver_key(change["introduced_in"]) <= _semver_key(data["skill_version"])
        }
        if not required_ids.issubset({change["id"] for change in data["changes"]}):
            raise ValueError
        candidate_changes = {change["id"]: change for change in data["changes"]}
        if any(
            not isinstance(change.get("summary"), str)
            or not 1 <= len(change["summary"]) <= 240
            or any(ord(character) < 32 or ord(character) == 127 for character in change["summary"])
            for change in data["changes"]
        ):
            raise ValueError
        if any(
            candidate_changes[change["id"]][field] != change[field]
            for change in local["changes"]
            if change["id"] in required_ids
            for field in ("introduced_in", "summary", "adoption_requirement", "affected_owner_patterns")
        ):
            raise ValueError
        # Bounded capability metadata only; do not persist arbitrary source fields or document bodies.
        return {
            "schema_version": 1,
            "skill_version": data["skill_version"],
            "changes": [
                {
                    key: change[key]
                    for key in ("id", "introduced_in", "summary", "adoption_requirement", "affected_owner_patterns")
                }
                for change in data["changes"]
            ],
        }
    except (ValueError, OSError, UnicodeError, KeyError) as exc:
        raise UpdateConflict("invalid_adoption_descriptor", "Candidate release capability metadata is invalid") from exc


def _materialize_tree(checkout: Path, resolved: str, source_path: str, candidate: Path) -> None:
    safe_source = _safe_source_path(source_path).as_posix()
    object_type = _run_git("cat-file", "-t", f"{resolved}:{safe_source}", cwd=checkout).stdout.strip()
    if object_type != "tree":
        raise UpdateConflict("invalid_source_path", "Source path is not a directory tree in the selected ref")
    completed = subprocess.run(
        ["git", "ls-tree", "-rz", "-r", resolved, "--", safe_source],
        cwd=checkout,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise UpdateConflict("git_error", "Unable to inspect candidate tree")
    candidate.mkdir(parents=True)
    prefix = safe_source.rstrip("/") + "/"
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_kind, object_id = metadata.decode("ascii").split()
            repo_path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise UpdateConflict("invalid_candidate_path", "Candidate contains an unsupported path") from exc
        if not repo_path.startswith(prefix):
            raise UpdateConflict("invalid_candidate_path", "Candidate tree entry escapes the source path")
        relative = Path(repo_path[len(prefix) :])
        if not relative.parts or relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise UpdateConflict("invalid_candidate_path", "Candidate contains an unsafe path")
        destination = candidate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if object_kind != "blob":
            raise UpdateConflict("invalid_candidate_object", "Candidate contains a non-file object")
        blob = subprocess.run(
            ["git", "cat-file", "blob", object_id],
            cwd=checkout,
            capture_output=True,
            check=False,
        )
        if blob.returncode != 0:
            raise UpdateConflict("git_error", "Unable to read a candidate object")
        if mode == "120000":
            try:
                link_target = blob.stdout.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise UpdateConflict("invalid_candidate_symlink", "Candidate symlink target is not UTF-8") from exc
            try:
                os.symlink(link_target, destination)
            except (OSError, ValueError) as exc:
                raise UpdateConflict("invalid_candidate_symlink", "Candidate symlink target is invalid") from exc
        elif mode in {"100644", "100755"}:
            destination.write_bytes(blob.stdout)
            destination.chmod(0o755 if mode == "100755" else 0o644)
        else:
            raise UpdateConflict("invalid_candidate_mode", "Candidate contains an unsupported file mode")


def _latest_stable_tag(checkout: Path) -> str:
    tags = _run_git("for-each-ref", "--format=%(refname:short) %(objecttype)", "refs/tags", cwd=checkout)
    stable = [
        tag
        for line in tags.stdout.splitlines()
        for tag, kind in [line.rsplit(" ", 1)]
        if kind == "tag" and STABLE_TAG_RE.fullmatch(tag)
    ]
    if not stable:
        raise UpdateConflict("stable_release_unavailable", "Upstream has no annotated stable SemVer release")
    return max(stable, key=lambda tag: _semver_key(tag[1:]))


def _clone_candidate(source_repo: str, source_path: str, ref: str | None, temp_root: Path) -> tuple[Path, Path, str]:
    checkout = temp_root / "source"
    try:
        _run_git("clone", "--quiet", "--no-checkout", "--", source_repo, str(checkout))
    except UpdateConflict as exc:
        raise UpdateConflict("upstream_unavailable", "Upstream could not be checked; currentness is unknown") from exc
    selected_ref = ref if ref is not None else _latest_stable_tag(checkout)
    resolved = _run_git("rev-parse", "--verify", f"{selected_ref}^{{commit}}", cwd=checkout).stdout.strip()
    candidate = temp_root / "candidate"
    _materialize_tree(checkout, resolved, source_path, candidate)
    return checkout, candidate, resolved


def _git_root(path: Path) -> Path | None:
    result = _run_git("-C", str(path), "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _plugin_managed_root(skill_path: Path) -> tuple[Path, list[str]] | None:
    for candidate in (skill_path, *list(skill_path.parents)[:4]):
        try:
            relative = skill_path.relative_to(candidate)
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] != "skills":
            continue
        platforms = []
        if (candidate / ".codex-plugin" / "plugin.json").is_file():
            platforms.append("codex")
        if (candidate / ".claude-plugin" / "plugin.json").is_file():
            platforms.append("claude")
        if platforms:
            return candidate, platforms
    return None


def _installation_details(install_path: Path, source_path: str) -> dict[str, Any]:
    if not install_path.exists() and not install_path.is_symlink():
        raise UpdateConflict("missing_installation", "The exact install path does not exist")
    symlinked = install_path.is_symlink()
    try:
        resolved = install_path.resolve(strict=True)
    except OSError as exc:
        raise UpdateConflict("broken_installation_symlink", "The install path cannot be resolved") from exc
    if not resolved.is_dir():
        raise UpdateConflict("invalid_installation", "The install path does not resolve to a directory")
    identity = read_skill_identity(resolved)
    if identity["name"] != "engineering-workflow":
        raise UpdateConflict("wrong_installed_skill", "The exact install path is not engineering-workflow")
    plugin_managed = _plugin_managed_root(resolved)
    if plugin_managed is not None:
        plugin_root, platforms = plugin_managed
        return {
            "active_installation_path": str(install_path.absolute()),
            "resolved_target_path": str(resolved),
            "installation_type": "plugin_managed",
            "update_strategy": "marketplace",
            "git_root": None,
            "plugin_root": str(plugin_root),
            "plugin_platforms": platforms,
            "previous_version": identity["version"],
        }
    root = _git_root(resolved)
    expected_relative = _safe_source_path(source_path)
    is_source_checkout = bool(root and (root / expected_relative).resolve() == resolved)
    if root and root == resolved:
        is_source_checkout = True
    strategy = "git_checkout" if is_source_checkout else "copied"
    installation_type = "symlink" if symlinked else strategy
    return {
        "active_installation_path": str(install_path.absolute()),
        "resolved_target_path": str(resolved),
        "installation_type": installation_type,
        "update_strategy": strategy,
        "git_root": root,
        "previous_version": identity["version"],
    }


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _tree_entries(root: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries[relative] = "symlink:" + os.readlink(path)
        elif path.is_file():
            entries[relative] = "file:" + _file_digest(path)
    return entries


def diff_summary(current: Path, candidate: Path) -> dict[str, Any]:
    old_files = _tree_entries(current)
    new_files = _tree_entries(candidate)
    old_names = set(old_files)
    new_names = set(new_files)
    modified = sorted(name for name in old_names & new_names if old_files[name] != new_files[name])
    return {
        "added": sorted(new_names - old_names),
        "modified": modified,
        "deleted": sorted(old_names - new_names),
        "counts": {
            "added": len(new_names - old_names),
            "modified": len(modified),
            "deleted": len(old_names - new_names),
        },
    }


def _filtered_diff(summary: dict[str, Any], predicate: Callable[[str], bool]) -> dict[str, Any]:
    filtered = {
        category: [path for path in summary[category] if predicate(path)]
        for category in ("added", "modified", "deleted")
    }
    filtered["counts"] = {category: len(filtered[category]) for category in ("added", "modified", "deleted")}
    return filtered


def _is_instruction_path(path: str) -> bool:
    return path in INSTRUCTION_FILES or path.startswith(INSTRUCTION_PREFIXES)


def _version_change_kind(previous: str, candidate: str) -> str:
    previous_match = SEMVER_RE.fullmatch(previous)
    candidate_match = SEMVER_RE.fullmatch(candidate)
    if not previous_match or not candidate_match:
        raise UpdateConflict("invalid_version", "Cannot compare invalid skill versions")
    if _semver_key(candidate) == _semver_key(previous):
        return "none"
    if _semver_key(candidate) < _semver_key(previous):
        return "downgrade"
    previous_core = tuple(int(previous_match.group(index)) for index in range(1, 4))
    candidate_core = tuple(int(candidate_match.group(index)) for index in range(1, 4))
    if candidate_core[0] != previous_core[0]:
        return "major"
    if candidate_core[1] != previous_core[1]:
        return "minor"
    if candidate_core[2] != previous_core[2]:
        return "patch"
    return "prerelease"


def refresh_decision(
    previous_version: str,
    candidate_version: str,
    summary: dict[str, Any],
    *,
    canonical_upstream: bool,
) -> dict[str, Any]:
    instruction_summary = _filtered_diff(summary, _is_instruction_path)
    content_changed = any(summary["counts"].values())
    instructions_changed = any(instruction_summary["counts"].values())
    version_change = _version_change_kind(previous_version, candidate_version)
    previous_match = SEMVER_RE.fullmatch(previous_version)
    candidate_match = SEMVER_RE.fullmatch(candidate_version)
    assert previous_match is not None and candidate_match is not None
    major_or_minor_changed = tuple(previous_match.group(index) for index in (1, 2)) != tuple(
        candidate_match.group(index) for index in (1, 2)
    )
    recommended = "update_installed_skill" if content_changed else "refresh_loaded_skill"
    protected = content_changed and (not canonical_upstream or version_change == "downgrade")
    return {
        "skill_content_changed": content_changed,
        "instructions_changed": instructions_changed,
        "instruction_diff_summary": instruction_summary,
        "version_change_kind": version_change,
        "major_or_minor_version_changed": major_or_minor_changed,
        "recommended_action": recommended,
        "next_agent_action": recommended,
        "automatic_update_allowed": content_changed and not protected,
        "confirmation_required": content_changed and not canonical_upstream,
    }


def _checkout_state(
    details: dict[str, Any],
    source_repo: str,
    ref: str,
    candidate_checkout: Path,
    candidate_commit: str,
) -> dict[str, Any]:
    root = details["git_root"]
    assert isinstance(root, Path)
    dirty = _run_git("status", "--porcelain=v1", "--untracked-files=all", cwd=root).stdout.strip()
    if dirty:
        raise UpdateConflict("dirty_checkout", "Git checkout has local changes")
    installed = Path(str(details["resolved_target_path"]))
    try:
        skill_relative = installed.relative_to(root).as_posix()
    except ValueError as exc:
        raise UpdateConflict("invalid_installation", "Installed skill is outside its Git checkout") from exc
    ignored = _run_git(
        "status",
        "--porcelain=v1",
        "--ignored=matching",
        "--untracked-files=all",
        "--",
        skill_relative,
        cwd=root,
    ).stdout.splitlines()
    flagged = _run_git("ls-files", "-v", "--", skill_relative, cwd=root).stdout.splitlines()
    if any(line.startswith("!! ") for line in ignored) or any(
        line and (line[0] == "S" or line[0].islower()) for line in flagged
    ):
        raise UpdateConflict(
            "checkout_hidden_drift",
            "Git checkout contains ignored or index-hidden content in the installed skill tree",
        )
    remote_result = _run_git("remote", "get-url", "origin", cwd=root, check=False)
    if remote_result.returncode != 0:
        raise UpdateConflict("missing_origin", "Git checkout has no origin remote")
    actual_remote = remote_result.stdout.strip()
    if _normalized_repo(actual_remote) != _normalized_repo(source_repo):
        raise UpdateConflict("remote_mismatch", "Git checkout origin does not match source repository")
    branch_result = _run_git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=root, check=False)
    if branch_result.returncode != 0:
        raise UpdateConflict("detached_checkout", "Git checkout is detached")
    branch = branch_result.stdout.strip()
    if re.fullmatch(r"[A-Za-z0-9._/-]+", ref) and ref not in {"HEAD", branch, f"refs/heads/{branch}"}:
        raise UpdateConflict("branch_ref_mismatch", "Current branch does not match the requested ref")
    current_commit = _run_git("rev-parse", "HEAD", cwd=root).stdout.strip()
    candidate_has_current = _run_git(
        "cat-file", "-e", f"{current_commit}^{{commit}}", cwd=candidate_checkout, check=False
    )
    if candidate_has_current.returncode != 0:
        raise UpdateConflict("divergent_checkout", "Current checkout commit is absent from source history")
    ancestor = _run_git(
        "merge-base", "--is-ancestor", current_commit, candidate_commit, cwd=candidate_checkout, check=False
    )
    if ancestor.returncode != 0:
        raise UpdateConflict("divergent_checkout", "Git checkout cannot be updated by fast-forward")
    return {"branch": branch, "current_commit": current_commit, "remote": actual_remote}


def _backup_destination(backup_dir: Path, version: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_dir / f"engineering-workflow-{version}-{stamp}"
    if destination.exists():
        destination = backup_dir / f"engineering-workflow-{version}-{stamp}-{uuid.uuid4().hex[:8]}"
    return destination


def _replace_copied_installation(current: Path, candidate: Path, backup_dir: Path, version: str) -> Path:
    resolved_current = current.resolve()
    resolved_backup_dir = backup_dir.resolve()
    if resolved_backup_dir == resolved_current or resolved_backup_dir.is_relative_to(resolved_current):
        raise UpdateConflict("unsafe_backup_path", "Backup directory must be outside the installed skill tree")
    backup: Path | None = None
    try:
        backup = _backup_destination(backup_dir, version)
        shutil.copytree(current, backup, symlinks=True)
    except Exception as exc:
        if backup is not None and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        raise UpdateConflict(
            "backup_failed",
            "Installation backup could not be created; the active installation is unchanged",
            recovery_path=backup if backup is not None and backup.exists() else None,
        ) from exc
    try:
        stage_parent = Path(tempfile.mkdtemp(prefix=".engineering-workflow-stage-", dir=current.parent))
    except Exception as exc:
        raise UpdateConflict(
            "staging_failed",
            "Installation staging directory could not be created; the active installation is unchanged",
            backup_path=backup,
        ) from exc
    staged = stage_parent / current.name
    rollback = current.parent / f".{current.name}.rollback-{uuid.uuid4().hex}"
    try:
        shutil.copytree(candidate, staged, symlinks=True)
        os.replace(current, rollback)
        try:
            os.replace(staged, current)
        except Exception as replacement_error:
            try:
                os.replace(rollback, current)
            except Exception as restore_error:
                raise UpdateConflict(
                    "rollback_failed",
                    "Copied installation replacement and automatic restore failed; recovery trees were preserved",
                    recovery_path=rollback,
                    backup_path=backup,
                ) from restore_error
            raise UpdateConflict(
                "replacement_failed",
                "Copied installation replacement failed and was rolled back",
                backup_path=backup,
            ) from replacement_error
        try:
            shutil.rmtree(rollback)
        except Exception as cleanup_error:
            raise UpdateConflict(
                "rollback_cleanup_failed",
                "Installation was replaced but the rollback tree could not be removed",
                recovery_path=rollback,
                backup_path=backup,
            ) from cleanup_error
    except UpdateConflict:
        raise
    except Exception as exc:
        if rollback.exists() and not current.exists():
            try:
                os.replace(rollback, current)
            except Exception as restore_error:
                raise UpdateConflict(
                    "rollback_failed",
                    "Copied installation replacement and automatic restore failed; recovery trees were preserved",
                    recovery_path=rollback,
                    backup_path=backup,
                ) from restore_error
        raise UpdateConflict(
            "replacement_failed",
            "Copied installation replacement failed and was rolled back",
            backup_path=backup,
        ) from exc
    finally:
        shutil.rmtree(stage_parent, ignore_errors=True)
    return backup


def _bundle_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise UpdateConflict("invalid_delivery_bundle", "Delivery bundle contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise UpdateConflict("invalid_delivery_bundle", "Delivery bundle contains a special file")
        name = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _delivery_provenance(text: str) -> dict[str, Any]:
    try:
        document = json.loads(text)
        if document["schema_version"] != 1 or document["catalog_version"] != "1.0.0":
            raise ValueError
        bundles = [item for item in document["bundles"] if item["name"] == PLUGIN_NAME]
        if len(bundles) != 1:
            raise ValueError
        bundle = bundles[0]
        if (
            not is_canonical_upstream(bundle["source_repository"])
            or bundle["source_policy"] != "latest-tag"
            or bundle["source_path"] != "plugins/engineering-workflow"
            or not STABLE_TAG_RE.fullmatch(bundle["source_ref"])
            or bundle["version"] != bundle["source_ref"][1:]
            or not FULL_COMMIT_RE.fullmatch(bundle["source_commit"])
            or not re.fullmatch(r"[0-9a-f]{64}", bundle["bundle_sha256"])
        ):
            raise ValueError
        return {
            key: bundle[key]
            for key in (
                "name",
                "version",
                "source_repository",
                "source_policy",
                "source_path",
                "source_ref",
                "source_commit",
                "bundle_sha256",
            )
        } | {"catalog_version": document["catalog_version"]}
    except (ValueError, TypeError, KeyError) as exc:
        raise UpdateConflict("invalid_delivery_provenance", "Catalog provenance is missing or invalid") from exc


def _run_platform(platform: str, *args: str) -> Any:
    try:
        completed = subprocess.run([platform, *args], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise UpdateConflict("native_update_unavailable", "Native plugin command is unavailable") from exc
    if completed.returncode:
        raise UpdateConflict("native_update_failed", "Native plugin command failed")
    if "--json" not in args or not completed.stdout.strip():
        return {}
    try:
        return json.loads(completed.stdout)
    except ValueError as exc:
        raise UpdateConflict("native_result_invalid", "Native plugin command returned invalid JSON") from exc


def _native_inventory(platform: str) -> dict[str, Any]:
    identifier = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
    args = (
        ("plugin", "list", "--marketplace", MARKETPLACE_NAME, "--json")
        if platform == "codex"
        else (
            "plugin",
            "list",
            "--json",
        )
    )
    document = _run_platform(platform, *args)
    entries = document.get("installed", []) if platform == "codex" and isinstance(document, dict) else document
    if not isinstance(entries, list):
        raise UpdateConflict("native_result_invalid", "Native plugin inventory has an unsupported schema")
    matches = [
        item
        for item in entries
        if isinstance(item, dict) and item.get("pluginId" if platform == "codex" else "id") == identifier
    ]
    if len(matches) != 1 or matches[0].get("enabled") is not True:
        raise UpdateConflict("native_active_identity_mismatch", "Exact plugin is missing, ambiguous, or disabled")
    item = matches[0]
    if platform == "codex":
        source = item.get("marketplaceSource", {})
        if source.get("sourceType") != "git" or _normalized_repo(source.get("source", "")) != _normalized_repo(
            CANONICAL_MARKETPLACE
        ):
            raise UpdateConflict("native_marketplace_mismatch", "Native plugin uses a different marketplace source")
    return item


def _native_path_resolution(item: dict[str, Any], platform: str) -> tuple[str | None, dict[str, Any]]:
    field_names = ("installedPath", "installPath") if platform == "codex" else ("installPath", "installedPath")
    for name in field_names:
        if isinstance(item.get(name), str):
            return item[name], {"source": "native_inventory", "field": name, "path": item[name]}
    if platform != "codex" or not isinstance(item.get("version"), str) or not SEMVER_RE.fullmatch(item["version"]):
        return None, {"source": "unresolved", "path": None}
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().absolute()
    derived = codex_home / "plugins" / "cache" / MARKETPLACE_NAME / PLUGIN_NAME / item["version"]
    return str(derived), {
        "source": "codex_cache_layout",
        "codex_home": str(codex_home),
        "marketplace": MARKETPLACE_NAME,
        "plugin": PLUGIN_NAME,
        "version": item["version"],
        "path": str(derived),
    }


def _native_active_path(item: dict[str, Any], platform: str) -> str | None:
    return _native_path_resolution(item, platform)[0]


def _native_active_skill(item: dict[str, Any], platform: str) -> Path:
    """Resolve the exact active skill path reported by the selected native client."""
    raw_path = _native_active_path(item, platform)
    if raw_path is None:
        raise UpdateConflict("native_active_identity_mismatch", "Native plugin inventory omits its active path")
    try:
        active_root = Path(raw_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise UpdateConflict("native_active_identity_mismatch", "Native active plugin path cannot be read") from exc
    active_skill = active_root if (active_root / "SKILL.md").is_file() else active_root / "skills" / PLUGIN_NAME
    try:
        active_skill = active_skill.resolve(strict=True)
        identity = read_skill_identity(active_skill)
    except (OSError, UpdateConflict) as exc:
        raise UpdateConflict("native_active_identity_mismatch", "Native active skill path cannot be verified") from exc
    if identity["name"] != PLUGIN_NAME:
        raise UpdateConflict("native_active_identity_mismatch", "Native inventory resolves to another skill")
    plugin_root = active_root if active_root != active_skill else active_skill.parent.parent
    manifest = plugin_root / f".{platform}-plugin" / "plugin.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise UpdateConflict("native_active_identity_mismatch", "Native active plugin manifest is not regular")
    return active_skill


def _record_native_observation(result: dict[str, Any], item: dict[str, Any], active_path: str | None) -> Path | None:
    """Preserve truthful post-mutation observations before strict byte verification."""
    result["currentness"] = "unknown"
    result["native_mutation_attempted"] = True
    observed_version = item.get("version")
    if isinstance(observed_version, str) and SEMVER_RE.fullmatch(observed_version):
        result["installed_version"] = observed_version
        result["observed_native_version"] = observed_version
    if not isinstance(active_path, str):
        return None
    observed_root = Path(active_path).expanduser().absolute()
    observed_skill = observed_root if (observed_root / "SKILL.md").is_file() else observed_root / "skills" / PLUGIN_NAME
    result["active_installation_path"] = str(observed_skill)
    result["resolved_target_path"] = str(observed_skill)
    result["observed_native_path"] = str(observed_skill)
    return observed_skill


def _begin_native_mutation(result: dict[str, Any]) -> None:
    """Drop pre-mutation active-state claims before the first native write."""
    result.update(
        {
            "currentness": "unknown",
            "native_mutation_attempted": True,
            "native_readback_verified": False,
            "installed_version": None,
            "active_installation_path": None,
            "resolved_target_path": None,
            "observed_native_version": None,
            "observed_native_path": None,
        }
    )


def _capture_native_observation(result: dict[str, Any], platform: str) -> None:
    """Best-effort, read-only native state recovery after a write-path failure."""
    try:
        observed = _native_inventory(platform)
    except (OSError, UpdateConflict):
        return
    active_path, evidence = _native_path_resolution(observed, platform)
    result.setdefault("path_resolution_evidence", {})["recovery"] = evidence
    _record_native_observation(result, observed, active_path)


def _catalog_snapshot_bundle(item: dict[str, Any], provenance: dict[str, Any]) -> None:
    source = item.get("source", {})
    if source.get("source") != "local" or not isinstance(source.get("path"), str):
        raise UpdateConflict("native_catalog_unverified", "Native marketplace snapshot path is unavailable")
    bundle = Path(source["path"])
    metadata = bundle.parent.parent / "PROVENANCE.json"
    try:
        if metadata.is_symlink() or not metadata.is_file():
            raise OSError
        observed = _delivery_provenance(metadata.read_text(encoding="utf-8"))
        if observed != provenance or _bundle_digest(bundle) != provenance["bundle_sha256"]:
            raise UpdateConflict("native_delivery_mismatch", "Native marketplace differs from the reviewed delivery")
    except (OSError, UnicodeError) as exc:
        raise UpdateConflict("native_catalog_unverified", "Native marketplace provenance cannot be read") from exc


def _claude_marketplace_snapshot() -> dict[str, Any]:
    document = _run_platform("claude", "plugin", "marketplace", "list", "--json")
    if not isinstance(document, list):
        raise UpdateConflict("native_result_invalid", "Native marketplace inventory has an unsupported schema")
    matches = [item for item in document if isinstance(item, dict) and item.get("name") == MARKETPLACE_NAME]
    if len(matches) != 1:
        raise UpdateConflict("native_marketplace_mismatch", "Exact native marketplace is missing or ambiguous")
    item = matches[0]
    repository = item.get("repo", "")
    if item.get("source") == "github":
        repository = "https://github.com/" + repository if isinstance(repository, str) else ""
    elif item.get("source") in {"git", "url"}:
        repository = item.get("url") or repository
    else:
        raise UpdateConflict("native_marketplace_mismatch", "Native marketplace source is unsupported")
    if not isinstance(repository, str):
        raise UpdateConflict("native_marketplace_mismatch", "Native marketplace source is unsupported")
    _reject_source_credentials(repository)
    if _normalized_repo(repository) != _normalized_repo(CANONICAL_MARKETPLACE):
        raise UpdateConflict("native_marketplace_mismatch", "Native plugin uses a different marketplace source")
    location = item.get("installLocation")
    if not isinstance(location, str):
        raise UpdateConflict("native_catalog_unverified", "Native marketplace snapshot path is unavailable")
    return {"source": {"source": "local", "path": str(Path(location) / "plugins" / PLUGIN_NAME)}}


def _update_plugin(
    result: dict[str, Any],
    details: dict[str, Any],
    source_checkout: Path,
    *,
    apply: bool,
    expected_commit: str | None,
    expected_catalog_commit: str | None,
    platform: str | None,
    canonical_upstream: bool,
    allow_downgrade: bool,
) -> dict[str, Any]:
    result["direct_cache_replacement_allowed"] = False
    result["source_latest_version"] = result["candidate_version"]
    result["source_latest_ref"] = result["source_ref"]
    result["source_latest_commit"] = result["resolved_commit"]
    result["currentness"] = "unknown"
    if not canonical_upstream:
        raise UpdateConflict("plugin_alternate_source_refused", "Plugin delivery requires the canonical source")
    with tempfile.TemporaryDirectory(prefix="engineering-workflow-delivery-") as temp_name:
        catalog, delivery_skill, catalog_commit = _clone_candidate(
            CANONICAL_MARKETPLACE, "plugins/engineering-workflow/skills/engineering-workflow", None, Path(temp_name)
        )
        catalog_ref = _latest_stable_tag(catalog)
        provenance = _delivery_provenance(_run_git("show", f"{catalog_commit}:PROVENANCE.json", cwd=catalog).stdout)
        bundle = Path(temp_name) / "bundle"
        _materialize_tree(catalog, catalog_commit, "plugins/engineering-workflow", bundle)
        _reject_executable_cache(bundle, "invalid_delivery_executable_cache")
        if _bundle_digest(bundle) != provenance["bundle_sha256"]:
            raise UpdateConflict("delivery_digest_mismatch", "Catalog bundle differs from its provenance digest")
        source_ref = provenance["source_ref"]
        if _run_git("cat-file", "-t", f"refs/tags/{source_ref}", cwd=source_checkout).stdout.strip() != "tag":
            raise UpdateConflict("unreleased_delivery_source", "Catalog source is not an annotated stable release")
        source_commit = _run_git("rev-parse", f"refs/tags/{source_ref}^{{commit}}", cwd=source_checkout).stdout.strip()
        if source_commit != provenance["source_commit"]:
            raise UpdateConflict("delivery_source_mismatch", "Catalog provenance differs from the source release")
        delivered_source = Path(temp_name) / "delivered-source"
        _materialize_tree(source_checkout, source_commit, CANONICAL_SOURCE_PATH, delivered_source)
        identity = validate_candidate(delivery_skill)
        if identity["version"] != provenance["version"] or any(
            diff_summary(delivered_source, delivery_skill)["counts"].values()
        ):
            raise UpdateConflict("delivery_source_mismatch", "Delivered skill bytes differ from the source release")
        result.update(
            {
                "catalog_ref": catalog_ref,
                "catalog_commit": catalog_commit,
                "delivery_provenance": provenance,
                "candidate_version": identity["version"],
                "source_ref": source_ref,
                "resolved_commit": source_commit,
                "delivery_pending": _semver_key(result["source_latest_version"]) > _semver_key(identity["version"]),
                "currentness": "checked",
                "release_adoption_descriptor": _candidate_descriptor(delivery_skill),
            }
        )
        current = Path(details["resolved_target_path"])
        result["diff_summary"] = diff_summary(current, delivery_skill)
        result.update(
            refresh_decision(
                details["previous_version"], identity["version"], result["diff_summary"], canonical_upstream=True
            )
        )
        if _semver_key(identity["version"]) < _semver_key(details["previous_version"]) and not allow_downgrade:
            raise UpdateConflict("downgrade_refused", "Marketplace delivery is older than the active installation")
        result["recommended_action"] = (
            "marketplace_update" if result["skill_content_changed"] else "refresh_loaded_skill"
        )
        result["next_agent_action"] = result["recommended_action"]
        result["marketplace_handoff"] = {
            "marketplace": MARKETPLACE_NAME,
            "plugin": PLUGIN_NAME,
            "platforms": details["plugin_platforms"],
            "direct_cache_replacement_allowed": False,
        }
        if not apply or not result["skill_content_changed"]:
            result["success"] = True
            result["update_status"] = "update_available" if result["skill_content_changed"] else "up_to_date"
            return result
        if expected_commit != source_commit or _validated_expected_commit(expected_catalog_commit) != catalog_commit:
            raise UpdateConflict(
                "expected_delivery_mismatch", "Native apply requires the exact reviewed source and catalog commits"
            )
        if platform not in details["plugin_platforms"]:
            raise UpdateConflict("native_platform_required", "Select the established native platform for update")
        before = _native_inventory(platform)
        _, before_path_evidence = _native_path_resolution(before, platform)
        result["path_resolution_evidence"] = {"before": before_path_evidence}
        before_skill = _native_active_skill(before, platform)
        if (
            before_skill != Path(details["resolved_target_path"]).resolve(strict=True)
            or before.get("version") != details["previous_version"]
            or read_skill_identity(before_skill)["version"] != details["previous_version"]
        ):
            raise UpdateConflict(
                "native_active_identity_mismatch", "Active plugin changed since installation inspection"
            )
        _reject_executable_cache(before_skill, "native_active_executable_cache")
        scope = None
        if platform == "claude":
            scope = before.get("scope")
            if scope not in CLAUDE_PLUGIN_SCOPES:
                raise UpdateConflict("native_scope_unverified", "Claude plugin scope is missing or unsupported")
            _claude_marketplace_snapshot()
        identifier = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
        applied_path = None
        _begin_native_mutation(result)
        try:
            if platform == "codex":
                _run_platform(platform, "plugin", "marketplace", "upgrade", MARKETPLACE_NAME, "--json")
                _catalog_snapshot_bundle(_native_inventory(platform), provenance)
                applied = _run_platform(platform, "plugin", "add", identifier, "--json")
                applied_path = applied.get("installedPath") if isinstance(applied, dict) else None
            else:
                _run_platform(platform, "plugin", "marketplace", "update", MARKETPLACE_NAME)
                _catalog_snapshot_bundle(_claude_marketplace_snapshot(), provenance)
                _run_platform(platform, "plugin", "update", identifier, "--scope", str(scope), "--json")
            after = _native_inventory(platform)
            active_path, after_path_evidence = _native_path_resolution(after, platform)
            result["path_resolution_evidence"]["after"] = after_path_evidence
            observed_skill = _record_native_observation(result, after, active_path)
            if not isinstance(active_path, str) or after.get("version") != identity["version"]:
                raise UpdateConflict(
                    "native_post_update_mismatch", "Native update did not activate the reviewed version/path"
                )
            if isinstance(applied_path, str) and Path(applied_path).resolve() != Path(active_path).resolve():
                raise UpdateConflict("native_post_update_mismatch", "Native apply and active inventory paths differ")
            try:
                active_bundle = Path(active_path).resolve(strict=True)
            except OSError as exc:
                raise UpdateConflict("native_post_update_mismatch", "Native active plugin path cannot be read") from exc
            active_skill = active_bundle / "skills" / PLUGIN_NAME
            if _bundle_digest(active_bundle) != provenance["bundle_sha256"] or any(
                diff_summary(active_skill, delivery_skill)["counts"].values()
            ):
                raise UpdateConflict(
                    "native_post_update_mismatch", "Active plugin bytes differ from the reviewed delivery"
                )
            if platform == "codex":
                _catalog_snapshot_bundle(after, provenance)
            else:
                _catalog_snapshot_bundle(_claude_marketplace_snapshot(), provenance)
        except (OSError, UpdateConflict):
            _capture_native_observation(result, platform)
            raise
        assert observed_skill is not None
        result.update(
            {
                "success": True,
                "update_status": "updated",
                "currentness": "checked",
                "active_installation_path": str(observed_skill),
                "resolved_target_path": str(observed_skill),
                "installed_version": read_skill_identity(observed_skill)["version"],
                "next_agent_action": "refresh_loaded_skill",
                "native_readback_verified": True,
            }
        )
        return result


def update_installation(
    install_path: Path,
    source_repo: str = CANONICAL_UPSTREAM,
    source_path: str = CANONICAL_SOURCE_PATH,
    ref: str | None = None,
    *,
    apply: bool = False,
    allow_downgrade: bool = False,
    backup_dir: Path | None = None,
    confirm_alternate_upstream: bool = False,
    expected_commit: str | None = None,
    expected_catalog_commit: str | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "success": False,
        "mode": "apply" if apply else "check",
        "source_repository": _public_source_label(source_repo),
        "source_path": source_path,
        "source_ref": ref,
        "release_channel": "stable" if ref is None else "explicit_ref",
        "currentness": "unknown",
        "resolved_commit": None,
        "expected_commit": None,
        "previous_version": None,
        "candidate_version": None,
        "active_installation_path": str(install_path.absolute()),
        "resolved_target_path": None,
        "installation_type": None,
        "backup_path": None,
        "recovery_path": None,
        "validation_result": {"success": False},
        "update_status": "failed",
        "restart_or_next_turn_required": False,
        "reload_fallback": "restart_if_change_not_detected",
        "skill_content_changed": None,
        "instructions_changed": None,
        "instruction_diff_summary": None,
        "version_change_kind": None,
        "major_or_minor_version_changed": None,
        "recommended_action": None,
        "next_agent_action": None,
        "automatic_update_allowed": False,
        "confirmation_required": False,
        "marketplace_handoff": None,
        "errors": [],
    }
    try:
        validated_expected = _validated_expected_commit(expected_commit)
        result["expected_commit"] = validated_expected
        details = _installation_details(install_path, source_path)
        result.update({key: value for key, value in details.items() if key not in {"git_root", "update_strategy"}})
        _reject_source_credentials(source_repo)
        canonical_upstream = is_canonical_upstream(source_repo)
        if apply and not canonical_upstream:
            if not confirm_alternate_upstream:
                result["update_status"] = "confirmation_required"
                raise UpdateConflict(
                    "alternate_upstream_confirmation_required",
                    "Alternate upstream requires explicit confirmation",
                )
            if validated_expected is None:
                raise UpdateConflict(
                    "expected_commit_required",
                    "Alternate-upstream apply requires the full commit returned by check mode",
                )
        with tempfile.TemporaryDirectory(prefix="engineering-workflow-update-") as temp_name:
            checkout, candidate, resolved_commit = _clone_candidate(source_repo, source_path, ref, Path(temp_name))
            validation = validate_candidate(candidate)
            if ref is None:
                selected_ref = _latest_stable_tag(checkout)
                result["source_ref"] = selected_ref
                if validation["version"] != selected_ref[1:]:
                    raise UpdateConflict("release_version_mismatch", "Release tag and skill version differ")
            result["resolved_commit"] = resolved_commit
            result["candidate_version"] = validation["version"]
            result["validation_result"] = validation
            result["release_adoption_descriptor"] = _candidate_descriptor(candidate)
            result["currentness"] = "checked"
            current = Path(str(result["resolved_target_path"]))
            result["diff_summary"] = diff_summary(current, candidate)
            result.update(
                refresh_decision(
                    str(result["previous_version"]),
                    validation["version"],
                    result["diff_summary"],
                    canonical_upstream=canonical_upstream,
                )
            )

            if (
                _semver_key(validation["version"]) < _semver_key(str(result["previous_version"]))
                and not allow_downgrade
            ):
                result["automatic_update_allowed"] = False
                raise UpdateConflict(
                    "downgrade_refused", "Candidate version is older; use --allow-downgrade to proceed"
                )
            if (
                apply
                and details["update_strategy"] != "marketplace"
                and validated_expected is not None
                and validated_expected != resolved_commit.lower()
            ):
                raise UpdateConflict(
                    "expected_commit_mismatch",
                    "Source ref no longer resolves to the reviewed commit",
                )
            if confirm_alternate_upstream:
                result["confirmation_required"] = False
            if details["update_strategy"] == "marketplace":
                return _update_plugin(
                    result,
                    details,
                    checkout,
                    apply=apply,
                    expected_commit=validated_expected,
                    expected_catalog_commit=expected_catalog_commit,
                    platform=platform,
                    canonical_upstream=canonical_upstream,
                    allow_downgrade=allow_downgrade,
                )
            checkout_state = None
            if details["update_strategy"] == "git_checkout":
                checkout_state = _checkout_state(details, source_repo, ref or "HEAD", checkout, resolved_commit)
                result["checkout"] = {
                    "branch": checkout_state["branch"],
                    "current_commit": checkout_state["current_commit"],
                }

            if not result["skill_content_changed"]:
                result["success"] = True
                result["update_status"] = "up_to_date"
                result["next_agent_action"] = "refresh_loaded_skill"
                return result

            if checkout_state is not None:
                if checkout_state["current_commit"] == resolved_commit:
                    result["automatic_update_allowed"] = False
                    result["next_agent_action"] = "resolve_checkout_content_mismatch"
                    raise UpdateConflict(
                        "checkout_content_mismatch",
                        "Git checkout skill content differs from its current source commit",
                    )
                if apply:
                    root = details["git_root"]
                    assert isinstance(root, Path)
                    _run_git("fetch", "--quiet", "--", source_repo, str(result["source_ref"]), cwd=root)
                    fetched = _run_git("rev-parse", "FETCH_HEAD", cwd=root).stdout.strip()
                    if fetched != resolved_commit:
                        raise UpdateConflict("source_changed", "Source ref changed between inspection and apply")
                    _run_git("-c", "core.hooksPath=/dev/null", "merge", "--ff-only", "FETCH_HEAD", cwd=root)
                    post_update_diff = diff_summary(current, candidate)
                    if any(post_update_diff["counts"].values()):
                        raise UpdateConflict(
                            "checkout_post_update_mismatch",
                            "Updated Git checkout does not match the validated candidate tree",
                        )
            elif apply:
                selected_backup = backup_dir or current.parent / ".engineering-workflow-backups"
                backup = _replace_copied_installation(
                    current,
                    candidate,
                    selected_backup.expanduser().resolve(),
                    str(result["previous_version"]),
                )
                result["backup_path"] = str(backup)

            result["success"] = True
            result["update_status"] = "updated" if apply else "update_available"
            result["next_agent_action"] = "refresh_loaded_skill" if apply else "update_installed_skill"
            return result
    except (UpdateConflict, OSError) as original:
        exc = (
            original
            if isinstance(original, UpdateConflict)
            else UpdateConflict("installation_io_failure", "Installation or candidate could not be read safely")
        )
        result["automatic_update_allowed"] = False
        result["next_agent_action"] = {
            "alternate_upstream_confirmation_required": "request_alternate_upstream_confirmation",
            "downgrade_refused": "request_downgrade_permission",
            "dirty_checkout": "resolve_dirty_checkout",
            "checkout_hidden_drift": "resolve_checkout_hidden_drift",
            "remote_mismatch": "resolve_source_mismatch",
            "checkout_content_mismatch": "resolve_checkout_content_mismatch",
            "expected_commit_required": "rerun_check_and_bind_expected_commit",
            "expected_commit_mismatch": "rerun_check_and_review_changed_commit",
            "native_post_update_mismatch": "recheck_native_installation_and_recover",
            "native_active_executable_cache": "reinstall_native_plugin_without_direct_cache_edits",
        }.get(exc.code, "report_update_failure")
        if result.get("native_mutation_attempted"):
            result["currentness"] = "unknown"
            result["native_readback_verified"] = False
            result["recommended_action"] = "recheck_native_installation"
            result["next_agent_action"] = "recheck_native_installation_and_recover"
        if exc.code in {"upstream_unavailable", "stable_release_unavailable"} and not result.get(
            "native_mutation_attempted"
        ):
            result["currentness"] = "unknown"
            result["recommended_action"] = "refresh_loaded_skill"
            result["next_agent_action"] = "continue_with_installed_skill"
        if result["update_status"] != "confirmation_required":
            result["update_status"] = exc.code
        if exc.backup_path is not None:
            result["backup_path"] = str(exc.backup_path)
        if exc.recovery_path is not None:
            result["recovery_path"] = str(exc.recovery_path)
        result["errors"].append({"code": exc.code, "message": str(exc)})
        return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check or safely update the exact active engineering-workflow installation."
    )
    parser.add_argument("--install-path", required=True)
    parser.add_argument("--source-repo", default=CANONICAL_UPSTREAM)
    parser.add_argument("--source-path", default=CANONICAL_SOURCE_PATH)
    parser.add_argument("--ref", help="Explicit development/tag ref; default is latest annotated stable release")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-downgrade", action="store_true")
    parser.add_argument("--backup-dir")
    parser.add_argument("--confirm-alternate-upstream", action="store_true")
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-catalog-commit")
    parser.add_argument("--platform", choices=("codex", "claude"))
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()

    result = update_installation(
        Path(args.install_path).expanduser(),
        args.source_repo,
        args.source_path,
        args.ref,
        apply=args.apply,
        allow_downgrade=args.allow_downgrade,
        backup_dir=Path(args.backup_dir) if args.backup_dir else None,
        confirm_alternate_upstream=args.confirm_alternate_upstream,
        expected_commit=args.expected_commit,
        expected_catalog_commit=args.expected_catalog_commit,
        platform=args.platform,
    )
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['update_status']}: {result.get('previous_version')} -> {result.get('candidate_version')}")
        for error in result["errors"]:
            print(f"{error['code']}: {error['message']}")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

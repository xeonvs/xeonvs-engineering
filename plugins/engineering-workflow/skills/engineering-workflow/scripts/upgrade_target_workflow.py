#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import difflib
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    CANONICAL_FILES,
    IGNORED_DIRS,
    PRIVACY_REVIEW_CONTRACT_VERSION,
    PRIVACY_REVIEW_ELIGIBLE_TYPES,
    STATE_MANIFEST_PATH,
    audit_repo,
    find_stale_completed_state,
    scan_privacy_text,
    scan_public_tree_with_fingerprints,
    validate_plan_schema,
)
from instruction_contract import check_instruction_contract
from plan_lifecycle import (
    INDEX_END,
    INDEX_START,
    LifecycleError,
    check_archive_indexes,
    closure_issues,
    planned_index_writes,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "templates"
AGENT_TEMPLATE_ROOT = SKILL_ROOT / "assets" / "agents"
CANONICAL_SOURCE_REPO = "https://github.com/xeonvs/codex-engineering-workflow"
PLAN_MARKER_START = "<!-- engineering-workflow:upgrade-plan:start -->"
PLAN_MARKER_END = "<!-- engineering-workflow:upgrade-plan:end -->"
TARGET_VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
LEGACY_PRISTINE_HASHES = {
    "AGENTS.md": {
        "c27a53d5105daae7e45ffb078d6441f19ee4285600a0fed9df776656f13bbb12",
        "6382547ce3e2d80a07aadf5dad93dba89dbdf8ab986a14674d49f802bc857037",
        "93dc99b298ff407c9e2d33b6fc1070fbdcb0d1073f4ec8726f6713409524c3a1",
        "67da11f6ca4e95c17aa057dc4d2a52b777b6a006186d001196efcdcf44476350",
        "c1f4ce431c370b1a272f56801553113ddedbc5caa2ad958468751ec8b3fa0925",
        "9ce8b3222996e2f81c66b1223ff75b1167e2a80371847107ea62806654d8d207",
    },
    CANONICAL_FILES["principles"]: {
        "cb72c47c3d9d7165eaeedfcded0d222a1d558ec90440887bf8569862b307b5aa",
        "9c54b3d5b7cddee93c9de05e75035f0750527bc0e86fe985b2cda95ede9ceb9f",
    },
    CANONICAL_FILES["pitfalls"]: {
        "87fc6d71cfef930f8198b7846628b86232e9131e966a52b49aa3f73d6b0f07c3",
        "09e5fcaca31eed41ab466df1393c49d805d2445a5e62759383551d8ed2baca5c",
    },
}


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_pristine_legacy(relative: str, text: str) -> bool:
    return _content_hash(text) in LEGACY_PRISTINE_HASHES.get(relative, set())


class MigrationConflict(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _validate_target_version(value: str) -> str:
    if not TARGET_VERSION_RE.fullmatch(value):
        raise MigrationConflict("invalid_target_version", "Target workflow version must be valid SemVer")
    return value


PrivacyFingerprint = tuple[str, str, int, str]


def _public_privacy_finding(finding: dict[str, int | str]) -> dict[str, int | str]:
    return {
        "type": finding["type"],
        "path": finding["path"],
        "line": finding["line"],
    }


def _privacy_fingerprint(finding: dict[str, int | str]) -> PrivacyFingerprint:
    return (
        str(finding["type"]),
        str(finding["path"]),
        int(finding["line"]),
        str(finding["line_sha256"]),
    )


def _privacy_review_token(
    findings: Counter[PrivacyFingerprint],
    current_workflow_version: str,
    target_version: str,
) -> str:
    canonical_findings = [list(fingerprint) for fingerprint in sorted(findings.elements())]
    payload = {
        "contract_version": PRIVACY_REVIEW_CONTRACT_VERSION,
        "current_workflow_version": current_workflow_version,
        "target_version": target_version,
        "findings": canonical_findings,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"privacy-review-v{PRIVACY_REVIEW_CONTRACT_VERSION}:{digest}"


def _evaluate_privacy_review(
    root: Path,
    current_workflow_version: str,
    target_version: str,
    approved_token: str | None,
) -> tuple[dict[str, Any], list[dict[str, int | str]], Counter[PrivacyFingerprint]]:
    detailed = scan_public_tree_with_fingerprints(root)
    eligible = [
        finding for finding in detailed if finding["type"] in PRIVACY_REVIEW_ELIGIBLE_TYPES
    ]
    hard = [
        finding for finding in detailed if finding["type"] not in PRIVACY_REVIEW_ELIGIBLE_TYPES
    ]
    candidates = [_public_privacy_finding(finding) for finding in eligible]
    empty: Counter[PrivacyFingerprint] = Counter()
    if not detailed:
        return (
            {
                "contract_version": PRIVACY_REVIEW_CONTRACT_VERSION,
                "status": "not_required",
                "review_token": None,
                "candidates": [],
                "approved_count": 0,
            },
            [],
            empty,
        )
    if hard:
        return (
            {
                "contract_version": PRIVACY_REVIEW_CONTRACT_VERSION,
                "status": "hard_block",
                "review_token": None,
                "candidates": candidates,
                "approved_count": 0,
            },
            [_public_privacy_finding(finding) for finding in detailed],
            empty,
        )

    fingerprints = Counter(_privacy_fingerprint(finding) for finding in eligible)
    expected_review = _privacy_review_token(
        fingerprints,
        current_workflow_version,
        target_version,
    )
    if approved_token is not None and hmac.compare_digest(approved_token, expected_review):
        return (
            {
                "contract_version": PRIVACY_REVIEW_CONTRACT_VERSION,
                "status": "approved",
                "review_token": None,
                "candidates": candidates,
                "approved_count": sum(fingerprints.values()),
            },
            [],
            fingerprints,
        )
    status = "token_mismatch" if approved_token is not None else "approval_required"
    return (
        {
            "contract_version": PRIVACY_REVIEW_CONTRACT_VERSION,
            "status": status,
            "review_token": expected_review,
            "candidates": candidates,
            "approved_count": 0,
        },
        candidates,
        empty,
    )


def _new_privacy_findings(
    root: Path,
    approved: Counter[PrivacyFingerprint],
) -> list[dict[str, int | str]]:
    """Return only findings not covered by the exact approved pre-apply multiset."""
    remaining = approved.copy()
    blocking: list[dict[str, int | str]] = []
    for finding in scan_public_tree_with_fingerprints(root):
        if finding["type"] not in PRIVACY_REVIEW_ELIGIBLE_TYPES:
            blocking.append(_public_privacy_finding(finding))
            continue
        fingerprint = _privacy_fingerprint(finding)
        if remaining[fingerprint] > 0:
            remaining[fingerprint] -= 1
        else:
            blocking.append(_public_privacy_finding(finding))
    return blocking


def _directory_identity(path: Path) -> tuple[int, int]:
    try:
        details = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise MigrationConflict("root_identity_changed", "Target repository identity is no longer available") from exc
    if not stat.S_ISDIR(details.st_mode):
        raise MigrationConflict("root_identity_changed", "Target repository path is no longer the audited directory")
    return details.st_dev, details.st_ino


class _SecureRoot:
    """Perform target reads and writes through a pinned, no-follow root descriptor."""

    def __init__(self, root: Path, expected_identity: tuple[int, int]):
        required = (os.open, os.mkdir, os.unlink, os.rmdir, os.stat)
        if (
            not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "O_NOFOLLOW")
            or any(function not in os.supports_dir_fd for function in required)
        ):
            raise MigrationConflict(
                "secure_filesystem_unavailable",
                "This platform cannot enforce descriptor-relative no-follow migration writes",
            )
        self.root = root
        self.expected_identity = expected_identity
        self.created_directories: list[str] = []
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            self._root_fd = os.open(root, flags)
        except OSError as exc:
            raise MigrationConflict("root_identity_changed", "Target repository root changed after audit") from exc
        try:
            opened = os.fstat(self._root_fd)
            if (opened.st_dev, opened.st_ino) != expected_identity:
                raise MigrationConflict("root_identity_changed", "Target repository root changed after audit")
            self.assert_identity()
        except Exception:
            os.close(self._root_fd)
            raise

    def __enter__(self) -> _SecureRoot:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        os.close(self._root_fd)

    def assert_identity(self) -> None:
        if _directory_identity(self.root) != self.expected_identity:
            raise MigrationConflict("root_identity_changed", "Target repository root changed after audit")
        opened = os.fstat(self._root_fd)
        if (opened.st_dev, opened.st_ino) != self.expected_identity:
            raise MigrationConflict("root_identity_changed", "Pinned target repository identity changed")

    @staticmethod
    def _parts(relative: str) -> tuple[str, ...]:
        normalized = Path(relative.replace("\\", "/"))
        if (
            normalized.is_absolute()
            or not normalized.parts
            or re.match(r"^[A-Za-z]:/", normalized.as_posix())
            or any(part in {"", ".", ".."} for part in normalized.parts)
        ):
            raise MigrationConflict("unsafe_target_path", "Migration path must be normalized and relative")
        return normalized.parts

    def _open_parent(self, relative: str, *, create: bool) -> tuple[int, str]:
        parts = self._parts(relative)
        current = os.dup(self._root_fd)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            traversed: list[str] = []
            for part in parts[:-1]:
                traversed.append(part)
                self.assert_identity()
                try:
                    following = os.open(part, flags, dir_fd=current)
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, mode=0o755, dir_fd=current)
                    created = Path(*traversed).as_posix()
                    if created not in self.created_directories:
                        self.created_directories.append(created)
                    following = os.open(part, flags, dir_fd=current)
                except OSError as exc:
                    raise MigrationConflict(
                        "unsafe_target_path",
                        "Migration parent is missing, replaced, or symbolic",
                    ) from exc
                os.close(current)
                current = following
            return current, parts[-1]
        except Exception:
            os.close(current)
            raise

    def _verify_parent(self, relative: str, parent_fd: int) -> None:
        verification, _leaf = self._open_parent(relative, create=False)
        try:
            actual = os.fstat(parent_fd)
            reopened = os.fstat(verification)
            if (actual.st_dev, actual.st_ino) != (reopened.st_dev, reopened.st_ino):
                raise MigrationConflict("target_path_changed", "Migration parent changed during apply")
        finally:
            os.close(verification)

    def exists(self, relative: str) -> bool:
        try:
            parent, leaf = self._open_parent(relative, create=False)
        except FileNotFoundError:
            return False
        try:
            try:
                details = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return False
            if stat.S_ISLNK(details.st_mode):
                raise MigrationConflict("unsafe_target_path", "Migration target is symbolic")
            return True
        finally:
            os.close(parent)

    def read_bytes(self, relative: str, *, missing_ok: bool = False) -> bytes | None:
        try:
            parent, leaf = self._open_parent(relative, create=False)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise MigrationConflict("missing_target_path", "Required migration path is missing")
        descriptor: int | None = None
        try:
            try:
                descriptor = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            except FileNotFoundError:
                if missing_ok:
                    return None
                raise MigrationConflict("missing_target_path", "Required migration path is missing")
            except OSError as exc:
                raise MigrationConflict("unsafe_target_path", "Migration target is not a safe regular file") from exc
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise MigrationConflict("unsafe_target_path", "Migration target is not a regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(parent)

    def read_text(self, relative: str, *, missing_ok: bool = False) -> str:
        data = self.read_bytes(relative, missing_ok=missing_ok)
        if data is None:
            return ""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MigrationConflict("invalid_target_text", "Migration target text is not UTF-8") from exc

    def write_bytes(self, relative: str, data: bytes) -> None:
        parent, leaf = self._open_parent(relative, create=True)
        descriptor: int | None = None
        temporary = f".{leaf}.{uuid.uuid4().hex}.tmp"
        try:
            try:
                existing = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None and not stat.S_ISREG(existing.st_mode):
                raise MigrationConflict("unsafe_target_path", "Migration target is not a regular file")
            file_mode = stat.S_IMODE(existing.st_mode) if existing is not None else 0o644
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                file_mode,
                dir_fd=parent,
            )
            offset = 0
            while offset < len(data):
                offset += os.write(descriptor, data[offset:])
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            self.assert_identity()
            self._verify_parent(relative, parent)
            try:
                os.replace(temporary, leaf, src_dir_fd=parent, dst_dir_fd=parent)
            except TypeError as exc:
                raise MigrationConflict(
                    "secure_filesystem_unavailable",
                    "Descriptor-relative atomic replacement is unavailable",
                ) from exc
            os.fsync(parent)
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=parent)
            except OSError:
                pass
            raise
        finally:
            os.close(parent)

    def write_text(self, relative: str, text: str) -> None:
        self.write_bytes(relative, text.encode("utf-8"))

    def unlink(self, relative: str) -> None:
        try:
            parent, leaf = self._open_parent(relative, create=False)
        except FileNotFoundError:
            return
        try:
            try:
                details = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return
            if not stat.S_ISREG(details.st_mode):
                raise MigrationConflict("unsafe_target_path", "Rollback target is not a regular file")
            self.assert_identity()
            self._verify_parent(relative, parent)
            os.unlink(leaf, dir_fd=parent)
        finally:
            os.close(parent)

    def rmdir(self, relative: str) -> None:
        try:
            parent, leaf = self._open_parent(relative, create=False)
        except FileNotFoundError:
            return
        try:
            try:
                details = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return
            if not stat.S_ISDIR(details.st_mode):
                raise MigrationConflict("unsafe_target_path", "Rollback directory is no longer a directory")
            self.assert_identity()
            self._verify_parent(relative, parent)
            os.rmdir(leaf, dir_fd=parent)
        finally:
            os.close(parent)


def _read(path: Path) -> str:
    if path.is_symlink():
        try:
            return os.readlink(path)
        except OSError:
            return ""
    if any(parent.is_symlink() for parent in path.parents):
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _template(name: str, replacements: dict[str, str] | None = None) -> str:
    text = (TEMPLATE_ROOT / name).read_text(encoding="utf-8")
    for key, value in (replacements or {}).items():
        text = text.replace("{{ " + key + " }}", value)
    return text


def _source_commit() -> str:
    repo_root = SKILL_ROOT.parents[1]
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value) else "unresolved"


def _manifest_version(path: Path) -> str | None:
    if not path.is_file():
        return None
    match = re.search(r"(?m)^skill_version:\s*[\"']?([^\s\"']+)", _read(path))
    return match.group(1) if match else None


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _first_symlink_component(root: Path, relative: str) -> str | None:
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return current.relative_to(root).as_posix()
    return None


def _existing_active_conflict(plans_text: str) -> str | None:
    for section in re.finditer(
        r"(?ms)^## Active Plan:\s*(?P<title>[^\n]+)\n(?P<body>.*?)(?=^## |\Z)",
        plans_text,
    ):
        title = section.group("title").strip()
        if title.startswith("Engineering Workflow Upgrade"):
            continue
        status = re.search(r"(?m)^Status:\s*(planned|in_progress|active|blocked|ready_for_closure)\s*$", section.group("body"))
        if status:
            return f"Unrelated active plan must remain owned by its current task: {title}"
    return None


def _scan_contract_conflicts(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    patterns = (
        ("compressed_plan_rule", re.compile(r"\b(?:lightweight|compact|short)\s+(?:active\s+)?plan\b", re.IGNORECASE)),
        ("compact_queue_rule", re.compile(r"\bcompact(?:\s+checked)?\s+queue(?:\s+item)?\b", re.IGNORECASE)),
        ("repo_change_without_plan", re.compile(r"\b(?:small|minor|quick)\s+changes?\b.{0,80}\b(?:without|no)\s+(?:a\s+)?plan\b", re.IGNORECASE)),
    )
    canonical_mutation_paths = {
        "PLANS.md",
        "AGENTS.md",
        *CANONICAL_FILES.values(),
        STATE_MANIFEST_PATH,
        ".codex/config.toml",
    }
    canonical_mutation_paths.update(
        f".codex/agents/{name}.toml" for name in ("utility", "explorer", "reviewer")
    )
    reported_symlinks = set()
    for relative in sorted(canonical_mutation_paths):
        symlink_component = _first_symlink_component(root, relative)
        if symlink_component and symlink_component not in reported_symlinks:
            reported_symlinks.add(symlink_component)
            findings.append(
                {
                    "type": "canonical_symlink",
                    "path": symlink_component,
                    "requires_decision": "true",
                }
            )
    agents_dir = root / ".codex" / "agents"
    if agents_dir.is_dir() and not _first_symlink_component(root, ".codex/agents"):
        for path in agents_dir.glob("*.toml"):
            if path.is_symlink():
                findings.append(
                    {
                        "type": "canonical_symlink",
                        "path": path.relative_to(root).as_posix(),
                        "requires_decision": "true",
                    }
                )
    for path in root.rglob("*"):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if (
            not path.is_file()
            or any(part in IGNORED_DIRS for part in rel_parts)
            or path.suffix.lower() not in {".md", ".txt", ".rst"}
        ):
            continue
        text = _read(path)
        rel = path.relative_to(root).as_posix()
        for kind, pattern in patterns:
            if pattern.search(text):
                finding = {"type": kind, "path": rel}
                if rel in set(CANONICAL_FILES.values()):
                    finding["requires_decision"] = "true"
                findings.append(finding)
    plans = root / "PLANS.md"
    if plans.exists():
        stale = find_stale_completed_state(_read(plans))
        findings.extend({"type": "stale_completed_state", "path": "PLANS.md", "detail": item} for item in stale)
        conflict = _existing_active_conflict(_read(plans))
        if conflict:
            findings.append({"type": "unrelated_active_plan", "path": "PLANS.md", "detail": conflict})

    config = root / ".codex" / "config.toml"
    if config.exists() and not _first_symlink_component(root, ".codex/config.toml"):
        text = _read(config)
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            findings.append({"type": "invalid_codex_config", "path": ".codex/config.toml"})
        else:
            agents = data.get("agents", {}) if isinstance(data, dict) else {}
            if isinstance(agents, dict) and agents.get("max_depth") not in {None, 1}:
                findings.append({"type": "conflicting_max_depth", "path": ".codex/config.toml"})
            if isinstance(agents, dict) and isinstance(agents.get("max_depth"), int) and agents.get("max_depth", 0) > 1:
                findings.append({"type": "recursive_delegation", "path": ".codex/config.toml"})
            if "agents" in data and isinstance(agents, dict) and agents.get("max_depth") is None and not re.search(r"(?m)^\[agents\][ \t]*(?:#.*)?$", text):
                findings.append({"type": "unsupported_inline_agents", "path": ".codex/config.toml"})
    return findings


def _topology(root: Path) -> dict[str, Any]:
    nested_agents = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("AGENTS.md")
        if path.is_file() and path != root / "AGENTS.md" and ".git" not in path.parts
    )
    agents_dir = root / ".codex" / "agents"
    agent_configs = (
        sorted(path.relative_to(root).as_posix() for path in agents_dir.glob("*.toml"))
        if agents_dir.is_dir() and not _first_symlink_component(root, ".codex/agents")
        else []
    )
    return {
        "root_agents": _present(root / "AGENTS.md"),
        "nested_agents": nested_agents,
        "plans": _present(root / "PLANS.md"),
        "backlog": _present(root / CANONICAL_FILES["backlog"]),
        "pitfalls": _present(root / CANONICAL_FILES["pitfalls"]),
        "principles": _present(root / CANONICAL_FILES["principles"]),
        "codex_config": _present(root / ".codex" / "config.toml"),
        "agent_configs": agent_configs,
        "state_manifest": _present(root / STATE_MANIFEST_PATH),
        "legacy_plan_locations": [
            value for value in ("docs/exec-plans", "docs/archive/plans") if (root / value).exists()
        ],
    }


def _proposed_changes(root: Path, include_agent_config: bool) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    plans_action = "update" if _present(root / "PLANS.md") else "create"
    changes.append({"path": "PLANS.md", "action": plans_action, "reason": "materialize full migration plan first"})
    template_map = {
        "AGENTS.md": "AGENTS.md.tmpl",
        CANONICAL_FILES["principles"]: "project_principles.md.tmpl",
        CANONICAL_FILES["backlog"]: "TASKS_BACKLOG.md.tmpl",
        CANONICAL_FILES["pitfalls"]: "AGENT_EXECUTION_PITFALLS.md.tmpl",
    }
    for relative in template_map:
        if not _present(root / relative):
            changes.append({"path": relative, "action": "create", "reason": "missing canonical shared workflow file"})
        elif _is_pristine_legacy(relative, _read(root / relative)):
            changes.append({"path": relative, "action": "update", "reason": "known pristine legacy template fingerprint"})
    index_dirs = ["docs", "docs/codex", "docs/engineering"]
    if (root / "docs/archive").exists():
        index_dirs.append("docs/archive")
    if (root / "docs/archive/plans").exists():
        index_dirs.append("docs/archive/plans")
    if (root / "docs/archive/backlog").exists():
        index_dirs.append("docs/archive/backlog")
    for relative_dir in index_dirs:
        relative = f"{relative_dir}/README.md"
        changes.append(
            {
                "path": relative,
                "action": "update" if _present(root / relative) else "create",
                "reason": "maintain navigation-only managed index",
            }
        )
    changes.append({
        "path": STATE_MANIFEST_PATH,
        "action": "update" if _present(root / STATE_MANIFEST_PATH) else "create",
        "reason": "record exact managed, shared, and protected paths",
    })
    if include_agent_config:
        changes.append({"path": ".codex/config.toml", "action": "structural_merge", "reason": "explicit runtime agent configuration request"})
        for name in ("utility", "explorer", "reviewer"):
            path = f".codex/agents/{name}.toml"
            if not _present(root / path):
                changes.append({"path": path, "action": "create", "reason": "explicit optional agent configuration request"})
    return changes


def build_migration_report(
    repo: Path,
    target_version: str,
    include_agent_config: bool = False,
    approved_privacy_review: str | None = None,
) -> dict[str, Any]:
    target_version = _validate_target_version(target_version)
    root = repo.resolve()
    if not root.is_dir():
        raise MigrationConflict("missing_repository", "Target repository does not exist")
    audit = audit_repo(root)
    conflicts = _scan_contract_conflicts(root)
    instruction_contract = audit["instruction_contract"]
    if not instruction_contract["success"]:
        existing_instruction_paths = [
            relative
            for relative in ("AGENTS.md", CANONICAL_FILES["principles"], CANONICAL_FILES["pitfalls"])
            if (root / relative).is_file()
        ]
        customized = [
            relative
            for relative in existing_instruction_paths
            if not _is_pristine_legacy(relative, _read(root / relative))
        ]
        if customized:
            finding = {
                "type": instruction_contract["status"],
                "path": ",".join(customized),
                "detail": "customized instruction owners require model-guided semantic migration",
            }
            if instruction_contract["status"] == "instruction_conflict":
                finding["requires_decision"] = "true"
            conflicts.append(finding)
    for relative_dir in ("docs", "docs/codex", "docs/engineering", "docs/archive", "docs/archive/plans", "docs/archive/backlog"):
        readme = root / relative_dir / "README.md"
        if readme.is_file():
            text = _read(readme)
            if INDEX_START not in text or INDEX_END not in text:
                conflicts.append(
                    {
                        "type": "index_migration_required",
                        "path": readme.relative_to(root).as_posix(),
                        "requires_decision": "true",
                        "detail": "existing README has no managed index marker block",
                    }
                )
    blocking_types = {
        "unrelated_active_plan",
        "invalid_codex_config",
        "instruction_migration_required",
        "instruction_conflict",
        "guard_missing",
        "index_migration_required",
    }
    if include_agent_config:
        blocking_types.update({"conflicting_max_depth", "unsupported_inline_agents"})
    questions = []
    for finding in conflicts:
        if finding["type"] == "unrelated_active_plan":
            questions.append("How should the workflow migration be linked to the unrelated active PLANS.md task?")
        elif include_agent_config and finding["type"] == "conflicting_max_depth":
            questions.append("Should the existing explicit agents.max_depth decision be preserved or changed?")
        elif include_agent_config and finding["type"] == "unsupported_inline_agents":
            questions.append("How should the existing inline or dotted agents configuration be structurally migrated?")
        elif finding["type"] == "canonical_symlink":
            questions.append(f"Should the canonical symlink at {finding['path']} be retained, retargeted, or replaced?")
        elif finding["type"] == "instruction_conflict":
            questions.append(f"Which canonical owners and routes should replace the customized instruction contract in {finding['path']}?")
        elif finding["type"] == "index_migration_required":
            questions.append(f"Where may the managed navigation block be inserted in {finding['path']} without replacing repository-owned prose?")
        elif finding.get("requires_decision") == "true":
            questions.append(f"Which source should own the contradictory planning rule in {finding['path']}?")
    proposed = _proposed_changes(root, include_agent_config)
    touched = {item["path"] for item in proposed}
    ownership = audit["ownership"]
    protected = sorted(set(ownership["protected"] + ownership["unknown"] + ownership["external_source_of_truth"]))
    current_workflow_version = (
        _manifest_version(root / STATE_MANIFEST_PATH)
        if not _first_symlink_component(root, STATE_MANIFEST_PATH)
        else None
    ) or "unknown"
    privacy_review, privacy_findings, _approved_fingerprints = _evaluate_privacy_review(
        root,
        current_workflow_version,
        target_version,
        approved_privacy_review,
    )
    return {
        "success": not any(item["type"] in blocking_types or item.get("requires_decision") == "true" for item in conflicts),
        "mode": "plan",
        "repository": ".",
        "target_version": target_version,
        "current_workflow_version": current_workflow_version,
        "detected_topology": _topology(root),
        "ownership": ownership,
        "managed_paths": ownership["managed"],
        "shared_paths": ownership["shared"],
        "protected_paths": protected,
        "historical_paths": ownership["historical"],
        "conflicts": conflicts,
        "instruction_contract": instruction_contract,
        "archive_indexes": audit["archive_indexes"],
        "privacy_findings": privacy_findings,
        "privacy_review": privacy_review,
        "proposed_changes": proposed,
        "untouched_files": sorted(path for path in protected if path not in touched),
        "required_user_questions": questions,
        "validation_plan": [
            "validate full PLANS.md schema and traceability",
            "validate instruction owners, routes, incident links, and guards",
            "validate documentation indexes and archive coverage",
            "parse workflow manifest and optional TOML",
            "verify protected files remain byte-identical",
            "scan changed public text for private paths and credential-like values",
        ],
        "rollback_plan": "Restore every pre-migration file snapshot in reverse mutation order; preserve a PLANS.md failure note if recovery is needed.",
        "include_agent_config": include_agent_config,
    }


def _migration_plan(target_version: str, include_agent_config: bool, *, done: bool = False, result: str = "Not run yet.") -> str:
    status = "ready_for_closure" if done else "active"
    checkbox = "x" if done else " "
    req_status = "done" if done else "in_progress"
    today = datetime.now(timezone.utc).date().isoformat()
    resume = "No unfinished migration queue item remains." if done else "Start with WQ-02, the first unfinished queue item."
    return f"""{PLAN_MARKER_START}
## Active Plan: Engineering Workflow Upgrade {target_version}

Status: {status}
Owner: root
Last Updated: {today}
plan_schema_version: 2

### Goal

Upgrade only the target repository workflow layer to engineering-workflow {target_version} while preserving repository-owned documentation and configuration.

### Plan Origin

direct_execution

### Requested Scope

- Materialize the full migration plan before any other target write.
- Add missing canonical workflow structure, exact ownership state, and optional agent configuration only when explicitly selected.

### Requirement Traceability

| Requirement | Complete outcome | Source | Work queue | Acceptance or validation | Status |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | Full migration plan is the first target write. | engineering-workflow contract | WQ-01 | Plan schema validates. | done |
| REQ-002 | Workflow-owned structure and manifest reach {target_version} without modifying protected docs. | migration report | WQ-02 | Protected snapshots agree and manifest parses. | {req_status} |
| REQ-003 | Runtime agent configuration follows the explicit selection. | user invocation | WQ-03 | Config is {'structurally merged' if include_agent_config else 'untouched'}. | {req_status} |

### Explicit Non-Goals

- Do not rewrite product, domain, architecture, operations, QA, release, security, or external-tracker sources.

### Constraints

- Unknown ownership remains protected; no shared file is replaced wholesale; rollback must remain bounded.

### Inputs And Sources

- Canonical source: {CANONICAL_SOURCE_REPO}
- Read-only target audit and migration report generated before apply.

### User Decisions And Answers

- Runtime agent configuration requested: {'yes' if include_agent_config else 'no'}.

### Completed Baseline State

- [x] WQ-00 — Target topology, ownership, conflicts, privacy signals, and proposed changes were audited without executing repository code.

### Current Work Queue

- [x] WQ-01 — Materialize this full plan for REQ-001 as the first write. `done`
- [{checkbox}] WQ-02 — Apply and validate canonical workflow/manifest changes for REQ-002. `{req_status}`
- [{checkbox}] WQ-03 — Preserve or structurally merge runtime configuration for REQ-003. `{req_status}`

### Locked Decisions

- Protected and unknown files remain untouched unless a later explicit decision changes ownership.

### Verification

- REQ-001: structural plan validation.
- REQ-002: manifest, ownership, privacy, and protected-file checks.
- REQ-003: TOML parse and exact configuration diff when selected.

### Latest Validation Results

- {today}: {result}

### Risks And Recovery

- Risk: partial migration. Recovery: restore captured file snapshots in reverse mutation order and record the exact failure.

### Resume Point

- {resume}

### Plan Fidelity Check

- [x] Outcomes, source URL, invocation decision, constraints, queue, validation, recovery, and resume state are preserved without compression.

### Reconciliation Check

- [{'x' if done else ' '}] Requirements, queue, validation, working tree, manifest, and statuses agree; completed text has no stale next-work state.

### Closure Gate

- [{'x' if done else ' '}] Every requirement and queue item is terminal, validation is current, and no promoted backlog or index state is stale.
- [{'x' if done else ' '}] Resume Point contains no unfinished in-scope work and compact closure can be applied atomically.

### Post-Close Delivery

- Target workflow migration only; commit, push, CI, release, and deployment are outside this operation.

### Handoff Notes

- {'Migration complete; no unfinished in-scope work remains.' if done else 'Continue only from the first unfinished queue item after reconciling target state.'}
{PLAN_MARKER_END}
"""


def _put_plan_first(existing: str, plan: str) -> str:
    if PLAN_MARKER_START in existing and PLAN_MARKER_END in existing:
        return re.sub(
            re.escape(PLAN_MARKER_START) + r".*?" + re.escape(PLAN_MARKER_END),
            plan.strip(),
            existing,
            count=1,
            flags=re.DOTALL,
        ).rstrip() + "\n"
    if not existing.strip():
        return "# Execution Plans\n\n" + plan
    lines = existing.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        return lines[0].rstrip() + "\n\n" + plan + "\n" + "".join(lines[1:]).lstrip()
    return "# Execution Plans\n\n" + plan + "\n" + existing


def _close_migration_plan(existing: str, target_version: str) -> str:
    without = re.sub(
        re.escape(PLAN_MARKER_START) + r".*?" + re.escape(PLAN_MARKER_END) + r"\s*",
        "",
        existing,
        count=1,
        flags=re.DOTALL,
    )
    without = re.sub(
        r"(?mi)^plan_schema_version:\s*`?\d+`?\s*$",
        "plan_schema_version: 2",
        without,
        count=1,
    )
    if "plan_schema_version: 2" not in without:
        lines = without.splitlines()
        if lines and lines[0].startswith("# "):
            without = lines[0] + "\n\nplan_schema_version: 2\n\n" + "\n".join(lines[1:]).lstrip()
        else:
            without = "# Execution Plans\n\nplan_schema_version: 2\n\n" + without.lstrip()
    entry = (
        f"- [x] {datetime.now(timezone.utc).date().isoformat()}: "
        f"Upgraded the repository workflow contract to {target_version} and validated instruction routing, indexes, ownership, and privacy."
    )
    recent = re.search(r"(?m)^## Recently Completed\s*$", without)
    if recent:
        insertion = recent.end()
        without = without[:insertion] + "\n\n" + entry + without[insertion:]
    else:
        without = without.rstrip() + "\n\n## Recently Completed\n\n" + entry + "\n"
    return without.rstrip() + "\n"


def _merge_codex_config(text: str) -> tuple[str, str]:
    try:
        parsed = tomllib.loads(text) if text.strip() else {}
    except tomllib.TOMLDecodeError as exc:
        raise MigrationConflict("invalid_codex_config", "Existing .codex/config.toml is invalid TOML") from exc
    agents = parsed.get("agents", {}) if isinstance(parsed, dict) else {}
    if isinstance(agents, dict) and agents.get("max_depth") not in {None, 1}:
        raise MigrationConflict("conflicting_max_depth", "Existing agents.max_depth requires an explicit decision")
    if isinstance(agents, dict) and agents.get("max_depth") == 1:
        return text, ""
    header = re.search(r"(?m)^\[agents\][ \t]*(?:#.*)?$", text)
    if "agents" in parsed and isinstance(agents, dict) and header is None:
        raise MigrationConflict("unsupported_inline_agents", "Inline or dotted agents configuration requires an explicit migration decision")
    if header:
        updated = text[: header.end()] + "\nmax_depth = 1" + text[header.end() :]
    else:
        separator = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
        updated = text + separator + "[agents]\nmax_depth = 1\n"
    diff = "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile="a/.codex/config.toml",
            tofile="b/.codex/config.toml",
            n=0,
        )
    )
    return updated, diff


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _manifest_text(
    target_version: str,
    protected_paths: list[str],
    shared_paths: list[str],
    include_agent_config: bool,
) -> str:
    applied = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "schema_version: 2",
        "skill_name: engineering-workflow",
        f"skill_version: {_yaml_quote(target_version)}",
        f"applied_at: {_yaml_quote(applied)}",
        "mode: upgrade_target_workflow",
        f"source_repo: {_yaml_quote(CANONICAL_SOURCE_REPO)}",
        f"source_ref: {_yaml_quote(target_version)}",
        f"source_commit: {_yaml_quote(_source_commit())}",
        "managed_paths:",
        f"  - {STATE_MANIFEST_PATH}",
        "shared_paths:",
    ]
    lines.extend(f"  - {_yaml_quote(path)}" for path in sorted(shared_paths))
    lines.append("protected_paths:")
    lines.extend(f"  - {_yaml_quote(path)}" for path in sorted(protected_paths))
    if not protected_paths:
        lines[-1] = "protected_paths: []"
    lines.extend(
        [
            f"runtime_agent_config_managed: {'true' if include_agent_config else 'false'}",
            "instruction_contract_version: 2",
            "planning_contract_version: 2",
            "orchestration_contract_version: 3",
        ]
    )
    return "\n".join(lines) + "\n"


def apply_migration(
    repo: Path,
    target_version: str,
    include_agent_config: bool = False,
    approved_privacy_review: str | None = None,
) -> dict[str, Any]:
    root = repo.resolve()
    expected_root_identity = _directory_identity(root)
    report = build_migration_report(
        root,
        target_version,
        include_agent_config,
        approved_privacy_review,
    )
    privacy_review, privacy_findings, approved_fingerprints = _evaluate_privacy_review(
        root,
        report["current_workflow_version"],
        target_version,
        approved_privacy_review,
    )
    report = {
        **report,
        "privacy_findings": privacy_findings,
        "privacy_review": privacy_review,
    }
    if report["required_user_questions"]:
        return {**report, "success": False, "mode": "apply", "update_status": "question_required", "mutation_log": []}
    if report["privacy_findings"]:
        return {
            **report,
            "success": False,
            "mode": "apply",
            "update_status": "privacy_review_required",
            "mutation_log": [],
            "validation_result": {"success": False, "privacy": False},
        }
    if not report["success"]:
        return {**report, "success": False, "mode": "apply", "update_status": "conflict", "mutation_log": []}

    try:
        secure_root = _SecureRoot(root, expected_root_identity)
    except MigrationConflict as exc:
        return {
            **report,
            "success": False,
            "mode": "apply",
            "update_status": exc.code,
            "errors": [{"code": exc.code, "message": str(exc)}],
            "mutation_log": [],
            "validation_result": {"success": False, "privacy": True},
        }

    with secure_root as secure:
        snapshots: dict[str, bytes | None] = {}
        mutation_log: list[str] = []
        created: list[str] = []
        changed: list[str] = []
        config_diff = ""
        final_privacy_findings: list[dict[str, int | str]] = []

        try:
            protected_snapshots = {}
            for relative in report["protected_paths"]:
                data = secure.read_bytes(relative, missing_ok=True)
                if data is not None:
                    protected_snapshots[relative] = data
        except MigrationConflict as exc:
            return {
                **report,
                "success": False,
                "mode": "apply",
                "update_status": exc.code,
                "errors": [{"code": exc.code, "message": str(exc)}],
                "mutation_log": [],
                "validation_result": {"success": False, "privacy": True},
            }

        def read(relative: str) -> str:
            return secure.read_text(relative, missing_ok=True)

        def write(relative: str, text: str) -> None:
            if relative not in snapshots:
                snapshots[relative] = secure.read_bytes(relative, missing_ok=True)
            before = snapshots[relative]
            secure.write_text(relative, text)
            mutation_log.append(relative)
            (created if before is None else changed).append(relative)

        try:
            initial_plan = _migration_plan(target_version, include_agent_config)
            write("PLANS.md", _put_plan_first(read("PLANS.md"), initial_plan))

            template_map = {
                "AGENTS.md": (
                    "AGENTS.md.tmpl",
                    {
                        "entrypoint_hint": "README.md" if secure.exists("README.md") else ".",
                        "subsystem_hint": "src/" if secure.exists("src") else ".",
                    },
                ),
                CANONICAL_FILES["principles"]: ("project_principles.md.tmpl", {}),
                CANONICAL_FILES["backlog"]: ("TASKS_BACKLOG.md.tmpl", {}),
                CANONICAL_FILES["pitfalls"]: ("AGENT_EXECUTION_PITFALLS.md.tmpl", {}),
            }
            for relative, (name, replacements) in template_map.items():
                existing = read(relative) if secure.exists(relative) else ""
                if not existing or _is_pristine_legacy(relative, existing):
                    write(relative, _template(name, replacements))

            try:
                for relative, data in planned_index_writes(root).items():
                    write(relative, data.decode("utf-8"))
            except LifecycleError as exc:
                raise MigrationConflict(exc.code, str(exc)) from exc

            instruction_result = check_instruction_contract(root)
            if not instruction_result["success"]:
                raise MigrationConflict(
                    instruction_result["status"],
                    "Generated instruction contract did not validate",
                )
            index_result = check_archive_indexes(root)
            if not index_result["success"]:
                raise MigrationConflict("index_validation_failed", "Generated documentation indexes did not validate")

            if include_agent_config:
                existing_config = read(".codex/config.toml")
                merged, config_diff = _merge_codex_config(existing_config)
                if merged != existing_config:
                    write(".codex/config.toml", merged)
                for name in ("utility", "explorer", "reviewer"):
                    relative = f".codex/agents/{name}.toml"
                    if not secure.exists(relative):
                        write(
                            relative,
                            (AGENT_TEMPLATE_ROOT / f"{name}.toml.tmpl").read_text(encoding="utf-8"),
                        )

            shared_paths = [path for path in CANONICAL_FILES.values() if secure.exists(path)]
            if include_agent_config:
                shared_paths.extend(
                    f".codex/agents/{name}.toml"
                    for name in ("utility", "explorer", "reviewer")
                    if secure.exists(f".codex/agents/{name}.toml")
                )
                if secure.exists(".codex/config.toml"):
                    shared_paths.append(".codex/config.toml")
            manifest = _manifest_text(
                target_version,
                report["protected_paths"],
                sorted(set(shared_paths)),
                include_agent_config,
            )
            if scan_privacy_text(manifest):
                raise MigrationConflict("unsafe_manifest", "Generated manifest contains private data")
            write(STATE_MANIFEST_PATH, manifest)

            plan_issues = validate_plan_schema(read("PLANS.md"), declared_external_sources=True)
            if plan_issues:
                raise MigrationConflict("invalid_generated_plan", "; ".join(plan_issues))
            if include_agent_config:
                tomllib.loads(read(".codex/config.toml"))
                for name in ("utility", "explorer", "reviewer"):
                    tomllib.loads(read(f".codex/agents/{name}.toml"))

            for relative, expected in protected_snapshots.items():
                if secure.read_bytes(relative, missing_ok=True) != expected:
                    raise MigrationConflict("protected_file_changed", "A protected file changed during migration")

            final_result = "Plan schema, ownership manifest, privacy, protected-file, and optional TOML checks passed."
            final_plan = _migration_plan(target_version, include_agent_config, done=True, result=final_result)
            write("PLANS.md", _put_plan_first(read("PLANS.md"), final_plan))
            final_plan_issues = validate_plan_schema(read("PLANS.md"), declared_external_sources=True)
            final_plan_issues.extend(closure_issues(read("PLANS.md"), require_ready=True))
            if final_plan_issues:
                raise MigrationConflict("invalid_generated_plan", "; ".join(final_plan_issues))
            write("PLANS.md", _close_migration_plan(read("PLANS.md"), target_version))

            secure.assert_identity()
            final_privacy_findings = _new_privacy_findings(root, approved_fingerprints)
            secure.assert_identity()
            if final_privacy_findings:
                raise MigrationConflict(
                    "privacy_review_required",
                    "Final pre-success privacy scan found public content requiring review",
                )
        except Exception as exc:
            code = exc.code if isinstance(exc, MigrationConflict) else type(exc).__name__
            rollback_errors: list[str] = []
            for relative, data in reversed(list(snapshots.items())):
                if relative == "PLANS.md":
                    continue
                try:
                    if data is None:
                        secure.unlink(relative)
                    else:
                        secure.write_bytes(relative, data)
                except Exception as restore_error:
                    rollback_errors.append(type(restore_error).__name__)
            for relative in reversed(secure.created_directories):
                try:
                    secure.rmdir(relative)
                except Exception as restore_error:
                    rollback_errors.append(type(restore_error).__name__)
            try:
                failure = _migration_plan(
                    target_version,
                    include_agent_config,
                    result=f"Apply failed and non-plan files were restored: {type(exc).__name__}.",
                )
                secure.write_text("PLANS.md", _put_plan_first(read("PLANS.md"), failure))
            except Exception as plan_error:
                rollback_errors.append(type(plan_error).__name__)
            rollback_failed = bool(rollback_errors)
            update_status = (
                "rollback_failed"
                if rollback_failed
                else ("privacy_review_required" if code == "privacy_review_required" else "rolled_back")
            )
            failure_privacy_review = report["privacy_review"]
            failure_privacy_findings = final_privacy_findings or report["privacy_findings"]
            if code == "privacy_review_required" and not rollback_failed:
                failure_privacy_review, failure_privacy_findings, _ignored = _evaluate_privacy_review(
                    root,
                    report["current_workflow_version"],
                    target_version,
                    None,
                )
            return {
                **report,
                "privacy_findings": failure_privacy_findings,
                "privacy_review": failure_privacy_review,
                "success": False,
                "mode": "apply",
                "update_status": update_status,
                "errors": [{"code": code, "message": str(exc)}],
                "rollback_errors": rollback_errors,
                "mutation_log": mutation_log,
                "config_diff": config_diff,
                "validation_result": {
                    "success": False,
                    "privacy": code != "privacy_review_required",
                },
            }

        return {
            **report,
            "success": True,
            "mode": "apply",
            "update_status": "updated",
            "created_files": sorted(set(created)),
            "changed_files": sorted(set(changed)),
            "mutation_log": mutation_log,
            "config_diff": config_diff,
            "validation_result": {
                "success": True,
                "plan_schema": True,
                "instruction_contract": True,
                "archive_indexes": True,
                "privacy": True,
                "toml": True,
            },
        }


def execute_prompt_upgrade(
    repo: Path,
    target_version: str,
    include_agent_config: bool = False,
    approved_privacy_review: str | None = None,
) -> dict[str, Any]:
    """Run report-first migration for an authorized natural-language target-upgrade request."""
    report = build_migration_report(
        repo,
        target_version,
        include_agent_config,
        approved_privacy_review,
    )
    if report["required_user_questions"]:
        return {
            **report,
            "success": False,
            "mode": "prompt",
            "update_status": "question_required",
            "agent_action": "ask_targeted_question",
            "question_to_ask": report["required_user_questions"][0],
            "report_reviewed": True,
            "mutation_log": [],
        }
    if report["privacy_findings"]:
        approval_required = report["privacy_review"]["status"] in {
            "approval_required",
            "token_mismatch",
        }
        return {
            **report,
            "success": False,
            "mode": "prompt",
            "update_status": "privacy_review_required",
            "agent_action": (
                "request_privacy_review_approval"
                if approval_required
                else "report_privacy_findings"
            ),
            "report_reviewed": True,
            "mutation_log": [],
        }
    reviewable_instruction_types = {"instruction_migration_required", "guard_missing"}
    non_instruction_blockers = {
        "unrelated_active_plan",
        "invalid_codex_config",
        "instruction_conflict",
        "index_migration_required",
    }
    if include_agent_config:
        non_instruction_blockers.update({"conflicting_max_depth", "unsupported_inline_agents"})
    instruction_review_only = not any(
        finding["type"] in non_instruction_blockers
        or (
            finding.get("requires_decision") == "true"
            and finding["type"] not in reviewable_instruction_types
        )
        for finding in report["conflicts"]
    )
    if (
        not report["success"]
        and not report["required_user_questions"]
        and instruction_review_only
        and report["instruction_contract"]["status"] in reviewable_instruction_types
    ):
        return {
            **report,
            "success": False,
            "mode": "prompt",
            "update_status": "instruction_migration_required",
            "agent_action": "review_instruction_migration",
            "report_reviewed": True,
            "mutation_log": [],
        }
    if not report["success"]:
        return {
            **report,
            "success": False,
            "mode": "prompt",
            "update_status": "conflict",
            "agent_action": "stop_on_conflict",
            "report_reviewed": True,
            "mutation_log": [],
        }

    applied = apply_migration(
        repo,
        target_version,
        include_agent_config,
        approved_privacy_review,
    )
    if applied.get("update_status") == "question_required":
        agent_action = "ask_targeted_question"
    elif applied.get("update_status") == "privacy_review_required":
        agent_action = (
            "request_privacy_review_approval"
            if applied.get("privacy_review", {}).get("status") in {"approval_required", "token_mismatch"}
            else "report_privacy_findings"
        )
    elif applied.get("success"):
        agent_action = "complete_and_validate"
    else:
        agent_action = "report_failure_and_recovery"
    result = {
        **applied,
        "mode": "prompt",
        "agent_action": agent_action,
        "report_reviewed": True,
    }
    if agent_action == "ask_targeted_question" and applied.get("required_user_questions"):
        result["question_to_ask"] = applied["required_user_questions"][0]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, apply, or prompt-orchestrate a conservative workflow migration.")
    parser.add_argument("--repo", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--prompt", action="store_true")
    parser.add_argument("--target-version", default="0.8.2")
    parser.add_argument("--include-agent-config", action="store_true")
    parser.add_argument(
        "--approve-privacy-review",
        help="Approve only the exact value-free privacy review token returned by a prior report.",
    )
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()

    try:
        if args.prompt:
            result = execute_prompt_upgrade(
                Path(args.repo),
                args.target_version,
                args.include_agent_config,
                args.approve_privacy_review,
            )
        elif args.apply:
            result = apply_migration(
                Path(args.repo),
                args.target_version,
                args.include_agent_config,
                args.approve_privacy_review,
            )
        else:
            result = build_migration_report(
                Path(args.repo),
                args.target_version,
                args.include_agent_config,
                args.approve_privacy_review,
            )
    except MigrationConflict as exc:
        selected_mode = "prompt" if args.prompt else ("apply" if args.apply else "plan")
        result = {"success": False, "mode": selected_mode, "errors": [{"code": exc.code, "message": str(exc)}]}
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result.get('mode')}: {'ok' if result.get('success') else 'failed'}")
        for item in result.get("proposed_changes", []):
            print(f"{item['action']}: {item['path']}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())

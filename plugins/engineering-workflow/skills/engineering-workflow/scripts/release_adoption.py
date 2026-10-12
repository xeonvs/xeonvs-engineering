#!/usr/bin/env python3
"""Release capability metadata and report-only target adoption assessment."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from common import INDEX_MARKER_END, INDEX_MARKER_START, discover_audit_files  # noqa: E402
from update_installed_skill import SEMVER_RE, _semver_key  # noqa: E402

DESCRIPTOR_PATH = Path(__file__).resolve().parents[1] / "assets" / "release_adoption.json"
STATE_PATH = "docs/codex/ENGINEERING_WORKFLOW_STATE.yaml"
CHANGE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,95}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ROUTE_RE = re.compile(r"<!--\s*ew:route\s+(.*?)\s*-->")
ATTR_RE = re.compile(r'([a-z_]+)="([^"]*)"')
WRITING_OWNER_NAMES = {"document_writing.md", "documentation_rules.md", "documentation_writing.md"}
EXCLUDED_OWNER_NAMES = {"PLANS.md", "ENGINEERING_WORKFLOW_STATE.yaml", "README.md"}
INDEX_BODY_RE = re.compile(
    re.escape(INDEX_MARKER_START.encode()) + b".*?" + re.escape(INDEX_MARKER_END.encode()), re.DOTALL
)


def load_descriptor(descriptor: dict[str, Any] | None = None) -> dict[str, Any]:
    data = descriptor if descriptor is not None else json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("skill_version"), str)
        or not SEMVER_RE.fullmatch(data["skill_version"])
        or not isinstance(data.get("changes"), list)
    ):
        raise ValueError("Invalid release adoption descriptor")
    ids: set[str] = set()
    for change in data.get("changes", []):
        if not isinstance(change, dict):
            raise ValueError("Invalid release adoption change")
        identifier = change.get("id", "")
        if (
            not isinstance(identifier, str)
            or not CHANGE_ID_RE.fullmatch(identifier)
            or identifier in ids
            or not isinstance(change.get("introduced_in"), str)
            or not SEMVER_RE.fullmatch(change["introduced_in"])
            or _semver_key(change["introduced_in"]) > _semver_key(data["skill_version"])
            or change.get("adoption_requirement") not in {"semantic_review", "runtime_only"}
            or not isinstance(change.get("affected_owner_patterns"), list)
            or any(
                not isinstance(pattern, str) or pattern.startswith("/") or ".." in pattern.split("/")
                for pattern in change["affected_owner_patterns"]
            )
        ):
            raise ValueError("Invalid release adoption change")
        ids.add(identifier)
    return data


def applicable_adoption_changes(
    current_version: str | None, descriptor: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Return every capability introduced after the target version, including skipped releases."""
    data = load_descriptor(descriptor)
    if current_version is not None and not SEMVER_RE.fullmatch(current_version):
        raise ValueError("Invalid current workflow version")
    return [
        dict(change)
        for change in data["changes"]
        if current_version is None or _semver_key(change["introduced_in"]) > _semver_key(current_version)
    ]


def _safe_bytes(root: Path, relative: str) -> bytes | None:
    """Read only regular files through no-follow root and parent descriptors."""
    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in relative
        or any(ord(char) < 32 for char in relative)
    ):
        raise ValueError("Unsafe adoption owner path")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY") or os.open not in os.supports_dir_fd:
        raise ValueError("No-follow adoption owner reads unavailable")
    descriptors: list[int] = []
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptors.append(os.open(root, directory_flags))
        for component in path.parts[:-1]:
            descriptors.append(os.open(component, directory_flags, dir_fd=descriptors[-1]))
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptors[-1])
        descriptors.append(descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Adoption owner is not a regular file")
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            return handle.read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Cannot safely read adoption owner") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _state_text(root: Path) -> str:
    return (_safe_bytes(root, STATE_PATH) or b"").decode("utf-8")


def _state_scalar(text: str, name: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(name)}:\s*[\"']?([^\s\"'#]+)", text)
    return match.group(1) if match else None


def _adopted_ids(text: str) -> set[str]:
    match = re.search(r"(?m)^adopted_change_ids:\s*\n((?:[ \t]+- [^\n]+\n?)*)", text)
    if not match:
        return set()
    return {item.strip().strip("\"'") for item in re.findall(r"(?m)^\s+- (.+)$", match.group(1))}


def _recorded_evidence(text: str, known: set[str]) -> dict[str, str]:
    headers = list(re.finditer(r"(?m)^adoption_evidence:[^\n]*$", text))
    if not headers:
        return {}
    if len(headers) != 1:
        raise ValueError("Duplicate adoption evidence mapping")
    header = headers[0]
    value = header.group().split(":", 1)[1].strip()
    if value not in {"", "{}"}:
        raise ValueError("Invalid adoption evidence mapping")
    result: dict[str, str] = {}
    for line in text[header.end() :].splitlines()[1:]:
        if line and not line[0].isspace():
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if value == "{}":
            raise ValueError("Invalid adoption evidence mapping")
        item = re.fullmatch(r"[ \t]+([a-z][a-z0-9-]{0,95}):[ \t]*(.*?)[ \t]*", line)
        if not item or item[1] not in known or item[1] in result:
            raise ValueError("Invalid or duplicate adoption evidence entry")
        digest = item[2]
        if digest.startswith(('"', "'")) and digest.endswith(digest[0]):
            digest = digest[1:-1]
        if not SHA256_RE.fullmatch(digest):
            raise ValueError("Invalid adoption evidence digest")
        result[item[1]] = digest
    return result


def recorded_adoption_evidence(text: str, descriptor: dict[str, Any] | None = None) -> dict[str, str]:
    """Parse optional state evidence without exposing malformed values in errors."""
    data = load_descriptor(descriptor)
    return _recorded_evidence(text, {change["id"] for change in data["changes"]})


def _owner_snapshots(root: Path, changes: list[dict[str, Any]], inventory: list[Path]) -> dict[str, dict]:
    if not changes:
        return {}
    instruction_owners = {"AGENTS.md"} | {
        path.relative_to(root).as_posix() for path in inventory if path.name == "AGENTS.md"
    }
    routes = []
    for owner in sorted(instruction_owners):
        agents = (_safe_bytes(root, owner) or b"").decode("utf-8")
        routes.extend(dict(ATTR_RE.findall(match[1])) for match in ROUTE_RE.finditer(agents))
    snapshots = {}
    for change in changes:
        owners = set(instruction_owners) | {
            path.relative_to(root).as_posix() for path in inventory if path.name in WRITING_OWNER_NAMES
        }
        for pattern in change["affected_owner_patterns"]:
            # Broad documentation matches identify review scope, not every mutable document.
            if not any(char in pattern for char in "*?[") and Path(pattern).name not in EXCLUDED_OWNER_NAMES:
                owners.add(pattern)
            for path in inventory:
                relative = path.relative_to(root).as_posix()
                if fnmatch.fnmatchcase(relative, pattern) and (
                    path.name == "AGENTS.md" or path.name == "project_principles.md" or path.name in WRITING_OWNER_NAMES
                ):
                    owners.add(relative)
        if "AGENTS.md" in change["affected_owner_patterns"]:
            owners.add("AGENTS.md")
        for route in routes:
            scope = f"{route.get('id', '')}|{route.get('triggers', '')}".lower()
            if not any(term in scope for term in ("document", "writing", "release adoption", "workflow-updates")):
                continue
            for owner in route.get("owners", "").split("|"):
                if owner and not owner.startswith("skill://"):
                    owner = owner.split("#", 1)[0]
                    if Path(owner).name not in EXCLUDED_OWNER_NAMES - {"README.md"}:
                        owners.add(owner)
        snapshot = {}
        for owner in sorted(owners):
            content = _safe_bytes(root, owner)
            if content is not None and Path(owner).name == "README.md":
                # A routed README can own writing rules outside its generated navigation.
                content = INDEX_BODY_RE.sub(b"", content)
            snapshot[owner] = hashlib.sha256(content).hexdigest() if content is not None else None
        snapshots[change["id"]] = snapshot
    return snapshots


def _evidence_from_snapshots(snapshots: dict[str, dict]) -> dict[str, str]:
    return {
        identifier: hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        for identifier, snapshot in snapshots.items()
    }


def adoption_evidence(
    root: Path, descriptor: dict[str, Any] | None = None, change_ids: list[str] | set[str] | None = None
) -> dict[str, str]:
    """Fingerprint reviewed local owner bytes; runtime-only changes need no evidence."""
    root = root.resolve()
    data = load_descriptor(descriptor)
    selected = set(change_ids) if change_ids is not None else {change["id"] for change in data["changes"]}
    if selected - {change["id"] for change in data["changes"]}:
        raise ValueError("Unknown adoption change IDs")
    changes = [
        change
        for change in data["changes"]
        if change["id"] in selected and change["adoption_requirement"] == "semantic_review"
    ]
    inventory, metadata = discover_audit_files(root)
    if changes and (metadata.get("truncated") or metadata.get("omission_reasons")):
        raise ValueError("Incomplete adoption owner discovery")
    return _evidence_from_snapshots(_owner_snapshots(root, changes, inventory))


def assess_target_adoption(
    root: Path,
    target_version: str,
    adopted_change_ids: list[str] | set[str] | None = None,
    *,
    descriptor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Report pending review IDs; a version stamp or keyword is never semantic adoption evidence."""
    root = root.resolve()
    if not SEMVER_RE.fullmatch(target_version):
        raise ValueError("Invalid target workflow version")
    data = load_descriptor(descriptor)
    descriptor_covers_target = _semver_key(data["skill_version"]) >= _semver_key(target_version)
    text = _state_text(root)
    current_version = _state_scalar(text, "skill_version")
    supplied = set(adopted_change_ids) if adopted_change_ids is not None else _adopted_ids(text)
    applicable = [
        dict(change)
        for change in data["changes"]
        if _semver_key(change["introduced_in"]) <= _semver_key(target_version)
    ]
    semantic = [change for change in applicable if change["adoption_requirement"] == "semantic_review"]
    known = {change["id"] for change in applicable}
    if supplied - known:
        raise ValueError("Unknown or future adoption change IDs")
    inventory, inventory_metadata = discover_audit_files(root)
    if semantic and (inventory_metadata.get("truncated") or inventory_metadata.get("omission_reasons")):
        raise ValueError("Incomplete adoption owner discovery")
    snapshots = _owner_snapshots(root, semantic, inventory)
    evidence = _evidence_from_snapshots(snapshots)
    recorded_evidence = recorded_adoption_evidence(text, data)
    if adopted_change_ids is None:
        supplied = {
            identifier
            for identifier in supplied
            if identifier not in evidence or recorded_evidence.get(identifier) == evidence[identifier]
        }
    pending = [change for change in semantic if change["id"] not in supplied]
    for change in semantic:
        owners = set()
        for pattern in change["affected_owner_patterns"]:
            owners.update(
                path.relative_to(root).as_posix()
                for path in inventory
                if fnmatch.fnmatchcase(path.relative_to(root).as_posix(), pattern)
                and not any(part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(root))
                and path.is_file()
            )
        change["existing_owners"] = sorted(
            owners | {path for path, digest in snapshots[change["id"]].items() if digest}
        )
        change["owner_evidence"] = evidence[change["id"]]
        change["owner_snapshot"] = snapshots[change["id"]]
        change["resolution"] = "resolved" if change["id"] in supplied else "pending"
    return {
        "mode": "report_only",
        "target_mutation_allowed": False,
        "current_workflow_version": current_version,
        "target_version": target_version,
        "adoption_status": "pending" if pending or not descriptor_covers_target else "resolved",
        "descriptor_version": data["skill_version"],
        "descriptor_covers_target": descriptor_covers_target,
        "pending_change_ids": [change["id"] for change in pending],
        "resolved_change_ids": sorted(supplied),
        "changes": semantic,
        "runtime_changes": [change for change in applicable if change["adoption_requirement"] == "runtime_only"],
        "semantic_review_performed": False,
        "owner_evidence": evidence,
        "owner_snapshot": snapshots,
        "owner_discovery": inventory_metadata,
    }

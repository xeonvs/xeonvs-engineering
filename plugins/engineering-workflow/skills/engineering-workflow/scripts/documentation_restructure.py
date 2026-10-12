#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import posixpath
import re
import sys
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import unquote

from common import (
    STATE_MANIFEST_PATH,
    parse_manifest_path_list,
    parse_manifest_path_scalar,
    scan_privacy_text,
    validate_plan_schema,
)
from documentation_navigation import _destination, _markdown_links, _without_code
from upgrade_target_workflow import MigrationConflict, _directory_identity, _SecureRoot

CONTRACT_VERSION = 1
TOKEN_PREFIX = "documentation-restructure-v1:"
DOCUMENT_SUFFIXES = {".md", ".markdown", ".mdx"}
INVENTORY_EXCLUDES = {".git", ".hg", ".svn"}
INVARIANT_RE = re.compile(r'<!--\s*ew:invariant\s+id="([^"]+)"\s*-->')
HEADING_RE = re.compile(r"(?m)^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
EXPLICIT_ANCHOR_RE = re.compile(r"<a\s+[^>]*(?:id|name)=[\"']([^\"']+)[\"']", re.IGNORECASE)
ACTIVE_PLAN_RE = re.compile(r"(?ms)^## Active Plan: .+?^Status:\s*active\s*$")
ROUTE_RE = re.compile(r"<!--\s*ew:route\s+(.*?)\s*-->")
ROUTE_ATTRIBUTE_RE = re.compile(r'([a-z_]+)="([^"]*)"')
STATE_FILE_LISTS = ("managed_paths", "shared_paths", "protected_paths", "documentation_indexes", "plan_archive_indexes")
ALLOWED_PROPOSAL_KEYS = {
    "schema_version",
    "scope_roots",
    "writes",
    "path_map",
    "anchor_map",
    "compatibility",
    "retired_invariants",
}
ALLOWED_COMPATIBILITY_STRATEGIES = {"updated_links", "shim", "no_incoming_links"}


class RestructureError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _normal_path(value: Any, *, allow_root: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise RestructureError("invalid_path", "Proposal paths must be non-empty normalized POSIX strings")
    if allow_root and value == ".":
        return value
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise RestructureError("invalid_path", "Proposal paths must be normalized repository-relative paths")
    return value


def _string_map(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RestructureError("invalid_proposal", f"{field} must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        key = _normal_path(key)
        if not isinstance(item, str) or not item:
            raise RestructureError("invalid_proposal", f"{field} values must be non-empty strings")
        result[key] = item
    return result


def _normalize_proposal(proposal: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(proposal, Mapping):
        raise RestructureError("invalid_proposal", "Proposal must be a JSON object")
    unknown = sorted(set(proposal) - ALLOWED_PROPOSAL_KEYS)
    missing = sorted(ALLOWED_PROPOSAL_KEYS - set(proposal))
    if unknown or missing:
        raise RestructureError(
            "invalid_proposal",
            "Proposal must contain exactly the documented restructuring fields",
        )
    if proposal["schema_version"] != CONTRACT_VERSION:
        raise RestructureError("invalid_proposal", "Unsupported proposal schema_version")

    raw_roots = proposal["scope_roots"]
    if not isinstance(raw_roots, list) or not raw_roots:
        raise RestructureError("invalid_proposal", "scope_roots must be a non-empty list")
    scope_roots = sorted({_normal_path(item, allow_root=True) for item in raw_roots})

    raw_writes = proposal["writes"]
    if not isinstance(raw_writes, dict) or not raw_writes:
        raise RestructureError("invalid_proposal", "writes must be a non-empty object")
    writes: dict[str, str | None] = {}
    for raw_path, content in raw_writes.items():
        path = _normal_path(raw_path)
        if path.casefold() == "plans.md":
            raise RestructureError("shared_state_write_forbidden", "A restructuring proposal cannot modify PLANS.md")
        if PurePosixPath(path).parts[0] in INVENTORY_EXCLUDES:
            raise RestructureError(
                "unsafe_target_path",
                "Repository metadata is outside documentation restructuring scope",
            )
        if content is not None and not isinstance(content, str):
            raise RestructureError("invalid_proposal", "writes values must be final UTF-8 text or null")
        if content is not None:
            try:
                content.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise RestructureError("invalid_proposal", "writes content must be valid UTF-8 text") from exc
        if not any(root == "." or path == root or path.startswith(root + "/") for root in scope_roots):
            raise RestructureError("path_outside_scope", "Every write must be inside an explicit scope root")
        writes[path] = content

    raw_path_map = _string_map(proposal["path_map"], "path_map")
    path_map: dict[str, str] = {}
    for old, raw_new in raw_path_map.items():
        new = _normal_path(raw_new)
        if old not in writes or new not in writes or writes[new] is None:
            raise RestructureError(
                "invalid_path_map",
                "Every mapped source and destination must be explicit writes with a resulting destination",
            )
        path_map[old] = new

    raw_anchor_map = proposal["anchor_map"]
    if not isinstance(raw_anchor_map, dict):
        raise RestructureError("invalid_proposal", "anchor_map must be an object")
    anchor_map: dict[str, str] = {}
    for old_ref, new_ref in raw_anchor_map.items():
        _split_explicit_reference(old_ref, "anchor_map")
        _split_explicit_reference(new_ref, "anchor_map")
        anchor_map[old_ref] = new_ref

    raw_compatibility = proposal["compatibility"]
    if not isinstance(raw_compatibility, dict):
        raise RestructureError("invalid_proposal", "compatibility must be an object")
    compatibility: dict[str, dict[str, str]] = {}
    for raw_old, evidence in raw_compatibility.items():
        old = _normal_path(raw_old)
        if not isinstance(evidence, dict) or set(evidence) != {"strategy", "target", "rationale"}:
            raise RestructureError("invalid_compatibility", "Compatibility evidence has an unsupported shape")
        strategy = evidence["strategy"]
        target = _normal_path(evidence["target"])
        rationale = evidence["rationale"]
        if strategy not in ALLOWED_COMPATIBILITY_STRATEGIES or not isinstance(rationale, str) or not rationale.strip():
            raise RestructureError("invalid_compatibility", "Compatibility strategy and rationale must be explicit")
        if path_map.get(old) != target:
            raise RestructureError("invalid_compatibility", "Compatibility evidence must match path_map")
        compatibility[old] = {"strategy": strategy, "target": target, "rationale": rationale}
    if set(compatibility) != set(path_map):
        raise RestructureError("invalid_compatibility", "Every path_map entry requires compatibility evidence")

    retired_invariants = _string_map(proposal["retired_invariants"], "retired_invariants")
    for invariant_id, rationale in retired_invariants.items():
        if "/" in invariant_id or not rationale.strip():
            raise RestructureError("invalid_retired_invariant", "Retired invariant IDs need an explicit rationale")

    return {
        "schema_version": CONTRACT_VERSION,
        "scope_roots": scope_roots,
        "writes": dict(sorted(writes.items())),
        "path_map": dict(sorted(path_map.items())),
        "anchor_map": dict(sorted(anchor_map.items())),
        "compatibility": dict(sorted(compatibility.items())),
        "retired_invariants": dict(sorted(retired_invariants.items())),
    }


def _split_explicit_reference(value: Any, field: str) -> tuple[str, str]:
    if not isinstance(value, str) or "#" not in value:
        raise RestructureError("invalid_proposal", f"{field} entries must use path#anchor references")
    raw_path, anchor = value.split("#", 1)
    path = _normal_path(raw_path)
    if not anchor:
        raise RestructureError("invalid_proposal", f"{field} anchors must be non-empty")
    return path, unquote(anchor)


def _is_document(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in DOCUMENT_SUFFIXES


def _inventory_documents(root: Path, secure: _SecureRoot) -> dict[str, bytes]:
    documents: dict[str, bytes] = {}
    for current, directories, files in os.walk(root, followlinks=False):
        secure.assert_identity()
        directories[:] = sorted(
            name for name in directories if name not in INVENTORY_EXCLUDES and not (Path(current) / name).is_symlink()
        )
        for name in sorted(files):
            absolute = Path(current) / name
            if absolute.is_symlink():
                if name == "AGENTS.md":
                    secure.read_bytes(absolute.relative_to(root).as_posix(), missing_ok=False)
                continue
            relative = absolute.relative_to(root).as_posix()
            if not _is_document(relative):
                continue
            data = secure.read_bytes(relative, missing_ok=False)
            assert data is not None
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RestructureError("invalid_document_text", "Documentation inputs must be UTF-8") from exc
            documents[relative] = data
    return documents


def _without_fenced_code(text: str, *, inline: bool = True) -> str:
    lines, fence, masked = text.splitlines(keepends=True), None, []
    for line in lines:
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        line_ending = "\n" if line.endswith("\n") else ""
        blank = " " * len(line.rstrip("\r\n")) + line_ending
        if fence:
            masked.append(blank)
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
        elif marker:
            fence = marker.group(1)
            masked.append(blank)
        elif line.startswith("    ") or line.startswith("\t"):
            masked.append(blank)
        else:
            masked.append(re.sub(r"(`+).*?\1", lambda match: " " * len(match.group()), line) if inline else line)
    return "".join(masked)


class _HTMLDependencies(HTMLParser):
    """Read static href/src attributes without executing or fetching HTML."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.line_offsets = [0] + [match.end() for match in re.finditer("\n", source)]
        self.links: list[tuple[str, int]] = []
        self.recognized: set[int] = set()

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line, column = self.getpos()
        position = self.line_offsets[line - 1] + column
        for attribute, value in attrs:
            if attribute in {"href", "src"} and value is not None:
                self.links.append((value, position))
                self.recognized.add(position)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def _parsed_links(text: str) -> tuple[list[tuple[int, str]], list[int]]:
    markdown_links, unsupported = _markdown_links(text)
    masked = _without_code(text)
    # Definitions are declared dependencies even when no use was recognized;
    # retaining them also avoids choosing the wrong duplicate-label destination.
    for definition in re.finditer(r"(?m)^ {0,3}\[[^\]\n]+\]:\s*(.+)$", masked):
        destination = _destination(definition.group(1))
        if destination is not None:
            markdown_links.append((destination, definition.start()))
    parser = _HTMLDependencies(masked)
    try:
        parser.feed(masked)
        parser.close()
    except (AssertionError, ValueError):
        line, column = parser.getpos()
        unsupported.append(parser.line_offsets[line - 1] + column)
    links = [(text.count("\n", 0, position) + 1, target) for target, position in markdown_links + parser.links]
    uncertain = [text.count("\n", 0, position) + 1 for position in unsupported if position not in parser.recognized]
    return links, sorted(set(uncertain))


def _iter_links(text: str) -> list[tuple[int, str]]:
    return _parsed_links(text)[0]


def _resolve_link(source: str, target: str) -> tuple[str, str] | None:
    target = target.strip()
    if not target or target.startswith("//"):
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return None
    path_part, separator, fragment = target.partition("#")
    path_part = path_part.split("?", 1)[0]
    try:
        decoded = unquote(path_part)
    except Exception:
        decoded = path_part
    if not decoded:
        resolved = source
    elif decoded.startswith("/"):
        resolved = posixpath.normpath(decoded.lstrip("/"))
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), decoded))
    if resolved in {"", ".", ".."} or resolved.startswith("../"):
        return ("", unquote(fragment) if separator else "")
    return resolved, unquote(fragment) if separator else ""


def _anchors(text: str) -> set[str]:
    text = _without_fenced_code(text, inline=False)
    anchors = set(EXPLICIT_ANCHOR_RE.findall(text))
    counts: Counter[str] = Counter()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        heading = (
            match.group(2)
            if match
            else lines[index - 1]
            if index and re.match(r"^\s{0,3}(?:=+|-+)\s*$", line)
            else None
        )
        if heading is None:
            continue
        explicit = re.search(r"\s*\{#([^}]+)\}\s*$", heading)
        if explicit:
            anchors.add(explicit.group(1))
            heading = heading[: explicit.start()]
        heading = re.sub(r"<[^>]*>", "", heading)
        heading = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", heading).lower()
        slug = "".join(
            character
            for character in heading
            if character.isspace() or character in "_-" or unicodedata.category(character)[0] in "LN"
        ).replace(" ", "-")
        duplicate = counts[slug]
        counts[slug] += 1
        anchors.add(slug + (f"-{duplicate}" if duplicate else ""))
    return anchors


def _invariants(documents: Mapping[str, str]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for path, text in documents.items():
        for invariant_id in INVARIANT_RE.findall(_without_fenced_code(text)):
            owners.setdefault(invariant_id, []).append(path)
    return owners


def _active_plan_issues(plan_text: str) -> list[dict[str, Any]]:
    reasons = set()
    for issue in validate_plan_schema(plan_text, require_fidelity_passed=True):
        if issue.startswith("missing or unsupported plan_schema_version"):
            reasons.add("plan_schema_version_invalid")
        elif issue.startswith("missing plan section:"):
            reasons.add("required_plan_section_missing")
        elif issue.startswith(("Plan Origin is empty", "invalid Plan Origin:")):
            reasons.add("plan_origin_invalid")
        elif issue.startswith("Requirement Traceability has no stable requirement IDs"):
            reasons.add("requirement_traceability_missing")
        elif issue.startswith("work queue does not cover"):
            reasons.add("work_queue_coverage_missing")
        elif issue.startswith("declared external sources are missing"):
            reasons.add("external_source_missing")
        elif issue.startswith("Inputs And Sources is empty"):
            reasons.add("inputs_missing")
        elif issue.startswith("User Decisions And Answers is empty"):
            reasons.add("user_decisions_missing")
        elif issue.startswith(("Plan Fidelity Check is empty", "Resume Point does not identify")):
            reasons.add("plan_fidelity_incomplete")
        elif issue.startswith("Current Work Queue is compressed or empty"):
            reasons.add("work_queue_incomplete")
        else:
            reasons.add("plan_schema_invalid")
    issues = [{"code": "invalid_active_plan", "path": "PLANS.md", "reason": reason} for reason in sorted(reasons)]
    if not ACTIVE_PLAN_RE.search(plan_text):
        issues.append({"code": "active_plan_required", "path": "PLANS.md"})
    return issues


def _privacy_findings(writes: Mapping[str, str | None]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path, content in writes.items():
        if content is None:
            continue
        for finding in scan_privacy_text(content):
            findings.append({"type": finding["type"], "path": path, "line": finding["line"]})
    return findings


def _instruction_dependencies(
    documents: Mapping[str, str], state_text: str | None
) -> tuple[list[dict[str, Any]], set[str], set[str], set[str]]:
    """Resolve repository-rooted route owners and explicit manifest file paths."""
    issues: list[dict[str, Any]] = []
    dependencies = {"AGENTS.md", STATE_MANIFEST_PATH}
    required_paths: set[str] = set()
    for source, text in documents.items():
        if PurePosixPath(source).name != "AGENTS.md":
            continue
        dependencies.add(source)
        text = _without_fenced_code(text)
        for marker in ROUTE_RE.finditer(text):
            line = text.count("\n", 0, marker.start()) + 1
            attributes = dict(ROUTE_ATTRIBUTE_RE.findall(marker.group(1)))
            if not {"id", "triggers", "owners", "guards"} <= attributes.keys() or not attributes["owners"].strip():
                issues.append({"code": "invalid_route", "path": source, "line": line})
                continue
            for owner in attributes["owners"].split("|"):
                owner = owner.strip()
                if owner.startswith("skill://"):
                    continue
                raw_target, _separator, raw_anchor = owner.partition("#")
                try:
                    target = _normal_path(unquote(raw_target))
                except RestructureError:
                    issues.append({"code": "unsafe_route_owner", "path": source, "line": line})
                    continue
                anchor = unquote(raw_anchor)
                dependencies.add(target)
                required_paths.add(target)
                if anchor and (target not in documents or anchor not in _anchors(documents[target])):
                    issues.append(
                        {"code": "missing_route_owner_anchor", "path": source, "line": line, "target": target}
                    )

    route_paths = set(required_paths)
    if state_text is not None:
        try:
            for key in STATE_FILE_LISTS:
                _declared, paths = parse_manifest_path_list(state_text, key)
                required_paths.update(paths)
            _declared, active_plan = parse_manifest_path_scalar(state_text, "active_plan", allow_null=True)
            if active_plan is not None:
                required_paths.add(active_plan)
        except ValueError:
            issues.append({"code": "invalid_state_paths", "path": STATE_MANIFEST_PATH})
        dependencies.update(required_paths)
    return issues, dependencies, required_paths, route_paths


def _unchanged_optional_state_paths(initial_state: str | None, final_state: str | None) -> set[str]:
    paths: set[str] = set()
    if initial_state is not None and final_state is not None:
        try:
            for key in ("managed_paths", "plan_archive_indexes"):
                _declared, initial_entries = parse_manifest_path_list(initial_state, key)
                _declared, final_entries = parse_manifest_path_list(final_state, key)
                paths.update(set(initial_entries) & set(final_entries))
        except ValueError:
            return set()
    return paths


def _validate_graph(
    initial_documents: Mapping[str, str],
    final_documents: Mapping[str, str],
    proposal: Mapping[str, Any],
    *,
    validate_transition: bool = True,
) -> tuple[list[dict[str, Any]], set[str]]:
    issues: list[dict[str, Any]] = []
    writes = proposal["writes"]
    affected = set(writes)
    old_paths = set(proposal["path_map"])
    incoming_sources: set[str] = set()
    dependencies: set[str] = set()
    parsed_documents = {source: _parsed_links(text) for source, text in final_documents.items()}

    for source, (links, unsupported_lines) in parsed_documents.items():
        for line in unsupported_lines:
            issues.append({"code": "unsupported_document_reference", "path": source, "line": line})
            dependencies.add(source)
        for line, raw_target in links:
            resolved = _resolve_link(source, raw_target)
            if resolved is None:
                continue
            target_path, _fragment = resolved
            directory_index = target_path.rstrip("/") + "/README.md"
            if target_path not in final_documents and directory_index in final_documents:
                target_path = directory_index
            if target_path in affected:
                incoming_sources.add(source)
            if target_path in old_paths and source not in affected:
                incoming_sources.add(source)

    checked_sources = {path for path in affected | incoming_sources if path in final_documents}
    incoming_old: Counter[str] = Counter()
    for source in sorted(checked_sources):
        for line, raw_target in parsed_documents[source][0]:
            resolved = _resolve_link(source, raw_target)
            if resolved is None:
                continue
            target_path, fragment = resolved
            directory_index = target_path.rstrip("/") + "/README.md"
            if target_path not in final_documents and directory_index in final_documents:
                target_path = directory_index
            if not target_path:
                issues.append({"code": "link_escape", "path": source, "line": line})
                continue
            dependencies.add(target_path)
            if target_path in old_paths and source != target_path:
                incoming_old[target_path] += 1
            if target_path in writes and writes[target_path] is not None and target_path not in final_documents:
                continue
            if target_path not in final_documents and target_path not in writes:
                # Non-document assets are validated by the secure snapshot stage.
                continue
            if target_path not in final_documents:
                issues.append({"code": "broken_local_link", "path": source, "line": line, "target": target_path})
                continue
            if fragment and fragment not in _anchors(final_documents[target_path]):
                issues.append({"code": "missing_anchor", "path": source, "line": line, "target": target_path})

    for old, target in proposal["path_map"].items():
        evidence = proposal["compatibility"][old]
        strategy = evidence["strategy"]
        if strategy in {"updated_links", "no_incoming_links"} and incoming_old[old]:
            issues.append({"code": "incoming_link_not_updated", "path": old, "count": incoming_old[old]})
        if strategy == "shim":
            old_text = final_documents.get(old)
            if old_text is None:
                issues.append({"code": "missing_compatibility_shim", "path": old})
            else:
                shim_targets = {
                    resolved[0]
                    for _line, raw in _iter_links(old_text)
                    if (resolved := _resolve_link(old, raw)) is not None
                }
                if target not in shim_targets:
                    issues.append({"code": "invalid_compatibility_shim", "path": old, "target": target})

    for old_ref, new_ref in proposal["anchor_map"].items():
        old_path, old_anchor = _split_explicit_reference(old_ref, "anchor_map")
        new_path, new_anchor = _split_explicit_reference(new_ref, "anchor_map")
        if validate_transition and (
            old_path not in initial_documents or old_anchor not in _anchors(initial_documents[old_path])
        ):
            issues.append({"code": "unknown_source_anchor", "path": old_path})
        if new_path not in final_documents or new_anchor not in _anchors(final_documents[new_path]):
            issues.append({"code": "missing_mapped_anchor", "path": new_path})

    if validate_transition:
        for old_path in proposal["writes"]:
            if old_path not in initial_documents:
                continue
            new_path = proposal["path_map"].get(old_path, old_path)
            compatibility_path = (
                old_path
                if old_path in proposal["path_map"] and proposal["compatibility"][old_path]["strategy"] == "shim"
                else new_path
            )
            old_anchors = _anchors(initial_documents[old_path])
            compatible_anchors = _anchors(final_documents.get(compatibility_path, ""))
            for old_anchor in sorted(old_anchors - compatible_anchors):
                if f"{old_path}#{old_anchor}" not in proposal["anchor_map"]:
                    issues.append({"code": "anchor_removed_without_map", "path": old_path})

    initial_invariants = _invariants(initial_documents)
    final_invariants = _invariants(final_documents)
    for invariant_id, owners in final_invariants.items():
        if len(owners) != 1:
            issues.append({"code": "duplicate_invariant", "invariant_id": invariant_id, "count": len(owners)})
    if validate_transition:
        removed = set(initial_invariants) - set(final_invariants)
        undeclared = removed - set(proposal["retired_invariants"])
        stale_retirements = set(proposal["retired_invariants"]) - removed
        for invariant_id in sorted(undeclared):
            issues.append({"code": "invariant_removed", "invariant_id": invariant_id})
        for invariant_id in sorted(stale_retirements):
            issues.append({"code": "invalid_invariant_retirement", "invariant_id": invariant_id})
    invariant_paths = {path for owners in initial_invariants.values() for path in owners}
    return issues, dependencies | incoming_sources | invariant_paths


def _snapshot_entry(data: bytes | None) -> dict[str, Any]:
    return {"state": "missing" if data is None else "file", "sha256": None if data is None else _digest(data)}


def _prepare_with_secure(
    root: Path,
    secure: _SecureRoot,
    proposal: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes | None]]:
    normalized = _normalize_proposal(proposal)
    plan_bytes = secure.read_bytes("PLANS.md", missing_ok=True)
    plan_issues: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    if plan_bytes is None:
        plan_issues.append({"code": "active_plan_required", "path": "PLANS.md"})
        plan_text = ""
    else:
        try:
            plan_text = plan_bytes.decode("utf-8")
        except UnicodeDecodeError:
            plan_text = ""
            plan_issues.append({"code": "invalid_active_plan", "path": "PLANS.md"})
        plan_issues.extend(_active_plan_issues(plan_text))

    state_bytes = secure.read_bytes(STATE_MANIFEST_PATH, missing_ok=True)
    final_state = normalized["writes"].get(STATE_MANIFEST_PATH, state_bytes)
    try:
        initial_state_text = None if state_bytes is None else state_bytes.decode("utf-8")
        state_text = final_state.decode("utf-8") if isinstance(final_state, bytes) else final_state
    except UnicodeDecodeError as exc:
        raise RestructureError("invalid_state_text", "Workflow state inputs must be UTF-8") from exc

    initial_bytes = _inventory_documents(root, secure)
    initial_documents = {path: data.decode("utf-8") for path, data in initial_bytes.items()}
    final_documents = dict(initial_documents)
    for path, content in normalized["writes"].items():
        if not _is_document(path):
            continue
        if content is None:
            final_documents.pop(path, None)
        else:
            final_documents[path] = content

    graph_issues, dependency_paths = _validate_graph(initial_documents, final_documents, normalized)
    issues.extend(graph_issues)
    link_dependency_paths = set(dependency_paths)
    instruction_issues, instruction_paths, required_paths, route_paths = _instruction_dependencies(
        final_documents, state_text
    )
    issues.extend(instruction_issues)
    dependency_paths.update(instruction_paths)

    snapshots: dict[str, bytes | None] = {"PLANS.md": plan_bytes, STATE_MANIFEST_PATH: state_bytes}
    for path in normalized["writes"]:
        try:
            snapshots[path] = secure.read_bytes(path, missing_ok=True)
        except MigrationConflict as exc:
            raise RestructureError(exc.code, str(exc)) from exc
    for path in sorted(dependency_paths):
        if path in snapshots:
            continue
        try:
            snapshots[path] = secure.read_bytes(path, missing_ok=True)
        except MigrationConflict as exc:
            issues.append({"code": exc.code, "path": path})

    for issue in issues:
        if issue.get("code") == "broken_local_link":
            continue
        target = issue.get("target")
        if isinstance(target, str) and target not in snapshots:
            snapshots[target] = secure.read_bytes(target, missing_ok=True)

    # A non-document local dependency is valid only when it is a safe regular file.
    for path in sorted(link_dependency_paths):
        if path not in final_documents and path not in normalized["writes"] and snapshots.get(path) is None:
            issues.append({"code": "broken_local_link", "path": path})
    allowed_missing_paths = {
        path
        for path in _unchanged_optional_state_paths(initial_state_text, state_text)
        - route_paths
        - set(normalized["writes"])
        if snapshots.get(path) is None
    }
    for path in sorted(required_paths - {"PLANS.md"} - allowed_missing_paths):
        if path in normalized["writes"]:
            missing = normalized["writes"][path] is None
        else:
            missing = snapshots.get(path) is None
        if missing:
            issues.append({"code": "broken_instruction_dependency", "path": path})

    privacy_findings = _privacy_findings(normalized["writes"])
    root_stat = os.fstat(secure._root_fd)
    token_payload = {
        "contract_version": CONTRACT_VERSION,
        "root_identity": [root_stat.st_dev, root_stat.st_ino],
        "root_path_sha256": _digest(os.fsencode(os.path.abspath(root))),
        "proposal": normalized,
        "inputs": {path: _snapshot_entry(data) for path, data in sorted(snapshots.items())},
        "outputs": {
            path: _snapshot_entry(None if content is None else content.encode("utf-8"))
            for path, content in normalized["writes"].items()
        },
    }
    approval_receipt = TOKEN_PREFIX + _digest(_canonical_json(token_payload))
    report = {
        "success": not issues and not privacy_findings,
        "mode": "prepare",
        "status": "prepared" if not issues and not privacy_findings else "blocked",
        "contract_version": CONTRACT_VERSION,
        "approval_token": approval_receipt,
        "plan_requirement": {"required_for": "apply", "satisfied": not plan_issues, "issues": plan_issues},
        "unchanged_missing_state_paths": sorted(allowed_missing_paths),
        "proposal_summary": {
            "scope_roots": normalized["scope_roots"],
            "write_count": sum(content is not None for content in normalized["writes"].values()),
            "delete_count": sum(content is None for content in normalized["writes"].values()),
            "move_count": len(normalized["path_map"]),
        },
        "input_snapshot": {path: _snapshot_entry(data) for path, data in sorted(snapshots.items())},
        "result_snapshot": token_payload["outputs"],
        "incoming_graph_files": sorted(
            path for path in snapshots if path not in normalized["writes"] and path != "PLANS.md"
        ),
        "issues": issues,
        "privacy_findings": privacy_findings,
    }
    return report, snapshots


def _root_path(repo_root: str | os.PathLike[str]) -> Path:
    root = Path(os.path.abspath(os.fspath(repo_root)))
    if root.is_symlink():
        raise RestructureError("unsafe_repository_root", "Repository root must not be a symlink")
    return root


def prepare_restructure(repo_root: str | os.PathLike[str], proposal: Mapping[str, Any]) -> dict[str, Any]:
    try:
        root = _root_path(repo_root)
        identity = _directory_identity(root)
        with _SecureRoot(root, identity) as secure:
            report, _snapshots = _prepare_with_secure(root, secure, proposal)
            return report
    except (RestructureError, MigrationConflict) as exc:
        return {
            "success": False,
            "mode": "prepare",
            "status": "blocked",
            "contract_version": CONTRACT_VERSION,
            "approval_token": None,
            "issues": [{"code": exc.code, "message": str(exc)}],
            "privacy_findings": [],
        }


def build_restructure_report(repo_root: str | os.PathLike[str], proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Compatibility name for the read-only prepare/report operation."""
    return prepare_restructure(repo_root, proposal)


def _post_write_validate(
    root: Path,
    secure: _SecureRoot,
    proposal: Mapping[str, Any],
    *,
    allowed_missing_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    initial_bytes = _inventory_documents(root, secure)
    documents = {path: data.decode("utf-8") for path, data in initial_bytes.items()}
    issues, _dependencies = _validate_graph(documents, documents, proposal, validate_transition=False)
    state_bytes = secure.read_bytes(STATE_MANIFEST_PATH, missing_ok=True)
    state_text = None if state_bytes is None else state_bytes.decode("utf-8")
    instruction_issues, _instruction_paths, required_paths, route_paths = _instruction_dependencies(
        documents, state_text
    )
    issues.extend(instruction_issues)
    permitted_missing = (allowed_missing_paths or set()) - route_paths
    for path in sorted(required_paths - permitted_missing):
        if secure.read_bytes(path, missing_ok=True) is None:
            issues.append({"code": "broken_instruction_dependency", "path": path})
    issues.extend(
        {"code": "privacy_finding", "path": finding["path"], "line": finding["line"], "type": finding["type"]}
        for finding in _privacy_findings(proposal["writes"])
    )
    for path, content in proposal["writes"].items():
        actual = secure.read_bytes(path, missing_ok=True)
        expected = None if content is None else content.encode("utf-8")
        if actual != expected:
            issues.append({"code": "result_mismatch", "path": path})
    return issues


def apply_restructure(
    repo_root: str | os.PathLike[str],
    proposal: Mapping[str, Any],
    approval_token: str | None,
) -> dict[str, Any]:
    mutation_log: list[str] = []
    try:
        root = _root_path(repo_root)
        identity = _directory_identity(root)
        secure_root = _SecureRoot(root, identity)
    except (RestructureError, MigrationConflict) as exc:
        return {
            "success": False,
            "mode": "apply",
            "status": "blocked",
            "issues": [{"code": exc.code, "message": str(exc)}],
            "mutation_log": [],
        }

    with secure_root as secure:
        post_issues: list[dict[str, Any]] = []
        try:
            report, snapshots = _prepare_with_secure(root, secure, proposal)
            normalized = _normalize_proposal(proposal)
        except (RestructureError, MigrationConflict) as exc:
            return {
                "success": False,
                "mode": "apply",
                "status": "blocked",
                "issues": [{"code": exc.code, "message": str(exc)}],
                "mutation_log": [],
            }
        if not report["plan_requirement"]["satisfied"]:
            return {
                **report,
                "success": False,
                "mode": "apply",
                "status": "blocked",
                "issues": report["issues"] + report["plan_requirement"]["issues"],
                "mutation_log": [],
            }
        if report["issues"]:
            return {**report, "mode": "apply", "status": "blocked", "mutation_log": []}
        if report["privacy_findings"]:
            return {**report, "mode": "apply", "status": "privacy_blocked", "mutation_log": []}
        if approval_token is None:
            return {**report, "success": False, "mode": "apply", "status": "approval_required", "mutation_log": []}
        if not hmac.compare_digest(approval_token, report["approval_token"]):
            return {**report, "success": False, "mode": "apply", "status": "stale_approval", "mutation_log": []}

        # Close the prepare/apply race before the first mutation.
        for path, expected in snapshots.items():
            if secure.read_bytes(path, missing_ok=True) != expected:
                return {
                    **report,
                    "success": False,
                    "mode": "apply",
                    "status": "input_changed",
                    "issues": [{"code": "input_changed", "path": path}],
                    "mutation_log": [],
                }

        write_snapshots = {path: snapshots[path] for path in normalized["writes"]}
        expected_outputs = {
            path: None if content is None else content.encode("utf-8") for path, content in normalized["writes"].items()
        }
        attempted_paths: list[str] = []
        try:
            for path, content in normalized["writes"].items():
                if content is None:
                    continue
                attempted_paths.append(path)
                secure.write_text(path, content)
                mutation_log.append(path)
            for path, content in normalized["writes"].items():
                if content is not None:
                    continue
                attempted_paths.append(path)
                secure.unlink(path)
                mutation_log.append(path)

            secure.assert_identity()
            for path, expected in snapshots.items():
                if path in normalized["writes"]:
                    continue
                if secure.read_bytes(path, missing_ok=True) != expected:
                    raise RestructureError("dependency_changed", "A validated dependency changed during apply")
            post_issues = _post_write_validate(
                root,
                secure,
                normalized,
                allowed_missing_paths=set(report["unchanged_missing_state_paths"]),
            )
            if post_issues:
                raise RestructureError("post_write_validation_failed", "Post-write documentation validation failed")
        except Exception as exc:
            rollback_errors: list[dict[str, str]] = []
            conflict_paths: set[str] = set()
            attempted = set(attempted_paths)
            for path in reversed(attempted_paths):
                original = write_snapshots[path]
                try:
                    current = secure.read_bytes(path, missing_ok=True)
                except Exception as restore_error:
                    rollback_errors.append({"path": path, "error": type(restore_error).__name__})
                    conflict_paths.add(path)
                    continue
                if current == original:
                    continue
                if current != expected_outputs[path]:
                    rollback_errors.append({"path": path, "error": "recovery_conflict"})
                    conflict_paths.add(path)
                    continue
                try:
                    if original is None:
                        secure.unlink(path)
                    else:
                        secure.write_bytes(path, original)
                except Exception as restore_error:
                    rollback_errors.append({"path": path, "error": type(restore_error).__name__})
                    conflict_paths.add(path)
            for path, original in write_snapshots.items():
                if path in attempted:
                    continue
                try:
                    current = secure.read_bytes(path, missing_ok=True)
                except Exception as restore_error:
                    rollback_errors.append({"path": path, "error": type(restore_error).__name__})
                    conflict_paths.add(path)
                    continue
                if current != original:
                    rollback_errors.append({"path": path, "error": "recovery_conflict"})
                    conflict_paths.add(path)
            for directory in reversed(secure.created_directories):
                try:
                    secure.rmdir(directory)
                except Exception as restore_error:
                    rollback_errors.append({"path": directory, "error": type(restore_error).__name__})
            for path in attempted_paths:
                if path in conflict_paths:
                    continue
                original = write_snapshots[path]
                try:
                    restored = secure.read_bytes(path, missing_ok=True)
                except Exception as restore_error:
                    rollback_errors.append({"path": path, "error": type(restore_error).__name__})
                    continue
                if restored != original:
                    rollback_errors.append({"path": path, "error": "rollback_bytes_mismatch"})
            rollback_failed = bool(rollback_errors)
            public_message = (
                str(exc) if isinstance(exc, (RestructureError, MigrationConflict)) else "Transaction failed"
            )
            return {
                **report,
                "success": False,
                "mode": "apply",
                "status": "rollback_failed" if rollback_failed else "rolled_back",
                "issues": [{"code": getattr(exc, "code", type(exc).__name__), "message": public_message}],
                "post_write_issues": post_issues,
                "mutation_log": mutation_log,
                "rollback_errors": rollback_errors,
                "recovery": (
                    {
                        "required": True,
                        "expected_original_snapshot": {
                            path: _snapshot_entry(data) for path, data in write_snapshots.items()
                        },
                    }
                    if rollback_failed
                    else {"required": False}
                ),
            }

        return {
            **report,
            "success": True,
            "mode": "apply",
            "status": "applied",
            "approval_token": None,
            "mutation_log": mutation_log,
            "rollback_errors": [],
            "recovery": {"required": False},
        }


def _load_proposal(value: str) -> Mapping[str, Any]:
    if value == "-":
        raw = sys.stdin.read()
    elif value.startswith("@"):
        raw = Path(value[1:]).read_text(encoding="utf-8")
    elif value.lstrip().startswith("{"):
        raw = value
    else:
        raw = Path(value).read_text(encoding="utf-8")
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise RestructureError("invalid_proposal", "Proposal JSON must be an object")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or apply an exact documentation restructuring proposal.")
    parser.add_argument("mode", choices=("prepare", "report", "apply"))
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--proposal", required=True, help="JSON text, JSON file, @file, or - for stdin")
    parser.add_argument("--approve", help="Exact token returned by prepare/report")
    args = parser.parse_args()
    try:
        proposal = _load_proposal(args.proposal)
        if args.mode in {"prepare", "report"}:
            result = prepare_restructure(args.repo_root, proposal)
        else:
            result = apply_restructure(args.repo_root, proposal, args.approve)
    except (OSError, json.JSONDecodeError, RestructureError) as exc:
        result = {
            "success": False,
            "mode": args.mode,
            "status": "blocked",
            "issues": [
                {
                    "code": getattr(exc, "code", type(exc).__name__),
                    "message": str(exc) if isinstance(exc, RestructureError) else "Proposal input could not be loaded",
                }
            ],
            "privacy_findings": [],
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only documentation inventory, scoped link checks and explicit index proposals.

Maps inspect paths, the state manifest and AGENTS route metadata, never document
bodies. Index proposals return bytes to a caller-owned transaction; they do not
write a target. Discovery inherits the audit's Git/ bounded-filesystem boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

# This entry point must not create local caches even when the caller omitted -B.
sys.dont_write_bytecode = True

from common import (  # noqa: E402 -- set the read-only import boundary first
    DOC_SUFFIXES,
    INDEX_MARKER_END,
    INDEX_MARKER_START,
    STATE_MANIFEST_PATH,
    SUPPORTED_ARCHIVE_PREFIXES,
    classify_workflow_artifact,
    discover_audit_files,
    parse_manifest_path_list,
    parse_manifest_path_scalar,
)

SCHEMA_VERSION = 1
MAX_TREE_NODES = 120
MAX_TREE_BYTES = 8192
COLLAPSED_NAMES = {
    "archive",
    "archives",
    "exec-plans",
    "vendor",
    "generated",
    "plugins",
    "node_modules",
    "build",
    "dist",
}
ROOT_DOCUMENTS = {"README.md", "AGENTS.md", "PLANS.md"}
ROUTE_RE = re.compile(r"<!--\s*ew:route\s+(.*?)\s*-->")
ATTR_RE = re.compile(r'([a-z_]+)="([^"]*)"')
LINK_START_RE = re.compile(r"(?<!\\)\[((?:\\.|[^\]\\\n])*)\]")


class NavigationError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(detail)


def _relative(value: str | Path, *, allow_dot: bool = False) -> str:
    raw = str(value)
    path = Path(raw)
    if (allow_dot and raw == ".") or not raw:
        if allow_dot and raw == ".":
            return "."
        raise NavigationError("path_unsafe", "Empty repository-relative path")
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in raw
        or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in raw)
    ):
        raise NavigationError("path_unsafe", "Expected a safe repository-relative path")
    return path.as_posix()


def _safe(root: Path, relative: str) -> bool:
    path = root / relative
    try:
        path.resolve().relative_to(root)
    except (ValueError, OSError, RuntimeError):
        return False
    while path != root:
        if path.is_symlink():
            return False
        path = path.parent
    return True


def _text(root: Path, relative: str) -> str:
    if Path(relative).name == "AGENTS.md" and recognized_source_repository(root):
        raise NavigationError("source_maintainer_routes_not_loaded", "Source AGENTS instructions remain model-owned")
    if not _safe(root, relative):
        raise NavigationError("path_unsafe", f"Symbolic or escaping documentation path: {relative}")
    try:
        with (root / relative).open(encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise NavigationError("document_unreadable", f"Cannot read UTF-8 document: {relative}") from exc


def _configuration(root: Path) -> dict:
    config = {"documentation_roots": [], "documentation_indexes": [], "managed_paths": [], "plan_archive_indexes": []}
    manifest = root / STATE_MANIFEST_PATH
    if not manifest.exists() and not manifest.is_symlink():
        return {**config, "documentation_roots_declared": False}
    text = _text(root, STATE_MANIFEST_PATH)
    try:
        roots_declared = False
        for key in config:
            declared, config[key] = parse_manifest_path_list(text, key)
            if key == "documentation_roots":
                roots_declared = declared
        _, archive = parse_manifest_path_scalar(text, "plan_archive_path")
        config["plan_archive_path"] = archive
        config["documentation_roots_declared"] = roots_declared
    except ValueError as exc:
        raise NavigationError("documentation_config_invalid", str(exc)) from exc
    return config


def recognized_source_repository(root) -> bool:
    """Recognize this donor source layout without loading maintainer policy."""
    root = Path(root).resolve()
    sentinels = ("skill/engineering-workflow/SKILL.md", "scripts/build_marketplace_package.py")
    return all(_safe(root, path) and (root / path).is_file() for path in sentinels)


def _scope(root: Path, roots, config: dict) -> list[str]:
    selected = list(roots) if roots is not None else config["documentation_roots"] or ["docs"]
    if roots is None and not config["documentation_roots"] and recognized_source_repository(root):
        selected.append("skill/engineering-workflow/references")
    result = sorted({_relative(value, allow_dot=True) for value in selected})
    for relative in result:
        if not _safe(root, relative):
            raise NavigationError("root_unsafe", "Documentation root is symbolic or escapes the repository")
        path = root / relative
        if path.exists() and not path.is_dir():
            raise NavigationError("root_invalid", "Documentation roots must be directories")
    return result


def _within(relative: str, roots: list[str]) -> bool:
    return any(prefix == "." or relative == prefix or relative.startswith(prefix + "/") for prefix in roots)


def _inventory(root: Path, inventory=None) -> tuple[list[str], dict]:
    if inventory is None:
        paths, metadata = discover_audit_files(root)
    elif isinstance(inventory, tuple) and len(inventory) == 2:
        paths, metadata = inventory
    else:
        paths = inventory
        metadata = {"mode": "provided", "truncated": False, "omission_reasons": []}
    relatives: set[str] = set()
    rejected = 0
    for value in paths:
        path = Path(value)
        try:
            if path.is_absolute():
                try:
                    path = path.relative_to(root)
                except ValueError:
                    # Normalize host aliases such as macOS /var without following
                    # the file itself (a symbolic document stays symbolic).
                    path = (Path(os.path.realpath(path.parent)) / path.name).relative_to(root)
            # Inventories represent actual filesystem names, including control
            # characters and undecodable Git bytes. Display escapes them; user
            # configuration and generated index paths remain more restrictive.
            if path.is_absolute() or ".." in path.parts or path.as_posix() == ".":
                raise NavigationError("path_unsafe", "Inventory path is outside the repository")
            relative = path.as_posix()
        except (ValueError, NavigationError):
            rejected += 1
            continue
        relatives.add(relative)
    metadata = dict(metadata)
    metadata["rejected_path_count"] = rejected
    metadata.setdefault("omission_reasons", [])
    metadata.setdefault("truncated", False)
    metadata.setdefault("mode", "provided")
    return sorted(relatives), metadata


def _routes(root: Path, relatives: list[str]) -> tuple[list[dict], list[dict]]:
    routes, warnings = [], []
    if recognized_source_repository(root):
        return routes, warnings
    for relative in relatives:
        if Path(relative).name != "AGENTS.md":
            continue
        try:
            text = _text(root, relative)
        except NavigationError as exc:
            warnings.append({"code": exc.code, "path": relative})
            continue
        for marker in ROUTE_RE.finditer(_without_code(text)):
            attrs = dict(ATTR_RE.findall(marker.group(1)))
            if not {"id", "owners", "triggers", "guards"} <= attrs.keys():
                warnings.append({"code": "route_incomplete", "path": relative})
                continue
            owners = [item.strip() for item in attrs["owners"].split("|") if item.strip()]
            routes.append(
                {
                    "id": attrs["id"],
                    "source": relative,
                    "line": text.count("\n", 0, marker.start()) + 1,
                    "owners": owners,
                    "triggers": attrs["triggers"].split("|"),
                    "guards": attrs["guards"].split("|"),
                }
            )
    return sorted(routes, key=lambda item: (item["source"], item["id"])), warnings


def build_documentation_map(root, roots=None, inventory=None) -> dict:
    """Return the full discovered graph; optional inventory is paths or (paths, metadata).

    Completeness is relative to the reported discovery boundary, never a promise
    that ignored, unreadable or pruned files were inspected. No doc bodies appear.
    """
    root = Path(root).resolve()
    config = _configuration(root)
    scopes = _scope(root, roots, config)
    relatives, discovery = _inventory(root, inventory)
    relatives = sorted(set(relatives) | {p for p in ROOT_DOCUMENTS if (root / p).exists() or (root / p).is_symlink()})
    routes, warnings = _routes(root, relatives)
    source_repository = recognized_source_repository(root)
    owner_routes: dict[str, list[str]] = {}
    external_owners: set[str] = set()
    owner_targets = {}
    for route in routes:
        for owner in route["owners"]:
            try:
                scheme = urlsplit(owner).scheme
            except ValueError:
                warnings.append({"code": "route_owner_unsafe", "path": route["source"]})
                continue
            if scheme:
                external_owners.add(owner)
                owner_targets[owner] = (owner, "")
                continue
            try:
                relative = _relative(unquote(owner.split("#", 1)[0]))
            except NavigationError:
                warnings.append({"code": "route_owner_unsafe", "path": route["source"]})
                continue
            owner_routes.setdefault(relative, []).append(route["id"])
            owner_targets[owner] = (relative, owner.partition("#")[2])
    selected = {
        p for p in relatives if Path(p).suffix.lower() in DOC_SUFFIXES and (_within(p, scopes) or p in ROOT_DOCUMENTS)
    }
    selected.update(owner_routes)
    selected.update(p for p in relatives if Path(p).name == "AGENTS.md")
    selected.update(p for p in config["documentation_indexes"] if _within(p, scopes))
    archive_path = config.get("plan_archive_path")
    if archive_path:
        selected.update(
            p for p in relatives if p.startswith(archive_path + "/") and Path(p).suffix.lower() in DOC_SUFFIXES
        )
        selected.update(p for p in config["plan_archive_indexes"] if (root / p).is_file() or (root / p).is_symlink())
    if source_repository:
        selected.add("skill/engineering-workflow/SKILL.md")
    directories = {"."}
    represented_scopes = scopes + ([archive_path] if archive_path and (root / archive_path).is_dir() else [])
    for scope in represented_scopes:
        if not (root / scope).is_dir():
            warnings.append({"code": "root_missing", "path": scope})
            continue
        parent = Path(scope)
        while parent.as_posix() != ".":
            directories.add(parent.as_posix())
            parent = parent.parent
    nodes = []
    document_counts = {".": len(selected)}
    managed = set(config["managed_paths"])
    for relative in sorted(selected):
        path = root / relative
        safe = _safe(root, relative)
        status = "present" if safe and path.is_file() else "unsafe" if not safe else "missing"
        classification = classify_workflow_artifact(root, path, managed, inspect_markers=False)
        declared_historical = bool(archive_path and relative.startswith(archive_path + "/"))
        historical = declared_historical or any(
            relative.lower().startswith(prefix) for prefix in SUPPORTED_ARCHIVE_PREFIXES
        )
        if declared_historical and classification != "managed":
            classification = "historical"
        archive_index = relative in config["plan_archive_indexes"]
        nodes.append(
            {
                "path": relative,
                "kind": "document",
                "status": status,
                "ownership": classification,
                "classification_basis": "declared_plan_archive_path"
                if declared_historical and classification == "historical"
                else "path_or_manifest",
                "routes": sorted(owner_routes.get(relative, [])),
                "historical": historical,
                "archive_index": archive_index,
                "navigation_owner": "plan_lifecycle" if archive_index else None,
                "ownership_evidence": "plan_archive_indexes" if archive_index else "path_or_manifest",
                "policy_metadata_loaded": not source_repository if path.name == "AGENTS.md" else None,
            }
        )
        parent = Path(relative).parent
        while parent.as_posix() != ".":
            parent_path = parent.as_posix()
            directories.add(parent_path)
            document_counts[parent_path] = document_counts.get(parent_path, 0) + 1
            parent = parent.parent
        if status != "present":
            warnings.append({"code": "document_" + status, "path": relative})
    for relative in sorted(directories):
        count = document_counts.get(relative, 0)
        nodes.append(
            {
                "path": relative,
                "kind": "directory",
                "document_count": count,
                "collapse_by_default": Path(relative).name.lower() in COLLAPSED_NAMES
                or relative == config.get("plan_archive_path"),
                "declared_plan_archive": relative == config.get("plan_archive_path"),
            }
        )
    for owner in sorted(external_owners):
        nodes.append({"path": owner, "kind": "external_owner", "status": "external_not_resolved"})
    edges = [
        {"source": Path(p).parent.as_posix(), "target": p, "kind": "contains"}
        for p in sorted(selected | (directories - {"."}))
    ]
    for route in routes:
        for owner in route["owners"]:
            if owner not in owner_targets:
                continue
            target, anchor = owner_targets[owner]
            edges.append(
                {
                    "source": route["source"],
                    "target": target,
                    "anchor": anchor,
                    "kind": "route_owner",
                    "route": route["id"],
                }
            )
    if (
        discovery["truncated"]
        or discovery["omission_reasons"]
        or discovery.get("pruned_directory_count")
        or discovery["rejected_path_count"]
    ):
        warnings.append({"code": "discovery_incomplete", "path": "."})
    discovery["scope_excluded_document_count"] = sum(
        Path(p).suffix.lower() in DOC_SUFFIXES and p not in selected for p in relatives
    )
    discovery["document_suffixes"] = sorted(DOC_SUFFIXES)
    return {
        "schema_version": SCHEMA_VERSION,
        "roots": scopes,
        "nodes": sorted(nodes, key=lambda n: (n["path"], n["kind"])),
        "edges": edges,
        "routes": routes,
        "source_maintainer_routes_not_loaded": source_repository,
        "discovery": discovery,
        "warnings": sorted(warnings, key=lambda w: (w["path"], w["code"])),
    }


def render_documentation_tree(
    report: dict, subtree: str | None = None, *, max_nodes=MAX_TREE_NODES, max_bytes=MAX_TREE_BYTES
) -> str:
    """Bounded paths/counts only, with focused expansion of a collapsed subtree."""
    if max_nodes < 1 or max_bytes < 256:
        raise NavigationError("output_budget_invalid", "Tree budgets require at least one node and 256 bytes")
    focus = _relative(subtree, allow_dot=True) if subtree else "."
    nodes = {n["path"]: n for n in report["nodes"] if n["kind"] != "external_owner"}
    if focus not in nodes:
        raise NavigationError("subtree_missing", "Subtree is outside the discovered documentation graph")
    children: dict[str, list[str]] = {}
    for relative in nodes:
        if relative != ".":
            children.setdefault(Path(relative).parent.as_posix(), []).append(relative)
    header = f"Documentation map v{report['schema_version']} (discovery: {report['discovery']['mode']})"
    footer = "Use --subtree PATH to expand; --format json for the complete discovered graph."
    if report["warnings"]:
        footer += f" {len(report['warnings'])} warning(s); see JSON discovery/warnings."
    lines = [header]
    reserve = len(("\n" + footer + "\n... output budget reached\n").encode("utf-8"))
    visible = 0
    stopped = False
    stack = [(focus, 0)]
    while stack:
        relative, depth = stack.pop()
        node = nodes[relative]
        label = relative if depth == 0 else Path(relative).name
        label = json.dumps(label, ensure_ascii=False)[1:-1]
        label = label.encode("utf-8", errors="backslashreplace").decode("utf-8")
        suffix = ""
        collapse = node["kind"] == "directory" and node["collapse_by_default"] and relative != focus
        if node["kind"] == "directory":
            suffix = f"/ ({node['document_count']} documents" + (", collapsed)" if collapse else ")")
        else:
            suffix = f" [{node['ownership']}; {node['status']}]"
            if node["routes"]:
                suffix += " [route owner]"
        line = "  " * min(depth, 20) + label + suffix
        if visible >= max_nodes or len(("\n".join(lines) + "\n" + line + "\n").encode("utf-8")) + reserve > max_bytes:
            stopped = True
            break
        lines.append(line)
        visible += 1
        if node["kind"] == "directory" and not collapse:
            stack.extend((p, depth + 1) for p in sorted(children.get(relative, []), reverse=True))
    if stopped:
        lines.append("... output budget reached")
    lines.append(footer)
    return "\n".join(lines) + "\n"


def _without_code(text: str, *, inline: bool = True) -> str:
    # Blank rather than remove to preserve locations for diagnostics.
    lines, fence, result = text.splitlines(keepends=True), None, []
    for line in lines:
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            result.append(re.sub(r"[^\r\n]", " ", line))
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
        elif marker:
            fence = marker.group(1)
            result.append(re.sub(r"[^\r\n]", " ", line))
        elif line.startswith("    ") or line.startswith("\t"):
            result.append(re.sub(r"[^\r\n]", " ", line))
        else:
            result.append(re.sub(r"(`+).*?\1", lambda m: " " * len(m.group()), line) if inline else line)
    return "".join(result)


def _destination(value: str) -> str | None:
    value = value.strip()
    if value.startswith("<"):
        match = re.match(r"<([^<>\n]*)>(?:\s+[\"'].*[\"'])?$", value)
        return match.group(1) if match else None
    match = re.match(r"(.*?)(?:\s+[\"'].*[\"'])?$", value)
    target = match.group(1) if match else ""
    return target if target and not re.search(r"\s", target) else None


def _markdown_links(text: str) -> tuple[list[tuple[str, int]], list[int]]:
    source = _without_code(text)
    links, unsupported = [], []
    unsupported.extend(match.start() for match in re.finditer(r"(?<!\\)\[[^\n]*?(?<!\\)\[[^\n]*?(?<!\\)\]\]\(", source))
    unsupported.extend(match.start() for match in re.finditer(r"(?i)<(?:a|img)\b[^>]*\b(?:href|src)\s*=", source))
    definitions = {}
    for match in re.finditer(r"(?m)^ {0,3}\[([^\]]+)\]:\s*(.+)$", source):
        destination = _destination(match.group(2))
        if destination is None:
            unsupported.append(match.start())
        else:
            definitions[match.group(1).strip().casefold()] = destination
    occupied = 0
    for match in LINK_START_RE.finditer(source):
        if match.start() < occupied:
            continue
        start = match.end()
        if (
            source[start : start + 1] == ":"
            and not source[source.rfind("\n", 0, match.start()) + 1 : match.start()].strip()
        ):
            continue
        if source[start : start + 1] == "(":
            end, depth, escaped, angled = start + 1, 1, False, False
            while end < len(source) and depth and source[end] != "\n":
                char = source[end]
                if not escaped:
                    if char == "<":
                        angled = True
                    elif char == ">":
                        angled = False
                    elif char == "(" and not angled:
                        depth += 1
                    elif char == ")" and not angled:
                        depth -= 1
                escaped = char == "\\" and not escaped
                end += 1
            occupied = end
            target = _destination(source[start + 1 : end - 1]) if depth == 0 else None
            if target is None:
                unsupported.append(match.start())
            else:
                links.append((re.sub(r"\\([() ])", r"\1", target), match.start()))
        else:
            reference = re.match(r"\[([^\]\n]*)\]", source[start:])
            label = (reference.group(1) or match.group(1)) if reference else match.group(1)
            key = label.strip().casefold()
            if key in definitions:
                links.append((definitions[key], match.start()))
            elif reference:
                unsupported.append(match.start())
            if reference:
                occupied = start + reference.end()
    return links, unsupported


def _anchors(text: str) -> set[str]:
    text = _without_code(text, inline=False)
    anchors = set(re.findall(r"\b(?:id|name)=[\"']([^\"']+)[\"']", text))
    counts = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?$", line)
        heading = match.group(1) if match else lines[i - 1] if i and re.match(r"^ {0,3}(?:=+|-+)\s*$", line) else None
        if heading is None:
            continue
        explicit = re.search(r"\s*\{#([^}]+)\}\s*$", heading)
        if explicit:
            anchors.add(explicit.group(1))
            heading = heading[: explicit.start()]
        heading = re.sub(r"<[^>]*>", "", heading)
        heading = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", heading).lower()
        slug = "".join(c for c in heading if c.isspace() or c in "_-" or unicodedata.category(c)[0] in "LN")
        slug = slug.replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug + (f"-{count}" if count else ""))
    return anchors


def _resolve_link(root: Path, source: str, target: str) -> tuple[str | None, str, str | None]:
    try:
        parsed = urlsplit(target)
    except ValueError:
        return None, "", "link_unsupported"
    if parsed.scheme or parsed.netloc:
        return None, "", None
    if parsed.query:
        return None, "", "link_unsupported"
    value = unquote(parsed.path)
    if "\\" in value or any(ord(c) < 32 for c in value):
        return None, "", "link_unsafe"
    path = (
        root / value.lstrip("/")
        if value.startswith("/")
        else root / Path(source).parent / value
        if value
        else root / source
    )
    try:
        # abspath normalizes parent segments but does not follow symbolic paths.
        relative = Path(os.path.abspath(path)).relative_to(root).as_posix()
    except ValueError:
        return None, "", "link_escape"
    if not _safe(root, relative):
        return relative, "", "link_unsafe"
    if not (root / relative).exists():
        return relative, "", "link_missing"
    return relative, unquote(parsed.fragment), None


def _managed_span(text: str) -> tuple[int, int] | None:
    source = _without_code(text)
    starts, ends = (
        list(re.finditer(r"(?m)^ {0,3}" + re.escape(INDEX_MARKER_START) + r"[ \t]*\r?$", source)),
        list(re.finditer(r"(?m)^ {0,3}" + re.escape(INDEX_MARKER_END) + r"[ \t]*\r?$", source)),
    )
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0].end() > ends[0].start():
        raise NavigationError("index_markers_invalid", "Expected exactly one ordered managed index block")
    return starts[0].end(), ends[0].start()


def _link_issue(root: Path, source: str, target: str, anchors_cache: dict) -> str | None:
    relative, anchor, issue = _resolve_link(root, source, target)
    if issue or relative is None or not anchor:
        return issue
    if Path(relative).suffix.lower() != ".md" or not (root / relative).is_file():
        return "anchor_unsupported"
    if recognized_source_repository(root) and Path(relative).name == "AGENTS.md":
        return "anchor_unsupported"
    try:
        if relative not in anchors_cache:
            anchors_cache[relative] = _anchors(_text(root, relative))
        return "anchor_missing" if anchor not in anchors_cache[relative] else None
    except NavigationError:
        return "anchor_unreadable"


def _check_route_owners(root: Path, report: dict, config: dict, changed: set, anchors_cache: dict) -> tuple[list, list]:
    errors, warnings = [], []
    managed = set(config["managed_paths"])
    for route in report["routes"]:
        source = route["source"]
        owned = source in managed or classify_workflow_artifact(root, root / source, managed) == "managed"
        for owner in route["owners"]:
            try:
                if urlsplit(owner).scheme:
                    continue
                target, _, anchor = owner.partition("#")
                target = _relative(unquote(target))
                destination = "/" + quote(target, safe="/._-~")
                if anchor:
                    destination += "#" + quote(unquote(anchor), safe="._-~")
                issue = _link_issue(root, source, destination, anchors_cache)
            except (NavigationError, ValueError):
                issue = "unsafe"
            if issue:
                blocking = issue not in {"link_unsupported", "anchor_unsupported"} and (source in changed or owned)
                code = "route_owner_" + (issue[5:] if issue.startswith("link_") else issue)
                (errors if blocking else warnings).append(
                    {"code": code, "path": source, "route": route["id"], "line": route["line"]}
                )
    return errors, warnings


def _index_paths(root: Path, report: dict, config: dict) -> set[str]:
    declared = (
        set(config["documentation_indexes"])
        | set(config["plan_archive_indexes"])
        | {p for p in config["managed_paths"] if Path(p).name == "README.md"}
    )
    indexes = {
        p
        for p in declared
        if _within(p, report["roots"])
        and (p not in config["plan_archive_indexes"] or (root / p).is_file() or (root / p).is_symlink())
    }
    for node in report["nodes"]:
        if node["kind"] != "document" or node["status"] != "present" or Path(node["path"]).suffix.lower() != ".md":
            continue
        if not _within(node["path"], report["roots"]):
            continue
        if report["source_maintainer_routes_not_loaded"] and Path(node["path"]).name == "AGENTS.md":
            continue
        try:
            text = _text(root, node["path"])
        except NavigationError:
            if node["path"] in declared:
                raise
            continue
        if _managed_span(text) is not None:
            indexes.add(node["path"])
    return indexes


def documentation_index_targets(root, index_path, *, files=None, extra_files=None) -> list[str]:
    """Expected relative targets shared by generic indexes and active lifecycle checks.

    ``files`` is an optional reusable inventory of absolute Paths or relative
    strings. Real child READMEs collapse their descendants; custom archive graph
    successors stay explicit without hiding unrelated documentation beside them.
    """
    root = Path(root).resolve()
    index_path = _relative(index_path)
    config = _configuration(root)
    relatives, _ = _inventory(root, files)
    available = {p for p in relatives if Path(p).suffix.lower() in DOC_SUFFIXES and _safe(root, p)}
    available.update(_relative(p) for p in extra_files or [])
    base = Path(index_path).parent.as_posix()
    candidates = {p for p in available if p != index_path and (base == "." or p.startswith(base + "/"))}
    archive_graph = config["plan_archive_indexes"]
    archive_path = config.get("plan_archive_path")
    successor = dict(zip(archive_graph[1:], archive_graph[:-1])).get(index_path)
    leaf = archive_graph[0] if archive_graph else None
    if archive_path and index_path != leaf:
        candidates = {p for p in candidates if not p.startswith(archive_path + "/")}
    if index_path in archive_graph:
        candidates.difference_update(archive_graph)
    if successor and (successor in available or (_safe(root, successor) and (root / successor).is_file())):
        candidates.add(successor)
    if index_path == leaf or base in {"docs/archive/plans", "docs/archive/backlog"}:
        return sorted(p for p in candidates if Path(p).parent.as_posix() == base)
    child_indexes = {p for p in candidates if Path(p).name == "README.md" and Path(p).parent.as_posix() != base}
    return sorted(
        p
        for p in candidates
        if p == successor
        or not any(p != child and p.startswith(Path(child).parent.as_posix() + "/") for child in child_indexes)
    )


def planned_documentation_index_writes(root, roots=None, extra_files=None) -> dict[str, bytes]:
    """Propose bytes only for marked or explicitly declared managed indexes.

    Existing unmarked prose is a conflict even on a declared path. A declared
    missing index is creatable only when the exact path is in managed_paths.
    """
    root = Path(root).resolve()
    config = _configuration(root)
    report = build_documentation_map(root, roots)
    if report["discovery"]["truncated"] or {"unreadable_directory", "unreadable_entry", "git_inventory_failed"} & set(
        report["discovery"]["omission_reasons"]
    ):
        raise NavigationError("discovery_incomplete", "Cannot regenerate managed indexes from incomplete discovery")
    indexes = _index_paths(root, report, config)
    files = {n["path"] for n in report["nodes"] if n["kind"] == "document" and n["status"] == "present"}
    for value in extra_files or []:
        relative = _relative(value)
        if not _safe(root, relative):
            raise NavigationError("path_unsafe", "Proposed documentation file has a symbolic ancestor")
        if Path(relative).suffix.lower() in DOC_SUFFIXES and _within(relative, report["roots"]):
            files.add(relative)
    files.update(indexes)
    writes = {}
    for index in sorted(indexes):
        if not _safe(root, index):
            raise NavigationError("index_unsafe", "Managed index has a symbolic or escaping path")
        if (root / index).exists():
            existing = _text(root, index)
            span = _managed_span(existing)
            if span is None:
                raise NavigationError("index_unmanaged", f"Existing declared index has no managed block: {index}")
        else:
            if index not in config["managed_paths"]:
                raise NavigationError("index_ownership_missing", "Missing index is not an exact managed_paths entry")
            existing = f"# {Path(index).parent.name or 'Documentation'}\n\n{INDEX_MARKER_START}\n{INDEX_MARKER_END}\n"
            span = _managed_span(existing)
        entries = documentation_index_targets(root, index, files=files)
        old_lines = {}
        for line in existing[span[0] : span[1]].splitlines():
            links, _ = _markdown_links(line)
            if len(links) == 1:
                target, _, error = _resolve_link(root, index, links[0][0])
                if target and (error is None or error == "link_missing"):
                    old_lines.setdefault(target, line)
        lines = []
        for target in sorted(entries):
            _relative(target)
            link = quote(os.path.relpath(root / target, root / Path(index).parent).replace(os.sep, "/"), safe="/._-~")
            label = Path(target).name.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
            lines.append(old_lines.get(target, f"- [{label}]({link})"))
        replacement = "\n" + "\n".join(lines) + "\n"
        writes[index] = (existing[: span[0]] + replacement + existing[span[1] :]).encode("utf-8")
    return writes


def check_documentation(root, roots=None, changed_paths=None) -> dict:
    """Check local Markdown links and explicit indexes; unrelated defects warn.

    Changed-file links and links inside owned index sections are blocking. Parser
    limitations always warn, so a success flag is not proof of complete parsing.
    """
    root = Path(root).resolve()
    errors, warnings, checked = [], [], []
    try:
        changed = {_relative(p) for p in changed_paths or []}
        report = build_documentation_map(root, roots)
        config = _configuration(root)
        indexes = _index_paths(root, report, config)
        proposed = planned_documentation_index_writes(root, roots)
    except NavigationError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "success": False,
            "errors": [{"code": exc.code, "path": "."}],
            "warnings": [],
            "checked_paths": [],
        }
    warnings.extend(report["warnings"])
    represented = {n["path"] for n in report["nodes"] if n["kind"] == "document"}
    for path in sorted(changed - represented):
        if Path(path).suffix.lower() == ".md":
            status = "unsafe" if not _safe(root, path) else "present" if (root / path).is_file() else "missing"
            report["nodes"].append({"kind": "document", "path": path, "status": status})
    anchors_cache = {}
    for node in report["nodes"]:
        if node["kind"] != "document" or Path(node["path"]).suffix.lower() != ".md":
            continue
        path = node["path"]
        if report["source_maintainer_routes_not_loaded"] and Path(path).name == "AGENTS.md":
            continue
        if node["status"] != "present":
            if path in changed or path in indexes:
                errors.append({"code": "document_" + node["status"], "path": path})
            continue
        checked.append(path)
        try:
            text = _text(root, path)
        except NavigationError as exc:
            (errors if path in changed or path in indexes else warnings).append({"code": exc.code, "path": path})
            continue
        span = _managed_span(text) if path in indexes else None
        links, unsupported = _markdown_links(text)
        for position in unsupported:
            warnings.append({"code": "link_unsupported", "path": path, "line": text.count("\n", 0, position) + 1})
        for target, position in links:
            issue = _link_issue(root, path, target, anchors_cache)
            if issue:
                blocking = issue not in {"link_unsupported", "anchor_unsupported"} and (
                    path in changed or bool(span and span[0] <= position < span[1])
                )
                (errors if blocking else warnings).append(
                    {"code": issue, "path": path, "line": text.count("\n", 0, position) + 1}
                )
    route_errors, route_warnings = _check_route_owners(root, report, config, changed, anchors_cache)
    errors.extend(route_errors)
    warnings.extend(route_warnings)
    for path, payload in proposed.items():
        if not (root / path).is_file() or (root / path).read_bytes() != payload:
            (errors if config["documentation_roots_declared"] or path in changed else warnings).append(
                {"code": "index_stale", "path": path}
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "success": not errors,
        "errors": sorted(errors, key=lambda i: (i["path"], i["code"])),
        "warnings": sorted(warnings, key=lambda i: (i["path"], i["code"])),
        "checked_paths": checked,
        "discovery": report["discovery"],
        "parser": "bounded_markdown_local_links",
        "source_maintainer_routes_not_loaded": report["source_maintainer_routes_not_loaded"],
    }


def _write_full_report(root: Path, target: Path, report: dict) -> dict:
    root = root.resolve()
    if not target.is_absolute() or target.is_symlink():
        raise NavigationError("report_path_unsafe", "Full report requires an absolute non-symbolic path")
    target = target.resolve()
    if target == root or root in target.parents:
        raise NavigationError("report_path_unsafe", "Full report must be outside the repository")
    parent = target.parent
    if not parent.is_dir() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise NavigationError("report_path_unprotected", "Full report parent must be a private existing directory")
    payload = (json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")
    name = ""
    try:
        with tempfile.NamedTemporaryFile(prefix=".documentation-map-", dir=parent, delete=False) as handle:
            name = handle.name
            os.chmod(name, 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
    finally:
        if name:
            Path(name).unlink(missing_ok=True)
    return {"path": str(target), "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("map", "check"))
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--root", action="append", dest="roots")
    parser.add_argument("--subtree")
    parser.add_argument("--format", choices=("tree", "json"), default="tree")
    parser.add_argument("--changed-path", action="append", dest="changed_paths")
    parser.add_argument("--full-report", type=Path)
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        parser.error("Repository root must be an existing directory")
    if args.command == "check" and args.subtree:
        parser.error("--subtree applies to map only; use --root for check scope")
    try:
        report = (
            build_documentation_map(root, args.roots)
            if args.command == "map"
            else check_documentation(root, args.roots, args.changed_paths)
        )
        full_report = _write_full_report(root, args.full_report, report) if args.full_report else None
        if full_report and args.format == "json":
            report = {**report, "full_report": full_report}
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
        elif args.command == "map":
            print(render_documentation_tree(report, args.subtree), end="")
        else:
            print(
                f"Documentation check: {'ok' if report['success'] else 'failed'}; {len(report['errors'])} error(s), {len(report['warnings'])} warning(s)."
            )
            for item in report["errors"][:20]:
                print(f"  {item['code']}: {item['path']}")
        if full_report and args.format != "json":
            print(json.dumps({"full_report": full_report}, sort_keys=True))
        return 0 if args.command == "map" or report["success"] else 1
    except (NavigationError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

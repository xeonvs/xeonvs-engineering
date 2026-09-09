#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any

from common import CANONICAL_FILES, IGNORED_DIRS

INVARIANT_RE = re.compile(r'<!--\s*ew:invariant\s+id="(?P<id>[a-z0-9][a-z0-9._-]*)"\s*-->')
ROUTE_RE = re.compile(r"<!--\s*ew:route\s+(?P<attrs>.*?)\s*-->")
ATTR_RE = re.compile(r'(?P<key>[a-z_]+)="(?P<value>[^"]*)"')
INCIDENT_RE = re.compile(r"(?m)^###\s+(?P<id>INC-\d+)\b(?P<title>[^\n]*)$")
CAUSE_CODES = {"missing_rule", "conflicting_rule", "unreachable_rule", "unguarded_rule"}
INCIDENT_STATUSES = {"active", "guarded", "retired"}
GUARD_KINDS = {"test", "lint", "harness", "release_gate", "manual_review"}
REQUIRED_CONTRACT_VERSION = 3
REQUIRED_INVARIANTS = {
    "workflow.efficient-execution",
    "workflow.evidence-driven-completion",
    "workflow.completion-driven-wait",
    "workflow.review-before-commit",
}
REQUIRED_ROUTES = {
    "repository-change": CANONICAL_FILES["principles"],
    "long-running-execution": CANONICAL_FILES["principles"],
}
REQUIRED_INCIDENT_FIELDS = {
    "Symptom",
    "Cause",
    "Invariant",
    "Owner",
    "Route",
    "Guard",
    "Evidence",
    "Status",
    "Retirement",
}
CONFLICT_PATTERNS = (
    re.compile(r"\bcompact(?:\s+checked)?\s+queue(?:\s+item)?\b", re.IGNORECASE),
    re.compile(r"\b(?:lightweight|compact|short)\s+(?:active\s+)?plan\b", re.IGNORECASE),
    re.compile(
        r"\b(?:small|minor|quick)\s+changes?\b.{0,100}\b(?:without|no)\s+(?:a\s+)?(?:full\s+)?plan\b",
        re.IGNORECASE | re.DOTALL,
    ),
)


def _read(path: Path) -> str:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _candidate_docs(root: Path) -> list[Path]:
    candidates: set[Path] = set()
    agents = root / CANONICAL_FILES["agents"]
    if agents.is_file() and not agents.is_symlink():
        candidates.add(agents)
    docs = root / "docs"
    if docs.is_dir() and not docs.is_symlink():
        for path in docs.rglob("*"):
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in {".md", ".rst", ".txt"}:
                continue
            rel = path.relative_to(root)
            if any(part in IGNORED_DIRS for part in rel.parts):
                continue
            if rel.parts[:2] in {("docs", "archive"), ("docs", "exec-plans")}:
                continue
            candidates.add(path)
    return sorted(candidates, key=lambda item: item.relative_to(root).as_posix())


def _slug(heading: str) -> str:
    value = re.sub(r"[^a-z0-9\s-]", "", heading.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


def _normalized_body(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse_invariants(root: Path, docs: list[Path]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    invariants: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    by_id: dict[str, list[dict[str, str]]] = {}
    for path in docs:
        text = _read(path)
        matches = list(INVARIANT_RE.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[match.end() : end].strip()
            heading_match = re.search(r"(?m)^#{2,6}\s+(?P<heading>[^\n]+)$", block)
            heading = heading_match.group("heading").strip() if heading_match else ""
            relative = path.relative_to(root).as_posix()
            item = {
                "id": match.group("id"),
                "owner": relative,
                "anchor": _slug(heading),
                "body": _normalized_body(block),
            }
            invariants.append(item)
            by_id.setdefault(item["id"], []).append(item)
            if relative == CANONICAL_FILES["agents"]:
                errors.append({"code": "router_defines_invariant", "path": relative, "detail": item["id"]})
            if relative == CANONICAL_FILES["pitfalls"]:
                errors.append({"code": "incident_catalog_defines_invariant", "path": relative, "detail": item["id"]})
            if not heading:
                errors.append({"code": "invariant_heading_missing", "path": relative, "detail": item["id"]})
    for invariant_id, items in sorted(by_id.items()):
        if len(items) != 1:
            errors.append(
                {
                    "code": "duplicate_invariant_owner",
                    "path": ",".join(item["owner"] for item in items),
                    "detail": invariant_id,
                }
            )
    return invariants, errors


def _parse_routes(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    routes: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    path = root / CANONICAL_FILES["agents"]
    if not path.exists():
        return routes, errors
    if path.is_symlink():
        return routes, [{"code": "instruction_path_unsafe", "path": "AGENTS.md", "detail": "symbolic file"}]
    text = _read(path)
    seen: set[str] = set()
    for marker in ROUTE_RE.finditer(text):
        attrs = {match.group("key"): match.group("value").strip() for match in ATTR_RE.finditer(marker.group("attrs"))}
        missing = sorted({"id", "triggers", "owners", "guards"} - attrs.keys())
        if missing:
            errors.append({"code": "route_fields_missing", "path": "AGENTS.md", "detail": ",".join(missing)})
            continue
        route_id = attrs["id"]
        if route_id in seen:
            errors.append({"code": "duplicate_route", "path": "AGENTS.md", "detail": route_id})
        seen.add(route_id)
        owners = [item.strip() for item in attrs["owners"].split("|") if item.strip()]
        guards = [item.strip() for item in attrs["guards"].split("|") if item.strip()]
        triggers = [item.strip() for item in attrs["triggers"].split("|") if item.strip()]
        route = {"id": route_id, "owners": owners, "guards": guards, "triggers": triggers}
        routes.append(route)
        for owner in owners:
            owner_path = owner.split("#", 1)[0]
            if owner_path.startswith("skill://"):
                continue
            if not (root / owner_path).is_file():
                errors.append(
                    {"code": "route_owner_missing", "path": "AGENTS.md", "detail": f"{route_id}:{owner_path}"}
                )
        for guard in guards:
            if not _valid_guard(guard):
                errors.append({"code": "guard_missing", "path": "AGENTS.md", "detail": f"{route_id}:{guard}"})
    return routes, errors


def _valid_guard(value: str) -> bool:
    kind, separator, identifier = value.partition(":")
    return bool(separator and kind in GUARD_KINDS and identifier.strip())


def _parse_incidents(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    path = root / CANONICAL_FILES["pitfalls"]
    if not path.exists():
        return [], []
    if path.is_symlink():
        return [], [{"code": "instruction_path_unsafe", "path": CANONICAL_FILES["pitfalls"], "detail": "symbolic file"}]
    text = _read(path)
    errors: list[dict[str, str]] = []
    incidents: list[dict[str, str]] = []
    if not re.search(r"(?m)^incident_schema_version:\s*1\s*$", text):
        errors.append(
            {"code": "incident_schema_missing", "path": CANONICAL_FILES["pitfalls"], "detail": "expected version 1"}
        )
    matches = list(INCIDENT_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        fields: dict[str, str] = {"id": match.group("id")}
        for field_match in re.finditer(r"(?m)^-\s+(?P<key>[A-Za-z ]+):\s*(?P<value>.*)$", body):
            fields[field_match.group("key").strip()] = field_match.group("value").strip().strip("`")
        missing = sorted(REQUIRED_INCIDENT_FIELDS - fields.keys())
        if missing:
            errors.append(
                {
                    "code": "incident_fields_missing",
                    "path": CANONICAL_FILES["pitfalls"],
                    "detail": f"{fields['id']}:{','.join(missing)}",
                }
            )
        if fields.get("Cause") and fields["Cause"] not in CAUSE_CODES:
            errors.append(
                {"code": "invalid_incident_cause", "path": CANONICAL_FILES["pitfalls"], "detail": fields["Cause"]}
            )
        if fields.get("Status") and fields["Status"] not in INCIDENT_STATUSES:
            errors.append(
                {"code": "invalid_incident_status", "path": CANONICAL_FILES["pitfalls"], "detail": fields["Status"]}
            )
        if fields.get("Guard") and not _valid_guard(fields["Guard"]):
            errors.append(
                {
                    "code": "guard_missing",
                    "path": CANONICAL_FILES["pitfalls"],
                    "detail": f"{fields['id']}:{fields['Guard']}",
                }
            )
        incidents.append(fields)
    if re.search(r"(?mi)^-\s*(?:Better default|Rule|Required action):", text):
        errors.append(
            {"code": "imperative_incident_field", "path": CANONICAL_FILES["pitfalls"], "detail": "normative field"}
        )
    for line in text.splitlines():
        if re.match(r"(?i)^-\s*Evidence:", line):
            continue
        if re.match(r"(?i)^-\s*(?:always|never|must|do not|don't|required to|should)\b", line.strip()):
            errors.append(
                {
                    "code": "imperative_incident_body",
                    "path": CANONICAL_FILES["pitfalls"],
                    "detail": "imperative list item",
                }
            )
            break
    return incidents, errors


def _duplicate_findings(invariants: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for index, left in enumerate(invariants):
        for right in invariants[index + 1 :]:
            if len(left["body"]) < 40 or len(right["body"]) < 40:
                continue
            detail = f"{left['id']}:{right['id']}"
            if left["body"] == right["body"]:
                errors.append(
                    {"code": "duplicate_invariant_body", "path": f"{left['owner']},{right['owner']}", "detail": detail}
                )
            elif difflib.SequenceMatcher(None, left["body"], right["body"]).ratio() >= 0.88:
                warnings.append(
                    {"code": "similar_invariant_body", "path": f"{left['owner']},{right['owner']}", "detail": detail}
                )
    return errors, warnings


def _planning_conflicts(root: Path, docs: list[Path]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in docs:
        text = _read(path)
        for pattern in CONFLICT_PATTERNS:
            if pattern.search(text):
                findings.append(
                    {
                        "code": "conflicting_planning_rule",
                        "path": path.relative_to(root).as_posix(),
                        "detail": "compact or plan-bypass policy",
                    }
                )
                break
    return findings


def check_instruction_contract(root: Path) -> dict[str, Any]:
    root = root.resolve()
    docs = _candidate_docs(root)
    agents = root / CANONICAL_FILES["agents"]
    pitfalls = root / CANONICAL_FILES["pitfalls"]
    has_surface = agents.exists() or pitfalls.exists() or (root / CANONICAL_FILES["principles"]).exists()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    invariants, invariant_errors = _parse_invariants(root, docs)
    routes, route_errors = _parse_routes(root)
    incidents, incident_errors = _parse_incidents(root)
    errors.extend(invariant_errors)
    errors.extend(route_errors)
    errors.extend(incident_errors)
    duplicate_errors, duplicate_warnings = _duplicate_findings(invariants)
    errors.extend(duplicate_errors)
    warnings.extend(duplicate_warnings)
    errors.extend(_planning_conflicts(root, docs))

    agents_text = _read(agents) if agents.exists() else ""
    version_match = re.search(r"(?m)^instruction_contract_version:\s*(\d+)\s*$", agents_text)
    contract_version = int(version_match.group(1)) if version_match else None
    invariant_ids = {item["id"] for item in invariants}
    route_by_id = {item["id"]: item for item in routes}
    missing_required_invariants = sorted(REQUIRED_INVARIANTS - invariant_ids) if has_surface else []
    missing_required_routes = []
    if has_surface:
        for route_id, owner in REQUIRED_ROUTES.items():
            route = route_by_id.get(route_id)
            route_owners = [item.split("#", 1)[0] for item in route["owners"]] if route else []
            if route is None or owner not in route_owners:
                missing_required_routes.append(route_id)

    if has_surface:
        if contract_version != REQUIRED_CONTRACT_VERSION:
            errors.append(
                {
                    "code": "instruction_migration_required",
                    "path": "AGENTS.md",
                    "detail": f"instruction contract version {REQUIRED_CONTRACT_VERSION} is required",
                }
            )
        for invariant_id in missing_required_invariants:
            errors.append(
                {
                    "code": "required_invariant_missing",
                    "path": CANONICAL_FILES["principles"],
                    "detail": invariant_id,
                }
            )
        for route_id in missing_required_routes:
            errors.append(
                {
                    "code": "required_route_missing",
                    "path": "AGENTS.md",
                    "detail": route_id,
                }
            )
        if pitfalls.exists() and not re.search(r"(?m)^incident_schema_version:\s*1\s*$", _read(pitfalls)):
            errors.append(
                {
                    "code": "instruction_migration_required",
                    "path": CANONICAL_FILES["pitfalls"],
                    "detail": "incident catalog migration required",
                }
            )

    invariant_by_id = {item["id"]: item for item in invariants}
    for incident in incidents:
        incident_id = incident.get("id", "incident")
        invariant_id = incident.get("Invariant", "")
        route_id = incident.get("Route", "")
        invariant = invariant_by_id.get(invariant_id)
        route = route_by_id.get(route_id)
        if invariant is None:
            errors.append(
                {
                    "code": "invariant_owner_missing",
                    "path": CANONICAL_FILES["pitfalls"],
                    "detail": f"{incident_id}:{invariant_id}",
                }
            )
        else:
            expected_owner = invariant["owner"] + (f"#{invariant['anchor']}" if invariant["anchor"] else "")
            if incident.get("Owner", "") != expected_owner:
                errors.append(
                    {"code": "invariant_owner_mismatch", "path": CANONICAL_FILES["pitfalls"], "detail": incident_id}
                )
        if route is None:
            errors.append(
                {"code": "route_missing", "path": CANONICAL_FILES["pitfalls"], "detail": f"{incident_id}:{route_id}"}
            )
        elif invariant is not None and invariant["owner"] not in [owner.split("#", 1)[0] for owner in route["owners"]]:
            errors.append(
                {"code": "unreachable_invariant", "path": "AGENTS.md", "detail": f"{incident_id}:{invariant_id}"}
            )
        elif incident.get("Guard") not in route["guards"]:
            errors.append(
                {"code": "guard_missing", "path": "AGENTS.md", "detail": f"{incident_id}:{incident.get('Guard', '')}"}
            )

    error_codes = {item["code"] for item in errors}
    if not errors:
        status = "valid"
    elif "guard_missing" in error_codes:
        status = "guard_missing"
    elif error_codes & {
        "duplicate_invariant_owner",
        "duplicate_invariant_body",
        "conflicting_planning_rule",
        "invariant_owner_mismatch",
        "router_defines_invariant",
        "incident_catalog_defines_invariant",
    }:
        status = "instruction_conflict"
    else:
        status = "instruction_migration_required"
    return {
        "success": not errors,
        "status": status,
        "contract_version": contract_version,
        "required_contract_version": REQUIRED_CONTRACT_VERSION,
        "missing_required_invariants": missing_required_invariants,
        "missing_required_routes": sorted(missing_required_routes),
        "routes": routes,
        "invariants": [{key: value for key, value in item.items() if key != "body"} for item in invariants],
        "incidents": incidents,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate canonical instruction ownership, routes, incidents, and guards."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--repo-root", default=".")
    check.add_argument("--format", choices=("human", "json"), default="human")
    args = parser.parse_args()
    result = check_instruction_contract(Path(args.repo_root))
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"instruction-contract: {result['status']}")
        for issue in result["errors"]:
            print(f"error: {issue['code']}: {issue['path']}: {issue['detail']}")
        for issue in result["warnings"]:
            print(f"warning: {issue['code']}: {issue['path']}: {issue['detail']}")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

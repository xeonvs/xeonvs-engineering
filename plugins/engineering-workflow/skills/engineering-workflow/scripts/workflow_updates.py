#!/usr/bin/env python3
"""Installation-scoped update policy and report-only target recommendations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from documentation_navigation import recognized_source_repository  # noqa: E402
from release_adoption import assess_target_adoption  # noqa: E402
from update_installed_skill import (  # noqa: E402
    SEMVER_RE,
    UpdateConflict,
    _installation_details,
    _tree_entries,
    update_installation,
)

CHECK_TTL_SECONDS = 24 * 60 * 60
POLICIES = {"notify_only", "automatic_stable"}
CACHE_FIELDS = {
    "success",
    "update_status",
    "currentness",
    "source_ref",
    "resolved_commit",
    "candidate_version",
    "previous_version",
    "recommended_action",
    "next_agent_action",
    "automatic_update_allowed",
    "confirmation_required",
    "skill_content_changed",
    "instructions_changed",
    "release_channel",
    "catalog_commit",
    "catalog_ref",
    "delivery_pending",
    "source_latest_version",
    "source_latest_commit",
    "source_latest_ref",
    "delivery_provenance",
    "version_change_kind",
    "major_or_minor_version_changed",
    "release_adoption_descriptor",
    "errors",
    "validation_result",
}


def _identity(value: str) -> str:
    return hashlib.sha256(os.fsencode(value)).hexdigest()


def _skill_fingerprint(skill_path: Path) -> str:
    return _identity(json.dumps(_tree_entries(skill_path), sort_keys=True, separators=(",", ":")))


def _owner_evidence_fingerprint(adoption: dict[str, Any]) -> str:
    evidence = adoption.get("owner_evidence", {})
    if not isinstance(evidence, dict) or any(
        not isinstance(identifier, str) or not isinstance(digest, str) for identifier, digest in evidence.items()
    ):
        raise ValueError("Invalid target owner evidence")
    return _identity(json.dumps(evidence, sort_keys=True, separators=(",", ":")))


def _valid_cached_descriptor(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {"schema_version", "skill_version", "changes"}:
        return False
    if value.get("schema_version") != 1 or not isinstance(value.get("skill_version"), str):
        return False
    if not SEMVER_RE.fullmatch(value["skill_version"]) or not isinstance(value.get("changes"), list):
        return False
    current_fields = {"id", "introduced_in", "summary", "adoption_requirement", "affected_owner_patterns"}
    legacy_fields = current_fields - {"summary"}
    return all(
        isinstance(change, dict)
        and frozenset(change) in {frozenset(current_fields), frozenset(legacy_fields)}
        and isinstance(change["id"], str)
        and isinstance(change["introduced_in"], str)
        and SEMVER_RE.fullmatch(change["introduced_in"]) is not None
        and (
            "summary" not in change
            or (
                isinstance(change["summary"], str)
                and 1 <= len(change["summary"]) <= 240
                and not any(ord(character) < 32 or ord(character) == 127 for character in change["summary"])
            )
        )
        and change["adoption_requirement"] in {"semantic_review", "runtime_only"}
        and isinstance(change["affected_owner_patterns"], list)
        and all(isinstance(pattern, str) for pattern in change["affected_owner_patterns"])
        for change in value["changes"]
    )


def _installation_key(install_path: Path) -> str:
    details = _installation_details(install_path, "skill/engineering-workflow")
    if details["installation_type"] == "plugin_managed":
        plugin = Path(details["plugin_root"])
        if SEMVER_RE.fullmatch(plugin.name):
            return _identity(str(plugin.parent))
    return _identity(str(install_path.absolute()))


def default_state_path(install_path: Path) -> Path:
    identity = _installation_key(install_path)
    return Path.home() / ".codex" / "engineering-workflow-state" / f"{identity}.json"


def _validate_state_path(path: Path, root: Path, install: Path) -> None:
    if path.is_symlink():
        raise ValueError("Installation policy state cannot use a symlink path")
    resolved = path.resolve()
    details = _installation_details(install, "skill/engineering-workflow")
    protected = [root.resolve(), Path(details["resolved_target_path"])]
    if details["installation_type"] == "plugin_managed":
        plugin = Path(details["plugin_root"])
        protected.append(plugin)
        protected.extend(parent for parent in plugin.parents if parent.name == "cache")
    if any(resolved == owner or resolved.is_relative_to(owner) for owner in protected):
        raise ValueError("Installation policy state must be outside targets and installation/cache trees")


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "policy": "notify_only", "proposals": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != 1
        or state.get("policy") not in POLICIES
        or set(state) - {"schema_version", "policy", "proposals", "installation_key", "check"}
    ):
        raise ValueError("Invalid installation update policy state")
    if not isinstance(state.get("proposals", {}), dict):
        raise ValueError("Invalid installation proposal state")
    cached = state.get("check", {})
    if (
        not isinstance(cached, dict)
        or set(cached) - {"checked_at", "installed_version", "installed_fingerprint", "result"}
        or not isinstance(cached.get("checked_at", 0), (int, float))
        or not isinstance(cached.get("result", {}), dict)
        or set(cached.get("result", {})) - CACHE_FIELDS
        or ("installed_version" in cached and not isinstance(cached["installed_version"], str))
        or ("installed_version" in cached and not SEMVER_RE.fullmatch(cached["installed_version"]))
        or ("installed_fingerprint" in cached and not isinstance(cached["installed_fingerprint"], str))
        or ("installed_fingerprint" in cached and len(cached["installed_fingerprint"]) != 64)
        or not _valid_cached_descriptor(cached.get("result", {}).get("release_adoption_descriptor"))
    ):
        raise ValueError("Invalid installation check cache")
    for key, proposal in state.get("proposals", {}).items():
        if (
            not isinstance(key, str)
            or len(key) != 64
            or not isinstance(proposal, dict)
            or proposal.get("outcome") not in {"proposed", "declined", "accepted"}
            or not {"candidate", "outcome", "version", "pending_change_ids"}.issubset(proposal)
            or set(proposal) - {"candidate", "outcome", "version", "pending_change_ids", "owner_evidence_fingerprint"}
            or not isinstance(proposal.get("candidate"), str)
            or len(proposal["candidate"]) != 64
            or (
                "owner_evidence_fingerprint" in proposal and not isinstance(proposal["owner_evidence_fingerprint"], str)
            )
            or ("owner_evidence_fingerprint" in proposal and len(proposal["owner_evidence_fingerprint"]) != 64)
        ):
            raise ValueError("Invalid installation proposal state")
    return state


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=".workflow-updates-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def record_proposal_outcome(state_path: Path, root: Path, install_path: Path, outcome: str) -> None:
    if outcome not in {"declined", "accepted"}:
        raise ValueError("Proposal outcome must be declined or accepted")
    _validate_state_path(state_path, root, install_path)
    state = _read_state(state_path)
    key = _identity(str(root.resolve()))
    if key not in state.get("proposals", {}):
        raise ValueError("No proposal has been emitted for this target")
    state["proposals"][key]["outcome"] = outcome
    _write_state(state_path, state)


def check_workflow_updates(
    root: Path,
    install_path: Path,
    *,
    state_path: Path | None = None,
    apply: bool = False,
    explicit_update: bool = False,
    force_check: bool = False,
    set_policy: str | None = None,
    platform: str | None = None,
    now: float | None = None,
    explicit_proposal: bool = False,
) -> dict[str, Any]:
    """Check/optionally update the skill, then recommend adoption without target mutation."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("Target root must be an existing directory")
    selected_state = state_path or default_state_path(install_path)
    _validate_state_path(selected_state, root, install_path)
    selected_state = selected_state.resolve()
    state = _read_state(selected_state)
    installation_key = _installation_key(install_path)
    if state.get("installation_key", installation_key) != installation_key:
        raise ValueError("Policy state belongs to another installation")
    state["installation_key"] = installation_key
    if set_policy is not None:
        if set_policy not in POLICIES:
            raise ValueError("Unknown installation update policy")
        state["policy"] = set_policy
    timestamp = time.time() if now is None else now
    active_details = _installation_details(install_path, "skill/engineering-workflow")
    active_version = active_details["previous_version"]
    active_fingerprint = _skill_fingerprint(Path(active_details["resolved_target_path"]))
    cached = state.get("check", {})
    age = timestamp - cached.get("checked_at", 0)
    cache_used = (
        not force_check
        and not explicit_update
        and 0 <= age < CHECK_TTL_SECONDS
        and cached.get("installed_version") == active_version
        and cached.get("installed_fingerprint") == active_fingerprint
        and isinstance(cached.get("result"), dict)
        and cached["result"].get("success") is True
        and cached["result"].get("currentness") == "checked"
        and all(
            "summary" in change
            for change in (cached["result"].get("release_adoption_descriptor") or {}).get("changes", [])
        )
    )
    update = dict(cached["result"]) if cache_used else update_installation(install_path)
    update_attempted = False
    may_apply = apply and (explicit_update or state["policy"] == "automatic_stable")
    if (
        may_apply
        and update.get("success")
        and update.get("skill_content_changed")
        and update.get("automatic_update_allowed")
    ):
        # Apply always rediscovers; pins both source and native delivery to the reviewed check.
        update_attempted = True
        update = update_installation(
            install_path,
            apply=True,
            expected_commit=update["resolved_commit"],
            expected_catalog_commit=update.get("catalog_commit"),
            platform=platform,
        )
    # Recommendations use the installed descriptor/version after any verified update.
    native_unverified = bool(update.get("native_mutation_attempted") and not update.get("native_readback_verified"))
    observed_install = Path(update.get("active_installation_path") or install_path)
    try:
        if native_unverified:
            raise UpdateConflict("native_readback_required", "Native installation identity requires verified readback")
        observed_details = _installation_details(observed_install, "skill/engineering-workflow")
        installed_version = observed_details["previous_version"]
        installed_fingerprint = _skill_fingerprint(Path(observed_details["resolved_target_path"]))
    except (OSError, UpdateConflict):
        observed_details = active_details
        installed_version = (
            update.get("observed_native_version")
            if native_unverified
            else (
                update.get("installed_version")
                if isinstance(update.get("installed_version"), str) and SEMVER_RE.fullmatch(update["installed_version"])
                else active_version
            )
        )
        installed_fingerprint = None if native_unverified else active_fingerprint
    cacheable = update.get("success") is True and update.get("currentness") == "checked"
    if not cache_used or update_attempted:
        if cacheable:
            state["check"] = {
                "checked_at": timestamp,
                "installed_version": installed_version,
                "installed_fingerprint": installed_fingerprint,
                "result": {key: value for key, value in update.items() if key in CACHE_FIELDS},
            }
        else:
            state.pop("check", None)
    proposed_version = update.get("candidate_version") if update.get("success") else None
    if native_unverified:
        adoption = {
            "mode": "report_only",
            "target_mutation_allowed": False,
            "adoption_status": "native_readback_required",
            "pending_change_ids": [],
            "resolved_change_ids": [],
            "changes": [],
            "runtime_changes": [],
            "owner_evidence": {},
            "semantic_review_performed": False,
            "target_version": None,
            "next_agent_action": "recheck_native_installation_and_recover",
        }
    elif recognized_source_repository(root):
        adoption = {
            "mode": "report_only",
            "target_mutation_allowed": False,
            "adoption_status": "source_maintainer_review",
            "pending_change_ids": [],
            "resolved_change_ids": [],
            "changes": [],
            "runtime_changes": [],
            "owner_evidence": {},
            "semantic_review_performed": False,
            "target_version": proposed_version or installed_version,
            "next_agent_action": "review_source_maintainer_owners_directly",
        }
    else:
        adoption = assess_target_adoption(
            root, proposed_version or installed_version, descriptor=update.get("release_adoption_descriptor")
        )
    owner_evidence_fingerprint = _owner_evidence_fingerprint(adoption)
    candidate_key = _identity(
        json.dumps(
            {
                "version": proposed_version or installed_version,
                "source_commit": update.get("resolved_commit"),
                "catalog_commit": update.get("catalog_commit"),
                "pending": adoption["pending_change_ids"],
                "owner_evidence": adoption.get("owner_evidence", {}),
            },
            sort_keys=True,
        )
    )
    target_key = _identity(str(root))
    previous = state.get("proposals", {}).get(target_key)
    if (
        update.get("currentness") == "unknown"
        and previous
        and previous.get("version") == installed_version
        and previous.get("pending_change_ids") == adoption["pending_change_ids"]
        and previous.get("owner_evidence_fingerprint") == owner_evidence_fingerprint
    ):
        candidate_key = previous["candidate"]
    should_propose = bool(adoption["pending_change_ids"]) and (
        explicit_proposal or previous is None or previous.get("candidate") != candidate_key
    )
    if should_propose:
        state.setdefault("proposals", {})[target_key] = {
            "candidate": candidate_key,
            "outcome": "proposed",
            "version": proposed_version or installed_version,
            "pending_change_ids": adoption["pending_change_ids"],
            "owner_evidence_fingerprint": owner_evidence_fingerprint,
        }
    _write_state(selected_state, state)
    return {
        "success": bool(update.get("success")),
        "mode": "workflow_updates",
        "installation_policy": state["policy"],
        "check_cache_used": cache_used,
        "check_cache_ttl_seconds": CHECK_TTL_SECONDS,
        "update_attempted": update_attempted,
        "skill_update": update,
        "installed_version": installed_version,
        "last_known_installed_version": active_version,
        "loaded_skill_refresh_required": update.get("update_status") == "updated",
        "target_recommendation": adoption
        | {
            "installation_update_required": proposed_version is not None and proposed_version != installed_version,
            "proposal_emitted": should_propose,
            "proposal_suppressed": bool(adoption["pending_change_ids"]) and not should_propose,
            "previous_outcome": previous.get("outcome") if previous else None,
        },
        "target_mutation_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--install-path", required=True)
    parser.add_argument("--state-path")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true", help="Explicitly request the reviewed stable update")
    mode.add_argument("--refresh", action="store_true", help="Apply only under automatic_stable policy")
    parser.add_argument("--set-policy", choices=sorted(POLICIES))
    parser.add_argument("--force-check", action="store_true")
    parser.add_argument("--platform", choices=("codex", "claude"))
    parser.add_argument("--explicit-proposal", action="store_true")
    parser.add_argument("--proposal-outcome", choices=("declined", "accepted"))
    parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args()
    root, install = Path(args.repo_root), Path(args.install_path).expanduser()
    try:
        state = Path(args.state_path).expanduser() if args.state_path else default_state_path(install)
        if args.proposal_outcome:
            record_proposal_outcome(state, root, install, args.proposal_outcome)
        result = check_workflow_updates(
            root,
            install,
            state_path=state,
            apply=args.apply or args.refresh,
            explicit_update=args.apply,
            force_check=args.force_check,
            set_policy=args.set_policy,
            platform=args.platform,
            explicit_proposal=args.explicit_proposal,
        )
    except (ValueError, OSError, UpdateConflict) as exc:
        result = {
            "success": False,
            "errors": [
                {
                    "code": getattr(exc, "code", "workflow_update_state_invalid"),
                    "message": "Workflow update state or installation could not be read safely",
                }
            ],
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

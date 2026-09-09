#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "templates" / "PROGRAMMATIC_TOOL_STAGE.md.tmpl"
STAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CALL_SHAPES = {"single", "multiple", "dependent", "unknown"}
CONTROL_FLOWS = {"predictable", "adaptive", "unknown"}
JUDGMENT_MODES = {"required", "not_required", "unknown"}
NATIVE_PATH_STATES = {"adequate", "inadequate", "unknown"}
SCHEMA_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "anyOf",
    "oneOf",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "pattern",
}
BOOLEAN_FIELDS = (
    "schemas_known",
    "can_reduce_output",
    "side_effecting",
    "approval_sensitive",
    "citations_required",
    "native_artifacts_required",
    "runtime_available",
)
SPEC_KEYS = {
    "schema_version",
    "stage_id",
    "eligible_tools",
    "call_shape",
    "schemas_known",
    "control_flow",
    "can_reduce_output",
    "fresh_model_judgment",
    "side_effecting",
    "approval_sensitive",
    "citations_required",
    "native_artifacts_required",
    "repo_native_path",
    "runtime_available",
    "output_schema",
    "evidence_fields",
    "max_calls",
    "max_concurrency",
    "retry_limit",
    "stop_condition",
    "direct_handoff",
}


class StageSpecError(ValueError):
    pass


def _contains_instruction_control(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in ("<tool_orchestration", "</tool_orchestration", "{{", "}}", "\x00"))
    if isinstance(value, dict):
        return any(
            _contains_instruction_control(key) or _contains_instruction_control(item) for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_instruction_control(item) for item in value)
    return False


def _optional_bool(spec: dict[str, Any], field: str, errors: list[str]) -> bool | None:
    value = spec.get(field)
    if value is not None and not isinstance(value, bool):
        errors.append(f"{field} must be true, false, or null")
        return None
    return value


def _bounded_text(spec: dict[str, Any], field: str, errors: list[str]) -> str:
    value = spec.get(field, "")
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")
        return ""
    value = value.strip()
    if len(value) > 500:
        errors.append(f"{field} must be at most 500 characters")
    if "\n" in value or "\r" in value:
        errors.append(f"{field} must be a single line")
    if _contains_instruction_control(value):
        errors.append(f"{field} must not contain instruction-control markers")
    return value


def _validate_schema_node(schema: Any, location: str, errors: list[str]) -> None:
    if not isinstance(schema, dict):
        errors.append(f"{location} must be an object")
        return
    if not all(isinstance(key, str) for key in schema):
        errors.append(f"{location} keywords must be strings")
        return
    unknown = sorted(set(schema) - SCHEMA_KEYS)
    if unknown:
        errors.append(f"{location} contains unsupported keywords: {', '.join(unknown)}")
    schema_type = schema.get("type")
    if schema_type is not None and (not isinstance(schema_type, str) or schema_type not in SCHEMA_TYPES):
        errors.append(f"{location}.type is unsupported")
    if schema_type is None and "anyOf" not in schema and "oneOf" not in schema:
        errors.append(f"{location} must declare type, anyOf, or oneOf")
    properties = schema.get("properties")
    required = schema.get("required")
    if schema_type == "object":
        if not isinstance(properties, dict):
            errors.append(f"{location}.properties must be an object")
            properties = {}
        elif not all(isinstance(key, str) and key for key in properties):
            errors.append(f"{location}.properties keys must be non-empty strings")
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            errors.append(f"{location}.required must be a string array")
            required = []
        elif len(set(required)) != len(required):
            errors.append(f"{location}.required must not contain duplicates")
        elif any(field not in properties for field in required):
            errors.append(f"{location}.required contains a field missing from properties")
        if schema.get("additionalProperties") is not False:
            errors.append(f"{location}.additionalProperties must be false")
        for field, child in properties.items():
            if isinstance(field, str) and field:
                _validate_schema_node(child, f"{location}.properties.{field}", errors)
    elif any(key in schema for key in ("properties", "required", "additionalProperties")):
        errors.append(f"{location} uses object keywords without type object")

    if schema_type == "array":
        if "items" not in schema:
            errors.append(f"{location}.items is required for arrays")
        else:
            _validate_schema_node(schema["items"], f"{location}.items", errors)
    elif "items" in schema:
        errors.append(f"{location} uses items without type array")

    for keyword in ("anyOf", "oneOf"):
        if keyword not in schema:
            continue
        choices = schema[keyword]
        if not isinstance(choices, list) or not 1 <= len(choices) <= 8:
            errors.append(f"{location}.{keyword} must contain 1 to 8 schemas")
            continue
        for index, choice in enumerate(choices):
            _validate_schema_node(choice, f"{location}.{keyword}[{index}]", errors)

    if "enum" in schema:
        values = schema["enum"]
        if not isinstance(values, list) or not values:
            errors.append(f"{location}.enum must be a non-empty array")
        elif any(isinstance(item, (dict, list)) for item in values):
            errors.append(f"{location}.enum supports scalar values only")
    for keyword in ("minimum", "maximum"):
        value = schema.get(keyword)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            errors.append(f"{location}.{keyword} must be a number")
        if keyword in schema and schema_type not in {"number", "integer"}:
            errors.append(f"{location}.{keyword} requires a numeric type")
    for keyword in ("minItems", "maxItems", "minLength", "maxLength"):
        value = schema.get(keyword)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            errors.append(f"{location}.{keyword} must be a non-negative integer")
    for keyword in ("minItems", "maxItems"):
        if keyword in schema and schema_type != "array":
            errors.append(f"{location}.{keyword} requires type array")
    for keyword in ("minLength", "maxLength", "pattern"):
        if keyword in schema and schema_type != "string":
            errors.append(f"{location}.{keyword} requires type string")
    if "pattern" in schema and not isinstance(schema["pattern"], str):
        errors.append(f"{location}.pattern must be a string")
    for minimum_key, maximum_key in (
        ("minimum", "maximum"),
        ("minItems", "maxItems"),
        ("minLength", "maxLength"),
    ):
        minimum = schema.get(minimum_key)
        maximum = schema.get(maximum_key)
        if (
            isinstance(minimum, (int, float))
            and not isinstance(minimum, bool)
            and isinstance(maximum, (int, float))
            and not isinstance(maximum, bool)
            and minimum > maximum
        ):
            errors.append(f"{location}.{minimum_key} must not exceed {maximum_key}")


def _validate_schema(schema: Any, evidence_fields: list[str], errors: list[str]) -> dict[str, Any] | None:
    if schema is None:
        return None
    if not isinstance(schema, dict):
        errors.append("output_schema must be an object or null")
        return None
    try:
        encoded = json.dumps(schema, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError, RecursionError):
        errors.append("output_schema must contain only JSON values")
        return None
    if len(encoded.encode("utf-8")) > 65_536:
        errors.append("output_schema must not exceed 64 KiB")
    if _contains_instruction_control(schema):
        errors.append("output_schema must not contain instruction-control markers")
    _validate_schema_node(schema, "output_schema", errors)
    if schema.get("type") != "object":
        errors.append("output_schema root type must be object")
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict):
        properties = {}
    if not isinstance(required, list):
        required = []
    for field in evidence_fields:
        if field not in properties or field not in required:
            errors.append(f"evidence field is not required by output_schema: {field}")
    return schema


def _result_schema(
    stage_id: str,
    payload_schema: dict[str, Any],
    evidence_fields: list[str],
) -> dict[str, Any]:
    evidence_schema = {
        "type": "object",
        "properties": {field: payload_schema["properties"][field] for field in evidence_fields},
        "required": [],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["completed", "failed"]},
            "stage": {"type": "string", "const": stage_id},
            "data": {"anyOf": [payload_schema, {"type": "null"}]},
            "evidence": evidence_schema,
            "missing": {"type": "array", "items": {"type": "string"}},
            "errors": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "stage", "data", "evidence", "missing", "errors"],
        "additionalProperties": False,
    }


def _render_instructions(spec: dict[str, Any], output_schema: dict[str, Any]) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    replacements = {
        "stage_id": spec["stage_id"],
        "eligible_tools": ", ".join(spec["eligible_tools"]),
        "max_calls": str(spec["max_calls"]),
        "max_concurrency": str(spec["max_concurrency"]),
        "result_schema": json.dumps(
            _result_schema(spec["stage_id"], output_schema, spec["evidence_fields"]),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ),
        "evidence_fields": ", ".join(spec["evidence_fields"]),
        "stop_condition": spec["stop_condition"],
        "retry_limit": str(spec["retry_limit"]),
        "direct_handoff": spec["direct_handoff"],
    }
    for key, value in replacements.items():
        template = template.replace("{{ " + key + " }}", value)
    if "{{" in template or "}}" in template:
        raise StageSpecError("runtime template contains an unresolved placeholder")
    return template


def assess_stage(spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict):
        return {
            "success": False,
            "decision": None,
            "reasons": [],
            "missing_fields": [],
            "errors": ["stage specification must be a JSON object"],
            "rendered_instructions": None,
        }

    errors: list[str] = []
    if not all(isinstance(key, str) for key in spec):
        errors.append("stage specification keys must be strings")
    else:
        unknown_keys = sorted(set(spec) - SPEC_KEYS)
        if unknown_keys:
            errors.append(f"stage specification contains unsupported fields: {', '.join(unknown_keys)}")
    schema_version = spec.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != 1:
        errors.append("schema_version must be 1")
    stage_id = spec.get("stage_id")
    if not isinstance(stage_id, str) or not STAGE_ID_RE.fullmatch(stage_id):
        errors.append("stage_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")

    call_shape = spec.get("call_shape", "unknown")
    if not isinstance(call_shape, str) or call_shape not in CALL_SHAPES:
        errors.append("call_shape must be single, multiple, dependent, or unknown")
        call_shape = "unknown"
    control_flow = spec.get("control_flow", "unknown")
    if not isinstance(control_flow, str) or control_flow not in CONTROL_FLOWS:
        errors.append("control_flow must be predictable, adaptive, or unknown")
        control_flow = "unknown"
    fresh_judgment = spec.get("fresh_model_judgment", "unknown")
    if not isinstance(fresh_judgment, str) or fresh_judgment not in JUDGMENT_MODES:
        errors.append("fresh_model_judgment must be required, not_required, or unknown")
        fresh_judgment = "unknown"
    native_path = spec.get("repo_native_path", "unknown")
    if not isinstance(native_path, str) or native_path not in NATIVE_PATH_STATES:
        errors.append("repo_native_path must be adequate, inadequate, or unknown")
        native_path = "unknown"

    booleans = {field: _optional_bool(spec, field, errors) for field in BOOLEAN_FIELDS}

    tools = spec.get("eligible_tools", [])
    if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools):
        errors.append("eligible_tools must be a string array")
        tools = []
    elif any(not TOOL_NAME_RE.fullmatch(item) for item in tools):
        errors.append("eligible_tools contains an invalid tool name")
    elif len(set(tools)) != len(tools):
        errors.append("eligible_tools must not contain duplicates")
    elif len(tools) > 32:
        errors.append("eligible_tools must contain at most 32 names")

    evidence_fields = spec.get("evidence_fields", [])
    if not isinstance(evidence_fields, list) or not all(isinstance(item, str) for item in evidence_fields):
        errors.append("evidence_fields must be a string array")
        evidence_fields = []
    elif len(set(evidence_fields)) != len(evidence_fields):
        errors.append("evidence_fields must not contain duplicates")
    elif any(not STAGE_ID_RE.fullmatch(item) for item in evidence_fields):
        errors.append("evidence_fields contains an invalid field name")
    elif len(evidence_fields) > 64:
        errors.append("evidence_fields must contain at most 64 names")

    max_calls = spec.get("max_calls")
    if max_calls is not None and (
        isinstance(max_calls, bool) or not isinstance(max_calls, int) or not 1 <= max_calls <= 100
    ):
        errors.append("max_calls must be an integer from 1 to 100")
    max_concurrency = spec.get("max_concurrency")
    if max_concurrency is not None and (
        isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) or not 1 <= max_concurrency <= 8
    ):
        errors.append("max_concurrency must be an integer from 1 to 8")
    if (
        isinstance(max_calls, int)
        and not isinstance(max_calls, bool)
        and isinstance(max_concurrency, int)
        and not isinstance(max_concurrency, bool)
        and max_concurrency > max_calls
    ):
        errors.append("max_concurrency must not exceed max_calls")
    if (
        call_shape in {"multiple", "dependent"}
        and isinstance(max_calls, int)
        and not isinstance(max_calls, bool)
        and max_calls < 2
    ):
        errors.append("multiple or dependent call_shape requires max_calls of at least 2")
    retry_limit = spec.get("retry_limit")
    if retry_limit is not None and (
        isinstance(retry_limit, bool) or not isinstance(retry_limit, int) or retry_limit not in (0, 1)
    ):
        errors.append("retry_limit must be 0 or 1")

    stop_condition = _bounded_text(spec, "stop_condition", errors)
    direct_handoff = _bounded_text(spec, "direct_handoff", errors)
    output_schema = _validate_schema(spec.get("output_schema"), evidence_fields, errors)

    if errors:
        return {
            "success": False,
            "decision": None,
            "reasons": [],
            "missing_fields": [],
            "errors": errors,
            "rendered_instructions": None,
        }

    direct_reasons: list[str] = []
    if booleans["runtime_available"] is False:
        direct_reasons.append("programmatic runtime is unavailable")
    if native_path == "adequate":
        direct_reasons.append("one adequate repository-native operation already owns the stage")
    if call_shape == "single":
        direct_reasons.append("one tool call is sufficient")
    if control_flow == "adaptive":
        direct_reasons.append("control flow is adaptive")
    if fresh_judgment == "required":
        direct_reasons.append("intermediate results require fresh model judgment")
    for field, reason in (
        ("side_effecting", "the stage is side-effecting"),
        ("approval_sensitive", "the stage crosses an approval boundary"),
        ("citations_required", "the final result requires citations"),
        ("native_artifacts_required", "the final result requires native artifacts"),
    ):
        if booleans[field] is True:
            direct_reasons.append(reason)
    if booleans["schemas_known"] is False:
        direct_reasons.append("tool result schemas are not known")
    if booleans["can_reduce_output"] is False:
        direct_reasons.append("code cannot reduce the intermediate results")
    if direct_reasons:
        return {
            "success": True,
            "decision": "direct",
            "reasons": direct_reasons,
            "missing_fields": [],
            "errors": [],
            "rendered_instructions": None,
        }

    missing_fields: list[str] = []
    if not tools:
        missing_fields.append("eligible_tools")
    if call_shape == "unknown":
        missing_fields.append("call_shape")
    if control_flow == "unknown":
        missing_fields.append("control_flow")
    if fresh_judgment == "unknown":
        missing_fields.append("fresh_model_judgment")
    if native_path == "unknown":
        missing_fields.append("repo_native_path")
    for field, value in booleans.items():
        if value is None:
            missing_fields.append(field)
    for field, value in (
        ("max_calls", max_calls),
        ("max_concurrency", max_concurrency),
        ("retry_limit", retry_limit),
    ):
        if value is None:
            missing_fields.append(field)
    if not stop_condition:
        missing_fields.append("stop_condition")
    if not direct_handoff:
        missing_fields.append("direct_handoff")
    if output_schema is None:
        missing_fields.append("output_schema")
    if not evidence_fields:
        missing_fields.append("evidence_fields")
    if missing_fields:
        return {
            "success": True,
            "decision": "ask",
            "reasons": ["material stage facts remain unresolved after repository inspection"],
            "missing_fields": missing_fields,
            "errors": [],
            "rendered_instructions": None,
        }

    normalized = {
        **spec,
        "stage_id": stage_id,
        "eligible_tools": tools,
        "evidence_fields": evidence_fields,
        "max_calls": max_calls,
        "max_concurrency": max_concurrency,
        "retry_limit": retry_limit,
        "stop_condition": stop_condition,
        "direct_handoff": direct_handoff,
    }
    try:
        rendered = _render_instructions(normalized, output_schema)
    except (OSError, TypeError, StageSpecError) as exc:
        return {
            "success": False,
            "decision": None,
            "reasons": [],
            "missing_fields": [],
            "errors": [f"instruction rendering failed: {type(exc).__name__}"],
            "rendered_instructions": None,
        }
    return {
        "success": True,
        "decision": "programmatic",
        "reasons": ["bounded predictable stage can reduce multiple structured tool results"],
        "missing_fields": [],
        "errors": [],
        "rendered_instructions": rendered,
    }


def _load_spec(path: str) -> Any:
    if path == "-":
        import sys

        return _decode_spec(sys.stdin.read(262_145))
    source = Path(path)
    if source.stat().st_size > 262_144:
        raise StageSpecError("stage specification exceeds 256 KiB")
    return _decode_spec(source.read_text(encoding="utf-8"))


def _reject_json_constant(value: str) -> None:
    raise StageSpecError(f"non-standard JSON constant is not allowed: {value}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StageSpecError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _decode_spec(raw: str) -> Any:
    if len(raw.encode("utf-8")) > 262_144:
        raise StageSpecError("stage specification exceeds 256 KiB")
    return json.loads(
        raw,
        object_pairs_hook=_object_without_duplicates,
        parse_constant=_reject_json_constant,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assess a model-supplied bounded stage and render Programmatic Tool Calling instructions."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", help="JSON stage specification path, or - for stdin")
    source.add_argument("--spec-json", help="In-memory JSON stage specification")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()
    try:
        loaded = _decode_spec(args.spec_json) if args.spec_json is not None else _load_spec(args.spec)
        result = assess_stage(loaded)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, StageSpecError) as exc:
        result = {
            "success": False,
            "decision": None,
            "reasons": [],
            "missing_fields": [],
            "errors": [f"stage specification could not be loaded: {type(exc).__name__}"],
            "rendered_instructions": None,
        }
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["decision"] or "invalid")
        for reason in result["reasons"] or result["errors"]:
            print(f"- {reason}")
        for field in result["missing_fields"]:
            print(f"- missing: {field}")
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

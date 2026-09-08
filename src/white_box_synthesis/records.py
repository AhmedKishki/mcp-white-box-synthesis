"""Public record validation and versions."""

from __future__ import annotations

from typing import Any

REPORT_SCHEMA = "white-box-synthesis.verify-report"
SCHEMA_VERSION = "1.0"
OPERATION_POLICY_VERSION = "0.1"


def contract_record(
    name: str = REPORT_SCHEMA,
    operation_policy_version: str = OPERATION_POLICY_VERSION,
) -> dict[str, str]:
    """Return version metadata for a public report."""
    return {
        "name": name,
        "schema_version": SCHEMA_VERSION,
        "operation_policy_version": operation_policy_version,
    }


def validate_record_version(value: dict[str, Any], label: str) -> str | None:
    """Validate an optional input record version."""
    version = value.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        return (
            f"{label} schema_version must be {SCHEMA_VERSION!r}; "
            f"received {version!r}."
        )
    return None


def index_passages(value: Any) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    """Validate source passage records and index them by id."""
    if not isinstance(value, list) or not value:
        return None, "At least one passage is required."

    indexed: dict[str, dict[str, Any]] = {}
    for index, passage in enumerate(value):
        label = f"passages[{index}]"
        if not isinstance(passage, dict):
            return None, f"{label} must be an object."
        problem = validate_record_version(passage, label)
        if problem:
            return None, problem

        passage_id = passage.get("id")
        text = passage.get("text")
        source = passage.get("source")
        if not isinstance(passage_id, str) or not passage_id.strip():
            return None, f"{label}.id must be a non-empty string."
        if not isinstance(text, str) or not text.strip():
            return None, f"{label}.text must be a non-empty string."
        if source is not None and not isinstance(source, str):
            return None, f"{label}.source must be a string when provided."
        if passage_id in indexed:
            return None, f"Duplicate passage id {passage_id!r}."
        indexed[passage_id] = passage

    return indexed, None


def validate_output_context(value: Any) -> str | None:
    """Validate the task context without treating it as source evidence."""
    if not isinstance(value, str) or not value.strip():
        return "output_context must be a non-empty string."
    return None


def validate_candidate(value: Any) -> str | None:
    """Validate the candidate envelope before operation-level reporting."""
    if not isinstance(value, dict):
        return "candidate must be an object."
    problem = validate_record_version(value, "candidate")
    if problem:
        return problem

    output = value.get("output")
    operations = value.get("operations")
    if not isinstance(output, str) or not output.strip():
        return "candidate.output must be a non-empty string."
    if not isinstance(operations, list) or not operations:
        return "candidate.operations must be a non-empty list."
    return None


def assessment_record(
    *,
    mechanical_status: str,
    record_validation: str,
    unverified_indexes: list[int] | None,
    human_review: str,
    mechanical_detail: str,
) -> dict[str, dict[str, Any]]:
    """Keep distinct kinds of verification and review explicit."""
    if unverified_indexes is None:
        unverified_work: dict[str, Any] = {"status": "not_applicable"}
    else:
        unverified_work = {
            "status": "present" if unverified_indexes else "absent",
            "operation_indexes": unverified_indexes,
        }

    return {
        "mechanical_validity": {
            "status": mechanical_status,
            "record_validation": record_validation,
            "detail": mechanical_detail,
        },
        "unverified_work": unverified_work,
        "agent_support": {
            "status": "not_assessed",
            "detail": (
                "The current verifier records no agent assessment of semantic "
                "support."
            ),
        },
        "human_review": {
            "status": human_review,
            "detail": (
                "Human review of meaning and source use is required."
                if human_review == "required"
                else "There is no usable candidate to review."
            ),
        },
    }

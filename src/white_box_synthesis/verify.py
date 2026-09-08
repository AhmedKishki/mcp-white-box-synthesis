"""Legacy flat derivation verification."""

from __future__ import annotations

import re
from typing import Any

from .records import (
    assessment_record,
    contract_record,
    index_passages,
    validate_candidate,
    validate_output_context,
    validate_record_version,
)

_WHITESPACE = re.compile(r"\s+")

CONTENT_OPS = frozenset({"COPY", "INFLECT", "NORMALISE"})
SILENT_OPS = frozenset({"DELETE", "ORDER"})
KNOWN_OPS = CONTENT_OPS | SILENT_OPS

INFLECT_AXES = frozenset({"tense", "number", "case", "article", "pronoun"})

VERIFIED = "verified"
UNVERIFIED = "unverified"
FAILED = "failed"

GAP_TYPES = frozenset({
    "Missing user wording",
    "Missing evidence",
    "Unsupported connection",
    "Source-context ambiguity",
    "Arc inconsistency",
    "Constraint conflict",
})

GAP_FIELDS = (
    "passage_id",
    "argument_id",
    "missing_requirement",
    "authoritative_owner",
    "question",
    "resolution_paths",
)


def normalise_whitespace(text: str) -> str:
    """Collapse whitespace for legacy reporting."""
    return _WHITESPACE.sub(" ", text).strip()


def strip_whitespace(text: str) -> str:
    """Remove whitespace for the legacy reconstruction check."""
    return _WHITESPACE.sub("", text)


def locate(haystack: str, needle: str, occurrence: int) -> tuple[int, int] | None:
    """Return offsets for a one-indexed, possibly overlapping occurrence."""
    if occurrence < 1 or not needle:
        return None
    index = -1
    for _ in range(occurrence):
        index = haystack.find(needle, index + 1)
        if index == -1:
            return None
    return index, index + len(needle)


def _entry(index: int, op_type: str, status: str, method: str, detail: str, **extra: Any) -> dict:
    entry = {
        "index": index,
        "type": op_type,
        "status": status,
        "method": method,
        "detail": detail,
    }
    entry.update(extra)
    return entry


def _check_operation(index: int, op: Any, passages: dict[str, dict]) -> tuple[dict, str | None]:
    """Verify one legacy operation."""
    if not isinstance(op, dict):
        return _entry(index, "?", FAILED, "structure", "Operation is not an object."), None

    problem = validate_record_version(op, f"operations[{index}]")
    if problem:
        return _entry(index, str(op.get("type", "?")), FAILED, "structure", problem), None

    op_type = op.get("type")
    if op_type not in KNOWN_OPS:
        return _entry(
            index,
            str(op_type),
            FAILED,
            "structure",
            f"Unknown operation type. Expected one of {sorted(KNOWN_OPS)}.",
        ), None

    passage_id = op.get("passage_id")
    text = op.get("text")
    occurrence = op.get("occurrence", 1)

    if (
        not isinstance(passage_id, str)
        or not passage_id.strip()
        or not isinstance(text, str)
        or not text
    ):
        return _entry(
            index, op_type, FAILED, "structure",
            "Operation needs a non-empty string passage_id and text.",
        ), None

    if (
        not isinstance(occurrence, int)
        or isinstance(occurrence, bool)
        or occurrence < 1
    ):
        return _entry(
            index, op_type, FAILED, "structure",
            "occurrence must be a positive integer.",
        ), None

    passage = passages.get(passage_id)
    if passage is None:
        return _entry(
            index, op_type, FAILED, "structure",
            f"No passage with id {passage_id!r}.",
            passage_id=passage_id,
        ), None

    span = locate(passage["text"], text, occurrence)
    if span is None:
        total = passage["text"].count(text)
        if total == 0:
            detail = "Quoted text does not appear in the passage."
        else:
            detail = (
                f"Quoted text appears {total} time(s) in the passage, "
                f"so occurrence {occurrence} does not exist."
            )
        return _entry(
            index, op_type, FAILED, "span_resolution", detail,
            passage_id=passage_id, source=passage.get("source"), text=text,
            occurrence=occurrence,
        ), None

    common = {
        "passage_id": passage_id,
        "source": passage.get("source"),
        "text": text,
        "occurrence": occurrence,
        "span": list(span),
    }

    if op_type == "COPY":
        return _entry(
            index, op_type, VERIFIED, "exact_substring",
            "Span reproduced verbatim from the passage.",
            **common,
        ), text

    if op_type in SILENT_OPS:
        note = op.get("note")
        if note is not None and not isinstance(note, str):
            return _entry(
                index, op_type, FAILED, "structure",
                "note must be a string when provided.",
                **common,
            ), None
        return _entry(
            index, op_type, VERIFIED, "legal_by_construction",
            "Cannot introduce new characters under the current policy. "
            "Recorded for audit; semantic legality is not assessed.",
            note=note, **common,
        ), None

    output_text = op.get("output_text")
    if not isinstance(output_text, str) or not output_text:
        return _entry(
            index, op_type, FAILED, "structure",
            f"{op_type} needs a non-empty output_text.",
            **common,
        ), None

    if op_type == "INFLECT":
        axis = op.get("axis")
        if axis not in INFLECT_AXES:
            return _entry(
                index, op_type, FAILED, "structure",
                f"INFLECT needs an axis from {sorted(INFLECT_AXES)}.",
                output_text=output_text, **common,
            ), None
        common["axis"] = axis

    return _entry(
        index, op_type, UNVERIFIED, "logged_only",
        f"{op_type} alters characters. Not checked in v0. The claim is "
        "recorded verbatim for human audit.",
        output_text=output_text, **common,
    ), output_text


def _basis_code(passage_id: str) -> str:
    return passage_id.removeprefix("src:")


def _declaration(report: list[dict], reconstruction_ok: bool) -> dict:
    """Derive the legacy provenance declaration."""
    content = [e for e in report if e["type"] in CONTENT_OPS]
    used = [e for e in report if e.get("passage_id") and e["status"] != FAILED]

    basis: list[str] = []
    for entry in used:
        code = _basis_code(entry["passage_id"])
        if code not in basis:
            basis.append(code)

    blocked = any(e["status"] == FAILED for e in report) or not reconstruction_ok
    altering = [e for e in content if e["type"] != "COPY"]
    passage_ids = {e["passage_id"] for e in content if e.get("passage_id")}

    if blocked:
        provenance = "Unverified"
        human_wording = "Unverified"
        method = "white-box synthesis"
    else:
        if altering:
            human_wording = "Unverified"
        else:
            human_wording = "100%"

        single_source = len(passage_ids) == 1 and len(content) == 1
        if single_source and not altering:
            provenance = "Human"
            code = next(iter(passage_ids))
            method = (
                "verbatim user wording" if code.startswith("user-")
                else "verbatim source excerpt"
            )
        else:
            provenance = "Mixed"
            method = "white-box synthesis"

    return {
        "provenance": provenance,
        "human_wording": human_wording,
        "method": method,
        "basis": basis or ["Unverified"],
        "compact": (
            f"**Provenance:** {provenance} \u00b7 Human wording: {human_wording} "
            f"\u00b7 Method: {method} \u00b7 Basis: "
            + ", ".join(basis or ["Unverified"])
        ),
        "blocks_selection": blocked or human_wording == "Unverified",
    }


def _check_gap(gap: Any) -> str | None:
    """Return an error message when the gap is not properly typed."""
    if not isinstance(gap, dict):
        return "gap must be an object."
    problem = validate_record_version(gap, "gap")
    if problem:
        return problem
    gap_type = gap.get("type")
    if gap_type not in GAP_TYPES:
        return f"gap type must be one of {sorted(GAP_TYPES)}."
    missing = [f for f in GAP_FIELDS if not gap.get(f)]
    if missing:
        return f"gap is missing required field(s): {', '.join(missing)}."
    string_fields = GAP_FIELDS[:-1]
    invalid_strings = [
        field
        for field in string_fields
        if not isinstance(gap[field], str) or not gap[field].strip()
    ]
    if invalid_strings:
        return (
            "gap field(s) must be non-empty strings: "
            + ", ".join(invalid_strings)
            + "."
        )
    paths = gap["resolution_paths"]
    if (
        not isinstance(paths, list)
        or not paths
        or any(not isinstance(path, str) or not path.strip() for path in paths)
    ):
        return "gap.resolution_paths must be a non-empty list of non-empty strings."
    return None


def _rejection(error: str) -> dict:
    """Build a versioned validation rejection."""
    return {
        "contract": contract_record(),
        "status": "rejected",
        "error": error,
        "assessment": assessment_record(
            mechanical_status="failed",
            record_validation="failed",
            unverified_indexes=None,
            human_review="not_applicable",
            mechanical_detail="The submitted record is invalid.",
        ),
    }


def verify(
    passages: list[dict],
    output_context: str,
    candidate: dict | None = None,
    gap: dict | None = None,
) -> dict:
    """Verify one submitted derivation, or record a declared gap."""
    if (candidate is None) == (gap is None):
        return _rejection("Submit exactly one of candidate or gap.")

    problem = validate_output_context(output_context)
    if problem:
        return _rejection(problem)

    by_id, problem = index_passages(passages)
    if problem:
        return _rejection(problem)
    assert by_id is not None

    if gap is not None:
        problem = _check_gap(gap)
        if problem:
            return _rejection(problem)
        return {
            "contract": contract_record(),
            "status": "gap",
            "output_context": output_context,
            "gap": gap,
            "assessment": assessment_record(
                mechanical_status="not_applicable",
                record_validation="passed",
                unverified_indexes=None,
                human_review="required",
                mechanical_detail="No candidate derivation was submitted.",
            ),
            "sources": [
                {"id": p["id"], "source": p.get("source")} for p in passages
            ],
        }

    problem = validate_candidate(candidate)
    if problem:
        return _rejection(problem)
    assert isinstance(candidate, dict)
    operations = candidate.get("operations")
    output = candidate.get("output")
    assert isinstance(output, str) and isinstance(operations, list)

    report: list[dict] = []
    contributions: list[str] = []
    for index, op in enumerate(operations):
        entry, contribution = _check_operation(index, op, by_id)
        report.append(entry)
        if contribution is not None:
            contributions.append(contribution)

    failed = [e for e in report if e["status"] == FAILED]
    record_valid = not any(
        entry["status"] == FAILED and entry["method"] == "structure"
        for entry in report
    )

    reconstruction_ok = strip_whitespace("".join(contributions)) == strip_whitespace(output)

    reconstruction_entry = {
        "ok": reconstruction_ok,
        "method": "whitespace_insensitive_exact_match",
        "detail": (
            "Every character of the output traces to a declared operation."
            if reconstruction_ok
            else "The output does not match the text the operations account for. "
                 "Something was inserted, dropped or altered outside the log."
        ),
    }
    if not reconstruction_ok:
        reconstruction_entry["reconstructed"] = normalise_whitespace(" ".join(contributions))
        reconstruction_entry["submitted"] = normalise_whitespace(output)

    accepted = not failed and reconstruction_ok
    unverified_indexes = [
        entry["index"] for entry in report if entry["status"] == UNVERIFIED
    ]

    return {
        "contract": contract_record(),
        "status": "accepted" if accepted else "rejected",
        "assessment": assessment_record(
            mechanical_status="passed" if accepted else "failed",
            record_validation="passed" if record_valid else "failed",
            unverified_indexes=unverified_indexes,
            human_review="required" if accepted else "not_applicable",
            mechanical_detail=(
                "Source spans resolved and the candidate reconstruction matched."
                if accepted
                else "At least one operation or the candidate reconstruction failed."
            ),
        ),
        "declaration": _declaration(report, reconstruction_ok),
        "output": output,
        "output_context": output_context,
        "reconstruction": reconstruction_entry,
        "operations": report,
        "summary": {
            "total": len(report),
            "verified": sum(1 for e in report if e["status"] == VERIFIED),
            "unverified": sum(1 for e in report if e["status"] == UNVERIFIED),
            "failed": len(failed),
        },
        "sources": [{"id": p["id"], "source": p.get("source")} for p in passages],
        "note": (
            "Mechanical source-wording checks passed only where reported. "
            "Unverified operations are recorded claims, agent support was not "
            "assessed, and human review of meaning remains required."
        ),
    }

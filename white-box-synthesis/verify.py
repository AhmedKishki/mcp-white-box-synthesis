"""Verification logic for white-box-synthesis.

Deliberately free of MCP, network and model dependencies so it can be tested
directly.

What this module guarantees
---------------------------
The property under verification is *human-ness*, not meaning. Meaning is the
human editor's job. This module only certifies that every character of the
submitted output is either verbatim human text from a source passage, or the
product of a declared, bounded transformation of one.

Consequences of that framing:

- COPY only ever reproduces human text, so resolving the span *is* the check.
- DELETE and ORDER remove or move human text. Neither can introduce machine
  text, so both are legal by construction and need no semantic check. They
  are recorded for the human's audit, not verified.
- INFLECT and NORMALISE alter characters. They are the only places machine
  text can enter, so they are the only operations that will ever need real
  verification. In v0 they are logged as unverified.
"""

from __future__ import annotations

import re
from typing import Any

_WHITESPACE = re.compile(r"\s+")

CONTENT_OPS = frozenset({"COPY", "INFLECT", "NORMALISE"})
SILENT_OPS = frozenset({"DELETE", "ORDER"})
KNOWN_OPS = CONTENT_OPS | SILENT_OPS

INFLECT_AXES = frozenset({"tense", "number", "case", "article", "pronoun"})

VERIFIED = "verified"
UNVERIFIED = "unverified"
FAILED = "failed"

# The six typed gaps from the skill. A gap is a successful outcome.
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
    """Collapse every run of whitespace to one space and strip the ends.

    Used for readable reporting, not for the authoritative comparison.
    """
    return _WHITESPACE.sub(" ", text).strip()


def strip_whitespace(text: str) -> str:
    """Remove every whitespace character.

    This is the authoritative form for the reconstruction check. Whitespace is
    not content, so spacing is left entirely to the agent: it can join spans
    with a space, without one, or across a paragraph break, and none of those
    can introduce machine text. Every other character difference still fails.

    The cost is that a run-together join like "theunion" passes. That is a
    typo rather than a human-ness violation, and it belongs to the human's
    proofing pass.
    """
    return _WHITESPACE.sub("", text)


def locate(haystack: str, needle: str, occurrence: int) -> tuple[int, int] | None:
    """Return the (start, end) offsets of the nth occurrence of needle.

    Occurrences are counted from position 1, and overlapping matches count.
    Returns None if there is no such occurrence.
    """
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
    """Verify one operation.

    Returns the report entry and the text this operation contributes to the
    output, or None when it contributes nothing.
    """
    if not isinstance(op, dict):
        return _entry(index, "?", FAILED, "structure", "Operation is not an object."), None

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

    if not isinstance(passage_id, str) or not isinstance(text, str):
        return _entry(
            index, op_type, FAILED, "structure",
            "Operation needs a string passage_id and a string text.",
        ), None

    if not isinstance(occurrence, int) or isinstance(occurrence, bool):
        return _entry(
            index, op_type, FAILED, "structure",
            "occurrence must be an integer.",
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
        return _entry(
            index, op_type, VERIFIED, "legal_by_construction",
            "Removes or reorders human text, so it cannot introduce machine "
            "text. Recorded for audit, not checked.",
            note=note, **common,
        ), None

    # INFLECT and NORMALISE both alter characters.
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
    """Basis codes are written A4, not src:A4."""
    return passage_id[4:] if passage_id.startswith("src:") else passage_id


def _declaration(report: list[dict], reconstruction_ok: bool) -> dict:
    """Derive the compact provenance declaration mechanically.

    Field values come from the provenance contract. Nothing here is a
    judgment call: each field falls out of what was actually checked.
    """
    content = [e for e in report if e["type"] in CONTENT_OPS]
    used = [e for e in report if e.get("passage_id") and e["status"] != FAILED]

    basis: list[str] = []
    for entry in used:
        code = _basis_code(entry["passage_id"])
        if code not in basis:
            basis.append(code)

    blocked = any(e["status"] == FAILED for e in report) or not reconstruction_ok
    altering = [e for e in content if e["type"] != "COPY"]
    passage_ids = {e["passage_id"] for e in content}

    if blocked:
        # An original, location or operation could not be established.
        provenance = "Unverified"
        human_wording = "Unverified"
        method = "white-box synthesis"
    else:
        if altering:
            # INFLECT and NORMALISE are logged, not checked, so the
            # reconstruction test is incomplete for them.
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
    gap_type = gap.get("type")
    if gap_type not in GAP_TYPES:
        return f"gap type must be one of {sorted(GAP_TYPES)}."
    missing = [f for f in GAP_FIELDS if not gap.get(f)]
    if missing:
        return f"gap is missing required field(s): {', '.join(missing)}."
    return None


def verify(
    passages: list[dict],
    output_context: str,
    candidate: dict | None = None,
    gap: dict | None = None,
) -> dict:
    """Verify one submitted derivation, or record a declared gap."""
    if (candidate is None) == (gap is None):
        return {
            "status": "rejected",
            "error": "Submit exactly one of candidate or gap.",
        }

    if not isinstance(passages, list) or not passages:
        return {"status": "rejected", "error": "At least one passage is required."}

    by_id: dict[str, dict] = {}
    for passage in passages:
        if not isinstance(passage, dict):
            return {"status": "rejected", "error": "Each passage must be an object."}
        pid, ptext = passage.get("id"), passage.get("text")
        if not isinstance(pid, str) or not isinstance(ptext, str):
            return {
                "status": "rejected",
                "error": "Each passage needs a string id and a string text.",
            }
        if pid in by_id:
            return {"status": "rejected", "error": f"Duplicate passage id {pid!r}."}
        by_id[pid] = passage

    if gap is not None:
        problem = _check_gap(gap)
        if problem:
            return {"status": "rejected", "error": problem}
        return {
            "status": "gap",
            "output_context": output_context,
            "gap": gap,
            "sources": [
                {"id": p["id"], "source": p.get("source")} for p in passages
            ],
        }

    operations = candidate.get("operations")
    output = candidate.get("output")
    if not isinstance(output, str) or not isinstance(operations, list):
        return {
            "status": "rejected",
            "error": "candidate needs a string output and a list of operations.",
        }

    report: list[dict] = []
    contributions: list[str] = []
    for index, op in enumerate(operations):
        entry, contribution = _check_operation(index, op, by_id)
        report.append(entry)
        if contribution is not None:
            contributions.append(contribution)

    failed = [e for e in report if e["status"] == FAILED]

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

    return {
        "status": "accepted" if accepted else "rejected",
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
            "Human-ness is verified, meaning is not. Unverified operations are "
            "recorded claims, not checked facts. Proof the meaning yourself."
        ),
    }

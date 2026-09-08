"""Execute source-wording operations."""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any

from .verify import INFLECT_AXES, locate

SCHEMA_VERSION = "2.0"
SEPARATORS = {"none": "", "space": " ", "paragraph": "\n\n"}
CONTENT_OPS = {"COPY", "INFLECT", "NORMALISE"}


class InvalidRecord(ValueError):
    pass


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise InvalidRecord(detail)


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def record(value: Any, label: str) -> dict:
    require(isinstance(value, dict), f"{label} must be an object.")
    require(
        value.get("schema_version", SCHEMA_VERSION) == SCHEMA_VERSION,
        f"{label}.schema_version must be {SCHEMA_VERSION!r}.",
    )
    return value


def word_char(char: str) -> bool:
    return char.isalnum() or char == "_" or unicodedata.category(char).startswith("M")


def splits_word(text: str, offset: int) -> bool:
    if not 0 < offset < len(text):
        return False
    if word_char(text[offset - 1]) and word_char(text[offset]):
        return True
    for position in (offset - 1, offset):
        if (
            text[position] in "'’-"
            and 0 < position < len(text) - 1
            and word_char(text[position - 1])
            and word_char(text[position + 1])
        ):
            return True
    return False


def source_span(value: Any, fragments: dict[str, dict], label: str) -> dict:
    value = record(value, label)
    fragment_id, text = value.get("fragment_id"), value.get("text")
    occurrence = value.get("occurrence", 1)
    require(
        nonempty(fragment_id) and nonempty(text),
        f"{label} needs fragment_id and non-empty text.",
    )
    require(
        type(occurrence) is int and occurrence > 0,
        f"{label}.occurrence must be a positive integer.",
    )
    require(fragment_id in fragments, f"{label} references an unknown fragment.")
    fragment = fragments[fragment_id]
    span = locate(fragment["text"], text, occurrence)
    require(span is not None, f"{label}.text does not resolve at that occurrence.")
    start, end = span
    require(
        not splits_word(fragment["text"], start)
        and not splits_word(fragment["text"], end),
        f"{label}.text splits a source word.",
    )
    return {
        "fragment_id": fragment_id,
        "text": text,
        "occurrence": occurrence,
        "span": [start, end],
        "source": fragment.get("source"),
        "locator": fragment.get("locator", "full"),
        "permitted_use": fragment.get("permitted_use", "wording"),
    }


def protected(fragment: dict, spans: list[list[int]]) -> bool:
    return fragment.get("protected", False) or any(
        start < protected_end and protected_start < end
        for start, end in spans
        for protected_start, protected_end in fragment["_protected_ranges"]
    )


def slice_spans(spans: list[list[int]], start: int, end: int) -> list[list[int]]:
    result, cursor = [], 0
    for left, right in spans:
        length = right - left
        overlap_start, overlap_end = max(start, cursor), min(end, cursor + length)
        if overlap_start < overlap_end:
            result.append([left + overlap_start - cursor, left + overlap_end - cursor])
        cursor += length
    return result


def assemble(parts: list[dict]) -> str:
    output = ""
    for part in parts:
        text = part["text"]
        if not text:
            part["output_span"] = [len(output), len(output)]
            continue
        separator = SEPARATORS[part["separator"]] if output else ""
        require(
            not (output and not separator and splits_word(output + text, len(output))),
            "Assembly would merge adjacent words; use a space or paragraph separator.",
        )
        output += separator
        start = len(output)
        output += text
        part["output_span"] = [start, len(output)]
    return output


def separator(value: dict, default: str) -> str:
    choice = value.get("separator", default)
    require(
        isinstance(choice, str) and choice in SEPARATORS,
        "separator must be none, space or paragraph.",
    )
    return choice


def normalisation_units(text: str) -> list[str]:
    text = text.casefold()
    units, word = [], ""
    for index, char in enumerate(text):
        internal_quote = (
            char in "'’"
            and 0 < index < len(text) - 1
            and word_char(text[index - 1])
            and word_char(text[index + 1])
        )
        if word_char(char) or internal_quote:
            word += char
            continue
        if word:
            units.append(word)
            word = ""
        if not char.isspace() and not unicodedata.category(char).startswith("P"):
            units.append(char)
    if word:
        units.append(word)
    return units


def transformation(operation: dict, origin: dict, constraints: dict) -> str:
    output = operation.get("output_text")
    require(nonempty(output), "Transformation needs a non-empty output_text.")
    if operation["type"] == "INFLECT":
        axes = operation.get("axes", [operation.get("axis")])
        require(
            isinstance(axes, list)
            and bool(axes)
            and all(isinstance(axis, str) and axis in INFLECT_AXES for axis in axes),
            f"INFLECT needs axes from {sorted(INFLECT_AXES)}.",
        )
        require(len(set(axes)) == len(axes), "INFLECT axes must be unique.")
    if origin["text"] == output:
        return "verified"
    if operation["type"] == "NORMALISE":
        if normalisation_units(origin["text"]) == normalisation_units(output):
            return "verified"
        rewritten = origin["text"]
        for pair in constraints.get("normalisations", []):
            rewritten = re.sub(
                r"(?<!\w)" + re.escape(pair["from"]) + r"(?!\w)",
                lambda match, replacement=pair["to"]: replacement,
                rewritten,
            )
        require(
            normalisation_units(rewritten) == normalisation_units(output),
            "NORMALISE changes vocabulary or word boundaries outside declared spelling pairs.",
        )
    return "unverified"


def execute(operations: Any, fragments: dict[str, dict], constraints: dict) -> dict:
    require(
        isinstance(operations, list) and bool(operations),
        "operations must be a non-empty list.",
    )
    pieces, order, trail = {}, [], []
    for index, value in enumerate(operations):
        operation = record(value, f"operations[{index}]")
        kind = operation.get("type")
        require(
            isinstance(kind, str) and kind in CONTENT_OPS | {"DELETE", "ORDER"},
            "Unknown operation type.",
        )
        require(
            not (
                {
                    "assessment",
                    "preserves",
                    "equivalence",
                    "duplicate_of",
                    "left_operation",
                    "right_operation",
                }
                & operation.keys()
            ),
            "Legacy operation fields are unsupported; use schema 2 operations and diagnostics.",
        )
        if kind in CONTENT_OPS:
            origin = source_span(operation, fragments, f"operations[{index}]")
            require(
                origin["permitted_use"] != "framework_check",
                "Framework-only fragments cannot supply output wording.",
            )
            text, status = origin["text"], "verified"
            if kind != "COPY":
                require(
                    not protected(fragments[origin["fragment_id"]], [origin["span"]])
                    or operation.get("output_text") == text,
                    "Cannot transform a protected source span.",
                )
                status = transformation(operation, origin, constraints)
                text = operation["output_text"]
            piece = {
                "operation_index": index,
                "text": text,
                "original": origin,
                "source_spans": [origin["span"]] if text == origin["text"] else None,
                "separator": separator(operation, "space"),
                "status": status,
            }
            pieces[index] = piece
            order.append(index)
            entry = {
                "index": index,
                "type": kind,
                **origin,
                "output_text": text,
                "separator": piece["separator"],
                "status": status,
            }
            if kind == "INFLECT":
                entry["axes"] = operation.get("axes", [operation.get("axis")])
            if kind == "NORMALISE" and status == "unverified":
                entry["declared_normalisations"] = deepcopy(
                    constraints.get("normalisations", [])
                )
            trail.append(entry)
        elif kind == "ORDER":
            permutation = operation.get("order")
            require(
                isinstance(permutation, list)
                and bool(permutation)
                and all(type(target) is int for target in permutation),
                "ORDER needs a list of content operation indexes.",
            )
            require(
                len(permutation) == len(pieces) and set(permutation) == set(pieces),
                "ORDER must include every emitted content operation exactly once.",
            )
            trail.append(
                {
                    "index": index,
                    "type": kind,
                    "before": order[:],
                    "order": permutation[:],
                    "status": "verified",
                }
            )
            order = permutation[:]
        else:
            target, text = operation.get("target"), operation.get("text")
            occurrence = operation.get("occurrence", 1)
            require(
                type(target) is int and target in pieces,
                "DELETE must target an earlier content operation.",
            )
            require(
                nonempty(text) and type(occurrence) is int and occurrence > 0,
                "DELETE needs non-empty text and a positive occurrence.",
            )
            piece = pieces[target]
            require(
                piece["source_spans"] is not None,
                "DELETE requires unchanged source spans; use separate source spans for transformed wording.",
            )
            match = locate(piece["text"], text, occurrence)
            require(
                match is not None, "DELETE text does not resolve in the current target."
            )
            start, end = match
            require(
                not splits_word(piece["text"], start)
                and not splits_word(piece["text"], end),
                "DELETE cannot split a source word.",
            )
            removed = slice_spans(piece["source_spans"], start, end)
            require(
                not protected(fragments[piece["original"]["fragment_id"]], removed),
                "Cannot delete protected source text.",
            )
            before = piece["text"]
            require(
                not splits_word(before[:start] + before[end:], start),
                "DELETE would merge adjacent words.",
            )
            piece["text"] = before[:start] + before[end:]
            piece["source_spans"] = slice_spans(
                piece["source_spans"], 0, start
            ) + slice_spans(piece["source_spans"], end, len(before))
            trail.append(
                {
                    "index": index,
                    "type": kind,
                    "target": target,
                    "fragment_id": piece["original"]["fragment_id"],
                    "text": text,
                    "occurrence": occurrence,
                    "span": [start, end],
                    "source_spans": removed,
                    "before": before,
                    "after": piece["text"],
                    "status": "verified",
                }
            )
    final_pieces = [pieces[index] for index in order]
    output = assemble(final_pieces)
    require(
        nonempty(output),
        "The argument produces no wording; submit a gap or revise the plan.",
    )
    return {"result_span": output, "operations": trail, "pieces": final_pieces}

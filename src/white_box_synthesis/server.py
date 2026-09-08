"""MCP adapters for white-box synthesis."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .synthesis import synthesise as _synthesise
from .verify import verify as _verify

mcp = MCPServer("white-box-synthesis", version="0.2.0")

PROCESS_PROMPT = """\
Construct one approved passage with `synthesise`. Match its ordered arguments
to approved human-authored fragments. Submit one operations record per argument.
Source wording must come from complete words, phrases or clauses; do not write
new prose or assemble words from source characters.

COPY emits an exact span using fragment_id, text and optional occurrence.
INFLECT uses the same source fields, output_text and axes (tense, number, case,
article or pronoun). NORMALISE uses the source fields and output_text for case,
punctuation or spelling. Content operations have an optional separator: none,
space or paragraph. Spacing follows each piece through ORDER; the first emitted
piece has no leading separator. DELETE uses target (an unchanged piece's operation
index), text and optional occurrence to remove wording. ORDER uses order, a permutation of all emitted
content operation indexes, to set their final order. Indexes are zero-based.

Submit candidate.records with argument_id and operations. The server derives
result_span and passage; supplied values are exact assertions. Unchecked edits
remain Unverified and block selection. Provenance describes wording lineage;
it does not establish preserved meaning or causality. Human review is required.

If construction is blocked, report a typed gap with passage_id, argument_id,
missing_requirement, authoritative_owner, question and resolution_paths. Types:
Missing user wording, Missing evidence, Unsupported connection, Source-context
ambiguity, Arc inconsistency, Constraint conflict.

Record observed causal gaps or source contradictions separately in optional
candidate.diagnostics: type (causal_gap or contradiction), argument_id, detail,
and basis (exact fragment_id, text and optional occurrence references). These
are agent findings; the core validates their references without assessing them.
"""


@mcp.prompt(name="white_box_synthesis_process")
def white_box_synthesis_process() -> str:
    """Minimum white-box synthesis rules."""
    return PROCESS_PROMPT


@mcp.tool()
def synthesise(
    passage_plan: dict[str, Any],
    fragments: list[dict[str, Any]],
    constraints: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    gap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one passage's construction and report wording provenance.

    Schema 2.0: passage_plan needs passage_id, claim and ordered arguments
    [{id, claim}]; relations are optional metadata. Fragments need id and text;
    source, locator, context and permitted_use are optional. Omit candidate and
    gap for an agent work request. Constraints are passed to the calling agent.

    candidate.records contains {argument_id, operations, separator?}; result_span
    and candidate.passage are optional exact assertions. COPY uses fragment_id,
    text, occurrence? and separator?. INFLECT adds output_text and axes; NORMALISE
    adds output_text. DELETE uses target (unchanged piece index), text, occurrence?.
    ORDER uses order (a permutation of all content operation indexes). Separators
    are none, space or paragraph; space is the default and the leading separator
    is omitted. Offsets are zero-based Unicode code points with exclusive ends;
    piece output spans are relative to their argument, argument spans to passage.

    A gap needs type, passage_id, argument_id, missing_requirement,
    authoritative_owner, question and resolution_paths. Optional diagnostics
    contain type (causal_gap or contradiction), argument_id, detail and basis
    [{fragment_id, text, occurrence?}]. Meaning and causality are not assessed.
    """
    return _synthesise(
        passage_plan,
        fragments,
        constraints=constraints,
        candidate=candidate,
        gap=gap,
    )


@mcp.tool()
def verify_synthesis(
    passages: list[dict[str, Any]],
    output_context: str,
    candidate: dict[str, Any] | None = None,
    gap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the legacy flat derivation check without semantic support checks."""
    return _verify(passages, output_context, candidate=candidate, gap=gap)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

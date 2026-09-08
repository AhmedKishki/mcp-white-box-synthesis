"""MCP server for white-box-synthesis.

A thin transport layer. All verification lives in verify.py.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .verify import verify as _verify

mcp = MCPServer("white-box-synthesis", version="0.1.0")

PROCESS_PROMPT = """\
You are performing white-box-synthesis: producing one output passage from N
human-written input passages, using only transformations that preserve the
human-ness of the text.

Read this carefully, because it is the point of the whole exercise. The
verifier does not check meaning. Meaning is the human editor's job, and they
will proof it after you. What the verifier checks is that every character you
output is either verbatim human text from a source passage, or the product of
a declared, bounded transformation of one. Nothing you write may originate
with you.

You will be given source passages, each with an id and a citation label, and
an output context describing what your output should support.

Five operations are licensed.

COPY
    Reproduce an exact, contiguous, unmodified span. Verified exactly.

DELETE
    Omit a span. You do not need to justify this semantically. Removing human
    text cannot introduce machine text, so deletion is free. Record it anyway,
    with a note, because the human proofing your output needs to see what was
    cut.

ORDER
    Arrange spans. Also free, for the same reason. The order of your
    operations list already determines the order of the output, so ORDER is
    recorded as an annotation rather than checked.

INFLECT
    Change only tense, grammatical number, grammatical case, article, or an
    unambiguous pronoun. Declare which axis. "workers are" to "a worker is" is
    legal. "may" to "will" is not: that is modality, not inflection.

NORMALISE
    Meaning-neutral spelling, capitalisation or punctuation changes only.
    Never substitute vocabulary.

INFLECT and NORMALISE are the two operations that alter characters, so they
are the two places machine text could enter. Right now the verifier logs them
without checking them. Be strict with yourself there, since nothing else will
be.

Punctuation does not travel for free. If a source has a comma where your
output needs a full stop, that is a NORMALISE operation and you must declare
it. It cannot arrive through the join. Spacing and paragraph breaks are the
exception: those are yours to choose and are not checked.

For every operation give the passage id, the exact source text quoted
verbatim, and which occurrence of that text within the passage you mean
(1 for the first). The verifier locates the span itself and will reject you if
your quotation is not exactly right.

If no legal derivation supports the output context, do not force one. Report a
typed gap instead. A gap is a successful outcome, not a failure. Use exactly
one of these types:

    Missing user wording, Missing evidence, Unsupported connection,
    Source-context ambiguity, Arc inconsistency, Constraint conflict

and give all six fields: passage_id, argument_id, missing_requirement,
authoritative_owner, one focused question, and allowed resolution_paths.

Every derivation returns a compact provenance declaration, derived
mechanically from what was actually checked. Note what this means right now:
because INFLECT and NORMALISE are logged rather than checked, any derivation
using either declares "Human wording: Unverified" and blocks selection. Only
COPY, DELETE and ORDER can reach 100%. That is not a bug you should work
around by mislabelling operations. It is the verifier being honest about what
it has confirmed.

Submit through the verify_synthesis tool.
"""


@mcp.prompt(name="white_box_synthesis_process")
def white_box_synthesis_process() -> str:
    """The white-box-synthesis process. Read before attempting a synthesis."""
    return PROCESS_PROMPT


@mcp.tool()
def verify_synthesis(
    passages: list[dict[str, Any]],
    output_context: str,
    candidate: dict[str, Any] | None = None,
    gap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify a white-box-synthesis derivation, or record a declared gap.

    Checks that every character of the output traces to a declared operation on
    a declared source span. Does not check meaning: that is the human's job.

    Args:
        passages: Source passages. Each needs `id` and `text`, and should carry
            a `source` citation label, which flows through to the report.
        output_context: What the output passage is meant to support.
        candidate: `{"output": str, "operations": [...]}`. Each operation needs
            `type` (COPY, INFLECT, NORMALISE, DELETE or ORDER), `passage_id`,
            `text` quoted verbatim from that passage, and `occurrence`
            (1-indexed). INFLECT and NORMALISE also need `output_text`, and
            INFLECT needs `axis` (tense, number, case, article or pronoun).
            DELETE and ORDER accept an optional `note`.
        gap: A typed gap when no legal derivation exists. Needs `type` (one of
            the six gap types), `passage_id`, `argument_id`,
            `missing_requirement`, `authoritative_owner`, `question` and
            `resolution_paths`. Submit exactly one of `candidate` or `gap`.

    Returns:
        A report with an overall status of accepted, rejected or gap, a
        per-operation verdict of verified, unverified or failed, the
        reconstruction result, counts, and a compact provenance declaration.
        Operations marked `unverified` are recorded claims rather than checked
        facts, and any derivation containing one declares `Human wording:
        Unverified`.
    """
    return _verify(passages, output_context, candidate=candidate, gap=gap)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

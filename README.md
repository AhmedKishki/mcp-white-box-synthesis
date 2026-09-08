# white-box-synthesis

An MCP server for constructing passages from approved human-authored fragments.
The core preserves human wording lineage through recorded edits. Meaning and
causality need separate review.

It uses the five operations from the
[white-box synthesis reference](https://github.com/AhmedKishki/agent-skills/blob/main/skills/draft-writing/references/white-box-synthesis.md).

## Core workflow

`synthesise` takes a passage plan, ordered arguments, approved fragments, and optional constraints. Without a candidate or gap, it returns `needs_agent`. The calling agent submits one construction record per argument using COPY, INFLECT, NORMALISE, ORDER, and DELETE, or reports a typed gap.

The server executes those operations and returns the passage and provenance. `complete` means construction succeeded. Checked wording is labelled `100%`; unchecked transformations are `Unverified` and block selection. These labels describe derivation from the supplied fragments, whose authorship is assumed. Human review remains required.

Case and punctuation changes are checked. Nontrivial inflections and declared spelling replacements remain unverified until narrower rules are implemented.

Optional agent diagnostics record causal gaps and source contradictions with exact basis spans. The core does not detect them or certify preserved meaning.

Minimal candidate request:

```json
{
  "passage_plan": {
    "passage_id": "p1", "claim": "Workers organise.",
    "arguments": [{"id": "a1", "claim": "Workers organise."}]
  },
  "fragments": [{"id": "user-1", "text": "Workers organise."}],
  "candidate": {"records": [{
    "argument_id": "a1",
    "operations": [{
      "type": "COPY", "fragment_id": "user-1", "text": "Workers organise."
    }]
  }]}
}
```

The synthesis record schema is `2.0`; explicit `1.0` records are rejected. DELETE now edits a target piece; ORDER applies a permutation. Semantic support fields are replaced by optional diagnostics.`verify_synthesis` retains its legacy `1.0` flat derivation contract.

## Run

```bash
uvx --from git+https://github.com/AhmedKishki/mcp-white-box-synthesis white-box-synthesis
```

For local development:

```bash
uvx --from . white-box-synthesis
python3 tests/test_synthesis.py
python3 tests/test_verify.py
```

See [ROADMAP.md](ROADMAP.md) for the remaining work.

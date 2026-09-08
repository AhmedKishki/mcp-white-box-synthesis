# white-box-synthesis

An MCP server that verifies a synthesised passage preserves the **human-ness**
of its source passages.

## What it does and does not do

The agent does the synthesis. The server checks the work. It holds no model, no
API key and no semantic judgment.

The property under verification is human-ness, not meaning. **Meaning is yours
to proof.** What the server certifies is that every character of the output is
either verbatim human text from a source passage, or the product of a declared,
bounded transformation of one.

That framing decides which operations need checking:

| Operation | What it does to the text | v0 status |
|---|---|---|
| COPY | reproduces human text | verified exactly |
| DELETE | removes human text | legal by construction, logged for your audit |
| ORDER | moves human text | legal by construction, logged |
| INFLECT | alters characters | logged, unverified |
| NORMALISE | alters characters | logged, unverified |

Removing and moving cannot introduce machine text, so they are free. INFLECT and
NORMALISE are the only places machine text can enter, so they are the only
operations that will ever need real verification.

**This diverges deliberately from the [`draft-writing` skill](https://github.com/AhmedKishki/agent-skills/blob/main/skills/draft-writing/references/white-box-synthesis.md)**, whose DELETE
removes repetition only when subject, claim, scope, modality and qualification
are identical, and whose ORDER requires an approved original establishing the
relation. Both conditions preserve *meaning*, which is not this server's job.
The skill needs updating to match. The two live in separate repositories and
can drift, so treat the skill as the definition of the operations and this
README as the record of where the verifier knowingly departs from it.

## The two checks that carry v0

1. **COPY resolution.** The quoted span must exist in the named passage at the
   stated occurrence, exactly.
2. **Reconstruction.** The text of all content-producing operations, joined in
   list order, must match the submitted output. Whitespace is ignored, because
   spacing is not content. Every other character difference fails.

Together these mean an invented word cannot pass. Punctuation does not travel
for free either: a comma becoming a full stop is a NORMALISE operation and must
be declared.

## Report

Each operation returns `verified`, `unverified` or `failed`. Citation labels on
passages flow through to the report for footnoting. One failure rejects the
whole derivation, because the report certifies a derivation rather than a set of
parts.

### Provenance declaration

Every derivation returns the compact declaration from the provenance contract,
derived mechanically:

```
**Provenance:** Mixed · Human wording: 100% · Method: white-box synthesis · Basis: A4, user-21
```

`Basis` is deduplicated in first-use order with the `src:` prefix stripped.
`Provenance` is `Human` for a single unaltered span, `Mixed` for several,
`Unverified` when anything failed.

**The honest consequence of v0.** The contract allows `Human wording: 100%` only
when every span passes the reconstruction test, which requires a sequence of
*permitted* operations. v0 logs INFLECT and NORMALISE without checking that they
are legal. So any derivation using either declares `Human wording: Unverified`
and sets `blocks_selection`. Only COPY, DELETE and ORDER reach 100%.

That is the roadmap with teeth: until the NORMALISE whitelist and INFLECT
morphology exist, no passage using them can be declared clean.

### Typed gaps

A gap is a successful outcome. It must carry one of the six types from the
skill (`Missing user wording`, `Missing evidence`, `Unsupported connection`,
`Source-context ambiguity`, `Arc inconsistency`, `Constraint conflict`) and all
six fields: `passage_id`, `argument_id`, `missing_requirement`,
`authoritative_owner`, `question`, `resolution_paths`. Untyped gaps are
rejected.

## Install

This is a working MCP server: one tool, `verify_synthesis`, and one prompt,
`white_box_synthesis_process`. It speaks stdio, so the client launches it as a
subprocess. Nothing is hosted.

Installation goes straight from this repository. There is no clone step and no
PyPI release. [uv](https://docs.astral.sh/uv/) does the work:

```bash
uvx --from git+https://github.com/AhmedKishki/mcp-white-box-synthesis white-box-synthesis
```

Note the two names differ and both are needed. `--from` takes the **repository**
(`mcp-white-box-synthesis`); the trailing argument is the **console script**
(`white-box-synthesis`). Repeating the repo name there fails with an executable
not found.

It will sit silently waiting for JSON-RPC on stdin. That is correct. Ctrl-C out.

Pin a tag for reproducibility:

```bash
uvx --from git+https://github.com/AhmedKishki/mcp-white-box-synthesis@v0.1.0 white-box-synthesis
```

### Claude Code

stdio is the default transport, so no transport flag is needed. Options go
before the name, and `--` separates them from the launch command:

```bash
claude mcp add white-box-synthesis \
  -- uvx --from git+https://github.com/AhmedKishki/mcp-white-box-synthesis white-box-synthesis
```

Scope defaults to local. `--scope project` writes a committable `.mcp.json`,
`--scope user` makes it available across projects. Confirm with `/mcp`.

### Cline, Claude Desktop, Kimi Code CLI, anything JSON-configured

```json
{
  "mcpServers": {
    "white-box-synthesis": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/AhmedKishki/mcp-white-box-synthesis",
        "white-box-synthesis"
      ]
    }
  }
}
```

### Releasing

Bump `version` in `pyproject.toml` and the `MCPServer(...)` call in
`server.py`, then tag:

```bash
git tag v0.1.1 && git push --tags
```

Anyone pinning a tag gets that build. Anyone on the bare URL gets `main`.

### Local development

```bash
git clone https://github.com/AhmedKishki/mcp-white-box-synthesis
cd mcp-white-box-synthesis
uvx --from . white-box-synthesis
```

### Verify it handshakes

```bash
printf '%s\n' \
'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}' \
'{"jsonrpc":"2.0","method":"notifications/initialized"}' \
'{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
| uvx --from . white-box-synthesis
```

### Four things that will bite you

- **Use absolute paths.** The client spawns the server from its own working
  directory, not yours.
- **`uvx` must be on the PATH the client sees.** GUI apps often do not inherit
  your shell PATH. If the server fails to start, replace `uvx` with the full
  path from `which uvx`.
- **Never print to stdout.** On stdio transport, stdout is the protocol
  channel. Any stray `print()` corrupts the stream. Log to stderr.
- **`uvx` caches the build.** During local development your edits will not
  appear until you run `uv cache clean`, or install editable with
  `uv tool install --editable .`. The same cache means an unpinned git install
  will not pick up new commits immediately either.

## Tests

```bash
python3 tests/test_verify.py
```

No dependencies. `verify.py` is deliberately free of MCP, network and model
imports.

## Backlog

Ordered by dependency weight. Testing decides what actually comes forward.

1. **NORMALISE whitelist.** A literal dictionary of substitution pairs, no
   dependencies. Seed it from what actually appears in testing. Must be
   lexicalised, not regex: an `-ize` to `-ise` rule turns *size* into *sise*.
2. **INFLECT morphology.** Needs spaCy. Covers tense, number, case, article.
   The pronoun sub-case is separate: count agreement-filtered antecedent
   candidates in a local window.
3. **Connectors.** The skill requires that every word, including a function
   word inserted at a join, occurs in an approved fragment. So connectors are
   drawn from fragments rather than invented, which makes them a constrained
   COPY and mechanically checkable.

## Not yet built, and they change the input schema

- **Argument structure.** The skill's Record is one row per *argument* against a
  passage plan with a passage claim and ordered argument IDs. The flat
  operations list cannot produce that table.
- **Protected regions.** Direct quotations, code, URLs, titles, citation data
  and proper names must stay exact, and INFLECT and NORMALISE apply only to
  unquoted output. Mechanical once regions are marked. Nothing implements it.
- **Locators.** The skill addresses fragments by code plus `paragraph N` or
  `lines N-M`, with exact quotations only to resolve ambiguity. This server uses
  occurrence-numbered quotations instead.

Dropped from the original design once the human-ness framing settled: the
DELETE duplicate-overlap check, the DELETE irrelevance embedding check, and the
ORDER marker lexicon. All three were checking meaning, which is not this
server's job.

## Known gap

Because whitespace is ignored, a run-together join like `theunion` passes. That
is a typo rather than a human-ness violation, and it belongs to your proofing
pass.

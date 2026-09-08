import sys
sys.path.insert(0, "src")

from white_box_synthesis.verify import verify, locate, normalise_whitespace

PASSAGES = [
    {
        "id": "P1",
        "source": "Smith 2019, p.42",
        "text": "The union delegation met twice. The union delegation met with "
                "management on Tuesday, and again on Thursday.",
    },
    {
        "id": "P2",
        "source": "Jones 2021, p.7",
        "text": "Wages were frozen for three years. Inflation ran at six per cent.",
    },
]

CONTEXT = "What happened in the Tuesday negotiations."

fails = 0


def check(label, condition):
    global fails
    print(("PASS  " if condition else "FAIL  ") + label)
    if not condition:
        fails += 1


# --- locate ---------------------------------------------------------------
check("locate finds 1st occurrence", locate("a b a b", "a", 1) == (0, 1))
check("locate finds 2nd occurrence", locate("a b a b", "a", 2) == (4, 5))
check("locate returns None past the end", locate("a b", "a", 2) is None)
check("locate returns None when absent", locate("a b", "z", 1) is None)
check("whitespace collapses", normalise_whitespace(" a \n\n b  ") == "a b")

# --- a clean derivation ---------------------------------------------------
# Note the NORMALISE: P1 reads "on Tuesday, and again", so turning that comma
# into a full stop is a punctuation change and must be declared. It cannot
# arrive silently through the join.
ops = [
    {"type": "COPY", "passage_id": "P1",
     "text": "The union delegation met with management on Tuesday",
     "occurrence": 1},
    {"type": "NORMALISE", "passage_id": "P1", "text": ",", "occurrence": 1,
     "output_text": "."},
    {"type": "COPY", "passage_id": "P2",
     "text": "Wages were frozen for three years.", "occurrence": 1},
    {"type": "DELETE", "passage_id": "P1", "text": "The union delegation met twice.",
     "occurrence": 1, "note": "irrelevant to the context"},
]
out = ("The union delegation met with management on Tuesday. "
       "Wages were frozen for three years.")
r = verify(PASSAGES, CONTEXT, candidate={"output": out, "operations": ops})
check("clean derivation accepted", r["status"] == "accepted")
check("reconstruction ok", r["reconstruction"]["ok"])
check("delete is verified by construction",
      r["operations"][3]["status"] == "verified")
check("citation label flows through", r["operations"][0]["source"] == "Smith 2019, p.42")
check("summary counts", r["summary"] == {"total": 4, "verified": 3,
                                         "unverified": 1, "failed": 0})

# --- undeclared punctuation is caught ------------------------------------
r = verify(PASSAGES, CONTEXT, candidate={
    "output": out,
    "operations": [ops[0], ops[2]],
})
check("undeclared full stop rejected", r["status"] == "rejected")

# --- whitespace tolerance -------------------------------------------------
r = verify(PASSAGES, CONTEXT, candidate={
    "output": "The union delegation met with management on Tuesday.\n\n"
              "   Wages were frozen for three years.",
    "operations": ops[:3],
})
check("paragraph break and spacing tolerated", r["status"] == "accepted")

# --- smuggled word --------------------------------------------------------
r = verify(PASSAGES, CONTEXT, candidate={
    "output": "The union delegation angrily met with management on Tuesday",
    "operations": [ops[0]],
})
check("inserted word rejected", r["status"] == "rejected")
check("reconstruction flags it", r["reconstruction"]["ok"] is False)

# --- ambiguous span, wrong occurrence ------------------------------------
r = verify(PASSAGES, CONTEXT, candidate={
    "output": "x",
    "operations": [{"type": "COPY", "passage_id": "P1",
                    "text": "The union delegation met", "occurrence": 3}],
})
check("nonexistent occurrence fails", r["operations"][0]["status"] == "failed")
check("error names the real count",
      "appears 2 time(s)" in r["operations"][0]["detail"])

# --- text not present -----------------------------------------------------
r = verify(PASSAGES, CONTEXT, candidate={
    "output": "x",
    "operations": [{"type": "COPY", "passage_id": "P1",
                    "text": "never written anywhere", "occurrence": 1}],
})
check("absent text fails", r["operations"][0]["status"] == "failed")

# --- INFLECT is logged, not checked --------------------------------------
r = verify(PASSAGES, CONTEXT, candidate={
    "output": "A union delegation meets with management on Tuesday",
    "operations": [{
        "type": "INFLECT", "passage_id": "P1",
        "text": "The union delegation met with management on Tuesday",
        "occurrence": 1,
        "output_text": "A union delegation meets with management on Tuesday",
        "axis": "tense",
    }],
})
check("inflect accepted but unverified", r["status"] == "accepted")
check("inflect marked unverified", r["operations"][0]["status"] == "unverified")
check("unverified counted", r["summary"]["unverified"] == 1)

# --- INFLECT with a bad axis ---------------------------------------------
r = verify(PASSAGES, CONTEXT, candidate={
    "output": "x",
    "operations": [{"type": "INFLECT", "passage_id": "P2",
                    "text": "Wages were frozen", "occurrence": 1,
                    "output_text": "Wages will be frozen", "axis": "modality"}],
})
check("bad inflect axis rejected", r["operations"][0]["status"] == "failed")

# --- typed gaps -----------------------------------------------------------
GOOD_GAP = {
    "type": "Missing evidence",
    "passage_id": "1.1",
    "argument_id": "1.1.2",
    "missing_requirement": "A source describing the Thursday session.",
    "authoritative_owner": "user",
    "question": "Do you have a source for the Thursday meeting?",
    "resolution_paths": ["supply a source", "drop the Thursday clause"],
}
r = verify(PASSAGES, CONTEXT, gap=GOOD_GAP)
check("typed gap returns gap status", r["status"] == "gap")

r = verify(PASSAGES, CONTEXT, gap={**GOOD_GAP, "type": "Vibes"})
check("untyped gap rejected", r["status"] == "rejected")

r = verify(PASSAGES, CONTEXT, gap={k: v for k, v in GOOD_GAP.items()
                                   if k != "authoritative_owner"})
check("gap missing a required field rejected", r["status"] == "rejected")
check("error names the field",
      "authoritative_owner" in verify(
          PASSAGES, CONTEXT,
          gap={k: v for k, v in GOOD_GAP.items() if k != "authoritative_owner"}
      )["error"])

# --- provenance declaration ----------------------------------------------
r = verify(PASSAGES, CONTEXT, candidate={
    "output": "Wages were frozen for three years.",
    "operations": [{"type": "COPY", "passage_id": "P2",
                    "text": "Wages were frozen for three years.", "occurrence": 1}],
})
check("pure COPY is Human", r["declaration"]["provenance"] == "Human")
check("pure COPY is 100%", r["declaration"]["human_wording"] == "100%")
check("pure COPY does not block", r["declaration"]["blocks_selection"] is False)

r = verify(PASSAGES, CONTEXT, candidate={
    "output": "Wages are frozen for three years.",
    "operations": [{"type": "INFLECT", "passage_id": "P2",
                    "text": "Wages were frozen for three years.", "occurrence": 1,
                    "output_text": "Wages are frozen for three years.",
                    "axis": "tense"}],
})
check("unchecked INFLECT cannot claim 100%",
      r["declaration"]["human_wording"] == "Unverified")
check("unchecked INFLECT blocks selection",
      r["declaration"]["blocks_selection"] is True)

r = verify(PASSAGES, CONTEXT, candidate={
    "output": "The union delegation met twice. Wages were frozen for three years.",
    "operations": [
        {"type": "COPY", "passage_id": "P1",
         "text": "The union delegation met twice.", "occurrence": 1},
        {"type": "COPY", "passage_id": "P2",
         "text": "Wages were frozen for three years.", "occurrence": 1}],
})
check("multiple spans are Mixed", r["declaration"]["provenance"] == "Mixed")
check("basis is deduplicated in first-use order",
      r["declaration"]["basis"] == ["P1", "P2"])

r = verify(PASSAGES, CONTEXT, candidate={
    "output": "invented",
    "operations": [{"type": "COPY", "passage_id": "P1",
                    "text": "The union delegation met twice.", "occurrence": 1}],
})
check("failed reconstruction gives Unverified provenance",
      r["declaration"]["provenance"] == "Unverified")

check("src: prefix stripped from basis",
      verify([{"id": "src:A4", "source": "Smith", "text": "Wages fell."}], "pay",
             candidate={"output": "Wages fell.", "operations": [
                 {"type": "COPY", "passage_id": "src:A4", "text": "Wages fell.",
                  "occurrence": 1}]})["declaration"]["basis"] == ["A4"])

# --- structural guards ----------------------------------------------------
check("both candidate and gap rejected",
      verify(PASSAGES, CONTEXT, candidate={"output": "", "operations": []},
             gap={"reason": "r", "missing": "m"})["status"] == "rejected")
check("neither rejected", verify(PASSAGES, CONTEXT)["status"] == "rejected")
check("unknown passage fails",
      verify(PASSAGES, CONTEXT, candidate={"output": "x", "operations": [
          {"type": "COPY", "passage_id": "P9", "text": "a", "occurrence": 1}]}
      )["operations"][0]["status"] == "failed")
check("unknown op type fails",
      verify(PASSAGES, CONTEXT, candidate={"output": "x", "operations": [
          {"type": "PARAPHRASE", "passage_id": "P1", "text": "The", "occurrence": 1}]}
      )["operations"][0]["status"] == "failed")
check("duplicate passage ids rejected",
      verify([PASSAGES[0], PASSAGES[0]], CONTEXT,
             candidate={"output": "x", "operations": []})["status"] == "rejected")

print()
print("all passed" if fails == 0 else f"{fails} failing")
sys.exit(1 if fails else 0)

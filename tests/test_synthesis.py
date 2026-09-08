"""Run with: python3 tests/test_synthesis.py"""

import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from white_box_synthesis.synthesis import synthesise

PLAN = {
    "passage_id": "1.1",
    "claim": "Workers organise.",
    "arguments": [{"id": "1.1.1", "claim": "Workers organise."}],
}
FRAGMENTS = [{"id": "src:A1", "text": "Workers do not organise."}]


def reference(text, fragment_id="src:A1", **fields):
    return {"fragment_id": fragment_id, "text": text, **fields}


def operation(text, kind="COPY", **fields):
    return {"type": kind, **reference(text), **fields}


def candidate(*operations, **fields):
    return {
        "records": [{"argument_id": "1.1.1", "operations": list(operations)}],
        **fields,
    }


class SynthesisTests(unittest.TestCase):
    def run_candidate(self, value, *, fragments=None, plan=None, constraints=None):
        return synthesise(
            PLAN if plan is None else plan,
            FRAGMENTS if fragments is None else fragments,
            constraints=constraints,
            candidate=value,
        )

    def assert_complete(self, result, passage, wording="100%"):
        self.assertEqual(result["state"], "complete", result)
        self.assertEqual(result["passage"], passage)
        self.assertEqual(result["provenance"]["human_wording"], wording)
        self.assertEqual(result["provenance"]["blocks_selection"], wording != "100%")
        self.assertEqual(result["assessment"]["mechanical_validity"], "passed")
        self.assertEqual(result["assessment"]["human_review"], "required")

    def assert_rejected(self, result):
        self.assertEqual(result["state"], "rejected", result)
        self.assertNotIn("passage", result)

    def test_initial_call_requests_operations(self):
        result = synthesise(PLAN, FRAGMENTS)
        self.assertEqual(result["state"], "needs_agent")
        self.assertEqual(result["contract"]["schema_version"], "2.0")
        self.assertEqual(result["contract"]["operation_policy_version"], "2.0")

    def test_copy_needs_no_semantic_attestation(self):
        result = self.run_candidate(candidate(operation("Workers do not organise.")))
        self.assert_complete(result, "Workers do not organise.")
        self.assertEqual(result["record"][0]["result_span"], result["passage"])
        self.assertEqual(result["provenance"]["basis"], ["A1"])
        self.assertEqual(result["assessment"]["unverified_work"], [])
        self.assertEqual(result["assessment"]["meaning"], "not_assessed")
        self.assertEqual(result["assessment"]["causality"], "not_assessed")

    def test_claim_is_not_a_semantic_gate(self):
        plan = copy.deepcopy(PLAN)
        plan["claim"] = plan["arguments"][0]["claim"] = "Factories cause rainfall."
        result = self.run_candidate(candidate(operation("Workers")), plan=plan)
        self.assert_complete(result, "Workers")
        self.assertEqual(result["assessment"]["meaning"], "not_assessed")

    def test_argument_records_assemble_in_plan_order(self):
        plan = copy.deepcopy(PLAN)
        plan["arguments"].append({"id": "1.1.2", "claim": "A second argument."})
        value = candidate(operation("Workers"))
        value["records"].append({
            "argument_id": "1.1.2", "separator": "paragraph",
            "operations": [operation("organise.")],
        })
        self.assert_complete(self.run_candidate(value, plan=plan), "Workers\n\norganise.")
        value["records"].reverse()
        self.assert_rejected(self.run_candidate(value, plan=plan))

    def test_plan_relations_do_not_require_support(self):
        plan = copy.deepcopy(PLAN)
        plan["arguments"].append({"id": "1.1.2", "claim": "Organising causes change."})
        plan["relations"] = [{
            "id": "R1", "kind": "causes", "claim": "An asserted connection.",
            "argument_ids": ["1.1.2", "1.1.1"],
        }]
        value = candidate(operation("Workers"))
        value["records"].append({
            "argument_id": "1.1.2", "operations": [operation("organise.")],
        })
        self.assert_complete(self.run_candidate(value, plan=plan), "Workers organise.")

    def test_expected_passage_and_record_are_checks(self):
        value = candidate(operation("Workers"), passage="Workers")
        value["records"][0]["result_span"] = "Workers"
        self.assert_complete(self.run_candidate(value), "Workers")
        for field in ("passage", "result_span"):
            with self.subTest(field=field):
                broken = copy.deepcopy(value)
                target = broken if field == "passage" else broken["records"][0]
                target[field] = "organise."
                self.assert_rejected(self.run_candidate(broken))

    def test_order_executes_a_permutation(self):
        value = candidate(
            operation("Workers", separator="space"),
            operation("organise.", separator="space"),
            {"type": "ORDER", "order": [1, 0]},
        )
        self.assert_complete(self.run_candidate(value), "organise. Workers")

    def test_order_defaults_follow_final_positions(self):
        value = candidate(
            operation("Workers"), operation("organise"),
            {"type": "ORDER", "order": [1, 0]},
        )
        self.assert_complete(self.run_candidate(value), "organise Workers")

    def test_order_uses_operation_indexes_after_delete(self):
        value = candidate(
            operation("Workers", separator="space"),
            {"type": "DELETE", "target": 0, "text": "Workers"},
            operation("organise.", separator="space"),
            {"type": "ORDER", "order": [2, 0]},
        )
        self.assert_complete(self.run_candidate(value), "organise.")

    def test_invalid_orders_reject_without_crashing(self):
        for order in ([], [0], [0, 0], [0, 2], [False, 1], [[0], 1], "1,0"):
            with self.subTest(order=order):
                value = candidate(
                    operation("Workers"), operation("organise."),
                    {"type": "ORDER", "order": order},
                )
                self.assert_rejected(self.run_candidate(value))

    def test_delete_executes_without_a_meaning_gate(self):
        value = candidate(
            operation("Workers do not organise."),
            {"type": "DELETE", "target": 0, "text": "not "},
        )
        result = self.run_candidate(value)
        self.assert_complete(result, "Workers do organise.")
        self.assertEqual(result["assessment"]["meaning"], "not_assessed")

    def test_deletions_address_current_remaining_text(self):
        fragments = [{"id": "src:A1", "text": "red red blue"}]
        value = candidate(
            operation("red red blue"),
            {"type": "DELETE", "target": 0, "text": "red ", "occurrence": 2},
            {"type": "DELETE", "target": 0, "text": "red "},
        )
        self.assert_complete(self.run_candidate(value, fragments=fragments), "blue")

    def test_invalid_delete_targets_reject_without_crashing(self):
        for target in (-1, 1, True, "0", [], {}):
            with self.subTest(target=target):
                value = candidate(
                    operation("Workers"),
                    {"type": "DELETE", "target": target, "text": "Workers"},
                )
                self.assert_rejected(self.run_candidate(value))

    def test_delete_cannot_target_an_order_operation(self):
        value = candidate(
            operation("Workers"), {"type": "ORDER", "order": [0]},
            {"type": "DELETE", "target": 1, "text": "Workers"},
        )
        self.assert_rejected(self.run_candidate(value))

    def test_delete_requires_an_exact_span(self):
        value = candidate(
            operation("Workers do not organise."),
            {"type": "DELETE", "target": 0, "text": "never "},
        )
        self.assert_rejected(self.run_candidate(value))

    def test_copy_resolves_exact_occurrence(self):
        fragments = [{"id": "src:A1", "text": "red blue red"}]
        result = self.run_candidate(candidate(operation("red", occurrence=2)), fragments=fragments)
        self.assert_complete(result, "red")
        self.assertEqual(result["record"][0]["operations"][0]["span"], [9, 12])
        for text, occurrence in (("Red", 1), ("red", 3), ("red", True)):
            with self.subTest(text=text, occurrence=occurrence):
                self.assert_rejected(self.run_candidate(
                    candidate(operation(text, occurrence=occurrence)), fragments=fragments,
                ))

    def test_source_whitespace_is_verbatim(self):
        text = "  Workers\torganise.  "
        self.assert_complete(self.run_candidate(
            candidate(operation(text)), fragments=[{"id": "src:A1", "text": text}],
        ), text)

    def test_word_fusing_joins_reject(self):
        self.assert_rejected(self.run_candidate(candidate(
            operation("Workers"), operation("organise", separator="none"),
        )))
        self.assert_complete(self.run_candidate(candidate(
            operation("Workers "), operation("organise", separator="none"),
        )), "Workers organise")

    def test_apostrophe_join_cannot_create_a_contraction(self):
        fragments = [{"id": "src:A1", "text": "can"}, {"id": "src:B2", "text": "'t"}]
        value = candidate(
            operation("can"), operation("'t", fragment_id="src:B2", separator="none"),
        )
        self.assert_rejected(self.run_candidate(value, fragments=fragments))

    def test_identity_transformations_remain_verified(self):
        for kind in ("INFLECT", "NORMALISE"):
            with self.subTest(kind=kind):
                self.assert_complete(self.run_candidate(candidate(operation(
                    "Workers", kind, output_text="Workers", axes=["number"],
                ))), "Workers")

    def test_inflection_is_unverified_without_a_morphology_checker(self):
        result = self.run_candidate(candidate(operation(
            "Workers", "INFLECT", output_text="Robots conquered Earth.", axis="number",
        )))
        self.assert_complete(result, "Robots conquered Earth.", wording="Unverified")
        self.assertEqual(result["assessment"]["unverified_work"], [
            {"argument_id": "1.1.1", "operation_index": 0},
        ])

    def test_case_and_punctuation_normalisation(self):
        self.assert_complete(self.run_candidate(candidate(operation(
            "Workers", "NORMALISE", output_text="workers!",
        ))), "workers!")

    def test_declared_word_replacement_is_unverified(self):
        value = candidate(operation("Workers", "NORMALISE", output_text="Robots"))
        self.assert_rejected(self.run_candidate(value))
        result = self.run_candidate(value, constraints={
            "normalisations": [{"from": "Workers", "to": "Robots"}],
        })
        self.assert_complete(result, "Robots", wording="Unverified")

    def test_normalisation_cannot_fuse_words(self):
        self.assert_rejected(self.run_candidate(candidate(operation(
            "Workers do", "NORMALISE", output_text="Workersdo",
        ))))

    def test_normalisation_cannot_silently_remove_combining_marks(self):
        text = "cafe\u0301"
        result = self.run_candidate(
            candidate(operation(text, "NORMALISE", output_text="cafe")),
            fragments=[{"id": "src:A1", "text": text}],
        )
        if result["state"] == "complete":
            self.assert_complete(result, "cafe", wording="Unverified")
        else:
            self.assert_rejected(result)

    def test_delete_cannot_edit_transformed_wording(self):
        for kind, output in (("INFLECT", "Worker"), ("NORMALISE", "workers")):
            with self.subTest(kind=kind):
                value = candidate(
                    operation("Workers", kind, output_text=output, axes=["number"]),
                    {"type": "DELETE", "target": 0, "text": output[0]},
                )
                self.assert_rejected(self.run_candidate(value))
        value = candidate(
            operation("Workers do not organise.", "INFLECT",
                      output_text="Workers do not organise.", axes=["number"]),
            {"type": "DELETE", "target": 0, "text": "not "},
        )
        self.assert_complete(self.run_candidate(value), "Workers do organise.")

    def test_protected_wording_allows_copy_but_not_changes(self):
        fragments = [{**FRAGMENTS[0], "protected": True}]
        self.assert_complete(self.run_candidate(
            candidate(operation("Workers")), fragments=fragments,
        ), "Workers")
        for value in (
            candidate(operation("Workers", "NORMALISE", output_text="workers")),
            candidate(operation("Workers do not organise."),
                      {"type": "DELETE", "target": 0, "text": "not "}),
        ):
            with self.subTest(candidate=value):
                self.assert_rejected(self.run_candidate(value, fragments=fragments))

    def test_protected_subspan_survives_other_deletions(self):
        fragments = [{**FRAGMENTS[0], "protected_spans": [{"text": "not"}]}]
        value = candidate(
            operation("Workers do not organise."),
            {"type": "DELETE", "target": 0, "text": "Workers "},
        )
        self.assert_complete(self.run_candidate(value, fragments=fragments), "do not organise.")
        value["records"][0]["operations"].append({
            "type": "DELETE", "target": 0, "text": "not ",
        })
        self.assert_rejected(self.run_candidate(value, fragments=fragments))

    def test_framework_fragments_cannot_supply_wording(self):
        for permitted_use in ("wording", "evidence", "user_interpretation", "framework_check"):
            with self.subTest(permitted_use=permitted_use):
                result = self.run_candidate(candidate(operation("Workers")), fragments=[{
                    **FRAGMENTS[0], "permitted_use": permitted_use,
                }])
                if permitted_use == "framework_check":
                    self.assert_rejected(result)
                else:
                    self.assert_complete(result, "Workers")

    def test_basis_follows_final_wording_and_omits_deleted_fragments(self):
        fragments = [*FRAGMENTS, {"id": "src:B2", "text": "People"},
                     {"id": "src:C3", "text": "unneeded"}]
        value = candidate(
            operation("Workers", separator="space"),
            operation("People", fragment_id="src:B2", separator="space"),
            operation("unneeded", fragment_id="src:C3", separator="space"),
            {"type": "DELETE", "target": 2, "text": "unneeded"},
            {"type": "ORDER", "order": [1, 0, 2]},
        )
        result = self.run_candidate(value, fragments=fragments)
        self.assert_complete(result, "People Workers")
        self.assertEqual(result["provenance"]["basis"], ["B2", "A1"])

    def test_agent_diagnostics_do_not_block_assembly(self):
        fragments = [*FRAGMENTS, {"id": "src:B2", "text": "No causal evidence."}]
        for kind in ("causal_gap", "contradiction"):
            with self.subTest(kind=kind):
                value = candidate(operation("Workers"), diagnostics=[{
                    "type": kind, "argument_id": "1.1.1",
                    "detail": "The proposed claim lacks source support.",
                    "basis": [reference("No causal evidence.", "src:B2")],
                }])
                result = self.run_candidate(value, fragments=fragments)
                self.assert_complete(result, "Workers")
                self.assertEqual(result["provenance"]["basis"], ["A1"])
                self.assertEqual(result["diagnostics"][0]["type"], kind)
                self.assertEqual(result["diagnostics"][0]["origin"], "agent")

    def test_gap_has_no_passage(self):
        gap = {
            "type": "Unsupported connection", "passage_id": "1.1", "argument_id": "1.1.1",
            "missing_requirement": "Wording for the connection.", "authoritative_owner": "user",
            "question": "Which wording should express the connection?",
            "resolution_paths": ["supply wording", "revise the claim"],
        }
        result = synthesise(PLAN, FRAGMENTS, gap=gap)
        self.assertEqual(result["state"], "gap", result)
        self.assertNotIn("passage", result)
        self.assert_rejected(synthesise(
            PLAN, FRAGMENTS, candidate=candidate(operation("Workers")), gap=gap,
        ))

    def test_explicit_old_schema_rejects(self):
        value = candidate(operation("Workers"), schema_version="1.0")
        self.assert_rejected(self.run_candidate(value))
        value["schema_version"] = "2.0"
        self.assert_complete(self.run_candidate(value), "Workers")

    def test_malformed_operation_types_reject_without_crashing(self):
        for kind in ([], {}, None, 12, "PARAPHRASE"):
            with self.subTest(kind=kind):
                self.assert_rejected(self.run_candidate(candidate(operation("Workers", kind))))

    def test_inputs_are_not_mutated(self):
        plan, fragments = copy.deepcopy(PLAN), copy.deepcopy(FRAGMENTS)
        value = candidate(operation("Workers"))
        before = copy.deepcopy((plan, fragments, value))
        self.assert_complete(self.run_candidate(value, fragments=fragments, plan=plan), "Workers")
        self.assertEqual((plan, fragments, value), before)

    def test_report_does_not_share_mutable_axes_with_caller(self):
        axes = ["number"]
        value = candidate(operation("Workers", "INFLECT", output_text="Workers", axes=axes))
        result = self.run_candidate(value)
        self.assert_complete(result, "Workers")
        axes.append("tense")
        self.assertEqual(result["record"][0]["operations"][0]["axes"], ["number"])


if __name__ == "__main__":
    unittest.main()

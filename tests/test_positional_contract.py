"""Offline regression tests for the positional provider contract.

Exact lengths reserve every field, but cannot prove that a string describes the
right concept. Semantic review remains separate from structural validation.
"""

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


_FIXTURE_NAME = "test_creative_intelligence"
if _FIXTURE_NAME in sys.modules:
    FIXTURES = sys.modules[_FIXTURE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(
        _FIXTURE_NAME, Path(__file__).with_name("test_creative_intelligence.py")
    )
    FIXTURES = importlib.util.module_from_spec(_spec)
    sys.modules[_FIXTURE_NAME] = FIXTURES
    _spec.loader.exec_module(FIXTURES)

CREATIVE = FIXTURES.CREATIVE
CORE = FIXTURES.CORE


def positional_response(master=None):
    """Encode an independent rich fixture in the versioned positional order."""
    master = copy.deepcopy(master if master is not None else FIXTURES.fixture_response())

    def at_path(value, path):
        for part in path.split("."):
            value = value[part]
        return copy.deepcopy(value)

    def pack(value, scalars, lists):
        block = {"list_values": [at_path(value, name) for name in lists]}
        if scalars:
            block["scalar_values"] = [at_path(value, name) for name in scalars]
        return block

    response = {
        name: pack(master[name], fields["scalar"], fields["list"])
        for name, fields in CREATIVE._SECTION_FIELDS.items()
    }
    response["evidence"] = master["evidence"]
    response["provenance"] = master["provenance"]
    response["original_shot_plan"] = [
        {
            "shot_id": shot["shot_id"],
            "planned_duration_seconds": shot["planned_duration_seconds"],
            **pack(shot, CREATIVE._SHOT_SCALAR_FIELDS, CREATIVE._SHOT_LIST_FIELDS),
            "seedance_direction": shot["seedance_direction"],
        }
        for shot in master["original_shot_plan"]
    ]
    return response


def positional_blocks(response):
    for name in CREATIVE._SECTION_FIELDS:
        yield name, response[name]
    for index, shot in enumerate(response["original_shot_plan"]):
        yield f"original_shot_plan[{index}]", shot


class PositionalContractTests(unittest.TestCase):
    def test_all_master_fields_roundtrip_without_mutation(self):
        master = FIXTURES.fixture_response()
        response = positional_response(master)
        original = copy.deepcopy(response)
        self.assertEqual(CREATIVE.expand_provider_creative_intelligence(response), master)
        self.assertEqual(response, original)
        self.assertEqual(
            CREATIVE.expand_provider_creative_intelligence(response, provider_schema_version="1.5.0"),
            master,
        )

    def test_every_positional_block_enforces_both_length_boundaries(self):
        for name, block in positional_blocks(positional_response()):
            for key in ("scalar_values", "list_values"):
                if key not in block:
                    continue
                for delta in (-1, 1):
                    with self.subTest(block=name, array=key, delta=delta):
                        response = positional_response()
                        target = dict(positional_blocks(response))[name][key]
                        target.pop() if delta < 0 else target.append(copy.deepcopy(target[-1]))
                        with self.assertRaises(CORE.AdsArtError):
                            CREATIVE.expand_provider_creative_intelligence(response)

    def test_missing_arrays_and_unknown_fields_fail_in_every_block(self):
        for name, block in positional_blocks(positional_response()):
            for key in ("scalar_values", "list_values"):
                if key in block:
                    with self.subTest(block=name, missing=key):
                        response = positional_response()
                        del dict(positional_blocks(response))[name][key]
                        with self.assertRaises(CORE.AdsArtError):
                            CREATIVE.expand_provider_creative_intelligence(response)
            with self.subTest(block=name, unknown="facets"):
                response = positional_response()
                dict(positional_blocks(response))[name]["facets"] = []
                with self.assertRaises(CORE.AdsArtError):
                    CREATIVE.expand_provider_creative_intelligence(response)

    def test_non_text_and_empty_scalar_positions_fail(self):
        for name, block in positional_blocks(positional_response()):
            if "scalar_values" not in block:
                continue
            for invalid in (None, False, 7, {}, [], "", " \t\n"):
                with self.subTest(block=name, invalid=invalid):
                    response = positional_response()
                    dict(positional_blocks(response))[name]["scalar_values"][0] = invalid
                    with self.assertRaises(CORE.AdsArtError):
                        CREATIVE.expand_provider_creative_intelligence(response)

    def test_array_types_and_nested_list_item_types_fail(self):
        for name, block in positional_blocks(positional_response()):
            for key in ("scalar_values", "list_values"):
                if key not in block:
                    continue
                for invalid in (None, "not an array", {}, 3):
                    with self.subTest(block=name, array=key, invalid=invalid):
                        response = positional_response()
                        dict(positional_blocks(response))[name][key] = invalid
                        with self.assertRaises(CORE.AdsArtError):
                            CREATIVE.expand_provider_creative_intelligence(response)
            for invalid in (None, "flattened list", {}, [None], [False], [7], [["nested too far"]]):
                with self.subTest(block=name, list_item=invalid):
                    response = positional_response()
                    dict(positional_blocks(response))[name]["list_values"][0] = invalid
                    with self.assertRaises(CORE.AdsArtError):
                        CREATIVE.expand_provider_creative_intelligence(response)

    def test_composition_has_reserved_slot_and_is_not_inferred_from_framing(self):
        self.assertEqual(CREATIVE._SHOT_SCALAR_FIELDS[6], "composition")
        self.assertEqual(len(CREATIVE._SHOT_SCALAR_FIELDS), 17)
        self.assertEqual(len(CREATIVE._SHOT_LIST_FIELDS), 4)
        response = positional_response()
        response["original_shot_plan"][0]["scalar_values"][6] = "Dedicated composition value."
        expanded = CREATIVE.expand_provider_creative_intelligence(response)
        self.assertEqual(expanded["original_shot_plan"][0]["composition"], "Dedicated composition value.")
        self.assertNotEqual(expanded["original_shot_plan"][0]["composition"], expanded["original_shot_plan"][0]["framing"])
        response["original_shot_plan"][0]["scalar_values"][6] = ""
        with self.assertRaises(CORE.AdsArtError):
            CREATIVE.expand_provider_creative_intelligence(response)

    def test_schema_and_prompt_agree_on_positions_and_exact_lengths(self):
        schema = CREATIVE.creative_intelligence_provider_schema(2, 3)
        _, prompt = CREATIVE.build_creative_intelligence_prompt(
            FIXTURES.fixture_brief(), {"concepts": []}, {"duration_seconds": 2}, True
        )
        layout = json.loads(prompt)["compact_provider_contract"]["positional_layout"]
        fields_by_name = dict(CREATIVE._SECTION_FIELDS)
        fields_by_name["original_shot_plan"] = {
            "scalar": CREATIVE._SHOT_SCALAR_FIELDS, "list": CREATIVE._SHOT_LIST_FIELDS,
        }
        for name, fields in fields_by_name.items():
            block = schema["properties"][name]
            if name == "original_shot_plan":
                block = block["items"]
            for category, key in (("scalar", "scalar_values"), ("list", "list_values")):
                expected = list(fields[category])
                with self.subTest(block=name, array=key):
                    if not expected:
                        self.assertNotIn(key, block["properties"])
                        self.assertNotIn(key, layout[name])
                        continue
                    self.assertEqual(layout[name][key], expected)
                    self.assertIn(key, block["required"])
                    array = block["properties"][key]
                    self.assertEqual(array["type"], "array")
                    self.assertEqual(array["minItems"], len(expected))
                    self.assertEqual(array["maxItems"], len(expected))
                    item = array["items"]
                    if category == "list":
                        self.assertEqual(item["type"], "array")
                        item = item["items"]
                    self.assertEqual(item["type"], "string")

    def test_provider_schema_avoids_refs_tuples_and_key_enumerations(self):
        schema = CREATIVE.creative_intelligence_provider_schema(4, 7)

        def visit(value, path=()):
            if isinstance(value, dict):
                self.assertFalse(set(value) & {"$schema", "$defs", "$ref", "prefixItems", "facets"}, path)
                if "enum" in value:
                    self.assertIn("evidence", path)
                if "items" in value:
                    self.assertIsInstance(value["items"], dict)
                for key, item in value.items():
                    visit(item, path + (key,))
            elif isinstance(value, list):
                for item in value:
                    visit(item, path)

        visit(schema)
        diagnostics = FIXTURES.GEMINI.validate_response_json_schema_for_provider(schema)
        self.assertEqual(diagnostics["unsupported_keywords"], [])

    def test_legacy_facets_require_explicit_version(self):
        legacy = FIXTURES.fixture_provider_response(provider_schema_version="1.3.0")
        with self.assertRaises(CORE.AdsArtError):
            CREATIVE.expand_provider_creative_intelligence(legacy)
        for version in ("1.3.0", "1.4.0"):
            self.assertEqual(
                CREATIVE.expand_provider_creative_intelligence(legacy, provider_schema_version=version),
                FIXTURES.fixture_response(),
            )
        with self.assertRaises(CORE.AdsArtError):
            CREATIVE.expand_provider_creative_intelligence(positional_response(), provider_schema_version="9.9.9")

    def test_string_swap_remains_structurally_valid_and_requires_semantic_review(self):
        response = positional_response()
        values = response["original_shot_plan"][0]["scalar_values"]
        original_composition, original_framing = values[6], values[7]
        values[6], values[7] = values[7], values[6]
        shot = CREATIVE.expand_provider_creative_intelligence(response)["original_shot_plan"][0]
        self.assertEqual(shot["composition"], original_framing)
        self.assertEqual(shot["framing"], original_composition)


if __name__ == "__main__":
    unittest.main()

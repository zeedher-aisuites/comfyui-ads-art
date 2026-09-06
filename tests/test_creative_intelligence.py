import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ads_art_creative_test_package",
    PACKAGE_ROOT / "__init__.py",
    submodule_search_locations=[str(PACKAGE_ROOT)],
)
PACKAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACKAGE
SPEC.loader.exec_module(PACKAGE)
CORE = sys.modules["ads_art_creative_test_package.ads_art_core"]
GEMINI = sys.modules["ads_art_creative_test_package.ads_art_gemini"]
CREATIVE = sys.modules["ads_art_creative_test_package.ads_art_creative"]
NODES = sys.modules["ads_art_creative_test_package.ads_art_creative_nodes"]

SYNC_SPEC = importlib.util.spec_from_file_location(
    "ads_art_sync_creative_workflow",
    PACKAGE_ROOT / "scripts" / "sync_creative_workflow_v2.py",
)
SYNC = importlib.util.module_from_spec(SYNC_SPEC)
SYNC_SPEC.loader.exec_module(SYNC)


def fixture_brief(project_id="creative_test"):
    return {
        "schema_version": "2.0.0",
        "product_paradigm": "reference_driven_advertising_intelligence_original_generation",
        "project_id": project_id,
        "character": {
            "name": "Madame X",
            "identity_notes": "Long profile, quiet confidence, dark auburn hair.",
            "personality": "Reserved and incisive.",
            "archetype": "Enigmatic cultural icon.",
            "style_constraints": "Preserve the approved identity.",
            "approval_status": "user_approved_identity_required",
        },
        "brand": {"creation_mode": "ai_propose", "name": "", "source": "ai_proposed"},
        "product": {"category": "fragrance", "description": "", "source": "ai_proposed_when_missing"},
        "audience": "Adults seeking quiet distinction.",
        "positioning": "Understated luxury.",
        "emotional_promise": "Self-possession.",
        "visual_brand_world": "Mineral surfaces and nocturnal warmth.",
        "brand_constraints": "Fictional and distinct from the reference.",
        "required_elements": "One approved character.",
        "forbidden_elements": "Reference brand, packaging, performer and scenes.",
        "user_constraints": "Create an original ad.",
        "target_duration_seconds": 10,
        "min_original_shots": 2,
        "max_original_shots": 3,
        "controls": {
            "positive_prompt": "One approved character.",
            "restrictive_prompt": "Fictional and distinct.",
            "negative_prompt": "Reference brand and scenes.",
            "creative_prompt": "Create an original ad.",
        },
        "conflicts": [],
        "ready": True,
    }


def fixture_response():
    shot_template = {
        "planned_duration_seconds": 5.0,
        "purpose": "Build a new visual premise.",
        "psychological_function": "Signal calm authority.",
        "retention_function": "Delay the reveal with a new visual question.",
        "character_action": "The character opens a narrow aperture in a mineral wall.",
        "expression": "Controlled curiosity.",
        "environment": "An original nocturnal mineral gallery.",
        "composition": "Asymmetric negative space around a new architectural form.",
        "framing": "Medium portrait with independent geometry.",
        "camera": "Eye-level camera with a restrained lateral drift.",
        "lens_or_perspective": "Natural perspective with modest depth compression.",
        "movement": "A slow lateral drift reveals the new product pedestal.",
        "lighting": "Warm edge light against a cool mineral ambient field.",
        "color_and_texture": "Charcoal stone, amber glass and soft black fabric.",
        "product_presence": "A fictional unbranded fragrance object enters late.",
        "audio_function": "A sparse tonal pulse resolves at the reveal.",
        "continuity_notes": "Preserve character identity and the mineral brand world.",
        "reference_principles_used": ["controlled withholding", "status through restraint"],
        "literal_reference_elements_avoided": ["reference performer", "reference set", "reference packaging"],
        "differentiation_notes": ["new environment", "new action", "new composition"],
        "nano_banana_prompt": "Original advertising keyframe in a nocturnal mineral gallery with the approved character and a fictional amber object.",
        "seedance_direction": {
            "performance": "Open the aperture with measured curiosity.",
            "camera_movement": "Restrained lateral drift.",
            "pacing": "Slow build followed by a concise reveal.",
            "emotional_goal": "Turn distance into self-possession.",
            "continuity": "Maintain the original mineral world and approved character.",
        },
        "uncertainties": ["Final fictional product geometry needs user review."],
    }
    first = {"shot_id": "shot_01", **copy.deepcopy(shot_template)}
    second = {"shot_id": "shot_02", **copy.deepcopy(shot_template)}
    second["character_action"] = "The character crosses a beam of amber light and pauses beside the pedestal."
    second["composition"] = "A new frontal field divided by light rather than architecture."
    return {
        "reference_observation": {
            "visual_facts": ["A single performer is frequently isolated in close framing."],
            "editing_facts": ["Cuts accelerate after the opening interval."],
            "audio_facts": ["Music rises before the final reveal."],
            "product_and_brand_facts": ["Brand material appears near the close."],
        },
        "reference_interpretation": {
            "core_concept": "Controlled distance creates desirability.",
            "creative_thesis": "Status is communicated through withholding.",
            "opening_hook": "An unresolved isolated figure.",
            "hook_mechanism": "Curiosity through incomplete context.",
            "emotional_promise": "Exclusive self-possession.",
            "audience_desire": "Belonging without visible effort.",
            "character_archetype": "Inaccessible icon.",
            "status_signals": ["spatial isolation"],
            "aspirational_mechanisms": ["controlled access"],
            "psychological_mechanisms": ["mystery", "scarcity"],
            "retention_mechanisms": ["delayed context"],
            "emotional_progression": ["distance", "curiosity", "reveal"],
        },
        "reference_strategy": {
            "visual_grammar": {
                "principles": ["isolation before reveal"],
                "composition_patterns": ["negative space"],
                "distance_and_framing": ["close to medium progression"],
                "color_and_texture": ["warm metallic contrast"],
            },
            "camera_language": {
                "principles": ["controlled movement"],
                "framing_patterns": ["isolated portraits"],
                "lens_or_perspective_patterns": ["compressed elegance"],
                "movement_patterns": ["slow reveal"],
            },
            "lighting_language": {
                "principles": ["directional separation"],
                "contrast_and_direction": ["warm edge light"],
                "motivated_sources": ["architectural openings"],
            },
            "editing_rhythm": {
                "pace": "Measured opening, denser middle, resolved close.",
                "progression": ["hold", "accelerate", "resolve"],
                "shot_duration_patterns": ["longer hook and closing shots"],
            },
            "audio_strategy": {
                "observed_structure": ["rising score"],
                "interpreted_function": ["anticipation"],
                "transferable_audio_principles": ["resolve music with product reveal"],
            },
            "product_reveal_strategy": "Delay clear product information until desire is established.",
            "brand_memory_strategy": "End on one simple sensory association.",
        },
        "evidence": [
            {
                "evidence_id": "evidence_01",
                "timestamp_seconds": 0.5,
                "shot_start_seconds": 0.0,
                "shot_end_seconds": 1.0,
                "candidate_timestamps": [0.4, 0.5, 0.6],
                "evidence_kind": "mixed",
                "observed_fact": "A lone figure is held before the first cut while the score rises.",
                "supports": sorted(CREATIVE.EVIDENCE_SUPPORTS),
            }
        ],
        "transfer_rules": {
            "transferable_principles": ["withhold context before revealing value"],
            "literal_elements_to_avoid": ["performer, set, pose and product"],
            "similarity_risks": ["matching the original blocking"],
            "brand_specific_elements_not_to_inherit": ["name, logo, bottle and claims"],
        },
        "original_adaptation": {
            "creative_thesis": "Quiet access to an impossible mineral world.",
            "new_hook": "The character discovers light inside opaque stone.",
            "new_character_role": "Keeper of a private sensory threshold.",
            "character_behavior": "Precise, curious and self-possessed.",
            "new_brand_world": "A fictional nocturnal mineral gallery.",
            "new_product_role": "A sensory key proposed by AI and pending approval.",
            "emotional_arc": ["distance", "discovery", "ownership"],
            "visual_rules": ["new mineral geometry", "restrained amber accents"],
            "audio_rules": ["sparse pulse, tactile reveal accent"],
            "editing_rules": ["measured hook, concise reveal"],
            "differentiation_from_reference": ["new setting, actions, object and composition"],
        },
        "original_shot_plan": [first, second],
        "provenance": {
            "user_provided": ["USER_PROVIDED: approved Madame X identity", "USER_PROVIDED: target duration"],
            "ai_proposed": ["AI_PROPOSED: fictional brand world", "AI_PROPOSED: fictional fragrance object"],
            "approved": ["USER_APPROVED: Madame X identity"],
            "unresolved_inputs": ["fictional brand name", "final product geometry"],
        },
    }


def fixture_provider_response(master=None):
    master = copy.deepcopy(master or fixture_response())

    def get_path(value, path):
        for part in path.split("."):
            value = value[part]
        return value

    provider = {}
    for section, fields in CREATIVE._SECTION_FIELDS.items():
        provider[section] = {
            "facets": [
                {"key": key, "values": [get_path(master[section], key)]}
                for key in fields["scalar"]
            ] + [
                {"key": key, "values": get_path(master[section], key)}
                for key in fields["list"]
            ],
        }
    provider["evidence"] = master["evidence"]
    provider["original_shot_plan"] = []
    for shot in master["original_shot_plan"]:
        provider["original_shot_plan"].append(
            {
                "shot_id": shot["shot_id"],
                "planned_duration_seconds": shot["planned_duration_seconds"],
                "facets": [
                    {"key": key, "values": [shot[key]]} for key in CREATIVE._SHOT_SCALAR_FIELDS
                ] + [
                    {"key": key, "values": shot[key]} for key in CREATIVE._SHOT_LIST_FIELDS
                ],
                "seedance_direction": copy.deepcopy(shot["seedance_direction"]),
            }
        )
    provider["provenance"] = master["provenance"]
    return provider


class CreativeIntelligenceTests(unittest.TestCase):
    def test_provider_schema_uses_only_documented_keyword_subset(self):
        for schema in (
            GEMINI.gemini_analysis_schema(3),
            CREATIVE.creative_intelligence_provider_schema(4, 7),
        ):
            diagnostics = GEMINI.validate_response_json_schema_for_provider(schema)
            self.assertEqual(diagnostics["unsupported_keywords"], [])
            self.assertNotIn("$schema", schema)

    def test_installed_sdk_serializes_compact_schema_without_network(self):
        try:
            from google.genai import types
        except ImportError:
            self.skipTest("google-genai is not installed in this test interpreter")
        schema = CREATIVE.creative_intelligence_provider_schema(4, 7)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema,
            max_output_tokens=8192,
            thinking_config={"thinking_level": "low"},
        )
        serialized = json.loads(config.model_dump_json(by_alias=True, exclude_none=True))
        self.assertEqual(serialized["responseJsonSchema"], schema)
        self.assertNotIn("$schema", serialized["responseJsonSchema"])

    def test_compact_provider_schema_is_near_v1_and_far_below_master(self):
        v1 = GEMINI.response_json_schema_diagnostics(GEMINI.gemini_analysis_schema(3))
        master = GEMINI.response_json_schema_diagnostics(CREATIVE.creative_intelligence_schema(4, 7))
        provider = GEMINI.response_json_schema_diagnostics(CREATIVE.creative_intelligence_provider_schema(4, 7))
        self.assertEqual(v1["property_declarations"], 30)
        self.assertEqual(master["property_declarations"], 104)
        self.assertLess(provider["property_declarations"], master["property_declarations"] // 2)
        self.assertLess(provider["serialized_bytes"], master["serialized_bytes"] * 0.55)
        self.assertLess(provider["constraint_declarations"], master["constraint_declarations"] // 2)

    def test_provider_expansion_is_deterministic_and_master_valid(self):
        provider = fixture_provider_response()
        first = CREATIVE.expand_provider_creative_intelligence(provider)
        second = CREATIVE.expand_provider_creative_intelligence(copy.deepcopy(provider))
        self.assertEqual(first, second)
        validated = CREATIVE.validate_creative_intelligence(
            first, duration_seconds=2.0, target_duration_seconds=10,
            min_shots=2, max_shots=3,
        )
        self.assertTrue(validated["validation"]["separation_validated"])

    def test_provider_missing_and_unknown_facets_fail(self):
        missing = fixture_provider_response()
        missing["reference_interpretation"]["facets"].pop()
        with self.assertRaisesRegex(CORE.AdsArtError, "faltan facetas obligatorias"):
            CREATIVE.expand_provider_creative_intelligence(missing)
        unknown = fixture_provider_response()
        unknown["reference_strategy"]["facets"][0]["key"] = "invented_strategy"
        with self.assertRaisesRegex(CORE.AdsArtError, "faceta desconocida"):
            CREATIVE.expand_provider_creative_intelligence(unknown)

    def test_provider_expansion_preserves_evidence_and_plan_validation(self):
        timestamp = fixture_provider_response()
        timestamp["evidence"][0]["timestamp_seconds"] = 9.0
        with self.assertRaisesRegex(CORE.AdsArtError, "fuera del video"):
            CREATIVE.validate_creative_intelligence(
                CREATIVE.expand_provider_creative_intelligence(timestamp),
                duration_seconds=2.0, target_duration_seconds=10, min_shots=2, max_shots=3,
            )

    def test_provider_evidence_kind_alias_is_normalized_not_invented(self):
        provider = fixture_provider_response()
        provider["evidence"][0]["evidence_kind"] = "observed_visual"
        master = CREATIVE.expand_provider_creative_intelligence(provider)
        self.assertEqual(master["evidence"][0]["evidence_kind"], "visual")
        provider["evidence"][0]["evidence_kind"] = "invented_kind"
        with self.assertRaisesRegex(CORE.AdsArtError, "evidence_kind desconocido"):
            CREATIVE.expand_provider_creative_intelligence(provider)

    def test_provider_shot_id_padding_is_canonicalized(self):
        provider = fixture_provider_response()
        provider["original_shot_plan"][0]["shot_id"] = "shot_001"
        master = CREATIVE.expand_provider_creative_intelligence(provider)
        self.assertEqual(master["original_shot_plan"][0]["shot_id"], "shot_01")
        count = fixture_provider_response()
        count["original_shot_plan"].pop()
        with self.assertRaisesRegex(CORE.AdsArtError, "fuera del rango"):
            CREATIVE.validate_creative_intelligence(
                CREATIVE.expand_provider_creative_intelligence(count),
                duration_seconds=2.0, target_duration_seconds=10, min_shots=2, max_shots=3,
            )
        duration = fixture_provider_response()
        duration["original_shot_plan"][0]["planned_duration_seconds"] = 1
        with self.assertRaisesRegex(CORE.AdsArtError, "no coincide"):
            CREATIVE.validate_creative_intelligence(
                CREATIVE.expand_provider_creative_intelligence(duration),
                duration_seconds=2.0, target_duration_seconds=10, min_shots=2, max_shots=3,
            )

    def test_provider_expansion_keeps_originality_guard(self):
        provider = fixture_provider_response()
        facet = next(
            item for item in provider["original_shot_plan"][0]["facets"]
            if item["key"] == "nano_banana_prompt"
        )
        facet["values"] = ["Recreate the reference shot exactly."]
        with self.assertRaisesRegex(CORE.AdsArtError, "copia literal"):
            CREATIVE.validate_creative_intelligence(
                CREATIVE.expand_provider_creative_intelligence(provider),
                duration_seconds=2.0, target_duration_seconds=10, min_shots=2, max_shots=3,
            )

    def test_unsupported_schema_stops_before_key_or_network(self):
        with mock.patch.object(GEMINI, "require_gemini_api_key") as key_lookup:
            with self.assertRaisesRegex(CORE.AdsArtError, r"keywords no admitidos.*\$schema"):
                GEMINI.call_gemini_analysis(
                    video_path="never-opened.mp4",
                    approved_identity_path=None,
                    system_instruction="local",
                    prompt="local",
                    response_schema={"$schema": "draft", "type": "object"},
                    source_has_audio=False,
                    duration_seconds=1,
                )
        key_lookup.assert_not_called()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_user_dir = CORE._default_user_directory
        CORE._default_user_directory = lambda: Path(self.temp.name)

    def tearDown(self):
        CORE._default_user_directory = self.previous_user_dir
        self.temp.cleanup()

    def make_video(self, name="reference.mp4"):
        import av
        import numpy as np

        path = Path(self.temp.name) / name
        container = av.open(str(path), mode="w")
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 64
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        for color in ((40, 20, 10), (180, 150, 80)):
            for _ in range(10):
                array = np.zeros((64, 64, 3), dtype=np.uint8)
                array[:, :] = color
                frame = av.VideoFrame.from_ndarray(array, format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        container.close()
        return path

    def test_exact_model_and_no_fallback(self):
        self.assertEqual(GEMINI.GEMINI_MODEL_ID, "gemini-3.6-flash")
        choices = NODES.AdsArtGeminiCreativeIntelligence.INPUT_TYPES()["required"]["model"][0]
        self.assertEqual(choices, ["gemini-3.6-flash"])

    def test_automatic_node_has_no_confirmation_gate(self):
        inputs = NODES.AdsArtGeminiCreativeIntelligence.INPUT_TYPES()["required"]
        self.assertNotIn("confirm_gemini_analysis", inputs)
        self.assertIn("reuse_matching_analysis", inputs)

    def test_new_schema_separates_observation_interpretation_and_proposal(self):
        schema = CREATIVE.creative_intelligence_schema(2, 5)
        properties = schema["properties"]
        self.assertIn("reference_observation", properties)
        self.assertIn("reference_interpretation", properties)
        self.assertIn("reference_strategy", properties)
        self.assertIn("original_adaptation", properties)
        self.assertIn("original_shot_plan", properties)
        self.assertEqual(properties["original_shot_plan"]["maxItems"], 5)

    def test_valid_response_has_evidence_and_original_plan(self):
        result = CREATIVE.validate_creative_intelligence(
            fixture_response(), duration_seconds=2.0, target_duration_seconds=10,
            min_shots=2, max_shots=3,
        )
        self.assertEqual(result["evidence"][0]["timestamp_seconds"], 0.5)
        self.assertEqual(len(result["original_shot_plan"]), 2)
        self.assertTrue(result["validation"]["separation_validated"])

    def test_evidence_timestamp_out_of_range_stops(self):
        response = fixture_response()
        response["evidence"][0]["timestamp_seconds"] = 3.0
        with self.assertRaisesRegex(CORE.AdsArtError, "fuera del video"):
            CREATIVE.validate_creative_intelligence(
                response, duration_seconds=2.0, target_duration_seconds=10,
                min_shots=2, max_shots=3,
            )

    def test_literal_remake_instruction_stops(self):
        response = fixture_response()
        response["original_shot_plan"][0]["nano_banana_prompt"] = "Recreate the reference shot exactly."
        with self.assertRaisesRegex(CORE.AdsArtError, "recreación literal|remake|literal"):
            CREATIVE.validate_creative_intelligence(
                response, duration_seconds=2.0, target_duration_seconds=10,
                min_shots=2, max_shots=3,
            )

    def test_signature_changes_with_brand_character_and_video(self):
        brief = fixture_brief()
        base = dict(video_sha256="a", video_bytes=1, identity_sha256="i", brief=brief, knowledge_sha256="k", local_detector={"cuts": [0]})
        original = GEMINI.stable_fingerprint(CREATIVE.creative_signature(**base))
        brand = copy.deepcopy(brief)
        brand["brand"]["name"] = "New Name"
        character = copy.deepcopy(brief)
        character["character"]["identity_notes"] += " New scar."
        self.assertNotEqual(original, GEMINI.stable_fingerprint(CREATIVE.creative_signature(**{**base, "brief": brand})))
        self.assertNotEqual(original, GEMINI.stable_fingerprint(CREATIVE.creative_signature(**{**base, "brief": character})))
        self.assertNotEqual(original, GEMINI.stable_fingerprint(CREATIVE.creative_signature(**{**base, "video_sha256": "b"})))
        signature = CREATIVE.creative_signature(**base)
        self.assertEqual(signature["provider_schema_version"], CREATIVE.CREATIVE_PROVIDER_SCHEMA_VERSION)
        self.assertEqual(signature["expander_version"], CREATIVE.CREATIVE_EXPANDER_VERSION)
        self.assertEqual(signature["max_output_tokens"], 16384)

    def test_missing_key_stops_before_provider_call(self):
        import torch

        video = self.make_video()
        node = NODES.AdsArtGeminiCreativeIntelligence()
        previous = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with mock.patch.object(NODES, "call_gemini_analysis", side_effect=AssertionError("must not call provider")):
                with self.assertRaisesRegex(CORE.AdsArtError, "Falta GEMINI_API_KEY"):
                    node.analyze(json.dumps(fixture_brief()), str(video), "gemini-3.6-flash", "faithful_principles", 0.1, 0.2, 10.0, True, True, False, 1, 10, torch.zeros((1, 64, 64, 3)))
        finally:
            if previous is not None:
                os.environ["GEMINI_API_KEY"] = previous

    def test_cache_prevents_second_inference_and_no_higgsfield(self):
        import torch

        video = self.make_video()
        call_result = {
            "response": fixture_provider_response(),
            "usage": {"prompt_token_count": 100, "candidates_token_count": 50, "thoughts_token_count": None},
            "cost_estimate": {"amount_usd": 0.001, "observed_charge_usd": None},
            "timings": {"upload_seconds": 0.1, "inference_seconds": 0.2},
            "provider": {"model_requested": "gemini-3.6-flash", "request_parameters": {"upload_retries": 1}},
        }
        node = NODES.AdsArtGeminiCreativeIntelligence()
        args = (json.dumps(fixture_brief()), str(video), "gemini-3.6-flash", "faithful_principles", 0.1, 0.2, 10.0, True, True, False, 1, 10, torch.zeros((1, 64, 64, 3)))
        with mock.patch.object(NODES, "gemini_credentials_configured", return_value=True), mock.patch.object(NODES, "call_gemini_analysis", return_value=call_result) as provider, mock.patch.object(CORE, "submit_request", side_effect=AssertionError("Higgsfield must not run")):
            first = node.analyze(*args)
            second = node.analyze(*args)
        self.assertEqual(provider.call_count, 1)
        self.assertIn("REMOTE ANALYSIS", first["ui"]["text"][0])
        self.assertIn("CACHE HIT", second["ui"]["text"][0])
        master = json.loads(second["result"][0])
        self.assertFalse(master["safety"]["paid_generation_submitted"])
        self.assertTrue(all(item["frame_role"] == "REFERENCE_EVIDENCE_ONLY_NOT_GENERATION_TARGET" for item in master["evidence"]))

    def test_invalid_provider_response_is_not_persisted_completed(self):
        import torch

        video = self.make_video()
        invalid = fixture_provider_response()
        invalid["original_adaptation"]["facets"].pop()
        call_result = {
            "response": invalid,
            "usage": {}, "cost_estimate": {}, "timings": {},
            "provider": {
                "attempt_counters": {
                    "model_preflight_attempts": 1,
                    "upload_attempts": 1,
                    "generate_content_attempts": 1,
                }
            },
        }
        node = NODES.AdsArtGeminiCreativeIntelligence()
        args = (
            json.dumps(fixture_brief()), str(video), "gemini-3.6-flash", "faithful_principles",
            0.1, 0.2, 10.0, True, True, False, 1, 10,
            torch.zeros((1, 64, 64, 3)),
        )
        with mock.patch.object(NODES, "gemini_credentials_configured", return_value=True), mock.patch.object(
            NODES, "call_gemini_analysis", return_value=call_result
        ):
            with self.assertRaisesRegex(CORE.AdsArtError, "faltan facetas obligatorias"):
                node.analyze(*args)
        state_files = list(
            (Path(self.temp.name) / "ads_art" / "projects" / "creative_test" / "analysis" / "creative_intelligence" / "state").glob("*.json")
        )
        self.assertEqual(len(state_files), 1)
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "analysis_failed")
        self.assertEqual(state["attempt_counters"]["generate_content_attempts"], 1)

    def test_original_keyframe_request_never_attaches_reference_evidence(self):
        import torch

        master = fixture_response()
        master.update({"project_id": "creative_test", "status": "completed"})
        output = NODES.AdsArtPrepareOriginalKeyframe().prepare(
            json.dumps(fixture_brief()), json.dumps(master), torch.zeros((1, 64, 64, 3)),
            1, True, "", None,
        )
        request = json.loads(output["result"][0])
        self.assertEqual(request["model"], "nano_banana_pro")
        self.assertEqual(request["params"]["aspect_ratio"], "4:5")
        self.assertEqual(request["params"]["resolution"], "2k")
        self.assertEqual([item["kind"] for item in request["media"]], ["approved_ai_character"])
        self.assertFalse(request["metadata"]["reference_evidence_frame_forwarded"])
        self.assertNotIn("original_commercial_frame", json.dumps(request))

    def test_seedance_v2_uses_only_approved_original_keyframe_and_images(self):
        import torch

        image = torch.zeros((1, 80, 64, 3), dtype=torch.float32)
        output = NODES.AdsArtPrepareOriginalSeedanceShot().prepare(
            json.dumps(fixture_brief()), image, image, "shot_01", True, True,
            "She reveals the fictional object with a measured gesture.",
            "A restrained lateral drift.", "Slow build and concise reveal.",
            "Preserve the approved character and original mineral world.",
            "The approved original keyframe contains a mineral aperture.", "",
            5, 5.0, "auto", False, "1080p", False, "standard", None, None,
        )
        request = json.loads(output["result"][0])
        self.assertEqual(request["model"], "seedance_2_5")
        self.assertEqual(request["params"]["mode"], "omni_reference")
        self.assertTrue(all(item["role"] in {"image", "start_image", "end_image"} for item in request["media"]))
        self.assertEqual(request["media"][0]["kind"], "approved_original_keyframe")
        self.assertFalse(request["metadata"]["reference_video_forwarded"])
        self.assertFalse(request["metadata"]["reference_audio_forwarded"])
        self.assertFalse(request["metadata"]["reference_evidence_frame_forwarded"])

    def test_manual_original_shot_override_persists(self):
        master = fixture_response()
        master.update({"project_id": "creative_test", "status": "completed"})
        node = NODES.AdsArtOriginalShotDraft()
        first = node.materialize(json.dumps(master), 1, manual_environment="A user-defined obsidian room")
        second = node.materialize(json.dumps(master), 1, manual_environment="")
        self.assertEqual(json.loads(first["result"][0])["effective"]["environment"], "A user-defined obsidian room")
        self.assertEqual(json.loads(second["result"][0])["effective"]["environment"], "A user-defined obsidian room")

    def test_v2_workflow_is_valid_and_paid_nodes_are_off(self):
        workflow = json.loads((PACKAGE_ROOT / "workflows" / "ads_art_creative_intelligence_v2.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["nodes"]}
        self.assertEqual(workflow["version"], 0.4)
        self.assertEqual(len(nodes), 19)
        gemini = next(node for node in nodes.values() if node["type"] == "AdsArtGeminiCreativeIntelligence")
        self.assertNotIn("confirm_gemini_analysis", [item["name"] for item in gemini["inputs"]])
        submits = [node for node in nodes.values() if node["type"] == "AdsArtSubmitJob"]
        self.assertTrue(all(node["mode"] == 2 and node["widgets_values"][0] is False for node in submits))
        for link_id, source_id, source_slot, target_id, target_slot, link_type in workflow["links"]:
            self.assertIn(source_id, nodes)
            self.assertIn(target_id, nodes)
            self.assertEqual(nodes[source_id]["outputs"][source_slot]["type"], link_type)
            self.assertEqual(nodes[target_id]["inputs"][target_slot]["type"], link_type)
        for node in nodes.values():
            if node["type"] not in PACKAGE.NODE_CLASS_MAPPINGS:
                continue
            node_class = PACKAGE.NODE_CLASS_MAPPINGS[node["type"]]
            declared = node_class.INPUT_TYPES()
            expected_inputs = list(declared.get("required", {})) + list(declared.get("optional", {}))
            self.assertEqual([item["name"] for item in node["inputs"]], expected_inputs)
            self.assertEqual([item["type"] for item in node["outputs"]], list(node_class.RETURN_TYPES))

    def test_v2_sync_preserves_v1_identity_notes_and_identity_image(self):
        template = json.loads((PACKAGE_ROOT / "workflows" / "ads_art_creative_intelligence_v2.json").read_text(encoding="utf-8"))
        v1 = json.loads((PACKAGE_ROOT / "workflows" / "ads_art_prepare_v1.json").read_text(encoding="utf-8"))
        identity_request = next(node for node in v1["nodes"] if node["id"] == 7)
        identity_request["widgets_values"][0] = "Exact private identity notes"
        approved_identity = next(node for node in v1["nodes"] if node["id"] == 9)
        approved_identity["widgets_values"][0] = "approved-private.png"
        merged = SYNC.merge(template, None, v1)
        brief = next(node for node in merged["nodes"] if node["type"] == "AdsArtCreativeBrief")
        identity = next(node for node in merged["nodes"] if node["id"] == 2)
        self.assertEqual(SYNC.widget_map(brief)["identity_notes"], "Exact private identity notes")
        self.assertEqual(SYNC.widget_map(identity)["image"], "approved-private.png")
        self.assertTrue(all(node["mode"] == 2 for node in merged["nodes"] if node["type"] == "AdsArtSubmitJob"))

    def test_historical_reports_remain(self):
        self.assertTrue((PACKAGE_ROOT / "GEMINI_TEST_REPORT_2026-09-06.md").is_file())
        self.assertTrue((PACKAGE_ROOT / "GEMINI_36_TEST_REPORT_2026-09-06.md").is_file())

    def test_source_does_not_log_api_key_or_private_prompt(self):
        combined = "\n".join((PACKAGE_ROOT / name).read_text(encoding="utf-8") for name in ("ads_art_creative.py", "ads_art_creative_nodes.py"))
        self.assertNotIn("print(prompt", combined)
        self.assertNotRegex(combined, r"AIza[0-9A-Za-z_-]{20,}")
        self.assertNotIn("os.environ['GEMINI_API_KEY'] =", combined)


if __name__ == "__main__":
    unittest.main()

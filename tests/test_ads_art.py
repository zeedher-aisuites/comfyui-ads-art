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
    "ads_art_test_package",
    PACKAGE_ROOT / "__init__.py",
    submodule_search_locations=[str(PACKAGE_ROOT)],
)
PACKAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACKAGE
SPEC.loader.exec_module(PACKAGE)
CORE = sys.modules["ads_art_test_package.ads_art_core"]
NODES = sys.modules["ads_art_test_package.ads_art_nodes"]
GEMINI = sys.modules["ads_art_test_package.ads_art_gemini"]
SYNC_SPEC = importlib.util.spec_from_file_location(
    "ads_art_sync_workflow", PACKAGE_ROOT / "scripts" / "sync_workflow.py"
)
SYNC = importlib.util.module_from_spec(SYNC_SPEC)
SYNC_SPEC.loader.exec_module(SYNC)


class AdsArtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_user_dir = CORE._default_user_directory
        CORE._default_user_directory = lambda: Path(self.temp.name)

    def tearDown(self):
        CORE._default_user_directory = self.previous_user_dir
        self.temp.cleanup()

    def base_video_request(self):
        image = Path(self.temp.name) / "frame.png"
        image.write_bytes(b"not decoded in policy tests")
        return {
            "schema_version": "1.0.0",
            "request_id": "00000000-0000-0000-0000-000000000001",
            "project_id": "test_project",
            "stage": "video",
            "shot_id": "shot_001",
            "model": "seedance_2_5",
            "prompt": "A controlled continuous shot.",
            "params": {
                "model": "seedance_2_5",
                "mode": "omni_reference",
                "aspect_ratio": "auto",
                "resolution": "1080p",
                "duration": 5,
                "generate_audio": False,
                "bitrate_mode": "standard",
            },
            "media": [{"role": "start_image", "kind": "approved_recreated_frame", "path": str(image)}],
            "metadata": {"original_video_forwarded": False, "original_audio_forwarded": False},
            "conflicts": [],
            "status": "prepared",
        }

    def make_synthetic_video(self, name="two_shots.mp4"):
        import av
        import numpy as np

        video_path = Path(self.temp.name) / name
        container = av.open(str(video_path), mode="w")
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 64
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        for color in ((255, 0, 0), (0, 0, 255)):
            for _ in range(10):
                array = np.zeros((64, 64, 3), dtype=np.uint8)
                array[:, :] = color
                frame = av.VideoFrame.from_ndarray(array, format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        container.close()
        return video_path

    def test_node_package_imports(self):
        self.assertEqual(len(PACKAGE.NODE_CLASS_MAPPINGS), 14)
        self.assertIn("AdsArtPrepareVideoShot", PACKAGE.NODE_CLASS_MAPPINGS)
        self.assertIn("AdsArtRecoverJob", PACKAGE.NODE_CLASS_MAPPINGS)
        self.assertIn("AdsArtGeminiAnalyzeCommercial", PACKAGE.NODE_CLASS_MAPPINGS)
        self.assertIn("AdsArtGeminiShotDraft", PACKAGE.NODE_CLASS_MAPPINGS)

    def test_knowledge_base_is_the_supplied_catalog(self):
        knowledge = CORE.load_knowledge()
        self.assertEqual(knowledge["schema_version"], "1.0.0")
        self.assertEqual(len(knowledge["concepts"]), 31)
        self.assertEqual(knowledge["scope_es"].split(".")[0], "Catálogo editorial y contrato de integración")

    def test_prompt_conflict_blocks_explicit_keep_and_remove(self):
        conflicts = CORE.detect_prompt_conflicts(
            "Conservar el vestido rojo",
            "Eliminar el vestido rojo",
            "",
            "",
        )
        self.assertTrue(CORE.blocking_conflicts(conflicts))

    def test_creative_conflict_yields_to_restriction(self):
        conflicts = CORE.detect_prompt_conflicts(
            "",
            "Eliminar el fondo azul",
            "",
            "Mejorar el fondo azul",
        )
        self.assertTrue(conflicts)
        self.assertEqual(conflicts[0]["severity"], "warning")
        self.assertEqual(conflicts[0]["resolved_by_policy"], "restrictive_prompt")

    def test_seedance_valid_image_only_request(self):
        CORE.validate_generation_request(self.base_video_request())

    def test_seedance_rejects_original_video_even_with_image_role(self):
        request = self.base_video_request()
        request["media"][0]["path"] = str(Path(self.temp.name) / "commercial.mp4")
        with self.assertRaisesRegex(CORE.AdsArtError, "sólo puede recibir archivos de imagen"):
            CORE.validate_generation_request(request)

    def test_seedance_rejects_video_role(self):
        request = self.base_video_request()
        request["media"][0]["role"] = "video"
        with self.assertRaisesRegex(CORE.AdsArtError, "Rol de medio prohibido"):
            CORE.validate_generation_request(request)

    def test_seedance_rejects_prohibited_modes(self):
        for mode in ("video_edit", "video_extension"):
            request = self.base_video_request()
            request["params"]["mode"] = mode
            with self.assertRaisesRegex(CORE.AdsArtError, "video_edit y video_extension"):
                CORE.validate_generation_request(request)

    def test_seedance_does_not_inherit_image_4_by_5(self):
        request = self.base_video_request()
        request["params"]["aspect_ratio"] = "4:5"
        with self.assertRaisesRegex(CORE.AdsArtError, "4:5 no figura"):
            CORE.validate_generation_request(request)

    def test_image_request_is_locked(self):
        image = Path(self.temp.name) / "art.png"
        image.write_bytes(b"policy test")
        request = {
            "stage": "identity",
            "status": "prepared",
            "model": "nano_banana_pro",
            "prompt": "Hyperreal identity.",
            "params": {"model": "nano_banana_pro", "aspect_ratio": "4:5", "resolution": "2k"},
            "media": [{"role": "image", "path": str(image)}],
            "conflicts": [],
        }
        CORE.validate_generation_request(request)
        request["params"]["resolution"] = "1k"
        with self.assertRaisesRegex(CORE.AdsArtError, "requiere imágenes a 2k"):
            CORE.validate_generation_request(request)

    def test_internal_negative_prompt_is_not_native_param(self):
        request = self.base_video_request()
        request["params"]["negative_prompt"] = "bad anatomy"
        with self.assertRaisesRegex(CORE.AdsArtError, "no se envía como parámetro nativo"):
            CORE.validate_generation_request(request)

    def test_prepare_only_does_not_call_cli_or_submit(self):
        job = CORE.submit_request(self.base_video_request(), confirm_submission=False)
        self.assertEqual(job["status"], "prepared_not_submitted")
        self.assertFalse(job["paid_generation_submitted"])
        self.assertIsNone(job["job_id"])

    def test_uncertain_submission_is_never_retried(self):
        request = self.base_video_request()
        store = CORE.ProjectStore(request["project_id"])
        store.write_json(
            f"jobs/{request['request_id']}.json",
            {
                "request_id": request["request_id"],
                "status": "submission_unknown",
                "job_id": None,
            },
        )
        with self.assertRaisesRegex(CORE.SubmissionUncertainError, "No se volverá a enviar"):
            CORE.submit_request(request, confirm_submission=True)

    def test_recover_job_from_persisted_request_without_provider_call(self):
        request_id = "00000000-0000-0000-0000-000000000010"
        job_id = "00000000-0000-0000-0000-000000000011"
        store = CORE.ProjectStore("test_project")
        store.write_json(
            f"jobs/{request_id}.json",
            {
                "project_id": "test_project",
                "request_id": request_id,
                "shot_id": "identity",
                "stage": "identity",
                "status": "submitted",
                "job_id": job_id,
            },
        )
        recovered = CORE.recover_job_record(
            {"project_id": "test_project"}, request_id=request_id
        )
        self.assertEqual(recovered["job_id"], job_id)
        self.assertEqual(recovered["status"], "submitted")

    def test_recover_job_from_known_manual_job_id(self):
        job_id = "00000000-0000-0000-0000-000000000012"
        recovered = CORE.recover_job_record(
            {"project_id": "test_project"},
            job_id=job_id,
            shot_id="shot_001",
            stage="video",
        )
        self.assertEqual(recovered["job_id"], job_id)
        self.assertEqual(recovered["stage"], "video")
        self.assertTrue(
            CORE.ProjectStore("test_project")
            .path(f"jobs/recovered_{job_id}.json")
            .is_file()
        )

    def test_result_url_extraction_ignores_uploaded_reference_urls(self):
        payload = {
            "params": {"medias": [{"url": "https://example.test/reference.png"}]},
            "results": {"rawUrl": "https://example.test/generated.mp4"},
        }
        self.assertEqual(
            CORE._collect_result_urls(payload),
            ["https://example.test/generated.mp4"],
        )

    def test_local_video_analysis_detects_and_extracts_synthetic_cut(self):
        video_path = self.make_synthetic_video()

        cuts, duration, detections = NODES._shot_boundaries(video_path, 0.1, 0.2, 10.0)
        self.assertGreaterEqual(len(cuts), 2)
        self.assertTrue(detections)
        targets = [(cuts[0] + cuts[1]) / 2.0, (cuts[1] + duration) / 2.0]
        extracted = NODES._extract_representative_frames(
            video_path, targets, Path(self.temp.name) / "frames"
        )
        self.assertEqual(len(extracted), 2)
        self.assertTrue(all(path.is_file() for path in extracted))

    def test_gemini_model_and_schema_are_exact_and_bounded(self):
        self.assertEqual(GEMINI.GEMINI_MODEL_ID, "gemini-2.5-flash")
        schema = GEMINI.gemini_analysis_schema(3)
        self.assertEqual(schema["properties"]["shots"]["maxItems"], 3)
        shot_properties = schema["properties"]["shots"]["items"]["properties"]
        self.assertIn("observed", shot_properties)
        self.assertIn("proposal", shot_properties)

    def test_gemini_missing_key_fails_without_exposing_a_secret(self):
        previous = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with self.assertRaisesRegex(CORE.AdsArtError, "GEMINI_API_KEY"):
                GEMINI.require_gemini_api_key()
        finally:
            if previous is not None:
                os.environ["GEMINI_API_KEY"] = previous

    def test_gemini_response_validation_checks_timestamps_and_catalog(self):
        response = {
            "analysis_summary": "Two observed color fields.",
            "global_missing_information": ["Product is unspecified."],
            "shots": [
                {
                    "shot_id": "shot_001",
                    "observed": {
                        "start_seconds": 0.0,
                        "end_seconds": 1.0,
                        "candidate_timestamps": [0.5],
                        "description": "A red field.",
                        "selection_reason": "Stable frame away from the cut.",
                    },
                    "proposal": {
                        "objective": "Establish the scene.",
                        "action": "Hold.",
                        "framing_and_composition": "Centered.",
                        "lighting": "Even.",
                        "camera_concept_ids": ["eye_level"],
                        "elements_to_preserve": ["red field"],
                        "elements_to_remove": [],
                        "elements_to_replace": [],
                        "nano_banana_prompt": "Recreate the observed frame.",
                        "seedance": {
                            "performance": "Stillness.",
                            "camera_movement": "Locked.",
                            "rhythm": "Quiet.",
                            "continuity": "Preserve geometry.",
                        },
                        "unverified_product_details": ["No product defined."],
                    },
                    "uncertainties": [],
                    "contradictions": [],
                }
            ],
        }
        validated = GEMINI.validate_gemini_response(
            response,
            duration_seconds=2.0,
            max_shots=3,
            allowed_camera_ids={item["id"] for item in CORE.load_knowledge()["concepts"]},
        )
        self.assertEqual(validated["shots"][0]["proposal"]["camera_concept_ids"], ["eye_level"])
        response["shots"][0]["observed"]["candidate_timestamps"] = [1.5]
        with self.assertRaisesRegex(CORE.AdsArtError, "fuera de su intervalo"):
            GEMINI.validate_gemini_response(
                response,
                duration_seconds=2.0,
                max_shots=3,
                allowed_camera_ids={"eye_level"},
            )

    def test_gemini_cost_is_estimate_from_reported_tokens_only(self):
        cost = GEMINI.estimate_standard_paid_cost(
            {
                "prompt_token_count": 1_000_000,
                "candidates_token_count": 1_000_000,
                "thoughts_token_count": 0,
            }
        )
        self.assertEqual(cost["amount_usd"], 2.8)
        self.assertIsNone(cost["observed_charge_usd"])
        self.assertTrue(cost["pricing"]["estimate_only"])

    def test_gemini_audio_tokens_use_separate_rate(self):
        cost = GEMINI.estimate_standard_paid_cost(
            {
                "prompt_token_count": 2_000,
                "candidates_token_count": 100,
                "thoughts_token_count": 50,
                "prompt_tokens_details": [
                    {"modality": "VIDEO", "token_count": 720},
                    {"modality": "AUDIO", "token_count": 1_280},
                ],
            },
            audio_included=True,
            duration_seconds=40.0,
        )
        breakdown = cost["input_breakdown"]
        self.assertEqual(breakdown["audio_tokens_billed_at_audio_input_rate"], 1_280)
        self.assertEqual(
            breakdown["text_image_video_tokens_billed_at_standard_input_rate"], 720
        )
        self.assertEqual(breakdown["audio_token_source"], "provider_reported_modality")
        self.assertAlmostEqual(cost["amount_usd"], 0.001871)

    def test_gemini_first_run_limits_are_explicit(self):
        self.assertEqual(GEMINI.GEMINI_GENERATION_CONFIG["video_sampling_fps"], 2.0)
        self.assertEqual(GEMINI.GEMINI_GENERATION_CONFIG["thinking_budget"], 2048)
        self.assertEqual(GEMINI.GEMINI_GENERATION_CONFIG["max_output_tokens"], 8192)

    def test_gemini_prepare_local_only_makes_zero_remote_calls(self):
        video_path = self.make_synthetic_video("gemini_preflight.mp4")
        project = CORE.make_project(
            "gemini_preflight",
            "Keep the approved identity.",
            "Do not invent product details.",
            "No typography.",
            "Faithful luxury reinterpretation.",
            "auto",
            "1080p",
            False,
        )
        with mock.patch.object(
            NODES,
            "call_gemini_analysis",
            side_effect=AssertionError("remote call must not run"),
        ):
            output = NODES.AdsArtGeminiAnalyzeCommercial().analyze(
                json.dumps(project),
                str(video_path),
                "gemini-2.5-flash",
                "faithful_reference",
                3,
                0.1,
                0.2,
                10.0,
                False,
                False,
                True,
                False,
                2,
                10,
            )
        analysis = json.loads(output["result"][0])
        self.assertEqual(analysis["status"], "prepared_not_called")
        self.assertEqual(analysis["gemini"]["remote_calls"], 0)
        self.assertLessEqual(len(analysis["shots"]), 3)
        self.assertTrue(all(not shot["review"]["approved"] for shot in analysis["shots"]))
        self.assertFalse(analysis["original_video_forwarded_to_seedance"])
        self.assertFalse(analysis["original_audio_forwarded_to_seedance"])

    def test_manual_gemini_override_survives_blank_rerun(self):
        from PIL import Image

        frame = Path(self.temp.name) / "candidate.png"
        Image.new("RGB", (32, 32), (12, 34, 56)).save(frame)
        analysis = {
            "project_id": "override_test",
            "shots": [
                {
                    "shot_id": "shot_001",
                    "representative_timestamp": 0.5,
                    "selected_frame_path": str(frame),
                    "gemini_observed": {"selection_reason": "Stable."},
                    "gemini_proposal": {
                        "objective": "Generated objective",
                        "action": "Generated action",
                        "camera_concept_ids": ["eye_level"],
                        "framing_and_composition": "Centered",
                        "lighting": "Soft",
                        "elements_to_preserve": [],
                        "elements_to_remove": [],
                        "elements_to_replace": [],
                        "nano_banana_prompt": "Generated frame prompt",
                        "seedance": {
                            "performance": "Subtle movement",
                            "camera_movement": "Locked",
                            "rhythm": "Slow",
                            "continuity": "Stable",
                        },
                    },
                    "uncertainties": [],
                    "contradictions": [],
                }
            ],
        }
        node = NODES.AdsArtGeminiShotDraft()
        first = node.materialize(json.dumps(analysis), 1, manual_objective="User objective")
        second = node.materialize(json.dumps(analysis), 1, manual_objective="")
        self.assertEqual(json.loads(first["result"][0])["effective"]["objective"], "User objective")
        self.assertEqual(json.loads(second["result"][0])["effective"]["objective"], "User objective")

    def test_seedance_prompt_can_be_updated_from_approved_frame(self):
        import torch

        project = CORE.make_project(
            "seedance_draft",
            "Keep the approved identity.",
            "Do not invent the product.",
            "No typography.",
            "",
            "auto",
            "1080p",
            False,
        )
        draft = {
            "project_id": "seedance_draft",
            "shot_id": "shot_001",
            "effective": {
                "seedance_performance": "She turns slowly.",
                "seedance_camera_movement": "Locked eye-level camera.",
                "seedance_rhythm": "Measured pace.",
                "seedance_continuity": "Preserve the black gown.",
            },
        }
        frame = torch.zeros((1, 80, 64, 3), dtype=torch.float32)
        output = NODES.AdsArtPrepareVideoShot().prepare(
            json.dumps(project),
            frame,
            frame,
            "shot_001",
            True,
            True,
            "",
            "",
            "",
            "",
            "The approved frame shows a closed gold gate.",
            "Keep the fabric motion subtle.",
            5,
            5.0,
            "auto",
            False,
            "1080p",
            False,
            "standard",
            None,
            json.dumps(draft),
        )
        request = json.loads(output["result"][0])
        self.assertIn("She turns slowly.", request["prompt"])
        self.assertIn("closed gold gate", request["prompt"])
        self.assertTrue(request["metadata"]["prompt_updated_from_approved_frame"])
        self.assertTrue(all(item["role"] in {"image", "start_image", "end_image"} for item in request["media"]))
        self.assertFalse(request["metadata"]["original_video_forwarded"])
        self.assertFalse(request["metadata"]["original_audio_forwarded"])

    def test_workflow_sync_preserves_personal_widgets_and_forces_remote_off(self):
        template = json.loads(
            (PACKAGE_ROOT / "workflows" / "ads_art_prepare_v1.json").read_text(encoding="utf-8")
        )
        installed = copy.deepcopy(template)
        identity = next(item for item in installed["nodes"] if item["id"] == 7)
        identity["widgets_values"][0] = "Private identity notes that must survive."
        gemini = next(item for item in installed["nodes"] if item["id"] == 23)
        gemini["widgets_values"][8] = True
        submit = next(item for item in installed["nodes"] if item["type"] == "AdsArtSubmitJob")
        submit["widgets_values"][0] = True
        merged = SYNC.merge_workflow(
            template,
            installed,
            identity_image="approved.png",
        )
        identity_after = next(item for item in merged["nodes"] if item["id"] == 7)
        gemini_after = next(item for item in merged["nodes"] if item["id"] == 23)
        self.assertEqual(identity_after["widgets_values"][0], "Private identity notes that must survive.")
        self.assertFalse(gemini_after["widgets_values"][8])
        self.assertEqual(gemini_after["mode"], 0)
        self.assertTrue(
            all(
                node["widgets_values"][0] is False and node["mode"] == 2
                for node in merged["nodes"]
                if node["type"] == "AdsArtSubmitJob"
            )
        )

    def test_workflow_links_are_well_formed_and_submission_defaults_off(self):
        workflow_path = PACKAGE_ROOT / "workflows" / "ads_art_prepare_v1.json"
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["nodes"]}
        self.assertEqual(workflow["version"], 0.4)
        for link_id, source_id, source_slot, target_id, target_slot, link_type in workflow["links"]:
            self.assertIn(source_id, nodes)
            self.assertIn(target_id, nodes)
            self.assertLess(source_slot, len(nodes[source_id]["outputs"]))
            self.assertLess(target_slot, len(nodes[target_id]["inputs"]))
            self.assertEqual(nodes[source_id]["outputs"][source_slot]["type"], link_type)
            self.assertEqual(nodes[target_id]["inputs"][target_slot]["type"], link_type)
        submit_nodes = [node for node in nodes.values() if node["type"] == "AdsArtSubmitJob"]
        self.assertEqual(len(submit_nodes), 3)
        self.assertTrue(all(node["widgets_values"][0] is False for node in submit_nodes))

        for node in nodes.values():
            if node["type"] not in PACKAGE.NODE_CLASS_MAPPINGS:
                continue
            node_class = PACKAGE.NODE_CLASS_MAPPINGS[node["type"]]
            declared = node_class.INPUT_TYPES()
            expected_inputs = list(declared.get("required", {})) + list(declared.get("optional", {}))
            self.assertEqual([item["name"] for item in node["inputs"]], expected_inputs)
            expected_outputs = list(getattr(node_class, "RETURN_TYPES", ()))
            self.assertEqual([item["type"] for item in node["outputs"]], expected_outputs)


if __name__ == "__main__":
    unittest.main()

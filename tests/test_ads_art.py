import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


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

    def test_node_package_imports(self):
        self.assertEqual(len(PACKAGE.NODE_CLASS_MAPPINGS), 12)
        self.assertIn("AdsArtPrepareVideoShot", PACKAGE.NODE_CLASS_MAPPINGS)
        self.assertIn("AdsArtRecoverJob", PACKAGE.NODE_CLASS_MAPPINGS)

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
        import av
        import numpy as np

        video_path = Path(self.temp.name) / "two_shots.mp4"
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

        cuts, duration, detections = NODES._shot_boundaries(video_path, 0.1, 0.2, 10.0)
        self.assertGreaterEqual(len(cuts), 2)
        self.assertTrue(detections)
        targets = [(cuts[0] + cuts[1]) / 2.0, (cuts[1] + duration) / 2.0]
        extracted = NODES._extract_representative_frames(
            video_path, targets, Path(self.temp.name) / "frames"
        )
        self.assertEqual(len(extracted), 2)
        self.assertTrue(all(path.is_file() for path in extracted))

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

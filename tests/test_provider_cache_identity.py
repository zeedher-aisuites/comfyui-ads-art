"""Regression coverage for paid-request identity across local expander changes."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


FIXTURE_MODULE_NAME = "test_creative_intelligence"
if FIXTURE_MODULE_NAME not in sys.modules:
    fixture_spec = importlib.util.spec_from_file_location(
        FIXTURE_MODULE_NAME, Path(__file__).with_name("test_creative_intelligence.py")
    )
    fixture_module = importlib.util.module_from_spec(fixture_spec)
    sys.modules[FIXTURE_MODULE_NAME] = fixture_module
    fixture_spec.loader.exec_module(fixture_module)
FIXTURES = sys.modules[FIXTURE_MODULE_NAME]
CORE = FIXTURES.CORE
CREATIVE = FIXTURES.CREATIVE
GEMINI = FIXTURES.GEMINI
NODES = FIXTURES.NODES


class ProviderCacheIdentityTests(unittest.TestCase):
    setUp = FIXTURES.CreativeIntelligenceTests.setUp
    tearDown = FIXTURES.CreativeIntelligenceTests.tearDown

    def test_expander_change_preserves_exact_provider_prompt_and_request_signature(self):
        brief = FIXTURES.fixture_brief()
        prompt_args = (brief, {"concepts": []}, {"duration_seconds": 2}, True)
        signature_args = {
            "video_sha256": "video-a",
            "video_bytes": 123,
            "identity_sha256": "identity-a",
            "brief": brief,
            "knowledge_sha256": "knowledge-a",
            "local_detector": {"cut_timestamps": [0.0]},
        }
        original_prompt = CREATIVE.build_creative_intelligence_prompt(*prompt_args)
        original_signature = CREATIVE.creative_provider_request_signature(**signature_args)
        fingerprint = GEMINI.stable_fingerprint(original_signature)
        original_materialization = CREATIVE.creative_materialization_signature(fingerprint)

        with mock.patch.object(CREATIVE, "CREATIVE_EXPANDER_VERSION", "local-test-expander"):
            changed_prompt = CREATIVE.build_creative_intelligence_prompt(*prompt_args)
            changed_signature = CREATIVE.creative_provider_request_signature(**signature_args)
            changed_materialization = CREATIVE.creative_materialization_signature(fingerprint)

        self.assertEqual(changed_prompt, original_prompt)
        self.assertEqual(changed_signature, original_signature)
        self.assertNotEqual(changed_materialization, original_materialization)
        self.assertNotIn(
            "expander_version", json.loads(original_prompt[1])["compact_provider_contract"]
        )

    def test_expander_change_cannot_retry_failed_or_unknown_paid_request_without_raw(self):
        import torch

        video = FIXTURES.CreativeIntelligenceTests.make_video(self)
        for outcome, status_code in (("analysis_unknown", None), ("analysis_failed", 400)):
            with self.subTest(outcome=outcome):
                project_id = f"creative_{outcome}"
                args = (
                    json.dumps(FIXTURES.fixture_brief(project_id)),
                    str(video), "gemini-3.6-flash", "faithful_principles",
                    0.1, 0.2, 10.0, True, True, False, 1, 10,
                    torch.zeros((1, 64, 64, 3)),
                )
                provider_error = GEMINI.GeminiCallError(
                    "Simulated provider inference failure; no network is used.",
                    stage="inference",
                    outcome_status=outcome,
                    timings={},
                    availability=None,
                    provider_error_type="SimulatedError",
                    provider_status_code=status_code,
                    attempt_counters={
                        "model_preflight_attempts": 1,
                        "upload_attempts": 1,
                        "generate_content_attempts": 1,
                    },
                )
                node = NODES.AdsArtGeminiCreativeIntelligence()
                analysis_dir = (
                    Path(self.temp.name) / "ads_art" / "projects" / project_id
                    / "analysis" / "creative_intelligence"
                )
                with mock.patch.object(
                    NODES, "gemini_credentials_configured", return_value=True
                ), mock.patch.object(
                    NODES, "call_gemini_analysis", side_effect=provider_error
                ) as provider, mock.patch.object(
                    CORE, "submit_request", side_effect=AssertionError("Higgsfield must not run")
                ):
                    with self.assertRaises(GEMINI.GeminiCallError):
                        node.analyze(*args)
                    state_paths = list((analysis_dir / "state").glob("*.json"))
                    self.assertEqual(len(state_paths), 1)
                    original_state_path = state_paths[0]
                    original_state_bytes = original_state_path.read_bytes()
                    original_state = json.loads(original_state_bytes)
                    self.assertEqual(original_state["status"], outcome)
                    self.assertEqual(
                        original_state["attempt_counters"]["generate_content_attempts"], 1
                    )
                    self.assertTrue(original_state["provider_request_fingerprint"])
                    self.assertEqual(
                        list((analysis_dir / "provider_responses").glob("*.json")), []
                    )

                    with mock.patch.object(
                        CREATIVE, "CREATIVE_EXPANDER_VERSION", "local-test-expander"
                    ), mock.patch.object(
                        NODES, "CREATIVE_EXPANDER_VERSION", "local-test-expander"
                    ):
                        with self.assertRaisesRegex(CORE.AdsArtError, "No se repetirá"):
                            node.analyze(*args)

                    self.assertEqual(provider.call_count, 1)
                    self.assertEqual(original_state_path.read_bytes(), original_state_bytes)
                    self.assertEqual(list((analysis_dir / "state").glob("*.json")), state_paths)


if __name__ == "__main__":
    unittest.main()

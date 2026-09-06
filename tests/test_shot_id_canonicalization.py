"""Offline coverage for strict, case-insensitive original shot identifiers."""

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
NODES = FIXTURES.NODES


def validate(master):
    return CREATIVE.validate_creative_intelligence(
        master, duration_seconds=2.0, target_duration_seconds=10,
        min_shots=2, max_shots=3,
    )


class ShotIdCanonicalizationTests(unittest.TestCase):
    def test_provider_accepts_only_case_variants_and_preserves_raw(self):
        for value in ("SHOT_01", "Shot_01", "shot_01"):
            with self.subTest(shot_id=value):
                raw = FIXTURES.fixture_provider_response()
                raw["original_shot_plan"][0]["shot_id"] = value
                original = copy.deepcopy(raw)
                expanded = CREATIVE.expand_provider_creative_intelligence(raw)
                self.assertEqual(expanded["original_shot_plan"][0]["shot_id"], "shot_01")
                master = validate(expanded)
                self.assertEqual(master["original_shot_plan"][0]["shot_id"], "shot_01")
                self.assertEqual(raw, original)

    def test_direct_master_validation_canonicalizes_case(self):
        for value in ("SHOT_01", "Shot_01", "shot_01"):
            with self.subTest(shot_id=value):
                master = FIXTURES.fixture_response()
                master["original_shot_plan"][0]["shot_id"] = value
                validated = validate(master)
                self.assertEqual(validated["original_shot_plan"][0]["shot_id"], "shot_01")

    def test_invalid_formats_are_not_padded_trimmed_or_coerced(self):
        for value in (
            "SHOT_1", "shot_001", "take_01", "shot_01x", "xshot_01",
            " shot_01", "shot_01 ", "shot_01\n", "shot_\u0660\u0661",
            None, 1, True, {}, [],
        ):
            with self.subTest(shot_id=value):
                raw = FIXTURES.fixture_provider_response()
                raw["original_shot_plan"][0]["shot_id"] = value
                with self.assertRaises(CORE.AdsArtError):
                    CREATIVE.expand_provider_creative_intelligence(raw)
                master = FIXTURES.fixture_response()
                master["original_shot_plan"][0]["shot_id"] = value
                with self.assertRaises(CORE.AdsArtError):
                    validate(master)

    def test_provider_duplicates_are_detected_after_canonicalization(self):
        for first, second in (("SHOT_01", "shot_01"), ("Shot_01", "SHOT_01")):
            with self.subTest(first=first, second=second):
                raw = FIXTURES.fixture_provider_response()
                raw["original_shot_plan"][0]["shot_id"] = first
                raw["original_shot_plan"][1]["shot_id"] = second
                with self.assertRaisesRegex(CORE.AdsArtError, "duplicado"):
                    validate(CREATIVE.expand_provider_creative_intelligence(raw))

    def test_direct_master_duplicates_are_case_insensitive(self):
        for first, second in (("SHOT_01", "shot_01"), ("Shot_01", "SHOT_01")):
            with self.subTest(first=first, second=second):
                master = FIXTURES.fixture_response()
                master["original_shot_plan"][0]["shot_id"] = first
                master["original_shot_plan"][1]["shot_id"] = second
                with self.assertRaisesRegex(CORE.AdsArtError, "duplicado"):
                    validate(master)

    def test_node_persists_canonical_ids_and_keeps_provider_raw_unchanged(self):
        import torch

        with tempfile.TemporaryDirectory() as directory:
            self.temp = type("TemporaryProject", (), {"name": directory})()
            video = FIXTURES.CreativeIntelligenceTests.make_video(self)
            raw = FIXTURES.fixture_provider_response()
            raw["original_shot_plan"][0]["shot_id"] = "SHOT_01"
            raw["original_shot_plan"][1]["shot_id"] = "Shot_02"
            original_raw = copy.deepcopy(raw)
            call_result = {
                "response": raw, "usage": {}, "cost_estimate": {}, "timings": {},
                "provider": {"attempt_counters": {
                    "model_preflight_attempts": 1, "upload_attempts": 1,
                    "generate_content_attempts": 1,
                }},
            }
            args = (
                json.dumps(FIXTURES.fixture_brief()), str(video), "gemini-3.6-flash",
                "faithful_principles", 0.1, 0.2, 10.0, True, True, False, 1, 10,
                torch.zeros((1, 64, 64, 3)),
            )
            with mock.patch.object(CORE, "_default_user_directory", return_value=Path(directory)), \
                    mock.patch.object(NODES, "gemini_credentials_configured", return_value=True), \
                    mock.patch.object(NODES, "call_gemini_analysis", return_value=call_result) as provider, \
                    mock.patch.object(CORE, "submit_request", side_effect=AssertionError("Higgsfield must not run")), \
                    mock.patch("socket.create_connection", side_effect=AssertionError("Network must not run")):
                node = NODES.AdsArtGeminiCreativeIntelligence()
                result = node.analyze(*args)
                cached_result = node.analyze(*args)
            provider.assert_called_once()
            self.assertIn("CACHE HIT", cached_result["ui"]["text"][0])
            self.assertEqual(raw, original_raw)
            master = json.loads(result["result"][0])
            self.assertEqual(master["status"], "completed")
            expected_ids = ["shot_01", "shot_02"]
            self.assertEqual([shot["shot_id"] for shot in master["original_shot_plan"]], expected_ids)
            project = Path(directory) / "ads_art" / "projects" / "creative_test"
            analysis = project / "analysis" / "creative_intelligence"
            cache_paths = list((analysis / "cache").glob("*.json"))
            self.assertEqual(len(cache_paths), 1)
            for path in (cache_paths[0], analysis / "master.json"):
                persisted = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(persisted["status"], "completed")
                self.assertEqual([shot["shot_id"] for shot in persisted["original_shot_plan"]], expected_ids)
            plan = json.loads((project / "shots" / "original_plan.json").read_text(encoding="utf-8"))
            self.assertEqual([shot["shot_id"] for shot in plan["shots"]], expected_ids)
            raw_paths = list((analysis / "provider_responses").glob("*.json"))
            self.assertEqual(len(raw_paths), 1)
            persisted_raw = json.loads(raw_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(persisted_raw["provider_raw_json"], original_raw)


if __name__ == "__main__":
    unittest.main()

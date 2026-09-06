"""ComfyUI nodes for automatic creative intelligence and original ad generation."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import torch

from .ads_art_core import (
    AdsArtError,
    IMAGE_ASPECT_RATIO,
    IMAGE_MODEL_ID,
    IMAGE_RESOLUTION,
    ProjectStore,
    compile_controls,
    json_dumps,
    load_image_tensor,
    load_knowledge,
    make_request,
    parse_json,
    resolve_input_path,
    save_image_tensor,
    utc_now,
)
from .ads_art_creative import (
    CREATIVE_PROMPT_VERSION,
    CREATIVE_SCHEMA_VERSION,
    build_creative_intelligence_prompt,
    creative_intelligence_schema,
    creative_signature,
    validate_creative_brief,
    validate_creative_intelligence,
)
from .ads_art_gemini import (
    GEMINI_GENERATION_CONFIG,
    GEMINI_MODEL_ID,
    call_gemini_analysis,
    gemini_credentials_configured,
    sha256_file,
    stable_fingerprint,
)
from .ads_art_nodes import (
    AdsArtPrepareVideoShot,
    _probe_video_metadata,
    _select_clean_candidate_frame,
    _shot_boundaries,
    _ui_result,
)


def _multiline(default: str = "") -> tuple[str, dict[str, Any]]:
    return "STRING", {"multiline": True, "default": default}


class AdsArtCreativeBrief:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project_id": ("STRING", {"default": "ads_art_project_001"}),
                "character_name": ("STRING", {"default": "Madame X"}),
                "identity_notes": _multiline(),
                "character_personality": _multiline(),
                "character_archetype": _multiline(),
                "character_style_constraints": _multiline(),
                "brand_creation_mode": (["ai_propose", "user_defined"], {"default": "ai_propose"}),
                "fictional_brand_name": ("STRING", {"default": ""}),
                "product_category": ("STRING", {"default": ""}),
                "product_description": _multiline(),
                "audience": _multiline(),
                "positioning": _multiline(),
                "emotional_promise": _multiline(),
                "visual_brand_world": _multiline(),
                "brand_constraints": _multiline(),
                "required_elements": _multiline(),
                "forbidden_elements": _multiline(),
                "user_constraints": _multiline(),
                "target_duration_seconds": ("INT", {"default": 15, "min": 5, "max": 40}),
                "min_original_shots": ("INT", {"default": 4, "min": 1, "max": 16}),
                "max_original_shots": ("INT", {"default": 7, "min": 1, "max": 16}),
            }
        }

    RETURN_TYPES = ("ADS_ART_CREATIVE_PROJECT", "ADS_ART_PROJECT", "STRING")
    RETURN_NAMES = ("creative_project", "compatible_project", "brief_status")
    FUNCTION = "configure"
    CATEGORY = "Ads Art v2/00 Project Brand Character"
    OUTPUT_NODE = True
    DESCRIPTION = "Define character, fictional brand/product authority and original-ad constraints."

    def configure(self, **values):
        brief = {
            "schema_version": CREATIVE_SCHEMA_VERSION,
            "product_paradigm": "reference_driven_advertising_intelligence_original_generation",
            "project_id": str(values["project_id"]).strip(),
            "character": {
                "name": str(values["character_name"]).strip(),
                "identity_notes": str(values["identity_notes"]).strip(),
                "personality": str(values["character_personality"]).strip(),
                "archetype": str(values["character_archetype"]).strip(),
                "style_constraints": str(values["character_style_constraints"]).strip(),
                "approval_status": "user_approved_identity_required",
            },
            "brand": {
                "creation_mode": str(values["brand_creation_mode"]),
                "name": str(values["fictional_brand_name"]).strip(),
                "source": "ai_proposed" if values["brand_creation_mode"] == "ai_propose" else "user_provided",
            },
            "product": {
                "category": str(values["product_category"]).strip(),
                "description": str(values["product_description"]).strip(),
                "source": "ai_proposed_when_missing" if values["brand_creation_mode"] == "ai_propose" else "user_provided",
            },
            "audience": str(values["audience"]).strip(),
            "positioning": str(values["positioning"]).strip(),
            "emotional_promise": str(values["emotional_promise"]).strip(),
            "visual_brand_world": str(values["visual_brand_world"]).strip(),
            "brand_constraints": str(values["brand_constraints"]).strip(),
            "required_elements": str(values["required_elements"]).strip(),
            "forbidden_elements": str(values["forbidden_elements"]).strip(),
            "user_constraints": str(values["user_constraints"]).strip(),
            "target_duration_seconds": int(values["target_duration_seconds"]),
            "min_original_shots": int(values["min_original_shots"]),
            "max_original_shots": int(values["max_original_shots"]),
            "controls": {
                "positive_prompt": str(values["required_elements"]).strip(),
                "restrictive_prompt": str(values["brand_constraints"]).strip(),
                "negative_prompt": str(values["forbidden_elements"]).strip(),
                "creative_prompt": str(values["user_constraints"]).strip(),
            },
            "conflicts": [],
            "ready": True,
        }
        validate_creative_brief(brief)
        path = ProjectStore(brief["project_id"]).write_json("creative_project.json", brief)
        report = (
            f"CREATIVE BRIEF READY | {brief['project_id']}\n"
            f"Character: {brief['character']['name']}\n"
            f"Brand authority: {brief['brand']['creation_mode']}\n"
            f"Original ad: {brief['target_duration_seconds']}s | "
            f"{brief['min_original_shots']}-{brief['max_original_shots']} shots\n"
            f"Persisted: {path}\n"
            "This brief authorizes analysis only. No paid generation is authorized."
        )
        serialized = json_dumps(brief)
        return _ui_result((serialized, serialized, report), report)


def _evidence_batch(master: dict[str, Any]) -> torch.Tensor:
    paths = [Path(str(item.get("frame_path", ""))) for item in master.get("evidence", [])]
    if not paths or any(not path.is_file() for path in paths):
        raise AdsArtError("Creative intelligence no contiene todos los frames de evidencia.")
    return torch.cat([load_image_tensor(path) for path in paths], dim=0)


class AdsArtGeminiCreativeIntelligence:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "creative_project": ("ADS_ART_CREATIVE_PROJECT",),
                "reference_video": ("STRING", {"default": ""}),
                "model": ([GEMINI_MODEL_ID], {"default": GEMINI_MODEL_ID}),
                "analysis_mode": (["faithful_principles", "bold_reinterpretation"], {"default": "faithful_principles"}),
                "scene_threshold": ("FLOAT", {"default": 0.22, "min": 0.02, "max": 1.0, "step": 0.01}),
                "min_reference_shot_seconds": ("FLOAT", {"default": 0.5, "min": 0.1, "max": 30.0, "step": 0.1}),
                "local_detector_fps": ("FLOAT", {"default": 6.0, "min": 0.5, "max": 30.0, "step": 0.5}),
                "identity_approved": ("BOOLEAN", {"default": True}),
                "reuse_matching_analysis": ("BOOLEAN", {"default": True}),
                "allow_retry_after_unknown": ("BOOLEAN", {"default": False}),
                "upload_retries": ("INT", {"default": 1, "min": 1, "max": 1}),
                "file_poll_attempts": ("INT", {"default": 60, "min": 1, "max": 120}),
                "approved_identity": ("IMAGE",),
            }
        }

    RETURN_TYPES = (
        "ADS_ART_CREATIVE_INTELLIGENCE", "IMAGE", "STRING", "STRING", "STRING", "STRING", "STRING"
    )
    RETURN_NAMES = (
        "creative_intelligence", "reference_evidence_frames", "creative_dna",
        "transfer_rules", "original_adaptation", "original_shot_plan", "unresolved_inputs",
    )
    FUNCTION = "analyze"
    CATEGORY = "Ads Art v2/02 Automatic Creative Intelligence"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "Automatically analyzes reference DNA and creates an original ad plan. Evidence is never a generation target."
    )

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def analyze(
        self,
        creative_project,
        reference_video,
        model,
        analysis_mode,
        scene_threshold,
        min_reference_shot_seconds,
        local_detector_fps,
        identity_approved,
        reuse_matching_analysis,
        allow_retry_after_unknown,
        upload_retries,
        file_poll_attempts,
        approved_identity,
    ):
        node_started = time.monotonic()
        brief = validate_creative_brief(parse_json(creative_project, "creative_project"))
        if model != GEMINI_MODEL_ID:
            raise AdsArtError(f"Ads Art v2 requiere exactamente {GEMINI_MODEL_ID}; no existe fallback.")
        if not bool(identity_approved):
            raise AdsArtError("La identidad central debe estar aprobada antes del análisis creativo automático.")
        source = resolve_input_path(reference_video)
        metadata = _probe_video_metadata(source)
        cuts, decoded_duration, detections = _shot_boundaries(
            source, float(scene_threshold), float(min_reference_shot_seconds), float(local_detector_fps)
        )
        duration = max(float(metadata["duration_seconds"]), float(decoded_duration))
        metadata["duration_seconds"] = round(duration, 6)
        cuts = sorted({round(min(max(float(value), 0.0), duration), 6) for value in cuts})
        if not cuts or cuts[0] != 0.0:
            cuts.insert(0, 0.0)
        store = ProjectStore(brief["project_id"])
        identity_path = store.path("references", "creative_intelligence", "approved_identity.png")
        save_image_tensor(approved_identity, identity_path)
        knowledge = load_knowledge()
        local_observation = {
            "role": "reference_evidence_only_not_generation_target",
            "source_filename": source.name,
            "duration_seconds": round(duration, 6),
            "width": metadata["width"],
            "height": metadata["height"],
            "fps": metadata["fps"],
            "has_audio": metadata["has_audio"],
            "gemini_static_video_fps": GEMINI_GENERATION_CONFIG["video_sampling_fps"],
            "audio_included_for_analysis": bool(metadata["has_audio"]),
            "detector": {
                "type": "local_mean_absolute_visual_change",
                "scene_threshold": float(scene_threshold),
                "min_reference_shot_seconds": float(min_reference_shot_seconds),
                "local_detector_fps": float(local_detector_fps),
                "cut_timestamps": cuts,
                "detections": detections,
            },
        }
        brief_for_prompt = {**brief, "analysis_mode": str(analysis_mode)}
        system_instruction, prompt = build_creative_intelligence_prompt(
            brief_for_prompt, knowledge, local_observation, True
        )
        signature = creative_signature(
            video_sha256=sha256_file(source),
            video_bytes=source.stat().st_size,
            identity_sha256=sha256_file(identity_path),
            brief=brief_for_prompt,
            knowledge_sha256=stable_fingerprint(knowledge),
            local_detector=local_observation["detector"],
        )
        cache_key = stable_fingerprint(signature)
        cache_relative = f"analysis/creative_intelligence/cache/{cache_key}.json"
        state_relative = f"analysis/creative_intelligence/state/{cache_key}.json"
        cached = store.read_json(cache_relative) if bool(reuse_matching_analysis) else None
        if cached and cached.get("status") == "completed":
            cached["cache_reused_at"] = utc_now()
            return self._result(cached, cache_status="CACHE HIT")
        if not gemini_credentials_configured():
            raise AdsArtError(
                "Falta GEMINI_API_KEY para el análisis creativo automático y no existe una caché válida. "
                "Defínala sólo en el entorno privado que inicia ComfyUI. No se subió ningún medio."
            )
        marker = store.read_json(state_relative)
        if marker and marker.get("status") in {"analysis_started", "analysis_unknown", "analysis_failed"} and not bool(allow_retry_after_unknown):
            raise AdsArtError(
                "Existe un análisis creativo iniciado, fallido o incierto para esta huella. "
                "No se repetirá automáticamente; revise el estado antes de habilitar el override manual."
            )
        started = {
            "schema_version": CREATIVE_SCHEMA_VERSION,
            "status": "analysis_started",
            "cache_key": cache_key,
            "signature": signature,
            "model": GEMINI_MODEL_ID,
            "started_at": utc_now(),
            "inference_attempts": int((marker or {}).get("inference_attempts", 0) or 0) + 1,
            "automatic_retry": False,
            "api_key_persisted": False,
        }
        store.write_json(state_relative, started)
        try:
            call_result = call_gemini_analysis(
                video_path=source,
                approved_identity_path=identity_path,
                system_instruction=system_instruction,
                prompt=prompt,
                response_schema=creative_intelligence_schema(
                    brief["min_original_shots"], brief["max_original_shots"]
                ),
                source_has_audio=bool(metadata["has_audio"]),
                duration_seconds=duration,
                upload_retries=1,
                file_poll_attempts=int(file_poll_attempts),
            )
            response = validate_creative_intelligence(
                call_result["response"],
                duration_seconds=duration,
                target_duration_seconds=brief["target_duration_seconds"],
                min_shots=brief["min_original_shots"],
                max_shots=brief["max_original_shots"],
            )
            extraction_started = time.monotonic()
            evidence_dir = store.directory("frames", "reference_evidence", cache_key)
            for item in response["evidence"]:
                quality = _select_clean_candidate_frame(
                    source,
                    item["candidate_timestamps"],
                    float(item["shot_start_seconds"]),
                    float(item["shot_end_seconds"]),
                    cuts[1:],
                    evidence_dir / f"{item['evidence_id']}.png",
                )
                item["requested_timestamp_seconds"] = item["timestamp_seconds"]
                item["timestamp_seconds"] = quality["selected_timestamp"]
                item["frame_path"] = quality["selected_frame_path"]
                item["frame_role"] = "REFERENCE_EVIDENCE_ONLY_NOT_GENERATION_TARGET"
                item["local_frame_validation"] = quality
            call_result["timings"]["evidence_frame_extraction_seconds"] = round(
                time.monotonic() - extraction_started, 3
            )
            call_result["timings"]["total_node_seconds"] = round(time.monotonic() - node_started, 3)
            master = {
                **response,
                "schema_version": CREATIVE_SCHEMA_VERSION,
                "status": "completed",
                "project_id": brief["project_id"],
                "product_paradigm": "reference_driven_advertising_intelligence_original_generation",
                "reference_media_role": "evidence_only_not_generation_target",
                "source_video_path": str(source),
                "creative_brief": brief_for_prompt,
                "gemini": {
                    "model": GEMINI_MODEL_ID,
                    "prompt_version": CREATIVE_PROMPT_VERSION,
                    "generation_config": GEMINI_GENERATION_CONFIG,
                    "cache_key": cache_key,
                    "cache_status": "REMOTE ANALYSIS",
                    "signature": signature,
                    "provider": call_result["provider"],
                    "timings": call_result["timings"],
                    "usage": call_result["usage"],
                    "cost": call_result["cost_estimate"],
                    "prompt": prompt,
                    "system_instruction": system_instruction,
                    "automatic_analysis": True,
                    "human_confirmation_required": False,
                    "automatic_retry_performed": False,
                },
                "safety": {
                    "reference_video_forwarded_to_nano": False,
                    "reference_frames_forwarded_to_nano": False,
                    "reference_video_forwarded_to_seedance": False,
                    "reference_audio_forwarded_to_seedance": False,
                    "paid_generation_submitted": False,
                    "visual_approval_inferred": False,
                },
            }
        except Exception as exc:
            started.update(
                {
                    "status": getattr(exc, "outcome_status", "analysis_unknown"),
                    "failed_at": utc_now(),
                    "failure_stage": getattr(exc, "stage", "validation_or_materialization"),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "automatic_retry_performed": False,
                }
            )
            store.write_json(state_relative, started)
            raise
        cache_path = store.write_json(cache_relative, master)
        master["record_path"] = str(cache_path)
        store.write_json("analysis/reference/latest.json", {
            "schema_version": CREATIVE_SCHEMA_VERSION,
            "reference_observation": master["reference_observation"],
            "reference_interpretation": master["reference_interpretation"],
            "reference_strategy": master["reference_strategy"],
            "evidence": master["evidence"],
        })
        store.write_json("analysis/creative_intelligence/master.json", master)
        store.write_json("adaptation/original_adaptation.json", master["original_adaptation"])
        store.write_json("shots/original_plan.json", {
            "schema_version": CREATIVE_SCHEMA_VERSION,
            "target_duration_seconds": brief["target_duration_seconds"],
            "shots": master["original_shot_plan"],
        })
        store.write_json(state_relative, {**started, "status": "completed", "completed_at": utc_now(), "cache_path": str(cache_path)})
        return self._result(master, cache_status="REMOTE ANALYSIS")

    def _result(self, master: dict[str, Any], *, cache_status: str):
        interpretation = master["reference_interpretation"]
        strategy = master["reference_strategy"]
        creative_dna = json_dumps({
            "cache_status": cache_status,
            "observation": master["reference_observation"],
            "interpretation": interpretation,
            "strategy": strategy,
        })
        transfer = json_dumps(master["transfer_rules"])
        adaptation = json_dumps(master["original_adaptation"])
        plan = json_dumps({
            "target_duration_seconds": master["creative_brief"]["target_duration_seconds"],
            "shots": master["original_shot_plan"],
        })
        unresolved = json_dumps({
            "unresolved_inputs": master["provenance"]["unresolved_inputs"],
            "user_provided": master["provenance"]["user_provided"],
            "ai_proposed": master["provenance"]["ai_proposed"],
            "approved": master["provenance"]["approved"],
        })
        report = (
            f"CREATIVE INTELLIGENCE COMPLETE | {cache_status}\n"
            f"Model: {GEMINI_MODEL_ID}\n"
            f"Reference evidence frames: {len(master['evidence'])}\n"
            f"Original shots: {len(master['original_shot_plan'])}\n"
            "Evidence is reference-only; it is not a Nano or Seedance target.\n"
            "Paid generation submitted: NO | Visual approval inferred: NO"
        )
        return _ui_result(
            (json_dumps(master), _evidence_batch(master), creative_dna, transfer, adaptation, plan, unresolved),
            report,
        )


class AdsArtCreativeIntelligenceViewer:
    SECTIONS = [
        "creative_dna", "psychology_and_hooks", "visual_camera_lighting",
        "editing_and_audio", "reference_evidence", "transfer_rules",
        "original_adaptation", "original_shot_plan", "provenance_and_unresolved",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"creative_intelligence": ("ADS_ART_CREATIVE_INTELLIGENCE",), "section": (cls.SECTIONS,)}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("inspection",)
    FUNCTION = "view"
    CATEGORY = "Ads Art v2/03 Inspect Intelligence"
    OUTPUT_NODE = True

    def view(self, creative_intelligence, section):
        data = parse_json(creative_intelligence, "creative_intelligence")
        mapping = {
            "creative_dna": {"observation": data["reference_observation"], "interpretation": data["reference_interpretation"]},
            "psychology_and_hooks": data["reference_interpretation"],
            "visual_camera_lighting": {key: data["reference_strategy"][key] for key in ("visual_grammar", "camera_language", "lighting_language")},
            "editing_and_audio": {key: data["reference_strategy"][key] for key in ("editing_rhythm", "audio_strategy", "product_reveal_strategy", "brand_memory_strategy")},
            "reference_evidence": {"role": data["reference_media_role"], "items": data["evidence"]},
            "transfer_rules": data["transfer_rules"],
            "original_adaptation": data["original_adaptation"],
            "original_shot_plan": data["original_shot_plan"],
            "provenance_and_unresolved": data["provenance"],
        }
        text = f"{section.upper()}\n\n{json_dumps(mapping[section])}"
        return _ui_result((text,), text)


class AdsArtOriginalShotDraft:
    @classmethod
    def INPUT_TYPES(cls):
        multiline = {"multiline": True, "default": ""}
        return {
            "required": {
                "creative_intelligence": ("ADS_ART_CREATIVE_INTELLIGENCE",),
                "shot_number": ("INT", {"default": 1, "min": 1, "max": 16}),
                "manual_character_action": ("STRING", multiline),
                "manual_environment": ("STRING", multiline),
                "manual_composition": ("STRING", multiline),
                "manual_lighting": ("STRING", multiline),
                "manual_nano_banana_prompt": ("STRING", multiline),
                "manual_seedance_direction": ("STRING", multiline),
                "manual_differentiation_notes": ("STRING", multiline),
            }
        }

    RETURN_TYPES = ("ADS_ART_SHOT_DRAFT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("original_shot_draft", "nano_banana_prompt", "seedance_direction", "shot_report")
    FUNCTION = "materialize"
    CATEGORY = "Ads Art v2/05 Original Shot Plan"
    OUTPUT_NODE = True

    def materialize(self, creative_intelligence, shot_number, **manual_values):
        master = parse_json(creative_intelligence, "creative_intelligence")
        index = int(shot_number) - 1
        if index < 0 or index >= len(master.get("original_shot_plan", [])):
            raise AdsArtError("shot_number está fuera del plan original.")
        shot = master["original_shot_plan"][index]
        store = ProjectStore(master["project_id"])
        relative = f"analysis/creative_intelligence/manual_overrides/{shot['shot_id']}.json"
        previous = store.read_json(relative) or {}
        overrides = dict(previous.get("values", {}))
        overrides.update({key.removeprefix("manual_"): str(value).strip() for key, value in manual_values.items() if str(value or "").strip()})
        if overrides:
            store.write_json(relative, {
                "schema_version": CREATIVE_SCHEMA_VERSION,
                "shot_id": shot["shot_id"],
                "updated_at": utc_now(),
                "values": overrides,
                "policy": "nonempty_manual_values_override_ai_and_survive_reanalysis",
            })
        seedance = shot["seedance_direction"]
        generated = {
            **shot,
            "seedance_performance": seedance["performance"],
            "seedance_camera_movement": seedance["camera_movement"],
            "seedance_rhythm": seedance["pacing"],
            "seedance_continuity": seedance["continuity"],
        }
        effective = {**generated, **overrides}
        if "seedance_direction" in overrides:
            effective["seedance_performance"] = overrides["seedance_direction"]
        draft = {
            "schema_version": CREATIVE_SCHEMA_VERSION,
            "project_id": master["project_id"],
            "shot_id": shot["shot_id"],
            "shot_number": int(shot_number),
            "source": "original_ad_plan_not_reference_evidence",
            "generated": generated,
            "manual_overrides": overrides,
            "effective": effective,
            "visual_approval_inferred": False,
            "updated_at": utc_now(),
        }
        seedance_text = json_dumps(shot["seedance_direction"]) if "seedance_direction" not in overrides else overrides["seedance_direction"]
        report = (
            f"{shot['shot_id']} | ORIGINAL SHOT | {shot['planned_duration_seconds']}s\n"
            f"Purpose: {shot['purpose']}\nPsychology: {shot['psychological_function']}\n"
            f"Reference principles used: {' | '.join(shot['reference_principles_used'])}\n"
            f"Literal elements avoided: {' | '.join(shot['literal_reference_elements_avoided'])}\n"
            f"Differentiation: {' | '.join(shot['differentiation_notes'])}\n\n"
            f"NANO BANANA PRO:\n{effective['nano_banana_prompt']}\n\nSEEDANCE:\n{seedance_text}\n\n"
            "No reference frame is a generation target. Manual non-empty fields persist."
        )
        return _ui_result((json_dumps(draft), effective["nano_banana_prompt"], seedance_text, report), report)


class AdsArtPrepareOriginalKeyframe:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "creative_project": ("ADS_ART_CREATIVE_PROJECT",),
                "creative_intelligence": ("ADS_ART_CREATIVE_INTELLIGENCE",),
                "approved_identity": ("IMAGE",),
                "shot_number": ("INT", {"default": 1, "min": 1, "max": 16}),
                "identity_approved": ("BOOLEAN", {"default": True}),
                "manual_prompt_adjustments": _multiline(),
            },
            "optional": {"original_shot_draft": ("ADS_ART_SHOT_DRAFT",)},
        }

    RETURN_TYPES = ("ADS_ART_REQUEST", "STRING")
    RETURN_NAMES = ("original_keyframe_request", "request_preview")
    FUNCTION = "prepare"
    CATEGORY = "Ads Art v2/06 Nano Original Keyframes"
    OUTPUT_NODE = True

    def prepare(self, creative_project, creative_intelligence, approved_identity, shot_number, identity_approved, manual_prompt_adjustments, original_shot_draft=None):
        brief = validate_creative_brief(parse_json(creative_project, "creative_project"))
        master = parse_json(creative_intelligence, "creative_intelligence")
        index = int(shot_number) - 1
        if index < 0 or index >= len(master.get("original_shot_plan", [])):
            raise AdsArtError("shot_number está fuera del plan original.")
        shot = dict(master["original_shot_plan"][index])
        if original_shot_draft:
            draft = parse_json(original_shot_draft, "original_shot_draft")
            if draft.get("project_id") != brief["project_id"] or draft.get("shot_id") != shot["shot_id"]:
                raise AdsArtError("El borrador original pertenece a otro proyecto o toma.")
            shot.update(draft.get("effective") or {})
        store = ProjectStore(brief["project_id"])
        identity_path = store.path("references", shot["shot_id"], "approved_identity_for_original_keyframe.png")
        save_image_tensor(approved_identity, identity_path)
        prompt = f"""Generate one ORIGINAL advertising keyframe for the supplied original shot plan.
Do not recreate, trace, replace, or match any shot, pose, blocking, background, composition, product, logo, packaging, claim, or character from the reference commercial. Reference-derived principles are abstract strategy only; no reference frame is supplied.

AI CHARACTER:
{json_dumps(brief['character'])}

FICTIONAL BRAND / PRODUCT BRIEF:
{json_dumps({'brand': brief['brand'], 'product': brief['product'], 'audience': brief['audience'], 'positioning': brief['positioning'], 'emotional_promise': brief['emotional_promise'], 'visual_brand_world': brief['visual_brand_world']})}

ORIGINAL SHOT:
{json_dumps(shot)}

USER PROMPT ADJUSTMENTS:
{str(manual_prompt_adjustments or '').strip() or '(none)'}

Create a coherent production-ready still with the approved AI character identity. No unrequested typography or legal copy. One image only."""
        controls = compile_controls(brief, "frame")
        if controls:
            prompt += "\n\n" + controls
        request = make_request(
            brief,
            "frame",
            shot["shot_id"],
            prompt,
            {"model": IMAGE_MODEL_ID, "aspect_ratio": IMAGE_ASPECT_RATIO, "resolution": IMAGE_RESOLUTION},
            [{"role": "image", "kind": "approved_ai_character", "path": str(identity_path), "approved": bool(identity_approved)}],
            approvals={"identity": bool(identity_approved)},
            metadata={
                "generation_target": "original_keyframe_for_original_shot_plan",
                "reference_video_forwarded": False,
                "reference_audio_forwarded": False,
                "reference_evidence_frame_forwarded": False,
                "generated_result_requires_user_approval": True,
                "paid_submission_requires_explicit_confirmation": True,
            },
        )
        report = (
            f"{shot['shot_id']} | ORIGINAL KEYFRAME REQUEST | {request['status'].upper()}\n"
            f"Model: {IMAGE_MODEL_ID} | {IMAGE_ASPECT_RATIO} | {IMAGE_RESOLUTION}\n"
            "Reference commercial media attached: NO\nPaid submission: NO\n\n"
            + request["prompt"]
        )
        return _ui_result((json_dumps(request), report), report)


class AdsArtPrepareOriginalSeedanceShot:
    """Compatibility adapter with v2 language and an original-keyframe contract."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("ADS_ART_PROJECT",),
                "approved_original_keyframe": ("IMAGE",),
                "approved_identity": ("IMAGE",),
                "shot_id": ("STRING", {"default": "shot_01"}),
                "keyframe_approved": ("BOOLEAN", {"default": False}),
                "identity_approved": ("BOOLEAN", {"default": True}),
                "performance": _multiline(),
                "camera_trajectory": _multiline(),
                "rhythm": _multiline(),
                "continuity": _multiline(),
                "approved_keyframe_observations": _multiline(),
                "seedance_prompt_adjustments": _multiline(),
                "generated_duration_seconds": ("INT", {"default": 5, "min": 4, "max": 30}),
                "final_edit_duration_seconds": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 120.0, "step": 0.1}),
                "video_aspect_ratio": (["auto", "16:9", "9:16", "1:1", "3:4", "4:3", "21:9"], {"default": "auto"}),
                "approve_aspect_adaptation": ("BOOLEAN", {"default": False}),
                "resolution": (["720p", "1080p"], {"default": "1080p"}),
                "generate_native_audio": ("BOOLEAN", {"default": False}),
                "bitrate_mode": (["standard", "high"], {"default": "standard"}),
            },
            "optional": {
                "approved_end_keyframe": ("IMAGE",),
                "original_shot_draft": ("ADS_ART_SHOT_DRAFT",),
            },
        }

    RETURN_TYPES = ("ADS_ART_REQUEST", "STRING")
    RETURN_NAMES = ("seedance_request", "request_preview")
    FUNCTION = "prepare"
    CATEGORY = "Ads Art v2/08 Seedance Original Shots"
    OUTPUT_NODE = True

    def prepare(self, project, approved_original_keyframe, approved_identity, shot_id, keyframe_approved, identity_approved, performance, camera_trajectory, rhythm, continuity, approved_keyframe_observations, seedance_prompt_adjustments, generated_duration_seconds, final_edit_duration_seconds, video_aspect_ratio, approve_aspect_adaptation, resolution, generate_native_audio, bitrate_mode, approved_end_keyframe=None, original_shot_draft=None):
        legacy_result = AdsArtPrepareVideoShot().prepare(
            project,
            approved_original_keyframe,
            approved_identity,
            shot_id,
            keyframe_approved,
            identity_approved,
            performance,
            camera_trajectory,
            rhythm,
            continuity,
            approved_keyframe_observations,
            seedance_prompt_adjustments,
            generated_duration_seconds,
            final_edit_duration_seconds,
            video_aspect_ratio,
            approve_aspect_adaptation,
            resolution,
            generate_native_audio,
            bitrate_mode,
            approved_end_keyframe,
            original_shot_draft,
        )
        request = parse_json(legacy_result["result"][0], "seedance_request")
        request["prompt"] = request["prompt"].replace("RECREATED FRAME", "ORIGINAL KEYFRAME").replace("recreated frame", "original keyframe")
        request["approvals"]["original_keyframe"] = request["approvals"].pop("recreated_frame")
        for item in request["media"]:
            if item.get("kind") == "approved_recreated_frame":
                item["kind"] = "approved_original_keyframe"
        request["metadata"]["source_contract"] = "original_keyframe_only"
        request["metadata"]["reference_video_forwarded"] = False
        request["metadata"]["reference_audio_forwarded"] = False
        request["metadata"]["reference_evidence_frame_forwarded"] = False
        ProjectStore(request["project_id"]).write_json(
            f"requests/{request['shot_id']}/{request['request_id']}.json", request
        )
        report = (
            f"{request['shot_id']} | SEEDANCE FROM APPROVED ORIGINAL KEYFRAME | {request['status'].upper()}\n"
            "Reference video/audio/evidence frames attached: NO\n"
            "Paid submission: NO\n\n" + request["prompt"]
        )
        return _ui_result((json_dumps(request), report), report)


NODE_CLASS_MAPPINGS = {
    "AdsArtCreativeBrief": AdsArtCreativeBrief,
    "AdsArtGeminiCreativeIntelligence": AdsArtGeminiCreativeIntelligence,
    "AdsArtCreativeIntelligenceViewer": AdsArtCreativeIntelligenceViewer,
    "AdsArtOriginalShotDraft": AdsArtOriginalShotDraft,
    "AdsArtPrepareOriginalKeyframe": AdsArtPrepareOriginalKeyframe,
    "AdsArtPrepareOriginalSeedanceShot": AdsArtPrepareOriginalSeedanceShot,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "AdsArtCreativeBrief": "Ads Art v2 — Project / Brand / Character",
    "AdsArtGeminiCreativeIntelligence": "Ads Art v2 — Automatic Creative Intelligence",
    "AdsArtCreativeIntelligenceViewer": "Ads Art v2 — Inspect Intelligence",
    "AdsArtOriginalShotDraft": "Ads Art v2 — Original Shot Draft",
    "AdsArtPrepareOriginalKeyframe": "Ads Art v2 — Prepare Original Nano Keyframe",
    "AdsArtPrepareOriginalSeedanceShot": "Ads Art v2 — Prepare Seedance from Original Keyframe",
}

"""ComfyUI nodes for Ads Art."""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from .ads_art_core import (
    AdsArtError,
    IMAGE_ASPECT_RATIO,
    IMAGE_MODEL_ID,
    IMAGE_RESOLUTION,
    ProjectStore,
    VIDEO_ASPECT_RATIOS,
    VIDEO_MODE,
    VIDEO_MODEL_ID,
    VIDEO_RESOLUTIONS,
    cli_version,
    compile_controls,
    get_account_status,
    get_live_model,
    image_ratio,
    json_dumps,
    load_image_tensor,
    load_knowledge,
    make_project,
    make_request,
    parse_json,
    poll_job,
    recover_job_record,
    ratio_to_float,
    resolve_input_path,
    save_image_tensor,
    submit_request,
    utc_now,
)


def _ui_result(result: tuple[Any, ...], text: str):
    return {"ui": {"text": [text]}, "result": result}


def _report_conflicts(conflicts: list[dict[str, Any]]) -> str:
    if not conflicts:
        return "Sin contradicciones detectadas."
    lines = []
    for item in conflicts:
        severity = str(item.get("severity", "warning")).upper()
        message = item.get("message_es") or item.get("id") or "conflicto"
        resolution = item.get("resolved_by_policy")
        suffix = f" Prioridad aplicada: {resolution}." if resolution else ""
        lines.append(f"[{severity}] {message}{suffix}")
    return "\n".join(lines)


def _video_duration(container: Any, stream: Any) -> float:
    if stream.duration is not None and stream.time_base is not None:
        return float(stream.duration * stream.time_base)
    if container.duration is not None:
        try:
            import av

            return float(container.duration / av.time_base)
        except Exception:
            return float(container.duration) / 1_000_000.0
    return 0.0


def _frame_time(frame: Any, index: int, fps: float) -> float:
    if frame.time is not None:
        return float(frame.time)
    if frame.pts is not None and frame.time_base is not None:
        return float(frame.pts * frame.time_base)
    return float(index) / fps if fps > 0 else 0.0


def _small_rgb(frame: Any) -> np.ndarray:
    return np.asarray(frame.to_image().convert("RGB").resize((64, 64), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0


def _shot_boundaries(
    video_path: Path,
    threshold: float,
    min_shot_seconds: float,
    analysis_fps: float,
) -> tuple[list[float], float, list[dict[str, float]]]:
    try:
        import av
    except ImportError as exc:
        raise AdsArtError("PyAV no está instalado en el entorno activo de ComfyUI.") from exc

    cuts = [0.0]
    detected: list[dict[str, float]] = []
    last_time = 0.0
    with av.open(str(video_path)) as container:
        if not container.streams.video:
            raise AdsArtError("El archivo no contiene una pista de video.")
        stream = container.streams.video[0]
        rate = float(stream.average_rate or stream.base_rate or stream.guessed_rate or 0)
        sample_step = max(1, round(rate / max(0.5, analysis_fps))) if rate else 1
        previous = None
        last_cut = 0.0
        for index, frame in enumerate(container.decode(stream)):
            timestamp = _frame_time(frame, index, rate)
            last_time = max(last_time, timestamp)
            if index % sample_step:
                continue
            current = _small_rgb(frame)
            if previous is not None:
                score = float(np.mean(np.abs(current - previous)))
                if score >= threshold and timestamp - last_cut >= min_shot_seconds:
                    cuts.append(timestamp)
                    detected.append({"timestamp": round(timestamp, 6), "visual_change_score": round(score, 6)})
                    last_cut = timestamp
            previous = current
        measured_duration = _video_duration(container, stream)
    return cuts, max(measured_duration, last_time), detected


def _evenly_limit(values: list[float], limit: int) -> tuple[list[float], bool]:
    if len(values) <= limit:
        return values, False
    if limit <= 1:
        return [values[0]], True
    indexes = sorted({round(i * (len(values) - 1) / (limit - 1)) for i in range(limit)})
    return [values[index] for index in indexes], True


def _extract_representative_frames(
    video_path: Path,
    targets: list[float],
    output_directory: Path,
) -> list[Path]:
    try:
        import av
    except ImportError as exc:
        raise AdsArtError("PyAV no está instalado en el entorno activo de ComfyUI.") from exc
    output_directory.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate or stream.base_rate or stream.guessed_rate or 0)
        target_index = 0
        for index, frame in enumerate(container.decode(stream)):
            if target_index >= len(targets):
                break
            timestamp = _frame_time(frame, index, fps)
            while target_index < len(targets) and timestamp >= targets[target_index]:
                target = targets[target_index]
                path = output_directory / f"shot_{target_index + 1:03d}_t{target:09.3f}.png"
                frame.to_image().convert("RGB").save(path, format="PNG")
                results.append(path)
                target_index += 1
    if len(results) < len(targets):
        raise AdsArtError("No fue posible extraer todos los frames representativos.")
    return results


def _extract_frame_at(video_path: Path, timestamp: float, output_path: Path) -> Path:
    try:
        import av
    except ImportError as exc:
        raise AdsArtError("PyAV no está instalado en el entorno activo de ComfyUI.") from exc
    chosen = None
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate or stream.base_rate or stream.guessed_rate or 0)
        for index, frame in enumerate(container.decode(stream)):
            chosen = frame
            if _frame_time(frame, index, fps) >= timestamp:
                break
    if chosen is None:
        raise AdsArtError("No se pudo decodificar un frame en el timestamp solicitado.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chosen.to_image().convert("RGB").save(output_path, format="PNG")
    return output_path


class AdsArtProjectConfig:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project_id": ("STRING", {"default": "ads_art_project_001"}),
                "positive_prompt": ("STRING", {"multiline": True, "default": ""}),
                "restrictive_prompt": ("STRING", {"multiline": True, "default": ""}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "creative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "video_aspect_ratio": (list(VIDEO_ASPECT_RATIOS), {"default": "auto"}),
                "video_resolution": (list(VIDEO_RESOLUTIONS), {"default": "1080p"}),
                "seedance_generate_audio": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("ADS_ART_PROJECT", "STRING")
    RETURN_NAMES = ("project", "validation_report")
    FUNCTION = "configure"
    CATEGORY = "Ads Art/01 Project"
    OUTPUT_NODE = True
    DESCRIPTION = "Crea el registro del proyecto y muestra contradicciones antes de preparar generaciones."

    def configure(
        self,
        project_id,
        positive_prompt,
        restrictive_prompt,
        negative_prompt,
        creative_prompt,
        video_aspect_ratio,
        video_resolution,
        seedance_generate_audio,
    ):
        project = make_project(
            project_id,
            positive_prompt,
            restrictive_prompt,
            negative_prompt,
            creative_prompt,
            video_aspect_ratio,
            video_resolution,
            seedance_generate_audio,
        )
        report = (
            f"Proyecto: {project_id}\n"
            f"Estado: {'LISTO' if project['ready'] else 'BLOQUEADO'}\n"
            f"Imagen bloqueada a: {IMAGE_MODEL_ID}, {IMAGE_ASPECT_RATIO}, {IMAGE_RESOLUTION}\n"
            f"Video bloqueado a: {VIDEO_MODEL_ID}, modo {VIDEO_MODE}\n\n"
            + _report_conflicts(project["conflicts"])
        )
        return _ui_result((json_dumps(project), report), report)


class AdsArtHiggsfieldStatus:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"refresh": ("BOOLEAN", {"default": True})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "check"
    CATEGORY = "Ads Art/01 Project"
    OUTPUT_NODE = True
    DESCRIPTION = "Consulta autenticación y catálogo mediante el CLI oficial, sin generar."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def check(self, refresh=True):
        status = {
            "checked_at": utc_now(),
            "transport": "official_higgsfield_cli",
            "cli_version": cli_version(),
            "account": get_account_status(),
            "models": {
                IMAGE_MODEL_ID: get_live_model(IMAGE_MODEL_ID),
                VIDEO_MODEL_ID: get_live_model(VIDEO_MODEL_ID),
            },
            "secrets_logged": False,
        }
        text = json_dumps(status)
        return _ui_result((text,), text)


class AdsArtAnalyzeCommercial:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("ADS_ART_PROJECT",),
                "video_path": ("STRING", {"default": "", "multiline": False}),
                "scene_threshold": ("FLOAT", {"default": 0.22, "min": 0.02, "max": 1.0, "step": 0.01}),
                "min_shot_seconds": ("FLOAT", {"default": 0.5, "min": 0.1, "max": 30.0, "step": 0.1}),
                "analysis_fps": ("FLOAT", {"default": 6.0, "min": 0.5, "max": 30.0, "step": 0.5}),
                "max_shots": ("INT", {"default": 24, "min": 1, "max": 100}),
                "manual_semantic_analysis": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("ADS_ART_ANALYSIS", "IMAGE", "STRING")
    RETURN_NAMES = ("analysis", "representative_frames", "report")
    FUNCTION = "analyze"
    CATEGORY = "Ads Art/02 Commercial"
    OUTPUT_NODE = True
    DESCRIPTION = "Mide el video, detecta cambios visuales y extrae un frame editable por toma."

    def analyze(
        self,
        project,
        video_path,
        scene_threshold,
        min_shot_seconds,
        analysis_fps,
        max_shots,
        manual_semantic_analysis,
    ):
        project_data = parse_json(project, "project")
        source = resolve_input_path(video_path)
        try:
            import av
        except ImportError as exc:
            raise AdsArtError("PyAV no está instalado en el entorno activo de ComfyUI.") from exc

        with av.open(str(source)) as container:
            if not container.streams.video:
                raise AdsArtError("El comercial no contiene video.")
            video = container.streams.video[0]
            fps = float(video.average_rate or video.base_rate or video.guessed_rate or 0)
            duration = _video_duration(container, video)
            audio_streams = list(container.streams.audio)
            audio_info = [
                {
                    "codec": getattr(stream.codec_context, "name", None),
                    "channels": getattr(stream.codec_context, "channels", None),
                    "sample_rate": getattr(stream.codec_context, "sample_rate", None),
                }
                for stream in audio_streams
            ]
            metadata = {
                "duration_seconds": round(duration, 6),
                "width": int(video.codec_context.width),
                "height": int(video.codec_context.height),
                "fps": round(fps, 6),
                "frame_count_declared": int(video.frames or 0),
                "has_audio": bool(audio_streams),
                "audio_streams": audio_info,
            }

        cuts, decoded_duration, detections = _shot_boundaries(
            source, float(scene_threshold), float(min_shot_seconds), float(analysis_fps)
        )
        duration = max(duration, decoded_duration)
        cuts, truncated = _evenly_limit(cuts, int(max_shots))
        ends = cuts[1:] + [duration]
        targets = [max(start, (start + max(start, end)) / 2.0) for start, end in zip(cuts, ends)]
        store = ProjectStore(project_data["project_id"])
        frame_dir = store.directory("frames", "original")
        paths = _extract_representative_frames(source, targets, frame_dir)
        shots = []
        for index, (start, end, target, path) in enumerate(zip(cuts, ends, targets, paths), 1):
            shots.append(
                {
                    "shot_id": f"shot_{index:03d}",
                    "index": index,
                    "start_seconds": round(start, 6),
                    "end_seconds": round(end, 6),
                    "representative_timestamp": round(target, 6),
                    "selected_frame_path": str(path),
                    "review": {"approved": False, "notes": ""},
                    "verified_observations": [
                        "Límites propuestos por cambio visual medido.",
                        "Timestamp y frame extraído directamente del archivo fuente.",
                    ],
                    "interpretations": [],
                }
            )
        analysis = {
            "schema_version": "1.0.0",
            "project_id": project_data["project_id"],
            "source_video_path": str(source),
            "created_at": utc_now(),
            "verified": metadata,
            "detector": {
                "type": "local_mean_absolute_visual_change",
                "scene_threshold": float(scene_threshold),
                "min_shot_seconds": float(min_shot_seconds),
                "analysis_fps": float(analysis_fps),
                "detections": detections,
                "shot_limit_applied": truncated,
            },
            "shots": shots,
            "manual_semantic_analysis": {
                "text": (manual_semantic_analysis or "").strip(),
                "verified": False,
                "source": "user_editable",
            },
            "semantic_capability": {
                "local_cli_available": False,
                "note_es": (
                    "El plugin MCP de esta sesión expone análisis de video, pero el CLI local 1.1.23 "
                    "no documenta un comando equivalente. No se inventó un endpoint. Use o edite el análisis manual."
                ),
            },
            "original_video_forwarded_to_seedance": False,
            "original_audio_forwarded_to_seedance": False,
        }
        analysis_path = store.write_json("analysis/commercial.json", analysis)
        analysis["record_path"] = str(analysis_path)
        tensors = [load_image_tensor(path) for path in paths]
        batch = torch.cat(tensors, dim=0)
        report = (
            f"Video: {source.name}\nDuración: {duration:.3f}s | {metadata['width']}x{metadata['height']} | "
            f"{metadata['fps']:.3f} FPS | audio={'sí' if metadata['has_audio'] else 'no'}\n"
            f"Tomas propuestas: {len(shots)}{' (límite aplicado)' if truncated else ''}\n"
            "Semántica: entrada manual editable; no se llamó a generación ni análisis externo."
        )
        return _ui_result((json_dumps(analysis), batch, report), report)


class AdsArtReviewFrame:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "analysis": ("ADS_ART_ANALYSIS",),
                "shot_number": ("INT", {"default": 1, "min": 1, "max": 100}),
                "approved": ("BOOLEAN", {"default": False}),
                "replacement_timestamp": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 86400.0, "step": 0.01}),
                "review_notes": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {"replacement_image": ("IMAGE",)},
        }

    RETURN_TYPES = ("ADS_ART_ANALYSIS", "IMAGE", "STRING")
    RETURN_NAMES = ("updated_analysis", "selected_frame", "report")
    FUNCTION = "review"
    CATEGORY = "Ads Art/02 Commercial"
    OUTPUT_NODE = True
    DESCRIPTION = "Aprueba o sustituye el frame representativo de una toma."

    def review(self, analysis, shot_number, approved, replacement_timestamp, review_notes, replacement_image=None):
        data = parse_json(analysis, "analysis")
        index = int(shot_number) - 1
        if index < 0 or index >= len(data.get("shots", [])):
            raise AdsArtError("shot_number está fuera del rango analizado.")
        shot = data["shots"][index]
        store = ProjectStore(data["project_id"])
        replacement = None
        if replacement_image is not None:
            replacement = store.path("frames", "reviewed", f"{shot['shot_id']}_replacement.png")
            save_image_tensor(replacement_image, replacement)
            shot["representative_timestamp"] = None
            shot["replacement_source"] = "user_image"
        elif float(replacement_timestamp) >= 0:
            replacement = store.path("frames", "reviewed", f"{shot['shot_id']}_t{float(replacement_timestamp):09.3f}.png")
            _extract_frame_at(Path(data["source_video_path"]), float(replacement_timestamp), replacement)
            shot["representative_timestamp"] = round(float(replacement_timestamp), 6)
            shot["replacement_source"] = "source_video_timestamp"
        if replacement is not None:
            shot["selected_frame_path"] = str(replacement)
        shot["review"] = {
            "approved": bool(approved),
            "notes": (review_notes or "").strip(),
            "reviewed_at": utc_now(),
        }
        store.write_json("analysis/commercial.json", data)
        image = load_image_tensor(shot["selected_frame_path"])
        report = (
            f"{shot['shot_id']}: {'APROBADO' if approved else 'PENDIENTE'}\n"
            f"Frame: {shot['selected_frame_path']}\nNotas: {shot['review']['notes'] or '(sin notas)'}"
        )
        return _ui_result((json_dumps(data), image, report), report)


class AdsArtPrepareIdentity:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("ADS_ART_PROJECT",),
                "art_image": ("IMAGE",),
                "identity_notes": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("ADS_ART_REQUEST", "STRING")
    RETURN_NAMES = ("identity_request", "request_preview")
    FUNCTION = "prepare"
    CATEGORY = "Ads Art/03 Identity"
    OUTPUT_NODE = True
    DESCRIPTION = "Prepara, guarda y valida la solicitud de identidad. No genera."

    def prepare(self, project, art_image, identity_notes):
        project_data = parse_json(project, "project")
        store = ProjectStore(project_data["project_id"])
        art_path = store.path("references", "identity", "artwork_source.png")
        save_image_tensor(art_image, art_path)
        prompt = (
            "Create one hyperrealistic human influencer interpretation of the person or character in the supplied artwork. "
            "Preserve recognizable facial structure, expression cues, silhouette, palette cues, and distinctive identity markers, "
            "while translating painted, drawn, or sculpted traits into plausible real skin, hair, eyes, anatomy, wardrobe materials, "
            "and photographic detail. Keep a neutral identity-reference pose, clean unobtrusive background, consistent proportions, "
            "and no typography, labels, grids, storyboard marks, or extra people. This image will be the approved identity anchor for every shot."
        )
        if (identity_notes or "").strip():
            prompt += "\n\nUSER IDENTITY NOTES:\n" + identity_notes.strip()
        controls = compile_controls(project_data, "identity")
        if controls:
            prompt += "\n\n" + controls
        request = make_request(
            project_data,
            "identity",
            "identity",
            prompt,
            {
                "model": IMAGE_MODEL_ID,
                "aspect_ratio": IMAGE_ASPECT_RATIO,
                "resolution": IMAGE_RESOLUTION,
            },
            [{"role": "image", "kind": "artwork_source", "path": str(art_path), "approved": True}],
            approvals={"artwork_selected_by_user": True},
            metadata={
                "generated_result_requires_user_approval": True,
                "reuse_approved_identity_in_all_shots": True,
            },
        )
        report = (
            f"Estado: {request['status'].upper()}\nModelo: {IMAGE_MODEL_ID}\n"
            f"Formato: {IMAGE_ASPECT_RATIO} | Resolución: {IMAGE_RESOLUTION}\n"
            "No se envió ningún job. La imagen resultante deberá aprobarse antes de recrear tomas.\n\n"
            + _report_conflicts(request["conflicts"])
            + "\n\nPROMPT COMPILADO:\n"
            + request["prompt"]
        )
        return _ui_result((json_dumps(request), report), report)


def _resolve_camera_concepts(value: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    knowledge = load_knowledge()
    concepts = knowledge.get("concepts", [])
    by_key: dict[str, dict[str, Any]] = {}
    for concept in concepts:
        by_key[concept["id"].lower()] = concept
        for alias in concept.get("aliases", []):
            by_key[str(alias).lower()] = concept
    requested = [item.strip().lower() for item in re.split(r"[,;\n]+", value or "") if item.strip()]
    resolved: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for item in requested:
        concept = by_key.get(item)
        if not concept:
            conflicts.append(
                {
                    "id": f"unknown_camera_concept_{item}",
                    "severity": "error",
                    "message_es": f"Concepto cinematográfico desconocido: {item}",
                }
            )
            continue
        if concept["id"] not in {existing["id"] for existing in resolved}:
            resolved.append(concept)
    by_dimension: dict[str, list[str]] = {}
    for concept in resolved:
        by_dimension.setdefault(concept.get("dimension", "unknown"), []).append(concept["id"])
    for dimension, ids in by_dimension.items():
        if len(ids) > 1:
            conflicts.append(
                {
                    "id": f"multiple_{dimension}",
                    "severity": "error",
                    "message_es": (
                        f"Hay más de una decisión dominante en {dimension}: {', '.join(ids)}. "
                        "Elija una; describa transiciones temporales por separado."
                    ),
                }
            )
    return resolved, conflicts


class AdsArtPrepareShot:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("ADS_ART_PROJECT",),
                "analysis": ("ADS_ART_ANALYSIS",),
                "selected_source_frame": ("IMAGE",),
                "approved_identity": ("IMAGE",),
                "shot_number": ("INT", {"default": 1, "min": 1, "max": 100}),
                "source_frame_approved": ("BOOLEAN", {"default": False}),
                "identity_approved": ("BOOLEAN", {"default": False}),
                "objective": ("STRING", {"multiline": True, "default": ""}),
                "action": ("STRING", {"multiline": True, "default": ""}),
                "camera_concepts": ("STRING", {"default": "", "multiline": True}),
                "framing_and_composition": ("STRING", {"multiline": True, "default": ""}),
                "lighting": ("STRING", {"multiline": True, "default": ""}),
                "elements_to_preserve": ("STRING", {"multiline": True, "default": ""}),
                "planned_changes": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("ADS_ART_REQUEST", "STRING")
    RETURN_NAMES = ("frame_request", "shot_plan_preview")
    FUNCTION = "prepare"
    CATEGORY = "Ads Art/04 Shot Planning"
    OUTPUT_NODE = True
    DESCRIPTION = "Planifica una toma con la base editorial y prepara Nano Banana Pro. No genera."

    def prepare(
        self,
        project,
        analysis,
        selected_source_frame,
        approved_identity,
        shot_number,
        source_frame_approved,
        identity_approved,
        objective,
        action,
        camera_concepts,
        framing_and_composition,
        lighting,
        elements_to_preserve,
        planned_changes,
    ):
        project_data = parse_json(project, "project")
        analysis_data = parse_json(analysis, "analysis")
        index = int(shot_number) - 1
        if index < 0 or index >= len(analysis_data.get("shots", [])):
            raise AdsArtError("shot_number está fuera del rango analizado.")
        shot = analysis_data["shots"][index]
        store = ProjectStore(project_data["project_id"])
        original_path = store.path("references", shot["shot_id"], "original_frame.png")
        identity_path = store.path("references", shot["shot_id"], "approved_identity.png")
        save_image_tensor(selected_source_frame, original_path)
        save_image_tensor(approved_identity, identity_path)
        resolved, concept_conflicts = _resolve_camera_concepts(camera_concepts)
        for field_name, field_value in (("objective", objective), ("action", action)):
            if not (field_value or "").strip():
                concept_conflicts.append(
                    {
                        "id": f"missing_{field_name}",
                        "severity": "error",
                        "message_es": f"Falta definir {field_name} para la toma.",
                    }
                )
        camera_text = "\n".join(
            f"- {item['label_es']} ({item['id']}): {item.get('prompt_fragment_en', item.get('definition_es', ''))}"
            for item in resolved
        ) or "- No camera catalog concept selected; use only the explicit framing notes."
        shot_record = {
            "shot_id": shot["shot_id"],
            "objective": (objective or "").strip(),
            "action": (action or "").strip(),
            "camera_concepts": [item["id"] for item in resolved],
            "framing_and_composition": (framing_and_composition or "").strip(),
            "lighting": (lighting or "").strip(),
            "elements_to_preserve": (elements_to_preserve or "").strip(),
            "planned_changes": (planned_changes or "").strip(),
            "catalog_status": "editorial_suggestions_selected_explicitly_by_user",
        }
        prompt = f"""Recreate the supplied original commercial frame as one hyperrealistic advertising still.
Use the approved identity reference as the same influencer in this shot. Preserve stable facial identity, body proportions, wardrobe logic, and recognizable traits. The original commercial frame is composition/action evidence, not an identity source.

SHOT OBJECTIVE:
{shot_record['objective']}

ACTION:
{shot_record['action']}

CAMERA KNOWLEDGE SELECTED BY THE USER:
{camera_text}

FRAMING AND COMPOSITION:
{shot_record['framing_and_composition']}

LIGHTING:
{shot_record['lighting']}

SHOT-SPECIFIC ELEMENTS TO PRESERVE:
{shot_record['elements_to_preserve']}

SHOT-SPECIFIC CHANGES:
{shot_record['planned_changes']}

Do not reproduce reference-board labels, grids, captions, or example subjects. Do not add unrequested typography. Return one coherent production-ready keyframe."""
        controls = compile_controls(project_data, "frame")
        if controls:
            prompt += "\n\n" + controls
        request = make_request(
            project_data,
            "frame",
            shot["shot_id"],
            prompt,
            {
                "model": IMAGE_MODEL_ID,
                "aspect_ratio": IMAGE_ASPECT_RATIO,
                "resolution": IMAGE_RESOLUTION,
            },
            [
                {"role": "image", "kind": "original_commercial_frame", "path": str(original_path), "approved": bool(source_frame_approved)},
                {"role": "image", "kind": "approved_identity", "path": str(identity_path), "approved": bool(identity_approved)},
            ],
            approvals={
                "source_frame": bool(source_frame_approved),
                "identity": bool(identity_approved),
            },
            extra_conflicts=concept_conflicts,
            metadata={"shot_record": shot_record, "generated_frame_requires_user_approval": True},
        )
        store.write_json(f"shots/{shot['shot_id']}/plan.json", shot_record)
        report = (
            f"{shot['shot_id']} | Estado: {request['status'].upper()}\n"
            f"Conceptos seleccionados: {', '.join(shot_record['camera_concepts']) or '(ninguno)'}\n"
            f"Modelo: {IMAGE_MODEL_ID}, {IMAGE_ASPECT_RATIO}, {IMAGE_RESOLUTION}\n"
            "No se envió ningún job.\n\n"
            + _report_conflicts(request["conflicts"])
            + "\n\nPROMPT COMPILADO:\n"
            + request["prompt"]
        )
        return _ui_result((json_dumps(request), report), report)


class AdsArtPrepareVideoShot:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("ADS_ART_PROJECT",),
                "approved_recreated_frame": ("IMAGE",),
                "approved_identity": ("IMAGE",),
                "shot_id": ("STRING", {"default": "shot_001"}),
                "frame_approved": ("BOOLEAN", {"default": False}),
                "identity_approved": ("BOOLEAN", {"default": False}),
                "performance": ("STRING", {"multiline": True, "default": ""}),
                "camera_trajectory": ("STRING", {"multiline": True, "default": ""}),
                "rhythm": ("STRING", {"multiline": True, "default": ""}),
                "continuity": ("STRING", {"multiline": True, "default": ""}),
                "generated_duration_seconds": ("INT", {"default": 5, "min": 4, "max": 30}),
                "final_edit_duration_seconds": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 120.0, "step": 0.1}),
                "video_aspect_ratio": (list(VIDEO_ASPECT_RATIOS), {"default": "auto"}),
                "approve_aspect_adaptation": ("BOOLEAN", {"default": False}),
                "resolution": (list(VIDEO_RESOLUTIONS), {"default": "1080p"}),
                "generate_native_audio": ("BOOLEAN", {"default": False}),
                "bitrate_mode": (["standard", "high"], {"default": "standard"}),
            },
            "optional": {"approved_end_frame": ("IMAGE",)},
        }

    RETURN_TYPES = ("ADS_ART_REQUEST", "STRING")
    RETURN_NAMES = ("video_request", "request_preview")
    FUNCTION = "prepare"
    CATEGORY = "Ads Art/05 Video"
    OUTPUT_NODE = True
    DESCRIPTION = "Prepara Seedance 2.5 con imágenes y texto exclusivamente. No genera."

    def prepare(
        self,
        project,
        approved_recreated_frame,
        approved_identity,
        shot_id,
        frame_approved,
        identity_approved,
        performance,
        camera_trajectory,
        rhythm,
        continuity,
        generated_duration_seconds,
        final_edit_duration_seconds,
        video_aspect_ratio,
        approve_aspect_adaptation,
        resolution,
        generate_native_audio,
        bitrate_mode,
        approved_end_frame=None,
    ):
        project_data = parse_json(project, "project")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", (shot_id or "").strip()):
            raise AdsArtError("shot_id no es válido.")
        store = ProjectStore(project_data["project_id"])
        shot_id = shot_id.strip()
        frame_path = store.path("references", shot_id, "approved_recreated_frame.png")
        identity_path = store.path("references", shot_id, "approved_identity_for_video.png")
        save_image_tensor(approved_recreated_frame, frame_path)
        save_image_tensor(approved_identity, identity_path)
        media = [
            {"role": "start_image", "kind": "approved_recreated_frame", "path": str(frame_path), "approved": bool(frame_approved)},
            {"role": "image", "kind": "approved_identity", "path": str(identity_path), "approved": bool(identity_approved)},
        ]
        if approved_end_frame is not None:
            end_path = store.path("references", shot_id, "approved_end_frame.png")
            save_image_tensor(approved_end_frame, end_path)
            media.append({"role": "end_image", "kind": "approved_end_frame", "path": str(end_path), "approved": bool(frame_approved)})
        conflicts: list[dict[str, Any]] = []
        requested_ratio = ratio_to_float(video_aspect_ratio)
        source_ratio = image_ratio(approved_recreated_frame)
        if requested_ratio is not None and not math.isclose(requested_ratio, source_ratio, rel_tol=0.025, abs_tol=0.025):
            if not approve_aspect_adaptation:
                conflicts.append(
                    {
                        "id": "aspect_adaptation_not_approved",
                        "severity": "error",
                        "message_es": (
                            f"El frame mide {source_ratio:.4f}:1 y el video solicita {video_aspect_ratio}. "
                            "No se recortará ni deformará; apruebe explícitamente la adaptación o use auto."
                        ),
                    }
                )
        for name, value in (("performance", performance), ("camera_trajectory", camera_trajectory), ("rhythm", rhythm), ("continuity", continuity)):
            if not (value or "").strip():
                conflicts.append(
                    {"id": f"missing_{name}", "severity": "error", "message_es": f"Falta definir {name}."}
                )
        prompt = f"""Animate this approved advertising keyframe into one continuous shot using only the supplied still-image references.
Keep the approved influencer identity stable and preserve all user-approved products, wardrobe, environment, geometry, and composition unless an explicit change is stated below.

PERFORMANCE AND ACTION:
{(performance or '').strip()}

CAMERA TRAJECTORY:
{(camera_trajectory or '').strip()}

RHYTHM AND TIMING:
{(rhythm or '').strip()}

CONTINUITY:
{(continuity or '').strip()}

Do not infer motion from or reproduce any source video or source audio; neither is supplied. Do not add cuts unless explicitly described. Maintain temporal identity and object consistency."""
        controls = compile_controls(project_data, "video")
        if controls:
            prompt += "\n\n" + controls
        params = {
            "model": VIDEO_MODEL_ID,
            "mode": VIDEO_MODE,
            "aspect_ratio": video_aspect_ratio,
            "resolution": resolution,
            "duration": int(generated_duration_seconds),
            "generate_audio": bool(generate_native_audio),
            "bitrate_mode": bitrate_mode,
        }
        request = make_request(
            project_data,
            "video",
            shot_id,
            prompt,
            params,
            media,
            approvals={"recreated_frame": bool(frame_approved), "identity": bool(identity_approved)},
            extra_conflicts=conflicts,
            metadata={
                "generated_duration_seconds": int(generated_duration_seconds),
                "final_edit_duration_seconds": float(final_edit_duration_seconds),
                "duration_values_are_independent": True,
                "image_source_ratio": source_ratio,
                "aspect_adaptation_approved": bool(approve_aspect_adaptation),
                "original_video_forwarded": False,
                "original_audio_forwarded": False,
                "original_audio_mounting_policy": "add_after_generation_by_default",
            },
        )
        report = (
            f"{shot_id} | Estado: {request['status'].upper()}\n"
            f"Modelo: {VIDEO_MODEL_ID} | modo: {VIDEO_MODE}\n"
            f"Video: {video_aspect_ratio}, {resolution}, generado={generated_duration_seconds}s, montaje={final_edit_duration_seconds:.2f}s\n"
            "Medios: sólo imágenes (start_image / image / end_image). Video y audio originales: NO enviados.\n"
            "No se envió ningún job.\n\n"
            + _report_conflicts(request["conflicts"])
            + "\n\nPROMPT COMPILADO:\n"
            + request["prompt"]
        )
        return _ui_result((json_dumps(request), report), report)


class AdsArtSubmitJob:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "request": ("ADS_ART_REQUEST",),
                "confirm_paid_submission": ("BOOLEAN", {"default": False}),
                "minimum_credits_after": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1000000.0, "step": 1.0}),
                "upload_retries": ("INT", {"default": 2, "min": 1, "max": 4}),
                "timeout_seconds": ("INT", {"default": 180, "min": 30, "max": 900}),
            }
        }

    RETURN_TYPES = ("ADS_ART_JOB", "STRING")
    RETURN_NAMES = ("job", "submission_status")
    FUNCTION = "submit"
    CATEGORY = "Ads Art/06 Jobs"
    OUTPUT_NODE = True
    DESCRIPTION = "Valida catálogo/medios, estima coste y envía una sola vez sólo con confirmación explícita."

    def submit(self, request, confirm_paid_submission, minimum_credits_after, upload_retries, timeout_seconds):
        job = submit_request(
            request,
            bool(confirm_paid_submission),
            float(minimum_credits_after),
            int(upload_retries),
            int(timeout_seconds),
        )
        report = (
            f"Estado: {job['status']}\n"
            f"Job ID: {job.get('job_id') or '(no enviado)'}\n"
            f"Generación de pago enviada: {job.get('paid_generation_submitted')}"
        )
        return _ui_result((json_dumps(job), report), report)


class AdsArtPollJob:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "job": ("ADS_ART_JOB",),
                "job_id_override": ("STRING", {"default": ""}),
                "download_completed": ("BOOLEAN", {"default": True}),
                "query_retries": ("INT", {"default": 2, "min": 1, "max": 4}),
            }
        }

    RETURN_TYPES = ("ADS_ART_JOB", "STRING", "STRING")
    RETURN_NAMES = ("updated_job", "result_paths", "status")
    FUNCTION = "poll"
    CATEGORY = "Ads Art/06 Jobs"
    OUTPUT_NODE = True
    DESCRIPTION = "Consulta un job existente sin crear otro y descarga resultados terminados."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def poll(self, job, job_id_override, download_completed, query_retries):
        updated = poll_job(job, job_id_override, bool(download_completed), int(query_retries))
        paths = "\n".join(updated.get("result_paths", []))
        report = f"Estado: {updated['status']}\nJob ID: {updated['job_id']}\nResultados:\n{paths or '(aún no disponibles)'}"
        return _ui_result((json_dumps(updated), paths, report), report)


class AdsArtRecoverJob:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("ADS_ART_PROJECT",),
                "request_id": ("STRING", {"default": ""}),
                "job_id": ("STRING", {"default": ""}),
                "shot_id": ("STRING", {"default": "identity"}),
                "stage": (["identity", "frame", "video"], {"default": "identity"}),
            }
        }

    RETURN_TYPES = ("ADS_ART_JOB", "STRING")
    RETURN_NAMES = ("job", "recovery_status")
    FUNCTION = "recover"
    CATEGORY = "Ads Art/06 Jobs"
    OUTPUT_NODE = True
    DESCRIPTION = "Recupera localmente un job persistido o registra un job ID conocido; no consulta ni genera."

    def recover(self, project, request_id, job_id, shot_id, stage):
        recovered = recover_job_record(project, request_id, job_id, shot_id, stage)
        report = (
            f"Registro recuperado localmente.\nEstado: {recovered.get('status')}\n"
            f"Request ID: {recovered.get('request_id')}\nJob ID: {recovered.get('job_id')}\n"
            "No se realizó ninguna llamada al proveedor."
        )
        return _ui_result((json_dumps(recovered), report), report)


class AdsArtLoadImageResult:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "load"
    CATEGORY = "Ads Art/06 Jobs"
    DESCRIPTION = "Carga una imagen descargada por Ads Art para revisión visual."

    def load(self, image_path):
        first = next((line.strip() for line in (image_path or "").splitlines() if line.strip()), "")
        if not first:
            raise AdsArtError("No hay una ruta de imagen resultante.")
        return (load_image_tensor(resolve_input_path(first)),)


def _find_ffmpeg() -> str:
    explicit = os.environ.get("ADS_ART_FFMPEG", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(Path(found))
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "Apps"
    if local.is_dir():
        candidates.extend(sorted(local.glob("*/ffmpeg.exe"), reverse=True))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    raise AdsArtError(
        "No se encontró ffmpeg para el montaje. Instálelo en PATH o defina ADS_ART_FFMPEG. "
        "El análisis y la preparación siguen funcionando sin esta herramienta."
    )


def _run_ffmpeg(args: list[str], timeout: int = 1800) -> None:
    executable = _find_ffmpeg()
    proc = subprocess.run(
        [executable, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
    )
    if proc.returncode != 0:
        raise AdsArtError(f"ffmpeg no pudo completar el montaje: {(proc.stderr or proc.stdout)[-3000:]}")


class AdsArtAssembleClips:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("ADS_ART_PROJECT",),
                "clip_paths": ("STRING", {"multiline": True, "default": ""}),
                "original_commercial_path": ("STRING", {"default": ""}),
                "audio_treatment": (["original", "silent", "external"], {"default": "original"}),
                "external_audio_path": ("STRING", {"default": ""}),
                "output_filename": ("STRING", {"default": "ads_art_final.mp4"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("video_path", "montage_report")
    FUNCTION = "assemble"
    CATEGORY = "Ads Art/07 Montage"
    OUTPUT_NODE = True
    DESCRIPTION = "Concatena clips elegidos y añade el audio original después de generar, por defecto."

    def assemble(self, project, clip_paths, original_commercial_path, audio_treatment, external_audio_path, output_filename):
        import folder_paths

        project_data = parse_json(project, "project")
        clips = [resolve_input_path(line.strip()) for line in (clip_paths or "").splitlines() if line.strip()]
        if not clips:
            raise AdsArtError("Debe proporcionar al menos un clip seleccionado, uno por línea.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.mp4", output_filename or ""):
            raise AdsArtError("output_filename debe ser un nombre .mp4 simple y seguro.")
        output_dir = (Path(folder_paths.get_output_directory()) / "ads_art" / project_data["project_id"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / output_filename
        with tempfile.TemporaryDirectory(prefix="ads_art_montage_") as temp_dir:
            temp_root = Path(temp_dir)
            concat_file = temp_root / "clips.txt"
            concat_lines = []
            for path in clips:
                ffconcat_path = str(path).replace("\\", "/").replace("'", "\\'")
                concat_lines.append(f"file '{ffconcat_path}'")
            concat_file.write_text(
                "\n".join(concat_lines) + "\n",
                encoding="utf-8",
            )
            silent_video = temp_root / "silent_concat.mp4"
            _run_ffmpeg(
                [
                    "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(silent_video),
                ]
            )
            audio_source = None
            if audio_treatment == "original":
                audio_source = resolve_input_path(original_commercial_path)
            elif audio_treatment == "external":
                audio_source = resolve_input_path(external_audio_path)
            if audio_source is None:
                shutil.copy2(silent_video, final_path)
            else:
                _run_ffmpeg(
                    [
                        "-i", str(silent_video), "-i", str(audio_source),
                        "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac",
                        "-shortest", "-movflags", "+faststart", str(final_path),
                    ]
                )
        record = {
            "created_at": utc_now(),
            "project_id": project_data["project_id"],
            "clip_paths": [str(path) for path in clips],
            "audio_treatment": audio_treatment,
            "audio_source": str(audio_source) if audio_source else None,
            "original_audio_was_sent_to_seedance": False,
            "output_path": str(final_path),
        }
        ProjectStore(project_data["project_id"]).write_json(
            f"montages/{uuid.uuid4()}.json", record
        )
        report = (
            f"Montaje exportado: {final_path}\nClips: {len(clips)}\n"
            f"Tratamiento de audio: {audio_treatment}\n"
            "El audio se incorporó localmente después de las generaciones."
        )
        return _ui_result((str(final_path), report), report)


NODE_CLASS_MAPPINGS = {
    "AdsArtProjectConfig": AdsArtProjectConfig,
    "AdsArtHiggsfieldStatus": AdsArtHiggsfieldStatus,
    "AdsArtAnalyzeCommercial": AdsArtAnalyzeCommercial,
    "AdsArtReviewFrame": AdsArtReviewFrame,
    "AdsArtPrepareIdentity": AdsArtPrepareIdentity,
    "AdsArtPrepareShot": AdsArtPrepareShot,
    "AdsArtPrepareVideoShot": AdsArtPrepareVideoShot,
    "AdsArtSubmitJob": AdsArtSubmitJob,
    "AdsArtRecoverJob": AdsArtRecoverJob,
    "AdsArtPollJob": AdsArtPollJob,
    "AdsArtLoadImageResult": AdsArtLoadImageResult,
    "AdsArtAssembleClips": AdsArtAssembleClips,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "AdsArtProjectConfig": "Ads Art — Project & Conflicts",
    "AdsArtHiggsfieldStatus": "Ads Art — Higgsfield Status",
    "AdsArtAnalyzeCommercial": "Ads Art — Analyze Commercial",
    "AdsArtReviewFrame": "Ads Art — Review / Replace Frame",
    "AdsArtPrepareIdentity": "Ads Art — Prepare Identity",
    "AdsArtPrepareShot": "Ads Art — Plan & Prepare Frame",
    "AdsArtPrepareVideoShot": "Ads Art — Prepare Seedance Shot",
    "AdsArtSubmitJob": "Ads Art — Submit Job (Explicit)",
    "AdsArtRecoverJob": "Ads Art — Recover Job Record",
    "AdsArtPollJob": "Ads Art — Poll Job",
    "AdsArtLoadImageResult": "Ads Art — Load Image Result",
    "AdsArtAssembleClips": "Ads Art — Assemble Clips",
}

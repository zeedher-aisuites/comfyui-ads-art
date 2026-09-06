"""ComfyUI nodes for Ads Art."""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
import time
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
from .ads_art_gemini import (
    GEMINI_GENERATION_CONFIG,
    GEMINI_MODEL_ID,
    GEMINI_PROMPT_VERSION,
    GEMINI_SCHEMA_VERSION,
    build_gemini_prompt,
    call_gemini_analysis,
    gemini_analysis_schema,
    gemini_credentials_configured,
    sha256_file,
    stable_fingerprint,
    validate_gemini_response,
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


def _probe_video_metadata(video_path: Path) -> dict[str, Any]:
    try:
        import av
    except ImportError as exc:
        raise AdsArtError("PyAV no está instalado en el entorno activo de ComfyUI.") from exc
    with av.open(str(video_path)) as container:
        if not container.streams.video:
            raise AdsArtError("El comercial no contiene video.")
        video = container.streams.video[0]
        fps = float(video.average_rate or video.base_rate or video.guessed_rate or 0)
        duration = _video_duration(container, video)
        audio_streams = list(container.streams.audio)
        return {
            "duration_seconds": round(duration, 6),
            "width": int(video.codec_context.width),
            "height": int(video.codec_context.height),
            "fps": round(fps, 6),
            "frame_count_declared": int(video.frames or 0),
            "has_audio": bool(audio_streams),
            "audio_streams": [
                {
                    "codec": getattr(stream.codec_context, "name", None),
                    "channels": getattr(stream.codec_context, "channels", None),
                    "sample_rate": getattr(stream.codec_context, "sample_rate", None),
                }
                for stream in audio_streams
            ],
        }


def _sharpness_score(image: Image.Image) -> float:
    gray = np.asarray(
        image.convert("L").resize((256, 256), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    dx = np.diff(gray, axis=1)
    dy = np.diff(gray, axis=0)
    return float(np.var(dx) + np.var(dy))


def _select_clean_candidate_frame(
    video_path: Path,
    candidates: list[float],
    start_seconds: float,
    end_seconds: float,
    cut_timestamps: list[float],
    output_path: Path,
) -> dict[str, Any]:
    """Inspect nearby source frames and prefer sharp samples away from cuts."""

    try:
        import av
    except ImportError as exc:
        raise AdsArtError("PyAV no está instalado en el entorno activo de ComfyUI.") from exc
    expanded = sorted(
        {
            round(min(max(candidate + offset, start_seconds), end_seconds), 6)
            for candidate in candidates
            for offset in (-0.30, -0.15, 0.0, 0.15, 0.30)
        }
    )
    evaluated: list[dict[str, Any]] = []
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate or stream.base_rate or stream.guessed_rate or 0)
        pending = list(expanded)
        for index, frame in enumerate(container.decode(stream)):
            if not pending:
                break
            timestamp = _frame_time(frame, index, fps)
            while pending and timestamp >= pending[0]:
                requested = pending.pop(0)
                image = frame.to_image().convert("RGB")
                distance_to_cut = min(
                    (abs(timestamp - cut) for cut in cut_timestamps),
                    default=float("inf"),
                )
                sharpness = _sharpness_score(image)
                evaluated.append(
                    {
                        "requested_timestamp": requested,
                        "decoded_timestamp": round(timestamp, 6),
                        "sharpness_score": round(sharpness, 6),
                        "distance_to_nearest_cut_seconds": (
                            None if math.isinf(distance_to_cut) else round(distance_to_cut, 6)
                        ),
                        "near_transition": distance_to_cut < 0.18,
                        "image": image,
                    }
                )
    if not evaluated:
        raise AdsArtError("No fue posible comprobar los frames candidatos de la toma.")
    eligible = [item for item in evaluated if not item["near_transition"]] or evaluated
    selected = max(eligible, key=lambda item: item["sharpness_score"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected["image"].save(output_path, format="PNG")
    public_checks = [
        {key: value for key, value in item.items() if key != "image"}
        for item in evaluated
    ]
    return {
        "selected_timestamp": selected["decoded_timestamp"],
        "selected_frame_path": str(output_path),
        "selected_sharpness_score": selected["sharpness_score"],
        "selected_distance_to_nearest_cut_seconds": selected[
            "distance_to_nearest_cut_seconds"
        ],
        "transition_avoidance_succeeded": not selected["near_transition"],
        "nearby_candidates_checked": public_checks,
        "review_status": "pending_visual_review",
    }


def _nearest_cut_distance(value: float, cuts: list[float]) -> float | None:
    if not cuts:
        return None
    return round(min(abs(value - cut) for cut in cuts), 6)


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


def _analysis_frame_batch(analysis: dict[str, Any]) -> Any:
    paths = [
        Path(str(shot.get("selected_frame_path", "")))
        for shot in analysis.get("shots", [])
    ]
    if not paths or any(not path.is_file() for path in paths):
        raise AdsArtError("El análisis no contiene todos los frames locales esperados.")
    return torch.cat([load_image_tensor(path) for path in paths], dim=0)


class AdsArtGeminiAnalyzeCommercial:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("ADS_ART_PROJECT",),
                "video_path": ("STRING", {"default": ""}),
                "model": ([GEMINI_MODEL_ID], {"default": GEMINI_MODEL_ID}),
                "adaptation_mode": (
                    ["faithful_reference", "creative_reinterpretation"],
                    {"default": "faithful_reference"},
                ),
                "max_shots": ("INT", {"default": 3, "min": 1, "max": 24}),
                "scene_threshold": (
                    "FLOAT",
                    {"default": 0.22, "min": 0.02, "max": 1.0, "step": 0.01},
                ),
                "min_shot_seconds": (
                    "FLOAT",
                    {"default": 0.5, "min": 0.1, "max": 30.0, "step": 0.1},
                ),
                "analysis_fps": (
                    "FLOAT",
                    {"default": 6.0, "min": 0.5, "max": 30.0, "step": 0.5},
                ),
                "identity_approved": ("BOOLEAN", {"default": False}),
                "confirm_gemini_analysis": ("BOOLEAN", {"default": False}),
                "reuse_matching_analysis": ("BOOLEAN", {"default": True}),
                "allow_retry_after_unknown": ("BOOLEAN", {"default": False}),
                "upload_retries": ("INT", {"default": 2, "min": 1, "max": 2}),
                "file_poll_attempts": ("INT", {"default": 60, "min": 1, "max": 120}),
            },
            "optional": {"approved_identity": ("IMAGE",)},
        }

    RETURN_TYPES = ("ADS_ART_ANALYSIS", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("analysis", "proposed_frames", "analysis_status", "prompt_preview")
    FUNCTION = "analyze"
    CATEGORY = "Ads Art/02 Commercial"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "Prepara o ejecuta una sola llamada Gemini validada, cruza timestamps con cortes "
        "locales y extrae candidatos nítidos. No genera medios."
    )

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def analyze(
        self,
        project,
        video_path,
        model,
        adaptation_mode,
        max_shots,
        scene_threshold,
        min_shot_seconds,
        analysis_fps,
        identity_approved,
        confirm_gemini_analysis,
        reuse_matching_analysis,
        allow_retry_after_unknown,
        upload_retries,
        file_poll_attempts,
        approved_identity=None,
    ):
        node_started = time.monotonic()
        project_data = parse_json(project, "project")
        if model != GEMINI_MODEL_ID:
            raise AdsArtError(
                f"Ads Art requiere exactamente {GEMINI_MODEL_ID}; no hay fallback automático."
            )
        source = resolve_input_path(video_path)
        max_shots = int(max_shots)
        metadata = _probe_video_metadata(source)
        cuts, decoded_duration, detections = _shot_boundaries(
            source,
            float(scene_threshold),
            float(min_shot_seconds),
            float(analysis_fps),
        )
        duration = max(float(metadata["duration_seconds"]), float(decoded_duration))
        metadata["duration_seconds"] = round(duration, 6)
        cuts = sorted({round(min(max(float(value), 0.0), duration), 6) for value in cuts})
        if not cuts or cuts[0] != 0.0:
            cuts.insert(0, 0.0)

        store = ProjectStore(project_data["project_id"])
        identity_path: Path | None = None
        identity_was_supplied = approved_identity is not None and bool(identity_approved)
        identity_pending_note = None
        if approved_identity is not None and not bool(identity_approved):
            identity_pending_note = (
                "Se conectó una identidad, pero identity_approved=false; no se enviará a Gemini."
            )
        if identity_was_supplied:
            identity_path = store.path("references", "gemini", "approved_identity.png")
            save_image_tensor(approved_identity, identity_path)

        knowledge = load_knowledge()
        local_observation = {
            "source_filename": source.name,
            "duration_seconds": round(duration, 6),
            "width": metadata["width"],
            "height": metadata["height"],
            "fps": metadata["fps"],
            "has_audio": metadata["has_audio"],
            "gemini_video_processing": {
                "mode": "static_generate_content",
                "video_sampling_fps": GEMINI_GENERATION_CONFIG["video_sampling_fps"],
                "audio_included": bool(metadata["has_audio"]),
                "audio_processing": (
                    "File API audio stream; documented 1 Kbps mono and 32 tokens/second"
                    if metadata["has_audio"]
                    else "no audio stream detected"
                ),
                "audio_pricing_is_separate_from_video": True,
            },
            "detector": {
                "type": "local_mean_absolute_visual_change",
                "scene_threshold": float(scene_threshold),
                "min_shot_seconds": float(min_shot_seconds),
                "analysis_fps": float(analysis_fps),
                "cut_timestamps": cuts,
                "detections": detections,
            },
        }
        system_instruction, prompt = build_gemini_prompt(
            project_data,
            knowledge,
            local_observation,
            max_shots,
            adaptation_mode,
            identity_was_supplied,
        )
        local_preflight_seconds = round(time.monotonic() - node_started, 3)
        signature = {
            "video_sha256": sha256_file(source),
            "video_bytes": source.stat().st_size,
            "identity_sha256": sha256_file(identity_path) if identity_path else None,
            "identity_approved": identity_was_supplied,
            "controls": project_data.get("controls", {}),
            "knowledge_sha256": stable_fingerprint(knowledge),
            "model": GEMINI_MODEL_ID,
            "generation_config": GEMINI_GENERATION_CONFIG,
            "prompt_version": GEMINI_PROMPT_VERSION,
            "schema_version": GEMINI_SCHEMA_VERSION,
            "adaptation_mode": adaptation_mode,
            "max_shots": max_shots,
            "local_detector": local_observation["detector"],
        }
        cache_key = stable_fingerprint(signature)
        cache_relative = f"analysis/gemini/cache/{cache_key}.json"
        marker_relative = f"analysis/gemini/state/{cache_key}.json"
        cached = store.read_json(cache_relative) if bool(reuse_matching_analysis) else None
        if cached and cached.get("status") == "completed":
            cached["cache_reused_at"] = utc_now()
            report = self._report(cached, cache_hit=True)
            return _ui_result(
                (json_dumps(cached), _analysis_frame_batch(cached), report, cached["gemini"]["prompt"]),
                report,
            )

        if not bool(confirm_gemini_analysis):
            analysis = self._prepare_local_only(
                project_data=project_data,
                source=source,
                metadata=metadata,
                cuts=cuts,
                detections=detections,
                max_shots=max_shots,
                signature=signature,
                cache_key=cache_key,
                prompt=prompt,
                system_instruction=system_instruction,
                identity_was_supplied=identity_was_supplied,
                identity_pending_note=identity_pending_note,
            )
            record = store.write_json(
                f"analysis/gemini/prepared/{cache_key}.json", analysis
            )
            analysis["record_path"] = str(record)
            report = self._report(analysis, cache_hit=False)
            return _ui_result(
                (json_dumps(analysis), _analysis_frame_batch(analysis), report, prompt),
                report,
            )

        marker = store.read_json(marker_relative)
        if (
            marker
            and marker.get("status") in {"analysis_started", "analysis_unknown"}
            and not bool(allow_retry_after_unknown)
        ):
            raise AdsArtError(
                "Ya existe un análisis Gemini iniciado o incierto para esta misma huella. "
                "No se repetirá automáticamente. Revise su registro y active "
                "allow_retry_after_unknown sólo tras confirmar que no existe respuesta reutilizable."
            )
        prior_attempts = int((marker or {}).get("inference_attempts", 0) or 0)
        started_marker = {
            "schema_version": GEMINI_SCHEMA_VERSION,
            "status": "analysis_started",
            "cache_key": cache_key,
            "signature": signature,
            "model": GEMINI_MODEL_ID,
            "started_at": utc_now(),
            "inference_attempts": prior_attempts + 1,
            "manual_retry_override_used": bool(marker and allow_retry_after_unknown),
            "api_key_persisted": False,
        }
        store.write_json(marker_relative, started_marker)
        try:
            call_result = call_gemini_analysis(
                video_path=source,
                approved_identity_path=identity_path,
                system_instruction=system_instruction,
                prompt=prompt,
                response_schema=gemini_analysis_schema(max_shots),
                source_has_audio=bool(metadata["has_audio"]),
                duration_seconds=duration,
                upload_retries=int(upload_retries),
                file_poll_attempts=int(file_poll_attempts),
            )
            response = validate_gemini_response(
                call_result["response"],
                duration_seconds=duration,
                max_shots=max_shots,
                allowed_camera_ids={item["id"] for item in knowledge["concepts"]},
            )
            extraction_started = time.monotonic()
            analysis = self._materialize_response(
                project_data=project_data,
                source=source,
                metadata=metadata,
                cuts=cuts,
                detections=detections,
                response=response,
                call_result=call_result,
                signature=signature,
                cache_key=cache_key,
                prompt=prompt,
                system_instruction=system_instruction,
                identity_was_supplied=identity_was_supplied,
            )
            call_result["timings"]["frame_extraction_seconds"] = round(
                time.monotonic() - extraction_started, 3
            )
            call_result["timings"]["local_preflight_seconds"] = local_preflight_seconds
            call_result["timings"]["total_node_seconds"] = round(
                time.monotonic() - node_started, 3
            )
        except Exception as exc:
            started_marker.update(
                {
                    "status": "analysis_unknown",
                    "failed_at": utc_now(),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "automatic_retry_performed": False,
                }
            )
            store.write_json(marker_relative, started_marker)
            raise

        cache_path = store.write_json(cache_relative, analysis)
        analysis["record_path"] = str(cache_path)
        store.write_json("analysis/commercial.json", analysis)
        store.write_json(
            marker_relative,
            {
                **started_marker,
                "status": "completed",
                "completed_at": utc_now(),
                "cache_path": str(cache_path),
            },
        )
        report = self._report(analysis, cache_hit=False)
        return _ui_result(
            (json_dumps(analysis), _analysis_frame_batch(analysis), report, prompt),
            report,
        )

    def _prepare_local_only(
        self,
        *,
        project_data: dict[str, Any],
        source: Path,
        metadata: dict[str, Any],
        cuts: list[float],
        detections: list[dict[str, float]],
        max_shots: int,
        signature: dict[str, Any],
        cache_key: str,
        prompt: str,
        system_instruction: str,
        identity_was_supplied: bool,
        identity_pending_note: str | None,
    ) -> dict[str, Any]:
        duration = float(metadata["duration_seconds"])
        selected_starts, truncated = _evenly_limit(cuts, max_shots)
        frame_dir = ProjectStore(project_data["project_id"]).directory(
            "frames", "gemini_preflight", cache_key
        )
        shots: list[dict[str, Any]] = []
        for index, start in enumerate(selected_starts, 1):
            end = next((cut for cut in cuts if cut > start), duration)
            if end <= start:
                end = duration
            midpoint = round((start + end) / 2.0, 6)
            quality = _select_clean_candidate_frame(
                source,
                [midpoint],
                start,
                end,
                cuts[1:],
                frame_dir / f"shot_{index:03d}.png",
            )
            uncertainty = [
                "Gemini no se ejecutó; observación semántica, motivo editorial y prompts pendientes."
            ]
            if identity_pending_note:
                uncertainty.append(identity_pending_note)
            shots.append(
                {
                    "shot_id": f"shot_{index:03d}",
                    "index": index,
                    "start_seconds": round(start, 6),
                    "end_seconds": round(end, 6),
                    "representative_timestamp": quality["selected_timestamp"],
                    "selected_frame_path": quality["selected_frame_path"],
                    "review": {"approved": False, "notes": ""},
                    "verified_local": {
                        "cut_interval": [round(start, 6), round(end, 6)],
                        "frame_quality": quality,
                    },
                    "gemini_observed": {
                        "description": "",
                        "selection_reason": "",
                        "candidate_timestamps": [midpoint],
                    },
                    "gemini_proposal": {},
                    "uncertainties": uncertainty,
                    "contradictions": [],
                }
            )
        return {
            "schema_version": GEMINI_SCHEMA_VERSION,
            "project_id": project_data["project_id"],
            "source_video_path": str(source),
            "created_at": utc_now(),
            "status": "prepared_not_called",
            "verified": metadata,
            "detector": {
                "type": "local_mean_absolute_visual_change",
                "detections": detections,
                "cut_timestamps": cuts,
                "shot_limit_applied": truncated,
            },
            "shots": shots,
            "gemini": {
                "model": GEMINI_MODEL_ID,
                "prompt_version": GEMINI_PROMPT_VERSION,
                "schema_version": GEMINI_SCHEMA_VERSION,
                "cache_key": cache_key,
                "signature": signature,
                "credentials_configured": gemini_credentials_configured(),
                "confirm_gemini_analysis": False,
                "remote_calls": 0,
                "identity_supplied": identity_was_supplied,
                "system_instruction": system_instruction,
                "prompt": prompt,
                "generation_config": GEMINI_GENERATION_CONFIG,
                "response": None,
                "usage": None,
                "cost": {
                    "kind": "not_available_before_call",
                    "amount_usd": None,
                    "observed_charge_usd": None,
                },
            },
            "original_video_forwarded_to_seedance": False,
            "original_audio_forwarded_to_seedance": False,
        }

    def _materialize_response(
        self,
        *,
        project_data: dict[str, Any],
        source: Path,
        metadata: dict[str, Any],
        cuts: list[float],
        detections: list[dict[str, float]],
        response: dict[str, Any],
        call_result: dict[str, Any],
        signature: dict[str, Any],
        cache_key: str,
        prompt: str,
        system_instruction: str,
        identity_was_supplied: bool,
    ) -> dict[str, Any]:
        store = ProjectStore(project_data["project_id"])
        frame_dir = store.directory("frames", "gemini", cache_key)
        shots: list[dict[str, Any]] = []
        for index, raw in enumerate(response["shots"], 1):
            observed = raw["observed"]
            proposal = raw["proposal"]
            start = float(observed["start_seconds"])
            end = float(observed["end_seconds"])
            quality = _select_clean_candidate_frame(
                source,
                list(observed["candidate_timestamps"]),
                start,
                end,
                cuts[1:],
                frame_dir / f"{raw['shot_id']}.png",
            )
            uncertainties = list(raw["uncertainties"])
            start_distance = _nearest_cut_distance(start, cuts)
            end_distance = _nearest_cut_distance(end, cuts + [metadata["duration_seconds"]])
            if start_distance is not None and start_distance > 0.75:
                uncertainties.append(
                    f"Inicio Gemini {start:.3f}s no coincide con un corte local cercano."
                )
            if end_distance is not None and end_distance > 0.75:
                uncertainties.append(
                    f"Fin Gemini {end:.3f}s no coincide con un corte local cercano."
                )
            if not quality["transition_avoidance_succeeded"]:
                uncertainties.append(
                    "Todos los candidatos cercanos quedaron junto a un corte; revisión manual necesaria."
                )
            shots.append(
                {
                    "shot_id": raw["shot_id"],
                    "index": index,
                    "start_seconds": round(start, 6),
                    "end_seconds": round(end, 6),
                    "representative_timestamp": quality["selected_timestamp"],
                    "selected_frame_path": quality["selected_frame_path"],
                    "review": {"approved": False, "notes": ""},
                    "verified_local": {
                        "gemini_interval_within_duration": True,
                        "distance_from_start_to_local_cut_seconds": start_distance,
                        "distance_from_end_to_local_cut_seconds": end_distance,
                        "frame_quality": quality,
                    },
                    "gemini_observed": observed,
                    "gemini_proposal": proposal,
                    "uncertainties": uncertainties,
                    "contradictions": raw["contradictions"],
                }
            )
        return {
            "schema_version": GEMINI_SCHEMA_VERSION,
            "project_id": project_data["project_id"],
            "source_video_path": str(source),
            "created_at": utc_now(),
            "status": "completed",
            "analysis_summary": response["analysis_summary"],
            "global_missing_information": response["global_missing_information"],
            "verified": metadata,
            "detector": {
                "type": "local_mean_absolute_visual_change",
                "detections": detections,
                "cut_timestamps": cuts,
            },
            "shots": shots,
            "gemini": {
                "model": GEMINI_MODEL_ID,
                "prompt_version": GEMINI_PROMPT_VERSION,
                "schema_version": GEMINI_SCHEMA_VERSION,
                "cache_key": cache_key,
                "signature": signature,
                "credentials_configured": True,
                "confirm_gemini_analysis": True,
                "remote_calls": 1,
                "identity_supplied": identity_was_supplied,
                "system_instruction": system_instruction,
                "prompt": prompt,
                "generation_config": GEMINI_GENERATION_CONFIG,
                "response": response,
                "provider": call_result["provider"],
                "timings": call_result["timings"],
                "usage": call_result["usage"],
                "cost": call_result["cost_estimate"],
            },
            "original_video_forwarded_to_seedance": False,
            "original_audio_forwarded_to_seedance": False,
        }

    def _report(self, analysis: dict[str, Any], cache_hit: bool) -> str:
        status = str(analysis.get("status", "unknown")).upper()
        lines = [
            f"Gemini: {status}",
            f"Modelo fijo: {GEMINI_MODEL_ID}",
            f"Caché: {'REUTILIZADA' if cache_hit else 'sin coincidencia reutilizada'}",
            f"Tomas propuestas: {len(analysis.get('shots', []))}",
            "Aprobaciones visuales inferidas: NO",
            (
                "Gemini video: "
                f"{GEMINI_GENERATION_CONFIG['video_sampling_fps']:.1f} FPS | "
                f"max_output_tokens={GEMINI_GENERATION_CONFIG['max_output_tokens']} | "
                f"thinking_budget={GEMINI_GENERATION_CONFIG['thinking_budget']}"
            ),
        ]
        if status == "PREPARED_NOT_CALLED":
            lines.append("Llamadas remotas: 0. Active confirm_gemini_analysis sólo para ejecutar.")
        for shot in analysis.get("shots", []):
            reason = shot.get("gemini_observed", {}).get("selection_reason") or "pendiente de Gemini"
            lines.append(
                f"- {shot['shot_id']}: {shot['start_seconds']:.3f}-{shot['end_seconds']:.3f}s | "
                f"frame {shot['representative_timestamp']:.3f}s | {reason}"
            )
            observed = shot.get("gemini_observed") or {}
            proposal = shot.get("gemini_proposal") or {}
            if observed.get("description"):
                lines.append("  OBSERVADO: " + str(observed["description"]))
            if proposal:
                lines.extend(
                    [
                        "  PROPUESTA: " + str(proposal.get("objective", "")),
                        "  PROMPT NANO BANANA PRO: "
                        + str(proposal.get("nano_banana_prompt", "")),
                        "  DIRECCIÓN SEEDANCE: "
                        + json_dumps(proposal.get("seedance", {})),
                    ]
                )
            if shot.get("uncertainties"):
                lines.append("  PENDIENTE: " + " | ".join(shot["uncertainties"]))
        missing = analysis.get("global_missing_information", [])
        if missing:
            lines.append("Información faltante: " + " | ".join(missing))
        return "\n".join(lines)


class AdsArtGeminiShotDraft:
    @classmethod
    def INPUT_TYPES(cls):
        multiline = {"multiline": True, "default": ""}
        return {
            "required": {
                "analysis": ("ADS_ART_ANALYSIS",),
                "shot_number": ("INT", {"default": 1, "min": 1, "max": 24}),
                "manual_objective": ("STRING", multiline),
                "manual_action": ("STRING", multiline),
                "manual_camera_concepts": ("STRING", multiline),
                "manual_framing_and_composition": ("STRING", multiline),
                "manual_lighting": ("STRING", multiline),
                "manual_elements_to_preserve": ("STRING", multiline),
                "manual_planned_changes": ("STRING", multiline),
                "manual_nano_banana_prompt": ("STRING", multiline),
                "manual_seedance_performance": ("STRING", multiline),
                "manual_seedance_camera_movement": ("STRING", multiline),
                "manual_seedance_rhythm": ("STRING", multiline),
                "manual_seedance_continuity": ("STRING", multiline),
            }
        }

    RETURN_TYPES = ("ADS_ART_SHOT_DRAFT", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("shot_draft", "selected_frame", "frame_prompt", "seedance_prompt")
    FUNCTION = "materialize"
    CATEGORY = "Ads Art/04 Shot Planning"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "Materializa campos Gemini como valores por defecto. Los overrides manuales no vacíos "
        "se guardan y nunca se sobrescriben al reanalizar."
    )

    def materialize(self, analysis, shot_number, **manual_values):
        data = parse_json(analysis, "analysis")
        index = int(shot_number) - 1
        if index < 0 or index >= len(data.get("shots", [])):
            raise AdsArtError("shot_number está fuera del análisis Gemini.")
        shot = data["shots"][index]
        proposal = shot.get("gemini_proposal") or {}
        seedance = proposal.get("seedance") or {}
        store = ProjectStore(data["project_id"])
        override_relative = f"analysis/gemini/manual_overrides/{shot['shot_id']}.json"
        previous = store.read_json(override_relative) or {}
        provided = {
            key.removeprefix("manual_"): str(value or "").strip()
            for key, value in manual_values.items()
            if str(value or "").strip()
        }
        preserved_overrides = dict(previous.get("values", {}))
        preserved_overrides.update(provided)
        if preserved_overrides:
            store.write_json(
                override_relative,
                {
                    "schema_version": "1.0.0",
                    "shot_id": shot["shot_id"],
                    "updated_at": utc_now(),
                    "values": preserved_overrides,
                    "policy": "nonempty_manual_values_override_gemini_and_survive_reanalysis",
                },
            )

        replacements = [f"Replace: {item}" for item in proposal.get("elements_to_replace", [])]
        removals = [f"Remove: {item}" for item in proposal.get("elements_to_remove", [])]
        generated = {
            "objective": str(proposal.get("objective", "")),
            "action": str(proposal.get("action", "")),
            "camera_concepts": ", ".join(proposal.get("camera_concept_ids", [])),
            "framing_and_composition": str(proposal.get("framing_and_composition", "")),
            "lighting": str(proposal.get("lighting", "")),
            "elements_to_preserve": "\n".join(proposal.get("elements_to_preserve", [])),
            "planned_changes": "\n".join([*removals, *replacements]),
            "nano_banana_prompt": str(proposal.get("nano_banana_prompt", "")),
            "seedance_performance": str(seedance.get("performance", "")),
            "seedance_camera_movement": str(seedance.get("camera_movement", "")),
            "seedance_rhythm": str(seedance.get("rhythm", "")),
            "seedance_continuity": str(seedance.get("continuity", "")),
        }
        effective = {
            key: preserved_overrides.get(key, value)
            for key, value in generated.items()
        }
        draft = {
            "schema_version": "1.0.0",
            "project_id": data["project_id"],
            "shot_id": shot["shot_id"],
            "shot_number": int(shot_number),
            "selected_frame_path": shot["selected_frame_path"],
            "representative_timestamp": shot["representative_timestamp"],
            "observed": shot.get("gemini_observed", {}),
            "generated": generated,
            "manual_overrides": preserved_overrides,
            "effective": effective,
            "uncertainties": shot.get("uncertainties", []),
            "contradictions": shot.get("contradictions", []),
            "visual_approval_inferred": False,
            "updated_at": utc_now(),
        }
        frame_prompt = effective["nano_banana_prompt"]
        seedance_prompt = "\n\n".join(
            [
                f"PERFORMANCE:\n{effective['seedance_performance']}",
                f"CAMERA MOVEMENT:\n{effective['seedance_camera_movement']}",
                f"RHYTHM:\n{effective['seedance_rhythm']}",
                f"CONTINUITY:\n{effective['seedance_continuity']}",
            ]
        )
        report = (
            f"{shot['shot_id']} | frame {shot['representative_timestamp']:.3f}s | APROBACIÓN PENDIENTE\n"
            f"Motivo: {shot.get('gemini_observed', {}).get('selection_reason') or '(pendiente)'}\n\n"
            f"OBJETIVO:\n{effective['objective']}\n\nACCIÓN:\n{effective['action']}\n\n"
            f"ENCUADRE:\n{effective['framing_and_composition']}\n\nILUMINACIÓN:\n{effective['lighting']}\n\n"
            f"PROMPT NANO BANANA PRO:\n{frame_prompt}\n\nDIRECCIÓN SEEDANCE:\n{seedance_prompt}\n\n"
            "Los campos manual_* no vacíos prevalecen y se conservan al reejecutar."
        )
        return _ui_result(
            (json_dumps(draft), load_image_tensor(shot["selected_frame_path"]), frame_prompt, seedance_prompt),
            report,
        )


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
            },
            "optional": {"gemini_draft": ("ADS_ART_SHOT_DRAFT",)},
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
        gemini_draft=None,
    ):
        project_data = parse_json(project, "project")
        analysis_data = parse_json(analysis, "analysis")
        index = int(shot_number) - 1
        if index < 0 or index >= len(analysis_data.get("shots", [])):
            raise AdsArtError("shot_number está fuera del rango analizado.")
        shot = analysis_data["shots"][index]
        draft_data: dict[str, Any] = {}
        if gemini_draft:
            parsed_draft = parse_json(gemini_draft, "gemini_draft")
            if parsed_draft.get("project_id") != project_data.get("project_id"):
                raise AdsArtError("El borrador Gemini pertenece a otro proyecto.")
            if parsed_draft.get("shot_id") != shot.get("shot_id"):
                raise AdsArtError("El borrador Gemini no corresponde a la toma seleccionada.")
            draft_data = parsed_draft.get("effective") or {}

        def manual_or_draft(manual_value: Any, draft_key: str) -> str:
            manual_text = str(manual_value or "").strip()
            return manual_text if manual_text else str(draft_data.get(draft_key, "") or "").strip()

        objective = manual_or_draft(objective, "objective")
        action = manual_or_draft(action, "action")
        camera_concepts = manual_or_draft(camera_concepts, "camera_concepts")
        framing_and_composition = manual_or_draft(framing_and_composition, "framing_and_composition")
        lighting = manual_or_draft(lighting, "lighting")
        elements_to_preserve = manual_or_draft(elements_to_preserve, "elements_to_preserve")
        planned_changes = manual_or_draft(planned_changes, "planned_changes")
        gemini_frame_prompt = str(draft_data.get("nano_banana_prompt", "") or "").strip()
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

GEMINI FRAME RECREATION DRAFT (subordinate to the explicit fields and user controls above):
{gemini_frame_prompt or '(none supplied)'}

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
            metadata={
                "shot_record": shot_record,
                "gemini_draft_connected": bool(draft_data),
                "gemini_frame_prompt_used": gemini_frame_prompt,
                "manual_nonempty_values_override_gemini": True,
                "generated_frame_requires_user_approval": True,
            },
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
                "approved_frame_observations": ("STRING", {"multiline": True, "default": ""}),
                "seedance_prompt_adjustments": ("STRING", {"multiline": True, "default": ""}),
                "generated_duration_seconds": ("INT", {"default": 5, "min": 4, "max": 30}),
                "final_edit_duration_seconds": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 120.0, "step": 0.1}),
                "video_aspect_ratio": (list(VIDEO_ASPECT_RATIOS), {"default": "auto"}),
                "approve_aspect_adaptation": ("BOOLEAN", {"default": False}),
                "resolution": (list(VIDEO_RESOLUTIONS), {"default": "1080p"}),
                "generate_native_audio": ("BOOLEAN", {"default": False}),
                "bitrate_mode": (["standard", "high"], {"default": "standard"}),
            },
            "optional": {
                "approved_end_frame": ("IMAGE",),
                "gemini_draft": ("ADS_ART_SHOT_DRAFT",),
            },
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
        approved_frame_observations,
        seedance_prompt_adjustments,
        generated_duration_seconds,
        final_edit_duration_seconds,
        video_aspect_ratio,
        approve_aspect_adaptation,
        resolution,
        generate_native_audio,
        bitrate_mode,
        approved_end_frame=None,
        gemini_draft=None,
    ):
        project_data = parse_json(project, "project")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", (shot_id or "").strip()):
            raise AdsArtError("shot_id no es válido.")
        store = ProjectStore(project_data["project_id"])
        shot_id = shot_id.strip()
        draft_data: dict[str, Any] = {}
        if gemini_draft:
            parsed_draft = parse_json(gemini_draft, "gemini_draft")
            if parsed_draft.get("project_id") != project_data.get("project_id"):
                raise AdsArtError("El borrador Gemini pertenece a otro proyecto.")
            if parsed_draft.get("shot_id") != shot_id:
                raise AdsArtError("El borrador Gemini no corresponde a shot_id.")
            draft_data = parsed_draft.get("effective") or {}

        def manual_or_draft(manual_value: Any, draft_key: str) -> str:
            manual_text = str(manual_value or "").strip()
            return manual_text if manual_text else str(draft_data.get(draft_key, "") or "").strip()

        performance = manual_or_draft(performance, "seedance_performance")
        camera_trajectory = manual_or_draft(camera_trajectory, "seedance_camera_movement")
        rhythm = manual_or_draft(rhythm, "seedance_rhythm")
        continuity = manual_or_draft(continuity, "seedance_continuity")
        approved_frame_observations = str(approved_frame_observations or "").strip()
        seedance_prompt_adjustments = str(seedance_prompt_adjustments or "").strip()
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

OBSERVATIONS FROM THE USER-APPROVED RECREATED FRAME:
{approved_frame_observations or '(none supplied; inspect the recreated frame before approval)'}

POST-APPROVAL SEEDANCE ADJUSTMENTS:
{seedance_prompt_adjustments or '(none supplied)'}

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
                "gemini_draft_connected": bool(draft_data),
                "manual_nonempty_values_override_gemini": True,
                "prompt_updated_from_approved_frame": bool(
                    approved_frame_observations or seedance_prompt_adjustments
                ),
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
    "AdsArtGeminiAnalyzeCommercial": AdsArtGeminiAnalyzeCommercial,
    "AdsArtGeminiShotDraft": AdsArtGeminiShotDraft,
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
    "AdsArtGeminiAnalyzeCommercial": "Ads Art — Gemini Commercial Analysis",
    "AdsArtGeminiShotDraft": "Ads Art — Gemini Shot Draft & Manual Overrides",
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
